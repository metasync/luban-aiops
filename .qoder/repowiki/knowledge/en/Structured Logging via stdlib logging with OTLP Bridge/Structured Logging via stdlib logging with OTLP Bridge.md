---
kind: logging_system
name: Structured Logging via stdlib logging with OTLP Bridge
category: logging_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
---

## Approach

Every product service in the workspace uses Python's built-in `logging` module — no third-party logger framework (no structlog, loguru, or logbook). Each service ships an identical `core/observability.py` that exposes two helpers:

- `configure_logging()` — raises the root logger from Uvicorn's default `WARNING` to `INFO` so structured audit events are not silently dropped. The effective level is read from the `LOG_LEVEL` environment variable (default `INFO`, upper-cased, falling back to `logging.INFO`).
- `log_event(logger, event, **fields)` — serializes `{"event": <name>, ...fields}` as a single JSON line via `json.dumps(..., default=str, sort_keys=True)` and emits it at `logger.info`. This is the canonical way to emit domain events across all services.

The pattern is replicated verbatim in every product:

| Service | File |
|---|---|
| agent-platform | `products/agent-platform/src/agent_service/core/observability.py` |
| audit-service | `products/audit-service/src/audit_service/core/observability.py` |
| execution-runtime | `products/execution-runtime/src/execution_runtime/core/observability.py` |
| identity-broker | `products/identity-broker/src/identity_service/core/observability.py` |
| incident-service | `products/incident-service/src/incident_service/core/observability.py` |
| platform-gateway | `products/platform-gateway/src/platform_gateway/core/observability.py` |
| skills-hub | `products/skills-hub/src/skills_hub/core/observability.py` |
| tool-gateway | `products/tool-gateway/src/tool_gateway/core/observability.py` |

Each service's `app.py` calls `configure_logging()` early during startup and then imports its own `LOGGER = logging.getLogger(__name__)` alongside business modules that call `log_event(LOGGER, "...", ...)`. There is no shared SDK for this; each product owns its own copy of the helper.

## Sinks

There is no custom handler attached by `configure_logging`; output goes to the standard root logger sink (stderr/stdout), producing one JSON object per line. No file sinks, no syslog, no separate debug/info/error streams are configured.

## OpenTelemetry bridge (opt-in)

Only `agent-platform` (`products/agent-platform/src/agent_service/core/telemetry.py`) installs an optional OpenTelemetry push pipeline gated by `OTEL_ENABLED` (truthy values: `1`, `true`, `yes`, `on`). When enabled it:

1. Sets up OTLP HTTP exporters for traces, metrics, and logs against `OTEL_EXPORTER_OTLP_ENDPOINT`.
2. Attaches `opentelemetry.instrumentation.logging.handler.LoggingHandler` to the root logger so every `logger.info` JSON line is also forwarded to the OTLP log exporter.
3. Detaches OTel's internal loggers (`logging.getLogger("opentelemetry").propagate = False`) to prevent recursion.
4. Instruments FastAPI and HTTPX clients automatically.
5. Is fail-open: setup exceptions are logged and swallowed; they never propagate into the request path.

The bridge comment states that stdout JSON lines remain the source of truth for the audit trail and the OTLP bridge is only for correlation with traces (trace/span ids attach automatically when a span is active).

## Structured fields convention

`log_event` enforces a flat payload shape: the first positional argument is the event name string, and all remaining keyword arguments become top-level fields on the JSON object. Field values are coerced to strings via `default=str`. Event names observed across the codebase follow a `<domain>_<action>` snake_case convention, e.g. `auth_login_url_requested`, `auth_login_started`, `auth_logout_requested`, `http_request`, `tool_invoked`, `policy_decision`, `otel telemetry enabled`.

## Level strategy

- Default: `INFO` (set explicitly because Uvicorn starts at `WARNING`).
- Override: `LOG_LEVEL` environment variable, any value accepted by `getattr(logging, ...)`, e.g. `DEBUG`, `WARNING`, `ERROR`.
- Tests assert that setting `LOG_LEVEL=WARNING` suppresses INFO-level `log_event` records (see `test_observability.py` in multiple products).

## Enforcement sources

- Every product's `app.py` calls `configure_logging()` near process start (verified by grep across all eight services).
- Unit tests in each product contain a `test_log_level_env_overrides` test that patches `os.environ["LOG_LEVEL"]` and asserts `configure_logging()` applies the new level.
- The `log_event` helper is the only place where structured audit events are emitted; direct `logger.info(json.dumps(...))` calls outside this helper are absent from the production code paths found by the search.
- The OTLP bridge is opt-in and guarded by `OTEL_ENABLED`; when disabled, `setup_telemetry` returns immediately and no OTel providers are initialized.

## Not present

- No structured-logging framework (structlog/loguru) is used.
- No per-sink routing rules (e.g. ERROR to a separate stream).
- No redaction/masking logic inside the logging layer itself.
- No centralized log aggregation configuration in the repo (the OTLP endpoint is supplied via environment variables provisioned at runtime).
- Only `agent-platform` has the OTLP bridge; the other seven services do not install the OTel logging handler.