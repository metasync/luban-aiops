---
kind: logging_system
name: Structured Logging and OTLP Log Bridge Across All Services
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/agent-platform/src/agent_service/app.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/audit-service/src/audit_service/core/telemetry.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/telemetry.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/identity-broker/src/identity_service/core/telemetry.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/incident-service/src/incident_service/core/telemetry.py
---

## Approach

Every Python service in the `products/` workspace uses Python's stdlib `logging` module for structured, single-line JSON audit logs, with an opt-in OpenTelemetry (OTel) push pipeline that mirrors those records to an OTLP backend. There is no third-party logging framework (no structlog, loguru, or similar); the convention is a thin per-service wrapper around `logging.Logger`.

The cross-cutting contract is documented in `shared/shared-contracts/observability-conventions.md`, which backs SPEC-005 (Observability Baseline). It defines two surfaces: `/metrics` (Prometheus, always on) and OTLP push (opt-in via `OTEL_ENABLED`).

## Key Files

- `shared/shared-contracts/observability-conventions.md` — authoritative spec for levels, fields, correlation, and OTLP bridge semantics.
- Per-service `core/observability.py` — exposes `configure_logging()` and `log_event(logger, event, **fields)`.
- Per-service `core/telemetry.py` — exposes `setup_telemetry(app, service_name)`, `is_enabled()`, `current_trace_id()`.
- Per-service `app.py` — calls `configure_logging()` at startup, installs an HTTP middleware that emits `http_request` events via `log_event`, then calls `setup_telemetry`.
- Per-service `core/request_context.py` — resolves/generates `x-request-id` and bridges it to the active OTel trace id.

Services following this pattern include agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, and tool-gateway (each has its own `core/observability.py` and `core/telemetry.py`).

## Architecture and Conventions

### Structured log format

Business and request events are emitted as one line of JSON via `log_event(logger, "event_name", field=value, ...)`. The helper wraps `logger.info(json.dumps(payload, default=str, sort_keys=True))`, so every record is a flat JSON object with an `event` key plus domain-specific fields. Example records observed:

- `http_request` (HTTP middleware): `service`, `request_id`, `method`, `path`, `status_code`, `duration_ms`.
- `auth_login_url_requested`, `auth_login_started`, `auth_logout_requested`, `identity_normalized` (identity-broker).
- `tool_invoked`, `policy_decisions`, `session_created`, etc., across services.

### Log levels

- Uvicorn starts the root logger at WARNING; `configure_logging()` raises it to INFO so audit records survive.
- Default level is INFO; override via the `LOG_LEVEL` environment variable (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`).
- Business/audit events use INFO. Debug-only messages use the module-level `LOGGER = logging.getLogger(__name__)` directly.

### Request correlation

- `x-request-id` is the log- and portal-facing correlation key. If absent, it is generated as `req-<uuid4>`; if present, it is forwarded on all outbound calls.
- When OTel tracing is active, `x-request-id` is set to the active span's W3C `trace_id` (32 hex chars), so logs and APM traces join on the same value.
- `traceparent` (W3C Trace Context) is the machine-facing propagation header, managed by OTel instrumentation.

### OTLP log bridge

When `OTEL_ENABLED=true`, `setup_telemetry` initializes TracerProvider, MeterProvider, FastAPI + HTTPX instrumentors, and attaches an OTel `LoggingHandler` to the root logger. Semantics:

- JSON stdout remains the source of truth; OTLP is a mirror for backend correlation.
- Records emitted inside an active span automatically carry `trace_id`/`span_id`.
- `logging.getLogger("opentelemetry").propagate = False` prevents recursion from exporter failures back into the bridge.
- Initialization is wrapped in try/except and fails open — setup errors are logged and the service continues without push.

### Metrics surface

Each service also exposes a local `/metrics` endpoint using `prometheus_client` (RED middleware). Metric naming follows `<service>_<noun>_<unit>` snake_case with `_total` suffixes on counters, bounded enum labels only, and no high-cardinality label values (raw URLs, user ids, session ids, request ids are forbidden as labels).

### Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `LOG_LEVEL` | Root logger level override | `INFO` |
| `OTEL_ENABLED` | Master gate for traces + metrics + log mirror | `false` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP HTTP base URL (OpenObserve router prefix) | — |
| `OTEL_EXPORTER_OTLP_HEADERS` | Basic auth headers for OpenObserve ingest | — |
| `OTEL_SERVICE_NAME` | Resource service name | service metadata name |

## Rules Enforced by Code

1. Every service must call `configure_logging()` before any business code runs, because uvicorn's default WARNING level would drop INFO audit records. (Enforced by `observability-conventions.md` and each service's `create_app()`.)
2. Audit events go through `log_event(...)`, not raw `logger.info(...)` with ad-hoc JSON, ensuring consistent `{"event": ..., ...}` shape and `sort_keys=True` output. (Enforced by the shared helper in each service's `core/observability.py`.)
3. OTel push is off by default and never breaks the request path; initialization failures are caught and logged. (Enforced by the try/except in `setup_telemetry` and the `is_enabled()` check.)
4. No service may silently drop an inbound `x-request-id`; it is either preserved or replaced with a generated UUID. (Enforced by `resolve_request_id` in each service's `request_context.py`.)
5. High-cardinality values (raw URL, user id, session id, request id) are prohibited as Prometheus label values. (Enforced by the cardinality rules in `observability-conventions.md`.)
6. The OTLP log bridge is gated by the same `OTEL_ENABLED` switch as traces/metrics; there are no per-signal toggles. (Enforced by the single `is_enabled()` check in `setup_telemetry`.)
7. Authentication for the OTLP backend comes from `OTEL_EXPORTER_OTLP_HEADERS`, provisioned via runtime secrets, never committed. (Enforced by the conventions doc and the telemetry module's reliance on env vars.)