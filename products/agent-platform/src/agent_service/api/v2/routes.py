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
    AgentChatRequest,
    AgentChatResponse,
    AgentHealth,
    AgentRuntimeMetadata,
    AgentSession,
    AgentStreamEvent,
)
from agent_service.services.runtime_dependencies import get_runtime_kernel
from agent_service.services.session_service import ensure_session, get_session
from agent_service.services.session_store import SESSION_STORE

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
    content = await get_runtime_kernel().reply_text(
        message=body.message,
        session_id=session.session_id,
        user_name=user_id,
        bearer_token=_bearer_token(authorization),
    )
    return AgentChatResponse(
        session_id=session.session_id,
        request_id=request_id,
        content=content,
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


def _normalize_stream_event(
    raw: dict[str, object], session_id: str, request_id: str
) -> AgentStreamEvent:
    """Translate a kernel stream chunk into a contract-conformant event."""
    event_type = str(raw.get("event", raw.get("type", "message_delta")))
    # Map any unrecognized types to message_delta for safety.
    if event_type not in ("message_start", "message_delta", "message_end", "error"):
        event_type = "message_delta"
    return AgentStreamEvent(
        type=event_type,  # type: ignore[arg-type]
        session_id=session_id,
        request_id=request_id,
        delta=raw.get("delta") if isinstance(raw.get("delta"), str) else None,
        message=raw.get("message") if isinstance(raw.get("message"), str) else None,
    )


# --- Sessions ---


@router.post("/sessions", response_model=AgentSession, status_code=201)
async def create_session(
    x_user_id: str | None = Header(None),
) -> AgentSession:
    user_id = _user_id(x_user_id)
    session = ensure_session(None, user_id)
    return AgentSession(
        session_id=session.session_id,
        user_id=session.user_id or user_id,
        created_at=session.created_at,
        status=session.status,  # type: ignore[arg-type]
    )


@router.get("/sessions/{session_id}", response_model=AgentSession)
async def read_session(
    session_id: str,
    x_user_id: str | None = Header(None),
) -> AgentSession:
    user_id = _user_id(x_user_id)
    session = get_session(session_id, user_id)
    return AgentSession(
        session_id=session.session_id,
        user_id=session.user_id or user_id,
        created_at=session.created_at,
        status=session.status,  # type: ignore[arg-type]
    )


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
    )
