---
kind: logging_system
name: Standard Library Logging with Structured JSON Events
category: logging_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/app.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
---

## Approach

The Luban platform uses Python's standard-library `logging` module exclusively — no third-party logging frameworks (structlog, loguru, etc.) are imported. Each product service ships its own tiny `core/observability.py` that configures the root logger and exposes a shared `log_event()` helper for structured event emission.

## Per-service initialization

Every FastAPI-based product (`agent-platform`, `audit-service`, `execution-runtime`, `identity-broker`, `incident-service`, `platform-gateway`, `skills-hub`, `tool-gateway`) follows the same pattern in its `app.py`:

1. Import `configure_logging, log_event` from `<service>.core.observability`.
2. Call `configure_logging()` at the top of `create_app()` before constructing the `FastAPI` instance.
3. Create a per-module logger via `LOGGER = logging.getLogger(__name__)`.
4. Emit structured events through `log_event(LOGGER, "event_name", **fields)` rather than calling `logger.info(...)` directly.

The `configure_logging()` function reads `LOG_LEVEL` from the environment (defaulting to `INFO`), converts it via `getattr(logging, level_name, logging.INFO)`, and applies it with `logging.basicConfig(level=level, force=True)`. The comment documents why this is necessary: Uvicorn starts the root logger at `WARNING`, which would silently drop every `log_event` record (http_request, toolkit registration, auth/routing events).

## Structured event format

`log_event(logger, event, **fields)` builds a dict `{"event": event, **fields}` and serializes it as a single-line JSON string via `json.dumps(payload, default=str, sort_keys=True)`. This means every structured log line is itself valid JSON with an `event` field plus arbitrary key/value pairs. There is no custom formatter; output goes to stdout/stderr using the default `logging` handler.

Observed event names include `http_request`, `auth`, `routing`, `handoff_rejection`, `toolkit_registration`, `session_start`, `skill_graduation`, `approval_decision`, `document_read`, `retention_sweep`, `export_started`, `ingest_received`, `query_executed`, `summary_generated`, among others spread across services.

## Log levels

- Default level: `INFO` (set by `LOG_LEVEL` env var default).
- Level override: `LOG_LEVEL` environment variable, uppercased and resolved against `logging` constants.
- Tests explicitly verify the override path (e.g. `products/agent-platform/tests/test_observability.py`, `products/identity-broker/tests/test_observability.py`).
- Some modules still call `logger.debug(...)`, `logger.error(...)`, or plain `LOGGER.info("...")` for non-structured messages (e.g. model discovery startup, session transcript writes); these bypass the JSON envelope.

## Sinks and routing

There is no programmatic sink configuration beyond `basicConfig`. Logs are written to the process stdout/stderr, relying on the surrounding container/orchestration layer (Docker, Kubernetes, OpenTelemetry sidecars) to collect them. No file handlers, rotating handlers, or external log aggregators are configured inside the Python code.

## Conventions observed

- Every product has a `src/<service>/core/observability.py` with identical `configure_logging` / `log_event` signatures.
- Application entry points import and invoke `configure_logging()` before creating the `FastAPI` app.
- Business logic emits structured audit/trace events via `log_event(LOGGER, <event>, ...)` so fields like `service`, `request_id`, `method`, `path`, `status_code`, `duration_ms` are consistently attached to HTTP request logs.
- Non-structured informational/error lines use `LOGGER.info(...)` / `logger.error(...)` directly.
- The `LOG_LEVEL` environment variable is the only runtime knob for verbosity.

## Rules enforced by the code

- The root logger level is always set via `logging.basicConfig(force=True)` in each service's `configure_logging()`, overriding whatever Uvicorn sets.
- `LOG_LEVEL` values not recognized by `logging` fall back to `logging.INFO` (the `getattr(..., logging.INFO)` default).
- All structured events go through `log_event`, which forces `logger.info` and JSON serialization with sorted keys — callers cannot accidentally emit unstructured JSON through that helper.