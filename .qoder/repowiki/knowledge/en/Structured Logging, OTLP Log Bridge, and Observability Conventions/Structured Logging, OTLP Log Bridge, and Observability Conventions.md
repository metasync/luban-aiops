---
kind: logging_system
name: Structured Logging, OTLP Log Bridge, and Observability Conventions
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/agent-platform/src/agent_service/app.py
    - products/audit-service/src/audit_service/app.py
    - products/execution-runtime/src/execution_runtime/app.py
    - products/identity-broker/src/identity_service/app.py
    - products/incident-service/src/incident_service/app.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/skills-hub/src/skills_hub/app.py
    - products/tool-gateway/src/tool_gateway/app.py
---

## What is used

The platform uses Python's stdlib `logging` module as the sole logging framework. Structured log records are emitted as single-line JSON to stdout via a thin `log_event()` helper in each product's `core/observability.py`. An opt-in OpenTelemetry (OTel) push pipeline mirrors those logs over OTLP HTTP/protobuf to an external backend (OpenObserve) through `opentelemetry.exporter.otlp.proto.http._log_exporter` and `LoggingHandler`, gated by `OTEL_ENABLED`.

There is no third-party structured-logging library (no structlog, no loguru). The only cross-cutting observability doc is `shared/shared-contracts/observability-conventions.md`, which defines the conventions all services follow.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — authoritative convention doc for metrics, tracing, logging, request correlation, and OTel switch semantics.
- Per-product `src/<service>/core/observability.py` — local copy of `configure_logging()` and `log_event(logger, event, **fields)`; every service ships its own copy so the surface is byte-identical across products.
- `products/agent-platform/src/agent_service/core/telemetry.py` — shared OTel initialization (`setup_telemetry`, `MetricsMirror`, `_attach_log_bridge`) used by agent-platform; other services have equivalent per-service implementations following the same pattern.
- Each product's `app.py` (`create_app`) calls `configure_logging()` at startup and emits an `http_request` event through the FastAPI HTTP middleware.

## Architecture and conventions

### Two surfaces

1. **JSON stdout** — source of truth for audit trail and container log collection. Every business/request event is one line of JSON produced by `log_event`, which serializes `{"event": ..., **fields}` with `json.dumps(..., default=str, sort_keys=True)`.
2. **OTLP push mirror** — opt-in trace/metric/log export to `OTEL_EXPORTER_OTLP_ENDPOINT`. Disabled by default (`OTEL_ENABLED=false`); fails open on any setup error.

### Level strategy

Uvicorn starts the root logger at `WARNING`; `configure_logging()` raises it to `INFO` via `logging.basicConfig(level=level, force=True)`, where `level = os.environ.get("LOG_LEVEL", "INFO").upper()`. The default must stay `INFO` so audit records (`http_request`, tool invocations, policy decisions) are never silently discarded. Levels are overridable per deployment via `LOG_LEVEL`.

### Event format

`log_event(logger, event, **fields)` wraps fields into `{"event": event, ...}` and emits at INFO level. Consumers parse the first field of each JSON line as the event name and treat remaining keys as structured fields. There is no fixed schema enforced at write time; callers supply arbitrary keyword arguments.

### Request correlation

- `x-request-id` is the log- and portal-facing correlation key. It is generated if absent and forwarded on outbound calls.
- When tracing is active, `x-request-id` is set to the active span's W3C `trace_id` (32 hex chars), bridging logs and APM traces.
- When tracing is inactive, `x-request-id` falls back to `req-<uuid4>`.
- No service may silently drop an inbound correlation id.

### OTLP log bridge

When `OTEL_ENABLED=true`, `setup_telemetry` attaches an OTel `LoggingHandler` to the root logger. Semantics:

- JSON stdout remains the source of truth; OTLP is a mirror for backend correlation.
- Trace/span association is automatic: records inside an active span carry `trace_id`/`span_id`.
- `logging.getLogger("opentelemetry").propagate = False` detaches OTel's internal loggers from the root logger to prevent recursion when exporter failures occur.
- The bridge is gated by the same `OTEL_ENABLED` switch and fails open.

### Fail-open guarantees

All OTel initialization (`setup_telemetry`, `MetricsMirror`, log bridge attachment) is wrapped in try/except that logs via `LOGGER.exception(...)` and swallows the exception. An unreachable or misconfigured OTLP backend never breaks a request.

### Metrics vs. logs

Prometheus `/metrics` (pull, always on) and OTLP push (opt-in) are deliberately decoupled. Domain metrics are mirrored to OTel via `MetricsMirror` (SPEC-065 R-2) but this has no effect on the logging path.

## Conventions and constraints

- **Convention:** Every product service defines its own `core/observability.py` exposing `configure_logging()` and `log_event(...)`, and calls both from `app.create_app()` before mounting routers.
- **Convention:** Business and request events are emitted as INFO-level single-line JSON via `log_event`, not via raw `logger.info(...)` calls with ad-hoc formatting.
- **Convention:** The root logger level defaults to `INFO` (overridable via `LOG_LEVEL`) so audit records survive uvicorn's WARNING default.
- **Rule (convention-enforced):** `OTEL_ENABLED` is the single master gate for traces + metrics + log mirror; there are no per-signal toggles. When false, no OTel providers or instrumentation are initialized (zero overhead).
- **Rule (convention-enforced):** JSON stdout stays the source of truth; OTLP is strictly a mirror — audit tooling must keep reading stdout.
- **Rule (convention-enforced):** The `opentelemetry` logger namespace is detached from the root logger (`propagate = False`) to prevent recursion through the bridge.
- **Rule (convention-enforced):** No service may silently drop an inbound `x-request-id` / correlation header.
- **Constraint (documented):** High-cardinality values (raw URL, user id, session id, request id) must not be used as metric labels; this is stated as a review rejection criterion in `observability-conventions.md`.
- **Constraint (documented):** Metric naming follows `<service>_<noun>_<unit>` snake_case with counters carrying `_total`; the `<service>` prefix is the short service name (`gateway`, `identity`, `agent`).
- **Constraint (documented):** Domain-metric label sets must be bounded enums; uncatalogued model names are coerced to the sentinel `unknown` to keep cardinality bounded.