---
kind: logging_system
name: Structured Logging via Python logging + OTLP Bridge
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
---

## Approach

The platform uses the standard-library `logging` module for all application output. There is no third-party logger framework (no structlog, loguru, or similar). Each product service ships its own tiny `core/observability.py` that exposes two functions — `configure_logging()` and `log_event(logger, event, **fields)` — which every service imports from its own package.

Business and request events are emitted as single-line JSON records at INFO level through `log_event(...)`. The payload is `{"event": <name>, ...fields}`, serialized with `json.dumps(..., default=str, sort_keys=True)`, then logged via `logger.info(...)`. This makes stdout the canonical audit trail; downstream consumers parse JSON lines rather than text patterns.

## Initialization and Levels

- `configure_logging()` calls `logging.basicConfig(level=..., force=True)` on the root logger. It reads `LOG_LEVEL` from the environment (defaulting to `"INFO"`) and converts it via `getattr(logging, level_name.upper(), logging.INFO)`, so any invalid value falls back to INFO.
- Uvicorn's default WARNING root level would silently drop all `log_event` records, so calling `configure_logging()` at app startup is mandatory — every service's `app.py` does this before mounting routes.
- Tests assert the fallback behavior: when `LOG_LEVEL` is absent the root level becomes INFO; when set to `WARNING` it becomes WARNING; a call without env restores the default.

## Per-Service Layout

Each of the eight Python services follows the same layout:

```
products/<service>/src/<package>/
├── core/observability.py   # configure_logging() + log_event()
├── core/telemetry.py       # OTel push pipeline (optional)
└── app.py                  # calls configure_logging() + log_event("app_started", ...)
```

Services observed with this pattern: `agent-platform`, `audit-service`, `execution-runtime`, `identity-broker`, `incident-service`, `platform-gateway`. Other services (`skills-hub`, `tool-gateway`, `policy-center`) were not fully scanned but follow the same convention where present.

## OTLP Log Bridge

When OpenTelemetry push is enabled (`OTEL_ENABLED=true`), `core/telemetry.py` attaches an OTel `LoggingHandler` to the root logger (`_attach_log_bridge`). Every structured record emitted by `log_event` is therefore mirrored to the OTLP log pipeline in addition to stdout. Key behaviors:

- The bridge is attached once per process via a `_log_bridge_attached` guard.
- `opentelemetry`'s internal loggers are detached from the root logger (`propagate = False`) so exporter failures cannot recurse into the bridge.
- The handler is configured at `logging.INFO`, matching the audit-trail level.
- Trace/span association is automatic: records emitted inside an active span carry W3C `trace_id`/`span_id`, joining logs to traces on the same id used by `x-request-id`.
- The bridge is gated by the same `OTEL_ENABLED` switch and fails open — setup errors are logged and swallowed.

## Structured Fields and Correlation

Business events use a flat key/value shape passed as keyword arguments to `log_event`. Common fields include `request_id` (the portal-facing correlation key, bridged to the active span's W3C `trace_id` when tracing is active), plus domain-specific keys such as `tool_name`, `decision`, `user_id`, etc. Because `sort_keys=True` is applied during serialization, field order is deterministic across runs.

## Conventions and Constraints

1. **Audit records are INFO-level JSON.** The observability conventions document states: "All business and request events are emitted as single-line JSON via `log_event(...)` at INFO level." Services call `configure_logging()` at startup to raise the root logger from uvicorn's WARNING default to INFO, and the default must stay INFO so audit records are never silently discarded.
2. **`LOG_LEVEL` overrides the root level.** Read from the environment, upper-cased, resolved via `getattr(logging, ...)`, falling back to INFO for unknown values.
3. **JSON stdout is the source of truth.** The OTLP mirror exists only so the backend can correlate logs with traces; audit tooling must keep reading stdout.
4. **No third-party logger framework.** All services use `import logging` and `logging.getLogger(__name__)` for their module-level `LOGGER` instances.
5. **OTel push is opt-in and fail-open.** Controlled by `OTEL_ENABLED`; when disabled, no OTel providers or instrumentation are initialized and `/metrics` stays unaffected. Exporter failures are logged and swallowed.
6. **Request correlation via `x-request-id`.** Set to the active span's W3C `trace_id` (32 hex chars) when tracing is active; otherwise falls back to a generated `req-<uuid4>`.
7. **Cardinality rules apply to labels** (from `shared/shared-contracts/observability-conventions.md`): never label on raw URL, user id, session id, or request id — these explode cardinality and are rejected at review.