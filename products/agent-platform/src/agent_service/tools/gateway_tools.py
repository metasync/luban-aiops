"""Gateway-backed tool functions for AgentScope Toolkit (SPEC-007 R-6).

This module fetches available tools from the tool-gateway and creates
callable functions suitable for registration with AgentScope's Toolkit.
Each function calls POST /api/v2/tools/invoke on the gateway.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import httpx

LOGGER = logging.getLogger(__name__)

# Timeout for tool invocations (K8s reads can be slow on large clusters).
INVOKE_TIMEOUT_SECONDS = 30.0
DISCOVER_TIMEOUT_SECONDS = 10.0


async def discover_tools(gateway_url: str) -> list[dict]:
    """Fetch the list of available tools from the gateway.

    Returns an empty list on failure (graceful degradation).
    """
    try:
        async with httpx.AsyncClient(timeout=DISCOVER_TIMEOUT_SECONDS) as client:
            response = await client.get(f"{gateway_url}/api/v2/tools")
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
    identity_context: dict[str, Any] | None = None,
) -> dict:
    """Invoke a tool through the gateway and return the result dict."""
    request_id = str(uuid.uuid4())
    payload = {
        "tool_name": tool_name,
        "parameters": parameters,
        "request_id": request_id,
    }
    if identity_context:
        payload["identity_context"] = identity_context

    async with httpx.AsyncClient(timeout=INVOKE_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"{gateway_url}/api/v2/tools/invoke",
            json=payload,
        )
        return response.json()


def build_toolkit_functions(
    gateway_url: str,
    tool_definitions: list[dict],
) -> list[tuple[str, Any]]:
    """Build (name, callable) pairs for AgentScope Toolkit registration.

    Each callable is an async function that accepts **kwargs matching the
    tool's parameter schema and returns a JSON string result.
    """
    functions: list[tuple[str, Any]] = []

    for tool_def in tool_definitions:
        tool_name = tool_def["name"]
        description = tool_def.get("description", "")

        # Create a closure that captures tool_name and gateway_url.
        def _make_fn(name: str, desc: str):
            async def tool_fn(**kwargs: Any) -> str:
                """Invoke a platform tool via the tool-gateway."""
                result = await invoke_gateway_tool(
                    gateway_url=gateway_url,
                    tool_name=name,
                    parameters=kwargs,
                )
                return json.dumps(result, default=str)

            # Set function metadata for AgentScope tool discovery.
            tool_fn.__name__ = name.replace(".", "_")
            tool_fn.__qualname__ = name.replace(".", "_")
            tool_fn.__doc__ = desc or f"Invoke {name}"
            return tool_fn

        fn = _make_fn(tool_name, description)
        functions.append((tool_name, fn))

    return functions


async def build_toolkit(gateway_url: str):
    """Build an AgentScope Toolkit populated with gateway tools.

    Returns a Toolkit instance (possibly empty if gateway is unreachable).
    """
    from agentscope.tool import Toolkit

    toolkit = Toolkit()
    tool_definitions = await discover_tools(gateway_url)

    for tool_name, fn in build_toolkit_functions(gateway_url, tool_definitions):
        try:
            toolkit.add(fn)
            LOGGER.info("registered toolkit function: %s", tool_name)
        except Exception as exc:
            LOGGER.warning("failed to register tool %s: %s", tool_name, exc)

    return toolkit
