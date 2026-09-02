import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from tool_gateway.api.router import router
from tool_gateway.core.config import get_settings
from tool_gateway.core.metrics import setup_metrics
from tool_gateway.core.observability import configure_logging, log_event
from tool_gateway.core.request_context import resolve_request_id
from tool_gateway.core.telemetry import setup_telemetry
from tool_gateway.metadata import SERVICE_NAME, SERVICE_TITLE, SERVICE_VERSION
from tool_gateway.tools.registry import ToolRegistry

LOGGER = logging.getLogger(__name__)


def _build_tool_registry() -> tuple[ToolRegistry, object | None]:
    """Build and populate the tool registry from enabled connectors.

    Returns the registry plus the browser connector (SPEC-049) when the
    browser flag is on — the connector needs app-lifecycle hooks for its
    eager CDP connection, which the registry itself does not own.
    """
    settings = get_settings()
    # Risk-tier admission (SPEC-021 R-1): mutating (write/admin) tools are
    # only admitted when GATEWAY_MUTATING_TOOLS_ENABLED is true; otherwise
    # the registry refuses their registration entirely.
    registry = ToolRegistry(allow_mutating=settings.mutating_tools_enabled)

    if settings.k8s_enabled:
        from tool_gateway.tools.k8s_connector import KubernetesConnector

        connector = KubernetesConnector(
            default_namespace=settings.k8s_namespace or None
        )
        connector.register_tools(registry)
        LOGGER.info("kubernetes connector registered")

    if settings.elastic_enabled:
        from tool_gateway.tools.elastic_connector import ElasticConnector

        connector = ElasticConnector(
            url=settings.elastic_url,
            api_key=settings.elastic_api_key,
            username=settings.elastic_username,
            password=settings.elastic_password,
            verify_tls=settings.elastic_verify_tls,
            alerts_index=settings.elastic_alerts_index,
        )
        connector.register_tools(registry)
        LOGGER.info("elastic connector registered")

    if settings.skills_service_url:
        from tool_gateway.tools.skills_connector import SkillsConnector

        connector = SkillsConnector(
            url=settings.skills_service_url,
            client_id=settings.skills_client_id,
            client_secret=settings.skills_client_secret,
        )
        connector.register_tools(registry)
        LOGGER.info("skills connector registered")

    if settings.incidents_service_url:
        from tool_gateway.tools.incidents_connector import IncidentsConnector

        connector = IncidentsConnector(
            url=settings.incidents_service_url,
            client_id=settings.incidents_client_id,
            client_secret=settings.incidents_client_secret,
        )
        connector.register_tools(registry)
        LOGGER.info("incidents connector registered")

    browser_connector = None
    if settings.browser_enabled:
        from tool_gateway.tools.browser_connector import BrowserConnector

        browser_connector = BrowserConnector(
            cdp_endpoint=settings.browser_cdp_endpoint,
            allow_origins=settings.browser_allow_origins,
            session_ttl_seconds=settings.browser_session_ttl_seconds,
            max_sessions=settings.browser_max_sessions,
            flow_max_steps=settings.browser_flow_max_steps,
            credential_sets_path=settings.browser_credential_sets_path,
            screenshot_max_bytes=settings.browser_screenshot_max_bytes,
            skills_service_url=settings.skills_service_url,
            skills_client_id=settings.skills_client_id,
            skills_client_secret=settings.skills_client_secret,
        )
        browser_connector.register_tools(registry)
        LOGGER.info("browser connector registered")

    return registry, browser_connector


def create_app() -> FastAPI:
    configure_logging()
    registry, browser_connector = _build_tool_registry()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # SPEC-049 R-1: with the flag on, connect eagerly to the sidecar
        # so first-navigate latency is paid at pod start, not first use.
        if browser_connector is not None:
            await browser_connector.start()
        yield
        if browser_connector is not None:
            await browser_connector.stop()

    app = FastAPI(
        title=SERVICE_TITLE, version=SERVICE_VERSION, lifespan=lifespan
    )
    app.state.tool_registry = registry
    if browser_connector is not None:
        app.state.browser_connector = browser_connector

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = resolve_request_id(request.headers.get("x-request-id"))
        started_at = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        log_event(
            LOGGER,
            "http_request",
            service="tool-gateway",
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
