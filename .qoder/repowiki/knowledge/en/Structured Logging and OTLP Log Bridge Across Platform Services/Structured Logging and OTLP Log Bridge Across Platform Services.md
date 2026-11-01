---
kind: logging_system
name: Structured Logging and OTLP Log Bridge Across Platform Services
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/incident-service/src/incident_service/app.py
---

## What is used

The platform uses Python's stdlib `logging` module for all application logging, with a thin per-service wrapper that emits single-line JSON records at INFO level. There is no third-party logger framework (no structlog, loguru, or gunicorn access loggers). Structured fields are emitted via a shared `log_event(logger, event, **fields)` helper that serializes `{"event": ..., ...fields}` through `json.dumps(..., default=str, sort_keys=True)`. Optional OpenTelemetry push (OTLP HTTP/protobuf) mirrors every structured record into the backend's log pipeline when `OTEL_ENABLED=true`, using `opentelemetry.instrumentation.logging.handler.LoggingHandler` attached to the root logger.

## Key files

- `shared/shared-contracts/observability-conventions.md` — authoritative cross-service convention document covering metric naming, cardinality rules, OTel switch semantics, structured logging levels, OTLP log bridge behavior, and request-correlation bridging (`x-request-id` ↔ W3C `traceparent`).
- `products/*/src/<service>/core/observability.py` — per-service copy of `configure_logging()` + `log_event()`. Found in agent-platform, audit-service, execution-runtime, identity-broker, incident-service, skills-hub, tool-gateway, platform-gateway.
- `products/*/src/<service>/core/telemetry.py` — per-service copy of the opt-in OTel push pipeline: `setup_telemetry()`, `is_enabled()`, `current_trace_id()`, `MetricsMirror`, and `_attach_log_bridge()`.
- `products/*/src/<service>/app.py` — service entrypoints that call `configure_logging()` at startup and emit an `app_starting` / `app_started` `log_event`.

## Architecture and conventions

1. **Per-service duplication of observability primitives.** Each product ships its own `core/observability.py` and `core/telemetry.py` rather than sharing a package. The telemetry module docstrings explicitly state the mirror must be "byte-identical across all eight services" so it names no service-specific metric; callers supply `(name, kind, labels)`.
2. **Root-level configuration.** `configure_logging()` reads `LOG_LEVEL` from the environment (default `INFO`, upper-cased, falling back to `logging.INFO` on unknown values) and calls `logging.basicConfig(level=level, force=True)`. This raises uvicorn's WARNING root level to INFO so business events survive as the audit trail.
3. **Structured event format.** All business/request events go through `log_event(logger, event, **fields)`, which produces one JSON line at INFO level with a required `event` field plus arbitrary key/value pairs. Fields are serialized with `default=str` and sorted keys for deterministic output.
4. **OTLP log bridge.** When `OTEL_ENABLED` is truthy (`1|true|yes|on`), `setup_telemetry()` installs an OTLP `LoggingHandler` on the root logger. The bridge:
   - Keeps JSON stdout as the source of truth (never replaces container logs).
   - Automatically attaches `trace_id`/`span_id` from the active span so logs join traces.
   - Detaches `opentelemetry.*` loggers from propagation to prevent recursion if the exporter fails.
   - Is gated by the same `OTEL_ENABLED` flag and fails open (errors logged, not raised).
5. **Request correlation.** `x-request-id` is the log- and portal-facing correlation key; `traceparent` (W3C Trace Context) is the machine-facing propagation header. When tracing is active, `x-request-id` is set to the active span's W3C `trace_id`; otherwise it falls back to `req-<uuid4>`. No service may silently drop an inbound correlation id.
6. **Fail-open guarantee.** Missing/misconfigured OTel backend never breaks a request. Exporter failures produce 401s at export time; batch processors drop telemetry; service setup catches exceptions and logs them instead of raising.
7. **Two decoupled surfaces.** `/metrics` (Prometheus pull, always on) and OTLP push (opt-in, off by default). They never depend on each other; disabling OTel leaves `/metrics` fully functional.
8. **Domain-metric mirror (SPEC-065).** `MetricsMirror` re-emits each service's `prometheus_client` domain families as OTel instruments with the same name and bounded label set when `OTEL_ENABLED=true`, making domain metrics visible in OpenObserve dashboards over the existing OTLP pipeline.

## Conventions and constraints

- **Convention:** Every service calls `configure_logging()` during app startup and emits business events via `log_event(LOGGER, "<event_name>", ...)` at INFO level. Verified by the identical `core/observability.py` present in agent-platform, audit-service, execution-runtime, identity-broker, incident-service, skills-hub, tool-gateway, and platform-gateway.
- **Convention:** Business and request events are single-line JSON with a required `event` field. Enforced by the `log_event` helper signature and usage across services.
- **Rule (documented):** Root logger level defaults to INFO so audit records are never silently discarded; override via `LOG_LEVEL`. Source: `shared/shared-contracts/observability-conventions.md` § "Structured Logging Levels" and the per-service `configure_logging()` docstrings.
- **Rule (documented):** OTel push is controlled exclusively by `OTEL_ENABLED`; there are no per-signal toggles. Source: `observability-conventions.md` § "OpenTelemetry Switch Semantics" and `telemetry.is_enabled()`.
- **Rule (documented):** Never use unbounded values as Prometheus labels (raw URL, user id, session id, request id); high-cardinality labels are rejected at review. Source: `observability-conventions.md` § "Cardinality Rules".
- **Rule (documented):** JSON stdout remains the source of truth; the OTLP mirror exists only for correlation with traces and must not replace container logs. Source: `observability-conventions.md` § "OTLP Log Bridge" and `_attach_log_bridge()` docstring.
- **Rule (documented):** No service may silently drop an inbound correlation id. Source: `observability-conventions.md` § "Request Correlation And Trace Bridging".
- **Constraint (enforced by code):** OTel initialization errors are caught and logged; they never propagate into the request path. Enforced in `setup_telemetry()` try/except, `MetricsMirror._ensure()`, and individual mirror methods.
- **Constraint (enforced by code):** The OTLP log bridge is attached exactly once per process via a global `_log_bridge_attached` guard.