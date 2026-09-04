---
kind: logging_system
name: Structured JSON Logging with OpenTelemetry Log Bridge Across All Services
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
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/audit-service/src/audit_service/core/telemetry.py
---

## What system/approach is used

Every Python service in the platform uses the standard library `logging` module to emit **single-line, sorted-key JSON** audit records. There is no third-party logging framework (no loguru, structlog, or gunicorn access-log formatter). Each product ships its own tiny `core/observability.py` that exposes two functions:

- `configure_logging()` — raises the root logger from uvicorn's default WARNING level to INFO so structured audit events are not silently dropped; the level is overridable per deployment via the `LOG_LEVEL` environment variable.
- `log_event(logger, event, **fields)` — serializes `{"event": <name>, ...fields}` as a single `json.dumps(..., sort_keys=True)` line at INFO level.

Business and request events across all services (`http_request`, `tool_invoked`, `policy_decision`, `auth_login_started`, `token_delegated`, `handoff_rejected`, etc.) go through this helper rather than calling `logger.info` directly, which enforces a uniform schema for the audit trail.

OpenTelemetry is an **opt-in mirror**: when `OTEL_ENABLED=1`, each service attaches an OTel `LoggingHandler` to the root logger so every structured record is also exported as an OTLP log record alongside traces and metrics. The stdout JSON remains the source of truth for the audit trail; the OTLP bridge exists only to correlate logs with traces via automatic trace/span id attachment. OTel setup is wrapped in try/except and fails open — exporter failures never break requests.

## Key files and packages

- Per-service logging init: `products/*/src/*/core/observability.py` — identical `configure_logging` / `log_event` pattern in agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway.
- Per-service telemetry bridge: `products/*/src/*/core/telemetry.py` — opt-in OTLP push pipeline gated by `OTEL_ENABLED`, exporting traces, metrics, and mirrored logs to `OTEL_EXPORTER_OTLP_ENDPOINT`.
- Shared conventions: `shared/shared-contracts/observability-conventions.md` — documents the two-surface model, metric naming, cardinality rules, OTel switch semantics, structured logging levels, OTLP log bridge behavior, and request-correlation bridging between `x-request-id` and W3C `traceparent`.
- Service entrypoints call `configure_logging()` early in startup (e.g. `agent_service/app.py`, `audit_service/app.py`, `execution_runtime/app.py`, `identity_service/app.py`, `incident_service/app.py`, `platform_gateway/app.py`, `skills_hub/app.py`, `tool_gateway/app.py`).

## Architecture and conventions

1. **Single sink first.** All business events are emitted as one JSON line on stdout via `log_event`. This is the authoritative audit stream; downstream consumers read container stdout, not OTLP.
2. **Root logger raised to INFO at startup.** Uvicorn initializes the root logger at WARNING, which would drop every `log_event` record. Every service calls `configure_logging()` during app bootstrap to set the root level to INFO (overridable via `LOG_LEVEL`).
3. **Uniform event schema.** `log_event` always wraps fields into `{"event": ..., **fields}` and sorts keys deterministically, making parsing stable across services.
4. **Opt-in OTLP log bridge.** When `OTEL_ENABLED` is true, `_attach_log_bridge` installs an OTel `LoggingHandler` on the root logger and detaches the `opentelemetry` internal loggers to prevent recursion. Records emitted inside an active span automatically carry `trace_id`/`span_id`, joining them to the same W3C trace that backs `x-request-id`.
5. **Fail-open design.** OTel initialization errors are caught and logged; missing/unreachable backends do not raise into the request path. Disabling OTel leaves `/metrics` and stdout logging fully functional.
6. **Request correlation.** `x-request-id` is the log- and portal-facing correlation key. When tracing is active it is set to the active span's W3C `trace_id`; otherwise it falls back to `req-<uuid4>`. No service may silently drop an inbound correlation id.
7. **No per-signal toggles.** One `OTEL_ENABLED` flag gates traces + metrics + log mirror together; there are no separate switches for individual signal types.

## Conventions and constraints

- **All business/request events must use `log_event`**, not raw `logger.info`, so they share the `{"event": ..., ...fields}` JSON shape enforced by the shared helper.
- **The root logger level must be raised to INFO at startup** via `configure_logging()`; relying on uvicorn's default WARNING level will discard audit records.
- **Audit records are INFO-level single-line JSON**; higher verbosity can be enabled per-deployment by setting `LOG_LEVEL` to DEBUG or TRACE.
- **Never label Prometheus metrics with unbounded values** (raw URL, user id, session id, request id) — bounded enum labels only — as documented in the observability conventions.
- **OTLP endpoint and auth come from environment:** `OTEL_EXPORTER_OTLP_ENDPOINT` (with exporters appending `/v1/{traces,metrics,logs}`), `OTEL_EXPORTER_OTLP_HEADERS` (Basic-auth for OpenObserve), and `OTEL_SERVICE_NAME` (defaults to service metadata name).
- **Trace/span association is automatic** when a span is active; no manual injection of trace ids into log fields is needed.
- **Exporter failures must not recurse:** the `opentelemetry` loggers are explicitly detached from the root logger to prevent infinite loops if the OTLP backend is down.
- **Services only expose `/metrics` and push OTLP**; scraping, storage, dashboards, and alerting are platform-ops concerns outside the service contract.