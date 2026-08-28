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
    - products/platform-gateway/src/platform_gateway/core/request_context.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/telemetry.py
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
---

## What system/approach is used

The platform uses Python's stdlib `logging` module as the sole logging framework. Every product service (agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway) ships an identical `core/observability.py` that provides two helpers: `configure_logging()` and `log_event(logger, event, **fields)`. Structured logs are single-line JSON objects emitted at INFO level via `logger.info(json.dumps(payload, default=str, sort_keys=True))`, where each record carries a top-level `event` field plus arbitrary domain fields.

OpenTelemetry is layered on top as an opt-in push pipeline. When `OTEL_ENABLED=true`, each service attaches an OTel `LoggingHandler` to the root logger so every structured log record is mirrored over OTLP HTTP/protobuf to the configured backend (OpenObserve). The bridge is gated by the same switch, fails open, and detaches `opentelemetry`'s own loggers from the root logger to prevent recursion.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — the authoritative spec for all services; defines the two surfaces (`/metrics` pull + OTel push), environment variables, cardinality rules, structured logging levels, request correlation, and the OTLP log bridge contract.
- Per-service `src/<service>/core/observability.py` — identical `configure_logging()` / `log_event()` helpers that raise the root logger from uvicorn's WARNING default to INFO and emit JSON lines.
- Per-service `src/<service>/core/telemetry.py` — opt-in OTel setup (`setup_telemetry(app, service_name)`), `current_trace_id()`, and `_attach_log_bridge(resource)` which installs the OTLP log bridge.
- Per-service `src/<service>/core/request_context.py` — resolves `x-request-id` per SPEC-005 R-4: inbound value wins, otherwise bridges to active OTel trace_id, else falls back to `req-<uuid4>`.
- Service entrypoints (`app.py`) call `configure_logging()` at startup and use `log_event(...)` for business events (e.g. http_request, tool_invoked, policy decisions).

## Architecture and conventions

1. **Two decoupled observability surfaces**:
   - `/metrics` (Prometheus pull, always on) — independent of OTel.
   - OTel push (opt-in via `OTEL_ENABLED`) — traces, metrics, and mirrored logs pushed via OTLP HTTP/protobuf to `OTEL_EXPORTER_OTLP_ENDPOINT`.

2. **Structured log format**: every business/event log is a single JSON line produced by `log_event(logger, "<event_name>", field=value, ...)`. Fields are serialized with `default=str` and keys sorted. There is no custom formatter — stdout is the source of truth for the audit trail.

3. **Log level strategy**: root logger is raised to INFO at startup because uvicorn defaults to WARNING, which would silently discard audit records. `LOG_LEVEL` overrides this per deployment. Business events must stay at INFO.

4. **Request correlation**: `x-request-id` is the log- and portal-facing correlation key. When tracing is active it is bridged to the active W3C `traceparent` span id; when inactive it falls back to `req-<uuid4>`. No service may silently drop an inbound correlation id.

5. **Cardinality rules**: labels and log fields must not include unbounded values (raw URL, user id, session id, request id). Domain counters use bounded enum labels only.

6. **Environment-driven configuration**:
   - `LOG_LEVEL` — root logger level override.
   - `OTEL_ENABLED` — master gate for traces/metrics/logs push (default false).
   - `OTEL_EXPORTER_OTLP_ENDPOINT` — OTLP HTTP base URL.
   - `OTEL_EXPORTER_OTLP_HEADERS` — Basic-auth headers provisioned via runtime secrets.
   - `OTEL_SERVICE_NAME` — resource service name, defaults to service metadata.

7. **Fail-open design**: OTel initialization errors are caught and logged; missing/invalid credentials produce export-time 401s dropped by batch processors. Setup failures never break the request path.

## Conventions and constraints

- All services must import and call `configure_logging()` in their app startup to ensure INFO-level structured events survive uvicorn's default WARNING threshold.
- Business and request events must be emitted through `log_event(logger, ...)` rather than direct `logger.info(...)` calls, so they consistently produce the required JSON shape with an `event` field.
- The OTLP log bridge is purely a mirror; container stdout remains the canonical audit stream. Downstream tooling must keep reading stdout, not the OTLP sink.
- Trace/span association is automatic via the OTel `LoggingHandler`; records emitted inside an active span carry `trace_id`/`span_id`, joining them to the trace view on the same W3C id.
- Metrics naming follows `<service>_<noun>_<unit>` snake_case with `_total` suffix on counters, prefixed by short service names (`gateway`, `identity`, `agent`, etc.).
- High-cardinality label values are prohibited and rejected at review.
- The `request_context.resolve_request_id` function enforces the bridging rule between `x-request-id` and OTel trace context across all services.