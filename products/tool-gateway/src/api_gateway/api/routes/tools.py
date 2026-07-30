"""Tool discovery and invocation routes (SPEC-007 R-4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from api_gateway.core.config import GatewaySettings, get_settings
from api_gateway.core.request_context import resolve_request_id
from api_gateway.schemas.api import IdentityContext
from api_gateway.services.gateway_service import (
    enforce_policy,
    resolve_request_identity,
)
from api_gateway.tools.registry import ToolRegistry

router = APIRouter(prefix="/api/v2/tools", tags=["tools"])

# Module-level registry, populated at startup via init_tool_registry().
_registry: ToolRegistry | None = None


def init_tool_registry(registry: ToolRegistry) -> None:
    """Set the module-level registry (called during app startup)."""
    global _registry
    _registry = registry


def get_tool_registry() -> ToolRegistry:
    """FastAPI dependency returning the active tool registry."""
    if _registry is None:
        return ToolRegistry()  # empty fallback
    return _registry


@router.get("")
async def list_tools(
    registry: ToolRegistry = Depends(get_tool_registry),
) -> list[dict]:
    """Return metadata for all registered tools."""
    return [defn.to_dict() for defn in registry.list_definitions()]


@router.post("/invoke")
async def invoke_tool(
    request: Request,
    x_request_id: str | None = Header(default=None),
    settings: GatewaySettings = Depends(get_settings),
    registry: ToolRegistry = Depends(get_tool_registry),
) -> JSONResponse:
    """Invoke a registered tool with policy enforcement and audit logging."""
    from api_gateway.services.gateway_service import invoke_tool as service_invoke

    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    return await service_invoke(settings, registry, request, identity, request_id)
