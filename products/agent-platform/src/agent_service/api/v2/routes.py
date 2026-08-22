"""Platform-owned agent-service contract v2 routes.

This module is the adapter layer between the HTTP boundary and the AgentScope
kernel. No AgentScope types leak through route signatures or response bodies.
Identity is conveyed via headers (X-User-ID, x-request-id), never in bodies.
The gateway-forwarded delegated token arrives as ``Authorization: Bearer`` and
is relayed opaquely to the kernel for tool calls (SPEC-008 R-5); the platform
never inspects or signs it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse

from agent_service.core.metrics import record_chat_request
from agent_service.schemas.v2 import (
    AgentChatConfirmRequest,
    AgentChatRequest,
    AgentChatResponse,
    AgentHealth,
    AgentRuntimeMetadata,
    AgentSession,
    AgentSessionCreateRequest,
    AgentSessionList,
    AgentSessionSummary,
    AgentStreamEvent,
)
from agent_service.services.agent_state_store import AGENT_STATE_STORE
from agent_service.services.hitl_confirmations import (
    ConfirmationExpired,
    ConfirmationNotFound,
    ConfirmationOwnerMismatch,
)
from agent_service.services.runtime_dependencies import (
    get_confirmation_registry,
    get_runtime_kernel,
)
from agent_service.services.session_service import (
    create_named_session,
    delete_session,
    ensure_session,
    get_session,
    list_sessions,
    mark_session_turn,
)
from agent_service.services.session_store import SESSION_STORE
from agent_service.services.session_transcript import extract_transcript

router = APIRouter(prefix="/api/v2")


def _user_id(x_user_id: str | None) -> str:
    if not x_user_id:
        raise HTTPException(status_code=401, detail="X-User-ID header required")
    return x_user_id


def _bearer_token(authorization: str | None) -> str | None:
    """Extract the raw bearer token forwarded by the gateway (SPEC-008 R-5)."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


async def _reject_if_parked(session_id: str) -> None:
    """SPEC-020 R-2: a parked session rejects new turns until resolved.

    A TTL-expired park is closed through ``expire_confirmation``
    (``UserInterruptEvent``) before the new turn proceeds — the kernel
    cannot accept a fresh message while a reply sits parked, so silent
    eviction would wedge the session.
    """
    kernel = get_runtime_kernel()
    pending = get_confirmation_registry().peek_parked(session_id)
    if pending is None:
        return
    if pending.is_expired(kernel.settings.hitl_confirm_timeout):
        try:
            await kernel.expire_confirmation(session_id, pending.confirm_id)
        except ConfirmationNotFound:
            # A concurrent confirm or expiry claimed the entry first — the
            # session is still busy with the resumed stream, so the new
            # turn stays rejected until that stream resolves the entry.
            raise HTTPException(
                status_code=409,
                detail="confirmation pending: the parked tool confirmation "
                "is being resolved; retry shortly",
            ) from None
        return
    raise HTTPException(
        status_code=409,
        detail="confirmation pending: answer or expire the parked "
        "tool confirmation before sending a new message",
    )


# --- Chat ---


@router.post("/chat", response_model=AgentChatResponse)
async def chat(
    body: AgentChatRequest,
    x_user_id: str | None = Header(None),
    x_request_id: str | None = Header(None),
    authorization: str | None = Header(None),
) -> AgentChatResponse:
    user_id = _user_id(x_user_id)
    request_id = x_request_id or "untracked"
    record_chat_request()
    session = ensure_session(body.session_id, user_id)
    await _reject_if_parked(session.session_id)
    mark_session_turn(session.session_id, body.message)
    content, structured_output = await get_runtime_kernel().reply_text(
        message=body.message,
        session_id=session.session_id,
        user_name=user_id,
        bearer_token=_bearer_token(authorization),
        response_schema=body.response_schema,
    )
    return AgentChatResponse(
        session_id=session.session_id,
        request_id=request_id,
        content=content,
        structured_output=structured_output,
    )


@router.get("/chat/stream")
async def chat_stream(
    message: str,
    session_id: str | None = None,
    x_user_id: str | None = Header(None),
    x_request_id: str | None = Header(None),
    authorization: str | None = Header(None),
) -> StreamingResponse:
    user_id = _user_id(x_user_id)
    request_id = x_request_id or "untracked"
    record_chat_request()
    session = ensure_session(session_id, user_id)
    await _reject_if_parked(session.session_id)
    mark_session_turn(session.session_id, message)
    bearer_token = _bearer_token(authorization)

    async def _events() -> AsyncIterator[str]:
        async for chunk in get_runtime_kernel().stream_events(
            message=message,
            request_id=request_id,
            session_id=session.session_id,
            user_name=user_id,
            bearer_token=bearer_token,
        ):
            event = _normalize_stream_event(chunk, session.session_id, request_id)
            yield f"data: {event.model_dump_json(exclude_none=True)}\n\n"

    return StreamingResponse(_events(), media_type="text/event-stream")


