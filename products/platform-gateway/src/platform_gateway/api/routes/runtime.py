from fastapi import APIRouter, Depends

from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.services.gateway_service import runtime_status

router = APIRouter()


@router.get("/api/v1/runtime")
async def runtime_metadata(
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict[str, object]:
    return await runtime_status(settings)
