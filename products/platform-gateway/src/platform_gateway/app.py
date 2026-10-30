import logging
import time

from fastapi import FastAPI, Request

from platform_gateway.api.router import router
from platform_gateway.core.metrics import setup_metrics
from platform_gateway.core.observability import configure_logging, log_event
from platform_gateway.core.secret_http import authorization_log_path, protect_http_records
from platform_gateway.services.target_authorization import BASE, NO_STORE, redirect
from fastapi.responses import JSONResponse
from platform_gateway.core.request_context import resolve_request_id
from platform_gateway.core.telemetry import setup_telemetry
from platform_gateway.metadata import SERVICE_NAME, SERVICE_TITLE, SERVICE_VERSION

LOGGER = logging.getLogger(__name__)


def create_app() -> FastAPI:
    protect_http_records()
    configure_logging()
    app = FastAPI(title=SERVICE_TITLE, version=SERVICE_VERSION)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        secret_edge = request.url.path.startswith(BASE)
        request_id = resolve_request_id(None if secret_edge else request.headers.get("x-request-id"))
        started_at = time.perf_counter()
        browser_navigation = request.url.path.startswith((BASE + "/callback", BASE + "/start/"))
        try:
            if browser_navigation and (request.method != "GET" or request.url.path.endswith("/")):
                response = redirect()
            else:
                response = await call_next(request)
        except Exception:
            if not secret_edge:
                raise
            response = redirect() if browser_navigation else JSONResponse(
                {"detail": "Target authorization unavailable"}, status_code=503)
        if secret_edge:
            for name, value in NO_STORE.items():
                response.headers[name] = value
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        log_event(
            LOGGER,
            "http_request",
            service="platform-gateway",
            request_id=request_id,
            method=request.method,
            path=authorization_log_path(request.url.path) if secret_edge else request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response

    app.include_router(router)
    setup_metrics(app)
    setup_telemetry(app, SERVICE_NAME, excluded_urls=(r"/api/v1/targets/authorizations",))
    return app


app = create_app()
