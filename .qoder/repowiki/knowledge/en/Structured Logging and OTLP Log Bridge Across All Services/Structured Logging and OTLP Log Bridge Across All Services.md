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
    - products/audit-service/src/audit_service/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
---

## What system/approach is used

The Luban platform uses Python's stdlib `logging` module as its sole logging framework — no third-party logger (structlog, loguru, python-json-logger) is imported anywhere in production code. Every product service ships an identical `core/observability.py` that exposes two functions:

- `configure_logging()` — raises the root logger from uvicorn's default `WARNING` to `INFO` via `logging.basicConfig(level=..., force=True)`, read from the `LOG_LEVEL` environment variable (defaulting to `INFO`).
- `log_event(logger, event, **fields)` — serializes a dict with a fixed `event` key plus arbitrary fields into a single-line JSON string (`json.dumps(..., default=str, sort_keys=True)`) and emits it at `INFO` level.

All structured audit events (HTTP requests, tool invocations, policy decisions, handoffs, etc.) go through this helper so they are machine-parseable JSON on stdout. There is no custom formatter; the JSON payload itself is the structured record.

OpenTelemetry is layered on top as an opt-in mirror: when `OTEL_ENABLED=true`, `core/telemetry.py` attaches an OTel `LoggingHandler` to the root logger so every `INFO`+ record is also exported over OTLP HTTP/protobuf to the configured backend (OpenObserve). The bridge is guarded against recursion by detaching `opentelemetry` loggers from the root logger.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — authoritative spec for the logging surface, levels, correlation keys, and OTLP bridge semantics.
- Per-service `core/observability.py` (identical across all eight services):
  - `products/agent-platform/src/agent_service/core/observability.py`
  - `products/audit-service/src/audit_service/core/observability.py`
  - `products/execution-runtime/src/execution_runtime/core/observability.py`
  - `products/identity-broker/src/identity_service/core/observability.py`
  - `products/incident-service/src/incident_service/core/observability.py`
  - `products/platform-gateway/src/platform_gateway/core/observability.py`
  - `products/skills-hub/src/skills_hub/core/observability.py`
  - `products/tool-gateway/src/tool_gateway/core/observability.py`
- Per-service `core/telemetry.py` — OTel push pipeline, log bridge, and `MetricsMirror`.
- Per-service `app.py` / `main.py` entrypoints call `configure_logging()` early and emit a startup `log_event`.
- Consumer sites: `audit_service/api/routes/{export,ingest,query,summary}.py`, `audit_service/services/retention.py`, and many agent-platform services under `services/`.

## Architecture and conventions

1. **Two decoupled observability surfaces** (per `observability-conventions.md`):
   - `/metrics` pull endpoint (Prometheus, always on).
   - OpenTelemetry push (opt-in via `OTEL_ENABLED`, defaults off).
2. **Structured logs are the audit trail.** Business and request events are emitted as single-line JSON at INFO level; disabling them would silently discard the audit trail, which is why `configure_logging()` explicitly raises the root level.
3. **Level control:** `LOG_LEVEL` env var (e.g. `WARNING`, `DEBUG`) overrides the default `INFO`. Tests in each service verify both the default and an explicit override.
4. **OTLP log bridge:** When enabled, the same stdout records are mirrored to OTLP logs so the backend can correlate them with traces (trace/span ids attach automatically inside active spans). Stdout remains the source of truth; container log tooling must keep reading it.
5. **Request correlation:** `x-request-id` is the log- and portal-facing correlation key; `traceparent` (W3C Trace Context) is the machine-facing propagation header. When tracing is active, `x-request-id` is set to the active span's W3C `trace_id`; otherwise it falls back to `req-<uuid4>`.
6. **Fail-open:** OTel setup errors are logged and swallowed — never raised into the request path. Missing/misconfigured credentials produce export-time 401s dropped by batch processors.
7. **No per-signal toggles:** `OTEL_ENABLED` gates traces + metrics + log mirror together.

## Conventions and constraints

- **Convention (observed across all eight services):** Each service has a `core/observability.py` implementing `configure_logging()` and `log_event()`, imported and called from the service's `app.py` at startup. The file contents are byte-identical between services.
- **Convention (observed):** Structured business events use `log_event(logger, "<event_name>", **fields)` rather than direct `logger.info(...)`, ensuring every audit record is a single JSON line with a stable `event` field.
- **Rule (documented in `shared/shared-contracts/observability-conventions.md`):** "All business and request events are emitted as single-line JSON via `log_event(...)` at INFO level." This is backed by the fact that every service calls `configure_logging()` at startup to raise the root logger from uvicorn's WARNING default.
- **Rule (documented):** `LOG_LEVEL` is the per-deployment override for the root logger level; the default must stay `INFO` so audit records are not silently discarded.
- **Rule (documented):** OTel push is controlled exclusively by `OTEL_ENABLED` (default `false`); there are no per-signal switches.
- **Rule (documented):** Never use unbounded values as metric labels (raw URL, user id, session id, request id) — high-cardinality labels are rejected at review.
- **Rule (documented):** `x-request-id` is the log- and portal-facing correlation key; no service may silently drop an inbound correlation id.
- **Constraint (enforced by implementation):** The OTLP log bridge is attached only once per process (guarded by `_log_bridge_attached`), and `opentelemetry` loggers are detached from the root logger to prevent recursion if exporters fail.