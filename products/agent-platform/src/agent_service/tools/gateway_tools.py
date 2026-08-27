"""Gateway-backed tool functions for AgentScope Toolkit (SPEC-007 R-6, SPEC-008 R-5, SPEC-011 R-2, SPEC-018).

This module fetches available tools from the tool-gateway and creates
callable functions suitable for registration with AgentScope's Toolkit.
Each function calls POST /api/v2/tools/invoke on the gateway.

The owning user's delegated token is presented as ``Authorization: Bearer``
on discovery and invocation; identity is carried exclusively by this token,
never in the body. Closures read the current token from the
``DELEGATED_TOKEN`` contextvar at call time (the runtime kernel sets it
around each turn) so cached toolkits keep working across portal token
refresh (SPEC-018 R-2).

SPEC-011 R-2 / SPEC-018 R-2: tool_call / tool_result evidence frames are
emitted by ``ToolEvidenceMiddleware`` from the gateway result carried on
the returned ``ToolChunk`` metadata; closures no longer own trace plumbing.
Permission decisions live in ``GatewayPermissionMiddleware`` (SPEC-018 R-1),
so the tools built here are plain ``FunctionTool`` instances.
"""

from __future__ import annotations

import hmac
import json
import logging
import uuid
from contextvars import ContextVar
from typing import Any

import httpx

LOGGER = logging.getLogger(__name__)

# Timeout for tool invocations (K8s reads can be slow on large clusters).
INVOKE_TIMEOUT_SECONDS = 30.0
DISCOVER_TIMEOUT_SECONDS = 10.0

# Request-scoped delegated token (SPEC-018 R-2): set by the runtime kernel
# around each turn so closures inside cached toolkits always present the
# current token, even after a portal token refresh.
DELEGATED_TOKEN: ContextVar[str | None] = ContextVar(
    "DELEGATED_TOKEN",
    default=None,
)

# Signed execution request state for the resumed stream (SPEC-037 R-2/R-3):
# the kernel sets EXECUTION_REQUESTS (call_id -> signed request envelope)
# around an approved resume; tool closures verify the invoked arguments
# against the envelope before the gateway call goes out. A missing-key
# resume sets EXECUTION_REJECTION instead, so every mutating invocation
# fails closed with that reason. EXECUTION_AUDIT_CONTEXT carries the
# correlation fields (settings, confirm_id, request id, identities) the
# rejection audit needs. CURRENT_CALL_ID binds the in-flight invocation
# to its parked call id (set by ToolEvidenceMiddleware).
EXECUTION_REQUESTS: ContextVar[dict[str, dict[str, Any]] | None] = ContextVar(
    "EXECUTION_REQUESTS",
    default=None,
)
EXECUTION_REJECTION: ContextVar[str | None] = ContextVar(
    "EXECUTION_REJECTION",
    default=None,
)
EXECUTION_AUDIT_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar(
    "EXECUTION_AUDIT_CONTEXT",
    default=None,
)
CURRENT_CALL_ID: ContextVar[str | None] = ContextVar(
    "CURRENT_CALL_ID",
    default=None,
)


def _auth_headers(bearer_token: str | None) -> dict[str, str]:
    if bearer_token:
        return {"Authorization": f"Bearer {bearer_token}"}
    return {}


async def discover_tools(gateway_url: str, bearer_token: str | None = None) -> list[dict]:
    """Fetch the list of available tools from the gateway.

    Returns an empty list on failure or when no token is available (graceful
    degradation to an empty Toolkit).
    """
    if not bearer_token:
        LOGGER.info("no delegated token; skipping tool discovery")
        return []
    try:
        async with httpx.AsyncClient(timeout=DISCOVER_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{gateway_url}/api/v2/tools",
                headers=_auth_headers(bearer_token),
            )
            response.raise_for_status()
            tools = response.json()
            LOGGER.info("discovered %d tools from gateway", len(tools))
            return tools
    except Exception as exc:
        LOGGER.warning("failed to discover tools from gateway: %s", exc)
        return []


