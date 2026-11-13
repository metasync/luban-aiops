---
kind: logging_system
name: Standard Library Logging with Structured JSON Events and OTLP Bridge
category: logging_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - shared/shared-contracts/observability-conventions.md
---

## Approach

The platform uses Python's standard library `logging` module as its sole logging framework — no third-party logger (loguru, structlog, logbook) is imported anywhere in production code. Each product ships an identical `core/observability.py` that exposes two entry points: `configure_logging()` and `log_event(logger, event, **fields)`.

Structured events are emitted as a single JSON string via `json.dumps(payload, default=str, sort_keys=True)` at INFO level; the payload always carries an `event` key plus arbitrary domain fields. This makes stdout the canonical audit trail (machine-parsable JSON lines), while OpenTelemetry's `LoggingHandler` bridges the same root-logger records into the OTLP log pipeline when `OTEL_ENABLED=true`, automatically attaching trace/span context.

## Key files

- `products/*/src/*/core/observability.py` — per-product copy of `configure_logging()` / `log_event()`
- `products/agent-platform/src/agent_service/core/telemetry.py` — OTel push setup, log bridge attachment, `current_trace_id()`, `MetricsMirror`
- `shared/shared-contracts/observability-conventions.md` — documented naming/field conventions for OTel and logs
- Per-product `app.py` / `main.py` / `native.py` — call sites for `configure_logging()` and `setup_telemetry()`

## Architecture and conventions

### Initialization

Every service calls `configure_logging()` early in startup. It reads `LOG_LEVEL` from the environment (defaulting to `INFO`), converts it via `getattr(logging, level_name, logging.INFO)`, then calls `logging.basicConfig(level=level, force=True)` on the root logger. The docstring documents why this is needed: Uvicorn starts the root logger at WARNING, which would silently drop every `log_event` record (http_request, toolkit registration, audit trail).

### Structured event format

`log_event(logger, event, **fields)` builds `{"event": event, ...fields}` and emits it at INFO. Callers pass domain-specific keyword arguments (`request_id`, `user_id`, `session_id`, etc.) rather than positional args. The identity-broker and platform-gateway both emit auth/session events like `auth_login_url_requested`, `auth_login_started`, `identity_normalized`; the agent-platform emits toolkit-registration and http-request events.

### Log levels

- Default: `INFO` (set by `LOG_LEVEL` or fallback)
- Uvicorn's built-in root logger defaults to WARNING, hence the explicit override
- Tests in `identity-broker/tests/test_observability.py` and `tool-gateway/tests/test_observability.py` verify that setting `LOG_LEVEL=WARNING` suppresses INFO events
- No custom log levels or formatters are defined — all output goes through the root handler

### Sinks

1. **stdout** — primary sink via `basicConfig`. JSON lines are the source of truth for the audit trail.
2. **OTLP (optional)** — when `OTEL_ENABLED` is true, `setup_telemetry()` attaches an `opentelemetry.instrumentation.logging.LoggingHandler` to the root logger, forwarding INFO+ records to the configured `OTEL_EXPORTER_OTLP_ENDPOINT`. The OTel internal loggers (`logging.getLogger("opentelemetry")`) have propagation disabled so exporter failures cannot recurse back into the bridge. Failures are logged via `LOGGER.exception(...)` and swallowed — fail-open behavior.
3. **No file/console/file-rotating sinks** — no custom handlers beyond the stdlib StreamHandler installed by `basicConfig`.

### Cross-cutting telemetry integration

`telemetry.py` (agent-platform, mirrored in other services) provides:
- `is_enabled()` — checks `OTEL_ENABLED`
- `setup_telemetry(app, service_name, excluded_urls=())` — installs TracerProvider, MeterProvider, FastAPI/HTTPX instrumentors, and the log bridge
- `current_trace_id()` — returns the active W3C trace_id if tracing is active
- `MetricsMirror` — re-emits prometheus domain families as OTel instruments (SPEC-065 R-2), lazy-built and fail-open

The bridge comment states: "The JSON lines on stdout remain the source of truth for the audit trail; this bridge ships the same records over OTLP so the backend can correlate them with traces."

### Environment variables

| Variable | Purpose |
|---|---|
| `LOG_LEVEL` | Root logger level (default `INFO`) |
| `OTEL_ENABLED` | Enables OTel push pipeline (gated, default false) |
| `OTEL_SERVICE_NAME` | Service name label on OTel resources |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP HTTP endpoint |
| `OTEL_EXPORTER_OTLP_HEADERS` | Authentication headers for the OTLP endpoint |
| `OTEL_PYTHON_FASTAPI_EXCLUDED_URLS` / `OTEL_PYTHON_EXCLUDED_URLS` | Routes excluded from tracing |

## Conventions and constraints

- **Convention**: Every product defines its own `core/observability.py` with the same `configure_logging()` + `log_event()` pair (observed in agent-platform, audit-service, execution-runtime, identity-broker, platform-gateway, tool-gateway). The pattern is replicated rather than centralized.
- **Convention**: Structured events use the `event` field as the discriminator and attach contextual fields as kwargs (`request_id`, `user_id`, `session_id`, `service_name`).
- **Convention**: All structured audit events are emitted at INFO level via `log_event`; ad-hoc debug/info/error messages use `LOGGER.info/debug/error` directly.
- **Rule (enforced by code)**: `configure_logging()` must be called before any `log_event` emission because it sets the root logger level; without it, Uvicorn's WARNING default drops INFO records (documented in the function's docstring).
- **Rule (enforced by code)**: OTel initialization is gated by `OTEL_ENABLED`; when disabled, `setup_telemetry()` returns immediately and `/metrics` is unaffected (SPEC-005 always-on guarantee).
- **Rule (enforced by code)**: OTel setup errors are caught and logged via `LOGGER.exception(...)`, never raised into the request path — fail-open semantics.
- **Rule (enforced by tests)**: `LOG_LEVEL=WARNING` suppresses INFO events — verified in `identity-broker/tests/test_observability.py` and `tool-gateway/tests/test_observability.py`.
- **Constraint**: No third-party logging libraries are used; only `logging` from the stdlib plus `opentelemetry.instrumentation.logging.LoggingHandler` for the optional bridge.