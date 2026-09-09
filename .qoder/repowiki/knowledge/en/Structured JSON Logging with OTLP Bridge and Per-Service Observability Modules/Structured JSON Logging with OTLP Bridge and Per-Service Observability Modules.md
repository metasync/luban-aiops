---
kind: logging_system
name: Structured JSON Logging with OTLP Bridge and Per-Service Observability Modules
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
    - products/audit-service/src/audit_service/core/observability.py
    - products/execution-runtime/src/execution_runtime/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/incident-service/src/incident_service/core/observability.py
    - products/skills-hub/src/skills_hub/core/observability.py
---

## What system/approach is used

The platform uses Python's stdlib `logging` module as the sole logging framework. Every service emits **single-line, sorted-key JSON** records via a shared `log_event(logger, event, **fields)` helper that calls `logger.info(json.dumps(payload, default=str, sort_keys=True))`. There is no third-party logger (no structlog, loguru, or logzero). Structured fields are passed as keyword arguments to `log_event`, which wraps them in an `{"event": ..., ...}` envelope.

For distributed correlation, each service maintains an `x-request-id` header (generated if absent) and bridges it into logs; when OpenTelemetry tracing is active, `x-request-id` is set to the active span's W3C `trace_id`, so a single value joins stdout logs and APM traces. The machine-facing propagation header is `traceparent` (W3C Trace Context), managed automatically by OpenTelemetry instrumentation.

OpenTelemetry push is **opt-in** and gated by `OTEL_ENABLED` (default false). When enabled, each service attaches an OTel `LoggingHandler` to the root logger so every structured record is also exported over OTLP HTTP/protobuf to the configured backend (OpenObserve). This bridge is a mirror — JSON stdout remains the source of truth for audit tooling.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — authoritative spec defining two surfaces (`/metrics` pull + OTLP push), metric naming, cardinality rules, OTel switch semantics, structured logging levels, OTLP log bridge behavior, and request-correlation bridging rules.
- Per-service `core/observability.py` modules — one per product under `products/<service>/src/<service_name>/core/observability.py`. Each exposes `configure_logging()` (raises root logger from uvicorn's WARNING default to INFO, overridable via `LOG_LEVEL`) and `log_event(logger, event, **fields)` (JSON-serializes payload with sorted keys).
- Per-service `core/telemetry.py` modules — identical implementations across services (`agent-platform`, `platform-gateway`, `tool-gateway`, etc.) providing `setup_telemetry(app, service_name)`, `is_enabled()`, `_attach_log_bridge(resource)`, and `current_trace_id()`.
- Per-service `app.py` entry points — call `configure_logging()` at startup, emit `http_request` events via `log_event` in an HTTP middleware, and invoke `setup_telemetry(app, SERVICE_NAME)`.
- `products/*/tests/test_observability.py` / `test_telemetry.py` — verify `LOG_LEVEL` override behavior and telemetry enablement.

## Architecture and conventions

1. **Per-service isolation**: Each product ships its own `core/observability.py` and `core/telemetry.py`. There is no shared library package for logging; duplication is intentional so services stay independent.
2. **Audit trail level**: Business and request events (e.g., `http_request`, `tool_invoked`, policy decisions) are emitted at **INFO** level. `configure_logging()` explicitly raises the root logger from uvicorn's WARNING default to INFO so these records are never silently discarded. The default can be overridden per deployment via `LOG_LEVEL`.
3. **Structured field convention**: All business events go through `log_event`, which produces a flat JSON object with an `event` discriminator field plus arbitrary key-value fields. Fields are serialized with `sort_keys=True` and `default=str` to keep records deterministic and safe.
4. **OTLP log bridge**: When `OTEL_ENABLED=true`, `_attach_log_bridge` installs an OpenTelemetry `LoggingHandler` on the root logger at INFO level. The handler automatically attaches `trace_id`/`span_id` to records emitted inside an active span, joining logs to traces. The `opentelemetry` internal loggers are detached (`propagate = False`) to prevent recursion. Export failures are swallowed — setup errors are logged and the service continues without push.
5. **Request correlation**: `x-request-id` is the log- and portal-facing correlation key. It is generated if missing and forwarded on outbound calls. When tracing is active, it is set to the active span's W3C `trace_id`; otherwise it falls back to `req-<uuid4>`.
6. **Fail-open design**: Both `/metrics` (Prometheus, always on) and OTLP push (opt-in) are decoupled. Disabling OTel has zero overhead and leaves `/metrics` fully functional. Missing/invalid credentials produce 401s at export time; batch processors drop telemetry on failure.
7. **Metric naming** (related observability surface): `<service>_<noun>_<unit>` snake_case counters with `_total` suffix, using bounded enum labels only (never raw URLs, user ids, session ids, or request ids as labels).

## Conventions and constraints

- **All business/request events must use `log_event`**, not direct `LOGGER.info(...)` string formatting, so they remain structured JSON with a stable `event` discriminator.
- **Root logger level defaults to INFO**; deployments may raise it via `LOG_LEVEL` but must not lower it below INFO because audit records would be dropped.
- **No unbounded label cardinality** on metrics: never label on raw request URL, user id, session id, or request id (enforced by review per the conventions doc).
- **OTLP endpoint and auth** are supplied via `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_EXPORTER_OTLP_HEADERS`; secrets are provisioned via runtime-secrets (e.g., `sync-otel-secrets.sh`) and never committed.
- **`x-request-id` must never be silently dropped** on inbound requests; it is preserved and forwarded across service boundaries.
- **Tracing inactive fallback**: when tracing is off, `x-request-id` falls back to a generated `req-<uuid4>` so correlation still works.
- **Log bridge is a mirror, not a replacement**: container stdout JSON remains the canonical audit source; OTLP logs exist solely for trace correlation in the backend.