"""Tool discovery and invocation routes (SPEC-007 R-4, SPEC-008 R-6).

Identity is derived exclusively from the verified bearer token; any identity
carried in a request body is never trusted (and is not part of the contract).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from tool_gateway.core.config import GatewaySettings, get_settings
from tool_gateway.core.dependencies import get_tool_registry
from tool_gateway.core.request_context import resolve_request_id
from tool_gateway.services.gateway_service import (
    enforce_policy,
    resolve_request_identity,
)
from tool_gateway.tools.registry import ToolRegistry

router = APIRouter(prefix="/api/v2/tools", tags=["tools"])


@router.get("")
async def list_tools(
    request: Request,
    x_request_id: str | None = Header(default=None),
    settings: GatewaySettings = Depends(get_settings),
    registry: ToolRegistry = Depends(get_tool_registry),
) -> list[dict]:
    """Return metadata for all registered tools (gated by ``tools:list``)."""
    request_id = getattr(request.state, "request_id", None) or resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, "tools:list", request_id)  # type: ignore[arg-type]
    return [defn.to_dict() for defn in registry.list_definitions()]


@router.post("/invoke")
async def invoke_tool(
    request: Request,
    x_request_id: str | None = Header(default=None),
    settings: GatewaySettings = Depends(get_settings),
    registry: ToolRegistry = Depends(get_tool_registry),
) -> JSONResponse:
    """Invoke a registered tool with policy enforcement and audit logging."""
    from tool_gateway.services.gateway_service import invoke_tool as service_invoke

    request_id = getattr(request.state, "request_id", None) or resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    # SPEC-070 producer wiring: when the authorization runtime is provisioned
    # (``delegated_authorization_enabled``), ``create_app`` publishes the
    # ``AuthorizationService`` on app state; a verified read-path delegated
    # re-authorization denial is then upgraded to a durable challenge. Absent it,
    # the transitional denial passes through untouched.
    producer = getattr(request.app.state, "authorization_service", None)
    return await service_invoke(
        settings, registry, request, identity, request_id,
        challenge_producer=producer,
    )


@router.post("/invoke-delegated")
async def invoke_tool_delegated(
    request: Request,
    x_request_id: str | None = Header(default=None),
    settings: GatewaySettings = Depends(get_settings),
    registry: ToolRegistry = Depends(get_tool_registry),
) -> JSONResponse:
    """SPEC-070 private delegated execution route.

    Identity is *not* resolved from a portal bearer here: the caller must present
    the exact execution-runtime workload token, and the two human bearers travel
    in the body for independent re-verification against the signed projection.
    Off by default (``GATEWAY_DELEGATED_INVOKE_ENABLED``); disabled fails closed.
    """
    from tool_gateway.services.gateway_service import (
        invoke_delegated as service_invoke_delegated,
    )

    request_id = getattr(request.state, "request_id", None) or resolve_request_id(x_request_id)
    return await service_invoke_delegated(settings, registry, request, request_id)
