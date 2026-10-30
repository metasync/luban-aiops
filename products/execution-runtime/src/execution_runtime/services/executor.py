"""One non-retrying gateway exchange; transport uncertainty is not a tool report."""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from execution_runtime.core.config import ExecutionSettings
from execution_runtime.services.execution_protocol import ProtocolError, validate

_INVOKE_PATH = "/api/v2/tools/invoke"
# SPEC-070: the private delegated route, callable only by this workload identity.
_DELEGATED_INVOKE_PATH = "/api/v2/tools/invoke-delegated"


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
    *,
    delegated_execution=None,
) -> dict[str, Any]:
    if not settings.tool_gateway_url:
        raise GatewayUncertain("gateway_not_configured")
    if delegated_execution is not None:
        # SPEC-070: a verified delegated execution forwards through the private
        # route under the workload identity, never with a human bearer as auth.
        return await _execute_delegated(
            settings, tool_name, arguments, delegated_token, request_id,
            session_id, approval_kind, execution_id, delegated_execution,
        )
    if not delegated_token:
        raise GatewayUncertain("credential_missing")
    payload = {"tool_name": tool_name, "parameters": arguments, "request_id": request_id}
    if session_id:
        payload["session_id"] = session_id
    if approval_kind:
        payload["approval_kind"] = approval_kind
    headers = {"Authorization": f"Bearer {delegated_token}", "x-request-id": request_id}
    if execution_id:
        headers["x-execution-id"] = execution_id
    return await _post_invoke(settings, _INVOKE_PATH, payload, headers, request_id, tool_name)


async def _execute_delegated(
    settings: ExecutionSettings,
    tool_name: str,
    arguments: dict[str, Any],
    delegated_token: str | None,
    request_id: str,
    session_id: str | None,
    approval_kind: str | None,
    execution_id: str | None,
    delegated_execution: Any,
) -> dict[str, Any]:
    """Forward a verified delegated execution to the private gateway route.

    The channel is authenticated with the execution-runtime workload identity
    (a projected JWT reread per send), never a human bearer; the verified
    projection and both human bearers ride the body so the gateway can
    independently re-verify them against the identity provider. ``check_send``
    and the workload-token read run BEFORE the exchange, so a stale binding, an
    expired human, or a missing workload credential stays a clean pre-send
    refusal with its own reason rather than being flattened into a transport
    uncertainty by the ``ValueError`` handler below.
    """
    from execution_runtime.services.delegated_execution import read_workload_token

    delegated_execution.check_send(
        tool_name, arguments, delegated_token, session_id, approval_kind, execution_id
    )
    workload_token = read_workload_token(settings)
    payload = {
        "projection": delegated_execution.projection,
        "parameters": arguments,
        "requester_token": delegated_execution.requester_token,
        "decider_token": delegated_token,
        "request_id": request_id,
    }
    headers = {"Authorization": f"Bearer {workload_token}", "x-request-id": request_id}
    return await _post_invoke(
        settings, _DELEGATED_INVOKE_PATH, payload, headers, request_id, tool_name
    )


async def _post_invoke(
    settings: ExecutionSettings,
    path: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    request_id: str,
    tool_name: str,
) -> dict[str, Any]:
    """One non-retrying gateway POST; a validated tool report or uncertainty."""
    try:
        async with asyncio.timeout(min(settings.gateway_timeout_seconds, 30)):
            async with httpx.AsyncClient(
                timeout=settings.gateway_timeout_seconds, follow_redirects=False,
                trust_env=False, transport=httpx.AsyncHTTPTransport(retries=0),
            ) as client:
                response = await client.post(
                    f"{settings.tool_gateway_url.rstrip('/')}{path}",
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
