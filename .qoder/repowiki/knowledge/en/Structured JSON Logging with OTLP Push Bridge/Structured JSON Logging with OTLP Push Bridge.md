---
kind: logging_system
name: Structured JSON Logging with OTLP Push Bridge
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
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
---

## Approach

Luban's services use Python's stdlib `logging` module exclusively — no third-party logger framework. Every service ships an identical `core/observability.py` that provides two helpers:

- `configure_logging()` — raises the root logger from uvicorn's default `WARNING` to `INFO` via `logging.basicConfig(level=..., force=True)`, read from the `LOG_LEVEL` environment variable.
- `log_event(logger, event, **fields)` — serializes `{"event": ..., ...fields}` as a single-line JSON string (`json.dumps(..., default=str, sort_keys=True)`) at INFO level.

Business and request events (http_request, tool_invoked, policy decisions, etc.) are emitted through `log_event`; internal diagnostics use `LOGGER = logging.getLogger(__name__)` followed by direct `logger.info/debug/error` calls.

## Key Files

- Per-service `core/observability.py` (8 copies under each product): `products/{agent-platform,audit-service,execution-runtime,identity-broker,incident-service,platform-gateway,skills-hub,tool-gateway}/src/*/core/observability.py`
- `shared/shared-contracts/observability-conventions.md` — the authoritative cross-service contract for metrics, tracing, logging, and correlation.
- `products/agent-platform/src/agent_service/core/telemetry.py` — opt-in OpenTelemetry push pipeline; sets up traces, metrics, and the OTLP log bridge.

## Architecture

Two decoupled observability surfaces (per `observability-conventions.md`):

1. **`/metrics` (pull, always on)** — Prometheus endpoint via `prometheus_client`. Independent of OTel.
2. **OpenTelemetry push (opt-in)** — gated by `OTEL_ENABLED` (default `false`). When enabled, `setup_telemetry()` installs TracerProvider, MeterProvider, FastAPI + HTTPX instrumentation, and attaches an OTel `LoggingHandler` to the root logger so every structured record is also exported over OTLP HTTP/protobuf to `OTEL_EXPORTER_OTLP_ENDPOINT`.

The OTLP log bridge is additive: container stdout JSON remains the source of truth for audit tooling; the bridge exists only so logs can be correlated with traces via automatic `trace_id`/`span_id` attachment when a span is active. The `opentelemetry` loggers are detached from the root logger (`propagate = False`) to prevent exporter failures from recursing back into the bridge.

## Conventions and Constraints

- **Structured fields**: All business/request events go through `log_event(event, **fields)`, producing one JSON line per record. Fields are merged into the payload without nesting.
- **Log level**: Default is `INFO` so audit records survive; overridden per deployment via `LOG_LEVEL`. Uvicorn's WARNING default is explicitly raised in `configure_logging()`.
- **OTel gating**: A single `OTEL_ENABLED` switch gates traces + metrics + log mirror; there are no per-signal toggles. Disabled state initializes nothing (zero overhead).
- **Fail-open**: OTel setup errors are logged and swallowed; they never propagate into the request path. Missing/misconfigured backend produces export-time drops, not startup failures.
- **Correlation**: `x-request-id` is the log- and portal-facing key; `traceparent` (W3C Trace Context) is the machine-facing propagation header. When tracing is active, `x-request-id` is set to the active span's W3C `trace_id` so logs and traces join on the same id.
- **Cardinality rules** (from `observability-conventions.md`): Never label on raw URL, user id, session id, or request id. Domain counters use bounded enum labels only.
- **Metric naming**: `<service>_<noun>_<unit>` snake_case, counters carry `_total`, service prefix is short name (`gateway`, `identity`, `agent`).
- **OTLP endpoint**: `OTEL_EXPORTER_OTLP_ENDPOINT` points at the org prefix (e.g. `http://openobserve-router:5080/api/default`); exporters append `/v1/{traces,metrics,logs}`. Authentication uses `OTEL_EXPORTER_OTLP_HEADERS` (Basic auth for OpenObserve), provisioned via runtime secrets.
- **Service identity**: `OTEL_SERVICE_NAME` resource attribute defaults to the service's metadata name.