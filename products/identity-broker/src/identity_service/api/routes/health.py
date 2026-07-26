from fastapi import APIRouter

from identity_service.services.identity_service import health_status

router = APIRouter()


@router.get("/health/live")
def live() -> dict[str, str]:
    return health_status()


@router.get("/health/ready")
def ready() -> dict[str, str]:
    return health_status()
