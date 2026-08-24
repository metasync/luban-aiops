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
    - products/audit-service/src/audit_service/core/observability.py
    - products/audit-service/src/audit_service/core/telemetry.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/identity-broker/src/identity_service/core/telemetry.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/incident-service/src/incident_service/core/telemetry.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/skills-hub/src/skills_hub/core/telemetry.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/telemetry.py
---

## What system/approach is used

The platform uses Python's standard `logging` module as the sole logging framework. Every microservice in `products/` (agent-platform, audit-service, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway) ships an identical pair of helpers under its own `src/<service>/core/observability.py`: a `configure_logging()` function that raises the root logger from Uvicorn's default `WARNING` to `INFO`, and a `log_event(logger, event, **fields)` helper that emits single-line structured JSON via `json.dumps(payload, default=str, sort_keys=True)`. Business and request events are emitted exclusively through this helper at `INFO` level; there is no ad-hoc `print` or unstructured log usage for audit-relevant events.

An opt-in OpenTelemetry push pipeline lives in each service's `core/telemetry.py`. When `OTEL_ENABLED=true`, it installs a `LoggingHandler` on the root logger so every `log_event(...)` record is mirrored into OTLP logs (HTTP/protobuf to `OTEL_EXPORTER_OTLP_ENDPOINT`). The stdout JSON remains the source of truth; the OTLP mirror exists only for correlation with traces/metrics in the backend (OpenObserve). OTel setup is fail-open: initialization errors are logged and never raised into the request path.

## Key files and packages

- Per-service observability helpers (identical across services):
  - `products/*/src/*_service/core/observability.py` — `configure_logging()`, `log_event()`
  - `products/*/src/*_service/core/telemetry.py` — OTel switch (`is_enabled`), bridge (`_attach_log_bridge`), trace/metric/log setup (`setup_telemetry`), `current_trace_id()`
- Shared contract documenting conventions:
  - `shared/shared-contracts/observability-conventions.md`
- Request-context propagation (used by routes to attach `x-request-id` / trace id to logs):
  - `products/*/src/*_service/core/request_context.py`
- Service entrypoints that call `configure_logging()` and `setup_telemetry(app)`:
  - `products/*/src/*_service/app.py` (e.g. `agent_service/app.py`, `audit_service/app.py`, `platform_gateway/app.py`, etc.)

## Architecture and conventions

1. **Single structured log format.** All business/request events go through `log_event(logger, "event_name", field=value, …)`, which serializes `{"event": ..., **fields}` as one JSON line at `INFO`. This makes every audit-relevant record parseable and queryable.
2. **Root logger elevation.** `configure_logging()` calls `logging.basicConfig(level=..., force=True)` using `LOG_LEVEL` (default `INFO`) so Uvicorn's default `WARNING` threshold does not drop audit records. Tests explicitly verify that setting `LOG_LEVEL=WARNING` suppresses those records.
3. **Opt-in OTel log bridge.** `setup_telemetry(app, service_name)` initializes TracerProvider, MeterProvider, FastAPI/HTTPX instrumentation, and attaches an OTel `LoggingHandler` to the root logger. The bridge is guarded by `OTEL_ENABLED`; when disabled, no OTel providers are created and `/metrics` stays unaffected. Exporter failures are isolated by detaching `opentelemetry` loggers from the root logger.
4. **Request correlation.** `x-request-id` is the log- and portal-facing correlation key. When tracing is active, it is set to the active span's W3C `trace_id` (via `current_trace_id()`); otherwise it falls back to a generated `req-<uuid4>`. Routes include it in every `log_event` call so downstream services can join the same request.
5. **Service naming.** `OTEL_SERVICE_NAME` overrides the resource `service.name`; otherwise the service's metadata name is used. `OTEL_EXPORTER_OTLP_HEADERS` carries Basic-auth credentials provisioned via runtime secrets (never committed).
6. **Fail-open design.** Both logging configuration and OTel setup are defensive: missing env vars use safe defaults, and any exception during telemetry initialization is caught and logged rather than propagated.

## Conventions and constraints

- **All audit-relevant events must be emitted via `log_event(...)`** at `INFO` level so they survive the root logger elevation and are captured by both stdout and the OTLP mirror. This is documented in `shared/shared-contracts/observability-conventions.md` and enforced by tests that assert `configure_logging()` raises the root level.
- **Log level override:** `LOG_LEVEL` controls the minimum level per deployment; the default must remain `INFO` so audit records are never silently discarded.
- **OTel push is off by default:** `OTEL_ENABLED` must be explicitly set to enable traces, metrics, and the log bridge. No per-signal toggles exist — one switch gates the full signal.
- **No high-cardinality labels in metrics** (related observability constraint): raw URLs, user ids, session ids, and request ids must not be used as metric labels.
- **JSON stdout is the source of truth.** The OTLP log mirror is secondary; consumers must keep reading container stdout for the audit trail.
- **Correlation header rule:** no service may silently drop an inbound `x-request-id`; when tracing is active, `x-request-id` equals the active span's `trace_id`.
- **Environment variables are the only configuration surface** for logging/telemetry: `LOG_LEVEL`, `OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_SERVICE_NAME`.

These patterns are replicated across every Python service in `products/`, making logging a uniform cross-cutting concern governed by shared contracts rather than per-service choices.