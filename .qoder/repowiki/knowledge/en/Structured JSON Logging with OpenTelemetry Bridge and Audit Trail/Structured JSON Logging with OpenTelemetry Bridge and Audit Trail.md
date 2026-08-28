---
kind: logging_system
name: Structured JSON Logging with OpenTelemetry Bridge and Audit Trail
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
    - products/agent-platform/src/agent_service/services/audit_emitter.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
---

## What system/approach is used

The platform uses Python's standard `logging` module as the sole logging framework, combined with an opt-in OpenTelemetry (OTel) push pipeline that mirrors structured logs over OTLP HTTP/protobuf. There is no third-party logger library (no structlog, loguru, or similar). Every service ships its own `core/observability.py` that provides two functions: `configure_logging()` and `log_event(logger, event, **fields)`.

## Key files and packages

- Per-service `core/observability.py` — identical pattern across all services:
  - `products/platform-gateway/src/platform_gateway/core/observability.py`
  - `products/agent-platform/src/agent_service/core/observability.py`
  - `products/audit-service/src/audit_service/core/observability.py`
  - `products/execution-runtime/src/execution_runtime/core/observability.py`
  - `products/incident-service/src/incident_service/core/observability.py`
  - `products/skills-hub/src/skills_hub/core/observability.py`
  - `products/tool-gateway/src/tool_gateway/core/observability.py`
  - `products/identity-broker/src/identity_service/core/observability.py`
- `shared/shared-contracts/observability-conventions.md` — authoritative specification for the logging strategy (SPEC-005).
- `products/*/core/telemetry.py` — OTel setup; attaches an OTel `LoggingHandler` to the root logger when `OTEL_ENABLED=true`, bridging every structured record into traces/metrics/logs.
- `products/*/core/request_context.py` — resolves `x-request-id` by bridging to the active OTel trace id when tracing is on, otherwise generating a UUID.
- `products/agent-platform/src/agent_service/services/audit_emitter.py` — builds and emits audit events via a separate channel (`build_audit_event` / `emit_audit_event`) distinct from stdout logs.

## Architecture and conventions

1. **Structured JSON audit trail on stdout.** `log_event(logger, event, **fields)` serializes `{"event": event, ...fields}` as a single-line JSON string at INFO level using `json.dumps(..., default=str, sort_keys=True)`. This is the canonical audit trail surface — tool invocations, policy decisions, HTTP requests, handoff rejections, receipt closes, etc. All business and request events are emitted this way.

2. **Root logger raised to INFO at startup.** Each service calls `configure_logging()` during app bootstrap. It reads `LOG_LEVEL` (default `INFO`, uppercased), maps it via `getattr(logging, ...)`, and calls `logging.basicConfig(level=..., force=True)`. This is necessary because Uvicorn starts the root logger at WARNING, which would silently discard every INFO-level structured record.

3. **Opt-in OTel log bridge.** When `OTEL_ENABLED=true`, `setup_telemetry(app, service_name)` initializes TracerProvider, MeterProvider, FastAPI/HTTPX instrumentation, and attaches an OTel `LoggingHandler` to the root logger. The bridge exports the same records over OTLP HTTP/protobuf so the backend can correlate logs with traces. The `opentelemetry` internal loggers are detached (`propagate = False`) to prevent recursion through exporter failures. Setup errors are logged and swallowed — fail-open.

4. **Request correlation.** `x-request-id` is the log- and portal-facing correlation key. Inbound values are preserved; if absent, the active span's W3C `trace_id` is used when tracing is enabled, otherwise a generated `req-<uuid4>` is produced. No service may silently drop an inbound correlation id.

5. **Two decoupled surfaces.** `/metrics` (Prometheus pull, always on) and OTel push (opt-in) never depend on each other. Disabling OTel leaves metrics fully functional.

6. **Audit events vs. logs.** The agent-platform additionally has a dedicated audit emitter (`build_audit_event` / `emit_audit_event`) that writes audit records through a separate channel (not stdout logs), used for events like chat confirmations and runtime kernel actions.

## Conventions and constraints

- **All business/request events go through `log_event`** at INFO level as single-line JSON. This is documented in `observability-conventions.md` as the audit trail contract.
- **Default log level must stay INFO** so audit records are never silently discarded; per-deployment override via `LOG_LEVEL`.
- **No unbounded label cardinality** for metrics (applies to the broader observability surface); raw URLs, user ids, session ids, and request ids must not be labels.
- **OTel push is gated by `OTEL_ENABLED`** (truthy values: `1`, `true`, `yes`, `on`). Off by default, zero overhead when disabled.
- **OTLP endpoint** is configured via `OTEL_EXPORTER_OTLP_ENDPOINT`; authentication via `OTEL_EXPORTER_OTLP_HEADERS` (provisioned as runtime secrets, never committed).
- **Service name** comes from `OTEL_SERVICE_NAME`, falling back to metadata.
- **Fail-open guarantee:** missing/invalid credentials produce export-time 401s dropped by batch processors; initialization exceptions are logged rather than raised into the request path.
- **Trace/span association** is automatic for records emitted inside an active span, joining the log mirror to the trace view via W3C `traceparent` propagated across service hops.