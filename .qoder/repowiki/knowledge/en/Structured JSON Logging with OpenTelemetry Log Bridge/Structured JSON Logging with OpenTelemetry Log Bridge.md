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

The platform uses Python's standard `logging` module as the sole logging framework. There is no third-party logger library (no structlog, loguru, or similar). Every service ships an identical `core/observability.py` that provides two helpers: `configure_logging()` and `log_event(logger, event, **fields)`. Structured events are emitted as single-line JSON via `json.dumps(..., default=str, sort_keys=True)` at `INFO` level, making them parseable by container log collectors.

An opt-in OpenTelemetry push pipeline mirrors every structured log record to OTLP HTTP/protobuf (`OTEL_ENABLED` gate, default off). The bridge attaches an `opentelemetry.instrumentation.logging.LoggingHandler` to the root logger so records automatically inherit the active span's `trace_id`/`span_id`, enabling correlation between stdout audit logs and APM traces.

## Key files and packages

- Per-service `src/<service>/core/observability.py` — defines `configure_logging()` (raises root logger from uvicorn's WARNING default to INFO; overridable via `LOG_LEVEL`) and `log_event()` (serializes `{event, ...fields}` to JSON).
- Per-service `src/<service>/core/telemetry.py` — implements `setup_telemetry(app, service_name)`, `is_enabled()`, `_attach_log_bridge(resource)`, and `current_trace_id()`. Gated by `OTEL_ENABLED`; fails open on setup errors.
- Per-service `src/<service>/app.py` — calls `configure_logging()` before creating the FastAPI app, installs an HTTP middleware that emits `http_request` events via `log_event`, then calls `setup_metrics()` and `setup_telemetry()`.
- Shared contract: `shared/shared-contracts/observability-conventions.md` — documents the two-surface model (`/metrics` pull + OTel push), metric naming, cardinality rules, OTel switch semantics, structured logging levels, OTLP log bridge behavior, and request-correlation bridging.

Services observed following this pattern include agent-platform, platform-gateway, audit-service, execution-runtime, identity-broker, incident-service, skills-hub, and tool-gateway.

## Architecture and conventions

1. **Root logger configuration** — Each service calls `configure_logging()` at startup. It reads `LOG_LEVEL` (default `INFO`) and applies it via `logging.basicConfig(level=level, force=True)`, overriding uvicorn's WARNING default so audit-level records are not silently dropped.
2. **Structured event emission** — Business and request events go through `log_event(LOGGER, "<event_name>", field=value, ...)`. The helper wraps fields in a dict with a top-level `event` key and serializes to JSON. This is the canonical way to emit audit-trail records such as `http_request`, `tool_invoked`, policy decisions, auth flows, etc.
3. **HTTP request logging** — Every service registers a FastAPI `@app.middleware("http")` that resolves `x-request-id`, measures duration, and emits an `http_request` event with `service`, `request_id`, `method`, `path`, `status_code`, `duration_ms`.
4. **OpenTelemetry log bridge** — When `OTEL_ENABLED=true`, `setup_telemetry` initializes TracerProvider, MeterProvider, and a LoggerProvider with a `BatchLogRecordProcessor` exporting via `OTLPSpanExporter`/`OTLPMetricExporter`/`OTLPLogExporter` to `OTEL_EXPORTER_OTLP_ENDPOINT`. The bridge adds an `opentelemetry.instrumentation.logging.LoggingHandler` to the root logger so every `log_event` call is also exported as an OTLP log record. `opentelemetry` loggers are detached (`propagate = False`) to prevent recursion on exporter failure.
5. **Request correlation** — `x-request-id` is the log- and portal-facing correlation key. When tracing is active, it is set to the active span's W3C `trace_id`; otherwise a generated `req-<uuid4>` is used. `traceparent` (W3C Trace Context) is propagated automatically by OTel instrumentation across service hops.
6. **Fail-open design** — OTel initialization is wrapped in try/except; failures are logged and do not break requests. Missing/misconfigured backends produce export-time drops without affecting the service.
7. **Two surfaces** — `/metrics` (Prometheus pull, always on) and OTLP push (opt-in) are deliberately decoupled; disabling OTel leaves metrics unaffected.

## Conventions and constraints

- All business/request events must be emitted as single-line JSON via `log_event(...)` at `INFO` level. The observability conventions explicitly state these records form the audit trail and must not be discarded.
- Root logger level must stay at least `INFO` per deployment unless overridden via `LOG_LEVEL`; services raise it from uvicorn's WARNING default during startup.
- Event names are free-form strings passed as the second argument to `log_event`; callers choose descriptive names (e.g. `http_request`, `auth_login_started`, `tool_invoked`).
- Fields are passed as keyword arguments and serialized with `sort_keys=True` for stable output.
- No unbounded label values may be used in metrics (cardinality rule); while this is a metrics convention, it reflects the broader principle of bounded, structured observability data.
- Correlation IDs must never be silently dropped on inbound requests; `x-request-id` is preserved and forwarded on all outbound calls.
- OTel push is controlled exclusively by `OTEL_ENABLED`; there are no per-signal toggles for traces, metrics, or logs.
- Authentication to the OTLP backend uses `OTEL_EXPORTER_OTLP_HEADERS` (provisioned via runtime secrets, never committed); credentials are never placed in ConfigMaps.
- The JSON stdout stream remains the source of truth for audit tooling; the OTLP mirror exists only for trace correlation.