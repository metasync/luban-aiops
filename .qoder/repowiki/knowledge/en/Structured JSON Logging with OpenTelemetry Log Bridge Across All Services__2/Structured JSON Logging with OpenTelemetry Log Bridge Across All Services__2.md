---
kind: logging_system
name: Structured JSON Logging with OpenTelemetry Log Bridge Across All Services
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/platform-gateway/src/platform-gateway/core/request_context.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
---

## What system/approach is used

The platform uses Python's standard `logging` module as the sole logging framework. Every service in the monorepo (`agent-platform`, `audit-service`, `execution-runtime`, `identity-broker`, `incident-service`, `platform-gateway`, `skills-hub`, `tool-gateway`) ships an identical `core/observability.py` that provides two helpers: `configure_logging()` and `log_event(logger, event, **fields)`. There is no third-party logger library (no structlog, loguru, or similar). Structured logs are single-line JSON emitted at INFO level via `json.dumps(payload, default=str, sort_keys=True)`.

OpenTelemetry is used only as an opt-in push pipeline for traces, metrics, and a mirrored copy of structured logs to OTLP HTTP/protobuf. The OTel bridge is attached by adding an `opentelemetry.instrumentation.logging.LoggingHandler` to the root logger when `OTEL_ENABLED=1`; it never replaces stdout JSON, which remains the source of truth for audit tooling.

## Key files and packages

- Per-service `src/<service>/core/observability.py` — defines `configure_logging()` (reads `LOG_LEVEL`, calls `logging.basicConfig(level=..., force=True)`) and `log_event(...)` (serializes `{event, ...fields}` to JSON).
- Per-service `src/<service>/core/telemetry.py` — implements the opt-in OTel pipeline: `setup_telemetry(app, service_name)`, `_attach_log_bridge(resource)`, `is_enabled()`, `current_trace_id()`; initializes TracerProvider, MeterProvider, FastAPIInstrumentor, HTTPX client instrumentation, and the OTLP log bridge.
- Per-service `src/<service>/core/request_context.py` — resolves `x-request-id` per SPEC-005 R-4: inbound header wins, otherwise bridges to active OTel trace id, otherwise generates `req-<uuid4>`.
- `shared/shared-contracts/observability-conventions.md` — the authoritative spec documenting the two-surface model (`/metrics` pull + OTel push), metric naming, cardinality rules, OTel switch semantics, structured logging levels, OTLP log bridge behavior, request correlation bridging, and backend relationship.

## Architecture and conventions

### Two decoupled observability surfaces
Each service exposes:
1. `/metrics` (Prometheus pull, always on, implemented with `prometheus_client`).
2. OpenTelemetry push (opt-in, gated by `OTEL_ENABLED`; off by default, fails open).

These surfaces never depend on each other — disabling OTel leaves `/metrics` fully functional.

### Structured log format
Business and request events are emitted through `log_event(LOGGER, "<event_name>", field=value, ...)`, which produces one JSON line like `{"event": "http_request", "method": "GET", "path": "/api/v1/sessions/{id}", ...}`. Audit-critical records include `http_request`, `tool_invoked`, `policy_decisions`, `auth_*`, `token_*`, `handoff_*`, `session_*`, etc., depending on the service.

### Log level strategy
Uvicorn starts with root logger at WARNING, which would silently discard all INFO-level audit records. Every service calls `configure_logging()` at app startup to raise the root level to INFO (overridable via `LOG_LEVEL`; default must stay INFO so audit records are never dropped).

### Request correlation
- `x-request-id` is the log- and portal-facing correlation key. It is generated if absent (preserving the portal contract) and forwarded on every outbound call.
- `traceparent` (W3C Trace Context) is the machine-facing propagation header, managed automatically by OTel instrumentation across hops.
- When tracing is active, `x-request-id` is set to the active span's W3C `trace_id` (32 hex chars) so a single value joins structured logs and APM traces; when inactive it falls back to `req-<uuid4>`.
- No service may silently drop an inbound correlation id.

### OTLP log bridge
When `OTEL_ENABLED=1`, each service attaches an OTel `LoggingHandler` to the root logger so every structured record is also exported as an OTLP log record. Semantics:
- JSON stdout stays the source of truth; the OTLP mirror exists for backend correlation with traces.
- Trace/span association is automatic — records emitted inside an active span carry its `trace_id`/`span_id`.
- Recursion guard: `logging.getLogger("opentelemetry").propagate = False` so exporter failures cannot loop back through the bridge.
- The bridge is gated by the same `OTEL_ENABLED` switch and fails open.

### Metric naming and cardinality
- Format: `<service>_<noun>_<unit>` snake_case; counters carry `_total` suffix.
- Standard RED labels: `method`, `handler` (templated route), `status`.
- Domain counters use bounded enum labels only (e.g. `decision ∈ {allow, deny}`).
- Never label on unbounded values: raw URL, user id, session id, request id.

### Environment variables
- `LOG_LEVEL` — overrides root logger level per deployment.
- `OTEL_ENABLED` — master gate for traces + metrics + log mirror (default false).
- `OTEL_EXPORTER_OTLP_ENDPOINT` — OTLP HTTP base URL (exporters append `/v1/traces`, `/v1/metrics`, `/v1/logs`).
- `OTEL_EXPORTER_OTLP_HEADERS` — ingest auth (Basic token for OpenObserve), provisioned via secrets.
- `OTEL_SERVICE_NAME` — resource service name; defaults to service metadata.

## Conventions and constraints

- **Every service must call `configure_logging()` at startup** to raise the root logger from uvicorn's WARNING default to INFO so audit records are not silently discarded. (Enforced by the convention documented in `observability-conventions.md` and duplicated in every service's `observability.py` docstring.)
- **All business/request events must go through `log_event(...)`**, not bare `logger.info(...)`, to guarantee consistent JSON shape with an `event` field plus arbitrary fields serialized via `json.dumps(..., default=str, sort_keys=True)`. (Observed consistently across all services' routes and services.)
- **OTel push is opt-in and fail-open**: setup errors are logged via `LOGGER.exception(...)` and never raised into the request path. Missing/invalid credentials produce export-time 401s; batch processors drop telemetry on failure. (Documented in `telemetry.py` docstrings and `observability-conventions.md`.)
- **No high-cardinality labels**: raw URLs, user ids, session ids, request ids must never be Prometheus labels. (Explicitly forbidden in `observability-conventions.md`.)
- **Audit trail integrity**: structured JSON on stdout is the source of truth for audit tooling; the OTLP log bridge is a secondary mirror and must never replace stdout consumption. (Stated in both `telemetry.py` comments and `observability-conventions.md`.)
- **Correlation rule**: no service may silently drop an inbound `x-request-id`; when tracing is active it must bridge to the active trace id. (SPEC-005 R-4, enforced by `request_context.resolve_request_id`.)
- **Secrets handling**: OTel headers and other runtime secrets are provisioned via `sync-otel-secrets.sh` into per-service Secrets and never committed or placed in ConfigMaps. (Documented in `observability-conventions.md`.)

This pattern is replicated uniformly across all eight Python services in the `products/` directory, making the logging system a cross-cutting concern governed by shared conventions rather than a single centralized library.