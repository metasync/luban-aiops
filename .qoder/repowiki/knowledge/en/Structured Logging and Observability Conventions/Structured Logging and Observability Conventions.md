---
kind: logging_system
name: Structured Logging and Observability Conventions
category: logging_system
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
    - products/agent-platform/src/agent_service/core/observability.py
    - products/tool-gateway/src/api_gateway/core/observability.py
    - products/identity-broker/src/identity_service/core/observability.py
    - products/agent-platform/src/agent_service/core/telemetry.py
    - products/tool-gateway/src/api_gateway/core/telemetry.py
    - products/identity-broker/src/identity_service/core/telemetry.py
    - products/agent-platform/src/agent_service/core/request_context.py
    - products/tool-gateway/src/api_gateway/core/request_context.py
    - products/agent-platform/src/agent_service/app.py
    - products/tool-gateway/src/api_gateway/app.py
    - products/identity-broker/src/identity_service/app.py
---

The Luban AIOps platform uses Python's standard `logging` module for all log output, with a consistent structured-logging pattern enforced across every service. There is no third-party logging framework (no structlog, loguru, or logzero); instead, each service defines an identical `core/observability.py` helper that serializes logs as JSON.

**Framework and initialization**
- Each service (`agent-platform`, `identity-broker`, `tool-gateway`) creates a module-level logger via `LOGGER = logging.getLogger(__name__)` in its `app.py` entry point.
- No global `basicConfig` or custom formatter is configured at the repository level; log formatting and sinks are expected to be provided by the runtime environment (e.g., container stdout/stderr consumed by Kubernetes/Elastic). The codebase does not configure handlers, levels, or formatters itself.

**Structured log format**
- All business and request-scoped events go through a shared `log_event(logger, event, **fields)` function defined identically in each service's `core/observability.py`. It builds a dict `{"event": event, **fields}` and emits it via `logger.info(json.dumps(payload, default=str, sort_keys=True))`, producing single-line JSON objects with sorted keys.
- Every HTTP request is logged through this helper from a FastAPI middleware that records `service`, `request_id`, `method`, `path`, `status_code`, and `duration_ms`.

**Request correlation and trace bridging**
- Each service exposes a `core/request_context.py` with a `resolve_request_id(request_id)` function that implements the SPEC-005 R-4 rule: inbound `x-request-id` wins; if absent, the active OTel `trace_id` is used when tracing is enabled; otherwise a `req-<uuid4>` fallback is generated.
- `core/telemetry.py` provides `current_trace_id()` which reads the active W3C `traceparent` span id when OpenTelemetry is enabled, enabling the bridge between structured logs and traces.

**OpenTelemetry integration (opt-in)**
- Telemetry push is gated by the `OTEL_ENABLED` environment variable (default false). When disabled, no OTel providers are initialized and there is zero overhead.
- When enabled, each service sets up a TracerProvider with a BatchSpanProcessor exporting via OTLP gRPC, a MeterProvider with PeriodicExportingMetricReader, and instruments both FastAPI and HTTPX clients.
- Fail-open semantics: setup exceptions are caught and logged via `LOGGER.exception(...)` rather than raised, so a misconfigured collector never breaks requests.

**Conventions documented in shared contracts**
- `shared/shared-contracts/observability-conventions.md` codifies the two-surface model: `/metrics` (Prometheus, always on) and OTLP push (opt-in). It also enforces metric naming (`<service>_<noun>_<unit>`), bounded labels, cardinality rules (no high-cardinality labels like raw URLs, user ids, session ids, request ids), and the `x-request-id` / `traceparent` bridging rule.
- Services only expose `/metrics` and push OTLP; scraping infrastructure and dashboards are platform-ops concerns outside the service contract.

**Observed usage patterns**
- Direct `LOGGER.info(...)`, `LOGGER.warning(...)`, and `LOGGER.exception(...)` calls are used throughout services for operational messages (e.g., JWT key loading, tool registration, policy decisions).
- Business events consistently use `log_event(LOGGER, "<event_name>", ...)` to produce structured JSON lines.
- No per-service log level configuration was found in the code; log severity is controlled through the standard `logging` level hierarchy.