---
kind: logging_system
name: Structured JSON Audit Logging with Optional OTLP Bridge
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/incident-service/src/incident_service/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/agent-platform/src/agent_service/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/telemetry.py
    - products/incident-service/src/incident_service/app.py
    - products/incident-service/src/incident_service/services/audit_emitter.py
---

## What system/approach is used

Every service in the repository implements a uniform, Python `logging`-based structured logging system. There is no third-party logging framework (no structlog, loguru, or logzero). The pattern is:

1. Each product package ships its own `src/<service>/core/observability.py` exposing two functions: `configure_logging()` and `log_event(logger, event, **fields)`.
2. `configure_logging()` calls `logging.basicConfig(level=..., force=True)` where the level is read from the `LOG_LEVEL` environment variable (default `INFO`). This raises the root logger above Uvicorn's default `WARNING` so INFO-level audit records are not silently dropped.
3. `log_event()` serializes the call as a single-line JSON object via `json.dumps(payload, default=str, sort_keys=True)` and emits it at `logger.info(...)`.
4. Every service's `app.create_app()` invokes `configure_logging()` before creating the FastAPI app, and business/request code logs through `log_event(LOGGER, "<event_name>", ...)` rather than calling `logger.info(...)` directly.
5. An optional OpenTelemetry push pipeline (`OTEL_ENABLED`) attaches an OTel `LoggingHandler` to the root logger so every structured record is mirrored over OTLP HTTP/protobuf to the configured backend (OpenObserve). The bridge is opt-in, fails open, and never replaces stdout — stdout remains the source of truth for the audit trail.

The approach is documented centrally in `shared/shared-contracts/observability-conventions.md`, which defines the two-surface model (Prometheus `/metrics` pull + OTLP push), the `LOG_LEVEL` override, the `x-request-id` correlation header, and the rule that all business and request events must be emitted as single-line JSON via `log_event(...)` at INFO level.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — authoritative cross-service contract describing the logging strategy, levels, OTLP bridge, and correlation rules.
- Per-service `src/<service>/core/observability.py` — identical `configure_logging()` / `log_event()` pair (incident-service, platform-gateway, audit-service, agent-platform, identity-broker, skills-hub, tool-gateway).
- Per-service `src/<service>/core/telemetry.py` — opt-in OTel setup; `tool_gateway/core/telemetry.py` shows the full implementation including `_attach_log_bridge`, `setup_telemetry(app, service_name)`, and `current_trace_id()`.
- Per-service `src/<service>/app.py` — calls `configure_logging()`, installs an HTTP middleware that emits `http_request` events via `log_event`, and wires `setup_metrics` / `setup_telemetry`.
- `products/incident-service/src/incident_service/services/audit_emitter.py` — example of emitting a domain-specific audit event (`incident_triaged`) to the dedicated audit-service ingest endpoint, separate from the local structured log stream.

## Architecture and conventions

- **Uniform per-service module**: each service owns its own `core/observability.py`; there is no shared library for logging. The modules are intentionally tiny and duplicated so services remain independently deployable.
- **Single-line JSON audit records**: every business/event log is one line of JSON containing at minimum an `event` field plus domain fields. Keys are sorted deterministically via `sort_keys=True`.
- **Root logger control**: `configure_logging()` uses `logging.basicConfig(force=True)` to reconfigure the root logger regardless of what Uvicorn/FastAPI set up. The effective level defaults to `INFO` and can be overridden by `LOG_LEVEL`.
- **HTTP request tracing**: each service registers an HTTP middleware that resolves `x-request-id` (generated if absent) and emits an `http_request` event carrying `method`, `path`, `status_code`, `duration_ms`, and `request_id`.
- **OTLP mirror**: when `OTEL_ENABLED=true`, `setup_telemetry` attaches an OTel `LoggingHandler` to the root logger so the same JSON records are exported as OTLP logs. The `opentelemetry` internal loggers are detached (`propagate = False`) to prevent recursion. Trace/span IDs attach automatically when a span is active, joining logs to traces via W3C `traceparent`.
- **Fail-open**: OTel initialization errors are caught and logged; they never raise into the request path. Missing/invalid credentials produce export-time drops, not startup failures.
- **Separation of concerns**: local structured logs (stdout JSON) are the audit trail; the `AuditConnector` in incident-service additionally pushes a domain event to the centralized `audit-service` ingest API (`/api/v1/audit/events`) for long-term retention and cross-service querying.

## Conventions and constraints

Observed conventions (descriptive):
- All services follow the same `core/observability.py` shape with `configure_logging()` and `log_event(logger, event, **fields)`.
- Business and request events are always emitted via `log_event(...)` at INFO level, never via raw `logger.info(...)`.
- `LOG_LEVEL` overrides the root logger level; the default must stay `INFO` so audit records are never silently discarded.
- `x-request-id` is the log- and portal-facing correlation key; `traceparent` (W3C Trace Context) is the machine-facing propagation header managed by OTel instrumentation.
- When tracing is active, `x-request-id` is bridged to the active span's W3C `trace_id`; when inactive it falls back to a generated `req-<uuid4>`.
- No service may silently drop an inbound correlation id.
- Structured logs on stdout remain the source of truth; the OTLP bridge is only a mirror for correlation with traces.
- Metrics use `prometheus_client` on a `/metrics` endpoint; this is independent from the logging system but co-located under `core/metrics.py`.

Enforced / documented rules (from `shared/shared-contracts/observability-conventions.md`):
- All business and request events must be emitted as single-line JSON via `log_event(...)` at INFO level.
- Every service must call `configure_logging()` at app startup to raise the root logger from uvicorn's WARNING default.
- `LOG_LEVEL` is the per-deployment override for the root logger level.
- OTel push is controlled solely by `OTEL_ENABLED`; when false, no OTel providers are initialized and `/metrics` is unaffected.
- High-cardinality labels must never be used as metric labels (applies to metrics, not logs); unbounded values such as raw URLs, user ids, session ids, and request ids are prohibited as labels.
- Fail-open guarantee: unreachable or misconfigured OTel backends must never break a request.