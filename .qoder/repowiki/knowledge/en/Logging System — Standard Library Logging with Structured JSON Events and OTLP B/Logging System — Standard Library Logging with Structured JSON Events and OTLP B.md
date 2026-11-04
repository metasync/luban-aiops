---
kind: logging_system
name: Logging System — Standard Library Logging with Structured JSON Events and OTLP Bridge
category: logging_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/agent-platform/src/agent_service/app.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
---

## What system/approach is used

The platform uses Python's standard-library `logging` module as the sole logging framework. There is no third-party logger (no structlog, loguru, or similar). Each service initializes its own root logger via a shared `core/observability.py` helper that calls `logging.basicConfig(level=..., force=True)`. Structured events are emitted as JSON strings through a thin `log_event()` wrapper that serializes a dict of fields with `json.dumps(..., sort_keys=True)`.

OpenTelemetry is wired in as an **opt-in** bridge (`OTEL_ENABLED`) that attaches an `opentelemetry.instrumentation.logging.handler.LoggingHandler` to the root logger, forwarding INFO+ records over OTLP HTTP/protobuf to `OTEL_EXPORTER_OTLP_ENDPOINT`. The bridge is fail-open: setup errors are logged and swallowed so the request path never fails because telemetry is down.

## Key files and packages

- `products/*/src/<service>/core/observability.py` — per-service `configure_logging()` / `log_event()` (agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway).
- `products/agent-platform/src/agent_service/core/telemetry.py` — OpenTelemetry push pipeline (traces + metrics + logs), `setup_telemetry()`, `MetricsMirror`, `current_trace_id()`.
- `products/agent-platform/src/agent_service/app.py` — FastAPI app factory; calls `configure_logging()` at startup, installs an HTTP middleware that emits `http_request` events via `log_event()`.
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — runtime env for each service (where `LOG_LEVEL`, `OTEL_*` vars are set in overlays).

## Architecture and conventions

1. **Per-service initialization.** Every product has its own `core/observability.py` exposing `configure_logging()` and `log_event(logger, event, **fields)`. The function reads `LOG_LEVEL` from the environment (default `INFO`, upper-cased, falls back to `logging.INFO` on unknown names) and applies it to the root logger with `force=True` to override Uvicorn's default WARNING level.
2. **Structured event format.** `log_event()` builds `{"event": <name>, ...fields}` and emits it at INFO level as a single JSON string. Call sites pass domain-specific key/value pairs (e.g. `service`, `request_id`, `method`, `path`, `status_code`, `duration_ms`).
3. **Logger instance convention.** Modules create a module-level `LOGGER = logging.getLogger(__name__)` and use `LOGGER.info/warning/error/exception(...)`. Business-path structured events go through `log_event`; operational messages use the logger directly.
4. **HTTP request tracing.** The agent-platform FastAPI app installs an `http` middleware that resolves `x-request-id`, measures duration, and emits a `http_request` event via `log_event`, attaching `service`, `request_id`, `method`, `path`, `status_code`, `duration_ms`.
5. **OTel bridge.** When `OTEL_ENABLED` is truthy (`1|true|yes|on`), `setup_telemetry()` creates TracerProvider, MeterProvider, and a LoggerProvider backed by `BatchLogRecordProcessor(OTLPLogExporter())`. It sets `OTEL_SERVICE_NAME` from env (falling back to the passed `service_name`), instruments FastAPI and HTTPX, and attaches the `LoggingHandler` to the root logger. `opentelemetry`'s own logger is detached (`propagate = False`) to prevent recursion.
6. **Fail-open design.** Both the OTel setup and the `MetricsMirror` wrap their initialization and record calls in try/except blocks that log via `LOGGER.exception(...)` and continue without raising. This ensures telemetry/logging failures cannot take down the service.
7. **Prometheus + OTel dual surface.** Domain metrics are recorded against prometheus `Counter`/`Histogram`/`Gauge` objects and additionally mirrored into OTel instruments via `MetricsMirror` when enabled, keeping the `/metrics` scrape endpoint as the source of truth while also pushing to dashboards over OTLP.

## Conventions and constraints

- **Level control:** Log level is configured exclusively through the `LOG_LEVEL` environment variable (default `INFO`); there is no programmatic per-module level tuning.
- **Structured event schema:** All structured audit/log events go through `log_event()` and must include an `event` field plus domain-relevant key/value pairs; they are serialized as sorted-key JSON strings.
- **Service identity:** The `service` field is consistently set to the service name (e.g. `"agent-service"`) in HTTP request events.
- **Trace correlation:** When OTel is enabled, trace/span IDs are attached automatically by the OTLP log exporter; `current_trace_id()` exposes the active W3C trace id for callers that need it.
- **Opt-in telemetry:** The OTLP push pipeline is disabled by default (`OTEL_ENABLED=false`); disabling it leaves stdout/stderr logging untouched and does not affect the prometheus `/metrics` endpoint.
- **Excluded URLs:** FastAPI instrumentation respects `OTEL_PYTHON_FASTAPI_EXCLUDED_URLS` / `OTEL_PYTHON_EXCLUDED_URLS`; the caller can append additional exclusions (e.g. secret routes) that cannot be removed via environment.
- **Uniformity across services:** The `core/observability.py` pattern is replicated verbatim across all eight Python services, ensuring identical logging initialization and behavior.