---
kind: logging_system
name: Structured JSON Logging with OpenTelemetry Log Bridge Across All Services
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/request_context.py
    - products/agent-platform/src/agent_service/app.py
    - products/audit-service/src/audit_service/core/telemetry.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/platform-gateway/src/platform_gateway/core/request_context.py
    - products/tool-gateway/src/tool_gateway/core/telemetry.py
    - products/execution-runtime/src/execution_runtime/core/telemetry.py
    - products/identity-broker/src/identity_service/core/telemetry.py
    - products/incident-service/src/incident_service/core/telemetry.py
    - products/skills-hub/src/skills_hub/core/telemetry.py
---

## What system/approach is used

Every Python service in the monorepo uses Python's built-in `logging` module to emit **single-line JSON** audit and request events at `INFO` level, wrapped by a shared `log_event(logger, event, **fields)` helper. Structured logs are written to stdout (the source of truth for the audit trail) and, when enabled, mirrored into an **OpenTelemetry OTLP log pipeline** via a `LoggingHandler`. The OTLP bridge is opt-in, gated by `OTEL_ENABLED`, and fails open — missing or misconfigured backends never break requests.

The observability surface is split per SPEC-005:
- `/metrics` (Prometheus pull, always on)
- OTLP push (traces + metrics + logs, off by default)

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — authoritative specification defining log levels, correlation headers, OTel switch semantics, cardinality rules, and backend contract.
- Per-service `core/telemetry.py` (identical across all services: agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway): initializes TracerProvider, MeterProvider, HTTPX/FastAPI instrumentation, and attaches the OTLP log bridge; exposes `setup_telemetry(app, service_name)` and `current_trace_id()`.
- Per-service `core/observability.py`: defines `configure_logging()` (raises root logger from uvicorn's WARNING default to INFO, overridable via `LOG_LEVEL`) and `log_event(logger, event, **fields)` which serializes `{event, ...fields}` as sorted JSON.
- Per-service `core/request_context.py`: resolves `x-request-id` using the inbound header, then the active OTel trace id, then a generated `req-<uuid4>` fallback.
- Per-service `app.py`: calls `configure_logging()`, installs an HTTP middleware that emits an `http_request` event via `log_event`, and invokes `setup_telemetry(app, SERVICE_NAME)`.

## Architecture and conventions

### Log emission pattern
Services create a module-level `LOGGER = logging.getLogger(__name__)` and emit business/request events through `log_event(LOGGER, "<event-name>", field=value, ...)`. The helper serializes the payload with `json.dumps(..., default=str, sort_keys=True)` and writes it at `INFO`. This makes every structured record a single JSON line suitable for log aggregation.

### Log level strategy
Uvicorn starts with root logger at `WARNING`; `configure_logging()` raises it to `INFO` so audit records (`http_request`, `tool_invoked`, policy decisions) are never silently discarded. The effective level can be overridden per deployment via `LOG_LEVEL` environment variable.

### Correlation and tracing
- `x-request-id` is the log- and portal-facing correlation key. It is preserved if present, bridged to the active W3C `traceparent` trace id when tracing is active, otherwise generated as `req-<uuid4>`.
- `traceparent` (W3C Trace Context) is the machine-facing propagation header, managed automatically by OpenTelemetry instrumentation across service hops.
- When tracing is active, `x-request-id` equals the span's `trace_id`, joining structured logs and APM traces on the same identifier.
- No service may silently drop an inbound correlation id.

### OTLP log bridge
When `OTEL_ENABLED=true`, each service attaches an OTel `LoggingHandler` to the root logger. Every structured record emitted via `log_event` is also exported as an OTLP log record via `BatchLogRecordProcessor(OTLPLogExporter())`. The bridge:
- Keeps JSON stdout as the audit source of truth; OTLP is a mirror for backend correlation.
- Automatically attaches `trace_id`/`span_id` when emitted inside an active span.
- Detaches `opentelemetry` loggers from the root logger to prevent recursion on exporter failure.
- Is fully gated by `OTEL_ENABLED`; initialization errors are logged and swallowed.

### Configuration
- `OTEL_ENABLED` — master gate (truthy values: `1`, `true`, `yes`, `on`); default false.
- `OTEL_EXPORTER_OTLP_ENDPOINT` — OTLP HTTP base URL (exporters append `/v1/traces`, `/v1/metrics`, `/v1/logs`).
- `OTEL_EXPORTER_OTLP_HEADERS` — Basic auth for OpenObserve ingest, provisioned via runtime secrets.
- `OTEL_SERVICE_NAME` — resource service name, defaults to service metadata.
- `LOG_LEVEL` — overrides the root logger level (default INFO).

### Metrics vs logs separation
Metrics use `prometheus_client` directly (with a RED middleware) exposed at `/metrics`; they are independent of OTLP push. Structured logs carry domain events; metrics carry counters/gauges. Cardinality rules forbid high-cardinality labels (raw URLs, user ids, session ids, request ids).

## Conventions and constraints

- **All business and request events must be single-line JSON** emitted via `log_event` at `INFO` — this is the audit trail and cannot be bypassed.
- **Root logger level must be raised to INFO** at startup via `configure_logging()`; leaving uvicorn's default WARNING discards audit records.
- **No per-signal toggles**: `OTEL_ENABLED` gates traces, metrics, and log mirroring together.
- **Fail-open**: OTel setup errors are caught and logged; services continue without push.
- **Never label on unbounded values** in metrics (and by extension, avoid embedding raw request/session/user identifiers in log fields that become indexed dimensions).
- **`x-request-id` must never be dropped** on inbound requests; it drives cross-service correlation.
- **OTLP credentials are never committed**; they are injected via runtime secrets by `sync-otel-secrets.sh`.
- **Backend decoupling**: services only expose `/metrics` and push OTLP; scraping, storage, dashboards, and alerting are platform-ops concerns.