import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from skills_hub.api.router import router
from skills_hub.core.config import get_settings
from skills_hub.core.metrics import setup_metrics
from skills_hub.core.observability import configure_logging, log_event
from skills_hub.core.request_context import resolve_request_id
from skills_hub.core.telemetry import setup_telemetry
from skills_hub.metadata import SERVICE_NAME, SERVICE_TITLE, SERVICE_VERSION
from skills_hub.services.skill_store import build_skill_store
from skills_hub.services.sync import SyncManager

LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    store = build_skill_store(settings)
    await store.initialize()
    # Sources removed from SKILLS_SOURCES never sync again; prune their
    # stale rows so the catalog matches the federation entry exactly.
    configured_sources = [spec.source_id for spec in settings.sources]
    if not configured_sources:
        # An empty federation entry wipes the durable store on restart;
        # that is consistent semantics, but a misdeploy should be loud.
        LOGGER.warning(
            "SKILLS_SOURCES is empty; pruning will remove every stored skill"
        )
    pruned = await store.prune_sources(configured_sources)
    if pruned:
        LOGGER.info(
            "pruned skills from unconfigured sources",
            extra={"pruned": pruned},
        )
    app.state.skills_store = store
    sync_manager = SyncManager(settings, store)
    app.state.sync_manager = sync_manager
    await sync_manager.start()
    LOGGER.info(
        "skills store ready",
        extra={
            "backend": settings.store_backend,
            "sources": [spec.source_id for spec in settings.sources],
            "sync_interval_seconds": settings.sync_interval_seconds,
        },
    )
    try:
        yield
    finally:
        await sync_manager.stop()
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
            service="skills-hub",
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
