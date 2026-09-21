"""Workspace tools catalog proxy (SPEC-019 R-4).

Read-only tool discovery for the portal. The gateway enforces ``tools:list``
at the edge, then forwards a broker-mediated delegated token (audience
``tool-gateway``) to tool-gateway's discovery endpoint — the downstream
re-enforces ``tools:list`` under real operator authority, unchanged.
"""

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.core.observability import log_event
from platform_gateway.core.request_context import resolve_request_id
from platform_gateway.services.delegation_client import obtain_delegated_token
from platform_gateway.services.gateway_service import (
    enforce_policy,
    resolve_request_identity,
)
from platform_gateway.services.policy_engine import ACTION_TOOLS_LIST
from platform_gateway.services.tool_gateway_client import list_tools, redeem_secret

router = APIRouter()
LOGGER = logging.getLogger(__name__)


def _bearer_token(request: Request) -> str | None:
    """Return the raw bearer token from the request, if present."""
    authorization = request.headers.get("authorization")
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


@router.get("/api/v1/secrets/delivery/{delivery_id}")
async def redeem_secret_route(
    delivery_id: str, request: Request,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
):
    from dataclasses import replace
    from fastapi.responses import JSONResponse

    headers = {"Cache-Control": "no-store", "Pragma": "no-cache"}
    request_id = resolve_request_id(x_request_id)
    try:
        identity = await resolve_request_identity(replace(settings, require_auth=True), request, request_id)
        token = await obtain_delegated_token(settings, identity.subject, _bearer_token(request))
        if not token:
            raise HTTPException(status_code=503, detail="Secret delivery unavailable")
        value = await redeem_secret(settings, request_id, token, delivery_id)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": "Secret delivery unavailable"}, headers=headers)
    return JSONResponse(content={"value": value}, headers=headers)


@router.get("/api/v1/tools")
async def list_tools_route(
    request: Request,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> list:
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, ACTION_TOOLS_LIST, request_id)
    delegated_token = await obtain_delegated_token(
        settings,
        identity.subject,  # type: ignore[union-attr]
        _bearer_token(request),
    )
    if not delegated_token:
        # Discovery runs under real operator authority (SPEC-019 R-4): like
        # triage, there is no useful tool-less fallback, so fail fast.
        raise HTTPException(
            status_code=503,
            detail="delegated token unavailable; tool catalog requires the delegation chain",
        )
    tools = await list_tools(settings, request_id, delegated_token)
    log_event(
        LOGGER,
        "tools_catalog_proxied",
        request_id=request_id,
        user_id=identity.username,  # type: ignore[union-attr]
        tool_count=len(tools) if isinstance(tools, list) else None,
    )
    return tools
