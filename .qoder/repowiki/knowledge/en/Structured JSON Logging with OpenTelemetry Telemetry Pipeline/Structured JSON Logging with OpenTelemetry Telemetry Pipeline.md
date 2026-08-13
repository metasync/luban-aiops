---
kind: logging_system
name: Structured JSON Logging with OpenTelemetry Telemetry Pipeline
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/tool-gateway/src/tool_gateway/core/telemetry.py
    - products/identity-broker/src/identity_service/core/telemetry.py
    - products/agent-platform/src/agent_service/app.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/tool-gateway/src/tool_gateway/app.py
    - products/identity-broker/src/identity_service/app.py
---

## What system/approach is used

The platform uses Python's standard `logging` module for structured, single-line JSON audit logs and an opt-in OpenTelemetry (OTel) push pipeline for distributed traces and metrics. There is no third-party logging framework (no structlog, loguru, or similar); every service implements the same pattern in its own `core/observability.py` and `core/telemetry.py`.

- **Structured logs**: emitted via a shared `log_event(logger, event, **fields)` helper that serializes `{"event": ..., **fields}` to JSON at INFO level. Business events include `http_request`, `tool_invoked`, policy decisions, token delegation, toolkit registration, etc.
- **Log level control**: `configure_logging()` calls `logging.basicConfig(level=..., force=True)` reading `LOG_LEVEL` from environment (default `INFO`). This explicitly raises the root logger above Uvicorn's default WARNING so audit records are never silently discarded.
- **Trace/metrics telemetry**: opt-in OTel push via `setup_telemetry(app, service_name)`, gated by `OTEL_ENABLED`. When enabled it configures a `TracerProvider` + `BatchSpanProcessor(OTLPSpanExporter())` and a `MeterProvider` + `PeriodicExportingMetricReader(OTLPMetricExporter())`, instruments FastAPI and HTTPX clients, and sets `service.name` from `OTEL_SERVICE_NAME`.
- **Prometheus metrics**: exposed on `/metrics` via `prometheus-fastapi-instrumentator`, always-on and independent of OTel.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — authoritative cross-service contract defining metric naming, cardinality rules, OTel switch semantics, request correlation, and structured logging levels.
- Per-service `core/observability.py` (agent-platform, platform-gateway, tool-gateway, identity-broker): identical `configure_logging()` + `log_event()` implementation.
- Per-service `core/telemetry.py` (same four services): identical `is_enabled()`, `setup_telemetry()`, `current_trace_id()`.
- Per-service `app.py`: bootstraps `configure_logging()`, registers the HTTP middleware that emits `http_request` events, calls `setup_metrics()` and `setup_telemetry()`.
- Per-service `core/request_context.py`: resolves/generates `x-request-id` per the correlation convention.
- `products/*/tests/test_observability.py` and `test_*.py` validate LOG_LEVEL override behavior and OTel enablement.

## Architecture and conventions

### Two decoupled observability surfaces
Every service exposes:
1. `/metrics` (pull, Prometheus, always on).
2. OTel push (opt-in, OTLP gRPC to the configured collector; off by default, fails open).
The two never depend on each other.

### Structured log format
All business and request events are single-line JSON produced by `log_event(logger, "event_name", field=value, ...)`. The payload shape is `{"event": <name>, ...fields}`, serialized with `json.dumps(..., default=str, sort_keys=True)` at INFO level. Because these records form the audit trail, the root logger is raised to INFO at startup.

### Request correlation and trace bridging
- `x-request-id` is the log- and portal-facing correlation key. It is generated if absent and forwarded on outbound calls.
- `traceparent` (W3C Trace Context) is the machine-facing propagation header, managed automatically by OTel instrumentation across hops.
- Bridging rule: when tracing is active, `x-request-id` is set to the active span's W3C `trace_id` (32 hex chars); when inactive it falls back to `req-<uuid4>`.
- No service may silently drop an inbound correlation id.

### Metric naming and labels
- Format: `<service>_<noun>_<unit>` snake_case; counters carry `_total`.
- Service prefix is short name: `gateway`, `identity`, `agent`.
- Labels must be bounded enums only (e.g. `decision ∈ {allow, deny}`, `result ∈ {valid, invalid, expired, missing}`).
- Never label on raw URL, user id, session id, or request id (cardinality rule).

### OTel switch semantics
- `OTEL_ENABLED` — master gate, default false; one switch gates traces + metrics.
- `OTEL_EXPORTER_OTLP_ENDPOINT` — collector URL.
- `OTEL_SERVICE_NAME` — resource service name, defaults to service metadata.
- Fail-open: unreachable/misconfigured collector never breaks a request; setup errors are logged via `LOGGER.exception`.

### Environment variables summary
| Variable | Purpose | Default |
|---|---|---|
| `LOG_LEVEL` | Root logger level for structured audit logs | `INFO` |
| `OTEL_ENABLED` | Master gate for OTel push pipeline | `false` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP collector endpoint | — |
| `OTEL_SERVICE_NAME` | Resource service name | service metadata |

## Conventions and constraints

- Every service must call `configure_logging()` before any request handling so audit records survive Uvicorn's WARNING default.
- All business events go through `log_event(...)` at INFO level; do not emit ad-hoc `print()` or unstructured logs for audit-relevant events.
- Metrics use `prometheus-fastapi-instrumentator`; do not implement custom `/metrics` endpoints.
- OTel initialization is wrapped in try/except and never raises into the request path.
- High-cardinality labels are rejected at review (per the conventions doc); never label on request ids, user ids, sessions, or raw URLs.
- Correlation id must never be dropped; fallback to generated UUID when neither `x-request-id` nor active trace exists.