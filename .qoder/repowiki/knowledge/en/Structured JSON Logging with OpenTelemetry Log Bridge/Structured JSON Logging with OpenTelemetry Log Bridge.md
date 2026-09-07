---
kind: logging_system
name: Structured JSON Logging with OpenTelemetry Log Bridge
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/agent-platform/src/agent_service/app.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
---

## What system/approach is used

The platform uses Python's standard `logging` module as the sole logging framework. Every service ships an identical `core/observability.py` that exposes two helpers: `configure_logging()` (raises the root logger from uvicorn's default WARNING to INFO so audit records are not silently dropped) and `log_event(logger, event, **fields)` which serializes a single-line JSON record via `json.dumps(..., sort_keys=True, default=str)` at INFO level. Structured logs are emitted to stdout; they are the canonical audit trail.

An opt-in OpenTelemetry (OTel) push pipeline mirrors every structured log into OTLP HTTP/protobuf (`/v1/logs`) via `opentelemetry.instrumentation.logging.handler.LoggingHandler`. The bridge is attached in `core/telemetry.py`'s `_attach_log_bridge`, gated by `OTEL_ENABLED`, and fails open — initialization errors are logged but never raised into the request path.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — authoritative spec for all services: log levels, OTel switch semantics, correlation headers, cardinality rules, and the relationship between stdout JSON and OTLP mirror.
- Per-service `src/<service>/core/observability.py` — identical `configure_logging()` / `log_event()` pair (agent-platform, platform-gateway, audit-service, execution-runtime, identity-broker, incident-service, skills-hub, tool-gateway).
- Per-service `src/<service>/core/telemetry.py` — identical OTel setup: `setup_telemetry(app, service_name)`, `is_enabled()`, `current_trace_id()`, and `_attach_log_bridge`.
- Per-service `src/<service>/app.py` — calls `configure_logging()` before creating the FastAPI app, installs an HTTP middleware that emits `http_request` events via `log_event`, then calls `setup_metrics` and `setup_telemetry`.
- `products/*/metadata.py` — provides `SERVICE_NAME` consumed by OTel Resource creation.

## Architecture and conventions

### Initialization order
Every service follows the same startup sequence:
1. `configure_logging()` — reads `LOG_LEVEL` (default `INFO`), calls `logging.basicConfig(level=..., force=True)`.
2. Create FastAPI app.
3. Register HTTP middleware that wraps each request, resolves `x-request-id`, measures duration, and emits an `http_request` event through `log_event`.
4. `setup_metrics(app)` — Prometheus `/metrics` endpoint (always on).
5. `setup_telemetry(app, SERVICE_NAME)` — if `OTEL_ENABLED` is truthy, initializes TracerProvider, MeterProvider, and attaches the OTel LoggingHandler to the root logger.

### Structured log format
Business and request events are emitted as one-line JSON objects containing at minimum an `event` field plus domain-specific fields. Example from the HTTP middleware:
```json
{"event": "http_request", "method": "POST", "path": "/api/v2/sessions", "request_id": "...", "service": "platform-gateway", "status_code": 200, "duration_ms": 12.34}
```
Fields are sorted keys and coerced to strings via `default=str`, ensuring stable, parseable output.

### Log levels
- INFO is the baseline for all audit/business events. Uvicorn's default WARNING level is explicitly raised because it would discard these records.
- DEBUG-level or lower logs are not part of the audit surface.
- `LOG_LEVEL` overrides per deployment.

### Request correlation
- `x-request-id` is the log- and portal-facing correlation key, generated if absent and forwarded on outbound calls.
- When tracing is active, `x-request-id` is set to the active span's W3C `trace_id` (32 hex chars); otherwise it falls back to `req-<uuid4>`.
- `traceparent` (W3C Trace Context) is propagated automatically by OTel instrumentation across service hops.
- `current_trace_id()` lets callers inject trace context into structured logs when needed.

### OTLP log bridge
When enabled, the bridge:
- Attaches `LoggingHandler` to the root logger at INFO level.
- Detaches `opentelemetry` internal loggers from propagation to prevent recursion.
- Automatically associates logs with active spans via `trace_id`/`span_id`.
- Exports via `OTEL_EXPORTER_OTLP_ENDPOINT` + `OTEL_EXPORTER_OTLP_HEADERS`; authentication is provisioned via runtime secrets, never committed.
- The JSON stdout stream remains the source of truth; the OTLP mirror exists only for backend correlation.

### Metric naming convention (related observability)
Metrics use `<service>_<noun>_<unit>` snake_case with `_total` suffix on counters, bounded enum labels only, and no high-cardinality labels (raw URLs, user ids, session ids, request ids). This complements the logging strategy by providing machine-readable signals alongside human-readable audit logs.

## Conventions and constraints

- **All business/request events go through `log_event(...)` at INFO level.** Ad hoc `logger.info("...")` without structured fields is not used for audit events; the HTTP middleware enforces this pattern for request lifecycle logging.
- **Root logger must be configured before any business code runs.** Each service calls `configure_logging()` inside `create_app()` before including routers.
- **OTel push is opt-in and fail-open.** `OTEL_ENABLED=false` (default) leaves `/metrics` fully functional and produces no OTel overhead. Setup exceptions are caught and logged; they never break requests.
- **No unbounded label cardinality.** The observability conventions explicitly forbid labeling on raw URLs, user ids, session ids, or request ids.
- **Audit records are single-line JSON on stdout.** Downstream consumers (container log collectors, audit tooling) read stdout; the OTLP mirror is secondary.
- **Service name tagging.** OTel Resource uses `OTEL_SERVICE_NAME` (defaults to `SERVICE_NAME` from metadata) so all traces/metrics/logs are attributable to a service.
- **Secrets for OTel auth** (`OTEL_EXPORTER_OTLP_HEADERS`) are provisioned via `sync-otel-secrets.sh` into runtime Secrets and never committed to source control.