"""Blocking handoff client for the execution-runtime worker (SPEC-038 R-4).

Approved mutating invocations in a resumed stream hand the signed SPEC-037
envelope, the parked arguments, and the confirmer's delegated token to the
execution-runtime worker and block on its response with a bounded timeout
(``AGENT_EXECUTION_WORKER_TIMEOUT_SECONDS``). The worker performs the
tool-gateway call, writes the receipt, and returns the gateway result,
which flows into the existing evidence-frame and transcript paths.

Fail-closed posture: a missing worker URL or handoff token raises before
any network call (reason ``worker_unavailable``), timeouts raise
``WorkerHandoffTimeout`` so the resumed stream surfaces the structured
timeout result, and any transport error raises ``WorkerHandoffError``
with ``worker_unavailable`` — there is no in-process fallback. Worker
verification rejections (4xx) carry the worker's reason back to the
invocation boundary. The handoff token and the delegated token are never
logged.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

LOGGER = logging.getLogger(__name__)

HANDOFF_PATH = "/api/v1/executions/handoff"

# Rejection reason used when the handoff cannot leave the process (missing
# configuration) or cannot reach the worker (transport failure).
REASON_WORKER_UNAVAILABLE = "worker_unavailable"


class WorkerHandoffError(Exception):
    """Fail-closed handoff failure carrying a rejection reason."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class WorkerHandoffTimeout(Exception):
    """The worker did not answer within the bounded budget.

    Kept separate from ``WorkerHandoffError``: a timeout is not a
    rejection — the call may still be running, so the resumed stream
    surfaces the structured timeout result and the record closes with a
    ``timeout`` receipt (first-write-wins with the worker's close).
    """


async def handoff(
    request: dict[str, Any],
    arguments: dict[str, Any],
    delegated_token: str | None,
    settings: Any,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Hand one signed execution to the worker and return its result.

    ``settings`` is the kernel's ``RuntimeSettings``; the worker URL, the
    handoff token, and the timeout budget all come from it. ``request_id``
    rides ``x-request-id`` so the worker's receipt and audit emission
    correlate with the resume. Raises ``WorkerHandoffError`` (with the
    worker's reason when one exists) or ``WorkerHandoffTimeout``; never
    returns an error dict.
    """
    if settings is None:
        raise WorkerHandoffError(
            REASON_WORKER_UNAVAILABLE,
            "execution worker settings are not available",
        )
    worker_url = getattr(settings, "execution_worker_url", None)
    handoff_token = getattr(settings, "execution_handoff_token", None)
    if not worker_url or not handoff_token:
        raise WorkerHandoffError(
            REASON_WORKER_UNAVAILABLE,
            "execution worker URL or handoff token is not configured",
        )

    headers = {"Authorization": f"Bearer {handoff_token}"}
    if request_id:
        headers["x-request-id"] = request_id
    body = {
        "request": request,
        "arguments": arguments,
        "delegated_token": delegated_token,
    }
    timeout = getattr(settings, "execution_worker_timeout_seconds", 60.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{worker_url}{HANDOFF_PATH}",
                json=body,
                headers=headers,
            )
    except httpx.TimeoutException as exc:
        LOGGER.warning("execution handoff timed out after %.1fs", timeout)
        raise WorkerHandoffTimeout(
            "execution handoff timed out before the worker answered"
        ) from exc
    except httpx.HTTPError as exc:
        # Log the exception class only: transport messages can echo
        # URLs or payloads and must never leak credentials.
        LOGGER.warning(
            "execution handoff transport failure: %s", exc.__class__.__name__
        )
        raise WorkerHandoffError(
            REASON_WORKER_UNAVAILABLE,
            "execution worker is unreachable",
        ) from exc

    if response.status_code == 200:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise WorkerHandoffError(
                REASON_WORKER_UNAVAILABLE,
                "execution worker returned a malformed response",
            )
        return result

    # Structured 4xx rejections carry the worker's verification reason;
    # anything unparsable degrades to worker_unavailable.
    LOGGER.warning(
        "execution handoff rejected with status %d", response.status_code
    )
    reason = REASON_WORKER_UNAVAILABLE
    try:
        payload = response.json()
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict) and error.get("reason"):
            reason = str(error["reason"])
    except ValueError:
        pass
    raise WorkerHandoffError(
        reason,
        f"execution worker rejected the handoff ({response.status_code})",
    )


async def handoff_original(request, arguments, delegated_token, settings, attempt_request_id):
    """v3 exchange: raw output leaves this boundary only as a verified original.

    The invocation coordinator must register first and durably accept afterward.
    Exceptions (including cancellation) never mean the target did not act.
    """
    from agent_service.services.execution_protocol import (
        ProtocolError, SAFE_REQUEST_ID, validate, validate_original, validate_request,
    )
    from agent_service.services.execution_signing import canonical_digest

    key = getattr(settings, "execution_signing_key", None)
    validate_request(request, key)
    worker_url = getattr(settings, "execution_worker_url", None)
    token = getattr(settings, "execution_handoff_token", None)
    if not worker_url or not token:
        raise ProtocolError("gateway_not_configured")
    if not isinstance(delegated_token, str) or not delegated_token.strip():
        raise ProtocolError("credential_missing")
    if not isinstance(arguments, dict) or canonical_digest(arguments) != request["args_digest"]:
        raise ProtocolError("args_digest_mismatch")
    if not isinstance(attempt_request_id, str) or not SAFE_REQUEST_ID.fullmatch(attempt_request_id):
        raise ProtocolError("bad_request")
    timeout = getattr(settings, "execution_worker_timeout_seconds", 60.0)
    if not isinstance(timeout, (int, float)) or not 0 < timeout <= 120:
        raise ProtocolError("bad_request")
    try:
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False,
                                         transport=httpx.AsyncHTTPTransport(retries=0)) as client:
                response = await client.post(
                    worker_url.rstrip("/") + HANDOFF_PATH,
                    headers={"Authorization": f"Bearer {token}", "x-request-id": attempt_request_id},
                    json={"request": request, "arguments": arguments, "delegated_token": delegated_token},
                )
        if response.headers.get("x-request-id") != attempt_request_id:
            raise ProtocolError("response_invalid")
        payload = response.json()
        validate("execution-handoff-response", payload)
        if payload["request_id"] != attempt_request_id:
            raise ProtocolError("response_invalid")
    except (TimeoutError, httpx.TimeoutException):
        raise ProtocolError("wait_expired") from None
    except httpx.HTTPError:
        raise ProtocolError("transport_error") from None
    except (ValueError, TypeError, KeyError, RecursionError):
        raise ProtocolError("response_invalid") from None
    if payload["kind"] != "original_result":
        # A separate durable read may establish scoped refusal. An arbitrary
        # error response or replay is never usable original output.
        raise ProtocolError("metadata_replay" if payload["kind"] == "status_only" else "transport_error")
    if response.status_code != 200:
        raise ProtocolError("response_invalid")
    return validate_original(payload, request, key, attempt_request_id, attempt_request_id)
