import asyncio
import contextlib
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from agent_service.api.v2.routes import router as v2_router
from agent_service.core.metrics import setup_metrics
from agent_service.core.observability import configure_logging, log_event
from agent_service.core.request_context import resolve_request_id
from agent_service.core.telemetry import setup_telemetry
from agent_service.metadata import SERVICE_NAME, SERVICE_TITLE, SERVICE_VERSION

LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def _app_lifespan(_: FastAPI):
    """SPEC-027 R-3: start the live model discovery background task
    (initial fetch, then periodic refresh); cancel it on shutdown.
    Skipped entirely when discovery is disabled or no provider is
    configured — startup stays byte-equivalent to SPEC-026."""
    from agent_service.services.model_catalog import (
        configured_providers,
        startup_settings,
    )
    from agent_service.services.model_discovery import build_discovery_service

    settings = startup_settings()
    service = build_discovery_service(settings, configured_providers(settings))
    if service is None:
        yield
        return
    task = asyncio.create_task(service.run_loop())
    LOGGER.info(
        "model discovery: background refresh every %ss",
        settings.model_discovery_refresh_seconds,
    )
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title=SERVICE_TITLE, version=SERVICE_VERSION, lifespan=_app_lifespan
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