@router.post("/chat/confirm")
async def chat_confirm(
    body: AgentChatConfirmRequest,
    x_user_id: str | None = Header(None),
    x_request_id: str | None = Header(None),
    authorization: str | None = Header(None),
) -> StreamingResponse:
    """Answer a parked kernel confirmation and stream the resumed turn.

    SPEC-020 R-2: session ownership rides the existing session lookup
    (foreign sessions 404, matching the session routes' anti-enumeration
    convention); registry errors map to 404/410. The entry is claimed
    before any headers go out, so a duplicate confirm fails closed with
    404 instead of double-resuming the parked batch.
    """
    user_id = _user_id(x_user_id)
    request_id = x_request_id or "untracked"
    session = get_session(body.session_id, user_id)
    kernel = get_runtime_kernel()
    registry = get_confirmation_registry()
    try:
        pending = registry.claim(
            session.session_id,
            body.confirm_id,
            kernel.settings.hitl_confirm_timeout,
        )
    except ConfirmationExpired:
        try:
            await kernel.expire_confirmation(
                session.session_id, body.confirm_id
            )
        except ConfirmationNotFound:
            # A concurrent request already closed the expired entry.
            pass
        raise HTTPException(
            status_code=410, detail="confirmation expired"
        ) from None
    except ConfirmationNotFound:
        raise HTTPException(
            status_code=404, detail="confirmation not found"
        ) from None

    async def _events() -> AsyncIterator[str]:
        try:
            async for chunk in kernel.resume_confirmation(
                session_id=session.session_id,
                pending=pending,
                decision=body.decision,
                user_name=user_id,
                request_id=request_id,
                bearer_token=_bearer_token(authorization),
            ):
                event = _normalize_stream_event(
                    chunk, session.session_id, request_id
                )
                yield f"data: {event.model_dump_json(exclude_none=True)}\n\n"
        except ConfirmationOwnerMismatch:
            # Mid-stream guard (registry owner and session owner diverged);
            # surface as an error frame since headers already went out.
            error_event = AgentStreamEvent(
                type="error",
                session_id=session.session_id,
                request_id=request_id,
                error={
                    "code": "confirmation_owner_mismatch",
                    "message": "only the session owner may answer this "
                    "confirmation",
                },
            )
            yield f"data: {error_event.model_dump_json(exclude_none=True)}\n\n"

    return StreamingResponse(_events(), media_type="text/event-stream")


_STREAM_EVENT_TYPES = frozenset(
    {
        "message_start",
        "message_delta",
        "message_end",
        "error",
        "tool_call",
        "tool_result",
        "confirmation_request",
        "confirmation_result",
    }
)

_TOOL_RESULT_STATUSES = frozenset(
    {"success", "error", "denied", "approved", "expired", "interrupted"}
)


def _normalize_stream_event(
    raw: dict[str, object], session_id: str, request_id: str
) -> AgentStreamEvent:
    """Translate a kernel stream chunk into a contract-conformant event.

    tool_call / tool_result frames carry the evidence-panel payload
    (SPEC-011 R-1) and must pass through untouched; anything unrecognized
    still degrades to message_delta for safety.
    """
    event_type = str(raw.get("event", raw.get("type", "message_delta")))
    if event_type not in _STREAM_EVENT_TYPES:
        event_type = "message_delta"
    return AgentStreamEvent(
        type=event_type,  # type: ignore[arg-type]
        session_id=session_id,
        request_id=request_id,
        delta=raw.get("delta") if isinstance(raw.get("delta"), str) else None,
        message=raw.get("message") if isinstance(raw.get("message"), str) else None,
        confirm_id=(
            raw.get("confirm_id")
            if isinstance(raw.get("confirm_id"), str)
            else None
        ),
        pending_calls=_coerce_pending_calls(raw.get("pending_calls")),
        tool_name=raw.get("tool_name") if isinstance(raw.get("tool_name"), str) else None,
        call_id=raw.get("call_id") if isinstance(raw.get("call_id"), str) else None,
        parameters=(
            raw.get("parameters") if isinstance(raw.get("parameters"), dict) else None
        ),
        status=(
            raw.get("status")  # type: ignore[arg-type]
            if raw.get("status") in _TOOL_RESULT_STATUSES
            else None
        ),
        evidence=raw.get("evidence") if isinstance(raw.get("evidence"), dict) else None,
        data_summary=_coerce_data_summary(raw.get("data_summary")),
        # Full tool payload (v5): already size-capped by the evidence
        # middleware, so pass it through untouched.
        data=raw.get("data"),
        error=raw.get("error") if isinstance(raw.get("error"), dict) else None,
    )


