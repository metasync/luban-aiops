# SPEC-005 Plan: Observability Baseline

> Finalized 2026-07-28 alongside spec approval; open questions resolved in the spec changelog.

## Approach

Work contract-first (R-5 conventions), then implement the two surfaces per service in dependency order: the always-on `/metrics` surface + domain counters (R-1/R-2), then the opt-in OTel push pipeline + correlation bridging (R-3/R-4). Each service gets an identical `core/telemetry.py` bootstrap so the three implementations stay dialect-free. Tests and overlays (R-6) land alongside.

## Design Per Requirement

### R-5: Observability conventions (shared-contracts)

- new `shared/shared-contracts/observability-conventions.md`:
  - metric naming: `<service>_<noun>_<unit>` (e.g. `gateway_policy_decisions_total`), `_total` suffix for counters
  - standard labels: RED metrics use `method`, `handler`/templated `path`, `status`; domain counters use bounded enum labels only
  - bounded cardinality: never label on raw URL, user id, or session id
  - `OTEL_*` switch semantics: `OTEL_ENABLED` master gate (default false), `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`
  - correlation: `x-request-id` is the log/portal key; equals W3C `trace_id` when tracing active; `traceparent` is OTel-managed
- shared-contracts README links the new doc

### R-1 + R-2: `/metrics` surface + domain counters (per service)

- affected: each `pyproject.toml`, each `app.py`, a new `core/metrics.py` per service
- dependency: `prometheus-fastapi-instrumentator>=6.0,<8.0`
- `core/metrics.py` defines the service's domain counters as module-level `prometheus_client.Counter` objects and small `record_*` helpers
- `app.py`: `Instrumentator().instrument(app).expose(app, endpoint="/metrics")` — always on, independent of OTel
  - the instrumentator uses the templated route for the `handler` label (bounded cardinality)
- gateway counters: `gateway_policy_decisions_total{action,decision}` (incremented in `enforce_policy`), `gateway_token_verification_total{result}` (incremented in `resolve_request_identity`: valid/invalid/expired/missing)
- identity-broker: `identity_tokens_issued_total` (incremented where `issue_token` succeeds)
- agent-platform: `agent_sessions_created_total`, `agent_chat_requests_total` (incremented in the v2 service layer)

### R-3: Opt-in OTel push pipeline (per service)

- affected: new `core/telemetry.py` per service, called from `create_app`
- dependencies: `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-exporter-otlp`
- `setup_telemetry(app, service_name)`:
  - read `OTEL_ENABLED` (default false). If false → return immediately (no providers, no instrumentation, zero overhead, `/metrics` untouched)
  - if true → configure `TracerProvider` with `BatchSpanProcessor(OTLPSpanExporter(endpoint))` and `MeterProvider` with `PeriodicExportingMetricReader(OTLPMetricExporter(endpoint))`; set global providers; `FastAPIInstrumentor.instrument_app(app)`; resource carries `service.name` from `OTEL_SERVICE_NAME` (default the service metadata name)
  - all exporter init wrapped so a bad/unreachable endpoint never raises into the request path (OTel batch processors already fail open; we additionally guard setup in try/except and log)
- `is_enabled()` helper for the correlation bridge

### R-4: Correlation + trace bridging

- affected: each `core/request_context.py` (gateway + agent-platform have one; identity-broker inlines it in app.py)
- `resolve_request_id(header_value)`:
  - if header present → use it (preserve contract)
  - elif OTel active and a current span exists with a valid trace_id → use the 32-hex `trace_id`
  - else → generate `req-<uuid4>`
- gateway already forwards `x-request-id` on outbound calls via `_service_headers`; verify agent_client does too and make uniform
- OTel `FastAPIInstrumentor` + httpx instrumentation auto-propagate `traceparent` on outbound httpx calls (add `opentelemetry-instrumentation-httpx` so gateway→backend hops carry the trace)

### R-6: Tests + overlays

- per service `tests/test_observability.py`: `/metrics` 200 + `text/plain` + expected metric names, with `OTEL_ENABLED` unset and set
- gateway `test_observability.py` also: counter increments via registry inspection; correlation bridge (trace_id when active, uuid when not); fail-open with unreachable endpoint
- OTel tests use `InMemorySpanExporter` / direct provider inspection rather than a real collector
- overlays: both dev bases gain `prometheus.io/scrape: "true"`, `prometheus.io/port: "8000"`, `prometheus.io/path: "/metrics"` annotations on the service/deployment pod templates, plus `OTEL_ENABLED=false` (+ commented endpoint placeholder) in each `runtime-config.env`
- regression: all three suites + `kustomize build` for both bases

## Sequencing And Dependencies

1. R-5 conventions doc — no dependencies
2. R-1/R-2 per service (metrics + counters) — depends on 1 for naming
3. R-3/R-4 per service (OTel + correlation) — depends on 2 (same app bootstrap)
4. R-6 tests + overlays — alongside 2 and 3

## Test Strategy

- unit: counter helpers, correlation bridge branches, telemetry gating (enabled vs disabled)
- integration: TestClient `/metrics` content; OTel in-memory exporter captures a span when enabled
- fail-open: point OTLP endpoint at a closed port, assert requests still succeed
- regression: full suites for all three products + overlay render

## Rollout And Migration

- `OTEL_ENABLED` defaults to false → deploying changes nothing operationally until the switch is flipped; overlays ship it off with a commented endpoint placeholder
- `/metrics` is additive and unauthenticated (platform plumbing) — no behavior change to existing routes
- rollback: revert the dependency + bootstrap; existing logging is untouched throughout
