---
kind: logging_system
name: Structured JSON Audit Logging with OpenTelemetry Log Bridge
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/audit-service/src/audit_service/core/telemetry.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/telemetry.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/identity-broker/src/identity_service/core/observability.py
---

## What system/approach is used

The platform uses Python's stdlib `logging` module as the sole logging framework. Every service emits **single-line JSON audit records** via a shared `log_event(logger, event, **fields)` helper that serializes `{"event": ..., ...fields}` with `json.dumps(..., default=str, sort_keys=True)`. There is no third-party structured-logging library (no structlog, loguru, or python-json-logger); the pattern is hand-rolled and duplicated identically in each product.

Structured logs are mirrored into an **opt-in OpenTelemetry push pipeline** (traces + metrics + logs) via `opentelemetry.instrumentation.logging.handler.LoggingHandler`, which attaches to the root logger when `OTEL_ENABLED=true`. The OTLP bridge exports over HTTP/protobuf to `OTEL_EXPORTER_OTLP_ENDPOINT` (OpenObserve ingest contract `/api/{org}/v1/{signal}`), authenticated via `OTEL_EXPORTER_OTLP_HEADERS`. The stdout JSON stream remains the source of truth for the audit trail; the OTLP mirror exists only so backend tools can correlate logs with traces using automatic `trace_id`/`span_id` attachment.

## Key files and packages

- Per-service `core/observability.py` — defines `configure_logging()` (raises root logger from uvicorn's WARNING default to INFO via `LOG_LEVEL`) and `log_event()` (JSON serialization). Identical across all services: `agent-platform`, `platform-gateway`, `audit-service`, `execution-runtime`, `incident-service`, `skills-hub`, `tool-gateway`, `identity-broker`.
- Per-service `core/telemetry.py` — opt-in OTel setup (`setup_telemetry(app, service_name)`), guarded by `OTEL_ENABLED`; installs FastAPI and HTTPX instrumentation, sets up trace/metric providers, and attaches the OTLP log bridge via `_attach_log_bridge`.
- `shared/shared-contracts/observability-conventions.md` — the authoritative spec documenting the two-surface model (`/metrics` pull always-on, OTel push opt-in), metric naming, cardinality rules, OTel switch semantics, structured logging levels, OTLP log bridge behavior, and request-correlation bridging between `x-request-id` and W3C `traceparent`.
- Service entry points call both `configure_logging()` and `setup_telemetry(app, metadata.service_name)` at startup (e.g. `products/agent-platform/src/agent_service/app.py`, `products/platform-gateway/src/platform_gateway/app.py`).

## Architecture and conventions

- **Two decoupled surfaces**: Prometheus `/metrics` (always on, local scrape) and OTel push (opt-in, zero overhead when disabled). Disabling OTel never affects `/metrics`.
- **Audit records are INFO-level JSON**: every business/event record goes through `log_event(...)`, emitted at INFO level. Services explicitly raise the root logger from uvicorn's WARNING default because otherwise these records would be silently discarded.
- **Level override**: `LOG_LEVEL` environment variable controls the root logger level per deployment; the default must stay INFO so audit records are never dropped.
- **OTel push is fully gated**: `OTEL_ENABLED` (truthy values: `1`, `true`, `yes`, `on`) switches on traces, metrics, and the log mirror together. Missing/unreachable backend fails open — setup errors are logged, never raised into the request path.
- **Request correlation**: `x-request-id` is the log/portal-facing key; when tracing is active it is set to the active span's W3C `trace_id` (via `current_trace_id()` in telemetry), otherwise falls back to `req-<uuid4>`. No service may drop an inbound correlation id.
- **Metric naming**: `<service>_<noun>_<unit>` snake_case, counters end in `_total`, bounded enum labels only (never raw URLs, user ids, session ids, request ids).
- **Service identity**: `OTEL_SERVICE_NAME` overrides the resource `service.name`; defaults to the service's metadata name.
- **Secrets**: `OTEL_EXPORTER_OTLP_HEADERS` (Basic auth for OpenObserve) provisioned via `sync-otel-secrets.sh` into runtime secrets, never committed.

## Conventions and constraints

- All business and request events MUST be emitted as single-line JSON via `log_event(...)` at INFO level — this is documented as the audit trail contract in `observability-conventions.md` and enforced by every service's `configure_logging()` raising the root logger to INFO.
- Structured fields are passed as keyword arguments to `log_event`; they are serialized with `default=str` and `sort_keys=True` so output is deterministic and parseable even if non-serializable types leak.
- Cardinality rule: never use unbounded values (raw URL, user id, session id, request id) as metric labels — enforced by review per the conventions doc.
- No service may silently drop an inbound correlation id (`x-request-id` / `traceparent`).
- The OTLP log bridge is attached once per process (`_log_bridge_attached` guard); OTel's own loggers are detached from the root logger (`propagate = False`) so exporter failures cannot recurse back into the bridge.
- Fail-open guarantee: missing/invalid OTel credentials produce export-time 401s that batch processors drop; initialization failures are caught and logged rather than raised.