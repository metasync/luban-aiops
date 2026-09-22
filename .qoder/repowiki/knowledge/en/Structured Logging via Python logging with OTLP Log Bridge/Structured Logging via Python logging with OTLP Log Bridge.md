---
kind: logging_system
name: Structured Logging via Python logging with OTLP Log Bridge
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/agent-platform/src/agent_service/app.py
    - products/audit-service/src/audit_service/app.py
    - products/platform-gateway/tests/test_observability.py
---

## What system/approach is used

The platform uses Python's built-in `logging` module as the sole logging framework. Each product service ships an identical `core/observability.py` that provides two functions:
- `configure_logging()` — raises the root logger from uvicorn's default WARNING to INFO (so audit-trail records are not silently dropped) and reads the effective level from the `LOG_LEVEL` environment variable.
- `log_event(logger, event, **fields)` — emits a single-line JSON record at INFO level by serializing `{"event": event, ...fields}` with `json.dumps(..., default=str, sort_keys=True)`.

OpenTelemetry is layered on top as an opt-in push pipeline (`OTEL_ENABLED`). When enabled, `setup_telemetry()` attaches an OTel `LoggingHandler` to the root logger so every structured log line is mirrored over OTLP HTTP/protobuf to the configured backend (OpenObserve). The bridge is gated by the same switch, fails open, and detaches `opentelemetry` loggers from the root logger to prevent recursion.

There is no third-party structured-logging library (no structlog, loguru, or python-json-logger); all services conform to the shared contract in `shared/shared-contracts/observability-conventions.md`.

## Key files and packages

- Per-service configuration: `products/<service>/src/<service_package>/core/observability.py` (identical across agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway).
- Per-service bootstrap: `products/*/src/*/app.py` calls `configure_logging()` early in startup and logs a startup event via `log_event`.
- OTel integration: `products/agent-platform/src/agent_service/core/telemetry.py` — the only place that wires traces, metrics, and the log bridge; other services follow the same pattern via their own telemetry modules.
- Shared contract: `shared/shared-contracts/observability-conventions.md` — documents the two-surface model, metric naming, cardinality rules, OTel switch semantics, structured logging levels, request correlation, and backend relationship.
- Tests exercising the convention: `test_observability.py` in each product verifies that `LOG_LEVEL` overrides work and that `configure_logging()` restores defaults.

## Architecture and conventions

1. **Uniform per-service observability module.** Every product exposes `core/observability.configure_logging` and `log_event`. New services copy this file rather than re-implementing it.
2. **Audit trail = INFO-level structured JSON.** Business events (http_request, tool_invoked, policy decisions, handoff rejections, session lifecycle) are emitted through `log_event` at INFO. Uvicorn's default WARNING root level would drop them, so `configure_logging()` explicitly sets the root level to INFO (overridable via `LOG_LEVEL`).
3. **Single-line JSON records.** `log_event` builds a dict with an `event` key plus arbitrary fields, then dumps it with sorted keys and string coercion for non-serializable values. Consumers parse stdout lines as JSON.
4. **Two decoupled surfaces.** `/metrics` (Prometheus pull, always on) and OpenTelemetry push (opt-in via `OTEL_ENABLED`). Disabling OTel leaves stdout logging and `/metrics` fully functional.
5. **OTLP log bridge mirrors stdout.** When OTel is enabled, the bridge exports the same records over OTLP so they can be correlated with traces via automatic trace/span context attachment. Stdout remains the source of truth; OTLP is a mirror.
6. **Request correlation.** `x-request-id` is the log- and portal-facing correlation key; when tracing is active it is set to the active span's W3C `trace_id`, otherwise falls back to `req-<uuid4>`. Outbound calls forward both `x-request-id` and `traceparent`.
7. **Fail-open design.** Missing/misconfigured OTLP endpoints produce export-time errors that are logged but never raised into the request path. Batch processors drop failed telemetry.
8. **Cardinality rules for metrics** (related observability concern): use bounded enum labels only; never label on raw URLs, user ids, session ids, or request ids.

## Conventions and constraints

- **Every service must call `configure_logging()` at app startup.** Verified by tests in each product that patch `LOG_LEVEL` and assert the root logger level changes accordingly.
- **Business events go through `log_event`, not direct `logger.info(...)` calls.** This ensures consistent JSON shape and audit-trail reliability.
- **Default log level is INFO and must stay INFO.** The `LOG_LEVEL` env var may override it per deployment, but the default cannot be lowered because audit records would be silently discarded by uvicorn.
- **OTel push is off by default.** Controlled solely by `OTEL_ENABLED`; there are no per-signal toggles. When disabled, zero OTel providers or instrumentation are initialized.
- **No unbounded label cardinality on metrics.** Enforced by review per the shared conventions document.
- **Correlation headers must not be silently dropped.** Inbound `x-request-id` / `traceparent` must be preserved and forwarded on outbound calls.
- **OTLP authentication is provisioned via runtime secrets**, never committed to the repo; the endpoint and headers come from `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_EXPORTER_OTLP_HEADERS`.