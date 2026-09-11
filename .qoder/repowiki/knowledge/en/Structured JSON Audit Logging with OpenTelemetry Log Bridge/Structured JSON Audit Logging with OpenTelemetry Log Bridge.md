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
    - products/agent-platform/src/agent_service/app.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/audit-service/src/audit_service/core/telemetry.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/identity-broker/src/identity_service/core/telemetry.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/incident-service/src/incident_service/core/telemetry.py
---

## What system/approach is used

The platform uses Python's standard `logging` module as the sole logging framework. Each product service ships its own `core/observability.py` that exposes two functions: `configure_logging()` and `log_event(logger, event, **fields)`. There is no third-party structured-logging library (no structlog, loguru, or similar). All business and request events are emitted as single-line JSON via `json.dumps(..., sort_keys=True)` at INFO level, forming the platform's audit trail.

OpenTelemetry is layered on top as an opt-in push pipeline (`OTEL_ENABLED`). When enabled, a `LoggingHandler` is attached to the root logger so every structured record is mirrored over OTLP HTTP/protobuf to the configured backend (OpenObserve), automatically associating logs with active spans via W3C trace context.

## Key files and packages

- Per-service observability modules:
  - `products/agent-platform/src/agent_service/core/observability.py`
  - `products/platform-gateway/src/platform_gateway/core/observability.py`
  - `products/audit-service/src/audit_service/core/observability.py`
  - `products/identity-broker/src/identity_service/core/observability.py`
  - `products/incident-service/src/incident_service/core/observability.py`
  - `products/skills-hub/src/skills_hub/core/observability.py`
  - `products/tool-gateway/src/tool_gateway/core/observability.py`
  - `products/execution-runtime/src/execution_runtime/core/observability.py`
- Per-service telemetry modules (OTel bridge):
  - `products/*/src/*_service/core/telemetry.py` (identical implementation across services)
- Cross-cutting convention doc:
  - `shared/shared-contracts/observability-conventions.md`
- App entry points that wire everything together:
  - `products/*/src/*_service/app.py` — each calls `configure_logging()` at startup, registers an HTTP middleware that emits `http_request` events via `log_event`, and calls `setup_telemetry(app, SERVICE_NAME)`.

## Architecture and conventions

### Startup wiring
Every service follows the same pattern in its `app.create_app()`: call `configure_logging()` before any request handling, then register an HTTP middleware that emits an `http_request` structured event per incoming request, then call `setup_metrics(app)` and `setup_telemetry(app, SERVICE_NAME)`. This ensures the root logger is raised from uvicorn's default WARNING to INFO before any code runs.

### Structured log format
`log_event(logger, event, **fields)` builds a dict `{"event": event, **fields}` and writes it via `logger.info(json.dumps(payload, default=str, sort_keys=True))`. The first field is always `event`, followed by whatever domain fields the caller supplies (e.g. `service`, `request_id`, `method`, `path`, `status_code`, `duration_ms` for `http_request`; `tool_invoked`, `policy_decision`, etc. elsewhere). Because `sort_keys=True`, the output is deterministic and parseable as a single JSON line.

### Log levels
- Business/request events (the audit trail) are emitted at **INFO** via `log_event`. The root logger is explicitly raised to INFO at startup because uvicorn defaults to WARNING, which would silently drop these records.
- The effective level can be overridden per deployment via the `LOG_LEVEL` environment variable; the default must stay INFO so audit records are never discarded.
- Internal diagnostics use `LOGGER.exception(...)` when setup fails (e.g. OTel initialization errors).

### OpenTelemetry log bridge
When `OTEL_ENABLED=true`, `setup_telemetry` attaches an OTel `LoggingHandler` to the root logger with `level=logging.INFO`. This mirrors every structured log record into the OTLP log pipeline alongside traces and metrics. The bridge has three safeguards:
1. `opentelemetry` internal loggers are set to `propagate = False` so exporter failures cannot recurse back through the bridge.
2. Initialization is wrapped in try/except and logged rather than raised — fail-open.
3. The bridge is gated by the same `OTEL_ENABLED` flag; when disabled, no OTel providers are initialized and there is zero overhead.

### Request correlation
- `x-request-id` is the log- and portal-facing correlation key, generated if absent and forwarded on outbound calls.
- `traceparent` (W3C Trace Context) is propagated automatically by OpenTelemetry instrumentation.
- When tracing is active, `x-request-id` is set to the active span's W3C `trace_id` (32 hex chars); when inactive, it falls back to `req-<uuid4>`.
- `current_trace_id()` in `telemetry.py` exposes the active trace id for callers that need to embed it in structured logs.

### Two decoupled surfaces
Per `observability-conventions.md`, each service exposes:
1. `/metrics` (pull, always on) — Prometheus endpoint implemented directly with `prometheus_client`.
2. OpenTelemetry push (opt-in) — traces, metrics, and mirrored logs pushed via OTLP HTTP/protobuf.
The two surfaces never depend on each other; disabling OTel leaves `/metrics` fully functional.

## Conventions and constraints

- **Every service must call `configure_logging()` at app startup.** Enforced by the convention documented in each `core/observability.py` docstring and the shared `observability-conventions.md`, which states that failing to do so causes uvicorn's WARNING-level root logger to discard all `log_event` audit records.
- **All audit events go through `log_event(...)`.** Business and request events are required to be single-line JSON via this helper so they remain parseable and consistent across services.
- **Never label high-cardinality values on metrics.** While this is a metrics rule, it reflects the broader cardinality discipline applied to all observability signals.
- **OTel push is off by default.** Controlled by `OTEL_ENABLED`; when false, no OTel providers or instrumentation are initialized. Authentication uses `OTEL_EXPORTER_OTLP_HEADERS` provisioned via runtime secrets, never committed.
- **JSON stdout remains the source of truth.** The OTLP mirror exists only for correlation with traces; tooling must keep reading stdout, not rely solely on the OTLP export.
- **No service may silently drop an inbound correlation id.** `x-request-id` must be preserved and forwarded on every outbound call.
- **Fail-open behavior:** Any OTel setup error is caught, logged, and does not break the request path.