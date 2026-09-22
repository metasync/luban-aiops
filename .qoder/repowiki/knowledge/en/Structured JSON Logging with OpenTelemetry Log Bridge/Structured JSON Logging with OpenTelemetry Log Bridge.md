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
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/agent-platform/src/agent_service/app.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/audit-service/src/audit_service/core/telemetry.py
    - products/audit-service/src/audit_service/app.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/telemetry.py
    - products/execution-runtime/src/execution_runtime/app.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/identity-broker/src/identity_service/core/telemetry.py
    - products/identity-broker/src/identity_service/app.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/incident-service/src/incident_service/core/telemetry.py
    - products/incident-service/src/incident_service/app.py
---

## What system/approach is used

The platform uses Python's standard `logging` module as the sole logging framework. Every product service emits **single-line JSON** structured log records through a per-service `core/observability.log_event()` helper, and optionally mirrors those records to an OpenTelemetry OTLP backend via a `LoggingHandler`. There is no third-party logger library (no structlog, loguru, or similar); all services follow the same pattern defined in `shared/shared-contracts/observability-conventions.md` (backed by SPEC-005).

Two surfaces are deliberately decoupled:
1. **JSON stdout** — the source of truth for audit tooling; always on.
2. **OpenTelemetry push** — opt-in traces + metrics + mirrored logs pushed over OTLP HTTP/protobuf to OpenObserve; gated by `OTEL_ENABLED`, fails open.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — authoritative spec defining levels, fields, correlation headers, OTel switch semantics, cardinality rules, and metric naming.
- Per-service `core/observability.py` (e.g. `products/platform-gateway/src/platform_gateway/core/observability.py`, `products/agent-platform/src/agent_service/core/observability.py`) — identical implementations that call `logging.basicConfig(level=LOG_LEVEL, force=True)` and expose `log_event(logger, event, **fields)` which dumps `{"event": ..., **fields}` as INFO-level JSON with sorted keys.
- Per-service `core/telemetry.py` (e.g. `products/platform-gateway/src/platform_gateway/core/telemetry.py`, `products/agent-platform/src/agent_service/core/telemetry.py`) — optional OTel pipeline: `setup_telemetry(app, service_name)` initializes TracerProvider, MeterProvider, FastAPI/HTTPX instrumentation, and attaches an OTLP `LoggingHandler` to the root logger when `OTEL_ENABLED` is true. `current_trace_id()` returns the active W3C trace id.
- Per-service `app.py` entrypoints — each calls `configure_logging()`, installs an HTTP middleware that emits `http_request` events via `log_event`, then calls `setup_metrics(app)` and `setup_telemetry(app, SERVICE_NAME)`. Examples: `products/platform-gateway/src/platform_gateway/app.py`, `products/audit-service/src/audit_service/app.py`, `products/execution-runtime/src/execution_runtime/app.py`, `products/identity-broker/src/identity_service/app.py`, `products/incident-service/src/incident_service/app.py`, `products/skills-hub/src/skills_hub/app.py`, `products/tool-gateway/src/tool_gateway/app.py`.

## Architecture and conventions

### Log level strategy
- Uvicorn starts the root logger at WARNING; every service calls `configure_logging()` at startup to raise it to INFO so audit records are never silently discarded.
- The effective level is read from `LOG_LEVEL` (default `INFO`); callers must use `logger.info(...)` via `log_event` for business/request events.
- DEBUG-level output is not part of the audit surface.

### Structured record shape
- All business and request events go through `log_event(logger, "<event-name>", **fields)`, producing one JSON line with an `event` key plus any additional fields.
- Common fields emitted by the HTTP middleware include `service`, `request_id`, `method`, `path`, `status_code`, `duration_ms`.
- Fields are serialized with `json.dumps(..., default=str, sort_keys=True)` so output is deterministic and parseable.

### Request correlation and trace bridging
- `x-request-id` is the log- and portal-facing correlation key; generated if absent and forwarded on outbound calls.
- When tracing is active (`OTEL_ENABLED=true`), `x-request-id` is set to the active span's W3C `trace_id`; otherwise it falls back to `req-<uuid4>`.
- `traceparent` (W3C Trace Context) is propagated automatically by OpenTelemetry instrumentation across service hops.
- The OTLP log bridge automatically attaches `trace_id`/`span_id` to log records emitted inside an active span, joining them to the trace view on the same W3C id.

### OTel push (opt-in)
- Controlled by `OTEL_ENABLED` (default false); when disabled, no providers are initialized and `/metrics` remains unaffected.
- Export endpoint: `OTEL_EXPORTER_OTLP_ENDPOINT` (e.g. OpenObserve router base URL); per-signal paths `/v1/traces`, `/v1/metrics`, `/v1/logs` are appended by exporters.
- Auth via `OTEL_EXPORTER_OTLP_HEADERS` (Basic auth for OpenObserve), provisioned at runtime via secrets — never committed.
- Service name via `OTEL_SERVICE_NAME`, defaults to the service's metadata name.
- Fail-open: setup errors are logged and swallowed; exporter failures drop telemetry without breaking requests.
- Recursion guard: `logging.getLogger("opentelemetry").propagate = False` prevents exporter failures from looping back through the bridge.

### Metrics (related observability surface)
- Each service exposes `/metrics` (pull, always on) using `prometheus_client` with a RED middleware; metric names follow `<service>_<noun>_<unit>` snake_case with `_total` suffix on counters.
- High-cardinality labels (raw URL, user id, session id, request id) are forbidden.

## Conventions and constraints

- **Every service must call `configure_logging()` before emitting audit events.** This is enforced by the convention that `app.py` entrypoints invoke it during app creation; the `observability-conventions.md` states the default must stay INFO so audit records are never silently discarded.
- **Business and request events must be emitted via `log_event` at INFO level.** The spec explicitly defines these records as the audit trail.
- **OTel push is off by default and must fail open.** `setup_telemetry` wraps initialization in try/except and logs rather than raising.
- **No service may silently drop an inbound correlation id.** The conventions mandate forwarding `x-request-id` on every outbound call.
- **Cardinality rule:** never label metrics on raw URLs, user ids, session ids, or request ids — only bounded enum labels are allowed.
- **JSON stdout is the source of truth.** The OTLP mirror exists solely for correlation with traces; audit tooling must keep reading stdout.