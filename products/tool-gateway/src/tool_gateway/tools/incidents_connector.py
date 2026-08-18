"""Incidents connector (SPEC-015 R-4).

Read-only access to the incident-service query API. Provides two tools:
  - incidents.list
  - incidents.get

Both call incident-service over HTTP with a gateway-held Basic query
credential (never the user's token). Upstream failures map to structured
error results; every outcome carries the standard evidence envelope. The
connector is only registered when ``GATEWAY_INCIDENTS_SERVICE_URL`` is set.
No mutating incident tool exists — write-back is internal
service-to-service only, keeping the SPEC-007 read-only invariant.
"""

from __future__ import annotations

import logging
import re
import time

import httpx

from tool_gateway.tools.base import (
    BaseTool,
    ToolDefinition,
    ToolResult,
    build_evidence,
    make_error_result,
)
from tool_gateway.tools.registry import ToolRegistry

LOGGER = logging.getLogger(__name__)

SOURCE_SYSTEM = "incidents"
REQUEST_TIMEOUT_SECONDS = 10.0
MAX_RESULTS = 50
DEFAULT_RESULTS = 20
LIST_PATH = "/api/v1/incidents"
INCIDENT_PATH_TEMPLATE = "/api/v1/incidents/{incident_id}"
# Contract pattern from shared/shared-contracts/schemas/incident.schema.json.
# The id is interpolated into the upstream URL path, so it must be validated
# before use: anything else is untrusted LLM input and could inject path or
# query segments into the gateway's authenticated request.
_INCIDENT_ID_PATTERN = re.compile(r"^inc-[a-z0-9-]+$")

_STATUSES = ("new", "triaging", "triaged", "triage_failed", "resolved")
_SEVERITIES = ("critical", "warning", "info")
_SOURCES = ("alertmanager", "manual")

# Keys projected into incidents.list entries; summaries stay out of the
# list view to match the portal representation.
_LIST_KEYS = (
    "incident_id",
    "fingerprint",
    "source",
    "severity",
    "status",
    "title",
    "labels",
    "reported_by",
    "session_id",
    "created_at",
    "updated_at",
    "resolved_at",
)


class IncidentsConnector:
    """Registers read-only incident tools backed by incident-service."""

    def __init__(
        self,
        url: str = "",
        client_id: str = "",
        client_secret: str = "",
    ) -> None:
        self._url = url
        self._client_id = client_id
        self._client_secret = client_secret

    def register_tools(self, registry: ToolRegistry) -> None:
        """Register all incident tools with the given registry."""
        registry.register(ListIncidentsTool(self))
        registry.register(GetIncidentTool(self))

    async def _get(self, path: str, params: dict | None = None) -> httpx.Response:
        """Issue an authenticated GET against incident-service."""
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            return await client.get(
                f"{self._url.rstrip('/')}{path}",
                params=params,
                auth=(self._client_id, self._client_secret),
            )


def _coerce_limit(value: object) -> tuple[int, str | None]:
    """Clamp limit into [1, MAX_RESULTS]."""
    if value is None:
        return DEFAULT_RESULTS, None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_RESULTS, (
            f"Parameter 'limit' must be an integer, got {value!r}."
        )
    if parsed < 1:
        return DEFAULT_RESULTS, (
            f"Parameter 'limit' must be at least 1, got {parsed}."
        )
    return min(parsed, MAX_RESULTS), None


def _check_enum(tool_name: str, name: str, value: object, allowed: tuple[str, ...]) -> str | None:
    """Validate an optional enum parameter; returns an error message or None."""
    if value is None:
        return None
    if str(value) not in allowed:
        return (
            f"Parameter '{name}' must be one of {', '.join(allowed)}, "
            f"got {value!r}."
        )
    return None


def _error_from_response(tool_name: str, response: httpx.Response) -> ToolResult:
    """Map an upstream error response to a structured tool error."""
    if response.status_code == 404:
        code, message = (
            "INCIDENT_NOT_FOUND",
            "The requested incident was not found.",
        )
    else:
        code, message = "UPSTREAM_ERROR", (
            f"incident-service returned HTTP {response.status_code}."
        )
    try:
        payload = response.json()
        upstream = payload.get("error", {}) if isinstance(payload, dict) else {}
        if isinstance(upstream, dict):
            if response.status_code != 404 and upstream.get("code"):
                code = str(upstream["code"])
            if upstream.get("message"):
                message = str(upstream["message"])
    except ValueError:
        pass
    return make_error_result(
        tool_name, code, message, source_system=SOURCE_SYSTEM,
    )


# --- Tool implementations ---


