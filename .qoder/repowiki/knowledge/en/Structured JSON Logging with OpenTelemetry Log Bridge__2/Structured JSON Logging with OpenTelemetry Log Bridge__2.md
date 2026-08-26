---
kind: logging_system
name: Structured JSON Logging with OpenTelemetry Log Bridge
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/platform-gateway/src/platform_gateway/core/request_context.py
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/agent-platform/src/agent_service/core/request_context.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/telemetry.py
---

## What system/approach is used

The platform uses Python's standard `logging` module as the sole logging framework. Each service ships a tiny, identical `core/observability.py` that exposes two functions:

- `configure_logging()` — raises the root logger from Uvicorn's default `WARNING` to `INFO` so structured audit records are not silently dropped; the level is read from the `LOG_LEVEL` environment variable (default `INFO`).
- `log_event(logger, event, **fields)` — serializes `{"event": event, ...fields}` to a single-line JSON string via `json.dumps(..., default=str, sort_keys=True)` and emits it at `logger.info(...)`.

OpenTelemetry is layered on top as an opt-in push pipeline (`OTEL_ENABLED`). When enabled, each service installs an OTel `LoggingHandler` onto the root logger so every structured record is mirrored into the OTLP log stream alongside traces and metrics. The OTel bridge is attached once per process, detaches `opentelemetry`'s own loggers from propagation to avoid recursion, and fails open if initialization errors occur.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — the authoritative specification for all services: structured logging levels, OTel switch semantics, request correlation, cardinality rules, and backend contract.
- Per-service `src/<service>/core/observability.py` — identical `configure_logging` / `log_event` implementations in `agent_service`, `platform_gateway`, `audit_service`, `incident_service`, `skills_hub`, `identity_service`, `tool_gateway`.
- Per-service `src/<service>/core/telemetry.py` — OTel setup, `setup_telemetry(app, service_name)`, `_attach_log_bridge`, `current_trace_id()`, `is_enabled()`.
- Per-service `src/<service>/core/request_context.py` — `resolve_request_id(request_id)` bridges inbound `x-request-id` to the active OTel trace id when tracing is active, otherwise generates `req-<uuid4>`.
- Call sites: every route/service module imports its local `LOGGER = logging.getLogger(__name__)` and emits events via `log_event(LOGGER, "<event_name>", field=value, ...)`.

## Architecture and conventions

1. **Single source of truth is stdout JSON.** Every business and request event is one line of JSON containing an `event` discriminator plus domain fields. This format is consumed by the container runtime / log collector as the audit trail.
2. **Audit trail lives at INFO level.** Because these records are auditable, `configure_logging()` explicitly sets the root logger to `INFO` regardless of Uvicorn's defaults. `LOG_LEVEL` can be raised per deployment but must stay `INFO` by default.
3. **OTLP mirror, not replacement.** When `OTEL_ENABLED=true`, the same stdout records are also exported over OTLP HTTP/protobuf to `OTEL_EXPORTER_OTLP_ENDPOINT`. Trace/span ids attach automatically when emitted inside an active span, joining logs to APM traces. Exporter failures never break requests.
4. **Request correlation key.** `x-request-id` is the portal-facing correlation id. It is resolved by `resolve_request_id`: inbound header wins, then the active OTel W3C `trace_id` (when tracing is on), then a generated `req-<uuid4>`. No service may silently drop an inbound correlation id.
5. **Opt-in telemetry.** OTel push is gated by `OTEL_ENABLED` (truthy values: `1`, `true`, `yes`, `on`). When disabled, no providers or instrumentation are initialized — zero overhead — and `/metrics` remains fully functional.
6. **Metric naming and cardinality** (from the shared spec): `<service>_<noun>_<unit>` snake_case counters with `_total`; bounded enum labels only; never label on raw URLs, user ids, session ids, or request ids.
7. **Backend contract.** OTLP endpoints append `/v1/{traces,metrics,logs}` to `OTEL_EXPORTER_OTLP_ENDPOINT`, targeting OpenObserve's ingest contract `/api/{org}/v1/{signal}`. Authentication via `OTEL_EXPORTER_OTLP_HEADERS` is provisioned as runtime secrets.

## Conventions and constraints

- **Every service must call `configure_logging()` at app startup** so structured events survive the root logger filter. This is documented in the docstring of each `configure_logging` and enforced by the shared spec.
- **All business and request events must go through `log_event(...)` at INFO level**, never via ad-hoc `print` or unstructured `logger.info("text")`. The shared spec calls these records the audit trail.
- **Event names are stable strings** (e.g. `http_request`, `tool_invoked`, `policy_decision`, `auth_login_url_requested`, `identity_normalized`) serving as the primary discriminator for downstream consumers.
- **Fields are passed as keyword arguments** to `log_event`, which flattens them into the JSON payload; sensitive data should not be included since the output is stdout-auditable.
- **Trace context bridging**: when tracing is active, `x-request-id` equals the active span's W3C `trace_id`; when inactive it falls back to `req-<uuid4>`. Outbound service-to-service calls forward this header.
- **No per-signal OTel toggles** — `OTEL_ENABLED` gates traces + metrics + log mirror together.
- **Cardinality rule**: never use unbounded values as metric labels (explicitly called out in the shared spec and rejected at review).
- **Fail-open guarantee**: missing/malconfigured OTel backend produces export-time drops and setup-time logged warnings; it never raises into the request path.