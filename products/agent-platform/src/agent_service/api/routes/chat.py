import logging

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse

from agent_service.core.observability import log_event
from agent_service.core.request_context import resolve_request_id
from agent_service.schemas.api import ChatRequest, ChatResponse
from agent_service.services.runtime_service import chat, stream_chat

router = APIRouter()
LOGGER = logging.getLogger(__name__)


@router.post("/api/v1/chat", response_model=ChatResponse)
async def chat_route(
    payload: ChatRequest,
    x_request_id: str | None = Header(default=None),
) -> ChatResponse:
    request_id = resolve_request_id(x_request_id)
    response = await chat(
        message=payload.message,
        session_id=payload.session_id,
        user_id=payload.user_id,
        request_id=request_id,
    )
    log_event(
        LOGGER,
        "chat_completed",
        request_id=request_id,
        session_id=response.session_id,
        user_id=payload.user_id or "user",
    )
    return response


@router.get("/api/v1/chat/stream")
async def chat_stream_route(
    message: str,
    session_id: str | None = None,
    user_id: str | None = None,
    x_request_id: str | None = Header(default=None),
) -> StreamingResponse:
    request_id = resolve_request_id(x_request_id)
    log_event(
        LOGGER,
        "chat_stream_started",
        request_id=request_id,
        session_id=session_id,
        user_id=user_id or "user",
    )
    return StreamingResponse(
        stream_chat(
            message=message,
            session_id=session_id,
            user_id=user_id,
            request_id=request_id,
        ),
        media_type="text/event-stream",
    )
