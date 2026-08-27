"""Authenticated internal handoff with fail-closed verification (SPEC-038 R-2).

``POST /api/v1/executions/handoff`` is the worker's only execution
surface. It authenticates the platform-internal caller with a static
scope-limited handoff token (SPEC-008 R-3 posture — the token carries
no user authority), verifies the signed execution request envelope
(the first production consumer of ``verify_envelope``), re-verifies
the invocation-boundary argument digest, and only then hands the call
to the executor. Every check fails closed and runs before any
execution; each rejection is audited ``execution_rejected``.

Response on success: ``{"receipt": <signed receipt envelope>,
"result": <gateway result dict>}``. Rejections return structured 4xx
bodies carrying the reason; transport headers never leak the token or
the envelope.
"""

from __future__ import annotations

import hmac
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from execution_runtime.core.config import get_settings
from execution_runtime.core.metrics import (
    record_completion,
    record_handoff,
    record_late_completion,
    record_rejection,
)
from execution_runtime.core.observability import log_event
from execution_runtime.core.request_context import resolve_request_id
from execution_runtime.services.audit_emitter import (
    build_audit_event,
    emit_audit_event,
)
from execution_runtime.services.execution_records import make_execution_record
from execution_runtime.services.execution_signing import (
    REASON_ARGS_DIGEST_MISMATCH,
    REASON_SIGNATURE_INVALID,
    REASON_UNAUTHORIZED,
    build_receipt,
    canonical_digest,
    verify_envelope,
)
from execution_runtime.services.executor import execute_tool, map_result_status

LOGGER = logging.getLogger(__name__)

router = APIRouter()

# Envelope fields the worker needs before it trusts anything else.
_REQUIRED_ENVELOPE_FIELDS = (
    "execution_id",
    "confirm_id",
    "call_id",
    "tool_name",
    "args_digest",
)


@router.post("/api/v1/executions/handoff")
async def handoff(request: Request):
    settings = get_settings()
    request_id = resolve_request_id(request.headers.get("x-request-id"))

    # 1. Handoff-token authentication (constant-time). An unprovisioned
    #    token fails closed: the check never degrades to open access.
    #    Byte-wise comparison: compare_digest on str rejects non-ASCII,
    #    which an unauthenticated caller controls via the header.
    presented = _presented_bearer(request.headers.get("authorization"))
    if (
        presented is None
        or not settings.handoff_token
        or not hmac.compare_digest(
            presented.encode("utf-8"), settings.handoff_token.encode("utf-8")
        )
    ):
        return _reject(
            settings,
            request_id,
            envelope=None,
            reason=REASON_UNAUTHORIZED,
            status_code=401,
        )

    # 2. Body shape: structured rejection before any envelope trust.
    body = await _parse_body(request)
    if body is None:
        record_rejection("bad_request")
        return JSONResponse(
            status_code=400,
            content={
                "request_id": request_id,
                "error": {
                    "code": "EXECUTION_REJECTED",
                    "reason": "bad_request",
                    "message": "the handoff body is not a valid envelope payload",
                },
            },
        )
    envelope = body["request"]
    arguments = body["arguments"]
    delegated_token = body["delegated_token"]

    missing = [key for key in _REQUIRED_ENVELOPE_FIELDS if not envelope.get(key)]
    if missing or not isinstance(arguments, dict):
        record_rejection("bad_request")
        return JSONResponse(
            status_code=400,
            content={
                "request_id": request_id,
                "error": {
                    "code": "EXECUTION_REJECTED",
                    "reason": "bad_request",
                    "message": "the execution envelope is missing required fields",
                },
            },
        )

    # 3. Signature verification (SPEC-037 contract). A missing signing
    #    key rejects here — the worker never executes an unverifiable
    #    request. Non-ASCII signatures are rejected up front so the
    #    constant-time comparison below never sees them.
    key = settings.execution_signing_key
    signature = envelope.get("signature") or ""
    if (
        not key
        or not signature
        or not signature.isascii()
        or not verify_envelope(envelope, signature, key)
    ):
        return _reject(
            settings,
            request_id,
            envelope=envelope,
            reason=REASON_SIGNATURE_INVALID,
            status_code=400,
        )

    # 4. Invocation-boundary argument digest re-verification
    #    (byte-wise, like the handoff-token comparison).
    if not hmac.compare_digest(
        canonical_digest(arguments).encode("utf-8"),
        (envelope.get("args_digest") or "").encode("utf-8"),
    ):
        return _reject(
            settings,
            request_id,
            envelope=envelope,
            reason=REASON_ARGS_DIGEST_MISMATCH,
            status_code=400,
        )

    # 5. Single-flight execution keyed by the stable execution id
    #    (SPEC-038 R-5): concurrent duplicates join, replays reuse.
    record_handoff()
    flights = request.app.state.single_flights
    outcome, _owner = await flights.run(
        envelope["execution_id"],
        lambda: _execute_and_close(
            request, settings, envelope, arguments, delegated_token, request_id
        ),
    )
    return JSONResponse(status_code=200, content=outcome)