class ListIncidentsTool(BaseTool):
    def __init__(self, connector: IncidentsConnector) -> None:
        self._connector = connector

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="incidents.list",
            description=(
                "List tracked incidents, newest first, with optional "
                "status/severity/source filters. Entries carry the incident "
                "state without summaries; use incidents.get for the full "
                "record and its triage report."
            ),
            risk_level="read",
            category="incidents",
            parameters_schema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": list(_STATUSES),
                        "description": "Restrict to one lifecycle status.",
                    },
                    "severity": {
                        "type": "string",
                        "enum": list(_SEVERITIES),
                        "description": "Restrict to one severity.",
                    },
                    "source": {
                        "type": "string",
                        "enum": list(_SOURCES),
                        "description": "Restrict to one intake source.",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_RESULTS,
                        "default": DEFAULT_RESULTS,
                        "description": (
                            f"Maximum entries (default {DEFAULT_RESULTS}, "
                            f"max {MAX_RESULTS})."
                        ),
                    },
                    "offset": {
                        "type": "integer",
                        "minimum": 0,
                        "default": 0,
                        "description": "Entries to skip for pagination.",
                    },
                },
            },
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        start = time.perf_counter()
        for name, allowed in (
            ("status", _STATUSES),
            ("severity", _SEVERITIES),
            ("source", _SOURCES),
        ):
            error = _check_enum("incidents.list", name, parameters.get(name), allowed)
            if error:
                return make_error_result(
                    "incidents.list", "INVALID_PARAMETERS",
                    error, source_system=SOURCE_SYSTEM,
                )
        limit, limit_error = _coerce_limit(parameters.get("limit"))
        if limit_error:
            return make_error_result(
                "incidents.list", "INVALID_PARAMETERS",
                limit_error, source_system=SOURCE_SYSTEM,
            )
        offset_raw = parameters.get("offset", 0)
        try:
            offset = int(offset_raw)
        except (TypeError, ValueError):
            return make_error_result(
                "incidents.list", "INVALID_PARAMETERS",
                f"Parameter 'offset' must be an integer, got {offset_raw!r}.",
                source_system=SOURCE_SYSTEM,
            )
        if offset < 0:
            return make_error_result(
                "incidents.list", "INVALID_PARAMETERS",
                f"Parameter 'offset' must be at least 0, got {offset}.",
                source_system=SOURCE_SYSTEM,
            )

        params: dict = {"limit": limit, "offset": offset}
        for name in ("status", "severity", "source"):
            if parameters.get(name):
                params[name] = str(parameters[name])

        try:
            response = await self._connector._get(LIST_PATH, params=params)
        except httpx.HTTPError as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            LOGGER.warning("incidents.list transport error: %s", exc)
            return make_error_result(
                "incidents.list", "TOOL_EXECUTION_ERROR",
                f"incident-service unreachable: {exc}",
                source_system=SOURCE_SYSTEM, duration_ms=duration_ms,
            )
        duration_ms = int((time.perf_counter() - start) * 1000)
        if response.status_code != 200:
            return _error_from_response("incidents.list", response)

        payload = response.json()
        entries = [
            {key: entry.get(key) for key in _LIST_KEYS if entry.get(key) is not None}
            for entry in payload.get("incidents", [])
        ]
        return ToolResult(
            tool_name="incidents.list",
            status="success",
            data={"incidents": entries, "total": payload.get("total", len(entries))},
            evidence=build_evidence("read", SOURCE_SYSTEM, duration_ms),
        )


class GetIncidentTool(BaseTool):
    def __init__(self, connector: IncidentsConnector) -> None:
        self._connector = connector

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="incidents.get",
            description=(
                "Fetch one incident by id, including its latest triage "
                "report (when present) and connector dispatch outcomes."
            ),
            risk_level="read",
            category="incidents",
            parameters_schema={
                "type": "object",
                "required": ["incident_id"],
                "properties": {
                    "incident_id": {
                        "type": "string",
                        "description": "Incident id, e.g. inc-9f2c1ab34de5.",
                    },
                },
            },
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        start = time.perf_counter()
        incident_id = parameters.get("incident_id")
        if not incident_id or not str(incident_id).strip():
            return make_error_result(
                "incidents.get", "INVALID_PARAMETERS",
                "Parameter 'incident_id' is required.",
                source_system=SOURCE_SYSTEM,
            )
        if not _INCIDENT_ID_PATTERN.match(str(incident_id)):
            return make_error_result(
                "incidents.get", "INVALID_PARAMETERS",
                "Parameter 'incident_id' is not a valid incident id "
                "(expected inc-<lowercase alphanumeric>).",
                source_system=SOURCE_SYSTEM,
            )

        path = INCIDENT_PATH_TEMPLATE.format(incident_id=str(incident_id))
        try:
            response = await self._connector._get(path)
        except httpx.HTTPError as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            LOGGER.warning("incidents.get transport error: %s", exc)
            return make_error_result(
                "incidents.get", "TOOL_EXECUTION_ERROR",
                f"incident-service unreachable: {exc}",
                source_system=SOURCE_SYSTEM, duration_ms=duration_ms,
            )
        duration_ms = int((time.perf_counter() - start) * 1000)
        if response.status_code != 200:
            return _error_from_response("incidents.get", response)

        return ToolResult(
            tool_name="incidents.get",
            status="success",
            data=response.json(),
            evidence=build_evidence("read", SOURCE_SYSTEM, duration_ms),
        )
