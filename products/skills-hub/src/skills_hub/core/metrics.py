"""Prometheus metrics surface for skills-hub (SPEC-005 R-1/R-2, SPEC-014).

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

SKILLS_SYNCS = Counter(
    "skills_syncs_total",
    "Per-source sync cycles completed.",
    ["source", "result"],
)

SKILLS_SEARCHES = Counter(
    "skills_searches_total",
    "Search requests served.",
)

SKILLS_REJECTED = Counter(
    "skills_ingest_rejected_total",
    "Documents rejected by ingestion validation.",
    ["reason"],
)

SKILLS_STORE_SIZE = Gauge(
    "skills_store_skills",
    "Number of validated skills currently served.",
    ["source"],
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


def record_sync(source: str, result: str) -> None:
    SKILLS_SYNCS.labels(source=source, result=result).inc()


def record_search() -> None:
    SKILLS_SEARCHES.inc()


def record_rejected(reason: str) -> None:
    SKILLS_REJECTED.labels(reason=reason).inc()


def set_source_size(source: str, count: int) -> None:
    SKILLS_STORE_SIZE.labels(source=source).set(count)


def record_audit_emit(result: str) -> None:
    AUDIT_EMITS.labels(result=result).inc()
