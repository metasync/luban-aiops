---
kind: logging_system
name: Structured Logging with OTLP Bridge and Audit-Grade INFO-Level JSON
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/agent-platform/src/agent_service/app.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
---

## What system/approach is used

The platform uses Python's stdlib `logging` module as the sole logging framework, combined with OpenTelemetry's `LoggingHandler` to bridge structured logs into an opt-in OTLP push pipeline. There is no third-party logger library (no structlog, loguru, or similar). All business/request events are emitted as single-line JSON records at **INFO** level.

Two observability surfaces are deliberately decoupled:

1. **stdout JSON lines** — the source of truth for the audit trail; consumed by container log collectors.
2. **OpenTelemetry push (opt-in)** — traces, metrics, and mirrored logs exported via OTLP HTTP/protobuf to the configured backend (OpenObserve), gated by `OTEL_ENABLED` (default off).

The conventions are documented centrally in `shared/shared-contracts/observability-conventions.md`, which backs SPEC-005 and SPEC-065.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — authoritative cross-service contract for metrics, tracing, logging, and request correlation.
- Per-product `core/observability.py` — tiny shared helpers (`configure_logging`, `log_event`) duplicated across each service.
- Per-product `core/telemetry.py` — opt-in OTel setup, log bridge, and `MetricsMirror`; byte-identical across all eight services (enforced by a `TelemetryParityTest`).
- Per-product `app.py` entrypoints call `configure_logging()` at startup and `setup_telemetry(app, service_name)` when tracing is enabled.

Services observed using this pattern: `agent-platform`, `audit-service`, `platform-gateway`. Other products follow the same shape (each has its own `core/observability.py` and `core/telemetry.py`).

## Architecture and conventions

### Log emission

Business and request events go through `log_event(logger, event, **fields)`, which builds `{"event": <name>, ...fields}` and emits it as `logger.info(json.dumps(payload, default=str, sort_keys=True))`. Call sites create per-module loggers via `LOGGER = logging.getLogger(__name__)` and pass them in.

### Level strategy

Uvicorn starts the root logger at WARNING, so `configure_logging()` raises it to INFO (overridable via `LOG_LEVEL`, defaulting to INFO) so audit records are never silently discarded. The convention is that INFO carries audit-grade events (http_request, tool_invoked, policy decisions); DEBUG/WARNING/ERROR are reserved for operational diagnostics.

### OTLP log bridge

When `OTEL_ENABLED=true`, `_attach_log_bridge` installs an `opentelemetry.instrumentation.logging.handler.LoggingHandler` on the root logger at INFO level. It ships the same JSON records over OTLP so the backend can correlate logs with traces — trace/span ids attach automatically when a span is active. The `opentelemetry` internal loggers are detached from the root logger (`propagate = False`) to prevent recursion if the exporter fails.

### Request correlation

- `x-request-id` is the log- and portal-facing correlation key; generated if absent and forwarded on every outbound call.
- `traceparent` (W3C Trace Context) is the machine-facing propagation header managed by OTel instrumentation.
- Bridging rule: when tracing is active, `x-request-id` is set to the active span's W3C `trace_id` (32 hex chars); when inactive, it falls back to `req-<uuid4>`.
- No service may silently drop an inbound correlation id.

### Fail-open semantics

Both `configure_logging` and `setup_telemetry` are fail-open: missing/misconfigured OTel credentials produce 401s at export time, batch processors drop telemetry on failure, and initialization errors are logged rather than raised into the request path. Disabling OTel leaves `/metrics` fully functional.

### Structured fields

Every log record is a flat JSON object with an `event` field identifying the semantic event, plus arbitrary additional keyword fields passed through `**fields`. Values are coerced to strings via `json.dumps(..., default=str)` and keys are sorted for stable output.

## Conventions and constraints

- **All business/request events are INFO-level single-line JSON.** Enforced by the `log_event` helper and the `configure_logging` root-level bump to INFO; the conventions doc states "the default must stay INFO so audit records are never silently discarded".
- **Audit trail lives on stdout JSON.** The conventions doc says "JSON stdout stays the source of truth"; the OTLP mirror exists only for backend correlation.
- **OTel push is controlled exclusively by `OTEL_ENABLED`.** The conventions doc states there are no per-signal toggles; one switch gates traces + metrics + log mirror.
- **No unbounded label cardinality on any signal.** The conventions doc forbids labeling on raw URL, user id, session id, or request id; high-cardinality labels are rejected at review.
- **Per-service `core/observability.py` and `core/telemetry.py` are duplicated verbatim across products.** The telemetry module docstring asserts they are "byte-identical across all eight services (TelemetryParityTest)", and tests enforce parity.
- **Request correlation headers must not be dropped.** The conventions doc states "No service may silently drop an inbound correlation id".
- **Domain-metric names follow `<service>_<noun>_<unit>` snake_case with counters suffixed `_total`.** Documented in the conventions file under Metric Naming.