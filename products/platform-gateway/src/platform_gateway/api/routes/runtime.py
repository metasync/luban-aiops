import logging

from fastapi import APIRouter, Depends, Header, Request

from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.core.observability import log_event
from platform_gateway.core.request_context import resolve_request_id
from platform_gateway.services.gateway_service import (
    enforce_policy,
    feature_flags,
    resolve_request_identity,
    runtime_status,
)
from platform_gateway.services.policy_engine import ACTION_RUNTIME_FLAGS

router = APIRouter()
LOGGER = logging.getLogger(__name__)


@router.get("/api/v1/runtime")
async def runtime_metadata(
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict[str, object]:
    return await runtime_status(settings)


@router.get("/api/v1/runtime/flags")
async def runtime_flags_route(
    request: Request,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    """Feature-flag inventory pass-through (SPEC-072 R-5).

    Proxies agent-service ``GET /api/v2/runtime/flags`` behind the
    ``runtime:flags`` policy action (the operational trio). The base
    ``/api/v1/runtime`` probe above stays unauthenticated and flag-free; the
    upstream payload is discovery-safe by construction (names + booleans,
    never a secret value).
    """
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, ACTION_RUNTIME_FLAGS, request_id)
    user_id = identity.username  # type: ignore[union-attr]
    response = await feature_flags(settings, request_id, user_id)
    log_event(
        LOGGER,
        "runtime_flags_listed",
        request_id=request_id,
        flag_count=len(response.get("feature_flags", [])),
        user_id=user_id,
        authenticated=identity.subject != "dev",  # type: ignore[union-attr]
        roles=identity.roles,  # type: ignore[union-attr]
    )
    return response
