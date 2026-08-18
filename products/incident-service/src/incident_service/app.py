import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from incident_service.api.router import router
from incident_service.core.config import get_settings
from incident_service.core.metrics import setup_metrics
from incident_service.core.observability import configure_logging, log_event
from incident_service.core.request_context import resolve_request_id
from incident_service.core.telemetry import setup_telemetry
from incident_service.metadata import SERVICE_NAME, SERVICE_TITLE, SERVICE_VERSION
from incident_service.services.connectors import build_connectors
from incident_service.services.incident_store import build_incident_store

LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # Unknown connector names fail startup fast (SPEC-015 R-5).
    connectors = build_connectors(settings)
    store = build_incident_store(settings)
    await store.initialize()
    app.state.incident_store = store
    app.state.connectors = connectors
    log_event(
        LOGGER,
        "incident_store_ready",
        service=SERVICE_NAME,
        backend=settings.store_backend,
        connectors=[connector.name for connector in connectors],
    )
    try:
        yield
    finally:
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
            service=SERVICE_NAME,
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
