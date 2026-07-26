from fastapi import APIRouter

from agent_service.services.runtime_service import runtime_metadata

router = APIRouter()


@router.get("/api/v1/runtime")
def runtime_metadata_route() -> dict[str, object]:
    return runtime_metadata()
