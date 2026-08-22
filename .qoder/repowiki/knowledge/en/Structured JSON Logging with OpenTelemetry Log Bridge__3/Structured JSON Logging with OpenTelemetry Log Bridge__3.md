---
kind: logging_system
name: Structured JSON Logging with OpenTelemetry Log Bridge
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/audit-service/src/audit_service/core/telemetry.py
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
---

## What system/approach is used

The platform uses Python's stdlib `logging` module as the sole logging framework. Every service emits **single-line, sorted-key JSON** records via a shared `log_event(logger, event, **fields)` helper in each service's `core/observability.py`. There is no third-party structured-logging library (no structlog, loguru, or similar). Logs are written to stdout by default; an opt-in OpenTelemetry push pipeline mirrors those same records over OTLP HTTP/protobuf to the organization's OpenObserve backend when `OTEL_ENABLED=true`.

## Key files and packages

- Per-service `core/observability.py` — defines `configure_logging()` and `log_event()`. Identical implementations across services: `platform-gateway`, `audit-service`, `agent-platform`, `identity-broker`, `incident-service`, `skills-hub`, `tool-gateway`.
- Per-service `core/telemetry.py` — implements the opt-in OTel push pipeline (`setup_telemetry`, `_attach_log_bridge`, `current_trace_id`).
- `shared/shared-contracts/observability-conventions.md` — the authoritative specification that all services follow for metrics, tracing, logging, and correlation.
- Service entrypoints (`app.py`) call `configure_logging()` at startup and emit `http_request` events through a FastAPI middleware.

## Architecture and conventions

### Initialization
Each service's `create_app()` calls `configure_logging()` before any request handling. This raises the root logger from Uvicorn's default `WARNING` level to `INFO` so audit-level records are not silently discarded. The effective level is read from the `LOG_LEVEL` environment variable (uppercased, defaults to `INFO`).

### Structured log format
Business and request events are emitted as:
```python
log_event(LOGGER, "event_name", field_a=value_a, field_b=value_b)
```
which serializes to a single JSON line with keys sorted alphabetically and values coerced to strings via `default=str`. The first positional argument after the logger is always an `event` string identifying the event type (e.g. `http_request`, `auth_login_url_requested`, `ingest_accepted`, `policy_decision`).

### Audit trail contract
Per `observability-conventions.md`, every business and request event is an INFO-level JSON record that constitutes the audit trail. Services must never drop these records; `configure_logging()` enforces this by raising the root level explicitly.

### Request correlation
- `x-request-id` is the log- and portal-facing correlation key, generated if absent and forwarded on outbound calls.
- When OTel tracing is active, `x-request-id` is bridged to the active span's W3C `trace_id`; otherwise it falls back to `req-<uuid4>`.
- `traceparent` (W3C Trace Context) is propagated automatically by OTel instrumentation.

### OpenTelemetry log bridge
When `OTEL_ENABLED=true`, `setup_telemetry` attaches an OTel `LoggingHandler` to the root logger. This bridges every structured log record to the OTLP log pipeline while keeping stdout JSON as the source of truth. The bridge includes trace/span context automatically and detaches `opentelemetry` internal loggers to prevent recursion. Setup failures are logged and swallowed — the pipeline is fail-open.

### Metrics surface (separate from logs)
Each service also exposes a `/metrics` endpoint using `prometheus_client` (with a minimal RED middleware), independent of the OTel push pipeline. Metric naming follows `<service>_<noun>_<unit>` snake_case with bounded labels only.

## Conventions and constraints

1. **Always call `configure_logging()` at app startup** — documented in every service's `observability.py` docstring and enforced by tests that assert the root logger level after configuration.
2. **Use `log_event(...)` for all business/request events** — raw `logger.info("...")` calls are avoided for audit-trail events; they should go through the helper to guarantee JSON structure and sorted keys.
3. **Log level is controlled by `LOG_LEVEL`** — defaults to `INFO`; can be overridden per deployment but must stay at least `INFO` for audit records.
4. **OTel push is off by default** — gated by `OTEL_ENABLED`; when disabled, no OTel providers are initialized and there is zero overhead.
5. **OTLP endpoint and auth via env vars** — `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_SERVICE_NAME`; secrets are provisioned into runtime-secrets Secrets, never committed.
6. **Never label high-cardinality values** — raw URLs, user IDs, session IDs, request IDs are prohibited as metric labels (convention enforced at review).
7. **No silent dropping of correlation IDs** — inbound `x-request-id` must be preserved and forwarded.
8. **Fail-open telemetry** — OTel setup exceptions are caught and logged; missing/misconfigured backends must never break requests.