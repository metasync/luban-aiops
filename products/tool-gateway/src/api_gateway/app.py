import logging
import time

from fastapi import FastAPI, Request

from api_gateway.api.router import router
from api_gateway.core.config import get_settings
from api_gateway.core.metrics import setup_metrics
from api_gateway.core.observability import log_event
from api_gateway.core.request_context import resolve_request_id
from api_gateway.core.telemetry import setup_telemetry
from api_gateway.metadata import SERVICE_NAME, SERVICE_TITLE, SERVICE_VERSION
from api_gateway.tools.registry import ToolRegistry

LOGGER = logging.getLogger(__name__)


def _build_tool_registry() -> ToolRegistry:
    """Build and populate the tool registry from enabled connectors."""
    settings = get_settings()
    registry = ToolRegistry()

    if settings.k8s_enabled:
        from api_gateway.tools.k8s_connector import KubernetesConnector

        connector = KubernetesConnector(
            default_namespace=settings.k8s_namespace or None
        )
        connector.register_tools(registry)
        LOGGER.info("kubernetes connector registered")

    return registry


def create_app() -> FastAPI:
    app = FastAPI(title=SERVICE_TITLE, version=SERVICE_VERSION)
    app.state.tool_registry = _build_tool_registry()

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = resolve_request_id(request.headers.get("x-request-id"))
        started_at = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        log_event(
            LOGGER,
            "http_request",
            service="api-gateway",
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
