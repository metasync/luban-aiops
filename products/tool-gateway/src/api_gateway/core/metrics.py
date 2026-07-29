"""Prometheus metrics surface (SPEC-005 R-1/R-2).

Always-on, collector-independent debug surface implemented directly with
prometheus_client: a minimal RED middleware plus GET /metrics.
(prometheus-fastapi-instrumentator was evaluated but its route introspection
is incompatible with the pinned starlette; see SPEC-005 changelog.)

Metric objects live at module level so repeated create_app() calls (tests)
never double-register them in the default registry. Conventions:
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

POLICY_DECISIONS = Counter(
    "gateway_policy_decisions_total",
    "Policy decisions evaluated by the gateway.",
    ["action", "decision"],
)

TOKEN_VERIFICATIONS = Counter(
    "gateway_token_verification_total",
    "Bearer token verification outcomes.",
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


def record_policy_decision(action: str, decision: str) -> None:
    POLICY_DECISIONS.labels(action=action, decision=decision).inc()


def record_token_verification(result: str) -> None:
    TOKEN_VERIFICATIONS.labels(result=result).inc()
