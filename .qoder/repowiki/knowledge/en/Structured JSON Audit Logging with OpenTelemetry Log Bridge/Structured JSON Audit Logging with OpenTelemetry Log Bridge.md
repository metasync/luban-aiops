---
kind: logging_system
name: Structured JSON Audit Logging with OpenTelemetry Log Bridge
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
---

## What system/approach is used

The platform uses Python's standard `logging` module as the sole logging framework. Every product service ships a local `core/observability.py` that exposes two functions: `configure_logging()` and `log_event(logger, event, **fields)`. Structured audit events are emitted as single-line JSON via `logger.info(json.dumps(payload, default=str, sort_keys=True))`, where the payload always contains an `event` field plus arbitrary domain fields. There is no third-party structured-logging library (no structlog, loguru, or python-json-logger); the JSON serialization happens inline in `log_event`.

An opt-in OpenTelemetry push pipeline mirrors every INFO-level record to OTLP HTTP/protobuf via `opentelemetry.instrumentation.logging.handler.LoggingHandler`. The bridge is attached by each service's `core/telemetry.py` when `OTEL_ENABLED=true`; it adds the same records to the OTLP logs stream so they can be correlated with traces on the backend (OpenObserve). The stdout JSON remains the source of truth — the OTLP mirror never replaces container logs.

## Key files and packages

- Per-service `core/observability.py` — defines `configure_logging()` and `log_event()`: `products/agent-platform/src/agent_service/core/observability.py`, `products/platform-gateway/src/platform_gateway/core/observability.py`, `products/audit-service/src/audit_service/core/observability.py`, `products/identity-broker/src/identity_service/core/observability.py`, `products/incident-service/src/incident_service/core/observability.py`, `products/tool-gateway/src/tool_gateway/core/observability.py`, `products/skills-hub/src/skills_hub/core/observability.py`.
- Per-service `core/telemetry.py` — initializes OTel providers and attaches the log bridge; called from each service's `app.py` after `configure_logging()`.
- Shared contract: `shared/shared-contracts/observability-conventions.md` — documents the logging conventions, level policy, OTel switch semantics, and request-correlation rules.
- Each service's `app.py` calls `configure_logging()` at startup and invokes `log_event(LOGGER, ...)` for business events (e.g. `http_request`, `tool_invoked`, `policy_decision`, `auth_login_started`).

## Architecture and conventions

1. **Root logger elevation.** Uvicorn starts with root logger at WARNING, which would silently drop all INFO audit records. Every service calls `configure_logging()` early in startup to set the root level to INFO (overridable per deployment via `LOG_LEVEL`; default must stay INFO).
2. **Single structured-event API.** Business code never calls `logger.info(...)` directly for audit events; it calls `log_event(LOGGER, "<event_name>", field=value, ...)`. This guarantees every audit record is a flat JSON object with a stable `event` discriminator.
3. **Audit trail = INFO-level JSON.** All request, tool-invocation, policy-decision, and auth events are emitted at INFO. DEBUG/INFO are reserved for operational noise; only INFO+ carries the audit trail.
4. **Opt-in OTLP mirror.** When `OTEL_ENABLED=true`, `setup_telemetry()` creates a `LoggerProvider` with a `BatchLogRecordProcessor(OTLPLogExporter())`, sets it as the global logger provider, detaches `opentelemetry` internal loggers from the root logger (to prevent recursion), and attaches a `LoggingHandler` at INFO level. Export failures are swallowed — setup is fail-open.
5. **Trace correlation.** When tracing is active, `x-request-id` is bridged to the W3C `traceparent` span id (see `request_context.py` in each service), so OTLP log records automatically carry `trace_id`/`span_id` and join with APM traces. When tracing is disabled, `x-request-id` falls back to a generated `req-<uuid4>`.
6. **Service isolation.** Each product owns its own `core/observability.py` and `core/telemetry.py`; there is no shared library package for logging. The convention is replicated identically across all seven services.

## Conventions and constraints

- **Level policy**: audit events are INFO; the root logger must be raised above WARNING at startup (`configure_logging()` enforces this). Level can be overridden via `LOG_LEVEL` per deployment.
- **Format**: one line per record, `json.dumps(payload, default=str, sort_keys=True)` — deterministic key order, stringified values.
- **Event naming**: the first positional argument to `log_event` is a short camelCase/descriptive event name (e.g. `http_request`, `tool_invoked`, `policy_decision`, `auth_login_started`, `auth_login_url_requested`).
- **No high-cardinality labels in metrics** (related observability rule): raw URLs, user ids, session ids, request ids must not become metric labels; this keeps `/metrics` safe while structured logs carry those identifiers freely.
- **OTel gate**: `OTEL_ENABLED` controls the entire push pipeline (traces + metrics + log mirror); there are no per-signal toggles. Default is off (zero overhead). Missing/misconfigured backend produces export-time drops, never request failures.
- **Correlation headers**: `x-request-id` is the log/portal-facing correlation key; `traceparent` (W3C Trace Context) is the machine-facing propagation header managed by OTel instrumentation. No service may silently drop an inbound correlation id.
- **Backends**: services expose `/metrics` (pull, always on) and push OTLP over HTTP/protobuf to `OTEL_EXPORTER_OTLP_ENDPOINT`; authentication via `OTEL_EXPORTER_OTLP_HEADERS` provisioned through runtime secrets. Storage, scraping, dashboards, and alerting are outside the service contract.