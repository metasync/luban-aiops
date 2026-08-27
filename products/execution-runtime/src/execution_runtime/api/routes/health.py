from fastapi import APIRouter, Request

from execution_runtime.core.config import ExecutionSettings, get_settings
from execution_runtime.metadata import SERVICE_NAME, SERVICE_VERSION

router = APIRouter()


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "version": SERVICE_VERSION}


@router.get("/health/ready")
def ready(request: Request) -> dict[str, object]:
    settings: ExecutionSettings = get_settings()
    store = request.app.state.execution_record_store
    return {
        "status": "ok",
        "store_backend": settings.state_store_backend,
        "store_ready": store.is_ready(),
        # Secrets stay fail-closed at the handoff route, never at health:
        # readiness reports their presence without echoing their values.
        "signing_key_configured": bool(settings.execution_signing_key),
        "handoff_token_configured": bool(settings.handoff_token),
    }
