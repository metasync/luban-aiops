from fastapi import APIRouter, Depends, Header, Query, Request

from api_gateway.core.config import GatewaySettings, get_settings
from api_gateway.core.request_context import resolve_request_id, resolve_user_id
from api_gateway.services.gateway_service import create_session, get_session

router = APIRouter()


@router.post("/api/v1/sessions")
async def create_session_route(
    request: Request,
    x_request_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    settings: GatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    payload = await request.json()
    user_id = resolve_user_id(settings.default_user_id, payload.get("user_id"), x_user_id)
    return await create_session(settings, request_id, user_id, payload)


@router.get("/api/v1/sessions/{session_id}")
async def get_session_route(
    session_id: str,
    user_id: str | None = Query(default=None),
    x_request_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    settings: GatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    resolved_user_id = resolve_user_id(settings.default_user_id, user_id, x_user_id)
    return await get_session(settings, request_id, session_id, resolved_user_id)
