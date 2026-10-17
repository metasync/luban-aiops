---
kind: logging_system
name: Structured Logging via Python stdlib logging with OTLP Bridge
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/agent-platform/src/agent_service/app.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
---

## What system/approach is used

The platform uses **Python's built-in `logging` module** (no third-party logger framework such as structlog or loguru). Structured, single-line JSON audit records are emitted through a thin per-service wrapper that serializes a dict of fields via `json.dumps(..., sort_keys=True)`. An opt-in OpenTelemetry bridge (`opentelemetry.instrumentation.logging.handler.LoggingHandler`) mirrors every record to the OTLP HTTP/protobuf pipeline when `OTEL_ENABLED=true`, so logs join traces in OpenObserve.

Two observability surfaces are deliberately decoupled:
- `/metrics` (Prometheus pull, always on)
- OTLP push (traces + metrics mirror + log mirror, gated by `OTEL_ENABLED`, default off, fail-open)

This is documented centrally in `shared/shared-contracts/observability-conventions.md` and implemented once per service under `<service>/core/observability.py` plus `<service>/core/telemetry.py`.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — authoritative spec for metric naming, cardinality rules, OTel switch semantics, structured logging levels, request correlation, and the OTLP log bridge contract.
- Per-service `core/observability.py` — defines `configure_logging()` (raises root logger from uvicorn's WARNING default to INFO; overridable via `LOG_LEVEL`) and `log_event(logger, event, **fields)` which emits a single JSON line at INFO level.
- Per-service `core/telemetry.py` — implements `setup_telemetry(app, service_name)`, `is_enabled()`, `current_trace_id()`, and the `MetricsMirror` class that re-emits prometheus families as OTel instruments (SPEC-065 R-2).
- Per-service `app.py` — calls `configure_logging()` during FastAPI startup and wires the HTTP request middleware to emit an `http_request` event via `log_event`.

Observed across eight product services: `agent-platform`, `audit-service`, `execution-runtime`, `identity-broker`, `incident-service`, `platform-gateway`, `skills-hub`, `tool-gateway`.

## Architecture and conventions

1. **Per-service duplication of the observability shim.** Each service ships its own `core/observability.py` and `core/telemetry.py` with identical `configure_logging` / `log_event` signatures. The convention is enforced by tests (`TelemetryParityTest` referenced in `telemetry.py`) that assert byte-identical behavior across services.
2. **Structured field shape.** Every business/request event goes through `log_event(logger, "event_name", service=..., request_id=..., ...)` producing a flat JSON object with keys `event` plus the supplied fields, sorted alphabetically.
3. **Log level policy.** Default root level is `INFO`; `LOG_LEVEL` overrides it. This is required because uvicorn defaults to `WARNING`, which would silently drop all audit records.
4. **OTLP log bridge.** When `OTEL_ENABLED=true`, `setup_telemetry` attaches an `opentelemetry.exporter.otlp.proto.http._log_exporter.OTLPLogExporter` via `LoggingHandler` to the root logger. Trace/span association is automatic: records emitted inside an active span carry `trace_id`/`span_id`. The `opentelemetry.*` loggers are detached (`propagate = False`) to prevent recursion if the exporter fails.
5. **Request correlation.** `x-request-id` is the log- and portal-facing correlation key; when tracing is active it is set to the active W3C `trace_id`, otherwise generated as `req-<uuid4>`. It is forwarded on every outbound call.
6. **Fail-open guarantees.** Both the OTel setup and the `MetricsMirror` catch exceptions, log them via `LOGGER.exception(...)`, and continue without raising into the request path. Disabling OTel leaves `/metrics` fully functional.
7. **Cardinality discipline.** `observability-conventions.md` forbids high-cardinality labels (raw URL, user id, session id, request id) — enforced by review, not code.
8. **Domain-metric mirroring.** `MetricsMirror` re-emits each service's prometheus domain families as OTel instruments with the same name and bounded label set, so dashboards can consume them over the OTLP push path (ADR-0014 / SPEC-065).

## Conventions and constraints

- **Convention:** All structured events go through `log_event(logger, event, **fields)` rather than direct `logger.info(...)` calls — observed consistently in API route handlers and service modules.
- **Convention:** Each service initializes logging via `configure_logging()` at FastAPI app creation time, before any request handling.
- **Convention:** Business and request events are emitted at `INFO` level; warnings/errors use `LOGGER.warning(...)` / `LOGGER.exception(...)` directly.
- **Rule (documented):** `LOG_LEVEL` controls the root logger level; the default must stay `INFO` so audit records are never silently discarded (`observability-conventions.md`).
- **Rule (documented):** OTel push is controlled exclusively by `OTEL_ENABLED` (default `false`); there are no per-signal toggles (`observability-conventions.md`).
- **Rule (documented):** `x-request-id` must never be silently dropped on inbound requests (`observability-conventions.md`).
- **Rule (documented):** Never use unbounded values as metric/log labels — raw URLs, user ids, session ids, request ids are explicitly prohibited (`observability-conventions.md`).
- **Rule (enforced by design):** The OTLP bridge is attached only once per process (guarded by `_log_bridge_attached`), and `opentelemetry` loggers have propagation disabled to prevent recursive export loops (`products/*/core/telemetry.py`).
- **Rule (enforced by parity test):** The `core/telemetry.py` implementation must remain byte-identical across all eight services, verified by `TelemetryParityTest`.