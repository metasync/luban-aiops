---
kind: logging_system
name: Structured JSON Logging with Opt-in OpenTelemetry Log Bridge
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/platform-gateway/src/platform_gateway/core/request_context.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/audit-service/src/audit_service/core/telemetry.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/identity-broker/src/identity_service/core/telemetry.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/incident-service/src/incident_service/core/telemetry.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/skills-hub/src/skills_hub/core/telemetry.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/telemetry.py
    - products/tool-gateway/src/tool_gateway/core/request_context.py
---

## What system/approach is used

Each service in the monorepo uses Python's standard `logging` module as its logging framework. Structured audit and business events are emitted as single-line JSON via a shared `log_event(logger, event, **fields)` helper that serializes `{"event": ..., **fields}` with sorted keys. The root logger level is raised from uvicorn's default `WARNING` to `INFO` at startup so these audit records are never silently discarded; the effective level is controlled by the `LOG_LEVEL` environment variable (default `INFO`).

When OpenTelemetry push is enabled (`OTEL_ENABLED=true`), every structured log record is mirrored into an OTLP log pipeline through an `opentelemetry.instrumentation.logging.LoggingHandler` attached to the root logger. This bridge exports logs over HTTP/protobuf to `OTEL_EXPORTER_OTLP_ENDPOINT` (OpenObserve) alongside traces and metrics, automatically associating each log record with the active span's W3C `trace_id`/`span_id`. The bridge is idempotent, guarded against recursion by detaching `opentelemetry`'s own loggers from the root logger, and fails open — setup errors are logged rather than raised.

The `/metrics` Prometheus surface (pull-based, always on) is decoupled from the OTel push pipeline (opt-in, zero overhead when disabled); disabling OTel has no effect on metrics.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — authoritative specification of the observability contract (SPEC-005): two surfaces, OTel switch semantics, structured logging levels, request correlation rules, and backend relationship.
- Per-service `core/observability.py` — defines `configure_logging()` (raises root logger to INFO, reads `LOG_LEVEL`) and `log_event(logger, event, **fields)` (single-line JSON emission).
- Per-service `core/telemetry.py` — identical opt-in OTel push pipeline: `is_enabled()`, `setup_telemetry(app, service_name)`, `_attach_log_bridge(resource)`, `current_trace_id()`; initializes TracerProvider, MeterProvider, FastAPI/HTTPX instrumentation, and the OTLP log bridge.
- Per-service `core/request_context.py` — resolves `x-request-id` per SPEC-005 R-4: inbound value wins, otherwise bridges to active OTel trace_id, else generates `req-<uuid4>`.
- Service entrypoints call `configure_logging()` during app startup and `setup_telemetry(app, metadata.service_name)` when tracing is desired.

## Architecture and conventions

1. **Two decoupled surfaces.** Every service exposes a pull-based `/metrics` endpoint (Prometheus, always on) and an opt-in OTel push pipeline for traces + metrics + logs. They never depend on each other.
2. **Audit trail = stdout JSON.** All business and request events (http_request, tool_invoked, policy decisions, auth outcomes) are emitted as INFO-level JSON lines on stdout. This is the source of truth; the OTLP mirror is secondary and exists only for correlation with traces.
3. **Structured fields via `log_event`.** Callers pass keyword arguments to `log_event`; the helper wraps them in `{"event": <name>, ...}` and emits a single line via `json.dumps(..., sort_keys=True)`. No ad-hoc string formatting for audit events.
4. **Log level strategy.** Root logger defaults to INFO (overriding uvicorn's WARNING). Override per deployment via `LOG_LEVEL`. The convention mandates INFO as the default so audit records are never dropped.
5. **Request correlation.** `x-request-id` is the log- and portal-facing correlation key. When tracing is active it is bridged to the OTel span's W3C `trace_id`; when inactive it falls back to `req-<uuid4>`. No service may silently drop an inbound correlation id.
6. **OTel push is opt-in and fail-open.** `OTEL_ENABLED` gates the entire pipeline (traces + metrics + logs). Missing or misconfigured backend produces export-time drops and setup-time warnings, never request failures.
7. **Resource tagging.** Each service sets `service.name` via `OTEL_SERVICE_NAME` (defaults to the service's metadata name) on the OTel Resource, used across traces/metrics/logs.
8. **No per-signal toggles.** One switch (`OTEL_ENABLED`) controls all three signals; there are no separate flags for traces vs metrics vs logs.

## Conventions and constraints

- **Emit audit events at INFO level via `log_event`**, not via raw `logger.info("...")` with formatted strings. (Enforced by the `observability-conventions.md` spec and the presence of the helper in every service.)
- **Call `configure_logging()` at app startup** to raise the root logger from uvicorn's WARNING to INFO. (Documented in each `core/observability.py` docstring.)
- **Never use unbounded values as metric labels** (raw URL, user id, session id, request id). (Cardinality rule in `observability-conventions.md`.)
- **Do not attach OTel providers until `OTEL_ENABLED` is true.** Providers are lazily imported inside `setup_telemetry` to avoid import overhead when disabled.
- **Detach `opentelemetry` loggers from the root logger** before attaching the bridge handler, preventing exporter failures from recursing back into the bridge. (Implemented in every service's `_attach_log_bridge`.)
- **Forward `x-request-id` on every outbound call** and preserve inbound values. (Constrained by the request-context helpers and the convention document.)
- **Authentication to the OTLP backend** is provided via `OTEL_EXPORTER_OTLP_HEADERS` (Basic auth for OpenObserve) provisioned from runtime secrets, never committed to source control.