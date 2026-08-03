from fastapi import APIRouter, Depends, Header, Request

from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.core.request_context import resolve_request_id
from platform_gateway.services.gateway_service import normalize_identity

router = APIRouter()


@router.post("/api/v1/identity/normalize")
async def normalize_identity_route(
    request: Request,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    return await normalize_identity(settings, request, request_id)
