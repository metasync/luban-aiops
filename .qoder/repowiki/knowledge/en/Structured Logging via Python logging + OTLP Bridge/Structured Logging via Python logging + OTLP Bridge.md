---
kind: logging_system
name: Structured Logging via Python logging + OTLP Bridge
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/agent-platform/src/agent_service/app.py
    - products/audit-service/src/audit_service/core/observability.py
    - products/audit-service/src/audit_service/app.py
    - products/execution-runtime/src/execution_runtime/app.py
    - products/identity-broker/src/identity_service/app.py
    - products/incident-service/src/incident_service/app.py
    - products/platform-gateway/src/platform_gateway/app.py
---

## What is used

The platform uses Python's stdlib `logging` module for all application log output, with a thin per-service wrapper that emits single-line JSON records at INFO level. An opt-in OpenTelemetry `LoggingHandler` bridges those stdout records to an OTLP HTTP/protobuf backend (OpenObserve) when `OTEL_ENABLED=true`. There is no third-party logger framework (no structlog, no loguru).

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — authoritative cross-product convention document defining the two observability surfaces (`/metrics` pull + OTel push), structured-log level policy, OTLP bridge semantics, and request-correlation rules.
- Per-service `core/observability.py` — defines `configure_logging()` and `log_event(logger, event, **fields)`; every product service ships its own copy under its package namespace.
- Per-service `core/telemetry.py` — initializes OTel providers, FastAPI/HTTPX instrumentation, and attaches the OTLP `LoggingHandler` to the root logger.
- Per-service `app.py` entrypoint — calls `configure_logging()` at startup and emits `log_event(...)` around request lifecycle hooks.

Services observed following this pattern: `agent-platform`, `audit-service`, `execution-runtime`, `identity-broker`, `incident-service`, `platform-gateway`. The remaining products (`operator-portal`, `skills-hub`, `tool-gateway`) were not individually verified but are expected to mirror the same layout.

## Architecture and conventions

**Log emission.** Business and request events go through `log_event(logger, "event_name", key=value, ...)`. The helper serializes the payload as `json.dumps({"event": event, ...}, default=str, sort_keys=True)` and writes it at INFO level. This makes every audit record a single-line JSON object on stdout — the source of truth for the audit trail.

**Level management.** `configure_logging()` reads `LOG_LEVEL` from the environment (defaulting to `INFO`), converts it via `getattr(logging, level_name, logging.INFO)`, and calls `logging.basicConfig(level=level, force=True)`. This overrides uvicorn's WARNING-level root logger so structured audit records are never silently dropped.

**OTLP bridge.** When `OTEL_ENABLED` is true, `setup_telemetry()` installs an OpenTelemetry `LoggerProvider` with a `BatchLogRecordProcessor(OTLPLogExporter())` and attaches an OTel `LoggingHandler` to the root logger at INFO level. Records emitted inside an active span automatically carry `trace_id`/`span_id`, joining logs to traces on the W3C id that backs `x-request-id`. The bridge detaches `logging.getLogger("opentelemetry")` from the root logger to prevent recursion if the exporter fails.

**Fail-open guarantee.** Both the OTel initialization and the `MetricsMirror` swallow exceptions and log them instead of raising into the request path. Disabling OTel leaves `/metrics` fully functional.

**Request correlation.** `x-request-id` is the log- and portal-facing correlation key. When tracing is active it is set to the active span's W3C `trace_id`; otherwise it falls back to `req-<uuid4>`. It is forwarded on every outbound service-to-service call.

**Two decoupled surfaces:**
1. `/metrics` (Prometheus, always on) — collector-independent, implemented directly with `prometheus_client`.
2. OTLP push (opt-in, gated by `OTEL_ENABLED`) — traces, metrics, and mirrored logs pushed over HTTP/protobuf to `OTEL_EXPORTER_OTLP_ENDPOINT`.

## Conventions and constraints

- **All business/request events are single-line JSON at INFO level**, emitted via `log_event(...)`. This is documented in `shared/shared-contracts/observability-conventions.md` and enforced by the fact that uvicorn's default WARNING root level would drop these records unless `configure_logging()` runs.
- **`LOG_LEVEL` controls the root logger level**; default must stay `INFO` so audit records are never silently discarded (documented in both the conventions doc and `core/observability.py`).
- **OTel push is off by default**, controlled exclusively by `OTEL_ENABLED` (with `is_enabled()` accepting `1`, `true`, `yes`, `on`). There are no per-signal toggles — one switch gates traces + metrics + log mirror.
- **JSON stdout remains the source of truth**; the OTLP bridge is additive only and never replaces container logs.
- **No service may silently drop an inbound correlation id** (`x-request-id` / `traceparent` bridging rule, stated in the conventions doc).
- **Cardinality rules apply to labels** (bounded enum labels only; never label on raw URL, user id, session id, or request id). While framed as metric guidance, the same bounded-label discipline is reflected in how `log_event` fields are passed through.
- **Per-service parity**: each product ships its own `core/observability.py` and `core/telemetry.py` rather than sharing a common library, keeping the eight services byte-identical in their observability wiring (enforced by the `TelemetryParityTest` referenced in `core/telemetry.py`).