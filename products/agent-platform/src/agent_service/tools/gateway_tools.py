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


def _make_tool_fn(
    gateway_url: str,
    name: str,
    desc: str,
):
    """Build the async gateway-invocation closure for one tool.

    The closure captures ``name`` and ``gateway_url``; the owning user's
    delegated token is read from ``DELEGATED_TOKEN`` at call time so one
    user's credential is never used for another user's session and cached
    toolkits survive token refresh. The returned ``ToolChunk`` carries the
    raw gateway result on its metadata so ``ToolEvidenceMiddleware`` can
    emit evidence frames without re-parsing the model-visible text
    (SPEC-018 R-2).
    """
    from agentscope.message import TextBlock
    from agentscope.tool import ToolChunk

    async def tool_fn(**kwargs: Any) -> ToolChunk:
        """Invoke a platform tool via the tool-gateway."""
        result = await invoke_gateway_tool(
            gateway_url=gateway_url,
            tool_name=name,
            parameters=kwargs,
            bearer_token=DELEGATED_TOKEN.get(),
        )
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
            fn = _make_tool_fn(gateway_url, tool_name, description)
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
