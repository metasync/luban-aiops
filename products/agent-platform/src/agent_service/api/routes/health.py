from fastapi import APIRouter

from agent_service.services.runtime_service import live_status, ready_status

router = APIRouter()


@router.get("/health/live")
def live() -> dict[str, str | bool]:
    return live_status()


@router.get("/health/ready")
def ready() -> dict[str, str | bool | None]:
    return ready_status()
