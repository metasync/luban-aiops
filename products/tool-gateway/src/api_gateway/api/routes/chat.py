import logging

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse

from api_gateway.core.config import GatewaySettings, get_settings
from api_gateway.core.observability import log_event
from api_gateway.core.request_context import resolve_request_id
from api_gateway.schemas.api import ChatRequest
from api_gateway.services.gateway_service import (
    chat,
    chat_stream,
    enforce_policy,
    resolve_request_identity,
)

router = APIRouter()
LOGGER = logging.getLogger(__name__)


@router.post("/api/v1/chat")
async def chat_route(
    request: Request,
    body: ChatRequest,
    x_request_id: str | None = Header(default=None),
    settings: GatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, "chat", request_id)
    user_id = identity.username  # type: ignore[union-attr]
    response = await chat(
        settings,
        request_id,
        user_id,
        body.message,
        body.session_id,
    )
    log_event(
        LOGGER,
        "chat_completed",
        request_id=request_id,
        session_id=response.get("session_id"),
        user_id=user_id,
        authenticated=identity.subject != "dev",  # type: ignore[union-attr]
        roles=identity.roles,  # type: ignore[union-attr]
    )
    return response


@router.get("/api/v1/chat/stream")
async def chat_stream_route(
    request: Request,
    message: str,
    session_id: str | None = None,
    x_request_id: str | None = Header(default=None),
    settings: GatewaySettings = Depends(get_settings),
) -> StreamingResponse:
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, "chat", request_id)
    user_id = identity.username  # type: ignore[union-attr]
    log_event(
        LOGGER,
        "chat_stream_started",
        request_id=request_id,
        session_id=session_id,
        user_id=user_id,
        authenticated=identity.subject != "dev",  # type: ignore[union-attr]
        roles=identity.roles,  # type: ignore[union-attr]
    )
    return chat_stream(
        settings=settings,
        request_id=request_id,
        user_id=user_id,
        message=message,
        session_id=session_id,
    )
