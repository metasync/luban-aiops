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
    - products/platform-gateway/src/platform-gateway/core/request_context.py
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
---

## What system/approach is used

The platform uses Python's standard `logging` module as the sole logging framework. Every product service (agent-platform, audit-service, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway) ships an identical `core/observability.py` that provides two functions: `configure_logging()` and `log_event(logger, event, **fields)`. There is no third-party structured-logging library (no structlog, loguru, or similar).

Structured logs are single-line JSON emitted at INFO level via `json.dumps(payload, default=str, sort_keys=True)`, where each record carries a required `event` field plus arbitrary domain fields. The root logger is raised from uvicorn's default WARNING to INFO so these audit records are never silently discarded.

An opt-in OpenTelemetry push pipeline (`core/telemetry.py`) bridges the same stdout JSON records into OTLP logs when `OTEL_ENABLED=true`, attaching trace/span context automatically. This bridge is additive — container stdout remains the source of truth for the audit trail.

## Key files and packages

- Per-service `src/<service>/core/observability.py` — defines `configure_logging()` and `log_event()` (identical across all services).
- Per-service `src/<service>/core/telemetry.py` — implements the OTel push pipeline, log bridge, and `current_trace_id()` helper.
- Per-service `src/<service>/core/request_context.py` — resolves `x-request-id` by bridging active OTel trace IDs to the portal-facing correlation key.
- `shared/shared-contracts/observability-conventions.md` — the authoritative spec documenting the conventions below.
- Service entrypoints (`app.py`, `main.py`) call `configure_logging()` during startup and `setup_telemetry(app, service_name)` when tracing is enabled.

## Architecture and conventions

**Initialization.** Each service calls `configure_logging()` at app startup. It reads `LOG_LEVEL` (default `INFO`), maps it to a `logging` constant, and calls `logging.basicConfig(level=..., force=True)` on the root logger. This raises the effective level above uvicorn's WARNING so audit events survive.

**Emission pattern.** Business and request events are emitted through `log_event(LOGGER, "<event_name>", **fields)`. The function builds `{"event": <name>, ...fields}` and writes it at INFO via `logger.info(json.dumps(...))`. Call sites in routes/services use this instead of calling `logger.info(...)` directly, ensuring every audit record has the `event` discriminator.

**Level strategy.** INFO is the audit baseline; DEBUG/WARNING/ERROR remain available for non-audit noise. The default must stay INFO — the convention explicitly forbids lowering it because audit records would be dropped.

**Structured fields.** Fields are passed as keyword arguments and serialized with `sort_keys=True` and `default=str`, so any serializable value becomes a flat JSON object. No nested loggers per subsystem — modules import the module-level `LOGGER = logging.getLogger(__name__)` and pass it to `log_event`.

**Request correlation.** `request_context.resolve_request_id()` produces the `x-request-id` header used in every log record. When OTel tracing is active, it borrows the active span's W3C `trace_id`; otherwise it generates `req-<uuid4>`. This value is included in log payloads so traces and logs join on a single key.

**OTel log bridge.** When `OTEL_ENABLED=true`, `setup_telemetry()` attaches an OTel `LoggingHandler` to the root logger. The handler mirrors every INFO+ record over OTLP HTTP/protobuf to `OTEL_EXPORTER_OTLP_ENDPOINT`. The bridge:
- Is gated by the same `OTEL_ENABLED` flag as traces/metrics.
- Detaches `opentelemetry.*` loggers from propagation to prevent recursion on exporter failure.
- Automatically attaches `trace_id`/`span_id` when emitted inside an active span.
- Fails open — setup exceptions are logged and do not break the request path.

**Service naming.** `OTEL_SERVICE_NAME` (defaulting to the service's metadata name) tags resource attributes so cross-service traces and logs can be grouped.

## Conventions and constraints

- **All business/request events go through `log_event` at INFO level.** The observability conventions document states this is the audit trail contract; tests assert the root logger level after `configure_logging()`.
- **Root logger level is configurable via `LOG_LEVEL` but defaults to INFO.** Tests verify both the default INFO behavior and override via environment.
- **No unbounded label values in metrics** (related observability constraint documented in `observability-conventions.md`).
- **OTel push is opt-in and fail-open.** `OTEL_ENABLED=false` (default) initializes nothing; initialization errors are caught and logged rather than raised.
- **Container stdout JSON is the source of truth.** The OTLP mirror exists only for correlation with traces; downstream tooling must keep reading stdout.
- **`x-request-id` must never be silently dropped.** Inbound correlation IDs are preserved and forwarded on outbound calls.
- **Audit events include bounded enum labels** (e.g., `decision ∈ {allow, deny}`, `result ∈ {valid, invalid, expired, missing}`) to avoid cardinality explosion.