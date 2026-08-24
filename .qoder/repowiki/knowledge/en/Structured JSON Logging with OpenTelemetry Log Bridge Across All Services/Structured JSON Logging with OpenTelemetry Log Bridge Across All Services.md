---
kind: logging_system
name: Structured JSON Logging with OpenTelemetry Log Bridge Across All Services
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
---

## What system/approach is used

The platform uses Python's standard `logging` module as the sole logging framework. Every service emits **single-line, sorted-key JSON** records at `INFO` level through a shared `log_event(logger, event, **fields)` helper that serializes `{"event": <name>, ...fields}` via `json.dumps(..., default=str, sort_keys=True)`. This structured output on stdout is treated as the **audit trail source of truth**. An opt-in OpenTelemetry (OTel) push pipeline mirrors those same records to an OTLP backend (OpenObserve) via a `LoggingHandler` attached to the root logger.

There is no third-party structured-logging library (no structlog, loguru, python-json-logger). The only cross-cutting observability dependency beyond stdlib is OpenTelemetry, which is imported lazily and gated by `OTEL_ENABLED`.

## Key files and packages

- Per-service `core/observability.py` — defines `configure_logging()` and `log_event()`. Identical in every product:
  - `products/agent-platform/src/agent_service/core/observability.py`
  - `products/platform-gateway/src/platform_gateway/core/observability.py`
  - `products/tool-gateway/src/tool_gateway/core/observability.py`
  - `products/audit-service/src/audit_service/core/observability.py`
  - `products/identity-broker/src/identity_service/core/observability.py`
  - `products/incident-service/src/incident_service/core/observability.py`
  - `products/skills-hub/src/skills_hub/core/observability.py`
- Per-service `core/telemetry.py` — initializes OTel traces, metrics, and the log bridge. Present in all services except agent-platform (which reuses the same pattern).
  - `products/platform-gateway/src/platform_gateway/core/telemetry.py`
  - `products/agent-platform/src/agent_service/core/telemetry.py`
  - `products/tool-gateway/src/tool_gateway/core/telemetry.py`
  - `products/audit-service/src/audit_service/core/telemetry.py`
  - `products/identity-broker/src/identity_service/core/telemetry.py`
  - `products/incident-service/src/incident_service/core/telemetry.py`
  - `products/skills-hub/src/skills_hub/core/telemetry.py`
- Central convention doc: `shared/shared-contracts/observability-conventions.md` — the authoritative specification for logging levels, OTel switch semantics, request correlation, and cardinality rules.
- Usage sites: every route/service module imports its local `LOGGER = logging.getLogger(__name__)` and calls `log_event(LOGGER, "<domain_event>", ...)` (e.g. `http_request`, `tool_invoked`, `policy_decision`, `auth_login_started`, `session_created`).

## Architecture and conventions

### Two decoupled surfaces
1. **stdout JSON logs** — always produced; consumed by container log collectors / audit tooling.
2. **OTLP push (opt-in)** — when `OTEL_ENABLED=1`, each service attaches an OTel `LoggingHandler` to the root logger so every `INFO` record is also exported over OTLP HTTP/protobuf to `OTEL_EXPORTER_OTLP_ENDPOINT`. The bridge is fail-open: setup errors are logged and never raised into the request path.

### Log-level strategy
- Uvicorn starts the root logger at `WARNING`; each service calls `configure_logging()` at startup to raise it to `INFO` so business/audit events are not silently dropped. The effective level is read from the `LOG_LEVEL` environment variable (default `INFO`).
- Business and request events are emitted at `INFO` via `log_event`; debug/verbose messages use the normal `logging.debug`/`info`/`warning`/`error` methods on the per-module `LOGGER`.

### Structured fields
- Every audit/event record is a flat JSON object with a required `event` field plus arbitrary domain-specific key/value pairs passed as `**fields`.
- Keys are sorted (`sort_keys=True`) for stable ordering in downstream consumers.
- Values are coerced to strings via `default=str` so non-serializable objects do not break emission.

### Request correlation
- `x-request-id` is the log- and portal-facing correlation key; generated if absent and forwarded on outbound calls.
- When tracing is active, `x-request-id` is set to the active span's W3C `trace_id` (32 hex chars); otherwise it falls back to `req-<uuid4>`.
- Trace/span association between logs and traces is automatic because the OTel `LoggingHandler` attaches `trace_id`/`span_id` when a span is active.

### Metrics/tracing integration
- `/metrics` (Prometheus pull) is always enabled and independent of OTel.
- Traces, metrics, and the log mirror share one gate: `OTEL_ENABLED`. There are no per-signal toggles.
- Resource `service.name` comes from `OTEL_SERVICE_NAME` or the service's metadata name.

### Cardinality and naming rules (from the convention doc)
- Never label on unbounded values (raw URL, user id, session id, request id).
- Metric names follow `<service>_<noun>_<unit>` snake_case with `_total` suffixes for counters.

## Conventions and constraints

- **Every service must call `configure_logging()` at app startup** to raise the root logger above uvicorn's `WARNING` default; this is enforced by tests that patch `LOG_LEVEL` and assert the resulting level (see `test_observability.py` in each product).
- **All audit/business events must go through `log_event`**, not raw `logger.info(...)`, ensuring consistent JSON shape and INFO-level emission.
- **OTel push is off by default**; nothing is initialized unless `OTEL_ENABLED` is truthy. Initialization failures are caught and logged — never propagated.
- **JSON stdout remains the source of truth**; the OTLP log bridge is a mirror for correlation, never a replacement.
- **No per-service custom log formatters** — the platform relies on the uniform `log_event` helper and lets the deployment's log collector parse the JSON lines.
- **Audit events include `request_id`** (and often `trace_id` when available) so they can be correlated across service boundaries.