---
kind: logging_system
name: Structured JSON Logging with OpenTelemetry Bridge Across Microservices
category: logging_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/platform-gateway/src/platform_gateway/core/request_context.py
    - products/agent-platform/src/agent_service/core/request_context.py
    - products/audit-service/src/audit_service/api/routes/ingest.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
---

## What system/approach is used

The platform uses Python's standard `logging` module as the sole logging framework across all microservices (`agent-platform`, `platform-gateway`, `audit-service`, `identity-broker`, `incident-service`, `skills-hub`, `tool-gateway`). There is no third-party structured logging library (e.g. structlog, loguru). Each service ships an identical `core/observability.py` that provides two functions:

- `configure_logging()` — raises the root logger level from Uvicorn's default `WARNING` to `INFO` so audit-trail events are not silently dropped; the effective level is read from the `LOG_LEVEL` environment variable.
- `log_event(logger, event, **fields)` — builds a dict `{"event": <name>, ...fields}`, serializes it to a single-line JSON string via `json.dumps(..., default=str, sort_keys=True)`, and emits it at `logger.info`.

Structured logs are therefore plain JSON lines on stdout. An opt-in OpenTelemetry bridge (gated by `OTEL_ENABLED`) attaches a `LoggingHandler` that mirrors those same records into the OTLP log pipeline, automatically attaching trace/span IDs when a span is active. The stdout JSON line remains the source of truth for the audit trail; the OTLP bridge is a secondary export path.

## Key files and packages

- Per-service `src/<service>/core/observability.py` — defines `configure_logging` / `log_event` (identical implementations across services).
- Per-service `src/<service>/core/telemetry.py` — implements `setup_telemetry(app, service_name)`, `is_enabled()`, `current_trace_id()`, and the `_attach_log_bridge` function that bridges `logging` to OTLP.
- Per-service `src/<service>/core/request_context.py` — resolves `x-request-id` from inbound header → active OTel trace ID → generated UUID, used as the correlation key in logs.
- Service entry points (`app.py` / `main.py`) call `configure_logging()` during startup and `setup_telemetry(app, SERVICE_NAME)` after FastAPI app creation.
- Consumers use `LOGGER = logging.getLogger(__name__)` and emit via `log_event(LOGGER, "<event_name>", request_id=..., ...)` or direct `LOGGER.info("...", extra={...})`.

## Architecture and conventions

1. **Root-level configuration**: Every service calls `logging.basicConfig(level=..., force=True)` in `configure_logging()` so its own log records are emitted even though Uvicorn configures the root logger at `WARNING`. This is intentional — the comment documents that without this step, every `log_event` record (http_request, auth, routing, tool_invoked, policy decisions) would be discarded.

2. **Structured field convention**: Audit-relevant events go through `log_event(event, **fields)`, which produces a flat JSON object with a required `event` field followed by arbitrary key/value pairs serialized with `default=str` and `sort_keys=True`. Examples observed: `audit_events_ingested(client=..., count=..., inserted=...)`, `auth_login_url_requested(request_id=...)`, `identity verified locally(sub=..., username=..., roles=..., authenticated=..., synthetic=...)`.

3. **Correlation keys**: `request_id` is resolved via `resolve_request_id(request_id)` in each service's `request_context.py`: prefer inbound `x-request-id`, fall back to the active OTel `trace_id` (via `current_trace_id()`), otherwise generate `req-<uuid4()>`. This value is attached to most log events so requests can be correlated across services.

4. **Opt-in OTLP bridge**: Telemetry is disabled by default (`OTEL_ENABLED` must be truthy). When enabled, `setup_telemetry` initializes TracerProvider, MeterProvider, FastAPI instrumentation, HTTPX client instrumentation, and a log bridge. Failures are caught and logged — setup never raises into the request path (fail-open).

5. **Service identity in logs**: `SERVICE_NAME` and `SERVICE_VERSION` from each service's `metadata.py` are included in health/status responses and in telemetry resource attributes; they also appear in log records propagated through the OTLP bridge via the `Resource` created in `setup_telemetry`.

6. **Direct vs structured logging**: Some modules (e.g. `gateway_service.py`) still use `LOGGER.info("message", extra={...})` for non-audit operational messages, while audit-critical events use `log_event(...)`. Both produce structured output because the OTLP bridge captures them.

## Conventions and constraints

- **Log level control**: The effective root logger level is controlled exclusively by the `LOG_LEVEL` environment variable (defaults to `INFO`). Tests in `test_observability.py` verify that setting `LOG_LEVEL=WARNING` suppresses INFO events, confirming the override works.
- **Audit trail integrity**: The docstrings in every `configure_logging()` explicitly state that raising the root level is necessary so `log_event` records survive — treating these records as the audit trail. This is enforced by the `force=True` flag in `basicConfig`.
- **Single JSON line per event**: All audit events are emitted as one JSON line via `json.dumps(..., sort_keys=True)`, making them parseable by line-oriented log collectors.
- **No per-module logger hierarchy**: Modules create their own `logging.getLogger(__name__)` but do not configure handlers or formatters — only the root logger is configured once per process.
- **Request context propagation**: Correlation via `x-request-id` is mandatory for cross-service tracing; services propagate it as an HTTP header (`_service_headers(request_id)`) on outbound calls.
- **OTLP endpoint contract**: Export targets `OTEL_EXPORTER_OTLP_ENDPOINT` with per-signal paths `/v1/{traces,metrics,logs}` matching the OpenObserve ingest contract documented in `shared/shared-contracts/observability-conventions.md`.
- **Fail-open telemetry**: Any exception during OTel initialization is caught and logged; the service continues running without traces/metrics/logs push.