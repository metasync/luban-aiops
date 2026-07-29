# SPEC-005: Observability Baseline — Metrics, Tracing, And Request Correlation

## Status

- status: `delivered`
- owner: workspace maintainers
- created: 2026-07-28
- delivered: 2026-07-28
- release slice: `Release 1` (operability before scale)
- related risks: E1 (no metrics or distributed tracing — the platform is unobservable)

## Summary

Give every service two decoupled observability surfaces. First, an always-on, collector-independent `GET /metrics` Prometheus endpoint (RED metrics + security-arc domain counters) that works with zero external infrastructure. Second, an opt-in OpenTelemetry push pipeline — traces and metrics via OTLP to the Elastic APM backend — gated by `OTEL_ENABLED`, fail-open, off by default. Request correlation keeps the existing `x-request-id` contract and bridges it to the W3C `trace_id` when tracing is active, so one value joins logs and APM traces. This is the instrumentation safety net that de-risks the stateful work that follows (C1 session durability).

## Motivation

The platform currently logs well but measures nothing:

- all three products emit structured JSON logs via an identical `log_event` helper, but there is **no `/metrics` endpoint anywhere** — no request rate, error rate, or latency histograms
- SPEC-003 (identity) and SPEC-004 (policy) record decisions only as log lines; there is no way to chart "policy denials per minute" without log parsing
- `x-request-id` correlation is generated at the gateway but **not forwarded consistently** downstream, so a request cannot be traced across all three services
- there is **no distributed tracing** — agent-platform's OpenTelemetry libraries are transitive (via agentscope), nothing wired in

The organization standardizes on the **Elastic stack** for observability, and an Elastic APM / OTLP collector is available in the dev environment. Elastic's first-class ingestion path is OTLP-native (traces + metrics + logs unified), so the platform should push OTel signal to Elastic rather than rely on Prometheus scraping alone.

## Decision: Dual Surface — Always-On `/metrics` Plus Opt-In OTel Push

Two surfaces with different lifecycles, deliberately decoupled:

- **`/metrics` (pull, always on):** collector-independent debug/health surface via `prometheus-fastapi-instrumentator`. Works in CI, in a bare cluster, and when Elastic is down. Carries RED metrics plus security-arc domain counters.
- **OTel push (opt-in):** `opentelemetry-instrumentation-fastapi` auto-instrumentation emits traces + metrics via an OTLP exporter to the configured Elastic endpoint. Gated by `OTEL_ENABLED` (default `false`); when disabled, no pipeline is initialized (zero overhead) and `/metrics` is unaffected. Fails open — an unreachable collector drops telemetry without affecting requests.

Correlation rule (resolved): `x-request-id` remains the human/log-facing correlation key and portal contract; when tracing is active it **equals the W3C `trace_id`**, and `traceparent` is the machine-facing propagation header managed by OTel. One switch (`OTEL_ENABLED`) gates the full signal (traces + metrics), not per-signal toggles.

## Requirements

### R-1: `/metrics` debug surface on every service

Each service exposes an always-on Prometheus endpoint, independent of any collector.

Acceptance criteria:

- `tool-gateway`, `identity-broker`, and `agent-platform` each expose `GET /metrics` in Prometheus exposition format, always enabled regardless of `OTEL_ENABLED`
- the endpoint is exempt from authentication and policy enforcement (platform plumbing, like `/health/*`)
- standard HTTP RED metrics registered via `prometheus-fastapi-instrumentator`: request count and duration histogram labeled by `method`, templated `path` (bounded cardinality), and `status`
- each `pyproject.toml` gains `prometheus-fastapi-instrumentator`
- the endpoint is documented in each product README

### R-2: Domain counters for the security arc

SPEC-003/004 decisions become queryable metrics on the `/metrics` surface.

Acceptance criteria:

- gateway counters: `gateway_policy_decisions_total{action,decision}`, `gateway_token_verification_total{result}` (result: `valid` | `invalid` | `expired` | `missing`)
- counters increment at the existing `enforce_policy` and `resolve_request_identity` call sites — metrics and audit logs stay co-located
- identity-broker: `identity_tokens_issued_total`
- agent-platform: `agent_sessions_created_total`, `agent_chat_requests_total`
- names/labels follow the R-5 conventions

### R-3: Opt-in OpenTelemetry push pipeline

Traces and metrics push to the configured collector, gated and fail-open.

Acceptance criteria:

