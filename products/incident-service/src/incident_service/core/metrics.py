"""Prometheus metrics surface for incident-service (SPEC-005 R-1/R-2, SPEC-015).

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

INCIDENTS_INTAKES = Counter(
    "incident_intakes_total",
    "Incidents accepted per intake channel.",
    ["source", "result"],
)

INCIDENT_TRIAGES = Counter(
    "incident_triages_total",
    "Triage runs completed per outcome.",
    ["result"],
)

INCIDENT_DISPATCHES = Counter(
    "incident_connector_dispatches_total",
    "Connector dispatch attempts per connector and outcome.",
    ["connector", "result"],
)

INCIDENTS_OPEN = Gauge(
    "incidents_open",
    "Number of incidents not yet resolved.",
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


def record_intake(source: str, result: str) -> None:
    INCIDENTS_INTAKES.labels(source=source, result=result).inc()


def record_triage(result: str) -> None:
    INCIDENT_TRIAGES.labels(result=result).inc()


def record_dispatch(connector: str, result: str) -> None:
    INCIDENT_DISPATCHES.labels(connector=connector, result=result).inc()


def set_open_incidents(count: int) -> None:
    INCIDENTS_OPEN.set(count)
