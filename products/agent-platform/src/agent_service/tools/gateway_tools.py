"""Gateway-backed tool functions for AgentScope Toolkit (SPEC-007 R-6, SPEC-008 R-5, SPEC-011 R-2).

This module fetches available tools from the tool-gateway and creates
callable functions suitable for registration with AgentScope's Toolkit.
Each function calls POST /api/v2/tools/invoke on the gateway.

The owning user's delegated token (forwarded by the gateway) is bound into the
toolkit closures and presented as ``Authorization: Bearer`` on discovery and
invocation; identity is carried exclusively by this token, never in the body.

SPEC-011 R-2: each closure optionally posts tool_call / tool_result trace
events to a per-request asyncio.Queue so the stream carries a complete audit
of tool usage alongside text deltas.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    import asyncio

LOGGER = logging.getLogger(__name__)

# Timeout for tool invocations (K8s reads can be slow on large clusters).
INVOKE_TIMEOUT_SECONDS = 30.0
DISCOVER_TIMEOUT_SECONDS = 10.0


def _build_gateway_function_tool_class():
    """Return the FunctionTool subclass used for gateway tools.

    AgentScope 2.x pauses every custom function tool behind an interactive
    ``RequireUserConfirmEvent`` (default permission decision: ASK). A headless
    SSE stream can never answer that prompt, so the agent stalls and emits no
    output at all. Gateway tools are pre-approved by design — they are
    registered and policy-checked by the tool-gateway — so read-only tools
    are allowed outright, mirroring AgentScope's own MCP adapter behaviour.
    Non-read-only tools keep the ASK default.
    """
    from agentscope.permission import PermissionBehavior, PermissionDecision
    from agentscope.tool import FunctionTool

    class GatewayFunctionTool(FunctionTool):
        async def check_permissions(self, *_args, **_kwargs):
            if self.is_read_only:
                return PermissionDecision(
                    behavior=PermissionBehavior.ALLOW,
                    message=(
                        "Read-only gateway tool; admission and policy are "
                        "enforced by the tool-gateway."
                    ),
                )
            return await super().check_permissions(*_args, **_kwargs)

    return GatewayFunctionTool


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


def _make_tool_fn(
    gateway_url: str,
    name: str,
    desc: str,
    token: str | None,
    tq: "asyncio.Queue | None",
    max_chars: int,
):
    """Build the async gateway-invocation closure for one tool.

    The closure captures ``name``, ``gateway_url`` and the delegated token so
    one user's credential is never used for another user's session. When
    ``tq`` is provided it posts ``tool_call`` / ``tool_result`` trace events
    for evidence panel rendering (SPEC-011 R-2).
    """
    async def tool_fn(**kwargs: Any) -> str:
        """Invoke a platform tool via the tool-gateway."""
        call_id = str(uuid.uuid4())

        # Post tool_call trace event before invocation.
        if tq is not None:
            await tq.put({
                "type": "tool_call",
                "tool_name": name,
                "call_id": call_id,
                "parameters": kwargs,
            })

        result = await invoke_gateway_tool(
            gateway_url=gateway_url,
            tool_name=name,
            parameters=kwargs,
            bearer_token=token,
        )

        # Post tool_result trace event after invocation.
        if tq is not None:
            trace_event: dict[str, Any] = {
                "type": "tool_result",
                "tool_name": name,
                "call_id": call_id,
                "status": result.get("status", "error"),
            }
            evidence = result.get("evidence")
            if evidence:
                trace_event["evidence"] = evidence
            trace_event["data_summary"] = _make_data_summary(
                result.get("data"), max_chars,
            )
            error = result.get("error")
            if error:
                trace_event["error"] = error
            await tq.put(trace_event)

        return json.dumps(result, default=str)

    # Set function metadata for AgentScope tool discovery.
    tool_fn.__name__ = name.replace(".", "_")
    tool_fn.__qualname__ = name.replace(".", "_")
    tool_fn.__doc__ = desc or f"Invoke {name}"
    return tool_fn


def build_function_tools(
    gateway_url: str,
    tool_definitions: list[dict],
    bearer_token: str | None = None,
    trace_queue: "asyncio.Queue | None" = None,
    data_summary_max_chars: int = 2000,
) -> list:
    """Build AgentScope ``FunctionTool`` objects for each gateway tool def.

    Each returned tool wraps an async closure that accepts **kwargs matching
    the tool's parameter schema and returns a JSON string result. The
    delegated token is bound into every closure so one user's credential is
    never used for another user's session.

    The closure only exposes **kwargs, so AgentScope would derive an empty
    input schema; the gateway's ``parameters_schema`` is therefore bound onto
    each tool explicitly so the model sees the real parameters.

    Tools that fail to wrap are skipped with a warning (never a hard failure).

    When ``trace_queue`` is provided, each closure posts ``tool_call`` and
    ``tool_result`` trace events for evidence panel rendering (SPEC-011 R-2).
    """
    tool_cls = _build_gateway_function_tool_class()
    tools: list = []
    for tool_def in tool_definitions:
        tool_name = tool_def["name"]
        description = tool_def.get("description", "")
        try:
            fn = _make_tool_fn(
                gateway_url,
                tool_name,
                description,
                bearer_token,
                trace_queue,
                data_summary_max_chars,
            )
            tool = tool_cls(
                fn,
                name=tool_name.replace(".", "_"),
                description=description or f"Invoke {tool_name}",
                is_read_only=(tool_def.get("risk_level") == "read"),
            )
            tool.input_schema = _normalize_input_schema(
                tool_def.get("parameters_schema"),
            )
            tools.append(tool)
            LOGGER.info("registered toolkit function: %s", tool_name)
        except Exception as exc:
            LOGGER.warning("failed to build tool %s: %s", tool_name, exc)
    return tools


def build_gateway_toolkit(
    tool_definitions: list[dict],
    gateway_url: str,
    bearer_token: str | None = None,
    trace_queue: "asyncio.Queue | None" = None,
    data_summary_max_chars: int = 2000,
):
    """Assemble an AgentScope Toolkit from gateway tool definitions.

    AgentScope 2.x has no ``Toolkit.add``; tools are passed at construction as
    ``Toolkit(tools=[FunctionTool(...)])``.
    """
    from agentscope.tool import Toolkit

    tools = build_function_tools(
        gateway_url,
        tool_definitions,
        bearer_token,
        trace_queue=trace_queue,
        data_summary_max_chars=data_summary_max_chars,
    )
    return Toolkit(tools=tools)


async def build_toolkit(
    gateway_url: str,
    bearer_token: str | None = None,
    trace_queue: "asyncio.Queue | None" = None,
    data_summary_max_chars: int = 2000,
):
    """Build an AgentScope Toolkit populated with gateway tools.

    Returns a Toolkit instance (empty if no token is available or the gateway
    is unreachable).

    When ``trace_queue`` is provided, toolkit functions emit tool trace
    events for evidence panel rendering (SPEC-011 R-2).
    """
    tool_definitions = await discover_tools(gateway_url, bearer_token)
    return build_gateway_toolkit(
        tool_definitions,
        gateway_url,
        bearer_token,
        trace_queue=trace_queue,
        data_summary_max_chars=data_summary_max_chars,
    )
