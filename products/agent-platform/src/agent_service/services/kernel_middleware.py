"""Kernel middleware aligning AgentScope with the platform contract (SPEC-018).

All cross-cutting kernel behavior lives on the supported ``MiddlewareBase``
surface instead of private agentscope internals:

- ``GatewayPermissionMiddleware`` (R-1) owns the permission gate for a
  headless SSE runtime: vetted read-only gateway tools and the built-in
  task tools are ALLOWed; every other tool is answered with an explicit
  ASK instead of delegating to agentscope's PermissionEngine, whose
  read-only fast path auto-allows read-only invocations in every mode and
  would silently bypass the platform allow-list. The ASK parks the batch
  on ``RequireUserConfirmEvent`` for the SPEC-020 confirmation bridge.
- ``ToolEvidenceMiddleware`` (R-2) emits the ``tool_call`` / ``tool_result``
  evidence frames (SPEC-011 R-2 contract) into a request-scoped sink set by
  the runtime kernel; blocking turns with no sink emit nothing.

Admission, policy, and audit remain enforced by the tool-gateway on every
invocation; this module only shapes kernel-local decisions and evidence.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

from agentscope.message import ToolCallBlock, ToolCallState
from agentscope.middleware import MiddlewareBase
from agentscope.permission import PermissionBehavior, PermissionDecision
from agentscope.tool import ToolResponse

from agent_service.services.flow_approvals import BROWSER_WRITE_TOOLS

LOGGER = logging.getLogger(__name__)

# Request-scoped evidence sink (SPEC-018 R-2): an asyncio.Queue set by
# ``AgentKernel.stream_events`` around each streamed turn. Unset (None) for
# blocking turns, so the evidence middleware stays inert there.
TOOL_EVIDENCE_SINK: ContextVar[Any | None] = ContextVar(
    "TOOL_EVIDENCE_SINK",
    default=None,
)

# Built-in agentscope task tools (SPEC-018 R-5). Names match the kernel's
# tool names; these tools mutate only session-local agent state and are
# always allowed — they must never hit the interactive ASK gate on a
# headless stream.
TASK_TOOL_NAMES = frozenset({
    "TaskCreate",
    "TaskGet",
    "TaskList",
    "TaskUpdate",
})

# Kernel-built-in tool that delivers response_schema turns (SPEC-017 R-2):
# it only shapes the final reply into the caller-provided schema and never
# touches external systems, so it must never park on the ASK gate either.
STRUCTURED_OUTPUT_TOOL_NAME = "GenerateStructuredOutput"

KERNEL_LOCAL_TOOL_NAMES = TASK_TOOL_NAMES | {STRUCTURED_OUTPUT_TOOL_NAME}

# Vetted tool names that may bypass the permission gate. Only read-only
# tools on this explicit allow-list are auto-approved; every other tool is
# answered with an explicit ASK and parks for operator confirmation
# (SPEC-020). Admission and policy are still enforced by the tool-gateway
# on every invocation.
DEFAULT_AUTO_ALLOWED_TOOLS = frozenset({
    "k8s.list_pods",
    "k8s.get_pod",
    "k8s.get_events",
    "k8s.get_pod_logs",
    "skills.search",
    "skills.get",
    "skills.list",
    "incidents.list",
    "incidents.get",
    # SPEC-049/SPEC-050: read-class browser probes may run without an extra
    # gate; the gateway still enforces the origin allowlist and flow guards
    # on every call. web.click/web.type/web.select/web.press_key/web.upload_file
    # are intentionally absent — they can never satisfy the read-only
    # invariant below. web.evaluate is also absent: arbitrary JS can mutate
    # the DOM and read masked secrets, so it inherits the write-tier HITL gate.
    "web.navigate",
    "web.snapshot",
    "web.screenshot",
    "web.fill_credential",
    "web.extract",
    "web.wait_for",
    "web.hover",
    "web.scroll",
    "web.switch_frame",
})
AUTO_ALLOW_ENV = "AGENT_GATEWAY_TOOL_AUTO_ALLOW"


def _load_auto_allowed_tools() -> frozenset[str]:
    """Resolve the auto-approve allow-list (env override or vetted default).

    ``AGENT_GATEWAY_TOOL_AUTO_ALLOW`` accepts a comma-separated list of
    gateway tool names; an empty string auto-approves nothing. Entries are
    normalized to the sanitized tool names used by AgentScope (dots become
    underscores), matching ``FunctionTool.name``.
    """
    raw = os.environ.get(AUTO_ALLOW_ENV)
    source = DEFAULT_AUTO_ALLOWED_TOOLS if raw is None else {
        part.strip() for part in raw.split(",") if part.strip()
    }
    return frozenset(name.replace(".", "_") for name in source)


def _make_data_summary(
    data: Any, max_chars: int = 2000,
) -> dict | None:
    """Build a bounded data_summary for trace events (SPEC-011 R-2).

    Serializes ``data`` to JSON and truncates if it exceeds ``max_chars``.
    Returns None when data is None or empty.
    """
    if data is None:
        return None
    serialized = json.dumps(data, default=str)
    if len(serialized) <= max_chars:
        return data
    # Truncate the serialized form and return a marker dict.
    return {"_truncated": True, "_preview": serialized[:max_chars], "_original_length": len(serialized)}


def _make_full_data(data: Any, max_chars: int = 128000) -> Any:
    """Return the full tool payload for evidence frames, size-guarded.

    Streams stay bounded: when the serialized payload exceeds
    ``max_chars`` the field is omitted from the frame entirely — the
    truncated ``data_summary`` still surfaces and the full result stays
    in the audit trail. Returns None when data is None.

    The default limit (128KB) accommodates base64-encoded screenshots
    from web.screenshot (up to 64KB raw → ~87KB base64).
    """
    if data is None:
        return None
    serialized = json.dumps(data, default=str)
    if len(serialized) > max_chars:
        return None
    return data


class GatewayPermissionMiddleware(MiddlewareBase):
    """Owns AgentScope's permission gate for a headless kernel (R-1).

    The platform allow-list is the only auto-approval surface (deny by
    default): tools that are read-only AND vetted are pre-approved, and
    state-local task tools always run — the tool-gateway still enforces
    admission and policy on every invocation and each call is
    audit-logged. Every other tool is answered with an explicit ASK
    rather than delegated to agentscope's PermissionEngine: the engine
    auto-allows read-only invocations in every mode (read-only fast
    path), which would silently skip the allow-list. The ASK parks the
    batch on RequireUserConfirmEvent, which the kernel bridges to the
    operator portal (SPEC-020).

    Calls already approved through that bridge traverse the middleware
    chain again on resume (state ALLOWED); they are delegated to the
    built-in resolution, which short-circuits ALLOWED calls — re-ASKing
    them would park the resumed reply forever.

    SPEC-051 R-1 adds one narrow runtime exception for browser flows: a
    mutating ``web.*`` call inside a flow the operator already approved is
    ALLOWed and auto-signed via the optional ``flow_signer`` (scoped to the
    session and the approved flow's identity), so a multi-step mutating flow
    parks a single card instead of one per write. This is runtime flow
    authority, not an allow-list entry — the read-only auto-allow invariant
    is unchanged, and the tool-gateway deviation guard still bounds the write.
    """

    def __init__(
        self,
        auto_allowed: frozenset[str] | None = None,
        flow_signer: Callable[[Any, str], dict | None] | None = None,
    ) -> None:
        self._allow_list = (
            auto_allowed if auto_allowed is not None else _load_auto_allowed_tools()
        )
        # SPEC-051 R-1: optional callback the kernel arms to auto-sign an
        # unlocked browser write. ``flow_signer(tool_call, gateway_tool_name)``
        # returns a signed execution envelope when the session holds a live
        # flow authority whose identity still matches the bound flow, else
        # ``None`` (→ the write parks as before). Never set for non-browser
        # writes; the static read-only allow-list above is untouched.
        self._flow_signer = flow_signer

    async def on_check_permission(
        self,
        agent: Any,
        input_kwargs: dict,
        next_handler: Any,
    ) -> PermissionDecision:
        tool = input_kwargs.get("tool")
        name = getattr(tool, "name", None)
        tool_call = input_kwargs.get("tool_call")
        if getattr(tool_call, "state", None) == ToolCallState.ALLOWED:
            # SPEC-020 resume: the operator already confirmed this exact
            # call. Agentscope re-traverses the middleware chain for
            # confirmed calls and expects the built-in resolution to
            # short-circuit the ALLOWED state; re-ASKing here would
            # re-park the resumed reply indefinitely.
            return await next_handler(**input_kwargs)
        if name in KERNEL_LOCAL_TOOL_NAMES:
            # State-local kernel built-ins (task tools, structured-output
            # delivery) never touch external systems.
            return PermissionDecision(
                behavior=PermissionBehavior.ALLOW,
                message=f"{name} mutates only session-local agent state.",
            )
        if (
            tool is not None
            and getattr(tool, "is_read_only", False)
            and name in self._allow_list
        ):
            # SPEC-021 R-3 invariant: the allow-list is read-only by
            # construction. Mutating tools carry is_read_only=False, so
            # naming one in AGENT_GATEWAY_TOOL_AUTO_ALLOW can never grant
            # auto-execution — it falls through to the ASK below and parks
            # for HITL confirmation regardless of configuration.
            return PermissionDecision(
                behavior=PermissionBehavior.ALLOW,
                message=(
                    "Vetted read-only gateway tool; admission and policy "
                    "are enforced by the tool-gateway."
                ),
            )
        if tool is None:
            # No tool surface to reason about; keep the built-in resolution.
            return await next_handler(**input_kwargs)
        # SPEC-051 R-1: one HITL gate per mutating browser flow. A browser
        # write (web.click/type/select/press_key/upload_file/evaluate) inside a
        # flow the operator already approved is admitted here and auto-signed
        # by ``flow_signer`` under the approving card's authority — never via
        # the static read-only allow-list above, and never for non-browser
        # writes (k8s.*, etc.). The signer returns None (fail-safe → ASK) when
        # no live authority exists, the signing key/execution state is unset,
        # or the bound flow's identity no longer matches the approval (a
        # rebind). The tool-gateway deviation guard still bounds the write.
        gateway_tool_name = getattr(tool, "gateway_tool_name", None)
        if (
            self._flow_signer is not None
            and gateway_tool_name in BROWSER_WRITE_TOOLS
            and not getattr(tool, "is_read_only", False)
        ):
            envelope = self._flow_signer(tool_call, gateway_tool_name)
            if envelope is not None:
                return PermissionDecision(
                    behavior=PermissionBehavior.ALLOW,
                    message=(
                        f"{gateway_tool_name} is unlocked by an approved "
                        "browser flow (SPEC-051 R-1); auto-signed under the "
                        "approving card and still bounded by the gateway "
                        "deviation guard."
                    ),
                )
        # Explicit ASK instead of delegating to agentscope's
        # PermissionEngine: its read-only fast path auto-allows read-only
        # invocations in every mode, which would silently bypass the
        # platform allow-list for unvetted read-only gateway tools. The
        # ASK parks the batch on RequireUserConfirmEvent for the SPEC-020
        # confirmation bridge.
        return PermissionDecision(
            behavior=PermissionBehavior.ASK,
            message=(
                f"{name} is outside the auto-approve allow-list; "
                "operator confirmation is required."
            ),
        )


class ToolEvidenceMiddleware(MiddlewareBase):
    """Emits tool_call / tool_result evidence frames for streamed turns (R-2).

    Frames keep the exact SPEC-011 R-2 field contract consumed by
    ``agent-stream-event.schema.json``. Only gateway-backed tools emit
    frames (identified by the ``gateway_tool_name`` attribute set at toolkit
    construction); built-in task tools and other kernel tools pass through
    silently, matching pre-middleware behavior. The gateway result dict is
    carried on ``ToolChunk``/``ToolResponse`` metadata by the tool closures
    so no JSON re-parse is needed.

    Besides the bounded ``data_summary``, each tool_result frame carries
    the full ``data`` payload when its serialized size stays within
    ``data_max_chars`` so the portal can offer a full-output view of a
    tool run regardless of how the model chooses to phrase its reply.
    Oversized payloads are omitted from the frame (the truncated summary
    still surfaces, and the full result remains in the audit trail).
    """

    def __init__(
        self,
        data_summary_max_chars: int = 2000,
        data_max_chars: int = 128000,
    ) -> None:
        self._max_chars = data_summary_max_chars
        self._data_max_chars = data_max_chars

    async def on_acting(
        self,
        agent: Any,
        input_kwargs: dict,
        next_handler: Any,
    ):
        sink = TOOL_EVIDENCE_SINK.get()
        tool_call = input_kwargs.get("tool_call")
        gateway_tool_name = None
        if tool_call is not None:
            tool = self._resolve_tool(agent, tool_call.name)
            gateway_tool_name = getattr(tool, "gateway_tool_name", None)

        if sink is None or not gateway_tool_name:
            # Blocking turn, or a non-gateway tool (task tools, builtins):
            # pass through without emitting evidence frames.
            async for item in next_handler(**input_kwargs):
                yield item
            return

        call_id = tool_call.id
        # SPEC-037 R-3: bind the in-flight invocation to its parked call
        # id so the tool closure can match it against the signed execution
        # request set by the resume path.
        from agent_service.tools.gateway_tools import CURRENT_CALL_ID

        call_token = CURRENT_CALL_ID.set(call_id)
        try:
            await sink.put({
                "type": "tool_call",
                "tool_name": gateway_tool_name,
                "call_id": call_id,
                "parameters": self._parse_parameters(tool_call),
            })

            gateway_result = None
            async for item in next_handler(**input_kwargs):
                if isinstance(item, ToolResponse):
                    gateway_result = (item.metadata or {}).get("gateway_result")
                yield item

            frame: dict[str, Any] = {
                "type": "tool_result",
                "tool_name": gateway_tool_name,
                "call_id": call_id,
            }
            if isinstance(gateway_result, dict):
                frame["status"] = gateway_result.get("status", "error")
                evidence = gateway_result.get("evidence")
                if evidence:
                    frame["evidence"] = evidence
                frame["data_summary"] = _make_data_summary(
                    gateway_result.get("data"), self._max_chars,
                )
                full_data = _make_full_data(
                    gateway_result.get("data"), self._data_max_chars,
                )
                if full_data is not None:
                    frame["data"] = full_data
                error = gateway_result.get("error")
                if error:
                    frame["error"] = error
            else:
                # The tool failed before the gateway returned a result; keep the
                # frame schema-valid.
                frame["status"] = "error"
                frame["data_summary"] = None
            await sink.put(frame)
        finally:
            CURRENT_CALL_ID.reset(call_token)

    @staticmethod
    def _resolve_tool(agent: Any, name: str) -> Any:
        """Find the registered tool instance for a tool call name."""
        toolkit = getattr(agent, "toolkit", None)
        for group in getattr(toolkit, "tool_groups", None) or []:
            for tool in getattr(group, "tools", None) or []:
                if getattr(tool, "name", None) == name:
                    return tool
        return None

    @staticmethod
    def _parse_parameters(tool_call: ToolCallBlock) -> dict:
        """Parse the tool call's raw JSON input into a parameters dict."""
        raw = getattr(tool_call, "input", "") or ""
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
