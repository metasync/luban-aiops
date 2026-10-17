---
kind: logging_system
name: Structured JSON Logging with OTLP Bridge and Per-Service Observability Modules
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/identity-broker/src/identity_service/app.py
    - products/incident-service/src/incident_service/app.py
    - products/platform-gateway/src/platform_gateway/app.py
---

## What is used

The platform uses Python's stdlib `logging` module for all application logging. There is no third-party logging framework (no structlog, loguru, or python-json-logger). Structured logs are emitted as single-line JSON via a thin `log_event(logger, event, **fields)` helper that serializes the payload with `json.dumps(..., default=str, sort_keys=True)`. An opt-in OpenTelemetry bridge (`opentelemetry.exporter.otlp.proto.http._log_exporter`) mirrors every INFO-level record to an OTLP HTTP/protobuf backend (OpenObserve in this org).

## Key files and packages

- Shared convention doc: `shared/shared-contracts/observability-conventions.md` — the authoritative spec for metrics, tracing, logging, and request-correlation across all services.
- Per-service observability modules (identical shape): `products/<service>/src/<service_package>/core/observability.py` implementing `configure_logging()` and `log_event()`.
- Per-service telemetry modules (opt-in OTel push): `products/<service>/src/<service_package>/core/telemetry.py` providing `setup_telemetry()`, `is_enabled()`, `current_trace_id()`, and the `MetricsMirror` class.
- Service entrypoints call both at startup: e.g. `products/agent-platform/src/agent_service/app.py`, `products/audit-service/src/audit_service/app.py`, `products/execution-runtime/src/execution_runtime/app.py`, `products/identity-broker/src/identity_service/app.py`, `products/incident-service/src/incident_service/app.py`, `products/platform-gateway/src/platform_gateway/app.py`.

## Architecture and conventions

### Two decoupled surfaces

Every service exposes two independent observability surfaces:

1. `/metrics` (Prometheus pull, always on) — implemented directly with `prometheus_client` plus a RED middleware; never depends on OTel.
2. OpenTelemetry push (opt-in) — traces, metrics, and mirrored logs exported over OTLP HTTP/protobuf to `OTEL_EXPORTER_OTLP_ENDPOINT`; gated by `OTEL_ENABLED` (default false); fails open.

### Structured log format

Business and request events go through `log_event(logger, "event_name", field=value, ...)`. The helper builds `{"event": event, ...}` and emits it at INFO level as one JSON line. This is the audit trail (http_request, tool_invoked, policy decisions, identity_normalized, etc.).

### Log level strategy

Uvicorn initializes the root logger at WARNING, which would silently discard every structured audit record. Every service calls `configure_logging()` at app startup, which reads `LOG_LEVEL` from the environment (defaulting to `INFO`) and runs `logging.basicConfig(level=level, force=True)`. The default must stay INFO so audit records are never discarded; per-deployment override is via `LOG_LEVEL`.

### OTLP log bridge

When `OTEL_ENABLED=true`, `setup_telemetry()` attaches an OTel `LoggingHandler` to the root logger. Semantics documented in `observability-conventions.md`:

- JSON stdout remains the source of truth; OTLP is a mirror for correlation with traces.
- Trace/span association is automatic — records emitted inside an active span carry `trace_id`/`span_id`.
- Recursion guard: `logging.getLogger("opentelemetry").propagate = False` prevents exporter failures from looping back.
- The bridge is gated by the same `OTEL_ENABLED` switch and fails open.

### Request correlation

- `x-request-id` is the log- and portal-facing correlation key, generated if absent and forwarded on outbound calls.
- `traceparent` (W3C Trace Context) is the machine-facing propagation header managed by OTel instrumentation.
- Bridging rule: when tracing is active, `x-request-id` is set to the active span's W3C `trace_id` (32 hex chars), so a single value joins structured logs and APM traces; when inactive, it falls back to `req-<uuid4>`.

### Domain-metric mirror (SPEC-065)

`MetricsMirror` re-emits each service's own `prometheus_client` domain families as OTel instruments (same name, same bounded label set) when `OTEL_ENABLED=true`, so dashboards can consume them over the OTLP push path. It is lazy, generic, and fail-open.

### Environment variables

- `LOG_LEVEL` — overrides the root logger level (default `INFO`).
- `OTEL_ENABLED` — master gate (default false); one switch for traces + metrics + log mirror.
- `OTEL_EXPORTER_OTLP_ENDPOINT` — OTLP HTTP base URL (e.g. `http://openobserve-router:5080/api/default`).
- `OTEL_EXPORTER_OTLP_HEADERS` — Basic auth headers for OpenObserve ingest.
- `OTEL_SERVICE_NAME` — resource service name; defaults to the service's metadata name.

## Conventions and constraints

- **All business/request events use `log_event(logger, "event_name", **fields)`** — observed across agent-platform, audit-service, execution-runtime, identity-broker, incident-service, and platform-gateway route handlers.
- **Services call `configure_logging()` at app startup** — observed in every product's `app.py` / `create_app()` factory.
- **Default log level is INFO** — enforced by `LOG_LEVEL` defaulting to `"INFO"` in `configure_logging()`; the convention doc states the default "must stay INFO so audit records are never silently discarded".
- **OTel push is off by default** — `OTEL_ENABLED` defaults to false; `setup_telemetry()` returns early when disabled, leaving `/metrics` unaffected.
- **Fail-open guarantee** — any OTel setup/export error is logged and swallowed; it never propagates into the request path (documented in `observability-conventions.md` and implemented in `setup_telemetry`'s try/except and `MetricsMirror._ensure`).
- **JSON stdout is the source of truth** — the convention doc explicitly states OTLP "never replaces container logs and audit tooling must keep reading stdout".
- **No unbounded metric labels** — cardinality rules prohibit labeling on raw URLs, user ids, session ids, or request ids; bounded enum labels only.
- **Per-service duplication of `core/observability.py`** — each product ships its own identical copy of the `configure_logging`/`log_event` helpers rather than sharing a package; tests verify parity across services.