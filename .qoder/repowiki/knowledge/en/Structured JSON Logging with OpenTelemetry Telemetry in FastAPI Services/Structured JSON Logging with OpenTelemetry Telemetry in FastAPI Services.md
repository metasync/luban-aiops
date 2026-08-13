---
kind: logging_system
name: Structured JSON Logging with OpenTelemetry Telemetry in FastAPI Services
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/agent-platform/src/agent_service/app.py
    - products/platform-gateway/src/platform_gateway/core/observability.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/tool-gateway/src/tool_gateway/core/observability.py
    - products/tool-gateway/src/tool_gateway/core/telemetry.py
    - products/tool-gateway/src/tool_gateway/app.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/identity-broker/src/identity_service/core/telemetry.py
    - products/identity-broker/src/identity_service/app.py
---

## What system/approach is used

The platform uses Python's standard `logging` module for structured, single-line JSON audit logs and an opt-in OpenTelemetry (OTel) push pipeline for traces and metrics. There is no third-party logging framework (no loguru, structlog, or python-json-logger); instead each service ships a tiny, identical `core/observability.py` that provides:

- `configure_logging()` — raises the root logger from uvicorn's default `WARNING` to `INFO` so audit records are never silently dropped; level is overridable via the `LOG_LEVEL` environment variable.
- `log_event(logger, event, **fields)` — serializes `{"event": event, ...fields}` as sorted-key JSON at `INFO` level.

OpenTelemetry is gated by `OTEL_ENABLED` (default false). When enabled it installs FastAPI and HTTPX instrumentation, sets up a `TracerProvider` + `BatchSpanProcessor` and a `MeterProvider` + `PeriodicExportingMetricReader` both exporting OTLP gRPC to `OTEL_EXPORTER_OTLP_ENDPOINT`, tagged with `service.name` from `OTEL_SERVICE_NAME` (falling back to the service's metadata name). Initialization errors are caught and logged — fail-open by design.

Prometheus `/metrics` is always-on (independent of OTel), implemented via `prometheus-fastapi-instrumentator` per `SPEC-005`.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — authoritative cross-service contract defining metric naming, cardinality rules, OTel switch semantics, request correlation (`x-request-id` bridged to W3C `traceparent`), and the two-surface model.
- Per-service `core/observability.py` (identical across all four services): `agent-platform/src/agent_service/core/observability.py`, `platform-gateway/src/platform_gateway/core/observability.py`, `tool-gateway/src/tool_gateway/core/observability.py`, `identity-broker/src/identity_service/core/observability.py`.
- Per-service `core/telemetry.py` (identical across all four services): `agent-platform/src/agent_service/core/telemetry.py`, `platform-gateway/src/platform_gateway/core/telemetry.py`, `tool-gateway/src/tool_gateway/core/telemetry.py`, `identity-broker/src/identity_service/core/telemetry.py`.
- Per-service `app.py` entrypoints: `products/*/src/*/app.py` — call `configure_logging()`, register an HTTP middleware that emits `http_request` events via `log_event`, then call `setup_metrics(app)` and `setup_telemetry(app, SERVICE_NAME)`.
- `products/*/tests/test_observability.py` — verify `LOG_LEVEL` overrides the root logger level.

## Architecture and conventions

### Two decoupled observability surfaces
1. **Structured logs** (`INFO` JSON via `log_event`) — the audit trail (HTTP requests, tool invocations, policy decisions, token delegation).
2. **OTel push** (opt-in) — traces + metrics pushed via OTLP gRPC.

They never depend on each other; disabling OTel leaves `/metrics` and structured logs fully functional.

### Log-level strategy
- Default root level is `INFO` (raised from uvicorn's `WARNING`).
- Overridden per-deployment via `LOG_LEVEL`.
- All business/request events use `INFO`; there is no custom level scheme beyond standard `logging` levels.

### Structured fields
Every audit record is a flat JSON object produced by `json.dumps(payload, default=str, sort_keys=True)` where `payload = {"event": <event_name>, **fields}`. Event names observed include `http_request`, `otel telemetry enabled`, and domain-specific ones like `tool_invoked`, `policy_decisions`, `token_delegation` referenced in docstrings.

### Request correlation
- `x-request-id` is the log- and portal-facing correlation key. It is generated if absent and forwarded on every outbound call.
- When tracing is active, `current_trace_id()` returns the active span's W3C `trace_id` (32 hex chars) and is used to set `x-request-id`, bridging logs and APM traces.
- When tracing is inactive, `x-request-id` falls back to `req-<uuid4>`.

### Metric naming (from the shared convention)
- Format: `<service>_<noun>_<unit>` snake_case; counters carry `_total`.
- Service prefix is short: `gateway`, `identity`, `agent`.
- Labels are bounded enums only; raw URLs, user ids, session ids, request ids are forbidden as labels.

### Deployment wiring
Each service's `create_app()` follows the same sequence:
1. `configure_logging()`
2. `FastAPI(...)`
3. Register HTTP middleware emitting `http_request` events
4. `setup_metrics(app)`
5. `setup_telemetry(app, SERVICE_NAME)`

## Conventions and constraints

- **Audit records must be INFO-level JSON** — enforced by the shared `log_event` helper and the `configure_logging()` call at app startup; tests assert the root logger level reflects `LOG_LEVEL`.
- **OTel is off by default** — `OTEL_ENABLED` defaults to false; initialization is wrapped in try/except so misconfiguration cannot break requests.
- **No unbounded label cardinality** — documented in `observability-conventions.md`; raw URLs, user/session/request IDs may not be used as Prometheus labels.
- **`x-request-id` must never be silently dropped** — inbound correlation IDs are preserved and propagated.
- **Per-service isolation** — each product ships its own `core/observability.py` and `core/telemetry.py`; there is no shared library package for logging, but the implementations are intentionally identical to keep services self-contained while following the same contract.