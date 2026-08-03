from fastapi import APIRouter, Depends

from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.services.gateway_service import live_status, ready_status

router = APIRouter()


@router.get("/health/live")
def live(settings: PlatformGatewaySettings = Depends(get_settings)) -> dict[str, str]:
    return live_status(settings)


@router.get("/health/ready")
async def ready(settings: PlatformGatewaySettings = Depends(get_settings)) -> dict[str, object]:
    return await ready_status(settings)