async def invoke_gateway_tool(
    gateway_url: str,
    tool_name: str,
    parameters: dict[str, Any],
    bearer_token: str | None = None,
) -> dict:
    """Invoke a tool through the gateway and return the result dict.

    Without a token, returns a structured error result (never raises).
    """
    request_id = str(uuid.uuid4())
    if not bearer_token:
        return {
            "tool_name": tool_name,
            "status": "error",
            "request_id": request_id,
            "error": {
                "code": "NO_CREDENTIAL",
                "message": "no delegated token available for tool invocation",
            },
        }

    payload = {
        "tool_name": tool_name,
        "parameters": parameters,
        "request_id": request_id,
    }
    async with httpx.AsyncClient(timeout=INVOKE_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"{gateway_url}/api/v2/tools/invoke",
            json=payload,
            headers=_auth_headers(bearer_token),
        )
        return response.json()


def _normalize_input_schema(schema: Any) -> dict:
    """Coerce a gateway parameters_schema into a Toolkit-valid shape.

    AgentScope rejects any ``input_schema`` that is not an object schema with
    a ``properties`` dict, so fill in defaults rather than letting one bad
    definition take down the whole toolkit registration.
    """
    if not isinstance(schema, dict) or schema.get("type") != "object":
        return {"type": "object", "properties": {}}
    normalized = dict(schema)
    if not isinstance(normalized.get("properties"), dict):
        normalized["properties"] = {}
    return normalized


def _verify_execution_request(
    parameters: dict[str, Any],
    call_id: str | None,
) -> str | None:
    """Verify one mutating invocation against its signed request (SPEC-037 R-3).

    Returns the rejection reason, or None when the call may proceed.
    Read-only tools never reach this gate. The check fails closed: a
    resume-wide rejection (missing signing key), an absent envelope, or a
    digest mismatch all block the invocation before the gateway call goes
    out — the kernel's ALLOWED state alone never suffices for a mutating
    call.
    """
    from agent_service.services.execution_signing import (
        REASON_ARGS_DIGEST_MISMATCH,
        REASON_REQUEST_MISSING,
        canonical_digest,
    )

    rejection = EXECUTION_REJECTION.get()
    if rejection:
        return rejection
    requests = EXECUTION_REQUESTS.get() or {}
    request = requests.get(call_id) if call_id else None
    if request is None:
        return REASON_REQUEST_MISSING
    if not hmac.compare_digest(
        canonical_digest(parameters), request.get("args_digest") or ""
    ):
        return REASON_ARGS_DIGEST_MISMATCH
    return None


def _rejection_result(
    tool_name: str,
    reason: str,
) -> dict[str, Any]:
    """Structured error result for a blocked mutating invocation.

    Same shape as the NO_CREDENTIAL error result: the stream stays alive,
    the evidence middleware still emits the tool_result frame, and the
    kernel's resumed-stream handling closes the execution record.
    """
    return {
        "tool_name": tool_name,
        "status": "error",
        "request_id": str(uuid.uuid4()),
        "error": {
            "code": "EXECUTION_REJECTED",
            "message": (
                "execution request verification failed: "
                "this mutating action was not executed"
            ),
            "reason": reason,
        },
    }


def _audit_execution_rejected(
    tool_name: str,
    call_id: str | None,
    reason: str,
) -> None:
    """Emit the execution_rejected audit event (SPEC-037 R-5).

    Best-effort and inert outside a resumed stream: the correlation
    context is only present while the kernel owns an approved resume.
    """
    context = EXECUTION_AUDIT_CONTEXT.get()
    if not context:
        return
    from agent_service.services.audit_emitter import (
        build_audit_event,
        emit_audit_event,
    )

    event = build_audit_event(
        "execution_rejected",
        context.get("request_id"),
        "deny",
        details={
            "confirm_id": context.get("confirm_id"),
            "call_id": call_id,
            "tool_name": tool_name,
            "reason": reason,
        },
        subject=context.get("decider_user_id"),
        username=context.get("decider_user_id"),
        session_id=context.get("session_id"),
    )
    emit_audit_event(context.get("settings"), event)


