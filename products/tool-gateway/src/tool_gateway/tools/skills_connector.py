"""Skills connector (SPEC-014 R-4).

Read-only access to the skills-hub retrieval API. Provides three tools:
  - skills.search
  - skills.get
  - skills.list

All tools call skills-hub over HTTP with a gateway-held Basic query
credential. Upstream failures map to structured error results; every
outcome carries the standard evidence envelope. The connector is only
registered when ``GATEWAY_SKILLS_SERVICE_URL`` is set.
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

SOURCE_SYSTEM = "skills"
REQUEST_TIMEOUT_SECONDS = 10.0
MAX_RESULTS = 20
DEFAULT_RESULTS = 5
SEARCH_PATH = "/api/v1/skills/search"
LIST_PATH = "/api/v1/skills"
SKILL_PATH_TEMPLATE = "/api/v1/skills/{skill_id}"
# Contract pattern from shared/shared-contracts/schemas/skill.schema.json.
# The id is interpolated into the upstream URL path, so it must be validated
# before use: anything else is untrusted LLM input and could inject path or
# query segments into the gateway's authenticated request.
_SKILL_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*(/[a-z0-9][a-z0-9-]*)+$")

# Keys projected into skills.search matches; everything else upstream
# returns (score, description, tags, ...) is dropped to keep the tool
# payload stable for the agent and the evidence panel.
_MATCH_KEYS = (
    "skill_id",
    "title",
    "excerpt",
    "source_id",
    "source_path",
    "source_ref",
    "updated_at",
)

# Keys projected into skills.list entries (summaries carry description
# and tags, which stay useful for discovery; bodies never leave via list).
_LIST_KEYS = (
    "skill_id",
    "title",
    "description",
    "source_id",
    "tags",
    "updated_at",
)


class SkillsConnector:
    """Registers read-only skills tools backed by the skills-hub API."""

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
        """Register all skills tools with the given registry."""
        registry.register(SearchSkillsTool(self))
        registry.register(GetSkillTool(self))
        registry.register(ListSkillsTool(self))

    async def _get(
        self,
        path: str,
        params: dict | None = None,
        request_id: str | None = None,
    ) -> httpx.Response:
        """Issue an authenticated GET against skills-hub.

        Forwards the caller's request id so skills-hub usage audit events
        (SPEC-029 R-3) correlate with this gateway's tool_invoked events.
        """
        headers = {"x-request-id": request_id} if request_id else None
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            return await client.get(
                f"{self._url.rstrip('/')}{path}",
                params=params,
                headers=headers,
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


def _error_from_response(tool_name: str, response: httpx.Response) -> ToolResult:
    """Map an upstream error response to a structured tool error."""
    if response.status_code == 404:
        code, message = "SKILL_NOT_FOUND", "The requested skill was not found."
    else:
        code, message = "UPSTREAM_ERROR", (
            f"skills-hub returned HTTP {response.status_code}."
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


class SearchSkillsTool(BaseTool):
    def __init__(self, connector: SkillsConnector) -> None:
        self._connector = connector

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="skills.search",
            description=(
                "Search team-owned operational skills and runbooks for "
                "procedures, interpretations, and remediation guidance."
            ),
            risk_level="read",
            category="skills",
            parameters_schema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Free-text search terms.",
                    },
                    "source": {
                        "type": "string",
                        "description": "Restrict to one skill source id.",
                    },
                    "tag": {
                        "type": "string",
                        "description": "Restrict to skills carrying this tag.",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_RESULTS,
                        "default": DEFAULT_RESULTS,
                        "description": (
                            f"Maximum matches (default {DEFAULT_RESULTS}, "
                            f"max {MAX_RESULTS})."
                        ),
                    },
                },
            },
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        start = time.perf_counter()
        query = parameters.get("query")
        if not query or not str(query).strip():
            return make_error_result(
                "skills.search", "INVALID_PARAMETERS",
                "Parameter 'query' is required.", source_system=SOURCE_SYSTEM,
            )
        limit, limit_error = _coerce_limit(parameters.get("limit"))
        if limit_error:
            return make_error_result(
                "skills.search", "INVALID_PARAMETERS",
                limit_error, source_system=SOURCE_SYSTEM,
            )

        params: dict = {"q": str(query), "limit": limit}
        if parameters.get("source"):
            params["source"] = str(parameters["source"])
        if parameters.get("tag"):
            params["tag"] = str(parameters["tag"])

        try:
            response = await self._connector._get(
                SEARCH_PATH, params=params, request_id=identity.get("request_id")
            )
        except httpx.HTTPError as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            LOGGER.warning("skills.search transport error: %s", exc)
            return make_error_result(
                "skills.search", "TOOL_EXECUTION_ERROR",
                f"skills-hub unreachable: {exc}",
                source_system=SOURCE_SYSTEM, duration_ms=duration_ms,
            )
        duration_ms = int((time.perf_counter() - start) * 1000)
        if response.status_code != 200:
            return _error_from_response("skills.search", response)

        payload = response.json()
        matches = [
            {key: hit.get(key) for key in _MATCH_KEYS}
            for hit in payload.get("matches", [])
        ]
        return ToolResult(
            tool_name="skills.search",
            status="success",
            data={"matches": matches, "total": len(matches)},
            evidence=build_evidence("read", SOURCE_SYSTEM, duration_ms),
        )


class GetSkillTool(BaseTool):
    def __init__(self, connector: SkillsConnector) -> None:
        self._connector = connector

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="skills.get",
            description="Fetch the full body of one skill by its id.",
            risk_level="read",
            category="skills",
            parameters_schema={
                "type": "object",
                "required": ["skill_id"],
                "properties": {
                    "skill_id": {
                        "type": "string",
                        "description": "Namespaced skill id, e.g. sre-alerting/alerts/kubepodnotready.",
                    },
                },
            },
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        start = time.perf_counter()
        skill_id = parameters.get("skill_id")
        if not skill_id or not str(skill_id).strip():
            return make_error_result(
                "skills.get", "INVALID_PARAMETERS",
                "Parameter 'skill_id' is required.", source_system=SOURCE_SYSTEM,
            )
        if not _SKILL_ID_PATTERN.match(str(skill_id)):
            return make_error_result(
                "skills.get", "INVALID_PARAMETERS",
                "Parameter 'skill_id' is not a valid namespaced skill id "
                "(expected <source_id>/<slug>, lowercase [a-z0-9-]).",
                source_system=SOURCE_SYSTEM,
            )

        path = SKILL_PATH_TEMPLATE.format(skill_id=str(skill_id))
        try:
            response = await self._connector._get(
                path, request_id=identity.get("request_id")
            )
        except httpx.HTTPError as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            LOGGER.warning("skills.get transport error: %s", exc)
            return make_error_result(
                "skills.get", "TOOL_EXECUTION_ERROR",
                f"skills-hub unreachable: {exc}",
                source_system=SOURCE_SYSTEM, duration_ms=duration_ms,
            )
        duration_ms = int((time.perf_counter() - start) * 1000)
        if response.status_code != 200:
            return _error_from_response("skills.get", response)

        return ToolResult(
            tool_name="skills.get",
            status="success",
            data=response.json(),
            evidence=build_evidence("read", SOURCE_SYSTEM, duration_ms),
        )


class ListSkillsTool(BaseTool):
    def __init__(self, connector: SkillsConnector) -> None:
        self._connector = connector

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="skills.list",
            description=(
                "List the skills registered in the skills hub (summaries, "
                "no bodies). Use it to discover what guidance exists; use "
                "skills.search for targeted queries and skills.get for the "
                "full text of one skill."
            ),
            risk_level="read",
            category="skills",
            parameters_schema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Restrict to one skill source id.",
                    },
                    "tag": {
                        "type": "string",
                        "description": "Restrict to skills carrying this tag.",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_RESULTS,
                        "default": MAX_RESULTS,
                        "description": (
                            f"Maximum entries (default and max "
                            f"{MAX_RESULTS}); page further with offset."
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
        limit_raw = parameters.get("limit")
        limit, limit_error = _coerce_limit(
            MAX_RESULTS if limit_raw is None else limit_raw
        )
        if limit_error:
            return make_error_result(
                "skills.list", "INVALID_PARAMETERS",
                limit_error, source_system=SOURCE_SYSTEM,
            )
        offset_raw = parameters.get("offset", 0)
        try:
            offset = int(offset_raw)
        except (TypeError, ValueError):
            return make_error_result(
                "skills.list", "INVALID_PARAMETERS",
                f"Parameter 'offset' must be an integer, got {offset_raw!r}.",
                source_system=SOURCE_SYSTEM,
            )
        if offset < 0:
            return make_error_result(
                "skills.list", "INVALID_PARAMETERS",
                f"Parameter 'offset' must be at least 0, got {offset}.",
                source_system=SOURCE_SYSTEM,
            )

        params: dict = {"limit": limit, "offset": offset}
        if parameters.get("source"):
            params["source"] = str(parameters["source"])
        if parameters.get("tag"):
            params["tag"] = str(parameters["tag"])

        try:
            response = await self._connector._get(
                LIST_PATH, params=params, request_id=identity.get("request_id")
            )
        except httpx.HTTPError as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            LOGGER.warning("skills.list transport error: %s", exc)
            return make_error_result(
                "skills.list", "TOOL_EXECUTION_ERROR",
                f"skills-hub unreachable: {exc}",
                source_system=SOURCE_SYSTEM, duration_ms=duration_ms,
            )
        duration_ms = int((time.perf_counter() - start) * 1000)
        if response.status_code != 200:
            return _error_from_response("skills.list", response)

        payload = response.json()
        entries = [
            {key: entry.get(key) for key in _LIST_KEYS}
            for entry in payload.get("skills", [])
        ]
        return ToolResult(
            tool_name="skills.list",
            status="success",
            data={"skills": entries, "total": payload.get("total", len(entries))},
            evidence=build_evidence("read", SOURCE_SYSTEM, duration_ms),
        )
