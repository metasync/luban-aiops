"""Kernel middleware aligning AgentScope with the platform contract (SPEC-018).

All cross-cutting kernel behavior lives on the supported ``MiddlewareBase``
surface instead of private agentscope internals:

- ``GatewayPermissionMiddleware`` (R-1) pre-answers the permission gate for
  a headless SSE runtime: vetted read-only gateway tools and the built-in
  task tools are ALLOWed; everything else delegates to the built-in
  resolution (ASK default), which a headless stream cannot answer.
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
from contextvars import ContextVar
from typing import Any

from agentscope.message import ToolCallBlock
from agentscope.middleware import MiddlewareBase
from agentscope.permission import PermissionBehavior, PermissionDecision
from agentscope.tool import ToolResponse

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

# Vetted tool names that may bypass AgentScope's interactive ASK permission
# gate. Only read-only tools on this explicit allow-list are auto-approved;
# every other tool keeps the ASK default (effectively non-runnable in a
# headless stream until interactively confirmed). Admission and policy are
# still enforced by the tool-gateway on every invocation.
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


class GatewayPermissionMiddleware(MiddlewareBase):
    """Pre-answers AgentScope's permission gate for a headless kernel (R-1).

    AgentScope 2.x pauses every custom function tool behind an interactive
    confirmation prompt (default permission decision: ASK). A headless SSE
    stream can never answer that prompt, so the agent stalls and emits no
    output at all. Tools on the explicit allow-list (read-only AND vetted)
    are pre-approved — the tool-gateway still enforces admission and policy
    on every invocation and each call is audit-logged; anything outside the
    allow-list keeps the ASK default rather than being blanket-approved.
    """

    def __init__(self, auto_allowed: frozenset[str] | None = None) -> None:
        self._allow_list = (
            auto_allowed if auto_allowed is not None else _load_auto_allowed_tools()
        )

    async def on_check_permission(
        self,
        agent: Any,
        input_kwargs: dict,
        next_handler: Any,
    ) -> PermissionDecision:
        tool = input_kwargs.get("tool")
        name = getattr(tool, "name", None)
        if name in TASK_TOOL_NAMES:
            # State-local task tools never touch external systems.
            return PermissionDecision(
                behavior=PermissionBehavior.ALLOW,
                message=f"{name} mutates only session-local agent state.",
            )
        if (
            tool is not None
            and getattr(tool, "is_read_only", False)
            and name in self._allow_list
        ):
            return PermissionDecision(
                behavior=PermissionBehavior.ALLOW,
                message=(
                    "Vetted read-only gateway tool; admission and policy "
                    "are enforced by the tool-gateway."
                ),
            )
        # Everything else keeps the built-in resolution (ASK default for
        # custom function tools), preserving today's headless parity.
        return await next_handler(**input_kwargs)


class ToolEvidenceMiddleware(MiddlewareBase):
    """Emits tool_call / tool_result evidence frames for streamed turns (R-2).

    Frames keep the exact SPEC-011 R-2 field contract consumed by
    ``agent-stream-event.schema.json``. Only gateway-backed tools emit
    frames (identified by the ``gateway_tool_name`` attribute set at toolkit
    construction); built-in task tools and other kernel tools pass through
    silently, matching pre-middleware behavior. The gateway result dict is
    carried on ``ToolChunk``/``ToolResponse`` metadata by the tool closures
    so no JSON re-parse is needed.
    """

    def __init__(self, data_summary_max_chars: int = 2000) -> None:
        self._max_chars = data_summary_max_chars

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
            error = gateway_result.get("error")
            if error:
                frame["error"] = error
        else:
            # The tool failed before the gateway returned a result; keep the
            # frame schema-valid.
            frame["status"] = "error"
            frame["data_summary"] = None
        await sink.put(frame)

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
