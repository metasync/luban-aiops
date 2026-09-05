---
kind: logging_system
name: Structured JSON Logging with Opt-in OpenTelemetry Log Bridge
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/audit-service/src/audit_service/core/telemetry.py
    - products/execution-runtime/src/execution_runtime/core/telemetry.py
    - products/identity-broker/src/identity_service/core/telemetry.py
    - products/incident-service/src/incident_service/core/telemetry.py
    - products/skills-hub/src/skills_hub/core/telemetry.py
    - products/tool-gateway/src/tool_gateway/core/telemetry.py
---

## What system/approach is used

The platform uses Python's stdlib `logging` module as the sole logging framework. Every service emits **single-line JSON** structured log records at `INFO` level, produced via a shared `log_event(logger, event, **fields)` helper that serializes `{"event": ..., **fields}` with `json.dumps(..., default=str, sort_keys=True)`. This JSON stream on stdout is declared the **source of truth for the audit trail**. An opt-in OpenTelemetry (OTel) push pipeline mirrors those same records to an OTLP backend (OpenObserve) by attaching an OTel `LoggingHandler` to the root logger; the bridge is gated by `OTEL_ENABLED` and fails open.

## Key files and packages

- `products/agent-platform/src/agent_service/core/observability.py` — defines `configure_logging()` (raises root logger from uvicorn's WARNING to INFO, overridable via `LOG_LEVEL`) and `log_event()` (structured JSON emitter).
- `products/*/core/telemetry.py` — one identical copy per service (`platform-gateway`, `audit-service`, `execution-runtime`, `identity-broker`, `incident-service`, `skills-hub`, `tool-gateway`). Each provides:
  - `is_enabled()` / `setup_telemetry(app, service_name)` — initializes TracerProvider, MeterProvider, FastAPI/HTTPX instrumentation, and the OTel log bridge.
  - `_attach_log_bridge(resource)` — installs `opentelemetry.instrumentation.logging.handler.LoggingHandler` on the root logger, detaches `opentelemetry.*` loggers to prevent recursion.
  - `current_trace_id()` — returns the active span's W3C trace id when tracing is active.
- `shared/shared-contracts/observability-conventions.md` — the authoritative spec documenting the two-surface model (`/metrics` pull + OTel push), environment variables, structured logging levels, request correlation rules, and cardinality constraints.

## Architecture and conventions

1. **Two decoupled observability surfaces** (per SPEC-005):
   - `/metrics` (Prometheus pull, always on, implemented with `prometheus_client`).
   - OTel push (opt-in, disabled by default). Disabling OTel has zero effect on `/metrics`.
2. **Log level strategy**: Uvicorn starts the root logger at `WARNING`; every service calls `configure_logging()` at startup to raise it to `INFO` so audit events are not silently dropped. The effective level is controlled by `LOG_LEVEL`.
3. **Structured record shape**: business/request events go through `log_event(logger, "event_name", field=value, ...)` which produces a single JSON line with keys `event` plus the supplied fields, sorted and stringified.
4. **OTel log bridge**: When `OTEL_ENABLED=true`, each service attaches an OTel `LoggingHandler` to the root logger so every `logger.info(json.dumps(...))` call is also exported as an OTLP log record. Trace/span context is automatically attached, enabling correlation between logs, traces, and metrics in the backend.
5. **Environment-driven configuration**:
   - `OTEL_ENABLED` — master gate (truthy values: `1`, `true`, `yes`, `on`).
   - `OTEL_EXPORTER_OTLP_ENDPOINT` — OTLP HTTP base URL (exporters append `/v1/{traces,metrics,logs}`).
   - `OTEL_EXPORTER_OTLP_HEADERS` — authentication headers provisioned via runtime secrets.
   - `OTEL_SERVICE_NAME` — resource service name, defaults to service metadata.
6. **Request correlation**: `x-request-id` is the log/portal-facing correlation key; when tracing is active it is set to the active span's W3C `trace_id`, otherwise falls back to `req-<uuid4>`. `traceparent` (W3C Trace Context) is propagated automatically by OTel instrumentation across service hops.
7. **Fail-open design**: OTel setup errors are caught and logged; they never propagate into the request path. Missing/malconfigured backends cause export-time drops, not service failures.
8. **Cardinality rules**: labels must be bounded enums; raw URLs, user ids, session ids, and request ids are prohibited as labels.

## Conventions and constraints

- **Every service must call `configure_logging()` at app startup** to ensure the root logger level is at least `INFO` (enforced by the convention doc and present in all services' entry points).
- **All business and request events must be emitted as single-line JSON via `log_event` at `INFO` level**; these records form the audit trail and cannot be silenced by changing the default level.
- **OTel push is off by default** and must be explicitly enabled via `OTEL_ENABLED`; no per-signal toggles exist.
- **JSON stdout remains the source of truth**; the OTLP mirror is supplemental for correlation and must not replace container log consumers.
- **No service may silently drop an inbound correlation id** (`x-request-id` / `traceparent`).
- **Unbounded label cardinality is forbidden** (raw URLs, user/session/request ids); violations are rejected at review per the conventions document.