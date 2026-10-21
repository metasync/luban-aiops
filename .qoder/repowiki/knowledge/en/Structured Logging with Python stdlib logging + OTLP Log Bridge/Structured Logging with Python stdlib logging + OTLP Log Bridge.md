---
kind: logging_system
name: Structured Logging with Python stdlib logging + OTLP Log Bridge
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/agent-platform/src/agent_service/app.py
---

## What is used

The platform uses **Python's standard library `logging`** module as the sole logging framework. There is no third-party logger (no structlog, loguru, or similar). Structured output is produced by serializing a dict to JSON via `json.dumps(..., sort_keys=True)` and emitting it at INFO level through a per-module `LOGGER = logging.getLogger(__name__)`. An opt-in OpenTelemetry bridge (`opentelemetry.instrumentation.logging.handler.LoggingHandler`) mirrors every structured record over OTLP HTTP/protobuf when `OTEL_ENABLED=true`, so logs join traces in OpenObserve.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — authoritative cross-service convention document for metrics, tracing, logging, and request correlation; defines the two-surface model (`/metrics` pull + OTel push), the `LOG_LEVEL` / `OTEL_ENABLED` switches, and the structured-log-level rule.
- `products/agent-platform/src/agent_service/core/observability.py` — `configure_logging()` raises the root logger from uvicorn's WARNING default to INFO (overridable via `LOG_LEVEL`) and exposes `log_event(logger, event, **fields)` which emits a single-line JSON record with an `event` field plus arbitrary fields.
- `products/agent-platform/src/agent_service/core/telemetry.py` — `setup_telemetry(app, service_name)` initializes OTel traces/metrics/logs when `OTEL_ENABLED`; `_attach_log_bridge(resource)` installs the OTLP `LoggingHandler` on the root logger, detaches `opentelemetry`'s own loggers, and guards against recursion.
- `products/agent-platform/src/agent_service/app.py` — calls `configure_logging()` at app startup and wraps every HTTP request in a middleware that emits an `http_request` event via `log_event` (service, request_id, method, path, status_code, duration_ms).
- Every other product service follows the same pattern: a `core/observability.py` (or equivalent) exposing `configure_logging`/`log_event`, and modules declaring `LOGGER = logging.getLogger(__name__)`.

## Architecture and conventions

1. **Single source of truth is stdout JSON.** Business and request events are emitted as one JSON line per call. The OTLP mirror is strictly additive — container stdout remains the audit trail; backend ingestion never replaces it.
2. **Event schema.** `log_event(logger, event, **fields)` produces `{"event": <string>, ...}` where `event` names the business occurrence (e.g. `http_request`, `tool_invoked`, policy decisions). Fields are flattened into the same JSON object; there is no nested envelope beyond the top-level `event` key.
3. **Log levels.** INFO is the default and carries the audit trail (http requests, tool invocations, policy decisions). The root logger is raised from uvicorn's WARNING default to INFO by `configure_logging()`. `LOG_LEVEL` overrides this per deployment but must stay INFO so audit records are not silently discarded.
4. **Per-module logger instances.** Modules declare `LOGGER = logging.getLogger(__name__)` at module scope rather than calling `logging.getLogger()` inline. This is observed across agent-platform services (agent_state_store, audit_emitter, authoring_trace, confirmation_records, document_prose, evidence_store, execution_records, execution_worker_client, incident_report, kernel_middleware, model_catalog, model_discovery, operation_documents, session_service, session_store, session_transcript, shift_summary, skill_draft, skills_client, gateway_tools, api routes, runtime_kernel, app).
5. **Request correlation.** `x-request-id` is the log- and portal-facing correlation key. When tracing is active, it is set to the active span's W3C `trace_id` (32 hex chars); otherwise it falls back to `req-<uuid4>`. No service may silently drop an inbound correlation id.
6. **OTLP log bridge semantics.** When enabled, the bridge attaches to the root logger, associates records with the active span's `trace_id`/`span_id`, and detaches `opentelemetry`'s internal loggers (`logging.getLogger("opentelemetry").propagate = False`) to prevent recursion if the exporter fails.
7. **Fail-open.** Both `configure_logging` and `setup_telemetry` swallow setup errors and continue without push; missing/invalid OTel credentials produce 401s at export time, and batch processors drop telemetry on failure.
8. **Two observability surfaces.** `/metrics` (Prometheus, always-on) and OTel push (opt-in, gated by `OTEL_ENABLED`). They never depend on each other; disabling OTel leaves `/metrics` fully functional.

## Conventions and constraints

- **Convention:** Emit structured audit events via `log_event(LOGGER, "<event-name>", **fields)` rather than raw `logger.info("...")`. Enforced by the `observability-conventions.md` statement that "all business and request events are emitted as single-line JSON via `log_event(...)` at INFO level".
- **Convention:** Initialize logging with `configure_logging()` at FastAPI app startup before any request handling begins. Observed in `app.create_app()`.
- **Constraint:** `LOG_LEVEL` defaults to `INFO` and must remain INFO so audit records are not silently discarded (documented in `observability-conventions.md`; enforced by the `basicConfig(level=level, force=True)` call).
- **Constraint:** OTel push is controlled exclusively by `OTEL_ENABLED` (plus endpoint/headers/service-name env vars); there are no per-signal toggles. Enforced by `is_enabled()` returning based only on `OTEL_ENABLED`.
- **Constraint:** Never use unbounded values as metric labels (raw URL, user id, session id, request id). Documented in `observability-conventions.md` under "Cardinality Rules".
- **Constraint:** `x-request-id` must be propagated on every outbound service-to-service call and must not be silently dropped on inbound. Documented in `observability-conventions.md` under "Request Correlation And Trace Bridging".