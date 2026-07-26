from fastapi import APIRouter, Depends

from api_gateway.core.config import GatewaySettings, get_settings
from api_gateway.services.gateway_service import live_status, ready_status

router = APIRouter()


@router.get("/health/live")
def live(settings: GatewaySettings = Depends(get_settings)) -> dict[str, str]:
    return live_status(settings)


@router.get("/health/ready")
async def ready(settings: GatewaySettings = Depends(get_settings)) -> dict[str, object]:
    return await ready_status(settings)
