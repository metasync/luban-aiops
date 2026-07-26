from fastapi import APIRouter, Depends, Header

from api_gateway.core.config import GatewaySettings, get_settings
from api_gateway.core.request_context import resolve_request_id
from api_gateway.services.gateway_service import fetch_login_url

router = APIRouter()


@router.get("/api/v1/auth/login-url")
async def login_url(
    x_request_id: str | None = Header(default=None),
    settings: GatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    return await fetch_login_url(settings, request_id)
