---
kind: logging_system
name: Structured JSON Audit Logging with Per-Service Observability Modules
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/request_context.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/agent-platform/src/agent_service/app.py
    - products/identity-broker/src/identity_service/api/routes/auth.py
---

## What system/approach is used

The platform uses Python's standard `logging` module exclusively — no third-party logging frameworks (no structlog, loguru, or similar). Each service ships a tiny, self-contained `core/observability.py` that provides two functions:

- `configure_logging()` — raises the root logger from uvicorn's default `WARNING` to `INFO` so audit records are never silently dropped; level can be overridden per deployment via the `LOG_LEVEL` environment variable.
- `log_event(logger, event, **fields)` — emits a single-line JSON record at `INFO` level: `{"event": <name>, ...fields}` with keys sorted and non-string values coerced via `default=str`.

There is no centralized shared library for logging; each product (`agent-platform`, `audit-service`, `identity-broker`, `platform-gateway`, `skills-hub`, `tool-gateway`) duplicates this identical module. The convention is documented centrally in `shared/shared-contracts/observability-conventions.md`, which defines the structured logging levels, correlation-id rules, and OTel integration policy.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — authoritative spec for metrics, tracing, request correlation, and structured logging conventions across all services.
- Per-service `src/<service>/core/observability.py` — identical implementations of `configure_logging()` and `log_event()`.
- Per-service `src/<service>/core/request_context.py` (e.g. `platform_gateway/core/request_context.py`) — resolves the `x-request-id` correlation key per SPEC-005 R-4.
- Per-service `src/<service>/core/telemetry.py` — exposes `current_trace_id()` used by request-context to bridge W3C trace context into logs.
- Service entrypoints (`app.py`, `main.py`) call `configure_logging()` during startup and emit `http_request` events in middleware.

## Architecture and conventions

### Structured log format
Every business and request event is emitted as one JSON line via `log_event(...)`. The first field is always `event` (a stable string name such as `http_request`, `auth_login_completed`, `token_exchange_rejected`, `tool_invoked`). Additional fields are passed as keyword arguments and serialized deterministically (`sort_keys=True`).

### Log-level strategy
- Uvicorn starts with root logger at `WARNING`; `configure_logging()` explicitly sets it to `INFO` (overridable via `LOG_LEVEL`).
- All audit-relevant events use `INFO` level so they survive the default uvicorn configuration.
- Tests assert the configured level (e.g. `test_observability.py` checks `logging.getLogger().level == logging.INFO`).

### Request correlation and trace bridging
- `x-request-id` is the log- and portal-facing correlation key. It is generated if absent (preserving the portal contract) and forwarded on every outbound call.
- When OpenTelemetry tracing is active, `x-request-id` is set to the active span's W3C `trace_id` (32 hex chars); when tracing is inactive it falls back to `req-<uuid4>`.
- No service may silently drop an inbound correlation id.

### Audit trail vs. debug logs
The conventions treat structured INFO logs as the audit trail (HTTP requests, tool invocations, policy decisions, auth flows). Debug/exception traces still go through the normal `logging.Logger` hierarchy; only the `log_event(...)` path is treated as auditable.

### Telemetry coupling
Logging is decoupled from metrics/tracing:
- `/metrics` (Prometheus pull endpoint) is always on.
- OpenTelemetry push is opt-in via `OTEL_ENABLED`; disabled means zero overhead and no impact on logging.
- `log_event` does not depend on OTel — correlation IDs are resolved independently.

### Cross-service propagation
Services propagate `x-request-id` and `traceparent` headers on outbound calls so a single request can be traced end-to-end across gateway → identity broker → agent platform / tool gateway → audit service.

## Conventions and constraints

- **Every service must call `configure_logging()` at app startup** so INFO audit records are not filtered by uvicorn's WARNING default. This is enforced by the duplicated module docstrings and verified by tests.
- **Audit events must use `log_event(...)` at INFO level**, never raw `logger.info("...")`, to guarantee JSON structure and deterministic field ordering.
- **Never label metrics with unbounded values** (raw URL, user id, session id, request id) — cardinality rule from the conventions spec.
- **Correlation ids must never be dropped**: inbound `x-request-id` is preserved and forwarded; missing values are bridged to `trace_id` or generated UUID.
- **OTel push is fail-open**: unreachable or misconfigured collectors must not break requests; initialization is guarded and logged rather than raising.
- **Log level override**: `LOG_LEVEL` environment variable controls the root logger level per deployment; default stays `INFO` so audit records are never silently discarded.
- **No shared logging SDK**: each product ships its own `core/observability.py`; there is no cross-package import of a logging utility, so changes must be replicated consistently.