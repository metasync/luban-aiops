---
kind: logging_system
name: Structured Logging and OTLP Log Bridge Across Services
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/agent-platform/src/agent_service/app.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/audit-service/src/audit_service/core/telemetry.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/telemetry.py
---

## Approach

The platform uses Python's stdlib `logging` module for all application logging, with a thin per-service wrapper that emits single-line JSON records. Structured logs are the audit trail; an opt-in OpenTelemetry OTLP log bridge mirrors them to the backend (OpenObserve) so they can be correlated with traces.

There is no third-party logging framework (no structlog, no loguru). The only cross-cutting observability dependency is OpenTelemetry, which is pulled in lazily and gated by `OTEL_ENABLED`.

## Key files

- `shared/shared-contracts/observability-conventions.md` — the authoritative convention document (SPEC-005 / SPEC-065) describing the two surfaces (`/metrics` pull + OTel push), structured-log level policy, OTLP log bridge semantics, and request-correlation rules.
- `products/*/src/<service>/core/observability.py` — per-service copy of `configure_logging()` and `log_event()`. Each service ships its own tiny implementation:
  - `configure_logging()` reads `LOG_LEVEL` (default `INFO`, upper-cased via `getattr(logging, ...)`), calls `logging.basicConfig(level=level, force=True)` to override uvicorn's WARNING default.
  - `log_event(logger, event, **fields)` serializes `{"event": event, **fields}` as sorted JSON at INFO level.
- `products/*/src/<service>/core/telemetry.py` — per-service copy of the OTel setup. It installs `opentelemetry.instrumentation.logging.handler.LoggingHandler` on the root logger when `OTEL_ENABLED=true`, detaches `logging.getLogger("opentelemetry")` from propagation to prevent recursion, and sets `resource={"service.name": OTEL_SERVICE_NAME or metadata.service_name}`.
- `products/*/src/<service>/app.py` — each service's FastAPI entrypoint calls `configure_logging()` early and then `setup_telemetry(app, service_name)`; business routes call `log_event(LOGGER, "<event>", ...)`.

## Architecture and conventions

1. **Two decoupled surfaces** (per `observability-conventions.md`):
   - `/metrics` (Prometheus pull, always on).
   - OpenTelemetry push (opt-in via `OTEL_ENABLED`; off by default, fail-open).
2. **Structured log format**: every business/request event is one line of JSON produced by `log_event`, emitted at INFO. Fields include at least `event`; additional fields are passed through `json.dumps(..., default=str, sort_keys=True)`.
3. **Log levels**: INFO is the audit-trail level. Uvicorn starts at WARNING, so `configure_logging()` raises the root logger explicitly. `LOG_LEVEL` overrides it per deployment.
4. **OTLP log bridge**: When tracing is enabled, `LoggingHandler` attaches to the root logger so every `logger.info(...)` record is also exported as an OTLP log. Trace/span association is automatic via the active span. Exporter failures cannot recurse because the `opentelemetry` logger is detached.
5. **Fail-open**: All OTel initialization is wrapped in try/except and logged rather than raised. Missing/misconfigured backends produce export-time drops but never break requests.
6. **Request correlation**: `x-request-id` is the log/portal-facing key; `traceparent` (W3C) is machine-facing. When tracing is active, `x-request-id` is set to the active span's W3C `trace_id`; otherwise it falls back to `req-<uuid4>`.
7. **Service identity**: `service.name` resource attribute comes from `OTEL_SERVICE_NAME` or the service's metadata name.
8. **Per-service duplication**: Each product service (`agent-platform`, `audit-service`, `execution-runtime`, `identity-broker`, `incident-service`, `platform-gateway`, `skills-hub`, `tool-gateway`) ships its own `core/observability.py` and `core/telemetry.py` with identical logic. There is no shared SDK yet — the convention doc is the contract.

## Conventions and constraints

- Business events use `log_event(LOGGER, "<event_name>", **fields)` at INFO level; ad-hoc `LOGGER.info(json.dumps(...))` calls exist in some modules but the documented path is `log_event`.
- Audit-trail records must survive at INFO level; `LOG_LEVEL` defaults to `INFO` and tests assert that lowering it would discard http_request/tool_invoked/policy-decision records.
- OTel push is controlled exclusively by `OTEL_ENABLED` — there are no per-signal toggles for traces/metrics/logs.
- OTLP endpoint: `OTEL_EXPORTER_OTLP_ENDPOINT` (HTTP/protobuf); auth via `OTEL_EXPORTER_OTLP_HEADERS`; service name via `OTEL_SERVICE_NAME`.
- High-cardinality values (raw URL, user id, session id, request id) are forbidden as metric labels; this rule is enforced by review per the conventions doc.
- Domain metrics follow `<service>_<noun>_<unit>` naming with bounded enum labels; counters carry `_total`.
- The OTLP log bridge is additive: stdout JSON remains the source of truth for audit tooling; the bridge exists only for trace/log correlation.