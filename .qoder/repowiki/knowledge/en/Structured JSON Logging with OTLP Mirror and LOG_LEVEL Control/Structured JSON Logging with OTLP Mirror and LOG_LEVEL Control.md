---
kind: logging_system
name: Structured JSON Logging with OTLP Mirror and LOG_LEVEL Control
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/agent-platform/src/agent_service/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/agent-platform/tests/test_observability.py
---

## What system/approach is used

The platform uses Python's stdlib `logging` module exclusively — no third-party logging frameworks (no structlog, loguru, or logzero). Each service defines an identical `core/observability.py` that provides two functions:

- `configure_logging()` — raises the root logger from Uvicorn's default WARNING level to INFO via `logging.basicConfig(level=..., force=True)`, reading the effective level from the `LOG_LEVEL` environment variable (defaulting to `INFO`).
- `log_event(logger, event, **fields)` — emits a single-line JSON record at INFO level by serializing `{"event": event, ...fields}` with `json.dumps(..., default=str, sort_keys=True)`.

When OpenTelemetry push is enabled (`OTEL_ENABLED=true`), each service attaches an OTel `LoggingHandler` to the root logger so every structured record is mirrored as an OTLP log record to the configured backend (OpenObserve over HTTP/protobuf). The OTel loggers are explicitly detached from the root logger to prevent recursion when exporter failures occur.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — the authoritative spec defining the logging contract for all services (SPEC-005 observability baseline).
- Per-service `core/observability.py` (identical across all seven services): `agent-platform`, `audit-service`, `identity-broker`, `platform-gateway`, `skills-hub`, `tool-gateway`.
- Per-service `core/telemetry.py` — initializes OTel providers and bridges logs; also sets `logging.getLogger("opentelemetry").propagate = False` to break recursion loops.
- Service entrypoints call `configure_logging()` during startup (e.g. `app.py` in each product) before any request handling begins.

## Architecture and conventions

**Single source of truth: stdout.** All business and request events are emitted as one-line JSON records to stdout. The OTLP mirror is secondary — it exists only so the backend can correlate logs with traces; audit tooling must keep reading stdout.

**Event-driven structured schema.** Every log record carries an `event` field naming the semantic event (e.g. `http_request`, `auth_login_started`, `tool_invoked`, `policy_decision`, `session_created`) plus domain-specific key/value fields. Fields are passed as keyword arguments to `log_event` and serialized deterministically (`sort_keys=True`).

**Level strategy.** The root logger is raised to INFO at process start so audit records are never silently dropped by Uvicorn's default WARNING threshold. `LOG_LEVEL` overrides the per-deployment level; tests assert that setting `LOG_LEVEL=WARNING` suppresses INFO records.

**Request correlation.** `x-request-id` is the log- and portal-facing correlation key. When tracing is active, it is set to the active span's W3C `trace_id`; otherwise it falls back to `req-<uuid4>`. Structured logs emitted inside an active span automatically carry `trace_id`/`span_id` through the OTel bridge, joining them to APM traces on the same W3C id.

**Cardinality and safety rules** (from the shared convention doc):
- Never use unbounded values as labels (raw URL, user id, session id, request id).
- Domain counters use bounded enum labels only.
- OTel push fails open: missing/invalid credentials produce 401s at export time; batch processors drop telemetry on failure; initialization guards raise rather than crash the service.
- No service may silently drop an inbound correlation id.

**Cross-service propagation.** Outbound calls forward `x-request-id` and rely on OpenTelemetry instrumentation to propagate `traceparent` (W3C Trace Context) headers automatically.

## Conventions and constraints

- **Every service must call `configure_logging()` at app startup** before handling requests, so INFO-level audit records survive Uvicorn's default WARNING filter. This is enforced by the shared convention document and verified by unit tests in each service.
- **All business/request events go through `log_event(...)`**, not raw `logger.info(...)`, ensuring uniform JSON shape and deterministic key ordering.
- **Audit trail events are always INFO level.** The convention explicitly states that http_request, tool_invoked, policy decisions, and token delegation events form the audit trail and must not be downgraded.
- **OTLP log bridge is opt-in via `OTEL_ENABLED`**; when disabled, `/metrics` remains fully functional with zero overhead.
- **No third-party logging framework is permitted.** The codebase uniformly uses stdlib `logging`; no imports of structlog, loguru, or similar libraries exist.
- **Recursion guard:** `opentelemetry` loggers are excluded from the root logger to prevent exporter failures from looping back through the bridge.