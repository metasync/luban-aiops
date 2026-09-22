---
kind: logging_system
name: Structured JSON Logging with OTLP Bridge and Per-Service Observability Modules
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
    - products/audit-service/src/audit_service/app.py
---

## What system/approach is used

The platform uses Python's standard `logging` module as the sole logging framework. Every product service (agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway) ships its own `core/observability.py` that exposes two functions — `configure_logging()` and `log_event(logger, event, **fields)` — which are imported at app startup and used throughout the codebase to emit structured, single-line JSON records. There is no third-party logger library; log output goes to stdout as one JSON object per line.

Structured logs are mirrored into OpenTelemetry via an opt-in OTLP HTTP bridge (`opentelemetry.exporter.otlp.proto.http._log_exporter`) so the backend can correlate logs with traces. The mirror is gated by `OTEL_ENABLED`; when disabled, only stdout JSON is produced.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — authoritative specification of the observability surface: metric naming, cardinality rules, OTel switch semantics, request correlation (`x-request-id`), and the rule that all business/request events are emitted as INFO-level JSON via `log_event(...)`.
- Per-product `src/<service>/core/observability.py` — identical implementations of `configure_logging()` (reads `LOG_LEVEL`, defaults to `INFO`, calls `logging.basicConfig(level=..., force=True)`) and `log_event()` (serializes `{"event": ..., **fields}` with `json.dumps(..., default=str, sort_keys=True)`).
- Per-product `src/<service>/core/telemetry.py` — identical `setup_telemetry(app, service_name)` that initializes TracerProvider, MeterProvider, FastAPI/HTTPX instrumentation, and attaches an OTLP `LoggingHandler` to the root logger when `OTEL_ENABLED` is truthy; also provides `current_trace_id()`.
- Service entry points call both in order: `configure_logging()` first, then `setup_telemetry(app, SERVICE_NAME)` after routers/metrics are attached (e.g. `products/agent-platform/src/agent_service/app.py`, `products/audit-service/src/audit_service/app.py`).
- `products/agent-platform/src/agent_service/core/request_context.py` — resolves/generates `x-request-id` and bridges it to the active W3C `traceparent` trace id when tracing is active.

## Architecture and conventions

1. **Per-service isolation.** Each product owns its own `core/observability.py` and `core/telemetry.py`. There is no shared SDK package for logging; the modules are duplicated across services but kept byte-equivalent so a future extraction is straightforward.
2. **Structured event schema.** Business and request events use `log_event(LOGGER, "http_request", service=..., request_id=..., method=..., path=..., status_code=..., duration_ms=...)`. The resulting JSON always contains an `event` field plus whatever fields the caller passes; keys are sorted for stable output.
3. **Log level strategy.** Uvicorn starts the root logger at `WARNING`, which would drop every `log_event` record. Services explicitly raise the root level to `INFO` at startup via `configure_logging()`. The effective level is controlled by the `LOG_LEVEL` environment variable (any value accepted by `getattr(logging, name, logging.INFO)`); the documented default must stay `INFO` so audit records are never silently discarded.
4. **OTLP log bridge.** When `OTEL_ENABLED=true`, `setup_telemetry` installs an OpenTelemetry `LoggingHandler` on the root logger. Records emitted inside an active span automatically carry `trace_id`/`span_id`, joining them to the trace view using the same W3C id that backs `x-request-id`. The `opentelemetry` internal loggers are detached from the root logger (`propagate = False`) to prevent recursion if the exporter fails.
5. **Fail-open design.** Missing or misconfigured OTLP endpoints produce export-time failures that are logged and dropped; they never raise into the request path. Disabling OTel leaves `/metrics` fully functional.
6. **Request correlation.** `x-request-id` is the log- and portal-facing correlation key. When tracing is active it is set to the active span's W3C `trace_id`; otherwise it falls back to a generated `req-<uuid4>`. No service may silently drop an inbound correlation id.
7. **Metrics vs logs separation.** The convention defines two decoupled surfaces: pull-based Prometheus `/metrics` (always on) and push-based OTLP traces/metrics/logs (opt-in). They never depend on each other.

## Conventions and constraints

- Emit business and request events as INFO-level single-line JSON through `log_event(...)`, not via raw `logger.info(...)` calls with ad-hoc formatting.
- Always call `configure_logging()` at application startup before any business code runs, so the root logger level is raised above uvicorn's WARNING default.
- Control verbosity per-deployment via the `LOG_LEVEL` environment variable; do not hard-code levels in code.
- Gate all OpenTelemetry initialization behind `OTEL_ENABLED`; when false, zero OTel providers are initialized and no network calls are made.
- Use `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`, and `OTEL_SERVICE_NAME` for OTLP configuration; credentials go in runtime secrets, never in ConfigMaps or source.
- Never label metrics with unbounded values (raw URL, user id, session id, request id); use bounded enum labels only.
- Do not replace stdout JSON with the OTLP mirror — stdout remains the source of truth for audit tooling; the OTLP bridge exists solely for trace/log correlation.
- Propagate `x-request-id` on every outbound service-to-service call; do not drop inbound correlation ids.