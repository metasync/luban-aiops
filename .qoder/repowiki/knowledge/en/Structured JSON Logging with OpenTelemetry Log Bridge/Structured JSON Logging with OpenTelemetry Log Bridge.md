---
kind: logging_system
name: Structured JSON Logging with OpenTelemetry Log Bridge
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/tool-gateway/src/tool_gateway/core/telemetry.py
---

## What system/approach is used

Every service in the Luban platform uses Python's standard `logging` module to emit **single-line, structured JSON** audit records. There is no third-party logging framework (no structlog, loguru, or logzero). Each product ships an identical `core/observability.py` that exposes two functions:

- `configure_logging()` — raises the root logger from Uvicorn's default `WARNING` to `INFO` so audit events are not silently dropped; level is overridable via the `LOG_LEVEL` environment variable.
- `log_event(logger, event, **fields)` — serializes `{"event": event, ...fields}` as sorted JSON and emits it at `INFO` level.

Business and request events (HTTP requests, tool invocations, policy decisions, auth flows, session lifecycle) are emitted through this helper. Direct `logger.info(...)` calls are used only for non-audit operational messages.

An opt-in OpenTelemetry push pipeline (`core/telemetry.py`) bridges the same stdout JSON lines into OTLP logs when `OTEL_ENABLED=true`, attaching trace/span context automatically so logs can be correlated with traces in the backend (OpenObserve).

## Key files and packages

- Per-service `src/<service>/core/observability.py` — defines `configure_logging()` and `log_event()` (identical across all services: agent-platform, platform-gateway, tool-gateway, audit-service, incident-service, skills-hub, identity-broker).
- Per-service `src/<service>/core/telemetry.py` — implements the opt-in OTel push pipeline (`setup_telemetry`, `_attach_log_bridge`, `current_trace_id`, `is_enabled`).
- `shared/shared-contracts/observability-conventions.md` — the authoritative specification for logging levels, OTel switch semantics, correlation headers, and the relationship between stdout JSON and the OTLP mirror.
- Service entrypoints call `configure_logging()` during app startup (e.g. `agent_service/app.py`, `platform_gateway/app.py`, etc.) before any request handling.
- Call sites use `log_event(LOGGER, "<event_name>", ...)` throughout API routes and services (e.g. `identity_service/api/routes/auth.py`, `audit_service/services/retention.py`, `incident_service/api/routes/webhooks.py`).

## Architecture and conventions

1. **Two decoupled surfaces.** `/metrics` (Prometheus pull, always on) and OTLP push (opt-in via `OTEL_ENABLED`) never depend on each other. Disabling OTel leaves metrics and stdout logging fully functional.
2. **Audit trail = stdout JSON.** The single-line JSON records produced by `log_event` are the source of truth for auditing; the OTLP bridge is a mirror only.
3. **Structured fields via kwargs.** Every audit record carries an `event` field plus domain-specific key/value pairs passed as `**fields`; values are coerced to strings via `default=str` and keys are sorted for deterministic output.
4. **Log level strategy.** INFO is the default minimum for audit records because they form the audit trail; `LOG_LEVEL` may be raised per deployment but must stay at least INFO so audit records are never discarded.
5. **Request correlation.** `x-request-id` is the log- and portal-facing correlation key; when tracing is active it is set to the active span's W3C `trace_id`, otherwise falls back to `req-<uuid4>`. Outbound calls forward it automatically.
6. **Fail-open OTel bridge.** When OTel push is enabled, a `LoggingHandler` is attached to the root logger so every structured record is also exported as an OTLP log. The `opentelemetry` internal loggers are detached (`propagate = False`) to prevent recursion if the exporter fails.
7. **Service naming.** `OTEL_SERVICE_NAME` defaults to the service's metadata name and becomes the `service.name` resource attribute on all signals.
8. **No unbounded label cardinality.** While this applies primarily to metrics, the convention extends to logs: avoid high-cardinality fields like raw URLs, user IDs, session IDs, or request IDs in labels; use bounded enums instead.

## Conventions and constraints

- **All business/request events go through `log_event` at INFO level.** This is enforced by the observability conventions document (SPEC-005) and reflected in every service's `observability.py`.
- **Root logger must be raised to INFO at startup** via `configure_logging()` so Uvicorn's WARNING default does not drop audit records.
- **OTel push is off by default**, gated by `OTEL_ENABLED`; initialization errors are logged and swallowed so they cannot break request processing.
- **Authentication for OTLP export** is provided via `OTEL_EXPORTER_OTLP_HEADERS` from runtime secrets (never committed); credentials are provisioned by `sync-otel-secrets.sh`.
- **Trace/log correlation**: records emitted inside an active span automatically carry `trace_id`/`span_id`, joining them to the APM view on the same W3C ID that backs `x-request-id`.
- **No service may silently drop an inbound correlation id** (`x-request-id` / `traceparent`).
- **Metrics naming** follows `<service>_<noun>_<unit>` snake_case with `_total` suffix on counters and bounded enum labels only.