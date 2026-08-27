import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from execution_runtime.api.router import router
from execution_runtime.core.metrics import setup_metrics
from execution_runtime.core.observability import configure_logging, log_event
from execution_runtime.core.request_context import resolve_request_id
from execution_runtime.core.telemetry import setup_telemetry
from execution_runtime.metadata import SERVICE_NAME, SERVICE_TITLE, SERVICE_VERSION
from execution_runtime.services.execution_records import build_execution_record_store
from execution_runtime.services.single_flight import SingleFlightRegistry

LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from execution_runtime.core.config import get_settings

    settings = get_settings()
    app.state.execution_record_store = build_execution_record_store(settings)
    app.state.single_flights = SingleFlightRegistry(
        retention_seconds=settings.flight_retention_seconds
    )
    LOGGER.info(
        "execution worker ready",
        extra={
            "store_backend": settings.state_store_backend,
            "tool_gateway_url": settings.tool_gateway_url,
            "signing_key_configured": bool(settings.execution_signing_key),
            "handoff_token_configured": bool(settings.handoff_token),
        },
    )
    yield


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
            service="execution-runtime",
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