async def _handoff_execution(
    tool_name: str,
    call_id: str | None,
    arguments: dict[str, Any],
    delegated_token: str | None,
) -> dict[str, Any]:
    """Hand one verified mutating invocation to the execution worker.

    SPEC-038 R-4: the resumed stream blocks on the worker with a bounded
    timeout. A missing worker configuration or a transport failure
    rejects with ``worker_unavailable`` (audited) — there is no
    in-process fallback. A handoff timeout surfaces the structured
    timeout result so the resumed-stream handling closes the record with
    a ``timeout`` receipt (first-write-wins with the worker's close).
    Worker-side verification rejections carry the worker's reason back to
    the invocation boundary.
    """
    from agent_service.services.execution_worker_client import (
        WorkerHandoffError,
        WorkerHandoffTimeout,
        handoff,
    )

    context = EXECUTION_AUDIT_CONTEXT.get() or {}
    settings = context.get("settings")
    requests_map = EXECUTION_REQUESTS.get() or {}
    envelope = requests_map.get(call_id) if call_id else None
    try:
        return await handoff(
            request=envelope,
            arguments=arguments,
            delegated_token=delegated_token,
            settings=settings,
            request_id=context.get("request_id"),
        )
    except WorkerHandoffTimeout:
        LOGGER.warning(
            "execution handoff for %s timed out", tool_name
        )
        return {
            "tool_name": tool_name,
            "status": "error",
            "request_id": str(uuid.uuid4()),
            "error": {
                "code": "TIMEOUT",
                "message": "execution handoff timed out before the "
                "worker answered",
            },
        }
    except WorkerHandoffError as exc:
        LOGGER.warning(
            "execution handoff for %s rejected: %s", tool_name, exc.reason
        )
        _audit_execution_rejected(tool_name, call_id, exc.reason)
        return _rejection_result(tool_name, exc.reason)


def _make_tool_fn(
    gateway_url: str,
    name: str,
    desc: str,
    *,
    is_read_only: bool = True,
):
    """Build the async gateway-invocation closure for one tool.

    The closure captures ``name`` and ``gateway_url``; the owning user's
    delegated token is read from ``DELEGATED_TOKEN`` at call time so one
    user's credential is never used for another user's session and cached
    toolkits survive token refresh. The returned ``ToolChunk`` carries the
    raw gateway result on its metadata so ``ToolEvidenceMiddleware`` can
    emit evidence frames without re-parsing the model-visible text
    (SPEC-018 R-2).

    Mutating tools (``is_read_only`` False) verify their invoked arguments
    against the signed execution request before anything goes out
    (SPEC-037 R-3); a failed verification returns a structured rejection
    result and never reaches the gateway. Verified mutating calls hand
    off to the execution-runtime worker instead of calling the gateway
    inline (SPEC-038 R-4): the worker performs the call, writes the
    receipt, and returns the gateway result, which flows into the
    ``ToolChunk`` unchanged. Read-only tools never consult the envelope
    and never hand off.
    """
    from agentscope.message import TextBlock
    from agentscope.tool import ToolChunk

    async def tool_fn(**kwargs: Any) -> ToolChunk:
        """Invoke a platform tool via the tool-gateway."""
        if not is_read_only:
            call_id = CURRENT_CALL_ID.get()
            reason = _verify_execution_request(kwargs, call_id)
            if reason is not None:
                LOGGER.warning(
                    "mutating invocation of %s rejected: %s",
                    name,
                    reason,
                )
                _audit_execution_rejected(name, call_id, reason)
                result = _rejection_result(name, reason)
                return ToolChunk(
                    content=[TextBlock(text=json.dumps(result, default=str))],
                    metadata={"gateway_result": result},
                )
            result = await _handoff_execution(
                name, call_id, kwargs, DELEGATED_TOKEN.get()
            )
            return ToolChunk(
                content=[TextBlock(text=json.dumps(result, default=str))],
                metadata={"gateway_result": result},
            )
        try:
            result = await invoke_gateway_tool(
                gateway_url=gateway_url,
                tool_name=name,
                parameters=kwargs,
                bearer_token=DELEGATED_TOKEN.get(),
            )
        except httpx.TimeoutException:
            # Surface the timeout as a structured result so the evidence
            # frame (and the SPEC-037 receipt) can distinguish it from a
            # gateway-reported failure.
            result = {
                "tool_name": name,
                "status": "error",
                "request_id": str(uuid.uuid4()),
                "error": {
                    "code": "TIMEOUT",
                    "message": "tool invocation timed out before the "
                    "gateway answered",
                },
            }
        return ToolChunk(
            content=[TextBlock(text=json.dumps(result, default=str))],
            metadata={"gateway_result": result},
        )

    # Set function metadata for AgentScope tool discovery.
    tool_fn.__name__ = name.replace(".", "_")
    tool_fn.__qualname__ = name.replace(".", "_")
    tool_fn.__doc__ = desc or f"Invoke {name}"
    return tool_fn


