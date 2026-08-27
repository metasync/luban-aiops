"""Prometheus metrics surface for execution-runtime (SPEC-005 parity, SPEC-038).

Always-on, collector-independent debug surface implemented directly with
prometheus_client: a minimal RED middleware plus GET /metrics. Metric objects
live at module level so repeated create_app() calls (tests) never
double-register them in the default registry. Conventions:
shared/shared-contracts/observability-conventions.md.
"""

from __future__ import annotations

import time

from fastapi import FastAPI, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
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

EXECUTION_HANDOFFS = Counter(
    "execution_handoffs_total",
    "Handoff requests accepted past authentication and verification.",
)

EXECUTION_REJECTIONS = Counter(
    "execution_handoff_rejections_total",
    "Handoff requests rejected before any execution (fail-closed).",
    ["reason"],
)

EXECUTION_COMPLETIONS = Counter(
    "execution_completions_total",
    "Executions closed with a signed receipt, by receipt status.",
    ["status"],
)

EXECUTION_LATE_COMPLETIONS = Counter(
    "execution_late_completions_total",
    "Receipt closes that found the row already closed (late arrival).",
)

AUDIT_EMITS = Counter(
    "audit_emits_total",
    "Audit event emission attempts to the audit service (SPEC-013).",
    ["result"],
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


def record_handoff() -> None:
    EXECUTION_HANDOFFS.inc()


def record_rejection(reason: str) -> None:
    EXECUTION_REJECTIONS.labels(reason=reason).inc()


def record_completion(status: str) -> None:
    EXECUTION_COMPLETIONS.labels(status=status).inc()


def record_late_completion() -> None:
    EXECUTION_LATE_COMPLETIONS.inc()


def record_audit_emit(result: str) -> None:
    """Record an audit emission outcome (``ok`` or ``error``)."""
    AUDIT_EMITS.labels(result=result).inc()
