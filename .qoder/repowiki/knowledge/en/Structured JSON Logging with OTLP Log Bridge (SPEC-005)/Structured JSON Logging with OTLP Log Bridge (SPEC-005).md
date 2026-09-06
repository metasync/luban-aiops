---
kind: logging_system
name: Structured JSON Logging with OTLP Log Bridge (SPEC-005)
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/platform-gateway/src/platform_gateway/core/config.py
---

## What system/approach is used

The platform uses Python's standard `logging` module as the sole logging framework. Every service emits **single-line, sorted-key JSON** records via a shared `log_event(logger, event, **fields)` helper that serializes `{"event": ..., ...fields}` at INFO level. There is no third-party logger library (no structlog, loguru, etc.).

An opt-in OpenTelemetry push pipeline mirrors every structured log record to an OTLP HTTP/protobuf backend (OpenObserve) through a `LoggingHandler` attached to the root logger. The bridge is gated by `OTEL_ENABLED`; when disabled, nothing OTel-related is initialized and there is zero overhead.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — authoritative cross-service contract defining the two observability surfaces (`/metrics` pull + OTLP push), environment variables, log levels, correlation headers, cardinality rules, and fail-open semantics.
- Per-service `core/observability.py` (identical pattern in `agent-platform`, `platform-gateway`, `audit-service`, `tool-gateway`, `identity-broker`, `execution-runtime`, `incident-service`, `skills-hub`): exposes `configure_logging()` and `log_event(logger, event, **fields)`.
- `products/*/src/*/core/telemetry.py` (present in each product) — initializes OTel TracerProvider, MeterProvider, FastAPI/HTTPX instrumentation, and attaches the OTLP log bridge via `_attach_log_bridge(resource)`.
- Each product's `app.py` / `main.py` calls `configure_logging()` early so Uvicorn's default WARNING root level does not swallow audit events.

## Architecture and conventions

1. **Root logger configuration** — `configure_logging()` reads `LOG_LEVEL` (default `INFO`) and calls `logging.basicConfig(level=..., force=True)`. This raises the root logger from Uvicorn's WARNING default so INFO-level audit records are never silently discarded.
2. **Structured event emission** — business/request events go through `log_event(LOGGER, "<event_name>", field=value, ...)`. Fields are passed as keyword arguments and merged into a dict; values are coerced to strings via `json.dumps(..., default=str)` and keys are sorted for deterministic output.
3. **Audit trail** — the spec designates these INFO-level JSON lines as the audit trail (e.g. `http_request`, `tool_invoked`, `policy decisions`, `auth_login_started`). Downstream tooling must read stdout JSON lines; the OTLP mirror is secondary.
4. **OTLP log bridge** — when `OTEL_ENABLED=true`, `setup_telemetry()` creates an OTel `LoggerProvider` with a `BatchLogRecordProcessor(OTLPLogExporter())`, sets it as the global logger provider, detaches `opentelemetry.*` loggers from propagation, and adds an OTel `LoggingHandler` to the root logger. Exporters append `/v1/logs` to `OTEL_EXPORTER_OTLP_ENDPOINT`. Authentication uses `OTEL_EXPORTER_OTLP_HEADERS` (Basic auth for OpenObserve).
5. **Fail-open** — OTel setup errors are caught and logged; missing/unreachable backends drop telemetry without raising. The service continues operating normally.
6. **Request correlation** — `x-request-id` is the log/portal-facing correlation key, generated if absent and forwarded on outbound calls. When tracing is active, `x-request-id` is set to the active span's W3C `trace_id` (32 hex chars); otherwise it falls back to `req-<uuid4>`. `traceparent` (W3C Trace Context) is propagated automatically by OTel instrumentation across service hops.
7. **Service name resource** — OTel Resource uses `OTEL_SERVICE_NAME` (defaults to the service's metadata name) so all signals are tagged consistently.
8. **Cardinality rules** — labels must be bounded enums; raw URLs, user IDs, session IDs, and request IDs are forbidden as metric labels. Structured log fields may carry high-cardinality data since they are line-based, not indexed labels.

## Conventions and constraints

- **Every service must call `configure_logging()` at startup.** The docstrings in each `core/observability.py` explicitly state that Uvicorn starts at WARNING and would discard audit records otherwise.
- **Business and request events use `log_event(...)` at INFO level**, not `logger.info("...")` with ad-hoc formatting. This ensures uniform JSON shape with a stable `event` field.
- **OTel push is off by default** (`OTEL_ENABLED=false`). It requires explicit enablement plus `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_EXPORTER_OTLP_HEADERS` provisioned via runtime secrets (`sync-otel-secrets.sh`).
- **No per-signal toggles** — one switch gates traces + metrics + log mirror together.
- **JSON stdout remains source of truth**; OTLP logs are a correlated mirror only.
- **Recursion guard** — `logging.getLogger("opentelemetry").propagate = False` prevents exporter failures from looping back through the bridge.
- **Correlation header rule**: no service may silently drop an inbound `x-request-id` or `traceparent`.
- **Metric naming** follows `<service>_<noun>_<unit>` snake_case with `_total` suffixes on counters, using bounded labels only.