from fastapi import APIRouter, Depends, Request

from audit_service.core.config import AuditSettings, get_settings
from audit_service.metadata import SERVICE_NAME, SERVICE_VERSION
from audit_service.services.audit_store import AuditStore

router = APIRouter()


def _store(request: Request) -> AuditStore:
    return request.app.state.audit_store


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "version": SERVICE_VERSION}


@router.get("/health/ready")
async def ready(
    request: Request, settings: AuditSettings = Depends(get_settings)
) -> dict[str, object]:
    store = _store(request)
    store_ready = await store.ready()
    body: dict[str, object] = {
        "status": "ok" if store_ready else "degraded",
        "service": SERVICE_NAME,
        "store_backend": settings.store_backend,
        "store_ready": store_ready,
        "retention_days": settings.retention_days,
        "max_events": settings.max_events,
    }
    if store_ready:
        body["event_count"] = await store.count()
    return body
