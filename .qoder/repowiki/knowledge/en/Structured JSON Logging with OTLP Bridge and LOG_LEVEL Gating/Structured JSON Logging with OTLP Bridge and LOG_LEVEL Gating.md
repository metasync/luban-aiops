---
kind: logging_system
name: Structured JSON Logging with OTLP Bridge and LOG_LEVEL Gating
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/agent-platform/src/agent_service/app.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/tests/test_observability.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
---

## What system/approach is used

The platform uses Python's built-in `logging` module as the sole logging framework. Each product service ships an identical `core/observability.py` that provides two helpers: `configure_logging()` (raises the root logger from uvicorn's default WARNING to INFO so audit records are not silently dropped) and `log_event(logger, event, **fields)` which emits a single-line JSON object via `json.dumps(payload, default=str, sort_keys=True)` at INFO level. There is no third-party structured-logging library; all business and request events are emitted through this helper.

An opt-in OpenTelemetry push pipeline (`core/telemetry.py`) bridges stdout JSON logs into OTLP HTTP/protobuf when `OTEL_ENABLED=true`. It attaches an OTel `LoggingHandler` to the root logger so every `log_event(...)` record is mirrored to the backend alongside traces and metrics. The bridge is fail-open: initialization or export failures are logged and never raised into the request path.

## Key files and packages

- Per-service `core/observability.py` — defines `configure_logging()` and `log_event()`. Present in every product:
  - `products/agent-platform/src/agent_service/core/observability.py`
  - `products/platform-gateway/src/platform_gateway/core/observability.py`
  - `products/audit-service/src/audit_service/core/observability.py`
  - `products/execution-runtime/src/execution_runtime/core/observability.py`
  - `products/identity-broker/src/identity_service/core/observability.py`
  - `products/incident-service/src/incident_service/core/observability.py`
  - `products/skills-hub/src/skills_hub/core/observability.py`
  - `products/tool-gateway/src/tool_gateway/core/observability.py`
- Per-service `core/telemetry.py` — OTel setup, log bridge attachment, `current_trace_id()` helper.
- Shared convention doc: `shared/shared-contracts/observability-conventions.md` — documents the two-surface model, metric naming, cardinality rules, OTel switch semantics, structured logging levels, OTLP log bridge behavior, and request-correlation bridging.
- Service entry points call `configure_logging()` early in `create_app()` (e.g. `products/agent-platform/src/agent_service/app.py`).
- Tests asserting behavior: e.g. `products/platform-gateway/tests/test_observability.py`, `products/agent-platform/tests/test_observability.py`, `products/identity-broker/tests/test_observability.py`.

## Architecture and conventions

### Two observability surfaces
Per `observability-conventions.md`, each service exposes:
1. `/metrics` (Prometheus pull, always on).
2. OpenTelemetry push (opt-in via `OTEL_ENABLED`; disabled by default, zero overhead when off).
The two are decoupled — disabling OTel does not affect `/metrics`.

### Structured log format
Every business/request event is emitted as one line of JSON containing at minimum an `event` field plus domain-specific key/value pairs. Fields are serialized with `default=str` and sorted keys for deterministic output. The audit trail consists of these INFO-level records (e.g. `http_request`, `tool_invoked`, policy decisions, auth flows); they must never be filtered out.

### Log level strategy
- Default root logger level is **INFO** (raised from uvicorn's WARNING) so audit records survive.
- Overridable per deployment via the `LOG_LEVEL` environment variable (`INFO`, `WARNING`, `DEBUG`, etc.).
- Tests assert that without `LOG_LEVEL` set, the root logger settles at `logging.INFO`.

### Request correlation and trace bridging
- `x-request-id` is the log- and portal-facing correlation key, generated if absent and forwarded on outbound calls.
- When tracing is active, `x-request-id` is bridged to the active span's W3C `trace_id` (32 hex chars); otherwise it falls back to `req-<uuid4>`.
- `traceparent` (W3C Trace Context) is the machine-facing propagation header managed by OTel instrumentation.
- No service may silently drop an inbound correlation id.

### OTLP log bridge
When `OTEL_ENABLED=true`, `setup_telemetry()` attaches an OTel `LoggingHandler` to the root logger. Semantics:
- JSON stdout remains the source of truth; OTLP is a mirror for backend correlation.
- Records emitted inside an active span automatically carry `trace_id`/`span_id`, joining them to the trace view via the same W3C id backing `x-request-id`.
- Recursion guard: `opentelemetry` loggers are detached from the root logger so exporter failures cannot loop back.
- Fail-open: missing/misconfigured credentials produce 401s at export time; batch processors drop telemetry on failure; service setup catches exceptions and continues.

### Metric and cardinality rules (related observability)
- Metric names follow `<service>_<noun>_<unit>` snake_case; counters end in `_total`.
- Labels are bounded enums only; raw URLs, user ids, session ids, request ids are never used as labels.

## Conventions and constraints

- **All services must call `configure_logging()` at app startup.** This is enforced by the shared convention doc and verified by tests that assert the root logger defaults to INFO.
- **Emit business/request events via `log_event(...)`, not direct `logger.info(...)` calls.** The helper guarantees the canonical `{"event": ..., **fields}` JSON shape used by the audit trail.
- **Audit records must remain at INFO level.** Raising the root logger above INFO would discard them; the default is intentionally INFO and tests verify this invariant.
- **OTel push is opt-in and fail-open.** `OTEL_ENABLED=false` (default) leaves the service fully functional with only stdout JSON logs and `/metrics`; enabling it adds a non-blocking OTLP mirror.
- **No unbounded label cardinality.** Raw identifiers (URL, user id, session id, request id) are forbidden as metric labels; this rule is explicitly called out in the convention doc and enforced at review.
- **Correlation ids must be preserved.** Inbound `x-request-id` is never silently dropped; when tracing is active it is bridged to the W3C `trace_id`.
- **Secrets for OTel auth (`OTEL_EXPORTER_OTLP_HEADERS`) are provisioned via runtime secrets, never committed.**
- **Each product maintains its own copy of `core/observability.py` and `core/telemetry.py`**, keeping services self-contained while following the shared contract documented in `shared/shared-contracts/observability-conventions.md`.