---
kind: logging_system
name: Structured JSON Logging with OpenTelemetry Log Bridge Across Platform Services
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/agent-platform/src/agent_service/app.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/audit-service/src/audit_service/core/telemetry.py
    - products/execution-runtime/src/execution_runtime/core/telemetry.py
    - products/incident-service/src/incident_service/core/telemetry.py
    - products/skills-hub/src/skills_hub/core/telemetry.py
    - products/tool-gateway/src/tool_gateway/core/telemetry.py
---

## What System/Approach Is Used

The platform uses Python's built-in `logging` module as the sole logging framework, augmented by an opt-in OpenTelemetry (OTel) push pipeline that mirrors structured logs to an OTLP backend. There is no third-party logging library (no structlog, loguru, or similar). All services are FastAPI applications and rely on uvicorn's default root logger, which starts at WARNING — deliberately raised to INFO at startup so audit-level events are not silently dropped.

Two distinct surfaces exist per service:
1. **JSON stdout** — the source of truth for the audit trail. Every business/request event is emitted as a single-line JSON string via a shared `log_event(logger, event, **fields)` helper.
2. **OTLP log mirror** — when `OTEL_ENABLED=true`, a `LoggingHandler` attached to the root logger forwards every INFO+ record over OTLP HTTP/protobuf to the configured endpoint (OpenObserve in this organization), automatically associating each record with the active trace/span via W3C Trace Context.

## Key Files and Packages

- `shared/shared-contracts/observability-conventions.md` — the authoritative specification defining the logging strategy, level policy, environment variables (`LOG_LEVEL`, `OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_SERVICE_NAME`), correlation rules, and fail-open semantics. This document backs SPEC-005.
- Per-service `core/observability.py` — contains the identical `configure_logging()` (raises root logger from WARNING to INFO, overridable via `LOG_LEVEL`) and `log_event(logger, event, **fields)` (serializes `{event, ...fields}` as sorted JSON via `json.dumps(..., sort_keys=True, default=str)`).
- Per-service `core/telemetry.py` — contains the identical opt-in OTel setup: `setup_telemetry(app, service_name)` initializes TracerProvider, MeterProvider, FastAPI + HTTPX instrumentation, and attaches the log bridge; `is_enabled()` reads `OTEL_ENABLED`; `current_trace_id()` returns the active span's W3C `trace_id` for request-correlation bridging into `x-request-id`.
- Each service's `app.py` calls `configure_logging()` early in startup and `setup_telemetry(app, SERVICE_NAME)` after app construction.
- Example callers: `products/agent-platform/src/agent_service/app.py`, `products/platform-gateway/src/platform_gateway/core/observability.py`, `products/audit-service/src/audit_service/api/routes/ingest.py`, `products/execution-runtime/src/execution_runtime/services/audit_emitter.py`, etc.

## Architecture and Conventions

### Log Format and Fields
- Every audit/business event goes through `log_event(logger, "<event_name>", field=value, ...)`. The resulting line is `json.dumps({"event": ..., **fields}, default=str, sort_keys=True)`, ensuring deterministic key ordering for downstream parsing.
- The `event` field names are domain-specific (e.g. `http_request`, `tool_invoked`, `policy_decision`, `session_created`) and serve as the primary filter key for consumers.
- No custom formatter is used — plain JSON lines to stdout.

### Log Levels
- Default root logger level is **INFO** (raised from uvicorn's WARNING default). This is enforced by calling `configure_logging()` at process start.
- Level can be overridden per deployment via `LOG_LEVEL` (any value accepted by `getattr(logging, name, logging.INFO)`).
- Audit records must never be silently discarded — the spec mandates INFO as the default.

### Structured Fields and Correlation
- Request correlation key `x-request-id` is generated if absent and forwarded on all outbound calls. When tracing is active, it is set to the active span's W3C `trace_id` (32 hex chars); otherwise it falls back to `req-<uuid4>`.
- `current_trace_id()` in each service's `core/telemetry.py` provides the active span ID for inclusion in structured log fields.
- Outbound HTTP clients are instrumented via `HTTPXClientInstrumentor`, propagating W3C `traceparent` headers automatically.

### OTLP Log Bridge
- Enabled only when `OTEL_ENABLED` evaluates to one of `{"1", "true", "yes", "on"}`.
- A `BatchLogRecordProcessor(OTLPLogExporter())` is added to a dedicated `LoggerProvider`; the provider is set via `set_logger_provider`.
- `opentelemetry`'s own loggers are detached from the root logger (`propagate = False`) to prevent recursion if the exporter fails.
- The bridge is initialized lazily inside `_attach_log_bridge(resource)` and guarded by a module-level `_log_bridge_attached` flag.
- Fail-open: initialization errors are caught and logged; missing/malconfigured backend produces export-time failures that batch processors drop without breaking requests.

### Metrics vs Logs Separation
- `/metrics` (Prometheus, always-on) and OTLP push (opt-in) are deliberately decoupled. Disabling OTel has zero effect on the metrics surface.
- Metric naming follows `<service>_<noun>_<unit>` snake_case with bounded enum labels; cardinality rules forbid unbounded label values (raw URLs, user IDs, session IDs, request IDs).

### Service Template Pattern
Every new service under `products/` follows the same layout:
```
src/<service>/
├── core/
│   ├── observability.py   # configure_logging(), log_event()
│   ├── telemetry.py       # setup_telemetry(), current_trace_id(), is_enabled()
│   ├── config.py
│   ├── metrics.py
│   ├── request_context.py
│   └── runtime.py
├── api/
├── services/
├── app.py                 # calls configure_logging() + setup_telemetry()
└── main.py
```

## Conventions and Constraints

- **All business and request events use `log_event` at INFO level.** Ad-hoc `logger.info("...")` with non-JSON strings is discouraged for audit-boundary events because they would not parse as structured records.
- **Root logger level must be raised before any handler is attached.** `configure_logging()` uses `logging.basicConfig(level=..., force=True)` to override uvicorn's defaults.
- **OTLP is opt-in and gated by a single switch.** There are no per-signal toggles; `OTEL_ENABLED` controls traces, metrics, and log mirror together.
- **Credentials never leave the container.** `OTEL_EXPORTER_OTLP_HEADERS` carries Basic auth provisioned via `sync-otel-secrets.sh`; secrets are injected from Kubernetes Secrets, never committed.
- **No service may silently drop an inbound correlation id.** Inbound `x-request-id` / `traceparent` must be preserved and forwarded.
- **Cardinality rule applies to both metrics and logs:** do not label/log high-cardinality values such as raw request URLs, user IDs, session IDs, or request IDs as free-form fields intended for aggregation.
- **Fail-open guarantee:** misconfigured OTel endpoints produce 401s at export time; batch processors drop telemetry on failure; service setup catches exceptions and continues without push.
- **Source-of-truth rule:** JSON stdout remains the canonical audit stream; the OTLP mirror exists solely for correlation with traces in the backend and must never replace stdout consumption.