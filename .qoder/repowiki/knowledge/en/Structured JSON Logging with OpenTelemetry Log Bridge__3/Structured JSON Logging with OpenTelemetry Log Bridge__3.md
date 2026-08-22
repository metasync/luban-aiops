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
    - products/platform-gateway/src/platform_gateway/core/request_context.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/audit-service/src/audit_service/core/telemetry.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/telemetry.py
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
---

## What system/approach is used

The platform uses Python's stdlib `logging` module as the sole logging framework. There is no third-party logger library (no structlog, loguru, or similar). Each product service ships an identical `core/observability.py` that provides two functions:

- `configure_logging()` — raises the root logger level from uvicorn's default `WARNING` to `INFO` so structured audit records are not silently dropped; the effective level is read from the `LOG_LEVEL` environment variable.
- `log_event(logger, event, **fields)` — emits a single-line JSON record via `logger.info(json.dumps({"event": event, **fields}, default=str, sort_keys=True))`. The `event` field names the business action (e.g. `http_request`, `tool_invoked`, `auth_login_started`, `policy_decision`) and every additional keyword becomes a top-level JSON key.

All services call `configure_logging()` at application startup (in their `app.py`).

An opt-in OpenTelemetry push pipeline (`core/telemetry.py`) bridges the same root logger to OTLP logs when `OTEL_ENABLED=true`. It attaches an OTel `LoggingHandler` to the root logger so every `log_event(...)` record is mirrored over OTLP HTTP/protobuf to the configured backend (OpenObserve) while stdout JSON remains the source of truth for container logs and audit tooling. The bridge is guarded by a recursion guard that detaches `opentelemetry` loggers from the root logger.

## Key files and packages

- Per-service `core/observability.py` — defines `configure_logging()` and `log_event()`. Found under every product: `agent-platform`, `platform-gateway`, `audit-service`, `identity-broker`, `incident-service`, `skills-hub`, `tool-gateway`.
- Per-service `core/telemetry.py` — implements the opt-in OTel push pipeline (`setup_telemetry`, `_attach_log_bridge`, `current_trace_id`, `is_enabled`). Identical across all services.
- Per-service `core/request_context.py` — resolves `x-request-id` per SPEC-005 R-4: inbound header wins, otherwise bridges to the active OTel trace id, otherwise falls back to `req-<uuid4>`.
- `shared/shared-contracts/observability-conventions.md` — the authoritative specification documenting the two-surface model (Prometheus `/metrics` pull + OTel push), structured logging levels, correlation rules, and cardinality constraints.

## Architecture and conventions

1. **Single sink, dual export.** Structured logs go to stdout as one JSON line per record. When OTel is enabled, the same records are also exported via OTLP so they can be correlated with traces using the active span's `trace_id`/`span_id`.
2. **Audit trail = INFO-level structured events.** Business and request events (HTTP requests, tool invocations, policy decisions, auth flows) are emitted at `INFO` via `log_event(...)`. Services explicitly raise the root logger from uvicorn's `WARNING` default because those records form the audit trail.
3. **Level control via `LOG_LEVEL`.** Default is `INFO`; deployments may override it per deployment through the environment variable.
4. **Request correlation.** Every structured log includes a `request_id` resolved by `resolve_request_id`: inbound `x-request-id` header wins, then the active OTel trace id (when tracing is on), then a generated `req-<uuid4>`. This value joins logs and APM traces.
5. **Fail-open OTel bridge.** If `OTEL_ENABLED` is false (default), no OTel providers are initialized and there is zero overhead. If initialization fails, errors are logged and the service continues without push.
6. **No unbounded label leakage into logs.** The observability conventions forbid high-cardinality values in metrics labels; structured log fields follow the same principle — only bounded, stable keys are attached to `log_event` calls.
7. **Consistent event taxonomy.** Call sites use descriptive string event names such as `http_request`, `tool_invoked`, `policy_decision`, `auth_login_url_requested`, `auth_login_started`, `auth_logout_requested`, `identity_normalized`, `session_created`, `chat_request_received`, `webhook_received`, `retention_cleanup_completed`, etc., making logs queryable by event type.

## Conventions and constraints

- **Every service must call `configure_logging()` at app startup** so audit records are not filtered by uvicorn's default WARNING threshold. (Enforced by the shared convention doc and present in every product's `app.py`.)
- **Business and request events must be emitted via `log_event(logger, "<event_name>", ...)` at INFO level**, never via raw `logger.info("...")` string formatting. (Observed consistently across all route handlers and services.)
- **OTel push is gated exclusively by `OTEL_ENABLED`**; there are no per-signal toggles for traces/metrics/logs. (Documented in `observability-conventions.md` and implemented identically in every service.)
- **`x-request-id` must never be silently dropped** on inbound requests; it is resolved and forwarded on outbound calls. (SPEC-005 R-4, enforced by `request_context.resolve_request_id`.)
- **Trace/span association is automatic** when tracing is active — logs emitted inside an active span carry its W3C `trace_id`/`span_id`, joining the log mirror to the trace view. (Guaranteed by the OTel `LoggingHandler` attachment in `_attach_log_bridge`.)
- **JSON stdout remains the source of truth**; the OTLP mirror is secondary and must not replace container log consumers. (Explicitly stated in both `telemetry.py` docstrings and the conventions doc.)
- **Cardinality rule:** do not attach unbounded values (raw URLs, user ids, session ids, request ids) as metric labels; structured log fields should follow the same bounded-key discipline. (From `observability-conventions.md` cardinality rules.)