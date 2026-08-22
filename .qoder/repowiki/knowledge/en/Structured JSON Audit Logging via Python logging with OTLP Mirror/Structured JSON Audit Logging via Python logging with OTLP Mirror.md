---
kind: logging_system
name: Structured JSON Audit Logging via Python logging with OTLP Mirror
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/audit-service/src/audit_service/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/agent-platform/src/agent_service/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/audit-service/src/audit_service/app.py
---

## What system/approach is used

Every product service in the monorepo uses the **Python standard library `logging`** module — no third-party logging framework (no structlog, loguru, or logzero). Each service ships an identical `core/observability.py` that provides two functions:

- `configure_logging()` — raises the root logger from Uvicorn's default `WARNING` to `INFO` so structured audit records are not silently dropped. The effective level is read from the `LOG_LEVEL` environment variable (default `INFO`).
- `log_event(logger, event, **fields)` — emits a single-line JSON record at `INFO` level: `{"event": <name>, ...fields}` serialized with `json.dumps(..., default=str, sort_keys=True)`.

An opt-in OpenTelemetry push pipeline (`core/telemetry.py`) mirrors every structured log line into OTLP logs when `OTEL_ENABLED=true`. It attaches an OTel `LoggingHandler` to the root logger and detaches `opentelemetry.*` loggers to prevent recursion. The OTLP mirror is explicitly documented as a *correlation aid* — stdout JSON remains the source of truth for audit tooling.

## Key files and packages

- Per-service observability modules (identical shape across all services):
  - `products/agent-platform/src/agent_service/core/observability.py`
  - `products/audit-service/src/audit_service/core/observability.py`
  - `products/platform-gateway/src/platform_gateway/core/observability.py`
  - `products/tool-gateway/src/tool_gateway/core/observability.py`
  - `products/incident-service/src/incident_service/core/observability.py`
  - `products/skills-hub/src/skills_hub/core/observability.py`
  - `products/identity-broker/src/identity_service/core/observability.py`
- Per-service telemetry modules that gate OTel push:
  - `products/agent-platform/src/agent_service/core/telemetry.py`
  - `products/audit-service/src/audit_service/core/telemetry.py`
  - `products/platform-gateway/src/platform_gateway/core/telemetry.py`
  - `products/tool-gateway/src/tool_gateway/core/telemetry.py`
  - `products/incident-service/src/incident_service/core/telemetry.py`
  - `products/skills-hub/src/skills_hub/core/telemetry.py`
  - `products/identity-broker/src/identity_service/core/telemetry.py`
- Service entry points that call `configure_logging()` during app creation (e.g. `app.py` in each service) and emit HTTP request events via `log_event` in an HTTP middleware.
- Authoritative convention doc: `shared/shared-contracts/observability-conventions.md`.

## Architecture and conventions

1. **Per-service isolation.** There is no shared logging package; each service duplicates the same `core/observability.py` pattern. This keeps services independent but ensures uniform behavior.
2. **Startup wiring.** Every service's `create_app()` calls `configure_logging()` before creating the FastAPI instance, then installs an HTTP middleware that emits `http_request` events via `log_event`, capturing `service`, `request_id`, `method`, `path`, `status_code`, and `duration_ms`.
3. **Structured fields, not positional args.** Business events are emitted through `log_event(LOGGER, "<event_name>", field=value, ...)`. The helper wraps them in `{"event": ..., **fields}` and serializes to JSON. Fields like `service`, `request_id`, `user_id`, `session_id`, `tool`, `decision` appear consistently across services.
4. **Log levels.** INFO is the audit baseline (HTTP requests, auth flows, policy decisions, tool invocations). DEBUG/TRACE usage is not observed in the codebase; the only documented override is `LOG_LEVEL`.
5. **Request correlation.** `x-request-id` is resolved per request (generated if absent) and included in every `log_event`. When OTel tracing is active, `x-request-id` is bridged to the W3C `traceparent` trace id so logs and traces share a single identifier.
6. **OTLP mirror.** When `OTEL_ENABLED=true`, the root logger gets an OTel `LoggingHandler` that exports the same JSON records over OTLP HTTP/protobuf to `OTEL_EXPORTER_OTLP_ENDPOINT`. The bridge is fail-open: setup errors are logged and never raised into the request path.
7. **Metrics surface is separate.** `/metrics` (Prometheus pull) lives in `core/metrics.py` and is intentionally decoupled from logging/tracing per the observability conventions.

## Conventions and constraints

- **Audit records must be INFO-level JSON.** The observability conventions state: "All business and request events are emitted as single-line JSON via `log_event(...)` at INFO level." Services raise the root logger from WARNING to INFO at startup so these records survive.
- **`LOG_LEVEL` overrides the default.** `configure_logging()` reads `LOG_LEVEL` (uppercased) and applies it via `logging.basicConfig(level=..., force=True)`; the default must stay `INFO` so audit records are never silently discarded.
- **Never use unbounded label values in metrics** (related observability rule from the same convention doc); this constrains how high-cardinality data may be correlated outside logs.
- **OTel push is off by default.** Controlled solely by `OTEL_ENABLED`; when false, no providers or instrumentation are initialized and `/metrics` remains unaffected.
- **Stdout JSON is the source of truth.** The OTLP log bridge exists only to correlate logs with traces; audit tooling must keep reading container stdout.
- **No service may silently drop an inbound correlation id.** `x-request-id` must be preserved and forwarded on every outbound call.
- **Fail-open guarantee.** Missing/invalid OTel credentials produce export-time 401s that batch processors drop; service setup additionally guards initialization and logs rather than raising exceptions.