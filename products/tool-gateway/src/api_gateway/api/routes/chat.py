import logging

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse

from api_gateway.core.config import GatewaySettings, get_settings
from api_gateway.core.observability import log_event
from api_gateway.core.request_context import resolve_request_id, resolve_user_id
from api_gateway.services.gateway_service import (
    chat,
    chat_stream,
    resolve_authenticated_identity,
)

router = APIRouter()
LOGGER = logging.getLogger(__name__)


@router.post("/api/v1/chat")
async def chat_route(
    request: Request,
    x_request_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    settings: GatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    payload = await request.json()
    identity = await resolve_authenticated_identity(settings, request, request_id)
    user_id = resolve_user_id(
        settings.default_user_id,
        payload.get("user_id"),
        x_user_id,
        identity["username"] if identity else None,
    )
    response = await chat(settings, request_id, user_id, payload)
    log_event(
        LOGGER,
        "chat_completed",
        request_id=request_id,
        session_id=response.get("session_id"),
        user_id=user_id,
        authenticated=identity is not None,
    )
    return response


@router.get("/api/v1/chat/stream")
async def chat_stream_route(
    request: Request,
    message: str,
    session_id: str | None = None,
    user_id: str | None = None,
    x_request_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    settings: GatewaySettings = Depends(get_settings),
) -> StreamingResponse:
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_authenticated_identity(settings, request, request_id)
    resolved_user_id = resolve_user_id(
        settings.default_user_id,
        user_id,
        x_user_id,
        identity["username"] if identity else None,
    )
    log_event(
        LOGGER,
        "chat_stream_started",
        request_id=request_id,
        session_id=session_id,
        user_id=resolved_user_id,
        authenticated=identity is not None,
    )
    return chat_stream(
        settings=settings,
        request_id=request_id,
        user_id=resolved_user_id,
        message=message,
        session_id=session_id,
    )
