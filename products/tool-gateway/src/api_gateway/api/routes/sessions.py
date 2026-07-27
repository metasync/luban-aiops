import logging

from fastapi import APIRouter, Depends, Header, Query, Request

from api_gateway.core.config import GatewaySettings, get_settings
from api_gateway.core.observability import log_event
from api_gateway.core.request_context import resolve_request_id, resolve_user_id
from api_gateway.services.gateway_service import (
    create_session,
    get_session,
    resolve_authenticated_identity,
)

router = APIRouter()
LOGGER = logging.getLogger(__name__)


@router.post("/api/v1/sessions")
async def create_session_route(
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
    response = await create_session(settings, request_id, user_id, payload)
    log_event(
        LOGGER,
        "session_created",
        request_id=request_id,
        session_id=response.get("session_id"),
        user_id=user_id,
        authenticated=identity is not None,
    )
    return response


@router.get("/api/v1/sessions/{session_id}")
async def get_session_route(
    request: Request,
    session_id: str,
    user_id: str | None = Query(default=None),
    x_request_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    settings: GatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_authenticated_identity(settings, request, request_id)
    resolved_user_id = resolve_user_id(
        settings.default_user_id,
        user_id,
        x_user_id,
        identity["username"] if identity else None,
    )
    response = await get_session(settings, request_id, session_id, resolved_user_id)
    log_event(
        LOGGER,
        "session_retrieved",
        request_id=request_id,
        session_id=session_id,
        user_id=resolved_user_id,
        authenticated=identity is not None,
    )
    return response