def build_function_tools(
    gateway_url: str,
    tool_definitions: list[dict],
) -> list:
    """Build AgentScope ``FunctionTool`` objects for each gateway tool def.

    Each returned tool wraps an async closure that accepts **kwargs matching
    the tool's parameter schema and returns a ``ToolChunk`` whose metadata
    carries the gateway result dict. The delegated token is read from the
    ``DELEGATED_TOKEN`` contextvar at call time so one user's credential is
    never used for another user's session.

    The closure only exposes **kwargs, so AgentScope would derive an empty
    input schema; the gateway's ``parameters_schema`` is therefore bound onto
    each tool explicitly so the model sees the real parameters.

    Permission decisions are made by ``GatewayPermissionMiddleware`` and
    evidence frames by ``ToolEvidenceMiddleware`` (SPEC-018 R-1/R-2); each
    tool carries its dotted gateway name on ``gateway_tool_name`` for
    evidence-frame parity.

    Tools that fail to wrap are skipped with a warning (never a hard failure).
    """
    from agentscope.tool import FunctionTool

    tools: list = []
    for tool_def in tool_definitions:
        tool_name = tool_def["name"]
        description = tool_def.get("description", "")
        try:
            fn = _make_tool_fn(
                gateway_url,
                tool_name,
                description,
                is_read_only=(tool_def.get("risk_level") == "read"),
            )
            tool = FunctionTool(
                fn,
                name=tool_name.replace(".", "_"),
                description=description or f"Invoke {tool_name}",
                is_read_only=(tool_def.get("risk_level") == "read"),
            )
            tool.input_schema = _normalize_input_schema(
                tool_def.get("parameters_schema"),
            )
            tool.gateway_tool_name = tool_name
            # Risk tier rides the tool so parked confirmations can surface
            # it on confirmation_request frames (SPEC-021 R-3).
            tool.gateway_risk_level = tool_def.get("risk_level", "read")
            tools.append(tool)
            LOGGER.info("registered toolkit function: %s", tool_name)
        except Exception as exc:
            LOGGER.warning("failed to build tool %s: %s", tool_name, exc)
    return tools


def build_gateway_toolkit(
    tool_definitions: list[dict],
    gateway_url: str,
):
    """Assemble an AgentScope Toolkit from gateway tool definitions.

    AgentScope 2.x has no ``Toolkit.add``; tools are passed at construction as
    ``Toolkit(tools=[FunctionTool(...)])``.
    """
    from agentscope.tool import Toolkit

    _log_mutating_auto_allow_exclusions(tool_definitions)
    tools = build_function_tools(gateway_url, tool_definitions)
    return Toolkit(tools=tools)


def _log_mutating_auto_allow_exclusions(tool_definitions: list[dict]) -> None:
    """Log once per toolkit build when mutating tools hit the auto-allow list.

    The auto-allow surface is read-only by construction (SPEC-021 R-3):
    ``GatewayPermissionMiddleware`` only auto-approves tools that are BOTH
    vetted and ``is_read_only``, so a mutating tool named in
    ``AGENT_GATEWAY_TOOL_AUTO_ALLOW`` can never auto-execute — it always
    parks for HITL confirmation. The exclusion is logged here so the
    misconfiguration stays visible instead of silently ignored.
    """
    from agent_service.services.kernel_middleware import (
        _load_auto_allowed_tools,
    )

    allow_list = _load_auto_allowed_tools()
    for tool_def in tool_definitions:
        if tool_def.get("risk_level", "read") == "read":
            continue
        tool_name = tool_def["name"]
        if tool_name.replace(".", "_") in allow_list:
            LOGGER.warning(
                "mutating tool %s appears in the auto-allow list but will "
                "never auto-execute: the auto-allow surface is read-only "
                "by construction (SPEC-021 R-3)",
                tool_name,
            )


async def build_toolkit(
    gateway_url: str,
    bearer_token: str | None = None,
):
    """Build an AgentScope Toolkit populated with gateway tools.

    Returns a Toolkit instance (empty if no token is available or the gateway
    is unreachable).
    """
    tool_definitions = await discover_tools(gateway_url, bearer_token)
    return build_gateway_toolkit(tool_definitions, gateway_url)
