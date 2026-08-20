---
kind: logging_system
name: Structured JSON Audit Logging with OpenTelemetry Log Bridge
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/incident-service/src/incident_service/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/agent-platform/src/agent_service/core/observability.py
    - products/incident-service/src/incident_service/core/telemetry.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/incident-service/src/incident_service/core/request_context.py
---

## What system/approach is used

Every service in the repository uses Python's stdlib `logging` module to emit **single-line, structured JSON** audit events. There is no third-party logging framework (no structlog, loguru, or similar). Each product exposes an identical `core/observability.py` that provides:

- `configure_logging()` — raises the root logger from Uvicorn's default `WARNING` to `INFO` so audit records are not silently dropped; the effective level is read from the `LOG_LEVEL` environment variable and defaults to `INFO`.
- `log_event(logger, event, **fields)` — builds a dict `{"event": <event_name>, ...fields}`, serializes it with `json.dumps(..., default=str, sort_keys=True)`, and emits it at `INFO` level.

An opt-in OpenTelemetry push pipeline (`core/telemetry.py`) bridges the same stdout JSON lines into OTLP logs via `opentelemetry.instrumentation.logging.LoggingHandler`. When `OTEL_ENABLED=true`, every structured record is also exported over HTTP/protobuf to `OTEL_EXPORTER_OTLP_ENDPOINT` (OpenObserve), automatically enriched with W3C `trace_id`/`span_id` when emitted inside an active span. The bridge is fail-open: setup errors are logged and never raised into the request path.

## Key files and packages

- Per-service `src/<service>/core/observability.py` — logging configuration + `log_event` helper (identical across all services).
- Per-service `src/<service>/core/telemetry.py` — OTel traces/metrics/logs push, `current_trace_id()`, and the OTLP log bridge.
- Per-service `src/<service>/core/request_context.py` — resolves `x-request-id` by preferring the inbound header, then the active OTel trace id, then a generated `req-<uuid4>`.
- Shared contract: `shared/shared-contracts/observability-conventions.md` — documents the two-surface model, metric naming, cardinality rules, OTel switch semantics, structured logging levels, OTLP log bridge behavior, and correlation/trace bridging.
- Usage sites: routes and services call `log_event(LOGGER, "<domain_event>", request_id=..., ...)` to emit audit entries (e.g. `auth_login_url_requested`, `tool_invoked`, `policy_decision`, `http_request`).

## Architecture and conventions

1. **Two decoupled observability surfaces.** `/metrics` (Prometheus pull, always on) and OTLP push (opt-in via `OTEL_ENABLED`). Disabling OTel has zero overhead and does not affect `/metrics`.
2. **Audit trail = stdout JSON.** All business and request events are single-line JSON at INFO level. Container stdout is the source of truth for audit tooling; the OTLP mirror exists only for correlation with traces.
3. **Root logger must be raised to INFO.** Uvicorn starts at WARNING; every service calls `configure_logging(force=True)` at startup so audit records survive. `LOG_LEVEL` can override per deployment.
4. **Structured fields via keyword args.** Callers pass domain-specific key/value pairs to `log_event`; the helper serializes them as a flat JSON object with sorted keys.
5. **Request correlation.** `x-request-id` is the log- and portal-facing correlation key. It is forwarded on every outbound call. When tracing is active, `x-request-id` is set to the active span's W3C `trace_id` so a single value joins logs and APM traces. When tracing is off, it falls back to `req-<uuid4>`.
6. **OTLP log bridge.** When enabled, a `LoggingHandler` is attached to the root logger so every `logger.info(json.dumps(...))` call is mirrored as an OTLP log record. `opentelemetry` internal loggers are detached (`propagate = False`) to prevent recursion if the exporter fails.
7. **Fail-open telemetry.** Missing/invalid credentials or unreachable endpoints produce export-time drops; initialization failures are caught and logged rather than raised.
8. **Service identity.** Resource `service.name` comes from `OTEL_SERVICE_NAME` or the service's metadata name, enabling cross-service join on traces and logs.

## Conventions and constraints

- **Emit audit events through `log_event`, not raw `logger.info` calls.** This guarantees the `{"event": ..., ...}` schema and sorted-key JSON output required by downstream consumers.
- **Never use unbounded values as metric labels.** Raw URLs, user ids, session ids, and request ids are prohibited as labels (cardinality rule documented in `observability-conventions.md`).
- **Never drop an inbound `x-request-id`.** Every service must preserve or bridge it on outbound calls.
- **OTel push is disabled by default.** Only initialize providers when `OTEL_ENABLED` is truthy; otherwise there is no runtime cost.
- **Authentication headers for OTLP (`OTEL_EXPORTER_OTLP_HEADERS`) are provisioned as runtime secrets**, never committed to source control.
- **Structured logs stay at INFO level** because they form the audit trail; lowering `LOG_LEVEL` below INFO will discard audit records.