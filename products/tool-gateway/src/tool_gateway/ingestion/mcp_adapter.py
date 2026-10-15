"""Generic, server-agnostic MCP-ingestion adapter (SPEC-069 R-2).

One reusable adapter over the official ``mcp`` Python SDK that maps an
**allowlisted** set of a remote MCP server's tools into the SPEC-007
``BaseTool``/``ToolDefinition``/``ToolRegistry`` seam as **typed tools**. The
adapter is server-agnostic: *what* to admit, the canonical tool name, the
JSON-Schema argument shape, and the risk tier are all **gateway-owned binding
configuration** (:class:`AdmittedTool`), never adapter code and never anything
the server advertises.

Two invariants drive the design:

* **Server metadata is untrusted.** Registration is purely config-driven — the
  adapter never calls ``list_tools`` to decide *what* to register or at *which*
  tier. A server tool absent from the allowlist is never exposed no matter how
  it describes itself, and a ``readOnlyHint``/``risk``/annotation the server
  advertises can never set a tier or auto-approve. Tier comes only from
  :attr:`AdmittedTool.risk_level` (this pilot admits read-tier tools only).
* **Fail closed.** A missing SDK, an unreachable/ timed-out server, a credential
  failure, or a server-reported tool error all become a *structured error*
  result — never an empty "success" and never an unauthenticated retry.

The kernel still reaches these tools through the existing signed-tool path
(SPEC-037); the kernel never becomes an MCP client. ``mcp`` is a direct
tool-gateway dependency only (its lockfile is separate from the kernel's
transitive AgentScope pin).
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable

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

# A session opener is an async context manager yielding an initialized MCP
# client session. Tests inject a fake opener so no live server is needed (CI
# makes no live external call, OQ-5); production uses ``_open_mcp_session``.
SessionOpener = Callable[["McpTransport", "str | None"], "AsyncIterator[Any]"]

# SPEC-069 R-4: how the managed target sees the caller's identity. This pilot
# (and the whole dev / self-hosted topology) addresses the target with the
# **acting service's** own credential or a loopback session — Luban still records
# attribution to the requesting principal, but the target does *not* enforce that
# user's own RBAC. The reserved alternative, ``"user_delegated"`` (the target
# enforces the requesting user's RBAC end to end), is realized by SPEC-070 and is
# deliberately **not** produced here; the audit record names the mode so it never
# implies target-side per-user RBAC the dev topology lacks.
TARGET_IDENTITY_ACTING_SERVICE = "acting_service"

# SPEC-069 R-5: error codes meaning the target could not be reached or did not
# answer. Audit attributes these ``target_unavailable`` — distinct from a policy
# denial (a separate ``policy_decision``/``deny`` event) and from a server-reported
# tool error (``MCP_TOOL_ERROR``: the target *was* available and answered).
TARGET_UNAVAILABLE_CODES = frozenset({"MCP_SDK_UNAVAILABLE", "MCP_TRANSPORT_ERROR"})


@dataclass(frozen=True)
class McpTransport:
    """How to reach one MCP server (operator configuration, never a model arg).

    ``kind`` is ``"streamable_http"`` (a URL endpoint — the self-hosted
    awx-mcp-server and AAP's read-only-mode server) or ``"stdio"`` (a local
    server process). ``timeout_ms`` bounds both the session read timeout and the
    HTTP client timeout.
    """

    kind: str = "streamable_http"
    url: str = ""
    command: str = ""
    args: tuple[str, ...] = ()
    timeout_ms: int = 10000


@dataclass(frozen=True)
class AdmittedTool:
    """Gateway-owned spec for one admitted server tool (the binding config).

    This — not the server's ``Tool`` object — is the sole source of the typed
    tool's identity, argument contract, and tier. ``server_name`` is the remote
    tool the call is dispatched to; ``argument_map`` optionally renames a
    canonical parameter to the server's argument name (identity when absent).
    """

    server_name: str
    name: str
    description: str
    risk_level: str
    category: str
    parameters_schema: dict = field(default_factory=dict)
    argument_map: dict[str, str] = field(default_factory=dict)


def _type_ok(expected: str, value: Any) -> bool:
    """JSON-Scalar type check for untrusted parameters (bool is not an int)."""
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True  # an unknown/absent type keyword imposes no constraint


def validate_parameters(schema: dict, parameters: Any) -> str | None:
    """Validate untrusted LLM parameters against a gateway-owned schema.

    A lightweight JSON-Schema subset (``required`` presence + scalar ``type`` +
    integer ``minimum``/``maximum``) matching the ad-hoc discipline the other
    connectors use. Returns an error message or ``None``; never raises, so a bad
    parameter surfaces as a structured ``INVALID_PARAMETERS`` result.
    """
    if not isinstance(parameters, dict):
        return "Parameters must be a JSON object."
    props = schema.get("properties") or {}
    for required in schema.get("required") or []:
        if parameters.get(required) in (None, ""):
            return f"Parameter '{required}' is required."
    for key, value in parameters.items():
        spec = props.get(key)
        if not isinstance(spec, dict) or value is None:
            continue
        expected = spec.get("type")
        if expected and not _type_ok(expected, value):
            return f"Parameter '{key}' must be of type {expected}."
        if expected == "integer":
            minimum, maximum = spec.get("minimum"), spec.get("maximum")
            if minimum is not None and value < minimum:
                return f"Parameter '{key}' must be >= {minimum}."
            if maximum is not None and value > maximum:
                return f"Parameter '{key}' must be <= {maximum}."
    return None


def map_arguments(spec: AdmittedTool, parameters: dict) -> dict:
    """Project validated parameters onto the server's argument names.

    Only keys the gateway-owned schema declares are forwarded, so an unexpected
    argument an LLM invents can never reach the server; declared keys are
    renamed through ``argument_map`` (identity when unmapped).
    """
    allowed = (spec.parameters_schema.get("properties") or {}).keys()
    return {
        spec.argument_map.get(key, key): value
        for key, value in parameters.items()
        if key in allowed
    }


def _extract_text(content: Any) -> str:
    """Join the text of a CallToolResult's text content blocks."""
    chunks: list[str] = []
    for block in content or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            chunks.append(text)
    return "\n".join(chunks).strip()


