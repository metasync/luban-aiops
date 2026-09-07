---
kind: logging_system
name: Structured JSON Logging with OTLP Bridge and Centralized Configuration
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/agent-platform/src/agent_service/app.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
---

## What system/approach is used

The platform uses Python's standard `logging` module as the sole logging framework. There is no third-party logger (no structlog, loguru, or similar). Each product service ships its own small `core/observability.py` that provides two functions: `configure_logging()` to set up the root logger, and `log_event(logger, event, **fields)` to emit structured audit events. All business and request events are emitted as single-line JSON via `logger.info(json.dumps(payload, default=str, sort_keys=True))`, where the payload always contains an `event` field plus arbitrary key/value fields.

OpenTelemetry is layered on top as an opt-in push pipeline (`OTEL_ENABLED`). When enabled, a `LoggingHandler` bridges every record from the root logger into the OTLP logs exporter so records can be correlated with traces in OpenObserve. The stdout JSON stream remains the source of truth for the audit trail; the OTLP bridge is only a mirror.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — the authoritative cross-product contract describing the two surfaces (`/metrics` pull + OTLP push), environment variables, level policy, correlation headers, cardinality rules, and the OTLP log bridge semantics.
- Per-service `core/observability.py` (identical implementation across all products): `agent-platform`, `platform-gateway`, `audit-service`, `execution-runtime`, `identity-broker`, `incident-service`, `skills-hub`, `tool-gateway`. Each exposes `configure_logging()` and `log_event()`.
- Per-service `core/telemetry.py` (identical implementation across all products): `setup_telemetry(app, service_name)`, `is_enabled()`, `current_trace_id()`. Gated by `OTEL_ENABLED`; initializes TracerProvider, MeterProvider, FastAPI/HTTPX instrumentation, and attaches the OTel `LoggingHandler` to the root logger.
- Service entrypoints call `configure_logging()` at app creation time (e.g. `products/*/src/*/app.py` lines like `configure_logging()` before `FastAPI(...)`).
- Request middleware in each service calls `log_event(LOGGER, "http_request", ...)` with `service`, `request_id`, `method`, `path`, `status_code`, `duration_ms`.

## Architecture and conventions

### Root logger configuration
Every service calls `configure_logging()` during startup. It reads `LOG_LEVEL` (default `INFO`) and calls `logging.basicConfig(level=level, force=True)`. This explicitly raises the root logger above Uvicorn's default `WARNING` level so INFO-level structured audit records are not silently discarded.

### Structured event format
All audit-relevant events go through `log_event(logger, event, **fields)`, which builds `{"event": event, **fields}` and emits it as one line of JSON at INFO level. Fields are flattened into the JSON object; there is no nested hierarchy beyond what callers pass. Event names are short strings such as `http_request`, `auth_login_url_requested`, `tool_invoked`, `policy_decision`, etc., chosen per domain.

### Log levels
- INFO is the baseline for all business/request/audit events. The convention mandates INFO because these records form the audit trail; lowering the level would silently drop them.
- DEBUG/ERROR/etc. are used sparingly via normal `LOGGER.debug(...)` / `LOGGER.exception(...)` calls (e.g. telemetry setup failures).
- The effective level is controlled per deployment by `LOG_LEVEL`.

### Correlation and trace bridging
- `x-request-id` is the log- and portal-facing correlation key. It is generated if absent and forwarded on outbound calls.
- `traceparent` (W3C Trace Context) is the machine-facing propagation header, managed automatically by OpenTelemetry instrumentation.
- When tracing is active, `x-request-id` is set to the active span's W3C `trace_id` (32 hex chars); when tracing is off, it falls back to `req-<uuid4>`.
- The OTel `LoggingHandler` automatically attaches `trace_id`/`span_id` to mirrored log records emitted inside an active span.

### Opt-in OTLP bridge
`setup_telemetry(app, service_name)` is called after the app is created. If `OTEL_ENABLED` is false, nothing is initialized (zero overhead). If true, it creates a `TracerProvider`, `MeterProvider`, instruments FastAPI and HTTPX, and attaches an OTel `LoggingHandler` to the root logger. Exporters send traces, metrics, and logs over OTLP HTTP/protobuf to `OTEL_EXPORTER_OTLP_ENDPOINT` (with auth via `OTEL_EXPORTER_OTLP_HEADERS`). Failures are logged but never raised — the pipeline fails open.

### Metrics surface (related observability)
Each service also exposes `/metrics` (Prometheus pull) via `prometheus_client` with RED middleware. Metric naming follows `<service>_<noun>_<unit>` snake_case, counters end in `_total`, labels are bounded enums only, and high-cardinality values (user id, session id, raw URL) are forbidden as labels.

## Conventions and constraints

- **Every service must call `configure_logging()` before handling requests** — observed in every product's `app.py` startup path.
- **Audit events must be emitted via `log_event(...)` at INFO level** — documented in `observability-conventions.md` as the audit trail; lowering the level would discard them.
- **Log output must be single-line JSON** — produced by `json.dumps(..., sort_keys=True)` in `log_event`.
- **`LOG_LEVEL` overrides the root logger level** — defaults to `INFO`; deployments may raise it for production noise reduction.
- **OTLP push is disabled by default** — controlled by `OTEL_ENABLED`; missing/invalid backend credentials produce export-time drops, never request failures.
- **Stdout JSON is the source of truth** — the OTLP bridge is a mirror; tooling must keep reading container logs.
- **No recursion between OTel loggers and the root logger** — `logging.getLogger("opentelemetry").propagate = False` prevents exporter failures from looping back.
- **Request correlation is mandatory** — services must not silently drop inbound `x-request-id`.
- **Metric label cardinality is bounded** — raw URLs, user ids, session ids, request ids must not be used as labels (enforced by review per the conventions doc).
- **Service prefix on metrics** — metric names are prefixed with the short service name (`gateway`, `identity`, `agent`, etc.).