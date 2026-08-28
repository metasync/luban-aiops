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
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/telemetry.py
    - products/identity-broker/src/identity_service/core/observability.py
---

## What system/approach is used

The platform uses Python's standard `logging` module as the sole logging framework. There is no third-party logger (no structlog, loguru, or similar). Each product service ships its own tiny `core/observability.py` that exposes two functions: `configure_logging()` and `log_event(logger, event, **fields)`. Structured logs are emitted as single-line JSON via `json.dumps(payload, default=str, sort_keys=True)` at `INFO` level, making them the canonical audit trail.

An opt-in OpenTelemetry push pipeline mirrors every structured log record to an OTLP backend (OpenObserve in this organization) through a `LoggingHandler` attached to the root logger. The OTLP bridge is gated by `OTEL_ENABLED`; when disabled, it initializes nothing and adds zero overhead.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — authoritative specification for all services' observability behavior (SPEC-005), including logging levels, OTel switch semantics, request correlation, and cardinality rules.
- Per-service `core/observability.py` (identical shape across products):
  - `products/agent-platform/src/agent_service/core/observability.py`
  - `products/platform-gateway/src/platform_gateway/core/observability.py`
  - `products/audit-service/src/audit_service/core/observability.py`
  - `products/identity-broker/src/identity_service/core/observability.py`
  - `products/incident-service/src/incident_service/core/observability.py`
  - `products/skills-hub/src/skills_hub/core/observability.py`
  - `products/tool-gateway/src/tool_gateway/core/observability.py`
  - `products/execution-runtime/src/execution_runtime/core/observability.py`
- Per-service `core/telemetry.py` (identical shape across products) — implements the OTel push pipeline (`setup_telemetry`, `_attach_log_bridge`, `current_trace_id`).
- Service `app.py` entrypoints call `configure_logging()` at startup and `setup_telemetry(app, service_name)` during FastAPI app bootstrap.

## Architecture and conventions

### Two decoupled surfaces
Every service exposes:
1. **`/metrics`** — pull-based Prometheus endpoint, always on, implemented directly with `prometheus_client` plus a minimal RED middleware.
2. **OpenTelemetry push** — traces, metrics, and mirrored logs pushed via OTLP HTTP/protobuf to `OTEL_EXPORTER_OTLP_ENDPOINT`; authentication via `OTEL_EXPORTER_OTLP_HEADERS`; resource `service.name` from `OTEL_SERVICE_NAME` (defaults to service metadata).

These surfaces never depend on each other; disabling OTel leaves `/metrics` fully functional.

### Structured log format
Business and request events go through `log_event(logger, "event_name", field=value, ...)`, which builds `{"event": event, ...}` and emits it as one JSON line at `INFO`. This is the audit trail (e.g. `http_request`, `tool_invoked`, policy decisions, token delegation events). Because Uvicorn starts the root logger at `WARNING`, every service calls `configure_logging()` at startup to raise the root level to `INFO` (overridable per deployment via `LOG_LEVEL`).

### Request correlation
- `x-request-id` is the log- and portal-facing correlation key; generated if absent and forwarded on every outbound call.
- `traceparent` (W3C Trace Context) is the machine-facing propagation header, managed automatically by OpenTelemetry instrumentation.
- When tracing is active, `x-request-id` is set to the active span's W3C `trace_id` (32 hex chars); otherwise it falls back to `req-<uuid4>`.
- No service may silently drop an inbound correlation id.

### OTLP log bridge
When `OTEL_ENABLED` is truthy, `_attach_log_bridge` installs an OTel `LoggingHandler` on the root logger so every `logger.info(json_line)` is also exported as an OTLP log record. Semantics enforced by the code:
- JSON stdout remains the source of truth; the OTLP mirror exists only for trace correlation.
- Records emitted inside an active span carry its `trace_id`/`span_id`, joining the log mirror to the trace view on the same W3C id.
- `logging.getLogger("opentelemetry").propagate = False` detaches OTel's internal loggers from the root logger so exporter failures cannot recurse into the bridge.
- The bridge is gated by the same `OTEL_ENABLED` switch and fails open (setup errors are logged, never raised into the request path).

### Metric naming and cardinality
- Format: `<service>_<noun>_<unit>`, snake_case; counters end in `_total`.
- Labels must be bounded enums; raw URLs, user ids, session ids, request ids are forbidden as labels.

## Conventions and constraints

- **All business/request events must use `log_event(...)` at INFO level.** The convention document states these records are the audit trail and must not be silently discarded.
- **Every service must call `configure_logging()` at app startup** to override Uvicorn's WARNING default; the default must stay INFO so audit records survive.
- **OTel push is off by default**, controlled exclusively by `OTEL_ENABLED`; there are no per-signal toggles.
- **Fail-open guarantee**: unreachable/misconfigured OTLP backends must never break a request; missing credentials produce export-time 401s dropped by batch processors; setup exceptions are caught and logged.
- **No unbounded label cardinality** on metrics; violations are rejected at review.
- **Never commit secrets**: `OTEL_EXPORTER_OTLP_HEADERS` and other runtime secrets are provisioned via GitOps (`sync-otel-secrets.sh`) into Kubernetes Secrets, never committed to the repo.
- **Service name tagging**: `service.name` comes from `OTEL_SERVICE_NAME` or the service's metadata; used to scope OTLP resources.