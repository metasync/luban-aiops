import logging
import signal
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from execution_runtime.api.router import router
from execution_runtime.core.metrics import record_drain_state, setup_metrics
from execution_runtime.core.observability import configure_logging, log_event
from execution_runtime.core.telemetry import setup_telemetry
from execution_runtime.metadata import SERVICE_NAME, SERVICE_TITLE, SERVICE_VERSION
from execution_runtime.services.execution_ledger import ExecutionLedger
from execution_runtime.services.execution_protocol import request_id as safe_request_id

LOGGER = logging.getLogger(__name__)


def _install_drain_signal_handler(app: FastAPI) -> None:
    """Flip ``draining`` on SIGTERM before uvicorn's graceful shutdown proceeds.

    SPEC-063 R-7c: on SIGTERM the worker must immediately refuse new handoffs
    and mark itself unready, then let in-flight work drain within the bounded
    graceful-shutdown budget and terminate WITHOUT releasing any claim. Only the
    main thread under a real server owns signal handling; under TestClient the
    lifespan runs off the main thread and the flag is driven by the lifespan
    shutdown instead. The previously installed (uvicorn) handler is preserved so
    the bounded drain still runs.
    """
    if threading.current_thread() is not threading.main_thread():
        return
    try:
        previous = signal.getsignal(signal.SIGTERM)
    except (ValueError, OSError):
        return

    def handler(signum, frame):
        app.state.draining = True
        record_drain_state(True)
        if callable(previous):
            previous(signum, frame)

    try:
        signal.signal(signal.SIGTERM, handler)
    except (ValueError, OSError):
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    from execution_runtime.core.config import get_settings

    settings = get_settings()
    if app.state.ledger is None:
        app.state.ledger = ExecutionLedger(
            settings.state_db_url if settings.state_store_backend == "postgres" else "",
            settings.execution_signing_key, settings.admission_epoch,
            admission_enabled=settings.admission_enabled,
        )
    app.state.draining = False
    record_drain_state(False)
    _install_drain_signal_handler(app)
    LOGGER.info(
        "execution worker started; readiness requires durable admission",
        extra={
            "store_backend": settings.state_store_backend,
            "signing_key_configured": bool(settings.execution_signing_key),
            "handoff_token_configured": bool(settings.handoff_token),
        },
    )
    yield
    app.state.draining = True
    record_drain_state(True)


def create_app(*, ledger=None, lifecycle_hook=None) -> FastAPI:
    configure_logging()
    app = FastAPI(
        title=SERVICE_TITLE, version=SERVICE_VERSION, lifespan=lifespan
    )

    app.state.ledger = ledger
    app.state.lifecycle_hook = lifecycle_hook
    app.state.draining = False

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = safe_request_id(request.headers.get("x-request-id"))
        request.state.request_id = request_id
        started_at = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        log_event(
            LOGGER,
            "http_request",
            service="execution-runtime",
            request_id=request_id,
            method=request.method,
            path=getattr(request.scope.get("route"), "path", "unmatched"),
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response

    app.include_router(router)
    setup_metrics(app)
    setup_telemetry(app, SERVICE_NAME)
    return app


app = create_app()
