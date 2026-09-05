---
kind: logging_system
name: Structured JSON Logging with OpenTelemetry Log Bridge Across All Services
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
    - products/platform-gateway/src/platform_gateway/app.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/audit-service/src/audit_service/core/telemetry.py
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

The platform uses Python's standard `logging` module as the sole logging framework. Every service emits structured, single-line JSON records to stdout via a shared `log_event(logger, event, **fields)` helper in each service's `core/observability.py`. These records form the audit trail and are consumed by container log collectors; they are also mirrored into the OpenTelemetry (OTLP) log pipeline when tracing is enabled.

For distributed tracing, metrics, and log correlation, each service ships an opt-in OpenTelemetry push pipeline (`core/telemetry.py`) that initializes TracerProvider, MeterProvider, and an OTLP log bridge on top of the root logger. The OTel pipeline is gated by `OTEL_ENABLED`, defaults to disabled, and fails open — initialization errors are logged but never raised into the request path.

## Key files and packages

- Per-service `core/observability.py` — defines `configure_logging()` and `log_event()`. Present in every product: `agent-platform/src/agent_service/core/observability.py`, `platform-gateway/src/platform_gateway/core/observability.py`, `audit-service/src/audit_service/core/observability.py`, `execution-runtime/src/execution_runtime/core/observability.py`, `identity-broker/src/identity_service/core/observability.py`, `incident-service/src/incident_service/core/observability.py`, `skills-hub/src/skills_hub/core/observability.py`, `tool-gateway/src/tool_gateway/core/observability.py`.
- Per-service `core/telemetry.py` — identical copy across all services implementing the OTel push pipeline (traces, metrics, logs). Each service calls `setup_telemetry(app, SERVICE_NAME)` from its `app.py`.
- Per-service `core/request_context.py` — resolves/generates `x-request-id` for correlation.
- Shared contract: `shared/shared-contracts/observability-conventions.md` — documents the two-surface model, level policy, OTel switch semantics, cardinality rules, and correlation conventions.
- Service entrypoints (`app.py` in each product) call `configure_logging()` at startup, install an HTTP middleware that emits `http_request` events via `log_event`, then call `setup_metrics` and `setup_telemetry`.

## Architecture and conventions

### Two decoupled observability surfaces
1. **Prometheus `/metrics`** — always-on pull endpoint implemented per service via `core/metrics.py` using `prometheus_client`. Independent of OTel.
2. **OpenTelemetry push** — opt-in traces + metrics + mirrored logs pushed over OTLP HTTP/protobuf to `OTEL_EXPORTER_OTLP_ENDPOINT`. Controlled by a single `OTEL_ENABLED` flag; when false, zero OTel code is imported or initialized.

### Structured log format
Every business and request event goes through `log_event(LOGGER, "event_name", field=value, ...)`, which serializes `{"event": ..., ...}` as a single JSON line via `json.dumps(..., sort_keys=True)`. The root logger level is raised from uvicorn's default WARNING to INFO at startup so these audit records are not silently dropped; it can be overridden per deployment via `LOG_LEVEL`.

### Request correlation
- `x-request-id` is the log- and portal-facing correlation key. It is generated if absent and forwarded on every outbound call.
- When tracing is active, `x-request-id` is set to the active span's W3C `trace_id` (32 hex chars), so a single value joins structured logs and APM traces. When tracing is inactive, it falls back to `req-<uuid4>`.
- No service may silently drop an inbound correlation id.

### OTLP log bridge
When OTel is enabled, `_attach_log_bridge()` installs an `opentelemetry.instrumentation.logging.LoggingHandler` on the root logger. This mirrors every `logger.info(...)` record (including those emitted by application code) into the OTLP log stream alongside traces and metrics. The bridge:
- Treats JSON stdout as the source of truth; OTLP is a mirror for correlation.
- Automatically attaches `trace_id`/`span_id` to records emitted inside an active span.
- Detaches `opentelemetry.*` loggers from the root logger to prevent recursion if the exporter fails.
- Is itself guarded by the same `OTEL_ENABLED` switch and fails open.

### Level strategy
- Default root logger level is INFO (overridable via `LOG_LEVEL`).
- Business/request events use `INFO` via `log_event`.
- Application code uses `LOGGER.info`, `LOGGER.warning`, `LOGGER.exception` directly where appropriate (e.g., telemetry setup failures).
- There is no custom log-level enum; standard `logging` levels apply.

### Configuration
- `OTEL_ENABLED` — master gate for traces + metrics + log mirror.
- `OTEL_EXPORTER_OTLP_ENDPOINT` — OTLP HTTP base URL (exporters append `/v1/{traces,metrics,logs}`).
- `OTEL_EXPORTER_OTLP_HEADERS` — authentication headers provisioned via runtime secrets.
- `OTEL_SERVICE_NAME` — resource service name, defaults to the service's metadata name.
- `LOG_LEVEL` — overrides the root logger level.

## Conventions and constraints

- **Every FastAPI service must call `configure_logging()` before any request handling.** Observed in every `app.py`.
- **All audit-relevant events go through `log_event`**, producing a stable JSON schema with an `event` field plus domain fields. Observed for `http_request`, toolkit registration, and other domain events.
- **No unbounded label values on metrics** — cardinality rules forbid labeling on raw URLs, user IDs, session IDs, or request IDs (enforced by review per the conventions doc).
- **OTel push is off by default and fail-open.** Setup exceptions are caught and logged; the service continues without tracing.
- **Correlation ids must never be dropped.** Inbound `x-request-id` is preserved and forwarded.
- **Audit tooling reads stdout JSON only.** The OTLP mirror is secondary and must not replace container log consumption.