---
kind: logging_system
name: Structured Logging and Observability Pipeline
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/tool-gateway/src/api_gateway/core/observability.py
    - products/agent-platform/src/agent_service/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/tool-gateway/src/api_gateway/core/telemetry.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/identity-broker/src/identity_service/core/telemetry.py
    - products/tool-gateway/src/api_gateway/core/request_context.py
    - products/agent-platform/src/agent_service/core/request_context.py
    - products/tool-gateway/src/api_gateway/app.py
    - products/agent-platform/src/agent_service/app.py
    - products/identity-broker/src/identity_service/app.py
---

The repository implements a consistent, structured logging system across all three Python services (`tool-gateway`, `agent-platform`, `identity-broker`) built on Python's standard `logging` module, layered with OpenTelemetry for optional distributed tracing and Prometheus metrics.

**Framework and structure**
- Each service defines an identical `core/observability.py` exposing a single `log_event(logger, event, **fields)` helper that serializes the payload as JSON with sorted keys via `json.dumps(..., default=str, sort_keys=True)`. This produces one-line JSON log records at `INFO` level.
- Every module creates a module-scoped logger via `LOGGER = logging.getLogger(__name__)`, giving each file its own logger name.
- HTTP request logging is centralized in each service's `app.py` FastAPI middleware: every request emits an `http_request` event containing `service`, `request_id`, `method`, `path`, `status_code`, and `duration_ms`.

**Structured fields and correlation**
- The `x-request-id` header is the primary correlation key. It is resolved per-request by `core/request_context.resolve_request_id()`: inbound value wins, otherwise it bridges to the active OTel `trace_id` when tracing is enabled, else falls back to a generated `req-<uuid4>`.
- The identity-broker additionally falls back to `current_trace_id()` directly in its middleware before generating a UUID.
- All business events are emitted through `log_event`, which guarantees a uniform `{"event": ..., ...fields}` shape.

**OpenTelemetry (opt-in)**
- Each service has an identical `core/telemetry.py` implementing an opt-in OTLP push pipeline gated by the `OTEL_ENABLED` environment variable (truthy values: `1`, `true`, `yes`, `on`). When disabled, no providers are initialized and there is zero overhead.
- On enable, it sets up a `TracerProvider` with a `BatchSpanProcessor(OTLPSpanExporter())`, a `MeterProvider` with a `PeriodicExportingMetricReader`, instruments FastAPI and HTTPX clients, and exposes `current_trace_id()` for correlation bridging.
- Initialization is fail-open: any exception during setup is logged via `LOGGER.exception(...)` and never raised into the request path.

**Prometheus metrics**
- A separate `/metrics` endpoint is always-on via `prometheus-fastapi-instrumentator`, configured through `setup_metrics(app)` in each service's app factory.
- Metric naming follows `<service>_<noun>_<unit>` snake_case with `_total` suffixes for counters, using bounded enum labels only (no high-cardinality labels like raw URLs, user ids, session ids).

**Conventions enforced by code and documentation**
- `shared/shared-contracts/observability-conventions.md` documents the two-surface model (pull `/metrics` + optional OTel push), metric naming, cardinality rules, and the `x-request-id` / `traceparent` bridging rule.
- No service may silently drop an inbound correlation id; request IDs must be forwarded on outbound calls.
- Log levels used consistently: `info` for normal operational events, `warning` for recoverable issues, `exception` for errors that need stack traces.
- Structured logs are always JSON lines; plain `print()` or unstructured string logging is not used for application events.