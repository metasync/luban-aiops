---
kind: logging_system
name: Per-Service Python stdlib logging with structured JSON events
category: logging_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/app.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/audit-service/src/audit_service/app.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/execution-runtime/src/execution_runtime/app.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/identity-broker/src/identity_service/app.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/incident-service/src/incident_service/app.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/skills-hub/src/skills_hub/app.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/tool-gateway/src/tool_gateway/app.py
---

## Approach

Every product service in `products/` implements its own logging setup using Python's standard library `logging` module — there is no shared logging framework, no third-party logger (no loguru/structlog/sentry), and no centralized logging package under `shared/`. Each service owns a small `core/observability.py` that both configures the root logger and exposes a helper for emitting structured audit events.

## Per-service observability module

Each service ships an identical-looking `core/observability.py`:

- `configure_logging()` reads `LOG_LEVEL` from the environment (defaulting to `"INFO"`, uppercased) and calls `logging.basicConfig(level=level, force=True)` on the root logger. The docstring explains the motivation: Uvicorn starts the root logger at `WARNING`, which would silently drop every `log_event` record (the audit trail).
- `log_event(logger, event, **fields)` builds a dict `{"event": event, **fields}`, serializes it with `json.dumps(..., default=str, sort_keys=True)`, and emits it at `logger.info` level.

The file exists in every product:

- `products/agent-platform/src/agent_service/core/observability.py`
- `products/audit-service/src/audit_service/core/observability.py`
- `products/execution-runtime/src/execution_runtime/core/observability.py`
- `products/identity-broker/src/identity_service/core/observability.py`
- `products/incident-service/src/incident_service/core/observability.py`
- `products/platform-gateway/src/platform_gateway/core/observability.py`
- `products/skills-hub/src/skills_hub/core/observability.py`
- `products/tool-gateway/src/tool_gateway/core/observability.py`

## Initialization pattern

Each service's entrypoint (`app.py`) imports `configure_logging` from its local `core.observability` and calls it early during startup:

- `products/agent-platform/src/agent_service/app.py` line 50
- `products/audit-service/src/audit_service/app.py` line 44
- `products/execution-runtime/src/execution_runtime/app.py` line 78
- `products/identity-broker/src/identity_service/app.py` line 17
- `products/incident-service/src/incident_service/app.py` line 43
- `products/platform-gateway/src/platform_gateway/app.py` line 17
- `products/skills-hub/src/skills_hub/app.py` line 60
- `products/tool-gateway/src/tool_gateway/app.py` line 171

## Logger instance convention

Modules obtain a per-module logger via the idiom `LOGGER = logging.getLogger(__name__)` at module scope (observed across dozens of files in `agent-platform/services/*`, `agent-platform/tools/*`, etc.). Structured events are then emitted through the shared `log_event(LOGGER, "...", ...)` helper rather than calling `LOGGER.info(...)` directly.

## Event shape

Structured audit events are single-line JSON strings with a fixed top-level key:

```
{"event": "<event_name>", <additional_fields...>}
```

Fields are serialized with `default=str` (so non-serializable objects become their string representation) and keys are sorted for deterministic output. Examples observed in the codebase include `http_request`, `auth_login_url_requested`, `auth_login_started`, `auth_logout_requested`, `auth_token_exchanged`, `identity_normalized`, `retention_cleanup_completed`, and others passed as keyword arguments to `log_event`.

## Log levels

- Default root level: `INFO` (via `LOG_LEVEL="INFO"`).
- Override: set the `LOG_LEVEL` environment variable to any name recognized by `logging` (e.g. `DEBUG`, `WARNING`, `ERROR`).
- Tests explicitly verify this override path: each service has a `tests/test_observability.py` that patches `os.environ["LOG_LEVEL"]` to `"WARNING"`, calls `configure_logging()`, and asserts that INFO-level records are dropped while WARNING+ records pass through.

## Sinks

No custom handlers or sinks are attached by `configure_logging`; output goes to the default `logging.StreamHandler` (stderr). There is no file rotation, no syslog handler, no OTLP/log exporter wired into the logging layer itself. Observability metrics/traces are handled separately (OpenTelemetry via `opentelemetry.*` packages, not the `logging` subsystem).

## Conventions and constraints

- Every product service must define its own `core/observability.py` exposing `configure_logging` and `log_event` — the pattern is replicated verbatim across all eight services rather than being factored into a shared package.
- Application startup must call `configure_logging()` before any business logic runs so the root logger level is raised above Uvicorn's default `WARNING`.
- Structured audit events should be emitted via `log_event(LOGGER, "<event_name>", **fields)`; raw `LOGGER.info(...)` is used only for non-audit messages.
- The `LOG_LEVEL` environment variable is the sole mechanism for changing verbosity at runtime; tests assert that unrecognized values fall back to `logging.INFO` via `getattr(logging, level_name, logging.INFO)`.
- No cross-service log correlation header or context propagation is implemented in the logging layer — correlation IDs (e.g. `request_id`) are carried manually as fields where needed.