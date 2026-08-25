---
kind: logging_system
name: Structured JSON Logging with OpenTelemetry OTLP Bridge
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/agent-platform/src/agent_service/app.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/audit-service/src/audit_service/core/telemetry.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
---

## What system/approach is used

The platform uses Python's standard `logging` module as the sole logging framework. Every service emits **single-line JSON** records to stdout via a shared `log_event(logger, event, **fields)` helper defined in each product's `core/observability.py`. Business and request events (HTTP requests, tool invocations, policy decisions) are emitted at **INFO** level so they survive uvicorn's default WARNING root level.

When tracing is enabled, an OpenTelemetry `LoggingHandler` is attached to the root logger, mirroring every structured record over OTLP HTTP/protobuf to the configured backend (OpenObserve). The OTLP mirror is explicitly documented as secondary — **JSON stdout remains the source of truth** for audit tooling.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — the authoritative specification defining log levels, correlation headers, OTel switch semantics, and the two-surface model (`/metrics` pull + opt-in OTLP push).
- Per-service `core/observability.py` (e.g. `products/agent-platform/src/agent_service/core/observability.py`, `products/platform-gateway/src/platform_gateway/core/observability.py`, `products/audit-service/src/audit_service/core/observability.py`) — identical implementations providing:
  - `configure_logging()` — raises root logger from uvicorn's WARNING to INFO (overridable via `LOG_LEVEL`).
  - `log_event(logger, event, **fields)` — serializes `{"event": ..., **fields}` as sorted JSON at INFO.
- Per-service `core/telemetry.py` — identical implementations providing:
  - `setup_telemetry(app, service_name)` — initializes TracerProvider, MeterProvider, FastAPI/HTTPX instrumentation, and attaches the OTLP log bridge when `OTEL_ENABLED` is true.
  - `_attach_log_bridge(resource)` — adds `opentelemetry.instrumentation.logging.handler.LoggingHandler` to the root logger; detaches `opentelemetry.*` loggers to prevent recursion.
  - `current_trace_id()` — returns the active W3C `trace_id` for correlation.
- Service entrypoints call `configure_logging()` early in `app.py` (e.g. `products/agent-platform/src/agent_service/app.py:50`, `products/audit-service/src/audit_service/app.py:44`, `products/platform-gateway/src/platform_gateway/app.py`).

## Architecture and conventions

1. **Two decoupled surfaces**: `/metrics` (Prometheus pull, always on) and OTLP push (opt-in via `OTEL_ENABLED`). Disabling OTel has zero impact on `/metrics` or stdout logs.
2. **Structured log shape**: every business event is a single JSON line with an `event` field plus domain fields, produced by `log_event`. Fields are serialized with `json.dumps(..., default=str, sort_keys=True)`.
3. **Log level strategy**: root logger is raised to INFO at startup so audit records are never silently discarded; `LOG_LEVEL` overrides per deployment.
4. **Request correlation**: `x-request-id` is the log- and portal-facing key; when tracing is active it is set to the active span's W3C `trace_id`, otherwise falls back to `req-<uuid4>`. No service may drop an inbound correlation id.
5. **OTLP log bridge**: attached once per process via `_attach_log_bridge`; records inside an active span automatically carry `trace_id`/`span_id`, joining logs to traces on the same W3C id that backs `x-request-id`. Exporter failures cannot recurse into the bridge because `logging.getLogger("opentelemetry").propagate = False`.
6. **Fail-open**: all OTel initialization is wrapped in try/except; setup errors are logged and the service continues without push.
7. **Service naming**: `OTEL_SERVICE_NAME` defaults to the service's metadata name; metric names use `<service>_<noun>_<unit>` snake_case with bounded enum labels.

## Conventions and constraints

- **All business/request events must go through `log_event`** at INFO level — this is the audit trail contract described in `observability-conventions.md`.
- **Never label metrics on unbounded values** (raw URL, user id, session id, request id); only bounded enum labels are allowed.
- **OTel push is off by default** (`OTEL_ENABLED` defaults false); credentials come from `OTEL_EXPORTER_OTLP_HEADERS` provisioned via runtime secrets, never committed.
- **Stdout JSON is the canonical sink**; OTLP is a mirror for trace correlation, not a replacement.
- **Correlation header rule**: `x-request-id` must be preserved across hops; when tracing is active it equals the W3C `trace_id`, otherwise a generated UUID.
- **No per-signal toggles**: one `OTEL_ENABLED` flag gates traces, metrics, and log mirror together.