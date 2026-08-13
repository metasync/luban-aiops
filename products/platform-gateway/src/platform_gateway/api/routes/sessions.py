import logging

from fastapi import APIRouter, Depends, Header, Request

from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.core.observability import log_event
from platform_gateway.core.request_context import resolve_request_id
from platform_gateway.schemas.api import CreateSessionRequest
from platform_gateway.services.audit_emitter import build_audit_event, emit_audit_event
from platform_gateway.services.gateway_service import (
    create_session,
    enforce_policy,
    get_session,
    resolve_request_identity,
)

router = APIRouter()
LOGGER = logging.getLogger(__name__)


@router.post("/api/v1/sessions")
async def create_session_route(
    request: Request,
    body: CreateSessionRequest,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, "session:create", request_id)
    user_id = identity.username  # type: ignore[union-attr]
    response = await create_session(
        settings,
        request_id,
        user_id,
    )
    log_event(
        LOGGER,
        "session_created",
        request_id=request_id,
        session_id=response.get("session_id"),
        user_id=user_id,
        authenticated=identity.subject != "dev",  # type: ignore[union-attr]
        roles=identity.roles,  # type: ignore[union-attr]
    )
    emit_audit_event(
        settings,
        build_audit_event(
            "session_created",
            request_id,
            "success",
            subject=identity.subject,  # type: ignore[union-attr]
            username=user_id,
            actor=identity.actor,  # type: ignore[union-attr]
            roles=identity.roles,  # type: ignore[union-attr]
            session_id=response.get("session_id"),
        ),
    )
    return response


@router.get("/api/v1/sessions/{session_id}")
async def get_session_route(
    request: Request,
    session_id: str,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, "session:read", request_id)
    user_id = identity.username  # type: ignore[union-attr]
    response = await get_session(settings, request_id, session_id, user_id)
    log_event(
        LOGGER,
        "session_retrieved",
        request_id=request_id,
        session_id=session_id,
        user_id=user_id,
        authenticated=identity.subject != "dev",  # type: ignore[union-attr]
        roles=identity.roles,  # type: ignore[union-attr]
    )
    return response