@asynccontextmanager
async def _open_mcp_session(
    transport: McpTransport, bearer_token: str | None
) -> AsyncIterator[Any]:
    """Open an initialized MCP client session over the configured transport.

    The ``mcp`` SDK is imported lazily (like ``k8s_connector`` imports
    ``kubernetes``) so an environment without it fails closed with a structured
    error rather than at import time. A bearer token — when present — rides an
    ``httpx2`` header (the SDK vendors a namespaced httpx); it is never placed in
    the URL and never logged.
    """
    from mcp.client.session import ClientSession

    timeout_s = transport.timeout_ms / 1000.0
    if transport.kind == "stdio":
        from mcp import StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=transport.command, args=list(transport.args)
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(
                read, write, read_timeout_seconds=timeout_s
            ) as session:
                await session.initialize()
                yield session
        return

    from mcp.client.streamable_http import streamable_http_client

    http_client = None
    if bearer_token:
        import httpx2

        http_client = httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {bearer_token}"}, timeout=timeout_s
        )
    try:
        async with streamable_http_client(
            transport.url, http_client=http_client
        ) as (read, write):
            async with ClientSession(
                read, write, read_timeout_seconds=timeout_s
            ) as session:
                await session.initialize()
                yield session
    finally:
        if http_client is not None:
            await http_client.aclose()


