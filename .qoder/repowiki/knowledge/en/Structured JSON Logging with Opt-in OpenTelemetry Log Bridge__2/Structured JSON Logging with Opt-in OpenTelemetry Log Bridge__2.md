---
kind: logging_system
name: Structured JSON Logging with Opt-in OpenTelemetry Log Bridge
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/platform-gateway/src/platform_gateway/core/request_context.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/audit-service/src/audit_service/core/telemetry.py
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/telemetry.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/identity-broker/src/identity_service/core/telemetry.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/incident-service/src/incident_service/core/telemetry.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/skills-hub/src/skills_hub/core/telemetry.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/telemetry.py
---

## What system/approach is used

The Luban platform uses Python's standard `logging` module as the sole logging framework. Every service emits **single-line, sorted-key JSON** records to stdout via a shared `log_event(logger, event, **fields)` helper, and optionally mirrors those same records into an OpenTelemetry OTLP log pipeline when tracing is enabled. There is no third-party logger library (no structlog, loguru, or similar); structured fields are passed as keyword arguments and serialized by `json.dumps(..., sort_keys=True)`.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — the authoritative specification for all services: log level defaults, structured format, correlation headers, OTel switch semantics, and the relationship between stdout logs and the OTLP mirror.
- Per-service `core/observability.py` (identical across `platform-gateway`, `audit-service`, `agent-platform`, `execution-runtime`, `identity-broker`, `incident-service`, `skills-hub`, `tool-gateway`) — provides:
  - `configure_logging()` — raises the root logger from uvicorn's default `WARNING` to `INFO` so audit-level events survive; reads `LOG_LEVEL` env var to override.
  - `log_event(logger, event, **fields)` — builds `{"event": ..., ...fields}` and emits it at `INFO` level as one JSON line.
- Per-service `core/telemetry.py` (identical across all services) — opt-in OpenTelemetry push pipeline gated by `OTEL_ENABLED`. When enabled it installs an OTel `LoggingHandler` on the root logger that bridges every `INFO`+ record to the configured `OTEL_EXPORTER_OTLP_ENDPOINT` via OTLP HTTP/protobuf (`/v1/logs`).
- `core/request_context.py` (e.g. `platform_gateway/core/request_context.py`) — resolves `x-request-id` by preferring the inbound header, then the active OTel trace id, then a generated `req-<uuid4>` fallback.
- Service entry points (`app.py` / `main.py`) call `configure_logging()` early in startup and `setup_telemetry(app, service_name)` after app construction.

## Architecture and conventions

### Two decoupled surfaces
Each service exposes two independent observability surfaces per SPEC-005:
1. **Prometheus `/metrics` pull endpoint** — always on, no external dependencies.
2. **OpenTelemetry push (opt-in)** — traces + metrics + mirrored logs pushed via OTLP HTTP/protobuf to the backend (OpenObserve). Controlled by a single `OTEL_ENABLED` flag; off by default, zero overhead when disabled.

### Structured log format
All business and request events are emitted as one JSON line at `INFO` level through `log_event(...)`. The payload shape is `{"event": <event-name>, ...domain-fields}`. Keys are sorted alphabetically via `sort_keys=True`. Because these records form the audit trail (HTTP requests, tool invocations, policy decisions), the root logger is explicitly raised to `INFO` at startup — without `configure_logging()`, uvicorn's default `WARNING` would silently drop them.

### Request correlation
- `x-request-id` is the portal-facing correlation key. It is resolved by `resolve_request_id`: inbound header → active OTel `trace_id` (when tracing is on) → `req-<uuid4>`.
- `traceparent` (W3C Trace Context) is propagated automatically by OTel instrumentation across service hops.
- When tracing is active, `x-request-id` equals the W3C `trace_id`, so a single value joins structured logs and APM traces.

### OTLP log bridge
When `OTEL_ENABLED=true`, `_attach_log_bridge` installs an OTel `LoggingHandler` on the root logger. Semantics:
- JSON stdout remains the source of truth; the OTLP mirror exists only for correlation with traces.
- Records emitted inside an active span automatically carry `trace_id`/`span_id`.
- The `opentelemetry` package's own loggers are detached (`propagate = False`) so exporter failures cannot recurse back into the bridge.
- Initialization is wrapped in try/except and fails open — setup errors are logged but never raised into the request path.

### Configuration
| Variable | Purpose | Default |
|---|---|---|
| `LOG_LEVEL` | Root logger threshold for stdout JSON audit trail | `INFO` |
| `OTEL_ENABLED` | Master gate for traces + metrics + log mirror | `false` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP HTTP base URL (exporters append `/v1/{traces,metrics,logs}`) | — |
| `OTEL_EXPORTER_OTLP_HEADERS` | Ingest auth (Basic token for OpenObserve) | — |
| `OTEL_SERVICE_NAME` | Resource service name for OTel signals | service metadata name |

### Conventions observed
- Every service has its own `core/observability.py` and `core/telemetry.py` implementing the same interface; they are copied rather than shared as a package, keeping each service self-contained.
- Business code calls `log_event(LOGGER, "http_request", method=..., status=...)` rather than calling `logger.info(json.dumps(...))` directly.
- No per-signal toggles exist — `OTEL_ENABLED` gates the entire pipeline (traces, metrics, logs).
- High-cardinality values (user ids, session ids, request ids) are never used as metric labels (per the conventions doc), though they may appear in structured log fields.
- Tests verify both `LOG_LEVEL` behavior and OTel enable/disable paths (see `test_observability.py`, `test_telemetry.py` in each product).

## Constraints enforced by the codebase

- Audit-level events must be emitted at `INFO`; services must call `configure_logging()` at startup because uvicorn defaults to `WARNING`.
- The OTel push pipeline must fail open — initialization exceptions are caught and logged, never re-raised.
- The `opentelemetry` internal loggers must be detached from the root logger to prevent recursion through the bridge.
- `x-request-id` must never be silently dropped on inbound requests; it is bridged to the active trace id when tracing is active.
- Secret material for OTel auth (`OTEL_EXPORTER_OTLP_HEADERS`) is provisioned via runtime secrets, never committed to the repository.