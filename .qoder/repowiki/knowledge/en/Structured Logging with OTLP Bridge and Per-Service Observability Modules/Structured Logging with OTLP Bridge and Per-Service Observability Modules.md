---
kind: logging_system
name: Structured Logging with OTLP Bridge and Per-Service Observability Modules
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
    - products/audit-service/src/audit_service/app.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/telemetry.py
    - products/execution-runtime/src/execution_runtime/app.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/platform-gateway/src/platform_gateway/app.py
---

## What system/approach is used

The platform uses Python's standard `logging` module as the sole logging framework, augmented by an opt-in OpenTelemetry (OTel) push pipeline that mirrors structured logs to an OTLP backend (OpenObserve via HTTP/protobuf). There is no third-party logging library (e.g. structlog, loguru); every service ships its own tiny `core/observability.py` providing two functions — `configure_logging()` and `log_event(logger, event, **fields)` — and its own `core/telemetry.py` providing `setup_telemetry(app, service_name)`.

The authoritative specification for this surface is `shared/shared-contracts/observability-conventions.md`, which defines the two-surface model (`/metrics` pull + OTLP push), the environment switches, the request-correlation rules, and the structured logging level policy.

## Key files and packages

- Shared convention doc: `shared/shared-contracts/observability-conventions.md`
- Per-service implementations (identical shape across all products):
  - `products/agent-platform/src/agent_service/core/observability.py`, `.../core/telemetry.py`, `.../app.py`
  - `products/audit-service/src/audit_service/core/observability.py`, `.../core/telemetry.py`, `.../app.py`
  - `products/execution-runtime/src/execution_runtime/core/observability.py`, `.../core/telemetry.py`, `.../app.py`
  - `products/platform-gateway/src/platform_gateway/core/observability.py`, `.../core/telemetry.py`, `.../app.py`
  - `products/identity-broker/src/identity_service/core/observability.py`, `.../core/telemetry.py`, `.../app.py`
  - `products/incident-service/src/incident_service/core/observability.py`, `.../core/telemetry.py`, `.../app.py`
  - `products/skills-hub/src/skills_hub/core/observability.py`, `.../core/telemetry.py`, `.../app.py`
  - `products/tool-gateway/src/tool_gateway/core/observability.py`, `.../core/telemetry.py`, `.../app.py`
- Tests exercising the behavior: `test_observability.py`, `test_telemetry.py` in each product's `tests/` directory.

## Architecture and conventions

### Two decoupled surfaces
Each service exposes:
1. **Prometheus `/metrics`** — always-on, collector-independent, implemented directly with `prometheus_client` plus a RED middleware; never depends on OTel.
2. **OpenTelemetry push** — opt-in via `OTEL_ENABLED`; when disabled, zero OTel code is imported and there is no overhead.

### Structured log format
Business and request events are emitted as single-line JSON via `log_event(logger, "event_name", field=value, ...)`. The helper serializes `json.dumps(payload, default=str, sort_keys=True)` at INFO level. Every service calls `configure_logging()` during app startup to raise the root logger from uvicorn's WARNING default to INFO so these audit records survive; the level can be overridden per deployment via `LOG_LEVEL`.

### Request correlation
- `x-request-id` is the log- and portal-facing correlation key, generated if absent and forwarded on every outbound call.
- When tracing is active, `x-request-id` is set to the active span's W3C `trace_id` (32 hex chars); otherwise it falls back to `req-<uuid4>`.
- `traceparent` (W3C Trace Context) is propagated automatically by OTel instrumentation across service hops.

### OTLP log bridge
When `OTEL_ENABLED=true`, `setup_telemetry` attaches an OTel `LoggingHandler` to the root logger. Semantics enforced in code:
- JSON stdout remains the source of truth; OTLP is a mirror for trace/log correlation.
- Records emitted inside an active span automatically carry `trace_id`/`span_id`.
- `opentelemetry` loggers are detached from the root logger (`propagate = False`) to prevent recursion.
- Initialization failures are caught and logged; the service continues without push (fail-open).

### Service bootstrap pattern
Every product's `app.py` follows the same sequence:
```python
def create_app():
    configure_logging()                          # raise root logger to INFO
    app = FastAPI(...)
    @app.middleware("http")
    async def log_requests(request, call_next):  # emit http_request event
        ...
        log_event(LOGGER, "http_request", ...)
    setup_metrics(app)
    setup_telemetry(app, SERVICE_NAME)           # optional OTel push
    return app
```

### Environment variables
| Variable | Purpose | Default |
|---|---|---|
| `LOG_LEVEL` | Root logger level override | `INFO` |
| `OTEL_ENABLED` | Master gate for traces + metrics + log mirror | `false` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP HTTP base URL | — |
| `OTEL_EXPORTER_OTLP_HEADERS` | Basic-auth header for OpenObserve ingest | — |
| `OTEL_SERVICE_NAME` | Resource service name | metadata name |

## Conventions and constraints

- **All business/request events go through `log_event` at INFO level.** Uvicorn's default WARNING level would silently drop them; `configure_logging()` exists specifically to prevent that.
- **Audit trail is JSON lines on stdout.** The OTLP mirror must never replace container logs; audit tooling reads stdout.
- **No unbounded label cardinality.** The conventions forbid labeling raw URLs, user ids, session ids, or request ids as Prometheus labels; use templated `handler` instead.
- **OTel push is fail-open.** Missing credentials or unreachable backends produce export-time 401s or dropped batches; initialization exceptions are logged and do not break requests.
- **Request correlation cannot be silently dropped.** Inbound `x-request-id` must be preserved and forwarded on every outbound call.
- **Per-service duplication is intentional.** Each product owns its `core/observability.py` and `core/telemetry.py`; there is no shared SDK yet, so the same small modules are copied into every product.