---
kind: logging_system
name: Structured JSON Logging with OTLP Bridge and LOG_LEVEL Control
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/agent-platform/src/agent_service/core/request_context.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/platform-gateway/src/platform_gateway/core/request_context.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/telemetry.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
---

## What system/approach is used

The platform uses Python's stdlib `logging` module as the sole logging framework across every service. There is no third-party logger (no structlog, loguru, or similar). Each service ships an identical `core/observability.py` that provides two helpers: `configure_logging()` to raise the root logger from uvicorn's default WARNING level to INFO (so audit records are not silently dropped), and `log_event(logger, event, **fields)` which serializes a single-line JSON object `{"event": <name>, ...fields}` via `json.dumps(..., sort_keys=True, default=str)` at INFO level. This JSON line on stdout is the canonical audit trail.

OpenTelemetry is layered on top as an opt-in mirror pipeline. The per-service `core/telemetry.py` initializes traces, metrics, and a `LoggingHandler` bridge when `OTEL_ENABLED=1`. The bridge attaches to the root logger so every structured record emitted by `log_event` is also exported as an OTLP log record; OTel's own loggers are explicitly detached (`logging.getLogger("opentelemetry").propagate = False`) to prevent recursion. When tracing is active, logs automatically carry `trace_id`/`span_id`, joining them to APM traces.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — authoritative spec for all services (SPEC-005): defines the two surfaces (`/metrics` pull + OTLP push), environment variables, correlation rules, cardinality constraints, and the structured logging contract.
- Per-service `src/<service>/core/observability.py` — identical `configure_logging()` / `log_event()` implementation in every product:
  - `products/agent-platform/src/agent_service/core/observability.py`
  - `products/platform-gateway/src/platform_gateway/core/observability.py`
  - `products/tool-gateway/src/tool_gateway/core/observability.py`
  - `products/audit-service/src/audit_service/core/observability.py`
  - `products/identity-broker/src/identity_service/core/observability.py`
  - `products/incident-service/src/incident_service/core/observability.py`
  - `products/skills-hub/src/skills_hub/core/observability.py`
- Per-service `src/<service>/core/telemetry.py` — OTel setup, `setup_telemetry(app, service_name)`, `is_enabled()`, `current_trace_id()`.
- Per-service `src/<service>/core/request_context.py` — `resolve_request_id()` bridges inbound `x-request-id` to the active OTel trace id when tracing is on, falling back to `req-<uuid4>`.
- Call sites throughout each service's `api/routes/*` and `services/*` modules invoke `log_event(LOGGER, "<domain_event>", request_id=x_request_id, ...)`.

## Architecture and conventions

1. **Single source of truth is stdout JSON.** Every business and request event is one JSON line at INFO level. Consumers read container stdout; OTLP is only a correlated mirror.
2. **Log level is controlled by `LOG_LEVEL`** (default INFO). Services call `configure_logging()` at app startup to override uvicorn's WARNING default. Tests assert both the default INFO behavior and that setting `LOG_LEVEL=WARNING` suppresses audit records.
3. **Event-driven structured schema.** `log_event(logger, event, **fields)` enforces a flat payload with an `event` name plus arbitrary key/value fields. Fields like `request_id`, `user_id`, `tool`, `decision`, `status` are consistently attached by callers.
4. **Request correlation.** `x-request-id` is the portal-facing correlation key. It is resolved via `resolve_request_id()`: prefer inbound header, then active OTel `trace_id`, then generated UUID. When tracing is active, `x-request-id` equals the W3C `traceparent` trace id, so a single value joins logs and traces.
5. **OTel push is opt-in and fail-open.** `OTEL_ENABLED` gates the entire pipeline (traces + metrics + logs). Initialization errors are caught and logged; they never break the request path. Missing/malformed credentials cause export-time drops, not runtime failures.
6. **Cardinality rules enforced by convention.** Labels must be bounded enums; raw URLs, user ids, session ids, request ids are forbidden as metric labels. Structured log fields can carry high-cardinality values because they are lines, not Prometheus labels.
7. **Metrics surface is separate.** `/metrics` is always-on Prometheus (implemented directly with `prometheus_client`); it is independent of OTel and unaffected by `OTEL_ENABLED`.

## Conventions and constraints

- **Every service must call `configure_logging()` at startup** so INFO audit records survive uvicorn's WARNING default. This is verified by tests in each product.
- **Business events must go through `log_event(...)`, not direct `logger.info(...)`**, ensuring consistent JSON shape and INFO severity for audit-trail records.
- **Audit records must never be silenced**: the default `LOG_LEVEL` is INFO; overriding to WARNING is a deployment-time decision, not a code default.
- **No unbounded label cardinality** on metrics (raw URL, user id, session id, request id are explicitly forbidden).
- **OTLP endpoint and auth** come from `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_EXPORTER_OTLP_HEADERS`; secrets are provisioned via runtime secrets, never committed.
- **Trace/span association** is automatic via the OTel `LoggingHandler`; no manual `trace_id` injection into log fields is needed when a span is active.
- **`x-request-id` must never be silently dropped** on inbound requests; it is propagated on every outbound service-to-service call.