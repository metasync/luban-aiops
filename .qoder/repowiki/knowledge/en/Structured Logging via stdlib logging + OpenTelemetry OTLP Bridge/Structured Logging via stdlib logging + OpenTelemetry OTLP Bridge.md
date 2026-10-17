---
kind: logging_system
name: Structured Logging via stdlib logging + OpenTelemetry OTLP Bridge
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
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/execution-runtime/src/execution_runtime/app.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/identity-broker/src/identity_service/app.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/incident-service/src/incident_service/app.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/skills-hub/src/skills_hub/core/observability.py
    - products/skills-hub/src/skills_hub/app.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/tool-gateway/src/tool_gateway/app.py
---

## Approach

The platform uses Python's stdlib `logging` module as the sole logging framework. There is no third-party logger (no structlog, loguru, or similar). Structured events are emitted as single-line JSON strings through a thin helper `log_event(logger, event, **fields)` that serializes `{"event": <name>, ...fields}` with `json.dumps(..., sort_keys=True)`. The JSON lines go to stdout and form the audit trail.

OpenTelemetry is used only as an opt-in push bridge: when `OTEL_ENABLED=true`, each service attaches an OTel `LoggingHandler` to the root logger so every structured record is also exported over OTLP HTTP/protobuf to the configured backend (OpenObserve). This mirror never replaces stdout — stdout remains the source of truth for audit tooling.

## Key files

- `shared/shared-contracts/observability-conventions.md` — authoritative cross-service convention document defining the two observability surfaces (`/metrics` pull always-on, OTel push opt-in), structured logging levels, OTLP log bridge semantics, request-correlation rules, and cardinality constraints.
- `products/*/src/<service>/core/observability.py` — per-service copy of `configure_logging()` and `log_event()`. Each product ships its own tiny implementation rather than importing from shared; all follow the same shape.
- `products/*/src/<service>/app.py` — every service calls `configure_logging()` at startup and then `setup_telemetry(app, service_name)` from `core/telemetry.py`.
- `products/agent-platform/src/agent_service/core/telemetry.py` — the canonical OTel setup code (traces, metrics, logs bridge, `MetricsMirror`). Other services replicate this pattern in their own `core/telemetry.py`.
- `products/agent-platform/tests/test_observability.py` — validates `LOG_LEVEL` override behavior.

## Architecture and conventions

1. **Per-service `core/observability.py`** provides:
   - `configure_logging()` — reads `LOG_LEVEL` from the environment (default `"INFO"`), converts it via `getattr(logging, level_name.upper(), logging.INFO)`, and calls `logging.basicConfig(level=level, force=True)`. This raises the root logger from uvicorn's default WARNING to INFO so structured audit records are not silently dropped.
   - `log_event(logger, event, **fields)` — builds a dict with a fixed `event` key plus arbitrary fields, serializes it to JSON, and emits it at INFO level.

2. **Log-level strategy**: All business and request events (http_request, tool_invoked, policy decisions) are INFO-level structured JSON. `LOG_LEVEL` can be overridden per deployment, but the documented default must stay INFO.

3. **OTel bridge** (`core/telemetry.py`):
   - Gated by `OTEL_ENABLED` (parsed case-insensitively against `{1, true, yes, on}`).
   - Initializes TracerProvider, MeterProvider, FastAPI instrumentation, HTTPX client instrumentation, and the OTLP log bridge once per process.
   - Detaches `opentelemetry` loggers from the root logger (`propagate = False`) so exporter failures cannot recurse back into the bridge.
   - Fails open: any exception during setup is logged and swallowed; the service continues without push.

4. **Request correlation** (from the conventions doc):
   - `x-request-id` is the log- and portal-facing correlation key, generated if absent and forwarded on outbound calls.
   - `traceparent` (W3C Trace Context) is the machine-facing propagation header managed by OTel.
   - When tracing is active, `x-request-id` is set to the active span's W3C `trace_id`; otherwise it falls back to `req-<uuid4>`.
   - No service may silently drop an inbound correlation id.

5. **Two decoupled surfaces**:
   - `/metrics` (Prometheus pull, always on).
   - OTel push (opt-in, fails open).
   - Domain metrics are mirrored to OTel instruments with the same name and bounded label set (`MetricsMirror`), per SPEC-065 ADR-0014.

## Conventions and constraints

- **All structured events are single-line JSON emitted at INFO level** via `log_event(...)`. This is stated as a requirement in `shared/shared-contracts/observability-conventions.md` under "Structured Logging Levels".
- **Root logger level defaults to INFO** and is raised explicitly via `configure_logging()` at app startup in every service (`agent-platform`, `audit-service`, `execution-runtime`, `identity-broker`, `incident-service`, `platform-gateway`, `skills-hub`, `tool-gateway`). The doc states the default "must stay INFO so audit records are never silently discarded".
- **OTel push is controlled exclusively by `OTEL_ENABLED`** — one switch gates traces + metrics + log mirror; there are no per-signal toggles (conventions doc, section "OpenTelemetry Switch Semantics").
- **OTLP endpoint configuration** uses `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`, and `OTEL_SERVICE_NAME` (conventions doc).
- **Fail-open guarantee**: unreachable/misconfigured OTel backend must never break a request; missing/invalid credentials produce 401s at export time and batch processors drop telemetry on failure (conventions doc).
- **Cardinality rule**: never use unbounded values as labels (raw URL, user id, session id, request id); high-cardinality labels are rejected at review (conventions doc, section "Cardinality Rules").
- **No service may silently drop an inbound correlation id** (conventions doc, section "Request Correlation And Trace Bridging").
- **JSON stdout stays the source of truth**; OTLP is a mirror for trace/log correlation, not a replacement for container logs (conventions doc, section "OTLP Log Bridge").

## Observed deviations / notes

- Several modules import `logging` directly and call `logger.info(...)` with keyword arguments (e.g. `LOGGER.info("otel telemetry enabled", extra={...})` in `telemetry.py`) rather than going through `log_event(...)`. These are internal diagnostic messages, not the structured audit events defined by the convention.
- Each product maintains its own copy of `core/observability.py` and `core/telemetry.py` instead of sharing a common package, which means drift between services is possible even though the patterns are nearly identical.