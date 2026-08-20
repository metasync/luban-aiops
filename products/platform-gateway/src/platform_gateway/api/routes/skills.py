"""Workspace skills inventory proxy (SPEC-019 R-4).

Read-only skills listing for the portal. The gateway enforces ``skills:read``
at the edge, then speaks to skills-hub with its own Basic query credential —
the user's token is never forwarded for inventory reads, the same posture as
the audit and incident proxies.
"""

import logging

from fastapi import APIRouter, Depends, Header, Query, Request

from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.core.observability import log_event
from platform_gateway.core.request_context import resolve_request_id
from platform_gateway.services.gateway_service import (
    enforce_policy,
    resolve_request_identity,
)
from platform_gateway.services.policy_engine import ACTION_SKILLS_READ
from platform_gateway.services.skills_hub_client import list_skills

router = APIRouter()
LOGGER = logging.getLogger(__name__)


@router.get("/api/v1/skills")
async def list_skills_route(
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    source: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, ACTION_SKILLS_READ, request_id)
    params: dict[str, str | int] = {"offset": offset, "limit": limit}
    for key, value in (("source", source), ("tag", tag)):
        if value is not None:
            params[key] = value
    response = await list_skills(settings, request_id, params)
    log_event(
        LOGGER,
        "skills_inventory_proxied",
        request_id=request_id,
        user_id=identity.username,  # type: ignore[union-attr]
        total=response.get("total"),
    )
    return response
