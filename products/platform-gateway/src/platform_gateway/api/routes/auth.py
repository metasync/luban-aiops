import logging

from fastapi import APIRouter, Depends, Header, Request

from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.core.observability import log_event
from platform_gateway.core.request_context import resolve_request_id
from platform_gateway.services.gateway_service import (
    build_logout_url,
    complete_login,
    fetch_login_url,
    refresh_token,
    start_login,
)
from platform_gateway.services.token_verifier import TokenVerificationError, verify_token

router = APIRouter()
LOGGER = logging.getLogger(__name__)


@router.get("/api/v1/auth/login-url")
async def login_url(
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    payload = await fetch_login_url(settings, request_id)
    log_event(LOGGER, "auth_login_url_requested", request_id=request_id)
    return payload


@router.get("/api/v1/auth/login")
async def login_start(
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    payload = await start_login(settings, request_id)
    log_event(LOGGER, "auth_login_started", request_id=request_id)
    return payload


@router.post("/api/v1/auth/callback")
async def login_callback(
    request: Request,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    payload = await complete_login(settings, request_id, await request.json())
    log_event(
        LOGGER,
        "auth_login_completed",
        request_id=request_id,
        user_id=payload["identity"]["username"],
    )
    return payload


@router.get("/api/v1/auth/me")
async def auth_me(
    authorization: str | None = Header(default=None),
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    if authorization is None:
        return {"authenticated": False}
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return {"authenticated": False}
    try:
        identity = verify_token(settings, token)
    except TokenVerificationError:
        return {"authenticated": False}
    log_event(
        LOGGER,
        "auth_identity_resolved",
        request_id=request_id,
        user_id=identity.username,
    )
    return {"authenticated": True, "identity": identity.model_dump(exclude_none=True)}


@router.post("/api/v1/auth/logout-url")
async def logout_url(
    request: Request,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    payload = await build_logout_url(settings, request_id, await request.json())
    log_event(LOGGER, "auth_logout_requested", request_id=request_id)
    return payload


@router.post("/api/v1/auth/refresh")
async def auth_refresh(
    request: Request,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    payload = await refresh_token(settings, request_id, await request.json())
    log_event(
        LOGGER,
        "auth_token_refreshed",
        request_id=request_id,
        user_id=payload.get("identity", {}).get("username"),
    )
    return payload