- a shared bootstrap (per service) initializes the OTel SDK only when `OTEL_ENABLED=true`; when false, nothing is initialized and `/metrics` is unaffected
- configuration: `OTEL_ENABLED` (default `false`), `OTEL_EXPORTER_OTLP_ENDPOINT` (collector URL), `OTEL_SERVICE_NAME` (defaults to each service's metadata name) — aligned with standard OTel env conventions
- `opentelemetry-instrumentation-fastapi` provides auto traces + metrics; the OTLP exporter ships to the endpoint
- the pipeline **fails open**: exporter/connection errors are swallowed by the SDK and never break a request
- one master switch gates the full signal (traces + metrics); no per-signal toggles in this slice
- when disabled, the app behaves exactly as before this spec (no OTel overhead)

### R-4: Request correlation and trace bridging

A request is correlatable across all three services in logs and, when enabled, in the APM.

Acceptance criteria:

- `x-request-id` remains the log/portal-facing correlation key; generated if absent (preserves the existing contract)
- when OTel is active, `x-request-id` is set to the active span's W3C `trace_id`; when inactive, it falls back to a generated UUID
- OTel auto-propagates `traceparent` on outbound calls between the three services (no manual per-hop code)
- the gateway still forwards `x-request-id` for log readability on all outbound calls
- no service silently drops an inbound correlation id

### R-5: Observability conventions in shared-contracts

Acceptance criteria:

- a new `observability-conventions.md` documents: metric naming (`<service>_<noun>_<unit>`), the standard label set, bounded-cardinality `path` rules, the `OTEL_*` switch semantics, and the `x-request-id` ↔ `trace_id` bridging rule
- the doc is the single reference all three implementations cite (stable target for a future shared SDK)

### R-6: Tests and CI enforcement

Acceptance criteria:

- each product: `GET /metrics` returns `200`, `text/plain`, and contains expected standard metric names — with `OTEL_ENABLED` both unset and set
- gateway: domain counters increment on a policy decision and on token verification (Prometheus registry asserted directly)
- OTel: push disabled by default emits nothing; enabled emits to a mocked/in-memory OTLP exporter; `/metrics` unaffected by the switch; fail-open on unreachable collector (request still succeeds)
- correlation: `x-request-id` forwarded on outbound calls and equals `trace_id` when tracing is active, UUID when not
- SPEC-001/002/003/004 regression suites pass; CI green for all three products
- both dev Kustomize overlay bases render (Prometheus scrape annotations + `OTEL_*` env entries, defaulting `OTEL_ENABLED=false`)

## Non-Goals

- metrics/traces storage, dashboards, or alerting (Grafana, Elastic dashboards, Prometheus server) — services only *expose* and *push*; backend provisioning is platform-ops
- log shipping to Elastic (OTel log export / Filebeat) — structured stdout logging stays; only log-to-trace correlation via trace_id is in scope
- a shared observability SDK in `shared/shared-sdk` — conventions documented now; code extraction waits for three real implementations
- per-signal OTel toggles (traces vs metrics separately) — one master switch this slice
- business/agent-level telemetry (tool invocation counts, provider latency) — platform RED + security-arc counters only

## Impact

- products touched: `tool-gateway`, `identity-broker`, `agent-platform` (metrics endpoint, domain counters, OTel bootstrap, correlation bridging)
- contracts touched: new `observability-conventions.md` in `shared/shared-contracts`
- dependencies added: `prometheus-fastapi-instrumentator` (all three); `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-exporter-otlp` (all three)
- deployment impact: dev overlays gain Prometheus scrape annotations and `OTEL_*` env entries (`OTEL_ENABLED=false` default, `OTEL_EXPORTER_OTLP_ENDPOINT` placeholder)
- living state docs to update on delivery: root `README.md`, each product `README.md`, `shared/shared-contracts/README.md`, `CHANGELOG.md`

## Open Questions

None — all resolved (see Changelog).

## Changelog

- 2026-07-28: created as `draft` addressing risk E1
- 2026-07-28: reframed after Elastic-stack clarification — resolved: (1) single `OTEL_ENABLED` switch gates the full signal (traces + metrics), no per-signal toggles; (2) keep `x-request-id` (Option A): it remains the log/portal correlation key and equals the W3C `trace_id` when tracing is active, with `traceparent` as the OTel-managed propagation header; the "defer tracing" non-goal is removed — tracing is in scope via the opt-in OTel push pipeline, while `/metrics` stays as an always-on collector-independent debug surface; status → `approved`
- 2026-07-28: delivered — all acceptance criteria verified; test suites green for `tool-gateway` (57 passed), `identity-broker` (21 passed), and `agent-platform` (53 passed); both dev Kustomize overlay bases render (Prometheus scrape annotations + `OTEL_*` env entries). Implementation deviation from approved spec: the `/metrics` surface is implemented directly with `prometheus_client` rather than `prometheus-fastapi-instrumentator` — the instrumentator's routing introspection is incompatible with the pinned starlette version (`AttributeError: '_IncludedRouter' object has no attribute 'path'`). Behavior is equivalent (standard RED metrics with templated route-path handler labels + bounded cardinality, `/metrics` auth/policy exempt); the `prometheus-fastapi-instrumentator` requirement wording in R-1/R-2 acceptance criteria will be reconciled in a follow-up spec.
