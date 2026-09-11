---
kind: logging_system
name: Structured JSON Logging with OTLP Mirror (SPEC-005)
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
    - products/audit-service/src/audit_service/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
---

## What system/approach is used

The platform uses Python's stdlib `logging` module as the sole logging framework. Each microservice ships a tiny, identical `core/observability.py` that exposes two functions: `configure_logging()` and `log_event(logger, event, **fields)`. Structured logs are emitted as single-line JSON objects via `json.dumps(..., sort_keys=True)` at INFO level. An opt-in OpenTelemetry push pipeline mirrors every structured record to an OTLP HTTP backend (OpenObserve) through a `LoggingHandler`, while stdout remains the source of truth for audit tooling.

## Key files and packages

- Per-service configuration entry point: `products/<service>/src/<service>/app.py` calls `configure_logging()` before creating the FastAPI app.
- Per-service observability helpers: `products/*/src/*_service/core/observability.py` — each contains the same `configure_logging()` / `log_event()` pair.
- OTel bridge: `products/*/src/*_service/core/telemetry.py` — initializes TracerProvider, MeterProvider, FastAPI/HTTPX instrumentation, and attaches an OTLP `LoggingHandler` when `OTEL_ENABLED` is true.
- Cross-cutting contract: `shared/shared-contracts/observability-conventions.md` documents the full logging strategy, levels, correlation headers, and OTLP semantics.

Services following this pattern include agent-platform, audit-service, execution-runtime, identity-broker, platform-gateway, skills-hub, and tool-gateway.

## Architecture and conventions

### Initialization
Every service calls `configure_logging()` at startup. It reads `LOG_LEVEL` from environment (default `INFO`) and calls `logging.basicConfig(level=..., force=True)` on the root logger. This is necessary because Uvicorn starts the root logger at WARNING, which would silently drop all INFO-level structured events that form the audit trail.

### Structured event format
Business and request events are emitted exclusively through `log_event(LOGGER, "event_name", field=value, ...)`. The helper builds `{"event": event_name, ...fields}` and writes it as a single JSON line at INFO level. There is no per-module log formatter; the JSON serialization happens in the helper.

### Log levels
- INFO: all business/request events (`http_request`, `tool_invoked`, `policy_decision`, `auth_login_started`, etc.) — these constitute the audit trail.
- DEBUG/WARNING/ERROR: used sparingly by application code via `logging.getLogger(__name__)`; not part of the standardized audit surface.
- The default level must stay INFO so audit records are never silently discarded; deployments may raise it via `LOG_LEVEL`.

### Request correlation
- `x-request-id` is the log- and portal-facing correlation key. It is generated if absent and forwarded on every outbound call.
- When tracing is active, `x-request-id` is bridged to the active span's W3C `trace_id`; otherwise it falls back to `req-<uuid4>`.
- No service may silently drop an inbound correlation id.

### OTLP mirror
When `OTEL_ENABLED=true`, `setup_telemetry()` attaches an OTLP `LoggingHandler` to the root logger. Semantics:
- JSON stdout stays the source of truth; OTLP is a mirror for trace/log correlation.
- Records emitted inside an active span automatically carry `trace_id`/`span_id`.
- The `opentelemetry` internal loggers are detached from the root logger to prevent recursion.
- The bridge fails open: setup errors are logged but never raised into the request path.

### Metrics/tracing separation
Metrics (`/metrics` pull endpoint) and OTLP push are deliberately decoupled. Disabling OTel leaves `/metrics` fully functional.

## Conventions and constraints

- **One structured-log helper per service**: use `log_event(LOGGER, "<event>", **fields)` rather than calling `logger.info(json.dumps(...))` directly. All services implement this in their own `core/observability.py`.
- **Single-line JSON only**: every audit event is one JSON object per line, keys sorted, values coerced to strings via `default=str`.
- **Root logger level must be INFO by default**: enforced by `configure_logging()` raising the root logger above Uvicorn's WARNING default; tests in `test_observability.py` verify behavior under different `LOG_LEVEL` values.
- **Audit events are INFO-level**: they cannot be filtered out by lowering the root level below INFO without losing the audit trail.
- **No unbounded label cardinality** applies to metrics, and the same principle guides log fields — avoid high-cardinality free-form values in favor of bounded enums where possible.
- **OTLP is opt-in and fail-open**: `OTEL_ENABLED=false` (default) means zero overhead; misconfigured endpoints produce export failures that are logged but do not break requests.
- **Correlation header rule**: no service may silently drop an inbound `x-request-id` or `traceparent` header.