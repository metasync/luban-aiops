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
    - products/tool-gateway/src/tool_gateway/core/telemetry.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
---

## What system/approach is used

The platform uses Python's standard `logging` module as the sole logging framework, emitting single-line JSON records to stdout. Every product service (agent-platform, audit-service, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway) follows an identical pattern: a local `core/observability.py` exposes `configure_logging()` and `log_event(logger, event, **fields)`; a local `core/telemetry.py` provides an opt-in OpenTelemetry push pipeline that mirrors those same structured logs over OTLP HTTP/protobuf via a `LoggingHandler`. There is no third-party logging library (no structlog, no loguru, no python-json-logger). The design is deliberately minimal — structured fields are produced by serializing a dict through `json.dumps(..., default=str, sort_keys=True)`.

## Key files and packages

- Per-service `src/<service>/core/observability.py` — defines `configure_logging()` (reads `LOG_LEVEL`, calls `logging.basicConfig(level=..., force=True)`) and `log_event(logger, event, **fields)` which emits `{"event": ..., ...}` at INFO level.
- Per-service `src/<service>/core/telemetry.py` — implements `setup_telemetry(app, service_name)`, `is_enabled()`, `_attach_log_bridge(resource)`, and `current_trace_id()`. Gated by `OTEL_ENABLED`; when enabled it installs an OTel `LoggerProvider` + `BatchLogRecordProcessor` + `OTLPLogExporter` and attaches a `LoggingHandler` to the root logger so every `log_event` record is also exported over OTLP.
- `shared/shared-contracts/observability-conventions.md` — the authoritative spec for the logging strategy (SPEC-005), documenting the two surfaces (`/metrics` pull + OTel push), the `LOG_LEVEL` / `OTEL_*` environment variables, the fail-open guarantee, and the request-correlation rules.
- Service entrypoints call `configure_logging()` early in startup (e.g. `products/*/src/*/app.py`) so uvicorn's default WARNING-level root logger does not swallow audit records.

## Architecture and conventions

1. **Single source of truth is stdout JSON.** Every business and request event is emitted as one line of JSON via `log_event`. This is explicitly documented as the audit trail; downstream consumers read container stdout, not the OTLP stream.
2. **OTLP mirror, not replacement.** When `OTEL_ENABLED=true`, a `LoggingHandler` bridges the root logger into the OTel log pipeline so records carry the active span's `trace_id`/`span_id` and can be correlated with traces in the backend (OpenObserve). The bridge is attached once per process via `_attach_log_bridge`, guarded by a module-level flag, and recursion is prevented by detaching `opentelemetry`'s own loggers from the root logger.
3. **Fail-open by design.** Both `configure_logging()` and `setup_telemetry()` catch exceptions during initialization and never raise them into the request path. If the OTLP endpoint is unreachable or credentials are invalid, the service continues running; only the export fails.
4. **Request correlation.** `x-request-id` is the log- and portal-facing correlation key. When tracing is active, `current_trace_id()` returns the active W3C trace id and it is set as `x-request-id`; otherwise a generated `req-<uuid4>` is used. Trace context propagates across service boundaries via `traceparent` managed by OTel instrumentation.
5. **Uniform per-service layout.** Each product service ships its own `core/observability.py` and `core/telemetry.py` rather than sharing a common package, but the implementations are byte-for-byte identical across services, ensuring consistent behavior.
6. **Structured field shape.** `log_event` always includes an `event` string plus arbitrary keyword fields flattened into the top-level JSON object. Fields are serialized with `default=str` and keys sorted, producing deterministic output suitable for indexing.
7. **Log levels.** Business/audit events use INFO level. The root logger is raised from uvicorn's default WARNING to INFO at startup via `configure_logging()`. The effective level can be overridden per deployment with `LOG_LEVEL`.

## Conventions and constraints

- **Every service must call `configure_logging()` at app startup** so INFO-level structured records survive uvicorn's default WARNING filter. (Enforced by the convention documented in each `observability.py` docstring.)
- **All audit-relevant events go through `log_event`**, not raw `logger.info(...)`. This ensures a uniform `{"event": ..., ...}` schema consumed by the audit trail.
- **OTel push is off by default** (`OTEL_ENABLED=false`). It must be explicitly enabled; when disabled, no OTel providers are initialized and there is zero overhead.
- **No unbounded label cardinality on metrics** (per `observability-conventions.md`); while this is a metrics rule, it reflects the broader observability discipline applied consistently across services.
- **Secrets for OTLP auth live only in runtime secrets** (`OTEL_EXPORTER_OTLP_HEADERS` provisioned by `sync-otel-secrets.sh`), never committed to the repo.
- **`x-request-id` must never be silently dropped** on inbound requests; it is preserved and forwarded on outbound calls.
- **JSON stdout remains the canonical sink**; the OTLP log bridge is a secondary correlation aid and must not replace stdout-based auditing.