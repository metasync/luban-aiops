import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from audit_service.api.router import router
from audit_service.core.config import get_settings
from audit_service.core.metrics import setup_metrics
from audit_service.core.observability import configure_logging, log_event
from audit_service.core.request_context import resolve_request_id
from audit_service.core.telemetry import setup_telemetry
from audit_service.metadata import SERVICE_NAME, SERVICE_TITLE, SERVICE_VERSION
from audit_service.services.audit_store import build_audit_store
from audit_service.services.retention import RetentionTask

LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    store = build_audit_store(settings)
    await store.initialize()
    app.state.audit_store = store
    retention = RetentionTask(store, settings)
    await retention.start()
    LOGGER.info(
        "audit store ready",
        extra={
            "backend": settings.store_backend,
            "retention_days": settings.retention_days,
            "max_events": settings.max_events,
        },
    )
    try:
        yield
    finally:
        await retention.stop()
        await store.close()


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title=SERVICE_TITLE, version=SERVICE_VERSION, lifespan=lifespan
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = resolve_request_id(request.headers.get("x-request-id"))
        started_at = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        log_event(
            LOGGER,
            "http_request",
            service="audit-service",
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
