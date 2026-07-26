from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse

from api_gateway.core.config import GatewaySettings, get_settings
from api_gateway.core.request_context import resolve_request_id, resolve_user_id
from api_gateway.services.gateway_service import chat, chat_stream

router = APIRouter()


@router.post("/api/v1/chat")
async def chat_route(
    request: Request,
    x_request_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    settings: GatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    payload = await request.json()
    user_id = resolve_user_id(settings.default_user_id, payload.get("user_id"), x_user_id)
    return await chat(settings, request_id, user_id, payload)


@router.get("/api/v1/chat/stream")
async def chat_stream_route(
    message: str,
    session_id: str | None = None,
    user_id: str | None = None,
    x_request_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    settings: GatewaySettings = Depends(get_settings),
) -> StreamingResponse:
    request_id = resolve_request_id(x_request_id)
    resolved_user_id = resolve_user_id(settings.default_user_id, user_id, x_user_id)
    return chat_stream(
        settings=settings,
        request_id=request_id,
        user_id=resolved_user_id,
        message=message,
        session_id=session_id,
    )
