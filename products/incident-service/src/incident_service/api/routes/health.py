from fastapi import APIRouter, Depends, Request

from incident_service.core.config import IncidentSettings, get_settings
from incident_service.metadata import SERVICE_NAME, SERVICE_VERSION
from incident_service.services.incident_store import IncidentStore

router = APIRouter()


def _store(request: Request) -> IncidentStore:
    return request.app.state.incident_store


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "version": SERVICE_VERSION}


@router.get("/health/ready")
async def ready(
    request: Request, settings: IncidentSettings = Depends(get_settings)
) -> dict[str, object]:
    store = _store(request)
    store_ready = await store.ready()
    body: dict[str, object] = {
        "status": "ok" if store_ready else "degraded",
        "service": SERVICE_NAME,
        "store_backend": settings.store_backend,
        "store_ready": store_ready,
        "connectors": list(settings.connectors),
    }
    if store_ready:
        body["incident_count"] = await store.count()
    return body
