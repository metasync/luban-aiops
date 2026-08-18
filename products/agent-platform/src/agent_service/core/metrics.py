"""Prometheus metrics surface (SPEC-005 R-1/R-2).

Always-on, collector-independent debug surface implemented directly with
prometheus_client: a minimal RED middleware plus GET /metrics. Metric objects
live at module level so repeated create_app() calls (tests) never
double-register them. Conventions:
shared/shared-contracts/observability-conventions.md.
"""

from __future__ import annotations

import time

from fastapi import FastAPI, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests processed.",
    ["method", "handler", "status"],
)

HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ["method", "handler"],
)

SESSIONS_CREATED = Counter(
    "agent_sessions_created_total",
    "Agent sessions created.",
)

CHAT_REQUESTS = Counter(
    "agent_chat_requests_total",
    "Chat requests handled (blocking and streaming).",
)


def _handler_label(request: Request) -> str:
    # Templated route path (bounded cardinality), never the raw URL.
    route = request.scope.get("route")
    return getattr(route, "path", "unmatched")


def setup_metrics(app: FastAPI) -> None:
    """Attach the RED middleware and expose GET /metrics (always on)."""

    @app.middleware("http")
    async def record_http_metrics(request: Request, call_next):
        started_at = time.perf_counter()
        response = await call_next(request)
        handler = _handler_label(request)
        if handler != "/metrics":
            HTTP_REQUESTS.labels(
                method=request.method,
                handler=handler,
                status=str(response.status_code),
            ).inc()
            HTTP_REQUEST_DURATION.labels(
                method=request.method, handler=handler
            ).observe(time.perf_counter() - started_at)
        return response

    @app.get("/metrics", include_in_schema=False)
    def metrics_endpoint() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def record_session_created() -> None:
    SESSIONS_CREATED.inc()


def record_chat_request() -> None:
    CHAT_REQUESTS.inc()


# --- Session store observability (SPEC-006 R-3/R-4) ---

SESSION_STORE_BACKEND_GAUGE = Gauge(
    "session_store_backend",
    "Active session store backend (1 = active).",
    ["backend"],
)

SESSION_STORE_ERRORS = Counter(
    "session_store_errors_total",
    "Session store operation failures.",
    ["operation"],
)

SESSION_STORE_FALLBACKS = Counter(
    "session_store_fallbacks_total",
    "Times the session store fell back to in-memory due to backend failure.",
)


def record_session_store_backend(backend: str) -> None:
    """Set the active backend gauge (1 for active, 0 for others)."""
    for label in ("redis", "memory", "postgres"):
        SESSION_STORE_BACKEND_GAUGE.labels(backend=label).set(
            1 if label == backend else 0
        )


def record_session_store_error(operation: str) -> None:
    SESSION_STORE_ERRORS.labels(operation=operation).inc()


def record_session_store_fallback() -> None:
    SESSION_STORE_FALLBACKS.inc()


# --- Agent state store observability (SPEC-017 R-5) ---

AGENT_STATE_BACKEND_GAUGE = Gauge(
    "agent_state_backend",
    "Active agent state store backend (1 = active).",
    ["backend"],
)

AGENT_STATE_ERRORS = Counter(
    "agent_state_errors_total",
    "Agent state store operation failures.",
    ["operation"],
)

AGENT_STATE_FALLBACKS = Counter(
    "agent_state_fallbacks_total",
    "Times the agent state store fell back to in-memory due to backend failure.",
)


def record_agent_state_backend(backend: str) -> None:
    """Set the active backend gauge (1 for active, 0 for others)."""
    for label in ("memory", "postgres"):
        AGENT_STATE_BACKEND_GAUGE.labels(backend=label).set(
            1 if label == backend else 0
        )


def record_agent_state_error(operation: str) -> None:
    AGENT_STATE_ERRORS.labels(operation=operation).inc()


def record_agent_state_fallback() -> None:
    AGENT_STATE_FALLBACKS.inc()
