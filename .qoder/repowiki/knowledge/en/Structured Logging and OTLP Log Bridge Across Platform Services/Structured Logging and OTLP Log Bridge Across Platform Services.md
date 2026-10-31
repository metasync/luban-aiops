---
kind: logging_system
name: Structured Logging and OTLP Log Bridge Across Platform Services
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/agent-platform/src/agent_service/app.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/audit-service/src/audit_service/app.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/execution-runtime/src/execution_runtime/app.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/identity-broker/src/identity_service/app.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/incident-service/src/incident_service/app.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/skills-hub/src/skills_hub/app.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/tool-gateway/src/tool_gateway/app.py
---

## Approach

The platform uses Python's stdlib `logging` module as the sole logging framework, with a thin per-service `core/observability.py` that centralizes initialization and a shared JSON event helper. Structured logs are emitted as single-line JSON via a `log_event(logger, event, **fields)` helper; when OpenTelemetry push is enabled, an OTLP log bridge (`opentelemetry.instrumentation.logging.handler.LoggingHandler`) mirrors every root-logger record to the OTLP pipeline so logs can be correlated with traces.

There is no third-party logger library (no structlog, loguru, sentry_sdk). The only external dependency for structured output is the optional OpenTelemetry SDK used for tracing/metrics/log export.

## Key Files

- `shared/shared-contracts/observability-conventions.md` — authoritative cross-product contract defining the two observability surfaces, OTel switch semantics, structured logging levels, cardinality rules, request-correlation bridging, and the OTLP log bridge behavior.
- `products/*/src/<service>/core/observability.py` — per-service copy of the same small module exposing `configure_logging()` and `log_event()`.
- `products/*/src/<service>/app.py` — each service calls `configure_logging()` at startup and uses `log_event(...)` in HTTP middleware / route handlers.
- `products/agent-platform/src/agent_service/core/telemetry.py` — opt-in OTel push pipeline (traces + metrics + log mirror) gated by `OTEL_ENABLED`; installs `FastAPIInstrumentor`, `HTTPXClientInstrumentor`, `BatchSpanProcessor`, `PeriodicExportingMetricReader`, and the OTLP log bridge.
- `products/agent-platform/src/agent_service/core/request_context.py` — bridges `x-request-id` and W3C `traceparent` so the same correlation key joins logs and traces.

## Architecture and Conventions

**Two decoupled surfaces** (per `observability-conventions.md`):
1. `/metrics` pull endpoint (Prometheus, always on).
2. OpenTelemetry push (opt-in, OTLP HTTP/protobuf to `OTEL_EXPORTER_OTLP_ENDPOINT`).

**Logging initialization:**
- Each service imports `configure_logging, log_event` from its own `core.observability` and invokes `configure_logging()` inside `create_app()` before mounting routes.
- `configure_logging()` reads `LOG_LEVEL` (default `"INFO"`), converts it via `getattr(logging, level_name, logging.INFO)`, and calls `logging.basicConfig(level=level, force=True)` to override uvicorn's default WARNING root level.
- `log_event(logger, event, **fields)` serializes `{"event": event, ...}` through `json.dumps(..., default=str, sort_keys=True)` and emits it at INFO level.

**OTLP log bridge:**
- Installed lazily by `_attach_log_bridge(resource)` inside `setup_telemetry` when `OTEL_ENABLED` is truthy.
- Creates an OTel `LoggerProvider` with a `BatchLogRecordProcessor(OTLPLogExporter())`, sets it as the global logger provider, detaches `opentelemetry` child loggers from propagation, and attaches `LoggingHandler(level=logging.INFO)` to the root logger.
- JSON stdout remains the source of truth; the OTLP mirror exists solely for trace-log correlation in the backend.
- Recursion guard: `logging.getLogger("opentelemetry").propagate = False` prevents exporter failures from looping back into the bridge.

**Request correlation:**
- `x-request-id` is the log- and portal-facing correlation key; generated if absent and forwarded on outbound calls.
- When tracing is active, `current_trace_id()` returns the active span's W3C `trace_id`; `request_context` bridges this into `x-request-id` so a single value joins structured logs and APM traces.
- `traceparent` (W3C Trace Context) is managed automatically by OTel instrumentation across service hops.

**Fail-open design:**
- OTel setup catches all exceptions and logs them via `LOGGER.exception(...)` rather than raising; services continue without push.
- Missing or invalid credentials produce 401s at export time; batch processors drop telemetry on failure.
- Disabling OTel (`OTEL_ENABLED=false`) leaves `/metrics` fully functional with zero overhead.

**Adoption across products:**
All eight Python services follow the same pattern: import `configure_logging, log_event` from their local `core.observability`, call `configure_logging()` in `create_app()`, and emit audit events via `log_event`. Verified in agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, and tool-gateway.

## Conventions and Constraints

- **Structured log format**: business and request events are single-line JSON produced by `log_event(...)`, not raw strings. Enforced by the documented convention in `observability-conventions.md` and the uniform usage across all services.
- **Default log level is INFO**: `configure_logging()` defaults to INFO so audit records (http_request, tool_invoked, policy decisions) are never silently discarded by uvicorn's WARNING default. Overridable per deployment via `LOG_LEVEL`.
- **OTel push is opt-in**: controlled exclusively by `OTEL_ENABLED` (truthy values: `1`, `true`, `yes`, `on`). No per-signal toggles. Default false.
- **Cardinality rules**: labels must be bounded enums; raw URLs, user ids, session ids, and request ids are prohibited as metric labels (documented in `observability-conventions.md`).
- **No unbounded label cardinality**: enforced as a review gate per the conventions doc.
- **JSON stdout is the source of truth**: the OTLP log bridge is additive and never replaces container logs; audit tooling must keep reading stdout.
- **Service naming**: `OTEL_SERVICE_NAME` defaults to the service metadata name; resource attributes include `service.name`.
- **Endpoint convention**: `OTEL_EXPORTER_OTLP_ENDPOINT` stops at the org prefix; exporters append `/v1/{traces,metrics,logs}`, matching the OpenObserve ingest contract `/api/{org}/v1/{signal}`.