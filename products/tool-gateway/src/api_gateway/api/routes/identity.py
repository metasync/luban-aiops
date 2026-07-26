from fastapi import APIRouter, Depends, Header, Request

from api_gateway.core.config import GatewaySettings, get_settings
from api_gateway.core.request_context import resolve_request_id
from api_gateway.services.gateway_service import normalize_identity

router = APIRouter()


@router.post("/api/v1/identity/normalize")
async def normalize_identity_route(
    request: Request,
    x_request_id: str | None = Header(default=None),
    settings: GatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    return await normalize_identity(settings, request, request_id)
