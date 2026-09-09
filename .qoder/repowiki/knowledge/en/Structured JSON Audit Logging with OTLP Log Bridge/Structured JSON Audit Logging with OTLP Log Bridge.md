---
kind: logging_system
name: Structured JSON Audit Logging with OTLP Log Bridge
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/agent-platform/src/agent_service/core/request_context.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/platform-gateway/src/platform_gateway/core/request_context.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
---

## What system/approach is used

Every service in the platform uses Python's stdlib `logging` module to emit **single-line, sorted-key JSON audit records** at INFO level. There is no third-party logging framework (no structlog, loguru, or gunicorn access-log middleware). The structured records are the canonical audit trail and are consumed by downstream tooling that reads container stdout.

An opt-in OpenTelemetry push pipeline mirrors every structured record over OTLP HTTP/protobuf to an external backend (OpenObserve) via a `LoggingHandler` attached to the root logger. This mirror is gated by `OTEL_ENABLED`; when disabled, nothing OTel-related is initialized and there is zero overhead. The bridge automatically attaches active span trace/span IDs so logs can be correlated with traces.

## Key files and packages

- Per-service `core/observability.py` — defines `configure_logging()` and `log_event(logger, event, **fields)`; identical across all services:
  - `products/agent-platform/src/agent_service/core/observability.py`
  - `products/platform-gateway/src/platform_gateway/core/observability.py`
  - `products/tool-gateway/src/tool_gateway/core/observability.py`
  - `products/audit-service/src/audit_service/core/observability.py`
  - `products/execution-runtime/src/execution_runtime/core/observability.py`
  - `products/identity-broker/src/identity_service/core/observability.py`
  - `products/incident-service/src/incident_service/core/observability.py`
  - `products/skills-hub/src/skills_hub/core/observability.py`
- `shared/shared-contracts/observability-conventions.md` — authoritative spec for all observability signals (metrics, tracing, logging, correlation).
- Per-service `core/telemetry.py` — initializes OTel providers, FastAPI/HTTPX instrumentation, and the OTLP log bridge (`_attach_log_bridge`).
- Per-service `core/request_context.py` — resolves `x-request-id` per SPEC-005 R-4.

## Architecture and conventions

### Initialization
Each service calls `configure_logging()` during app startup. It raises the root logger from Uvicorn's default WARNING to INFO so audit events are not silently dropped. The effective level is read from the `LOG_LEVEL` environment variable (default `INFO`, uppercased); callers must never call `basicConfig` themselves after this point.

### Structured event format
Business and request events are emitted through `log_event(LOGGER, "event_name", field=value, ...)`. The helper builds `{"event": event_name, ...fields}` and serializes it with `json.dumps(..., default=str, sort_keys=True)`, then emits at INFO. Every audit event is therefore a single line of JSON containing an `event` key plus arbitrary domain fields. Examples observed: `http_request`, `tool_invoked`, `policy_decision`, `auth_login_url_requested`, `auth_logout_requested`, `identity_normalized`, `session_created`, etc.

### Request correlation
`x-request-id` is the log- and portal-facing correlation key. Each service's `resolve_request_id(request_id)` returns the inbound value if present, otherwise bridges to the active OTel `trace_id` (via `current_trace_id()`), otherwise falls back to `req-<uuid4>`. When tracing is active, `x-request-id` equals the W3C `traceparent`'s trace ID, joining logs and APM traces on a single value.

### OTLP log bridge
When `OTEL_ENABLED=true`, `setup_telemetry(app, service_name)` creates a `LoggerProvider` with a `BatchLogRecordProcessor(OTLPLogExporter())`, sets it as the global logger provider, detaches `opentelemetry` internal loggers from the root logger to prevent recursion, and adds an OTel `LoggingHandler` to the root logger. All subsequent `log_event` calls are thus exported as OTLP log records while still being written to stdout. Export failures are swallowed — the pipeline fails open.

### Metrics and tracing (supporting surfaces)
- `/metrics` (Prometheus pull) is always enabled and independent of OTel.
- Traces + metrics are pushed via OTLP when enabled; metric naming follows `<service>_<noun>_<unit>` with bounded enum labels and `_total` counters.
- Cardinality rules forbid labeling on raw URLs, user ids, session ids, or request ids.

## Conventions and constraints

1. **All audit events go through `log_event` at INFO.** The convention document states: "All business and request events are emitted as single-line JSON via `log_event(...)` at INFO level." Services must not bypass this helper for audit-worthy events.
2. **Root logger level must be raised at startup.** Every service's `configure_logging()` explicitly sets the root level to INFO (overridable via `LOG_LEVEL`) because Uvicorn defaults to WARNING, which would discard audit records.
3. **No per-signal OTel toggles.** `OTEL_ENABLED` gates the entire push pipeline (traces + metrics + log mirror). There are no switches to enable only traces or only logs.
4. **Fail-open guarantee.** OTel setup errors are logged and ignored; missing/misconfigured endpoints do not break requests. Exporter failures drop telemetry without raising.
5. **JSON stdout is the source of truth.** The OTLP mirror exists solely for correlation with traces; consumers must keep reading stdout, not the OTLP stream.
6. **Correlation rule:** `x-request-id` wins if present; otherwise bridge to active trace_id; otherwise generate `req-<uuid4>`. No service may silently drop an inbound correlation id.
7. **Cardinality rules:** Never use unbounded values as Prometheus labels (raw URL, user id, session id, request id). Domain counters must use bounded enum labels.
8. **Service name propagation:** `OTEL_SERVICE_NAME` overrides the resource service name; otherwise the service's metadata name is used.
9. **Secrets handling:** `OTEL_EXPORTER_OTLP_HEADERS` carries Basic auth for OpenObserve and is provisioned via runtime secrets, never committed or placed in ConfigMaps.