def _presented_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


async def _parse_body(request: Request) -> dict[str, Any] | None:
    """Parse the handoff body into its three fields, or None on any flaw."""
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 — malformed bodies reject uniformly
        return None
    if not isinstance(payload, dict):
        return None
    envelope = payload.get("request")
    arguments = payload.get("arguments")
    delegated_token = payload.get("delegated_token")
    if not isinstance(envelope, dict) or arguments is None:
        return None
    if delegated_token is not None and not isinstance(delegated_token, str):
        return None
    return {
        "request": envelope,
        "arguments": arguments,
        "delegated_token": delegated_token,
    }


async def _execute_and_close(
    request: Request,
    settings,
    envelope: dict[str, Any],
    arguments: dict[str, Any],
    delegated_token: str | None,
    request_id: str,
) -> dict[str, Any]:
    """Run the invocation once and close the execution record (R-3)."""
    store = request.app.state.execution_record_store
    result = await execute_tool(
        settings,
        envelope["tool_name"],
        arguments,
        delegated_token,
        request_id,
    )
    status = map_result_status(result)
    receipt = build_receipt(envelope, status, result, request_id,
                            settings.execution_signing_key)

    # Best-effort durable close: first write wins. A row already closed
    # (the resumed stream's timeout receipt, or a replayed close) keeps
    # its receipt — the late completion is logged and counted, never
    # overwrites.
    try:
        existing = store.close_execution(
            make_execution_record(envelope), receipt, digest_match=True
        )
    except Exception as exc:  # noqa: BLE001 — durability degrades, never the response
        existing = None
        LOGGER.warning(
            "execution record receipt write failed for %s: %s",
            envelope["execution_id"],
            exc,
        )
    if existing is not None:
        record_late_completion()
        log_event(
            LOGGER,
            "execution_late_completion",
            execution_id=envelope["execution_id"],
            confirm_id=envelope["confirm_id"],
            status=status,
            request_id=request_id,
        )
    record_completion(status)
    _emit_completed(settings, envelope, receipt, request_id)
    return {"receipt": receipt, "result": result}


def _emit_completed(
    settings,
    envelope: dict[str, Any],
    receipt: dict[str, Any],
    request_id: str,
) -> None:
    """Emit execution_completed correlating with the resume's audit chain."""
    decider = envelope.get("decider_user_id")
    event = build_audit_event(
        "execution_completed",
        request_id,
        "success" if receipt["status"] == "succeeded" else "error",
        details={
            "confirm_id": envelope.get("confirm_id"),
            "execution_id": envelope.get("execution_id"),
            "call_id": envelope.get("call_id"),
            "tool_name": envelope.get("tool_name"),
            "status": receipt["status"],
            "duration_ms": _execution_duration_ms(envelope),
            "request_id": receipt["request_id"],
        },
        subject=decider,
        username=decider,
        session_id=envelope.get("session_id"),
    )
    emit_audit_event(settings, event)


def _execution_duration_ms(envelope: dict[str, Any]) -> int:
    """Whole-milliseconds between request signing and receipt close."""
    try:
        started = datetime.strptime(
            envelope["requested_at"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
    except (KeyError, ValueError):
        return 0
    elapsed = datetime.now(timezone.utc) - started
    return max(int(elapsed.total_seconds() * 1000), 0)


def _reject(
    settings,
    request_id: str,
    envelope: dict[str, Any] | None,
    reason: str,
    status_code: int,
):
    """Structured, audited, fail-closed rejection — nothing executed."""
    record_rejection(reason)
    log_event(
        LOGGER,
        "execution_handoff_rejected",
        reason=reason,
        request_id=request_id,
        confirm_id=(envelope or {}).get("confirm_id"),
        execution_id=(envelope or {}).get("execution_id"),
    )
    if envelope is not None:
        decider = envelope.get("decider_user_id")
        event = build_audit_event(
            "execution_rejected",
            request_id,
            "deny",
            details={
                "confirm_id": envelope.get("confirm_id"),
                "execution_id": envelope.get("execution_id"),
                "call_id": envelope.get("call_id"),
                "tool_name": envelope.get("tool_name"),
                "reason": reason,
                "rejected_by": "execution-runtime",
            },
            subject=decider,
            username=decider,
            session_id=envelope.get("session_id"),
        )
        emit_audit_event(settings, event)
    return JSONResponse(
        status_code=status_code,
        content={
            "request_id": request_id,
            "error": {
                "code": "EXECUTION_REJECTED",
                "reason": reason,
                "message": (
                    "execution request verification failed: "
                    "this mutating action was not executed"
                ),
            },
        },
    )
