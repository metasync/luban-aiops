"""Native read-only ServiceNow Table-API connector (SPEC-067 R-2, OQ-3 fallback).

The transport taken at Stage-0 (read-only 2026-10-19 on the operator's PDI
``dev417985``): ServiceNow's own MCP server is **unavailable** there — a
provisioning/entitlement gap, not a release gap — so the pilot binds the
documented **REST/Table-API fallback** rather than reusing SPEC-069's generic
MCP adapter. This connector mirrors the shipped ``ansible_native.py``: it
registers the *same* SPEC-007 ``BaseTool``/``ToolDefinition``/``ToolRegistry``
seam, so a caller sees a ``servicenow.*`` read tool exactly as it sees an
``ansible.*`` one, and the kernel reaches it through the existing signed-tool
path (SPEC-037) — **no new kernel seam, and the kernel never becomes an MCP
client**. **No new dependency**: the REST path uses ``httpx`` (already present);
``mcp>=2.3`` (added by SPEC-069) is unused here.

Four hard safety rules, all enforced in the connector (never left to the model):

* **Fixed table.** Each tool's ServiceNow table is gateway-owned binding config
  (:mod:`~tool_gateway.ingestion.servicenow_binding`), never a model argument,
  so the URL path segment can never be model-selected.
* **Allowlisted field projection.** Every record is projected down to the
  tool's declared ``fields`` allowlist *after* the response arrives, so even a
  target (or mock) that returns extra columns can never leak one — a
  ``sys_user`` ``password``/``user_password`` hash is dropped by construction,
  not by luck. ``sysparm_fields`` also restricts the request.
* **Read tier only.** Every admitted tool is ``risk_level="read"``; there is no
  POST/PUT/PATCH/DELETE anywhere in this module. Writes stay behind the
  existing HITL/signed-execution path.
* **Fail closed, never fabricate.** A transport timeout/connect failure, a
  non-2xx upstream, or an unparseable body is a structured **error** outcome
  with a reason — never an empty "success" (SPEC-067 R-5; the deliberate
  inverse of ``http.get``, whose job is to *report* a status, whereas a
  ServiceNow record read that got a 404/401/500 did **not** get the record).

The credential is operator configuration (a single named set bound at
construction), **not** a model-supplied parameter, and it resolves through the
SPEC-068 seam (:func:`~tool_gateway.tools.auth_resolution.resolve_outbound_auth`)
— no pilot-local re-implementation. Only the set **name** can ever surface; an
acquired token flows straight into the client and never into a result, evidence
field, or log line. The base URL, credential set, and timeout are operator
config, never model-selected arguments.

``identity`` (the requester) is **not** forwarded to the target: the connector
addresses ServiceNow with the gateway's own acting-service credential
(``target_identity_mode = acting_service``); per-user delegation to the target
is SPEC-070's production seam and is deliberately not wired here. The requester
identity still flows through the gateway's audit path (SPEC-067 R-4).
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from tool_gateway.tools.auth_resolution import resolve_outbound_auth
from tool_gateway.tools.base import (
    BaseTool,
    ToolDefinition,
    ToolResult,
    build_evidence,
    make_error_result,
)
from tool_gateway.tools.credential_sets import CredentialSetStore
from tool_gateway.tools.oauth_client import OAuth2TokenClient
from tool_gateway.tools.registry import ToolRegistry

LOGGER = logging.getLogger(__name__)

SOURCE_SYSTEM = "servicenow"
CATEGORY = "servicenow"

DEFAULT_TIMEOUT_MS = 10000
MAX_TIMEOUT_MS = 30000
# Bound a read-tier page: the Table API default (10000) is far larger than an
# evidence frame should carry, so the connector caps ``sysparm_limit`` hard.
DEFAULT_LIMIT = 20
MAX_LIMIT = 100

# A ServiceNow ``sys_id`` is a 32-char hex GUID. Validating it before it becomes
# a URL path segment is what makes path injection impossible.
_SYS_ID_RE = re.compile(r"^[0-9a-fA-F]{32}$")
# Defense in depth: a table name is a gateway-owned constant, but assert its
# shape anyway so a malformed binding can never build an unexpected path.
_TABLE_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# SPEC-067 R-4: the connector addresses the target with the gateway's own
# execution identity, never the requesting user's delegated identity (SPEC-070's
# production path). Audit states this so the record never implies target-side
# per-user RBAC this connector cannot provide.
TARGET_IDENTITY_ACTING_SERVICE = "acting_service"

# SPEC-067 R-5: codes meaning the target could not be reached; audit attributes
# these ``target_unavailable``. A config gap (``SERVICENOW_NOT_CONFIGURED``,
# ``SERVICENOW_INVALID_BASE_URL``) and a credential failure are deliberately
# excluded — those are gateway faults, not an unreachable target.
TARGET_UNAVAILABLE_CODES = frozenset({
    "SERVICENOW_TIMEOUT",
    "SERVICENOW_UNREACHABLE",
})


@dataclass(frozen=True)
class ServiceNowReadTool:
    """One gateway-owned read-tool declaration (SPEC-067 R-2/OQ-4).

    The connector is generic over these; the six admitted declarations live in
    :mod:`~tool_gateway.ingestion.servicenow_binding`. ``op`` is ``"list"`` (a
    bounded, ``sysparm_limit``-capped page) or ``"get"`` (one record by a
    validated ``sys_id``). ``fields`` is the projection allowlist applied to
    every returned record.
    """

    name: str
    table: str
    op: str  # "list" | "get"
    description: str
    fields: tuple[str, ...]
    parameters_schema: dict


def _project(record: dict, fields: tuple[str, ...]) -> dict:
    """Reduce one Table-API record to the allowlisted fields actually present.

    This is the safety net behind ``sysparm_fields``: even if the target returns
    a column we did not ask for (a ``password`` hash, say), it is dropped here
    because it is not in ``fields``.
    """
    return {name: record[name] for name in fields if name in record}


class ServiceNowNativeConnector:
    """Read-only ServiceNow Table-API reads (no MCP substrate).

    Registers one ``ServiceNowTableTool`` per admitted declaration. Inert until
    ``base_url`` is set (``configured`` is False), exactly like
    ``ansible_native.py`` — so rollback needs no code revert, only the removal
    of the credential set and its config.
    """

    def __init__(
        self,
        *,
        base_url: str = "",
        admitted: tuple[ServiceNowReadTool, ...] = (),
        credential_set: str = "",
        credential_sets_path: str = "",
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = (base_url or "").strip()
        self._admitted = admitted
        self._credential_set = credential_set
        self._timeout_ms = min(max(timeout_ms, 1), MAX_TIMEOUT_MS)
        self._credentials = CredentialSetStore(credential_sets_path)
        # SPEC-068 R-2/R-3: own one token client so its in-memory cache persists
        # across calls. It shares the injected transport, so a test's
        # MockTransport can serve both the OAuth token endpoint and the Table API.
        self._tokens = OAuth2TokenClient(transport=transport)
        # Test seam: an injected transport replaces the real socket at the single
        # call site in ``_table_request``. ``None`` uses httpx's default.
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self._base_url)

    def register_tools(self, registry: ToolRegistry) -> None:
        for spec in self._admitted:
            registry.register(ServiceNowTableTool(self, spec))

    # --- credential resolution (SPEC-068 seam; no local re-implementation) ---

    async def _resolve_auth(self) -> tuple[httpx.Auth | None, tuple[str, str, str] | None]:
        """Resolve the bound credential set into outbound auth.

        No credential set bound means no auth header (a loopback dev mock needs
        none). Otherwise delegate the scheme dispatch — ``basic`` / ``bearer`` /
        ``oauth2_client_credentials`` (OQ-1's pinned scheme) — to the reusable
        SPEC-068 R-3 resolver. Fails closed: a missing store, an unknown set, or
        a failed token acquisition is a gateway error, never an unauthenticated
        fallback. Only the set **name** ever surfaces.
        """
        if not self._credential_set:
            return None, None
        name = self._credential_set
        if not self._credentials.configured:
            return None, (
                "CREDENTIAL_SET_NOT_FOUND",
                f"No credential-set store is configured "
                f"(GATEWAY_SERVICENOW_CREDENTIAL_SETS), so '{name}' cannot be "
                f"resolved.",
                "error",
            )
        entry = self._credentials.get(name)
        if entry is None:
            return None, (
                "CREDENTIAL_SET_NOT_FOUND",
                f"Credential set '{name}' was not found.",
                "error",
            )
        resolved, err = await resolve_outbound_auth(
            set_name=name, entry=entry, token_client=self._tokens
        )
        if err is not None:
            return None, err
        return (resolved.auth if resolved is not None else None), None

    # --- request discipline (single transport call site) ---

    def _validate_base_url(self) -> tuple[str, str, str] | None:
        """Reject a base URL that is not a plain http(s) origin with no userinfo."""
        try:
            parsed = urlsplit(self._base_url)
        except ValueError:
            return (
                "SERVICENOW_INVALID_BASE_URL",
                "GATEWAY_SERVICENOW_BASE_URL is not a parseable URL.",
                "error",
            )
        if parsed.scheme not in {"http", "https"}:
            return (
                "SERVICENOW_INVALID_BASE_URL",
                f"GATEWAY_SERVICENOW_BASE_URL scheme "
                f"{parsed.scheme or '(none)'!r} is not allowed; only http and "
                f"https are accepted.",
                "error",
            )
        if not parsed.hostname:
            return (
                "SERVICENOW_INVALID_BASE_URL",
                "GATEWAY_SERVICENOW_BASE_URL has no host component.",
                "error",
            )
        # A credential in ``scheme://user:pass@host`` would be a secret in the
        # URL; authentication goes through the credential set only.
        if parsed.username or parsed.password:
            return (
                "SERVICENOW_INVALID_BASE_URL",
                "GATEWAY_SERVICENOW_BASE_URL may not carry userinfo "
                "(user:password@host); authenticate with the bound credential "
                "set instead.",
                "error",
            )
        return None

    def _build_target(
        self, spec: ServiceNowReadTool, parameters: dict
    ) -> tuple[tuple[str, dict, str] | None, tuple[str, str, str] | None]:
        """Validate model args and build the Table-API URL + query params.

        Returns ``((url, params, table), None)`` on success or
        ``(None, (code, msg, status))`` on refusal. The table is the
        gateway-owned constant; the only model-supplied inputs are a validated
        ``sys_id`` (get) and a clamped ``limit`` (list), so no model string
        reaches the path unvalidated.
        """
        if not _TABLE_RE.match(spec.table):
            return None, (
                "SERVICENOW_INVALID_TABLE",
                f"Internal error: table name {spec.table!r} is not a valid "
                f"ServiceNow table identifier.",
                "error",
            )
        root = f"{self._base_url.rstrip('/')}/api/now/table/{spec.table}"
        fields = ",".join(spec.fields)
        if spec.op == "get":
            sys_id = parameters.get("sys_id")
            if not isinstance(sys_id, str) or not _SYS_ID_RE.match(sys_id):
                return None, (
                    "INVALID_PARAMETERS",
                    "Parameter 'sys_id' is required and must be a 32-character "
                    "hex ServiceNow sys_id.",
                    "error",
                )
            return (
                f"{root}/{sys_id}",
                {"sysparm_fields": fields, "sysparm_display_value": "true"},
                spec.table,
            ), None
        # op == "list": clamp the optional limit into [1, MAX_LIMIT].
        raw_limit = parameters.get("limit")
        limit = DEFAULT_LIMIT
        if raw_limit is not None:
            try:
                parsed_limit = int(raw_limit)
            except (TypeError, ValueError):
                return None, (
                    "INVALID_PARAMETERS",
                    f"Parameter 'limit' must be an integer, got {raw_limit!r}.",
                    "error",
                )
            if parsed_limit < 1:
                return None, (
                    "INVALID_PARAMETERS",
                    f"Parameter 'limit' must be at least 1, got {parsed_limit}.",
                    "error",
                )
            limit = min(parsed_limit, MAX_LIMIT)
        return (
            root,
            {
                "sysparm_limit": str(limit),
                "sysparm_fields": fields,
                "sysparm_display_value": "true",
            },
            spec.table,
        ), None

    async def _table_request(
        self, spec: ServiceNowReadTool, parameters: dict
    ) -> tuple[dict | None, tuple[str, str, str] | None]:
        """Issue one bounded Table-API GET and project it.

        Returns ``(data, None)`` on success or ``(None, (code, message, status))``
        on any refusal, credential failure, transport fault, non-2xx upstream,
        or unparseable/shapeless body. This is the single transport call site
        every read tool shares, so a future read verb inherits every bound.
        """
        base_err = self._validate_base_url()
        if base_err is not None:
            return None, base_err
        target, build_err = self._build_target(spec, parameters)
        if build_err is not None or target is None:
            return None, build_err
        url, params, table = target
        auth, err = await self._resolve_auth()
        if err is not None:
            return None, err

        timeout = self._timeout_ms / 1000.0
        client_kwargs: dict = {"follow_redirects": False, "timeout": timeout}
        if self._transport is not None:
            client_kwargs["transport"] = self._transport
        request_kwargs: dict = {"params": params}
        if auth is not None:
            request_kwargs["auth"] = auth
        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.get(url, **request_kwargs)
        except httpx.TimeoutException:
            return None, (
                "SERVICENOW_TIMEOUT",
                f"The ServiceNow Table API read timed out after "
                f"{self._timeout_ms}ms.",
                "error",
            )
        except httpx.ConnectError as exc:
            LOGGER.warning(
                "servicenow transport connect error: %s", exc.__class__.__name__
            )
            return None, (
                "SERVICENOW_UNREACHABLE",
                f"Could not connect to the ServiceNow instance: "
                f"{exc.__class__.__name__}.",
                "error",
            )
        except httpx.HTTPError as exc:
            LOGGER.warning("servicenow transport error: %s", exc.__class__.__name__)
            return None, (
                "SERVICENOW_UNREACHABLE",
                f"The ServiceNow request could not be completed: "
                f"{exc.__class__.__name__}.",
                "error",
            )

        if response.status_code != 200:
            # The target answered with an error: a fact, but NOT the record we
            # were asked for, so it is a failed outcome — never an empty success.
            return None, (
                "SERVICENOW_UPSTREAM_ERROR",
                f"The ServiceNow Table API returned HTTP {response.status_code} "
                f"for table '{table}'.",
                "error",
            )
        try:
            payload = response.json()
        except ValueError:
            return None, (
                "SERVICENOW_RESPONSE_INVALID",
                f"The ServiceNow Table API returned a non-JSON body for table "
                f"'{table}'.",
                "error",
            )
        result = payload.get("result") if isinstance(payload, dict) else None
        if spec.op == "list":
            if not isinstance(result, list):
                return None, (
                    "SERVICENOW_RESPONSE_INVALID",
                    f"Expected a result list from table '{table}'.",
                    "error",
                )
            records = [
                _project(record, spec.fields)
                for record in result
                if isinstance(record, dict)
            ]
            return {"table": table, "count": len(records), "records": records}, None
        if not isinstance(result, dict):
            return None, (
                "SERVICENOW_RESPONSE_INVALID",
                f"Expected a single result object from table '{table}'.",
                "error",
            )
        return {"table": table, "record": _project(result, spec.fields)}, None


class ServiceNowTableTool(BaseTool):
    """One read-tier ServiceNow Table-API tool, generic over its declaration."""

    def __init__(
        self, connector: ServiceNowNativeConnector, spec: ServiceNowReadTool
    ) -> None:
        self._connector = connector
        self._spec = spec

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self._spec.name,
            description=self._spec.description,
            risk_level="read",
            category=CATEGORY,
            parameters_schema=self._spec.parameters_schema,
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        start = time.perf_counter()
        name = self._spec.name
        if not self._connector.configured:
            return make_error_result(
                name,
                "SERVICENOW_NOT_CONFIGURED",
                "No ServiceNow base URL is configured "
                "(GATEWAY_SERVICENOW_BASE_URL).",
                source_system=SOURCE_SYSTEM,
            )
        data, err = await self._connector._table_request(self._spec, parameters)
        duration_ms = int((time.perf_counter() - start) * 1000)
        if err is not None or data is None:
            code, message, status = err  # type: ignore[misc]
            return ToolResult(
                tool_name=name,
                status=status,
                evidence=build_evidence("read", SOURCE_SYSTEM, duration_ms),
                error={"code": code, "message": message},
            )
        return ToolResult(
            tool_name=name,
            status="success",
            data=data,
            evidence=build_evidence("read", SOURCE_SYSTEM, duration_ms),
        )

    def audit_attribution(self, result: ToolResult) -> dict:
        """SPEC-067 R-4/R-5: target-identity mode + target-unavailable class.

        Read by ``gateway_service.invoke_tool`` (duck-typed, opt-in), mirroring
        ``ansible_native.py``. The connector addresses ServiceNow with the
        gateway's own acting-service identity, never the requesting user's; a
        timeout or unreachable target is attributed ``target_unavailable``
        (distinct from a policy denial or a gateway config/credential gap).
        """
        attribution = {"target_identity_mode": TARGET_IDENTITY_ACTING_SERVICE}
        code = (result.error or {}).get("code") if result.status == "error" else None
        if code in TARGET_UNAVAILABLE_CODES:
            attribution["failure_class"] = "target_unavailable"
        return attribution
