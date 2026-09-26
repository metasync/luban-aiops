from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from execution_runtime.core.config import ExecutionSettings, get_settings
from execution_runtime.metadata import SERVICE_NAME, SERVICE_VERSION

router = APIRouter()


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "version": SERVICE_VERSION}


@router.get("/health/ready")
def ready(request: Request):
    settings: ExecutionSettings = get_settings()
    health = request.app.state.ledger.health()
    configured = bool(settings.execution_signing_key and settings.handoff_token
                      and settings.tool_gateway_url and settings.admission_epoch)
    ready = health["admission_enabled"] and configured and not request.app.state.draining
    return JSONResponse(status_code=200 if ready else 503, content={
        "status": "ok" if ready else "unavailable",
        "configured_backend": settings.state_store_backend,
        **health,
        "protocol_ready": ready,
        "draining": request.app.state.draining,
        "signing_key_configured": bool(settings.execution_signing_key),
        "handoff_token_configured": bool(settings.handoff_token),
        "gateway_configured": bool(settings.tool_gateway_url),
    })
