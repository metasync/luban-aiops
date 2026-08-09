import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request

from identity_service.api.router import router
from identity_service.core.metrics import setup_metrics
from identity_service.core.observability import configure_logging, log_event
from identity_service.core.telemetry import current_trace_id, setup_telemetry
from identity_service.metadata import SERVICE_NAME, SERVICE_TITLE, SERVICE_VERSION

LOGGER = logging.getLogger(__name__)


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title=SERVICE_TITLE, version=SERVICE_VERSION)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = (
            request.headers.get("x-request-id")
            or current_trace_id()
            or f"req-{uuid4()}"
        )
        started_at = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        log_event(
            LOGGER,
            "http_request",
            service="identity-service",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response

    app.include_router(router)
    setup_metrics(app)
    setup_telemetry(app, SERVICE_NAME)
    return app


app = create_app()