def _coerce_data_summary(value: object) -> dict[str, object] | None:
    """The contract requires an object; wrap non-object summaries safely."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    return {"value": value}


def _coerce_pending_calls(value: object) -> list[dict[str, object]] | None:
    """Keep confirmation_request batches schema-conformant (SPEC-020 R-1)."""
    if not isinstance(value, list):
        return None
    calls: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        call_id = item.get("call_id")
        tool_name = item.get("tool_name")
        parameters = item.get("parameters")
        calls.append(
            {
                "call_id": call_id if isinstance(call_id, str) else "",
                "tool_name": tool_name if isinstance(tool_name, str) else "",
                "parameters": (
                    parameters if isinstance(parameters, dict) else {}
                ),
            }
        )
    return calls or None


# --- Sessions ---


@router.post("/sessions", response_model=AgentSession, status_code=201)
async def create_session(
    body: AgentSessionCreateRequest | None = None,
    x_user_id: str | None = Header(None),
) -> AgentSession:
    user_id = _user_id(x_user_id)
    requested_id = body.session_id.strip() if body and body.session_id else ""
    if requested_id:
        # Dedicated named session (SPEC-015 R-3): idempotent for the owner.
        session = create_named_session(requested_id, user_id)
    else:
        session = ensure_session(None, user_id)
    return AgentSession(
        session_id=session.session_id,
        user_id=session.user_id or user_id,
        created_at=session.created_at,
        status=session.status,  # type: ignore[arg-type]
    )


@router.get("/sessions", response_model=AgentSessionList)
async def list_sessions_route(
    x_user_id: str | None = Header(None),
) -> AgentSessionList:
    """The caller's sessions, most-recently-active first, capped (SPEC-022 R-1)."""
    user_id = _user_id(x_user_id)
    registry = get_confirmation_registry()
    return AgentSessionList(
        sessions=[
            AgentSessionSummary(
                session_id=record.session_id,
                title=record.title,
                created_at=record.created_at,
                last_active_at=record.last_active_at,
                pending_confirmation=registry.has_pending(record.session_id),
            )
            for record in list_sessions(user_id)
        ]
    )


@router.get("/sessions/{session_id}", response_model=AgentSession)
async def read_session(
    session_id: str,
    x_user_id: str | None = Header(None),
) -> AgentSession:
    user_id = _user_id(x_user_id)
    session = get_session(session_id, user_id)
    transcript_available, transcript = extract_transcript(session.session_id)
    return AgentSession(
        session_id=session.session_id,
        user_id=session.user_id or user_id,
        created_at=session.created_at,
        status=session.status,  # type: ignore[arg-type]
        title=session.title,
        last_active_at=session.last_active_at,
        pending_confirmation=get_confirmation_registry().has_pending(
            session.session_id
        ),
        transcript_available=transcript_available,
        transcript=transcript,
    )


@router.delete("/sessions/{session_id}")
async def delete_session_route(
    session_id: str,
    x_user_id: str | None = Header(None),
) -> dict:
    """Owner-only session delete (SPEC-022 R-1).

    Foreign or unknown ids 404 per the anti-enumeration house convention;
    a session holding a parked confirmation 409s so a delete can never
    orphan an awaiting-approval workflow.
    """
    user_id = _user_id(x_user_id)
    session = get_session(session_id, user_id)
    if get_confirmation_registry().has_pending(session.session_id):
        raise HTTPException(
            status_code=409,
            detail="session has a parked confirmation: resolve it before "
            "deleting the session",
        )
    if not delete_session(session.session_id, user_id):
        raise HTTPException(status_code=404, detail="session not found")
    return {"session_id": session.session_id, "deleted": True}


# --- Runtime metadata ---


@router.get("/runtime", response_model=AgentRuntimeMetadata)
async def runtime_metadata() -> AgentRuntimeMetadata:
    kernel = get_runtime_kernel()
    meta = kernel.runtime_metadata()
    return AgentRuntimeMetadata(
        runtime_mode=str(meta.get("runtime_mode", kernel.mode())),
        runtime_state=str(meta.get("runtime_state", kernel.runtime_state())),  # type: ignore[arg-type]
        provider=str(meta.get("provider", kernel.provider_name())),
        model_name=meta.get("model_name") if isinstance(meta.get("model_name"), str) else None,
        hint=meta.get("hint") if isinstance(meta.get("hint"), str) else None,
        last_error=meta.get("last_error") if isinstance(meta.get("last_error"), str) else None,
    )


# --- Health (v2-conformant) ---


@router.get("/health", response_model=AgentHealth)
async def health() -> AgentHealth:
    kernel = get_runtime_kernel()
    configured = kernel.is_configured()
    return AgentHealth(
        status="ready" if configured else "not_ready",
        runtime_mode=kernel.mode(),
        runtime_state=kernel.runtime_state(),  # type: ignore[arg-type]
        provider=kernel.provider_name(),
        configured=configured,
        session_store=SESSION_STORE.backend_name,
        session_store_ready=SESSION_STORE.is_ready(),
        agent_state=AGENT_STATE_STORE.backend_name,
        agent_state_ready=AGENT_STATE_STORE.is_ready(),
    )
