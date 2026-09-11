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
    - products/audit-service/src/audit_service/core/observability.py
    - products/audit-service/src/audit_service/core/telemetry.py
    - products/platform-gateway/src/platform_gateway/core/telemetry.py
    - products/tool-gateway/src/tool_gateway/core/telemetry.py
---

## What system/approach is used

The platform uses Python's standard `logging` module as the sole logging framework. Every service emits **single-line JSON** records via a shared `log_event(logger, event, **fields)` helper that serializes a dict containing an `event` name plus arbitrary structured fields using `json.dumps(..., default=str, sort_keys=True)`. There is no third-party logger library (no structlog, loguru, or similar). The root logger level is raised from uvicorn's WARNING default to INFO at startup so audit-level events are never silently dropped; the effective level can be overridden per deployment via the `LOG_LEVEL` environment variable.

For distributed tracing correlation, each service initializes an opt-in OpenTelemetry push pipeline (`setup_telemetry`) that attaches an OTel `LoggingHandler` to the root logger. When enabled, every structured record emitted to stdout is also mirrored over OTLP HTTP/protobuf to the configured backend (OpenObserve), automatically associating logs with the active span's `trace_id`/`span_id`. The bridge is guarded by `OTEL_ENABLED`; when disabled, zero OTel providers are initialized and there is no overhead. Exporter failures cannot recurse back into the bridge because `logging.getLogger("opentelemetry").propagate = False` is set.

## Key files and packages

- `shared/shared-contracts/observability-conventions.md` — authoritative specification of the logging, metrics, tracing, and request-correlation conventions all services must follow (SPEC-005).
- `products/*/src/<service>/core/observability.py` — per-service `configure_logging()` and `log_event()` helpers (agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway each ship their own copy).
- `products/*/src/<service>/core/telemetry.py` — per-service identical OTel initialization: `is_enabled()`, `_attach_log_bridge()`, `setup_telemetry(app, service_name)`, `current_trace_id()`.
- `products/*/src/<service>/app.py` — FastAPI app factory that calls `configure_logging()`, installs an HTTP middleware emitting `http_request` events via `log_event`, then calls `setup_metrics` and `setup_telemetry`.
- `products/*/src/<service>/api/routes/*.py` — route handlers emit domain events (e.g. `tool_invoked`, `policy_decision`, `session_created`) through `log_event`.

## Architecture and conventions

1. **Per-service observability modules.** Each product ships its own `core/observability.py` and `core/telemetry.py`. The implementations are intentionally duplicated rather than shared via a package, so each service can be built and deployed independently while still following the same contract.
2. **Structured event model.** Business and request events are logged as one JSON line per call with a required `event` field (e.g. `http_request`, `tool_invoked`, `policy_decision`, `session_created`). Fields are passed as keyword arguments and merged into the payload; values are coerced to strings via `default=str` so non-serializable objects do not break emission.
3. **Log levels.** INFO is the audit baseline. Uvicorn's root logger starts at WARNING; `configure_logging()` raises it to INFO (or whatever `LOG_LEVEL` specifies). DEBUG/ERROR/etc. are available on the stdlib logger but the audit trail lives at INFO.
4. **Request correlation.** A middleware in each service resolves `x-request-id` (generated if absent, forwarded on outbound calls) and includes it in every `http_request` event. When tracing is active, `x-request-id` is bridged to the active W3C `trace_id`; when inactive it falls back to `req-<uuid4>`.
5. **Two decoupled surfaces.** `/metrics` (Prometheus, always-on, implemented directly with `prometheus_client`) and OTLP push (opt-in via `OTEL_ENABLED`). Disabling OTel has zero effect on metrics or stdout logging.
6. **Fail-open telemetry.** `setup_telemetry` wraps provider initialization in try/except; any exception is logged and the service continues without push. Missing credentials produce export-time 401s that batch processors drop.
7. **No unbounded label/cardinality leakage into logs.** The conventions forbid labeling raw URLs, user ids, session ids, or request ids as metric labels; the same principle applies to log fields that could explode cardinality.
8. **Source-of-truth rule.** JSON stdout remains the canonical audit trail; the OTLP mirror exists only for backend correlation and must never replace stdout consumption.

## Conventions and constraints

- Every service must call `configure_logging()` during app creation before any business code runs.
- All business/request events must go through `log_event(logger, "<event_name>", ...)` — direct `logger.info(json.dumps(...))` calls bypass the convention and are discouraged.
- `OTEL_ENABLED` is the single master switch for traces + metrics + log mirror; there are no per-signal toggles.
- `OTEL_EXPORTER_OTLP_ENDPOINT` points to the org prefix (exporters append `/v1/traces`, `/v1/metrics`, `/v1/logs`); authentication is supplied via `OTEL_EXPORTER_OTLP_HEADERS` provisioned from runtime secrets.
- `OTEL_SERVICE_NAME` defaults to the service's metadata name and becomes the resource attribute attached to all signals.
- No service may silently drop an inbound `x-request-id`; it must be preserved and forwarded on all outbound calls.
- Metric names follow `<service>_<noun>_<unit>` snake_case with counters suffixed `_total`; labels must be bounded enums.
- High-cardinality values (raw URL, user id, session id, request id) must never be used as metric labels.
- The `opentelemetry` internal logger is detached from the root logger to prevent recursion between the bridge and the exporter.