---
kind: logging_system
name: Structured JSON Audit Logging with OpenTelemetry Log Bridge
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/app.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
---

## What system/approach is used

Each Python service in the platform uses Python's stdlib `logging` module to emit **single-line, sorted-key JSON** audit records at INFO level. There is no third-party logging framework (no structlog, loguru, or gunicorn access-loggers). The structured records are emitted via a per-service `core/observability.log_event()` helper and routed through `logging.basicConfig(force=True)` so that Uvicorn's default WARNING root level does not silently drop them.

An opt-in OpenTelemetry push pipeline (`OTEL_ENABLED`) mirrors every structured record into an OTLP log stream via `opentelemetry.instrumentation.logging.LoggingHandler`. When enabled, the bridge attaches to the root logger, sets `service.name` from `OTEL_SERVICE_NAME`, detaches the `opentelemetry` internal logger from propagation to avoid recursion, and joins logs to traces automatically via W3C `traceparent` / `span_id` fields.

## Key files and packages

- Per-service `core/observability.py` — identical `configure_logging()` + `log_event(logger, event, **fields)` pair:
  - `products/agent-platform/src/agent_service/core/observability.py`
  - `products/platform-gateway/src/platform_gateway/core/observability.py`
  - `products/audit-service/src/audit_service/core/observability.py`
  - `products/identity-broker/src/identity_service/core/observability.py`
  - `products/incident-service/src/incident_service/core/observability.py`
  - `products/skills-hub/src/skills_hub/core/observability.py`
  - `products/tool-gateway/src/tool_gateway/core/observability.py`
- Per-service `core/telemetry.py` — optional OTel setup gated by `OTEL_ENABLED`; contains `_attach_log_bridge()` which installs the `LoggingHandler` on the root logger.
- Shared contract: `shared/shared-contracts/observability-conventions.md` — documents the two-surface model, environment variables, cardinality rules, and request-correlation bridging.
- App entry points call `configure_logging()` before creating the FastAPI app (e.g. `platform_gateway/app.py`, `agent_platform/src/agent_service/app.py`).

## Architecture and conventions

1. **Single source of truth for audit output**: every business and request event is a single JSON line on stdout via `logger.info(json.dumps(payload, default=str, sort_keys=True))`. The payload always carries an `event` field plus domain-specific key-value pairs (e.g. `http_request`, `tool_invoked`, `policy_decision`, `auth_login_started`, `identity_normalized`).
2. **Root logger elevation**: `configure_logging()` reads `LOG_LEVEL` (default `INFO`, uppercased) and calls `logging.basicConfig(level=level, force=True)`. This raises the root logger above Uvicorn's WARNING default so audit records are never dropped.
3. **Per-module loggers**: modules create `LOGGER = logging.getLogger(__name__)` and pass it to `log_event(LOGGER, ...)`; the library function handles serialization.
4. **Request correlation**: a FastAPI middleware in each service emits an `http_request` event carrying `request_id` (from `x-request-id`, generated if absent), `method`, `path`, `status_code`, `duration_ms`. The `x-request-id` value is bridged to the active span's W3C `trace_id` when tracing is active, so one ID joins structured logs and APM traces.
5. **Opt-in OTel mirror**: `setup_telemetry(app, service_name)` in `core/telemetry.py` initializes TracerProvider, MeterProvider, HTTPX client instrumentation, and the log bridge only when `OTEL_ENABLED` is truthy. It fails open — exceptions during setup are logged and never raised into the request path. Export targets are configured via `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_EXPORTER_OTLP_HEADERS`.
6. **Metrics surface is separate**: Prometheus `/metrics` is always-on and independent of logging/tracing; it is set up via `core/metrics.setup_metrics(app)` and follows `<service>_<noun>_<unit>` naming with bounded labels.

## Conventions and constraints

- **All audit events go through `log_event(...)`**, not raw `logger.info(...)`. This ensures consistent JSON shape and sorting.
- **Audit records are emitted at INFO level**; `LOG_LEVEL` may be raised per deployment but must never be lowered below INFO because those records form the audit trail.
- **No unbounded label values in metrics** (per `observability-conventions.md`): do not label on raw URLs, user ids, session ids, or request ids — use templated route names and bounded enum labels.
- **OTel push is off by default** (`OTEL_ENABLED` defaults to false); services run with zero OTel overhead unless explicitly enabled.
- **Export failures are non-fatal**: missing/invalid credentials produce export-time 401s that batch processors drop; initialization errors are caught and logged rather than raised.
- **`x-request-id` must never be silently dropped** on inbound requests; it is preserved and forwarded on outbound calls.
- **Container stdout remains the source of truth** for audit tooling; the OTLP log bridge is a secondary correlation surface, not a replacement.