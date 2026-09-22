---
kind: logging_system
name: Structured JSON Logging with OTLP Mirror and Per-Service Observability Modules
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/agent-platform/src/agent_service/app.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/audit-service/src/audit_service/app.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/execution-runtime/src/execution_runtime/app.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/identity-broker/src/identity_service/app.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/incident-service/src/incident_service/app.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/skills-hub/src/skills_hub/app.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/tool-gateway/src/tool_gateway/app.py
---

## What system/approach is used

The platform uses Python's standard `logging` module as the sole logging framework. Every product service ships its own small `core/observability.py` that exposes two functions — `configure_logging()` and `log_event(logger, event, **fields)` — and a `core/telemetry.py` that optionally bridges structured logs into OpenTelemetry via an OTLP HTTP exporter. There is no third-party logger library (no structlog, loguru, or logzero); all structured output is produced by serializing a dict to JSON on a single line.

Structured records are emitted at INFO level and written to stdout as one JSON object per line. An opt-in OpenTelemetry pipeline (`OTEL_ENABLED`) attaches an OTel `LoggingHandler` to the root logger so every record is also exported over OTLP HTTP/protobuf to the configured backend (OpenObserve in this organization). The OTLP mirror never replaces stdout; container logs remain the source of truth for audit tooling.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — repository-wide specification defining the two-surface observability model, metric naming, cardinality rules, OTel switch semantics, structured logging levels, OTLP log bridge behavior, and request-correlation conventions.
- Per-service `core/observability.py` (identical implementation across services): raises the root logger from uvicorn's WARNING default to INFO (overridable via `LOG_LEVEL`) and defines `log_event`, which builds `{"event": ..., **fields}` and emits it via `json.dumps(..., sort_keys=True)` at INFO.
- Per-service `core/telemetry.py`: implements `setup_telemetry(app, service_name)`, `is_enabled()`, and `current_trace_id()`. When `OTEL_ENABLED` is true it initializes TracerProvider, MeterProvider, FastAPI + HTTPX instrumentation, and attaches an OTLP log bridge via `opentelemetry.instrumentation.logging.handler.LoggingHandler`.
- Each service's `app.py` calls `configure_logging()` during app creation, installs an HTTP middleware that emits an `http_request` event via `log_event`, calls `setup_metrics(app)`, then calls `setup_telemetry(app, SERVICE_NAME)`.

Services following this pattern include agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, and tool-gateway.

## Architecture and conventions

### Two decoupled surfaces
Every service exposes:
1. `/metrics` — Prometheus pull endpoint implemented directly with `prometheus_client`; always on.
2. OpenTelemetry push — opt-in, gated by `OTEL_ENABLED`; when disabled nothing is initialized and `/metrics` is unaffected.

### Structured log format
Business and request events are single-line JSON objects with a required `event` field plus domain-specific fields. Example from the HTTP middleware: `{"event": "http_request", "service": "...", "request_id": "...", "method": "...", "path": "...", "status_code": ..., "duration_ms": ...}`. Fields are sorted keys and stringified via `default=str` to keep serialization safe.

### Log levels
- Default root level is INFO (raised from uvicorn's WARNING) so audit records are never silently discarded.
- Level can be overridden per deployment via `LOG_LEVEL`.
- All business/audit events use INFO; internal debug noise stays at lower levels.

### Request correlation
- `x-request-id` is the log- and portal-facing correlation key. It is generated if absent and forwarded on every outbound call.
- When tracing is active, `x-request-id` is set to the active span's W3C `trace_id` (via `current_trace_id()`), joining structured logs and APM traces on the same ID.
- When tracing is inactive, `x-request-id` falls back to a generated `req-<uuid4>`.
- No service may silently drop an inbound correlation id.

### OTLP log bridge
When enabled, the bridge:
- Attaches an OTel `LoggingHandler` to the root logger at INFO level.
- Automatically associates records with the active trace/span via `trace_id`/`span_id`.
- Detaches `opentelemetry` loggers from the root logger to prevent recursion.
- Is gated by the same `OTEL_ENABLED` flag and fails open (exceptions are logged, not raised).

### Environment variables
- `LOG_LEVEL` — overrides the root logger level (default INFO).
- `OTEL_ENABLED` — master gate for traces + metrics + log mirror (default false).
- `OTEL_EXPORTER_OTLP_ENDPOINT` — OTLP HTTP base URL (exporters append `/v1/{traces,metrics,logs}`).
- `OTEL_EXPORTER_OTLP_HEADERS` — Basic auth headers provisioned via runtime secrets.
- `OTEL_SERVICE_NAME` — resource service name (defaults to service metadata).

### Fail-open guarantee
Missing or invalid OTel credentials produce 401s at export time; batch processors drop telemetry on failure and setup additionally guards initialization and logs rather than raising. An unreachable backend must never break a request.

## Conventions and constraints

Observed conventions enforced by the code and documented in `observability-conventions.md`:
- Every service's `create_app()` calls `configure_logging()` before any request handling.
- Every service's `create_app()` installs an HTTP middleware that emits an `http_request` event via `log_event` with `service`, `request_id`, `method`, `path`, `status_code`, and `duration_ms`.
- Business events are emitted through `log_event(logger, "<event_name>", **fields)` rather than direct `logger.info(json.dumps(...))` calls.
- Metrics use `<service>_<noun>_<unit>` snake_case naming with `_total` suffix on counters and bounded enum labels only.
- High-cardinality values (raw URLs, user ids, session ids, request ids) are never used as metric labels.
- The OTLP log bridge is opt-in and never replaces stdout; audit tooling must keep reading container logs.
- `x-request-id` must never be silently dropped on inbound requests.