"""Gateway-backed tool functions for AgentScope Toolkit (SPEC-007 R-6, SPEC-008 R-5).

This module fetches available tools from the tool-gateway and creates
callable functions suitable for registration with AgentScope's Toolkit.
Each function calls POST /api/v2/tools/invoke on the gateway.

The owning user's delegated token (forwarded by the gateway) is bound into the
toolkit closures and presented as ``Authorization: Bearer`` on discovery and
invocation; identity is carried exclusively by this token, never in the body.
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


def build_toolkit_functions(
    gateway_url: str,
    tool_definitions: list[dict],
    bearer_token: str | None = None,
) -> list[tuple[str, Any]]:
    """Build (name, callable) pairs for AgentScope Toolkit registration.

    Each callable is an async function that accepts **kwargs matching the
    tool's parameter schema and returns a JSON string result. The delegated
    token is bound into every closure so one user's credential is never used
    for another user's session.
    """
    functions: list[tuple[str, Any]] = []

    for tool_def in tool_definitions:
        tool_name = tool_def["name"]
        description = tool_def.get("description", "")

        # Create a closure that captures tool_name, gateway_url, and the token.
        def _make_fn(name: str, desc: str, token: str | None):
            async def tool_fn(**kwargs: Any) -> str:
                """Invoke a platform tool via the tool-gateway."""
                result = await invoke_gateway_tool(
                    gateway_url=gateway_url,
                    tool_name=name,
                    parameters=kwargs,
                    bearer_token=token,
                )
                return json.dumps(result, default=str)

            # Set function metadata for AgentScope tool discovery.
            tool_fn.__name__ = name.replace(".", "_")
            tool_fn.__qualname__ = name.replace(".", "_")
            tool_fn.__doc__ = desc or f"Invoke {name}"
            return tool_fn

        fn = _make_fn(tool_name, description, bearer_token)
        functions.append((tool_name, fn))

    return functions


async def build_toolkit(gateway_url: str, bearer_token: str | None = None):
    """Build an AgentScope Toolkit populated with gateway tools.

    Returns a Toolkit instance (empty if no token is available or the gateway
    is unreachable).
    """
    from agentscope.tool import Toolkit

    toolkit = Toolkit()
    tool_definitions = await discover_tools(gateway_url, bearer_token)

    for tool_name, fn in build_toolkit_functions(
        gateway_url, tool_definitions, bearer_token
    ):
        try:
            toolkit.add(fn)
            LOGGER.info("registered toolkit function: %s", tool_name)
        except Exception as exc:
            LOGGER.warning("failed to register tool %s: %s", tool_name, exc)

    return toolkit
