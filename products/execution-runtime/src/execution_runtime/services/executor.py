"""One-shot gateway execution for handed-off requests (SPEC-038 R-3).

Runs exactly one tool invocation per handoff against the tool-gateway,
presenting the confirmer's delegated token as bearer so the gateway
re-evaluates the approving identity (the third auth layer; the token
itself is never logged or persisted). Timeouts and transport failures
map onto the same structured result shapes agent-service produces, so
the resumed-stream receipt handling cannot tell them apart.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from execution_runtime.core.config import ExecutionSettings

LOGGER = logging.getLogger(__name__)


async def execute_tool(
    settings: ExecutionSettings,
    tool_name: str,
    arguments: dict[str, Any],
    delegated_token: str | None,
    request_id: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Invoke one tool through the gateway and return the result dict.

    Never raises: every failure mode maps onto a structured error
    result with the forwarded ``request_id``, so the handoff route can
    always sign a receipt for the attempt.
    """
    if not settings.tool_gateway_url:
        return _error_result(
            tool_name,
            request_id,
            "NO_GATEWAY",
            "the worker has no tool-gateway endpoint configured",
        )
    if not delegated_token:
        return _error_result(
            tool_name,
            request_id,
            "NO_CREDENTIAL",
            "no delegated token was forwarded for tool invocation",
        )

    payload = {
        "tool_name": tool_name,
        "parameters": arguments,
        # The resumed stream's x-request-id rides the gateway call so
        # tool_invoked events correlate with execution_completed.
        "request_id": request_id,
    }
    # SPEC-049 R-1: forward the chat session id from the signed envelope so
    # a stateful gateway connector (the browser pool) keys the resumed
    # write-tier interaction onto the same session the owner's read-tier
    # setup bound the flow to. It is a correlation handle, not authority —
    # the bearer token still carries the approving identity.
    if session_id:
        payload["session_id"] = session_id
    try:
        async with httpx.AsyncClient(
            timeout=settings.gateway_timeout_seconds
        ) as client:
            response = await client.post(
                f"{settings.tool_gateway_url.rstrip('/')}/api/v2/tools/invoke",
                json=payload,
                headers={"Authorization": f"Bearer {delegated_token}"},
            )
    except httpx.TimeoutException:
        return _error_result(
            tool_name,
            request_id,
            "TIMEOUT",
            "tool invocation timed out before the gateway answered",
        )
    except httpx.HTTPError as exc:
        # Transport detail stays in the log, never the token.
        LOGGER.warning(
            "gateway invocation transport failure for %s: %s",
            tool_name,
            exc,
        )
        return _error_result(
            tool_name,
            request_id,
            "TRANSPORT_ERROR",
            "the tool gateway was unreachable",
        )
    try:
        return response.json()
    except ValueError:
        LOGGER.warning(
            "gateway invocation returned a non-JSON body for %s (status %s)",
            tool_name,
            response.status_code,
        )
        return _error_result(
            tool_name,
            request_id,
            "BAD_GATEWAY_RESPONSE",
            "the tool gateway returned an unparseable response",
        )


def map_result_status(result: dict[str, Any]) -> str:
    """Map a gateway result onto the receipt status vocabulary.

    Mirrors the kernel's resumed-stream mapping: ``success`` results
    close ``succeeded``; an ``error.code`` of ``TIMEOUT`` closes
    ``timeout``; anything else closes ``failed``.
    """
    if result.get("status") == "success":
        return "succeeded"
    error = result.get("error")
    error = error if isinstance(error, dict) else {}
    if error.get("code") == "TIMEOUT":
        return "timeout"
    return "failed"


def _error_result(
    tool_name: str,
    request_id: str,
    code: str,
    message: str,
) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "status": "error",
        "request_id": request_id,
        "error": {"code": code, "message": message},
    }
