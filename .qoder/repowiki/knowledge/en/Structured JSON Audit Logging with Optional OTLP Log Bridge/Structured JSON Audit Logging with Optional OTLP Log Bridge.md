---
kind: logging_system
name: Structured JSON Audit Logging with Optional OTLP Log Bridge
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
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/identity-broker/src/identity_service/api/routes/auth.py
---

## What system/approach is used

The platform uses Python's stdlib `logging` module as the sole logging framework. Every service ships a tiny, identical `core/observability.py` that provides two functions:

- `configure_logging()` — raises the root logger from Uvicorn's default `WARNING` to `INFO` so structured audit records are never silently dropped; the level is read from the `LOG_LEVEL` environment variable.
- `log_event(logger, event, **fields)` — emits a single-line JSON string via `logger.info(json.dumps(payload, default=str, sort_keys=True))`, where `payload = {"event": event, **fields}`.

This pattern is replicated verbatim in every product service: `agent-platform`, `platform-gateway`, `audit-service`, `execution-runtime`, `identity-broker`, and `tool-gateway`. Business and request events (HTTP requests, tool invocations, policy decisions, auth flows) are emitted through this helper rather than calling `logging.Logger.info` directly with ad-hoc formatting.

An optional OpenTelemetry push pipeline (`core/telemetry.py`) mirrors every INFO-level record to an OTLP backend (OpenObserve) via `opentelemetry.instrumentation.logging.handler.LoggingHandler`. The bridge is gated by `OTEL_ENABLED`, fails open on setup errors, and explicitly detaches `opentelemetry` loggers from the root logger to prevent recursion.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — the authoritative specification for all services' observability behavior, including logging levels, OTel switch semantics, correlation headers, and cardinality rules.
- Per-service `src/<service>/core/observability.py` — the `configure_logging` / `log_event` pair (identical across services).
- Per-service `src/<service>/core/telemetry.py` — opt-in OTLP traces + metrics + mirrored logs, gated by `OTEL_ENABLED`.
- Per-service `app.py` entry points call `configure_logging()` at startup and use `log_event(...)` for lifecycle events (e.g., `http_request`, `otel telemetry enabled`).
- `products/*/tests/test_observability.py` and `test_telemetry.py` validate the logging configuration and OTel gating.

## Architecture and conventions

### Two decoupled surfaces
Per `observability-conventions.md`, each service exposes:
1. `/metrics` (pull, always on, Prometheus via `prometheus_client`).
2. OpenTelemetry push (opt-in, OTLP HTTP/protobuf to `OTEL_EXPORTER_OTLP_ENDPOINT`).
The two never depend on each other; disabling OTel leaves `/metrics` fully functional.

### Structured log format
All audit-relevant events are single-line JSON with a required `event` field plus arbitrary key-value fields. Keys are sorted, values coerced to strings. This makes stdout consumable by log collectors without parsing overhead.

### Log levels
- INFO is the default minimum level for audit records; Uvicorn's WARNING default is explicitly raised.
- `LOG_LEVEL` overrides per deployment (e.g. DEBUG for local dev).
- Non-audit internal diagnostics may use lower levels but must not rely on them being visible in production.

### Request correlation
- `x-request-id` is the log- and portal-facing correlation key; generated if absent and forwarded on every outbound call.
- When tracing is active, `x-request-id` is set to the active span's W3C `trace_id` (32 hex chars), joining logs and APM traces.
- When tracing is inactive, `x-request-id` falls back to `req-<uuid4>`.
- No service may silently drop an inbound correlation id.

### OTLP log bridge
When `OTEL_ENABLED=true`, a `LoggingHandler` is attached to the root logger so every `log_event` record is also exported as an OTLP log record. Trace/span association is automatic because records emitted inside an active span carry its `trace_id`/`span_id`. The bridge is a mirror — JSON stdout remains the source of truth for the audit trail.

### Fail-open guarantees
OTel initialization is wrapped in try/except; failures are logged via `LOGGER.exception(...)` and never raised into the request path. Missing/misconfigured credentials produce export-time 401s that batch processors drop.

## Conventions and constraints

- **Every service must call `configure_logging()` at app startup** before any request handling begins, so audit records are not filtered by Uvicorn's default WARNING level. (Enforced by convention in every `app.py`; tests assert the root logger level.)
- **Audit events must go through `log_event(...)`**, not raw `logging` calls, to guarantee consistent JSON shape and INFO severity.
- **Never label metrics or logs with unbounded values**: raw URLs, user IDs, session IDs, request IDs are prohibited as labels (cardinality rule in `observability-conventions.md`).
- **OTel push is off by default** (`OTEL_ENABLED=false`); enabling it requires explicit configuration of `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_EXPORTER_OTLP_HEADERS` (Basic-auth for OpenObserve). Secrets are provisioned via `sync-otel-secrets.sh` into runtime secrets, never committed.
- **Service name propagation**: `OTEL_SERVICE_NAME` defaults to the service's metadata name and is used as the OTel resource `service.name`.
- **No silent drops**: no service may drop an inbound correlation id; trace context (`traceparent`) is propagated automatically by OTel instrumentation across service hops.