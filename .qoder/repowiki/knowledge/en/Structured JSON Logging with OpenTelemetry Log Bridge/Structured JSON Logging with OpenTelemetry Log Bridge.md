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
    - products/agent-platform/src/agent_service/app.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
---

## What system/approach is used

The platform uses Python's standard `logging` module as the sole logging framework. Each product service (agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway) ships an identical `core/observability.py` that exposes two functions: `configure_logging()` and `log_event(logger, event, **fields)`. Structured logs are emitted as single-line JSON via `json.dumps(..., sort_keys=True)` at INFO level, forming the platform's audit trail.

An opt-in OpenTelemetry push pipeline (`core/telemetry.py`) bridges the root logger to OTLP HTTP/protobuf when `OTEL_ENABLED=true`, exporting traces, metrics, and a mirror of every structured log record to the organization's OpenObserve backend. The bridge is attached by adding an OTel `LoggingHandler` to the root logger; OTel's own loggers are detached from the root logger to prevent recursion on exporter failures.

## Key files and packages

- Per-service `src/<service>/core/observability.py` — defines `configure_logging()` (reads `LOG_LEVEL`, calls `logging.basicConfig(level=..., force=True)`) and `log_event()` (serializes `{event, ...fields}` to JSON).
- Per-service `src/<service>/core/telemetry.py` — implements `setup_telemetry(app, service_name)`, `is_enabled()`, `_attach_log_bridge(resource)`, and `current_trace_id()`; gated by `OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_SERVICE_NAME`.
- Per-service `src/<service>/app.py` — calls `configure_logging()` before creating the FastAPI app, installs an HTTP middleware that emits `http_request` events via `log_event`, then calls `setup_metrics(app)` and `setup_telemetry(app, SERVICE_NAME)`.
- Shared contract `shared/shared-contracts/observability-conventions.md` — the authoritative specification for all observability behavior across services.

## Architecture and conventions

### Two decoupled surfaces
1. **stdout JSON lines** — the source-of-truth audit trail, always produced at INFO level.
2. **OpenTelemetry push** — opt-in (default off), pushes traces + metrics + mirrored logs over OTLP HTTP/protobuf to `OTEL_EXPORTER_OTLP_ENDPOINT`; fails open so misconfiguration never breaks requests.

### Log levels and initialization
- Uvicorn starts the root logger at WARNING; each service calls `configure_logging()` to raise it to INFO (overridable per deployment via `LOG_LEVEL`).
- Business and request events use `log_event(...)` at INFO level; they must not be silently discarded.

### Structured field shape
Every `log_event` call produces a flat JSON object with a required `event` string key plus domain-specific fields. Examples observed in the codebase include `http_request` (with `service`, `request_id`, `method`, `path`, `status_code`, `duration_ms`), `auth_login_url_requested`, `auth_login_started`, `identity_normalized`, `tool_invoked`, policy decisions, etc. Fields are serialized with `sort_keys=True` and `default=str` to guarantee stable, parseable output.

### Request correlation
- `x-request-id` is the log- and portal-facing correlation key, generated if absent and forwarded on every outbound call.
- When tracing is active, `x-request-id` is set to the active span's W3C `trace_id` (32 hex chars); otherwise it falls back to `req-<uuid4>`.
- `traceparent` (W3C Trace Context) is propagated automatically by OpenTelemetry instrumentation.
- No service may silently drop an inbound correlation id.

### OTLP log bridge semantics
When `OTEL_ENABLED=true`, the bridge attaches an OTel `LoggingHandler` to the root logger so every structured record is also exported as an OTLP log record. Trace/span association is automatic (records emitted inside an active span carry its `trace_id`/`span_id`). The bridge is gated by the same switch and fails open.

### Metric naming (related surface)
Metrics follow `<service>_<noun>_<unit>` snake_case with counters suffixed `_total`; bounded enum labels only (no raw URLs, user ids, session ids, or request ids as labels). Service prefixes are short names like `gateway`, `identity`, `agent`.

## Conventions and constraints

Observed conventions enforced by the shared spec and replicated across all services:
- Emit business/request events as single-line JSON via `log_event(...)` at INFO level — never ad-hoc `print` or unstructured strings.
- Call `configure_logging()` at app startup to override uvicorn's default WARNING level.
- Gate OTel push behind `OTEL_ENABLED`; when disabled, no providers or instrumentation are initialized (zero overhead).
- Exporters target `OTEL_EXPORTER_OTLP_ENDPOINT` with auth via `OTEL_EXPORTER_OTLP_HEADERS`; secrets are provisioned at runtime, never committed.
- Use `OTEL_SERVICE_NAME` (defaults to service metadata) for resource tagging.
- Never label metrics with high-cardinality values (raw URL, user id, session id, request id).
- Always propagate `x-request-id` and never drop it.
- The `/metrics` Prometheus endpoint is always-on and independent of OTel push.
- Audit tooling reads stdout JSON lines; the OTLP mirror exists only for trace correlation and must not replace stdout.