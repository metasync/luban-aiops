---
kind: logging_system
name: Structured JSON Logging with OpenTelemetry Trace Bridging
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/agent-platform/src/agent_service/app.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/tool-gateway/src/tool_gateway/app.py
    - products/identity-broker/src/identity_service/app.py
    - products/agent-platform/src/agent_service/core/request_context.py
    - products/platform-gateway/src/platform_gateway/core/request_context.py
    - products/tool-gateway/src/tool_gateway/core/request_context.py
    - products/identity-broker/src/identity_service/core/telemetry.py
    - products/agent-platform/tests/test_observability.py
---

## What system/approach is used

Each service in the platform (agent-platform, platform-gateway, identity-broker, tool-gateway) implements an identical, self-contained logging subsystem built on Python's stdlib `logging` module. There is no third-party logging framework (no structlog, loguru, or logzero). The core pattern lives in each service's `core/observability.py`, which exposes two functions:

- `configure_logging()` — raises the root logger from Uvicorn's default `WARNING` to `INFO` so that structured audit events are not silently dropped; the effective level is read from the `LOG_LEVEL` environment variable and defaults to `INFO`.
- `log_event(logger, event, **fields)` — serializes a single-line JSON record via `json.dumps(payload, default=str, sort_keys=True)` at `logger.info(...)`. Every business and request event is emitted this way, producing a flat JSON object whose first field is always `event` (e.g. `http_request`, `tool_invoked`, `policy_decision`, `token_delegation`).

Structured logs are therefore plain JSON lines on stdout/stderr, consumable by any log sink (the organization uses Elastic as the backend per the conventions doc).

OpenTelemetry push is opt-in and completely decoupled from the logging pipeline. It is initialized in `core/telemetry.py` only when `OTEL_ENABLED` is truthy; initialization errors are caught and logged rather than raised (fail-open). When tracing is active, the active span's W3C `trace_id` is bridged into the log correlation key (`x-request-id`) so a single value joins structured logs and APM traces.

## Key files and packages

- `products/*/src/<service>/core/observability.py` — identical `configure_logging()` / `log_event()` implementation in all four services.
- `products/*/src/<service>/app.py` — calls `configure_logging()` during FastAPI app creation and installs an HTTP middleware that emits `http_request` events via `log_event`.
- `products/*/src/<service>/core/request_context.py` — `resolve_request_id()` resolves the `x-request-id` header, falling back to the active OTel trace ID or a generated `req-<uuid4>`.
- `products/*/src/<service>/core/telemetry.py` — opt-in OTLP exporter setup, `current_trace_id()`, and `is_enabled()`.
- `shared/shared-contracts/observability-conventions.md` — the cross-service specification governing levels, fields, correlation keys, metric naming, cardinality rules, and OTel switch semantics.
- `products/agent-platform/tests/test_observability.py` — unit tests asserting default INFO level, `LOG_LEVEL` override behavior, and `/metrics` availability.

## Architecture and conventions

### Log-level strategy
The root logger is explicitly configured at process start via `logging.basicConfig(level=..., force=True)`. The default level is `INFO`; it can be overridden per deployment through the `LOG_LEVEL` environment variable. This is enforced by tests that assert `logging.getLogger().level == logging.INFO` after `configure_logging()` without `LOG_LEVEL` set, and that setting `LOG_LEVEL=WARNING` changes the root level accordingly.

### Structured event format
Every audit/log event goes through `log_event(logger, event, **fields)`, which builds `{"event": event, **fields}` and dumps it as sorted-key JSON. Common fields observed across services include `service`, `request_id`, `method`, `path`, `status_code`, `duration_ms` for HTTP requests, plus domain-specific fields like `tool_invoked`, `decision`, `result`, etc. Because `default=str` is used, non-serializable values are coerced to strings rather than raising.

### Request correlation
All services implement the same correlation rule documented in `observability-conventions.md` (SPEC-005 R-4):
1. If the inbound `x-request-id` header is present, use it verbatim.
2. Otherwise, if tracing is enabled, bridge the active OTel span's W3C `trace_id` (32 hex chars).
3. Otherwise, generate a `req-<uuid4>` fallback.
No service may silently drop an inbound correlation id.

### Service boundary
Each service owns its own `core/observability.py` and `core/telemetry.py`; there is no shared package for logging code. The duplication is intentional — every service is independently deployable and must call `configure_logging()` at startup.

### Relationship to metrics/tracing
Logging is deliberately decoupled from metrics and tracing:
- `/metrics` (Prometheus pull) is always on, implemented via `prometheus-fastapi-instrumentator` in `core/metrics.py`.
- OTLP push (traces + metrics) is off by default, gated by `OTEL_ENABLED`, and fails open.
- Structured logs are the audit trail; metrics are counters/durations; traces are machine-facing propagation headers (`traceparent`).

## Conventions and constraints

Observed conventions (descriptive):
- All business and request events are emitted as single-line JSON at `INFO` level via `log_event(...)`.
- Each service's `create_app()` calls `configure_logging()` before creating the FastAPI instance.
- An HTTP middleware on every service emits an `http_request` event containing `service`, `request_id`, `method`, `path`, `status_code`, `duration_ms`.
- Correlation IDs flow via `x-request-id`; tracing flows via W3C `traceparent` managed by OpenTelemetry instrumentation.
- Metric labels follow `<service>_<noun>_<unit>` snake_case naming with bounded enum values; high-cardinality values (raw URL, user id, session id, request id) are never used as labels.

Enforced rules (documented in `shared/shared-contracts/observability-conventions.md` and verified by tests):
- The root logger must be raised to `INFO` by default so audit records survive; `LOG_LEVEL` may override it.
- `OTEL_ENABLED` is the master gate for OTel push; when false, no providers are initialized and `/metrics` remains unaffected.
- No service may silently drop an inbound correlation id.
- Cardinality rule: do not label metrics on raw URLs, user ids, session ids, or request ids.
- Fail-open guarantee: OTel setup exceptions are logged, never raised into the request path.