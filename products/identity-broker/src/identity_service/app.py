import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request

from identity_service.api.router import router
from identity_service.core.observability import log_event
from identity_service.metadata import SERVICE_TITLE, SERVICE_VERSION

LOGGER = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title=SERVICE_TITLE, version=SERVICE_VERSION)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or f"req-{uuid4()}"
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
    return app


app = create_app()
