# SPEC-005 Tasks: Observability Baseline

Task states: `[ ]` pending, `[x]` done. Implementation starts when the spec is `approved`.

## R-5: Observability conventions in shared-contracts

- [x] create `shared/shared-contracts/observability-conventions.md` (naming, labels, cardinality, OTEL_* switch, correlation bridging)
- [x] link the conventions doc from `shared/shared-contracts/README.md`

## R-1 + R-2: tool-gateway `/metrics` + domain counters

- [x] add `prometheus-client` to `products/tool-gateway/pyproject.toml` (direct use; `prometheus-fastapi-instrumentator` proved incompatible with the pinned starlette — see spec changelog)
- [x] create `core/metrics.py`: `gateway_policy_decisions_total{action,decision}`, `gateway_token_verification_total{result}` + record helpers
- [x] wire `setup_metrics(app)` middleware + `GET /metrics` in `app.py`
- [x] increment counters in `enforce_policy` and token verification paths

## R-3 + R-4: tool-gateway OTel push + correlation

- [x] add OTel deps (`opentelemetry-sdk`, `-instrumentation-fastapi`, `-instrumentation-httpx`, `-exporter-otlp`)
- [x] create `core/telemetry.py`: `setup_telemetry()` gated on `OTEL_ENABLED`, fail-open; `is_enabled()`
- [x] bridge `resolve_request_id` to W3C `trace_id` when tracing active
- [x] verify `x-request-id` forwarded uniformly on all outbound calls

## R-1 + R-2: identity-broker `/metrics` + counters

- [x] add `prometheus-client` to `products/identity-broker/pyproject.toml`
- [x] create `core/metrics.py`: `identity_tokens_issued_total` + record helper
- [x] wire `/metrics` in `app.py`; increment counter on token issuance

## R-3 + R-4: identity-broker OTel + correlation

- [x] add OTel deps; create `core/telemetry.py`; call from `create_app`
- [x] correlation: read/generate `x-request-id`, bridge to trace_id

## R-1 + R-2: agent-platform `/metrics` + counters

- [x] add `prometheus-client` to `products/agent-platform/pyproject.toml`
- [x] create `core/metrics.py`: `agent_sessions_created_total`, `agent_chat_requests_total` + helpers
- [x] wire `/metrics` in `app.py`; increment counters in the v2 service layer

## R-3 + R-4: agent-platform OTel + correlation

- [x] add OTel deps; create `core/telemetry.py`; call from `create_app`
- [x] bridge `resolve_request_id` to trace_id when tracing active

## R-6: Tests + overlays + CI

- [x] per-service `tests/test_observability.py`: `/metrics` 200 + content (OTEL unset and set)
- [x] gateway: counter-increment, correlation-bridge, fail-open tests
- [x] overlays: Prometheus scrape annotations + `OTEL_*` env (default off) in both dev bases (`shared/observability.env` merged into the shared `platform-runtime-config` ConfigMap)
- [x] verify CI green for all three products; both overlay bases render

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified
- [x] living state docs updated (root README, three product READMEs, shared-contracts README)
- [x] `CHANGELOG.md` entry added referencing `SPEC-005`
- [x] spec index in `docs/specs/README.md` updated
- [x] spec status set to `delivered`
