---
kind: logging_system
name: Structured Logging with OpenTelemetry Log Bridge (SPEC-005)
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/agent-platform/src/agent_service/core/request_context.py
    - products/agent-platform/src/agent_service/app.py
---

## What system/approach is used

The platform implements a **structured JSON logging** approach built on Python's stdlib `logging`, with an opt-in OpenTelemetry OTLP push pipeline that mirrors every log record to the backend. The design is codified in `shared/shared-contracts/observability-conventions.md` and implemented per-service via a shared pattern: each service initializes logging at startup, emits single-line JSON events through a helper, and optionally bridges those records into traces/metrics/logs via OTLP HTTP/protobuf.

Key components:
- **Stdlib `logging`** as the sole logger framework — no third-party logging libraries are used.
- **Structured event emission** via a `log_event(logger, event, **fields)` helper that serializes `{event, ...fields}` as sorted-key JSON.
- **OpenTelemetry push** (traces, metrics, logs) gated by `OTEL_ENABLED`; when enabled, a `LoggingHandler` attaches to the root logger so every structured record is exported over OTLP alongside stdout.
- **Prometheus `/metrics`** endpoint exposed independently of OTel, using `prometheus_client` directly (per conventions).

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — authoritative specification for metrics, tracing, logging, request correlation, and environment variables.
- `products/agent-platform/src/agent_service/core/observability.py` — `configure_logging()` raises the root logger from uvicorn's WARNING default to INFO (overridable via `LOG_LEVEL`) and `log_event()` emits structured JSON.
- `products/agent-platform/src/agent_service/core/telemetry.py` — `setup_telemetry(app, service_name)` initializes TracerProvider, MeterProvider, FastAPI/HTTPX instrumentation, and the OTLP log bridge; `current_trace_id()` returns the active span's W3C trace id.
- `products/agent-platform/src/agent_service/core/request_context.py` — `resolve_request_id()` bridges inbound `x-request-id` to the active OTel `trace_id` or falls back to `req-<uuid4>`.
- `products/agent-platform/src/agent_service/app.py` — application bootstrap that calls `configure_logging()`, installs an HTTP middleware emitting `http_request` events via `log_event`, then calls `setup_metrics()` and `setup_telemetry()`.

Other product services follow the same pattern (imports of `configure_logging`, `log_event`, `setup_telemetry`, and `LOGGER = logging.getLogger(__name__)` appear across agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway).

## Architecture and conventions

### Two decoupled observability surfaces
1. **`/metrics` (pull, always on)** — Prometheus endpoint independent of OTel.
2. **OpenTelemetry push (opt-in)** — traces + metrics + mirrored logs pushed via OTLP HTTP/protobuf to the configured backend (OpenObserve). Controlled by `OTEL_ENABLED`; off by default; fails open.

### Structured logging contract
- All business and request events are emitted as **single-line JSON** at **INFO** level via `log_event(logger, "event_name", field=value, ...)`. Fields are serialized with `json.dumps(..., default=str, sort_keys=True)`.
- Every service calls `configure_logging()` at app startup to raise the root logger from uvicorn's WARNING default to INFO so audit records are never silently discarded. The effective level can be overridden per deployment via `LOG_LEVEL`.
- Business events include `http_request`, `tool_invoked`, policy decisions, etc., carrying fields like `service`, `request_id`, `method`, `path`, `status_code`, `duration_ms`.

### Request correlation and trace bridging
- `x-request-id` is the log- and portal-facing correlation key. It is generated if absent and forwarded on every outbound call.
- When tracing is active, `x-request-id` is set to the active span's W3C `trace_id` (32 hex chars), joining structured logs and APM traces. When inactive, it falls back to `req-<uuid4>`.
- No service may silently drop an inbound correlation id.

### OTLP log bridge semantics
- JSON stdout remains the **source of truth**; the OTLP mirror exists only so the backend can correlate logs with traces.
- Trace/span association is automatic: records emitted inside an active span carry its `trace_id`/`span_id`.
- Recursion guard: `opentelemetry` loggers are detached from the root logger (`propagate = False`) so exporter failures cannot loop back through the bridge.
- The bridge is gated by `OTEL_ENABLED` and fails open.

### Environment variables
- `LOG_LEVEL` — overrides root logger level (default INFO).
- `OTEL_ENABLED` — master gate for all OTel signals (default false); values `1`, `true`, `yes`, `on` enable it.
- `OTEL_EXPORTER_OTLP_ENDPOINT` — OTLP HTTP base URL (exporters append `/v1/{traces,metrics,logs}`).
- `OTEL_EXPORTER_OTLP_HEADERS` — authentication headers (Basic auth for OpenObserve), provisioned via runtime secrets.
- `OTEL_SERVICE_NAME` — resource service name; defaults to the service's metadata name.

### Metric naming convention
- Format: `<service>_<noun>_<unit>` snake_case; counters end with `_total`.
- Service prefix is short: `gateway`, `identity`, `agent`.
- Labels use bounded enums only; raw URLs, user ids, session ids, request ids must never be labels.

## Conventions and constraints

- **Every service must call `configure_logging()` at startup** to ensure INFO-level structured events survive uvicorn's default WARNING threshold.
- **All business/request events must go through `log_event()`**, not direct `logger.info(...)` calls, to guarantee consistent JSON structure.
- **OTel push is opt-in and fail-open**: missing/unreachable backend must never break a request; setup errors are logged and ignored.
- **No unbounded label cardinality**: raw request URLs, user ids, session ids, request ids are prohibited as metric labels.
- **`x-request-id` must never be dropped** on inbound requests; it is bridged to the active OTel `trace_id` when tracing is active.
- **Audit trail integrity**: because `LOG_LEVEL` defaults to INFO, audit records (http_request, tool_invoked, policy decisions) are never silently discarded unless explicitly raised above INFO.