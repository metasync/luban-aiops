from fastapi import APIRouter, Depends, Request

from skills_hub.core.config import SkillsSettings, get_settings
from skills_hub.metadata import SERVICE_NAME, SERVICE_VERSION
from skills_hub.services.skill_store import SkillStore

router = APIRouter()


def _store(request: Request) -> SkillStore:
    return request.app.state.skills_store


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "version": SERVICE_VERSION}


@router.get("/health/ready")
async def ready(
    request: Request, settings: SkillsSettings = Depends(get_settings)
) -> dict[str, object]:
    store = _store(request)
    store_ready = await store.ready()
    body: dict[str, object] = {
        "status": "ok" if store_ready else "degraded",
        "service": SERVICE_NAME,
        "store_backend": settings.store_backend,
        "store_ready": store_ready,
        "source_count": len(settings.sources),
    }
    if store_ready:
        body["skill_count"] = await store.count()
    return body
