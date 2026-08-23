import logging

from fastapi import APIRouter, Depends, Header, Request

from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.core.observability import log_event
from platform_gateway.core.request_context import resolve_request_id
from platform_gateway.services.gateway_service import (
    enforce_policy,
    list_models,
    resolve_request_identity,
)
from platform_gateway.services.policy_engine import ACTION_MODELS_LIST

router = APIRouter()
LOGGER = logging.getLogger(__name__)


@router.get("/api/v1/models")
async def list_models_route(
    request: Request,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    """Model catalog discovery pass-through (SPEC-024 R-2).

    Proxies agent-service GET /api/v2/models behind the ``models:list``
    policy action; the upstream payload is discovery-safe by construction
    (no credentials, no base URLs).
    """
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, ACTION_MODELS_LIST, request_id)
    user_id = identity.username  # type: ignore[union-attr]
    response = await list_models(settings, request_id, user_id)
    log_event(
        LOGGER,
        "models_listed",
        request_id=request_id,
        model_count=len(response.get("models", [])),
        user_id=user_id,
        authenticated=identity.subject != "dev",  # type: ignore[union-attr]
        roles=identity.roles,  # type: ignore[union-attr]
    )
    return response
