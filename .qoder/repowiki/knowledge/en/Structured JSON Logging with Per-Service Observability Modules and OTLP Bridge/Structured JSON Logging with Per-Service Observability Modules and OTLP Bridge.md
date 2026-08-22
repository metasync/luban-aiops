---
kind: logging_system
name: Structured JSON Logging with Per-Service Observability Modules and OTLP Bridge
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/agent-platform/src/agent_service/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/audit-service/src/audit_service/app.py
    - products/agent-platform/src/agent_service/app.py
    - products/platform-gateway/src/platform_gateway/core/request_context.py
    - products/tool-gateway/src/tool_gateway/services/audit_emitter.py
---

## What system/approach is used

The platform uses Python's stdlib `logging` module exclusively — no third-party logging frameworks (no structlog, loguru, or similar). Each service ships a tiny, self-contained `core/observability.py` that provides two functions:

- `configure_logging()` — raises the root logger from Uvicorn's default `WARNING` to `INFO` via `logging.basicConfig(level=..., force=True)`, reading the level from the `LOG_LEVEL` environment variable (defaulting to `INFO`).
- `log_event(logger, event, **fields)` — emits a single-line JSON record at `INFO` level: `{"event": <event_name>, ...fields}` serialized with `json.dumps(..., default=str, sort_keys=True)`.

Structured events are the audit trail. Business and request events (`http_request`, `tool_invoked`, `policy_decision`, `auth_login_started`, etc.) are emitted through this helper rather than ad-hoc `logger.info(...)` calls.

OpenTelemetry is layered on top as an opt-in mirror: when `OTEL_ENABLED=true`, each service attaches an OTel `LoggingHandler` to the root logger so every structured record is also exported as an OTLP log record over HTTP/protobuf to OpenObserve. The bridge is gated by the same switch and fails open; container stdout remains the source of truth.

## Key files and packages

Per-service observability modules (identical shape across all services):
- `products/platform-gateway/src/platform_gateway/core/observability.py`
- `products/audit-service/src/audit_service/core/observability.py`
- `products/agent-platform/src/agent_service/core/observability.py`
- `products/tool-gateway/src/tool_gateway/core/observability.py`
- `products/incident-service/src/incident_service/core/observability.py`
- `products/identity-broker/src/identity_service/core/observability.py`
- `products/skills-hub/src/skills_hub/core/observability.py`

Startup wiring in each service's `app.py` (calls `configure_logging()` before creating the FastAPI app and installs an HTTP middleware that logs every request via `log_event`).

Correlation helpers:
- `products/*/core/request_context.py` — `resolve_request_id()` bridges inbound `x-request-id`, active OTel trace ID, or a generated `req-<uuid4>` fallback.
- `products/*/core/telemetry.py` — `setup_telemetry(app, SERVICE_NAME)` initializes OTel providers and the log bridge.

Cross-cutting contract:
- `shared/shared-contracts/observability-conventions.md` — documents the conventions enforced by the code (structured INFO-level JSON, `LOG_LEVEL`, `OTEL_*` env vars, cardinality rules, correlation).

Audit emission path (fire-and-forget):
- `products/tool-gateway/src/tool_gateway/services/audit_emitter.py` — builds audit envelopes matching `shared/shared-contracts/schemas/audit-event.schema.json` and posts them to the audit service over HTTP on a daemon thread; failures are swallowed and logged via `LOGGER.warning(..., extra={...})`.

## Architecture and conventions

1. **Per-service isolation.** There is no shared logging package. Every product under `products/` defines its own `core/observability.py` with the same API. This keeps services independently deployable and testable without cross-service import coupling.

2. **Root logger configuration at startup.** `configure_logging()` is called exactly once per process during `create_app()`. It uses `logging.basicConfig(force=True)` so it overrides any prior configuration (including Uvicorn's defaults).

3. **Structured event schema.** All business events go through `log_event(logger, "<event_name>", **fields)`, producing one JSON line per event. Fields are flattened into the top-level object; there is no nested structure beyond what callers pass.

4. **Request correlation.** Every HTTP request middleware call resolves a stable `request_id` via `resolve_request_id()`, which prefers the inbound `x-request-id` header, then bridges to the active OTel `trace_id`, then falls back to `req-<uuid4>`. This value is included in every `http_request` event and forwarded on outbound calls.

5. **OTLP mirror, not replacement.** When `OTEL_ENABLED=true`, the OTel `LoggingHandler` mirrors every structured record to the configured backend. The convention explicitly states that stdout JSON is the source of truth; OTLP is for correlation with traces.

6. **Level strategy.** Default root level is `INFO` so audit records are never silently discarded. Operators can raise the level per deployment via `LOG_LEVEL` (e.g. `WARNING` to suppress audit noise). Tests verify this behavior by patching `os.environ["LOG_LEVEL"]`.

7. **Cardinality discipline.** The observability conventions forbid using unbounded values as metric labels (raw URL, user id, session id, request id). Structured log fields do not have this restriction, but the same principle applies to avoid noisy audit trails.

8. **Fire-and-forget audit emission.** Audit events are sent asynchronously on a daemon thread with a short timeout; failures are recorded via metrics and a warning log, never propagated to the caller. If `GATEWAY_AUDIT_SERVICE_URL` is unset, emission is a no-op.

## Conventions and constraints

- **Every service must call `configure_logging()` before creating the FastAPI app** — documented in each `observability.py` docstring and verified by tests that assert the root logger level after calling it.
- **Business and request events must be emitted via `log_event(...)` at INFO level** — stated in `shared/shared-contracts/observability-conventions.md` as the audit-trail surface.
- **`LOG_LEVEL` controls the root logger level** — read from the environment, uppercased, mapped via `getattr(logging, ...)`, defaulting to `INFO`.
- **`OTEL_ENABLED` gates the entire OTel pipeline** (traces, metrics, log mirror) — fail-open, zero overhead when disabled.
- **`x-request-id` is the log- and portal-facing correlation key**; `traceparent` (W3C Trace Context) is the machine-facing propagation header managed by OTel instrumentation.
- **Audit events must conform to `shared/shared-contracts/schemas/audit-event.schema.json`** — enforced by the `build_audit_event` builder which omits optional identity fields when absent.
- **No third-party logging framework is used** — the codebase relies solely on `logging` plus OTel's `LoggingHandler`; no structlog/loguru imports exist anywhere.
- **Metrics and logs are decoupled surfaces** — `/metrics` (Prometheus pull) always works; OTLP push is opt-in and independent.