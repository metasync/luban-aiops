"""Per-source sync status (SPEC-014 R-2).

Auth-exempt operational surface, like /health: reports the last sync outcome
per source (timestamp, ref, accepted count, bounded rejection list) plus the
store backend.
"""

from fastapi import APIRouter, Depends, Request

from skills_hub.core.config import SkillsSettings, get_settings
from skills_hub.services.sync import SyncManager

router = APIRouter(prefix="/api/v1")


def _sync_manager(request: Request) -> SyncManager:
    return request.app.state.sync_manager


@router.get("/skills/status")
def skills_status(
    request: Request, settings: SkillsSettings = Depends(get_settings)
) -> dict[str, object]:
    manager = _sync_manager(request)
    return {
        "store_backend": settings.store_backend,
        "sync_interval_seconds": settings.sync_interval_seconds,
        "sources": manager.status_report(),
    }
