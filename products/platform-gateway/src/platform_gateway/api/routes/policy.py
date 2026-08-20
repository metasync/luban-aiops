"""Policy transparency route (SPEC-019 R-2).

Serves the live role x action permission matrix derived from the policy
bundle this gateway actually enforces. The endpoint is gated by the
``policy:read`` action and rows are scoped server-side: platform-admin
sees the full matrix, every other identity only its own granted roles.
"""

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.core.observability import log_event
from platform_gateway.core.request_context import resolve_request_id
from platform_gateway.services.gateway_service import (
    enforce_policy,
    resolve_request_identity,
)
from platform_gateway.services.policy_engine import (
    ACTION_POLICY_READ,
    PolicyLoadError,
)
from platform_gateway.services.policy_matrix import build_policy_matrix

router = APIRouter()
LOGGER = logging.getLogger(__name__)


@router.get("/api/v1/policy/matrix")
async def policy_matrix_route(
    request: Request,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    try:
        # enforce_policy loads the bundle itself, so a degraded bundle must be
        # mapped here — the matrix-build guard below covers the same failure.
        enforce_policy(settings, identity, ACTION_POLICY_READ, request_id)
        payload = build_policy_matrix(settings, identity)
    except PolicyLoadError as exc:
        raise HTTPException(
            status_code=503, detail="policy bundle unavailable"
        ) from exc
    log_event(
        LOGGER,
        "policy_matrix_served",
        request_id=request_id,
        user_id=identity.username,  # type: ignore[union-attr]
        scope=payload["scope"],
    )
    return payload