class McpIngestionConnector:
    """Registers an allowlisted server's tools as typed gateway tools.

    Server-agnostic by construction: two different bindings (a self-hosted
    dev/mock server and an AAP read-only-mode config) are two different
    ``admitted`` tuples handed to the *same* adapter class — no adapter-code
    change. The optional credential set resolves through the SPEC-068 seam; a
    loopback sidecar simply names no set.
    """

    def __init__(
        self,
        *,
        transport: McpTransport,
        admitted: tuple[AdmittedTool, ...],
        source_system: str = "mcp",
        target_identity_mode: str = TARGET_IDENTITY_ACTING_SERVICE,
        credential_set: str = "",
        credential_sets_path: str = "",
        token_client: OAuth2TokenClient | None = None,
        session_opener: SessionOpener | None = None,
    ) -> None:
        self._transport = transport
        self._admitted = tuple(admitted)
        self._source_system = source_system
        self._target_identity_mode = target_identity_mode
        self._credential_set = credential_set
        self._credentials = CredentialSetStore(credential_sets_path)
        # SPEC-068 R-2/R-3: one token client so its cache persists across calls.
        self._tokens = token_client or OAuth2TokenClient()
        self._session_opener = session_opener or _open_mcp_session

    @property
    def admitted(self) -> tuple[AdmittedTool, ...]:
        return self._admitted

    @property
    def target_identity_mode(self) -> str:
        """SPEC-069 R-4: how the target sees the caller (see module constant)."""
        return self._target_identity_mode

    def register_tools(self, registry: ToolRegistry) -> None:
        """Register one typed tool per admitted spec.

        Registration is config-driven and does **not** contact the server. The
        registry's own risk-tier admission (SPEC-021 R-1) is a second backstop:
        a non-read tier is refused unless mutating tools are enabled.
        """
        for spec in self._admitted:
            registry.register(McpTool(self, spec))

    async def _resolve_bearer(self) -> tuple[str | None, tuple[str, str, str] | None]:
        """Resolve the configured credential set into a bearer token (SPEC-068).

        Returns ``(token|None, err|None)``. No configured set means an
        unauthenticated loopback session (``None, None``). The MCP transport
        needs a bearer form, so a ``basic`` set — which has none — fails closed
        rather than silently downgrading to no auth.
        """
        if not self._credential_set:
            return None, None
        name = self._credential_set
        if not self._credentials.configured:
            return None, (
                "CREDENTIAL_SET_NOT_FOUND",
                f"No credential-set store is configured, so '{name}' cannot be "
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
        token = resolved.bearer_token if resolved is not None else None
        if token is None:
            return None, (
                "CREDENTIAL_SCHEME_UNSUPPORTED",
                f"Credential set '{name}' resolved to a scheme with no bearer "
                f"token for the MCP transport.",
                "error",
            )
        return token, None

    async def _call(
        self, server_name: str, arguments: dict
    ) -> tuple[Any | None, tuple[str, str, str] | None]:
        """Dispatch one call to the server; fail closed on any transport fault."""
        token, err = await self._resolve_bearer()
        if err is not None:
            return None, err
        try:
            async with self._session_opener(self._transport, token) as session:
                result = await session.call_tool(server_name, arguments)
        except ImportError as exc:
            LOGGER.warning("mcp SDK unavailable: %s", exc.__class__.__name__)
            return None, (
                "MCP_SDK_UNAVAILABLE",
                "The 'mcp' SDK is not installed in this deployment.",
                "error",
            )
        except Exception as exc:  # transport/timeout/connection — never fabricate
            LOGGER.warning(
                "MCP call to %r failed: %s", server_name, exc.__class__.__name__
            )
            return None, (
                "MCP_TRANSPORT_ERROR",
                f"MCP server call failed ({exc.__class__.__name__}).",
                "error",
            )
        return result, None

    async def list_server_tools(self) -> tuple[list[str] | None, tuple[str, str, str] | None]:
        """Diagnostic: the tool names the server advertises.

        Deliberately **not** used to decide registration or tier (server metadata
        is untrusted); it exists for an operator health check and for tests that
        assert an unlisted/advertised-read-only server tool is still not exposed.
        """
        token, err = await self._resolve_bearer()
        if err is not None:
            return None, err
        try:
            async with self._session_opener(self._transport, token) as session:
                result = await session.list_tools()
        except ImportError:
            return None, (
                "MCP_SDK_UNAVAILABLE",
                "The 'mcp' SDK is not installed in this deployment.",
                "error",
            )
        except Exception as exc:
            LOGGER.warning("MCP discovery failed: %s", exc.__class__.__name__)
            return None, (
                "MCP_TRANSPORT_ERROR",
                f"MCP server discovery failed ({exc.__class__.__name__}).",
                "error",
            )
        return [t.name for t in getattr(result, "tools", [])], None


class McpTool(BaseTool):
    """One admitted server tool, exposed as a typed gateway tool.

    The definition is built entirely from the gateway-owned :class:`AdmittedTool`
    spec; nothing is read from the server. ``execute`` validates parameters
    against the gateway schema, projects them onto the server's argument names,
    dispatches, and normalizes the result — mapping a server-reported error or a
    transport fault to a structured error, never a fabricated success.
    """

    def __init__(self, connector: McpIngestionConnector, spec: AdmittedTool) -> None:
        self._connector = connector
        self._spec = spec

    @property
    def definition(self) -> ToolDefinition:
        spec = self._spec
        return ToolDefinition(
            name=spec.name,
            description=spec.description,
            risk_level=spec.risk_level,
            category=spec.category,
            parameters_schema=spec.parameters_schema,
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        start = time.perf_counter()
        spec = self._spec
        source = self._connector._source_system

        invalid = validate_parameters(spec.parameters_schema, parameters)
        if invalid is not None:
            return make_error_result(
                spec.name, "INVALID_PARAMETERS", invalid,
                risk_level=spec.risk_level, source_system=source,
            )

        arguments = map_arguments(spec, parameters)
        result, err = await self._connector._call(spec.server_name, arguments)
        duration_ms = int((time.perf_counter() - start) * 1000)
        if err is not None:
            code, message, _status = err
            return make_error_result(
                spec.name, code, message,
                risk_level=spec.risk_level, source_system=source,
                duration_ms=duration_ms,
            )
        return self._normalize(result, duration_ms)

    def _normalize(self, result: Any, duration_ms: int) -> ToolResult:
        """Map a CallToolResult onto the tool-result envelope (no fabrication)."""
        spec = self._spec
        source = self._connector._source_system
        is_error = bool(getattr(result, "is_error", False))
        text = _extract_text(getattr(result, "content", None))
        if is_error:
            return make_error_result(
                spec.name, "MCP_TOOL_ERROR",
                text or "The MCP server reported a tool error.",
                risk_level=spec.risk_level, source_system=source,
                duration_ms=duration_ms,
            )
        structured = getattr(result, "structured_content", None)
        data = structured if isinstance(structured, dict) else (
            {"text": text} if text else {}
        )
        return ToolResult(
            tool_name=spec.name,
            status="success",
            data=data,
            evidence=build_evidence(spec.risk_level, source, duration_ms),
        )

    def audit_attribution(self, result: ToolResult) -> dict:
        """SPEC-069 R-4/R-5 audit attribution for one admitted-tool call.

        Read by ``gateway_service.invoke_tool`` (duck-typed, opt-in) and merged
        into the ``tool_invoked`` audit details; a tool that does not declare it
        audits byte-identically to before. It folds in (a) the target-identity
        mode — this pilot addresses the target as the acting service, never the
        requesting user's delegated identity (SPEC-070's production path) — and
        (b) on a transport/timeout/SDK failure, the ``target_unavailable`` class
        that separates an unreachable target from a policy denial or a
        server-reported tool error.
        """
        attribution = {"target_identity_mode": self._connector.target_identity_mode}
        code = (result.error or {}).get("code") if result.status == "error" else None
        if code in TARGET_UNAVAILABLE_CODES:
            attribution["failure_class"] = "target_unavailable"
        return attribution
