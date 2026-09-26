"""One non-retrying gateway exchange; transport uncertainty is not a tool report."""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from execution_runtime.core.config import ExecutionSettings
from execution_runtime.services.execution_protocol import ProtocolError, validate


class GatewayUncertain(ProtocolError):
    """No trustworthy tool report; the target may still have acted."""


async def execute_tool(
    settings: ExecutionSettings,
    tool_name: str,
    arguments: dict[str, Any],
    delegated_token: str | None,
    request_id: str,
    session_id: str | None = None,
    approval_kind: str | None = None,
    execution_id: str | None = None,
) -> dict[str, Any]:
    if not settings.tool_gateway_url or not delegated_token:
        raise GatewayUncertain("gateway_not_configured" if not settings.tool_gateway_url else "credential_missing")
    payload = {"tool_name": tool_name, "parameters": arguments, "request_id": request_id}
    if session_id:
        payload["session_id"] = session_id
    if approval_kind:
        payload["approval_kind"] = approval_kind
    headers = {"Authorization": f"Bearer {delegated_token}", "x-request-id": request_id}
    if execution_id:
        headers["x-execution-id"] = execution_id
    try:
        async with asyncio.timeout(min(settings.gateway_timeout_seconds, 30)):
            async with httpx.AsyncClient(
                timeout=settings.gateway_timeout_seconds, follow_redirects=False,
                trust_env=False, transport=httpx.AsyncHTTPTransport(retries=0),
            ) as client:
                response = await client.post(
                    f"{settings.tool_gateway_url.rstrip('/')}/api/v2/tools/invoke",
                    json=payload, headers=headers,
                )
        # Schema-valid tool failures are reports even on an HTTP error. Redirects
        # are never followed and cannot be interpreted as successful execution.
        if 300 <= response.status_code < 400 or response.headers.get("x-request-id") != request_id:
            raise GatewayUncertain("response_invalid")
        result = response.json()
        validate("tool-result", result)
        if (result["tool_name"] != tool_name
                or (result["status"] == "success" and ("data" not in result or result.get("error")))
                or (result["status"] != "success" and not result.get("error"))):
            raise GatewayUncertain("response_invalid")
        return result
    except (TimeoutError, httpx.HTTPError):
        raise GatewayUncertain("transport_error") from None
    except (ValueError, TypeError, RecursionError):
        raise GatewayUncertain("response_invalid") from None


def map_result_status(result: dict[str, Any]) -> str:
    """Map a validated tool report, never a synthetic transport error."""
    if result["status"] == "success":
        return "succeeded"
    if (result.get("error") or {}).get("code") == "TIMEOUT":
        return "timeout"
    return "failed"
