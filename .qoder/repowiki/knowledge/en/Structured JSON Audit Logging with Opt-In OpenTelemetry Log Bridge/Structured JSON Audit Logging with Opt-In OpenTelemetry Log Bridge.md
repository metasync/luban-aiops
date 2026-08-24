---
kind: logging_system
name: Structured JSON Audit Logging with Opt-In OpenTelemetry Log Bridge
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/audit-service/src/audit_service/app.py
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/agent-platform/src/agent_service/app.py
    - products/tool-gateway/src/tool_gateway/core/telemetry.py
    - products/tool-gateway/src/tool_gateway/app.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/incident-service/src/incident_service/api/routes/webhooks.py
---

## What system/approach is used

The platform uses Python's stdlib `logging` module as the sole logging framework. Every product service (agent-platform, audit-service, identity-broker, incident-service, platform-gateway, tool-gateway, skills-hub) follows an identical pattern: a per-product `core/observability.py` exposes two functions — `configure_logging()` and `log_event(logger, event, **fields)` — that are imported into each service's `app.py`. Structured logs are single-line JSON emitted at `INFO` level via `json.dumps(payload, default=str, sort_keys=True)`, making them machine-parseable and suitable for an audit trail.

OpenTelemetry is integrated as an **opt-in** push pipeline (`OTEL_ENABLED`). When enabled, each service attaches an OTel `LoggingHandler` to the root logger so every structured record is mirrored over OTLP HTTP/protobuf to the configured backend (OpenObserve). The stdout JSON remains the source of truth; the OTLP mirror exists only to correlate logs with traces via automatic `trace_id`/`span_id` attachment.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — authoritative specification defining the two-surface model (Prometheus `/metrics` always-on + OTel push opt-in), environment variables, log levels, correlation rules, and cardinality constraints. All services reference this doc.
- Per-product `core/observability.py` (e.g. `products/platform-gateway/src/platform_gateway/core/observability.py`, `products/audit-service/src/audit_service/core/observability.py`, `products/agent-platform/src/agent_service/core/observability.py`) — identical implementations of `configure_logging()` (raises root logger from uvicorn's WARNING default to INFO, overridable via `LOG_LEVEL`) and `log_event(...)`.
- Per-product `core/telemetry.py` (e.g. `products/tool-gateway/src/tool_gateway/core/telemetry.py`, `products/agent-platform/src/agent_service/core/telemetry.py`) — `setup_telemetry(app, service_name)` initializes TracerProvider, MeterProvider, FastAPI/HTTPX instrumentation, and the OTel log bridge; guarded by `OTEL_ENABLED`; fails open on setup errors.
- Each product's `app.py` calls `configure_logging()`, registers an HTTP middleware that emits `http_request` events via `log_event`, then calls `setup_metrics(app)` and `setup_telemetry(app, SERVICE_NAME)`.
- `core/request_context.py` in each product resolves/generates `x-request-id` and bridges it to the active W3C `traceparent` when tracing is active.

## Architecture and conventions

1. **Two decoupled surfaces.** Prometheus `/metrics` (pull, always on) and OpenTelemetry push (opt-in) never depend on each other. Disabling OTel leaves metrics fully functional.
2. **Structured audit log format.** Business and request events go through `log_event(logger, "event_name", field=value, ...)`, which serializes `{"event": ..., **fields}` to a single JSON line at INFO. This is the audit trail; every service raises the root logger to INFO at startup because uvicorn defaults to WARNING and would silently drop these records.
3. **Request correlation.** `x-request-id` is the log- and portal-facing correlation key. It is generated if absent and forwarded on outbound calls. When tracing is active, `x-request-id` is set to the active span's W3C `trace_id` so a single value joins logs and APM traces. No service may silently drop an inbound correlation id.
4. **OTLP log bridge semantics.** When `OTEL_ENABLED=true`, the root logger gets an OTel `LoggingHandler` that mirrors every record to the OTLP log pipeline. The `opentelemetry` internal loggers are detached (`propagate = False`) so exporter failures cannot recurse back into the bridge. Trace/span association is automatic inside active spans.
5. **Environment-driven configuration.**
   - `LOG_LEVEL` — overrides the root logger level (default INFO).
   - `OTEL_ENABLED` — master gate for traces + metrics + log mirror (default false).
   - `OTEL_EXPORTER_OTLP_ENDPOINT` — OTLP HTTP base URL (exporters append `/v1/{traces,metrics,logs}`).
   - `OTEL_EXPORTER_OTLP_HEADERS` — authentication headers provisioned via runtime secrets.
   - `OTEL_SERVICE_NAME` — resource service name, defaults to the service's metadata name.
6. **Fail-open design.** OTel setup errors are caught and logged; they never raise into the request path. Missing/invalid credentials produce export-time 401s dropped by batch processors.
7. **Metric naming convention** (from the shared spec): `<service>_<noun>_<unit>` snake_case, counters suffixed `_total`, bounded enum labels only, no high-cardinality labels (raw URLs, user ids, session ids, request ids).

## Conventions and constraints

- **Every service must call `configure_logging()` before any request handling** — observed in every product's `create_app()` / `app.py` entry point.
- **All business/request events must use `log_event(...)`**, not raw `logger.info("...")` — ensures consistent JSON shape with an `event` discriminator field.
- **Audit records must be INFO level** — the spec mandates raising the root logger from uvicorn's WARNING default to INFO so audit records are never silently discarded; `LOG_LEVEL` may override but the default must stay INFO.
- **No unbounded label cardinality** — the observability conventions explicitly forbid labeling on raw request URLs, user ids, session ids, or request ids; domain counters must use bounded enum labels.
- **OTel push is off by default** — `OTEL_ENABLED` must remain false unless explicitly enabled; initialization is wrapped in try/except so misconfiguration never breaks the service.
- **Stdout JSON is the source of truth** — the OTLP log mirror is secondary; audit tooling must keep reading container stdout, not the OTLP stream.
- **Correlation header forwarding is mandatory** — no service may silently drop an inbound `x-request-id` or `traceparent`.
- **Secrets for OTel auth live only in runtime-secrets** — `OTEL_EXPORTER_OTLP_HEADERS` is provisioned by `sync-otel-secrets.sh` and must never be committed or placed in ConfigMaps.