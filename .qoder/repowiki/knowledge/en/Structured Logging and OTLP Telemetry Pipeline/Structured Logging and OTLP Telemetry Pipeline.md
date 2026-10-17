---
kind: logging_system
name: Structured Logging and OTLP Telemetry Pipeline
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
---

## Approach

The platform uses Python's stdlib `logging` module for all application output, with a thin shared convention layer (`core/observability.py`) that every service copies into its own package. Structured events are emitted as single-line JSON via the per-service `log_event(logger, event, **fields)` helper, which serializes `{"event": ..., **fields}` with `json.dumps(..., default=str, sort_keys=True)`. This is the audit trail — HTTP request records, tool invocations, policy decisions, session lifecycle events.

OpenTelemetry (OTel) provides an opt-in push pipeline (traces + metrics + mirrored logs) over OTLP HTTP/protobuf to OpenObserve. The two surfaces are deliberately decoupled: `/metrics` (Prometheus pull, always on) and OTLP push (gated by `OTEL_ENABLED`, off by default). Disabling OTel has zero overhead and never breaks requests.

## Key Files

- `shared/shared-contracts/observability-conventions.md` — the authoritative cross-service contract (SPEC-005 / SPEC-065), defining naming, cardinality, correlation, and OTel switch semantics.
- Per-service `src/<service>/core/observability.py` — identical `configure_logging()` + `log_event()` helpers in agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway.
- Per-service `src/<service>/core/telemetry.py` — opt-in OTel setup, `MetricsMirror`, `current_trace_id()`, and the root logger bridge (`LoggingHandler`).
- Per-service `app.py` — calls `configure_logging()` at startup and wires `setup_telemetry(app, service_name)`.

## Architecture and Conventions

### Log level configuration

Uvicorn starts with the root logger at `WARNING`, which would silently drop every `INFO`-level structured record. Every service calls `configure_logging()` at app startup:

```python
level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
level = getattr(logging, level_name, logging.INFO)
logging.basicConfig(level=level, force=True)
```

Default is `INFO`; override per deployment via `LOG_LEVEL`. Tests assert both the default and a `WARNING` override.

### Structured event format

Business/request events go through `log_event(LOGGER, "event_name", field=value, ...)`, producing one JSON line like:

```
{"event":"http_request","method":"GET","path":"/api/v1/sessions/{id}","status":200,"request_id":"..."}
```

Fields are free-form but should be bounded; high-cardinality values (raw URL, user id, session id, request id) are explicitly forbidden as metric labels per the conventions doc.

### Request correlation

- `x-request-id` is the log- and portal-facing correlation key. Generated if absent, forwarded on outbound calls.
- `traceparent` (W3C Trace Context) is the machine-facing propagation header, managed by OTel instrumentation.
- When tracing is active, `x-request-id` is bridged to the active span's W3C `trace_id` (32 hex chars); otherwise it falls back to `req-<uuid4>`.
- No service may silently drop an inbound correlation id.

### OTel log bridge

When `OTEL_ENABLED=true`, `setup_telemetry()` attaches an OTel `LoggingHandler` to the root logger so every structured record is also exported as an OTLP log record. Semantics documented in the conventions:

- JSON stdout remains the source of truth; OTLP is a mirror for trace-log correlation.
- Trace/span association is automatic inside an active span.
- `opentelemetry` loggers are detached from the root logger (`propagate = False`) to prevent recursion on exporter failure.

### Metrics mirror (SPEC-065 R-2)

`MetricsMirror` re-emits each service's `prometheus_client` domain families as OTel instruments (same name, same bounded label set) when OTel is enabled, so domain metrics reach dashboards over OTLP instead of only via scraping. It is lazy (instruments built on first record), no-op when disabled, fail-open, and byte-identical across all eight services.

### Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `LOG_LEVEL` | Root logger level override | `INFO` |
| `OTEL_ENABLED` | Master gate for traces+metrics+logs push | `false` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP HTTP base URL | unset |
| `OTEL_EXPORTER_OTLP_HEADERS` | Ingest auth headers (Basic for OpenObserve) | unset |
| `OTEL_SERVICE_NAME` | Resource service name | service metadata name |

### Fail-open guarantee

OTel initialization errors are caught and logged (`LOGGER.exception(...)`); they never propagate into the request path. Export failures are handled by OTel batch processors. Missing/misconfigured credentials produce 401s at export time without affecting the service.

## Enforced Rules

- All business and request events are emitted as single-line JSON via `log_event(...)` at INFO level — stated as a requirement in `observability-conventions.md` and enforced by the `configure_logging()` helper raising the root logger from uvicorn's WARNING default.
- High-cardinality values (raw URL, user id, session id, request id) must not be used as metric labels — explicitly prohibited in the conventions doc.
- OTel push is controlled exclusively by `OTEL_ENABLED`; there are no per-signal toggles — stated in the conventions doc and implemented in `_flag_enabled()`.
- `x-request-id` must never be silently dropped on inbound requests — stated as a rule in the conventions doc.
- Domain-metric names follow `<service>_<noun>_<unit>` snake_case with counters carrying `_total` — specified in the conventions doc.