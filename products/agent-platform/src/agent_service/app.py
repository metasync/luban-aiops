import logging
import time

from fastapi import FastAPI, Request

from agent_service.api.v2.routes import router as v2_router
from agent_service.core.metrics import setup_metrics
from agent_service.core.observability import configure_logging, log_event
from agent_service.core.request_context import resolve_request_id
from agent_service.core.telemetry import setup_telemetry
from agent_service.metadata import SERVICE_NAME, SERVICE_TITLE, SERVICE_VERSION

LOGGER = logging.getLogger(__name__)


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title=SERVICE_TITLE, version=SERVICE_VERSION)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = resolve_request_id(request.headers.get("x-request-id"))
        started_at = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        log_event(
            LOGGER,
            "http_request",
            service="agent-service",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response

    app.include_router(v2_router)
    setup_metrics(app)
    setup_telemetry(app, SERVICE_NAME)
    return app


app = create_app()
