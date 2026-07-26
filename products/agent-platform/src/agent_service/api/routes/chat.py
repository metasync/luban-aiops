from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse

from agent_service.core.request_context import resolve_request_id
from agent_service.schemas.api import ChatRequest, ChatResponse
from agent_service.services.runtime_service import chat, stream_chat

router = APIRouter()


@router.post("/api/v1/chat", response_model=ChatResponse)
async def chat_route(
    payload: ChatRequest,
    x_request_id: str | None = Header(default=None),
) -> ChatResponse:
    request_id = resolve_request_id(x_request_id)
    return await chat(
        message=payload.message,
        session_id=payload.session_id,
        user_id=payload.user_id,
        request_id=request_id,
    )


@router.get("/api/v1/chat/stream")
async def chat_stream_route(
    message: str,
    session_id: str | None = None,
    user_id: str | None = None,
    x_request_id: str | None = Header(default=None),
) -> StreamingResponse:
    request_id = resolve_request_id(x_request_id)
    return StreamingResponse(
        stream_chat(
            message=message,
            session_id=session_id,
            user_id=user_id,
            request_id=request_id,
        ),
        media_type="text/event-stream",
    )
