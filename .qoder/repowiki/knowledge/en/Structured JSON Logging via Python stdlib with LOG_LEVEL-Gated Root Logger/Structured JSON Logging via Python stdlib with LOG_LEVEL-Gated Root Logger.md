---
kind: logging_system
name: Structured JSON Logging via Python stdlib with LOG_LEVEL-Gated Root Logger
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/agent-platform/src/agent_service/app.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/audit-service/src/audit_service/app.py
    - products/identity-broker/src/identity_service/app.py
    - products/tool-gateway/src/tool_gateway/app.py
    - products/agent-platform/src/agent_service/core/request_context.py
---

## What system/approach is used

Every FastAPI service in the platform (agent-platform, platform-gateway, identity-broker, audit-service, tool-gateway) uses **Python's built-in `logging` module** — no third-party logging framework. Structured logs are emitted as single-line JSON payloads through a shared helper `log_event(logger, event, **fields)` that serializes `{"event": ..., ...fields}` with `json.dumps(..., default=str, sort_keys=True)` and writes them at `INFO` level.

The root logger is intentionally raised from Uvicorn's default `WARNING` to `INFO` at application startup so that these structured records (the audit trail) are not silently discarded. The effective log level is read from the `LOG_LEVEL` environment variable per deployment; the documented default must remain `INFO`.

## Key files and packages

- Per-service initialization: `products/*/src/*/app.py` — each calls `configure_logging()` before creating the `FastAPI` app and installs an HTTP middleware that emits an `http_request` event via `log_event`.
- Per-service observability helpers: `products/*/src/*/core/observability.py` — identical implementations of `configure_logging()` and `log_event()` across all five services.
- Request correlation: `products/*/src/*/core/request_context.py` (and `identity_service/core/telemetry.py`) resolve the `x-request-id` header by bridging to the active OpenTelemetry `trace_id` when tracing is enabled, otherwise generating `req-<uuid4>`.
- Platform-wide convention doc: `shared/shared-contracts/observability-conventions.md` — codifies the structured logging strategy, level policy, and request-correlation rules.

## Architecture and conventions

1. **Single entry point per service.** Each `create_app()` function calls `configure_logging()` first, then attaches an `@app.middleware("http")` handler that wraps every request, measures `duration_ms`, resolves `request_id`, and emits one `http_request` structured log line.
2. **Uniform structured schema.** All business events go through `log_event(logger, "<event_name>", field=value, ...)`. The resulting JSON always contains an `event` key plus whatever fields the caller supplies; values are coerced to strings via `default=str` and keys are sorted for deterministic output.
3. **Level control via env var.** `LOG_LEVEL` is read at startup (`os.environ.get("LOG_LEVEL", "INFO").upper()`) and applied via `logging.basicConfig(level=..., force=True)`. This lets operators tune verbosity per deployment without code changes.
4. **Request correlation bridge.** `x-request-id` is the log- and portal-facing correlation key. When OpenTelemetry tracing is active, it is set to the active span's W3C `trace_id`; when inactive it falls back to `req-<uuid4>`. No service may silently drop an inbound correlation id.
5. **Audit-trail intent.** The comments in every `configure_logging()` explicitly state that INFO-level structured records form the audit trail (e.g. `http_request`, `tool_invoked`, `policy decisions`, `auth_login_started`). Raising the root logger from WARNING to INFO is therefore a correctness requirement, not just a convenience.
6. **Decoupled from metrics/tracing.** Structured logging is independent of the `/metrics` Prometheus endpoint and the opt-in OpenTelemetry push surface described in the same conventions doc.

## Conventions and constraints

- **Emit structured logs only through `log_event`** — ad-hoc `logger.info("...", extra={...})` is avoided for domain events; the convention document mandates single-line JSON via `log_event(...)` at INFO level.
- **Default log level is INFO** — the conventions doc states the default must stay INFO so audit records are never silently discarded; tests in `agent_platform/tests/test_observability.py` verify this behavior.
- **No unbounded label leakage into logs** — while cardinality rules are stated for metrics labels, the same principle applies to structured fields: avoid high-cardinality values like raw URLs, user ids, session ids, or request ids as free-form fields unless they serve correlation.
- **Correlation headers must be preserved** — `x-request-id` is generated if absent (preserving the portal contract) and forwarded on every outbound call; `traceparent` (W3C Trace Context) is handled automatically by OTel instrumentation across hops.
- **Fail-open telemetry** — OTel push is gated by `OTEL_ENABLED` and must never break a request; logging itself remains unaffected by OTel configuration.