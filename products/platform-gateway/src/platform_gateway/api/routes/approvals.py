import logging

from fastapi import APIRouter, Depends, Header, Request

from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.core.observability import log_event
from platform_gateway.core.request_context import resolve_request_id
from platform_gateway.services.gateway_service import (
    approvals_inbox,
    enforce_policy,
    resolve_request_identity,
)
from platform_gateway.services.policy_engine import ACTION_APPROVALS_LIST

router = APIRouter()
LOGGER = logging.getLogger(__name__)


@router.get("/api/v1/approvals/inbox")
async def approvals_inbox_route(
    request: Request,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    """The designated approver's confirmation inbox (SPEC-031 R-3).

    Cross-session discovery of parked and historical confirmations,
    metadata only (no owner transcript text — SPEC-030 Q-1 posture).
    The `approvals:list` action is granted to the tier_2 decider roles
    by the bundle; everyone else gets the standard audited policy 403.
    """
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, ACTION_APPROVALS_LIST, request_id)
    user_id = identity.username  # type: ignore[union-attr]
    response = await approvals_inbox(settings, request_id, user_id)
    items = response.get("confirmations", [])
    log_event(
        LOGGER,
        "approvals_inbox_listed",
        request_id=request_id,
        item_count=len(items),
        pending_count=sum(
            1 for item in items if item.get("status") == "pending"
        ),
        user_id=user_id,
        authenticated=identity.subject != "dev",  # type: ignore[union-attr]
        roles=identity.roles,  # type: ignore[union-attr]
    )
    return response
