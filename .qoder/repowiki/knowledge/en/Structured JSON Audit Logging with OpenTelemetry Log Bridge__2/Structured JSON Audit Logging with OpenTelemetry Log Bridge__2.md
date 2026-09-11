---
kind: logging_system
name: Structured JSON Audit Logging with OpenTelemetry Log Bridge
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/tool-gateway/src/tool_gateway/core/telemetry.py
---

## What system/approach is used

The platform uses Python's standard `logging` module as the sole logging framework. Each service defines an identical `core/observability.py` that provides two functions:
- `configure_logging()` — raises the root logger from Uvicorn's default WARNING to INFO (overridable via the `LOG_LEVEL` environment variable) so structured audit records are never silently dropped.
- `log_event(logger, event, **fields)` — emits a single-line JSON object at INFO level with a required `event` field plus arbitrary domain fields, serialized via `json.dumps(..., default=str, sort_keys=True)`.

There is no third-party logging library (no structlog, loguru, or similar). Structured logs are plain JSON lines on stdout and serve as the canonical audit trail for every product service.

An opt-in OpenTelemetry push pipeline (`core/telemetry.py`, enabled by `OTEL_ENABLED`) attaches an OTel `LoggingHandler` to the root logger so every `INFO` record is mirrored to the OTLP log exporter (`OTEL_EXPORTER_OTLP_ENDPOINT`). The bridge is gated by the same switch, fails open, and detaches `opentelemetry`'s own loggers from the root logger to prevent recursion when exporters fail.

## Key files and packages

- Per-service observability module: `products/*/src/*_service/core/observability.py` (agent-platform, platform-gateway, tool-gateway, audit-service, identity-broker, incident-service, skills-hub, execution-runtime).
- Per-service telemetry module: `products/*/src/*_service/core/telemetry.py` — initializes traces, metrics, and the log bridge; exposes `is_enabled()`, `setup_telemetry(app, service_name)`, `current_trace_id()`.
- Shared contract: `shared/shared-contracts/observability-conventions.md` — documents the two-surface model (/metrics pull + OTel push), environment variables, metric naming, cardinality rules, structured logging levels, OTLP log bridge semantics, and request-correlation bridging between `x-request-id` and W3C `traceparent`.
- Service entry points call `configure_logging()` during startup and use `log_event(LOGGER, ...)` throughout API routes and services (e.g., `identity_service/api/routes/auth.py`, `audit_service/api/routes/ingest.py`, `execution_runtime/api/routes/handoff.py`).

## Architecture and conventions

1. **Two decoupled surfaces.** Every service exposes `/metrics` (Prometheus pull, always on) independently of the OpenTelemetry push pipeline. Disabling OTel has zero effect on `/metrics`.
2. **Single source of truth for logs.** JSON lines on stdout are the authoritative audit trail. The OTLP mirror exists only so a backend can correlate logs with traces; consumers must keep reading stdout.
3. **Event-driven structured schema.** All business/request events go through `log_event`, producing `{"event": <name>, ...fields}`. Event names are camelCase identifiers such as `auth_login_url_requested`, `tool_invoked`, `policy_decision`, `http_request`. Fields carry domain context (e.g., `request_id`, `decision`, `result`).
4. **Level policy.** INFO is the default minimum level for audit records; `LOG_LEVEL` overrides per deployment but must remain INFO in production defaults so records are not discarded. Uvicorn's WARNING default is explicitly raised at startup.
5. **Request correlation.** `x-request-id` is the log- and portal-facing key; `traceparent` (W3C Trace Context) is the machine-facing propagation header. When tracing is active, `x-request-id` is set to the active span's W3C `trace_id` so a single value joins structured logs and APM traces. No service may silently drop an inbound correlation id.
6. **Environment configuration.**
   - `LOG_LEVEL` — root logger threshold.
   - `OTEL_ENABLED` — master gate for traces + metrics + log mirror (default false).
   - `OTEL_EXPORTER_OTLP_ENDPOINT` — OTLP HTTP base URL (exporters append `/v1/{traces,metrics,logs}`).
   - `OTEL_EXPORTER_OTLP_HEADERS` — Basic auth headers provisioned via runtime secrets.
   - `OTEL_SERVICE_NAME` — resource service name, defaults to service metadata.
7. **Fail-open design.** OTel setup errors are logged and swallowed; missing/invalid credentials produce export-time drops, never request failures.
8. **Cardinality rules for metrics** (from the shared convention doc): bounded enum labels only; never label on raw URLs, user ids, session ids, or request ids.

## Conventions and constraints

- **Every service must call `configure_logging()` at app startup** so INFO-level structured events survive Uvicorn's default WARNING filter. This is enforced by the shared convention document and duplicated identically across all eight product services.
- **All audit/business events must be emitted via `log_event(...)` at INFO level**, never via ad-hoc `print` or unstructured `logger.info("...")`. The convention explicitly calls these records the "audit trail" and requires them to be single-line JSON.
- **OTel push is opt-in and off by default.** It is controlled exclusively by `OTEL_ENABLED`; there are no per-signal toggles. When disabled, no providers or instrumentation are initialized (zero overhead).
- **No high-cardinality labels on metrics.** Raw request URLs, user ids, session ids, and request ids are prohibited as labels per the shared convention; violations are rejected at review.
- **Correlation ids must propagate.** No service may silently drop an inbound `x-request-id`; when tracing is active it must be bridged to the W3C `trace_id`.
- **Secrets for OTel auth** (`OTEL_EXPORTER_OTLP_HEADERS`) are provisioned into runtime secrets by `sync-otel-secrets.sh` and must never be committed or placed in ConfigMaps.
- **Service-to-service propagation:** outbound HTTP calls are instrumented via `HTTPXClientInstrumentor`, so spans and trace context flow automatically across service boundaries.