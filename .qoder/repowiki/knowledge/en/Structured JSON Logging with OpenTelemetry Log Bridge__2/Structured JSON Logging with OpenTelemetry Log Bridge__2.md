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
    - products/platform-gateway/src/platform_gateway/app.py
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/agent-platform/src/agent_service/app.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/audit-service/src/audit_service/core/telemetry.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
---

## What system/approach is used

The platform uses Python's standard `logging` module as the sole logging framework. Every service emits **single-line JSON** structured logs via a shared `log_event(logger, event, **fields)` helper that serializes an `event` name plus arbitrary fields into a JSON string at `INFO` level. There is no third-party logger (no structlog, loguru, or similar). The root logger is configured at process startup to raise uvicorn's default WARNING threshold up to INFO so audit records are never silently dropped.

An opt-in OpenTelemetry push pipeline mirrors every structured log record to an OTLP HTTP backend (OpenObserve) through `opentelemetry.instrumentation.logging.LoggingHandler`. This bridge is gated by `OTEL_ENABLED`; when disabled, services emit only stdout JSON with zero overhead.

## Key files and packages

- Per-service `core/observability.py` — defines `configure_logging()` and `log_event()`. Identical across all services:
  - `products/agent-platform/src/agent_service/core/observability.py`
  - `products/audit-service/src/audit_service/core/observability.py`
  - `products/identity-broker/src/identity_service/core/observability.py`
  - `products/incident-service/src/incident_service/core/observability.py`
  - `products/platform-gateway/src/platform_gateway/core/observability.py`
  - `products/skills-hub/src/skills_hub/core/observability.py`
  - `products/tool-gateway/src/tool_gateway/core/observability.py`
- Per-service `core/telemetry.py` — initializes traces/metrics/logs push via OTLP (`setup_telemetry`, `_attach_log_bridge`).
- Shared contract: `shared/shared-contracts/observability-conventions.md` — documents the two-surface model, field conventions, cardinality rules, and OTel switch semantics.
- Service app entrypoints call `configure_logging()` before creating the FastAPI app (e.g. `platform_gateway/app.py`, `agent_service/app.py`, `audit_service/app.py`, etc.).

## Architecture and conventions

### Two decoupled surfaces
1. **stdout JSON lines** — the source of truth for the audit trail. Produced by `log_event(...)` which calls `logger.info(json.dumps({"event": ..., **fields}, default=str, sort_keys=True))`.
2. **OTLP push mirror** — attached only when `OTEL_ENABLED=true`. A single `LoggingHandler` is added to the root logger; it copies each record to the OTLP log exporter while stdout remains primary. Exporter failures cannot recurse back because `logging.getLogger("opentelemetry").propagate = False`.

### Startup sequence (per service)
1. `create_app()` calls `configure_logging()` → reads `LOG_LEVEL` env var (default `INFO`) and runs `logging.basicConfig(level=..., force=True)`.
2. FastAPI app is created.
3. An HTTP middleware logs every request/response via `log_event(LOGGER, "http_request", ...)` including `service`, `request_id`, `method`, `path`, `status_code`, `duration_ms`.
4. `setup_metrics(app)` registers Prometheus `/metrics`.
5. `setup_telemetry(app, SERVICE_NAME)` optionally wires traces + metrics + log bridge.

### Structured fields
Business events are emitted as `{"event": <name>, ...}` where the first key is always `event` followed by domain-specific fields. Examples observed in the codebase include `http_request`, `tool_invoked`, `policy_decision`, `auth_login_started`, `auth_logout_requested`, `identity_normalized`, `ingest_success`, `query_success`, `webhook_received`, `retention_cleanup`, `session_created`, `chat_request`, etc. Fields are passed as keyword arguments and serialized with `default=str` to keep everything JSON-safe.

### Request correlation
- `x-request-id` is the log- and portal-facing correlation key, resolved via `resolve_request_id()` (preserving inbound value or generating `req-<uuid4>`).
- When tracing is active, `x-request-id` is set to the active span's W3C `trace_id` so a single value joins structured logs and APM traces.
- `traceparent` (W3C Trace Context) is propagated automatically by OpenTelemetry instrumentation across service hops.

### Configuration
| Variable | Purpose | Default |
|---|---|---|
| `LOG_LEVEL` | Root logger level for stdout JSON audit trail | `INFO` |
| `OTEL_ENABLED` | Master gate for OTLP push (traces + metrics + log mirror) | `false` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP HTTP base URL (exporters append `/v1/{signal}`) | — |
| `OTEL_EXPORTER_OTLP_HEADERS` | Authentication headers for the OTLP backend | — |
| `OTEL_SERVICE_NAME` | Resource service name on exported signals | service metadata name |

### Cardinality and level rules
- All business/request events use `INFO` level via `log_event`; there is no per-event level customization.
- Labels must be bounded enums (documented in observability conventions); unbounded values like raw URLs, user IDs, session IDs, and request IDs are forbidden as metric labels.
- Fail-open: telemetry setup errors are logged but never raised into the request path.

## Conventions and constraints

- **Every service must call `configure_logging()` at app startup.** This is enforced by the identical `create_app()` pattern in each product's `app.py` and documented in the per-service `observability.py` docstrings.
- **All audit-relevant events go through `log_event(...)`, not direct `logger.info(...)` calls.** This ensures consistent JSON shape and INFO-level emission.
- **Audit records must never be discarded.** The root logger is explicitly raised from uvicorn's WARNING default to INFO; tests assert this behavior (e.g. `test_observability.py` checks `logging.getLogger().level == logging.INFO`).
- **OTLP is opt-in and fail-open.** `OTEL_ENABLED=false` leaves stdout-only logging fully functional; initialization exceptions are caught and logged rather than raised.
- **No per-signal OTel toggles.** One switch (`OTEL_ENABLED`) gates traces, metrics, and the log bridge together.
- **JSON stdout stays the source of truth.** The OTLP mirror exists solely for trace correlation; consumers must read stdout, not the OTLP stream.
- **Service names follow `<service>_...` metric prefix convention** (e.g. `gateway`, `identity`, `agent`, `audit`, `incident`, `skills`, `tool`) as defined in `observability-conventions.md`.