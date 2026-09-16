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
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/audit-service/src/audit_service/app.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/tool-gateway/src/tool_gateway/app.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/execution-runtime/src/execution_runtime/app.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/identity-broker/src/identity_service/app.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/incident-service/src/incident_service/app.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/skills-hub/src/skills_hub/app.py
---

## What system/approach is used

The platform uses Python's stdlib `logging` module as the sole logging framework, emitting single-line JSON records to stdout. There is no third-party logger library (no loguru, structlog, or python-json-logger). Each product service defines its own thin `core/observability.py` that exposes two functions — `configure_logging()` and `log_event(logger, event, **fields)` — which every service imports and calls at startup.

Structured logs are emitted via `log_event`, which serializes `{"event": <name>, ...fields}` through `json.dumps(..., default=str, sort_keys=True)` and writes them at INFO level. Business events include `http_request`, `tool_invoked`, policy decisions, session lifecycle, etc., with a stable set of fields such as `service`, `request_id`, `method`, `path`, `status_code`, `duration_ms`, plus domain-specific keys.

An opt-in OpenTelemetry push pipeline mirrors these same structured records over OTLP HTTP/protobuf to the configured backend (OpenObserve in this organization) via an attached `LoggingHandler`. The bridge is gated by `OTEL_ENABLED`; when disabled, nothing is initialized and there is zero overhead. The OTLP mirror never replaces stdout — stdout remains the source of truth for audit tooling.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — repository-wide specification defining the two observability surfaces (`/metrics` pull + OTLP push), metric naming, cardinality rules, request correlation, and structured logging conventions. This is the authoritative contract all services follow.
- `products/*/src/<service>/core/observability.py` — per-service copy of `configure_logging()` and `log_event()`. The agent-platform version is the canonical implementation; other services mirror it.
- `products/*/src/<service>/core/telemetry.py` — per-service `setup_telemetry(app, service_name)` that initializes TracerProvider, MeterProvider, FastAPI instrumentation, HTTPX client instrumentation, and attaches the OTLP log bridge when `OTEL_ENABLED` is true.
- `products/*/src/<service>/app.py` — each service's FastAPI factory calls `configure_logging()` before creating the app, installs an HTTP middleware that emits `log_event("http_request", ...)`, then calls `setup_metrics(app)` and `setup_telemetry(app, SERVICE_NAME)`.
- `products/*/src/<service>/metadata.py` — provides `SERVICE_NAME` used as `OTEL_SERVICE_NAME` resource attribute.

## Architecture and conventions

**Startup sequence (per service):**
1. Call `configure_logging()` — raises root logger from uvicorn's WARNING default to INFO so structured audit records are not silently discarded. Level can be overridden via `LOG_LEVEL` environment variable.
2. Create FastAPI app.
3. Register HTTP middleware that resolves `x-request-id` (via `resolve_request_id`) and emits an `http_request` event with `service`, `request_id`, `method`, `path`, `status_code`, `duration_ms`.
4. Include routers, call `setup_metrics(app)`.
5. Call `setup_telemetry(app, SERVICE_NAME)` — if `OTEL_ENABLED` is truthy, initializes trace/metric/log providers and attaches the OTLP log bridge; otherwise returns immediately.

**Structured log format:**
- Single-line JSON objects serialized with sorted keys and string coercion for non-serializable values.
- Every business event goes through `log_event`, never direct `LOGGER.info(...)` calls for audit-relevant data.
- Fields are flat key-value pairs; no nested structures beyond what `json.dumps` handles.

**Request correlation:**
- `x-request-id` is the log- and portal-facing correlation key. Generated if absent (preserving the portal contract) and forwarded on every outbound call.
- When tracing is active, `x-request-id` is set to the active span's W3C `trace_id` (32 hex chars); when inactive, falls back to `req-<uuid4>`.
- `traceparent` (W3C Trace Context) is propagated automatically by OpenTelemetry instrumentation across service hops.

**OTel log bridge behavior:**
- Attaches `opentelemetry.instrumentation.logging.handler.LoggingHandler` to the root logger at INFO level.
- Detaches `opentelemetry` internal loggers from propagation to prevent recursion.
- Uses `BatchLogRecordProcessor` for async export.
- Fails open: setup exceptions are logged and ignored; exporter failures drop telemetry without breaking requests.

**Environment variables:**
- `LOG_LEVEL` — overrides root logger level (default INFO).
- `OTEL_ENABLED` — master gate for traces + metrics + log mirror (defaults false).
- `OTEL_EXPORTER_OTLP_ENDPOINT` — OTLP HTTP base URL (e.g. `http://openobserve-router:5080/api/default`).
- `OTEL_EXPORTER_OTLP_HEADERS` — Basic auth header for OpenObserve ingest.
- `OTEL_SERVICE_NAME` — resource service name (defaults to metadata name).

## Conventions and constraints

- All business and request events must be emitted as single-line JSON via `log_event(...)` at INFO level — this is the audit trail and cannot be bypassed.
- `configure_logging()` must be called before any business code runs, so audit records survive uvicorn's default WARNING-level root logger.
- No unbounded label values may be used in metrics; similarly, avoid high-cardinality fields in logs (raw URLs, user ids, session ids) — documented in `observability-conventions.md`.
- The OTLP log bridge is purely additive; stdout JSON remains the authoritative sink. Audit tooling must keep reading stdout.
- `x-request-id` must never be silently dropped on inbound requests; it is generated if missing and forwarded on all outbound calls.
- OTel push is off by default and fail-open; misconfiguration must never break a request path.
- Each product service owns its own `core/observability.py` and `core/telemetry.py` copies rather than sharing a single package — the convention is uniform API surface but per-service implementation.