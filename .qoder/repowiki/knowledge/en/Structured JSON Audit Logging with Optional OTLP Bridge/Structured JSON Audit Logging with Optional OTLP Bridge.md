---
kind: logging_system
name: Structured JSON Audit Logging with Optional OTLP Bridge
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/platform-gateway/src/platform_gateway/core/request_context.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/app.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
---

## What system/approach is used

The platform uses Python's stdlib `logging` module exclusively — no third-party logging frameworks (no loguru, structlog, logzero). Each service ships a tiny, identical `core/observability.py` that exposes two functions:

- `configure_logging()` — raises the root logger from Uvicorn's default WARNING to INFO so structured audit records are never silently dropped; level can be overridden per deployment via the `LOG_LEVEL` environment variable.
- `log_event(logger, event, **fields)` — emits a single-line JSON record at INFO level: `{"event": <event>, ...fields}` serialized with `json.dumps(..., default=str, sort_keys=True)`. This is the canonical way to emit every business and request event across all services.

Business events emitted include `http_request`, `auth_login_url_requested`, `auth_login_started`, `auth_logout_requested`, `identity_normalized`, `tool_invoked`, policy decisions, ingestion results, etc. The `event` field plus domain fields form the audit trail.

An opt-in OpenTelemetry push pipeline (`core/telemetry.py`) bridges these same stdout records into an OTLP log stream when `OTEL_ENABLED=true`. A `LoggingHandler` is attached to the root logger so every `log_event` call is mirrored as an OTLP log record carrying the active span's `trace_id`/`span_id`, enabling correlation between logs and traces. The bridge is fail-open: setup errors are logged and never raised into the request path.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — authoritative spec for metrics, tracing, logging, request-correlation, and OTel switch semantics (SPEC-005).
- Per-service `core/observability.py` (identical pattern in `agent-platform`, `audit-service`, `identity-broker`, `incident-service`, `platform-gateway`, `skills-hub`, `tool-gateway`).
- Per-service `core/telemetry.py` — OTel push initialization, log bridge attachment, `current_trace_id()` helper.
- Per-service `app.py` — calls `configure_logging()` at startup, installs an HTTP middleware that emits `http_request` via `log_event`, then wires up `setup_metrics` and `setup_telemetry`.
- `platform_gateway/core/request_context.py` — resolves `x-request-id` by bridging to the active OTel trace id when tracing is on, otherwise generating `req-<uuid4>`.

## Architecture and conventions

1. **Single source of truth is stdout JSON.** Every service writes structured audit records to stdout as one JSON line per record. Log aggregation reads stdout; it is not replaced by OTLP.
2. **Audit trail lives at INFO level.** Because these records are the audit trail, `configure_logging()` forces the root logger to INFO regardless of Uvicorn's default WARNING. `LOG_LEVEL` may raise or lower it per deployment.
3. **Uniform event shape.** All business events go through `log_event(logger, "<event_name>", **fields)`, producing `{"event": ..., **fields}`. Fields like `service`, `request_id`, `method`, `path`, `status_code`, `duration_ms` are consistently included on `http_request` events.
4. **Request correlation key.** `x-request-id` is the log- and portal-facing correlation key. It is resolved via `resolve_request_id()`: inbound header wins; if absent and tracing is active, the active W3C `trace_id` is used; otherwise a generated `req-<uuid4>` is produced. No service may silently drop an inbound correlation id.
5. **Machine-facing propagation.** `traceparent` (W3C Trace Context) is propagated automatically by OpenTelemetry instrumentation across service hops.
6. **Two decoupled surfaces:** `/metrics` (pull, always-on Prometheus) and OTLP push (opt-in via `OTEL_ENABLED`). Disabling OTel has zero effect on `/metrics`.
7. **Fail-open OTel.** When OTel is enabled but the backend is unreachable or misconfigured, batch processors drop telemetry and setup exceptions are caught and logged — the request path is never broken.
8. **No recursion risk.** `opentelemetry` loggers are detached from the root logger so exporter failures cannot recurse back through the bridge.
9. **Service naming.** `OTEL_SERVICE_NAME` defaults to each service's metadata name; resource attributes carry `service.name`.

## Conventions and constraints

- **Every service must call `configure_logging()` during app startup** before any request handling begins, so INFO-level audit records survive Uvicorn's default WARNING threshold. (Enforced by the convention documented in each `observability.py` docstring.)
- **All business and request events must be emitted via `log_event(...)` at INFO level**, never via bare `logger.info("...")` string formatting. (Specified in `shared/shared-contracts/observability-conventions.md` under "Structured Logging Levels".)
- **OTel push is controlled by a single master switch `OTEL_ENABLED`** (truthy values: `1`, `true`, `yes`, `on`); there are no per-signal toggles. (Defined in `observability-conventions.md`.)
- **OTLP endpoint, headers, and service name** come from `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`, and `OTEL_SERVICE_NAME`; secrets are provisioned via runtime-secrets and never committed.
- **Cardinality rules apply to metrics labels** (bounded enums only; never raw URLs, user ids, session ids, request ids) — this constrains what may appear as metric labels, while log fields remain free-form JSON.
- **`x-request-id` must never be silently dropped** on inbound requests; it is preserved and forwarded on outbound calls. (Constrained by the request-context resolution logic.)
- **When tracing is active, `x-request-id` is set to the active span's W3C `trace_id`**, so a single value joins structured logs and APM traces. (Documented in the observability conventions.)
- **Prometheus metrics use `<service>_<noun>_<unit>` snake_case naming** with `_total` suffix on counters, prefixed by the short service name (`gateway`, `identity`, `agent`, etc.). (Defined in `observability-conventions.md`.)