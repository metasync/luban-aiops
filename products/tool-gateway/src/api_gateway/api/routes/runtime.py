from fastapi import APIRouter, Depends

from api_gateway.core.config import GatewaySettings, get_settings
from api_gateway.services.gateway_service import runtime_status

router = APIRouter()


@router.get("/api/v1/runtime")
async def runtime_metadata(
    settings: GatewaySettings = Depends(get_settings),
) -> dict[str, object]:
    return await runtime_status(settings)
