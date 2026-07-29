# Observability Conventions

## Purpose

Define the metrics, tracing, and request-correlation conventions that all platform services follow, so that signal from `tool-gateway`, `identity-broker`, and `agent-platform` is consistent, joinable, and stable enough for a future shared SDK or backend migration.

These conventions back `SPEC-005` (observability baseline).

## Two Surfaces

Each service exposes two deliberately decoupled observability surfaces:

1. **`/metrics` (pull, always on)** — a collector-independent Prometheus endpoint for debugging and health. Works with no external infrastructure. Implemented with `prometheus-fastapi-instrumentator`.
2. **OpenTelemetry push (opt-in)** — traces and metrics pushed via OTLP to the configured collector (the Elastic APM backend in this organization). Gated by `OTEL_ENABLED`; off by default; fails open.

The two never depend on each other: disabling OTel push leaves `/metrics` fully functional.

## Metric Naming

- format: `<service>_<noun>_<unit>`, snake_case
- counters carry the `_total` suffix (Prometheus convention)
- the `<service>` prefix is the short service name: `gateway`, `identity`, `agent`

Examples:

- `gateway_policy_decisions_total{action,decision}`
- `gateway_token_verification_total{result}`
- `identity_tokens_issued_total`
- `agent_sessions_created_total`, `agent_chat_requests_total`

## Standard Labels

- HTTP RED metrics (from the instrumentator): `method`, `handler` (the templated route, e.g. `/api/v1/sessions/{session_id}`), `status`
- domain counters use **bounded enum labels only** (e.g. `decision` ∈ {allow, deny}; `result` ∈ {valid, invalid, expired, missing})

## Cardinality Rules

Never use an unbounded value as a label. In particular, do **not** label on:

- raw request URL (use the templated `handler`)
- user id / subject
- session id
- request id

High-cardinality labels explode storage and query cost and are rejected at review.

## OpenTelemetry Switch Semantics

OTel push is controlled by standard-aligned environment variables:

- `OTEL_ENABLED` — master gate, default `false`. When false, no OTel providers or instrumentation are initialized (zero overhead) and `/metrics` is unaffected. One switch gates the full signal (traces + metrics); there are no per-signal toggles.
- `OTEL_EXPORTER_OTLP_ENDPOINT` — the collector / APM OTLP endpoint URL.
- `OTEL_SERVICE_NAME` — the resource service name; defaults to the service's metadata name.

Fail-open guarantee: an unreachable or misconfigured collector must never break a request. OTel batch processors drop telemetry on export failure; service setup additionally guards initialization and logs rather than raising.

## Request Correlation And Trace Bridging

- `x-request-id` is the **log- and portal-facing** correlation key. It is generated if absent (preserving the existing portal contract) and forwarded on every outbound service-to-service call.
- `traceparent` (W3C Trace Context) is the **machine-facing** propagation header, managed automatically by OpenTelemetry instrumentation across service hops.
- Bridging rule: when tracing is active, `x-request-id` is set to the active span's W3C `trace_id` (32 hex chars), so a single value joins structured logs and APM traces. When tracing is inactive, `x-request-id` falls back to a generated `req-<uuid4>`.
- No service may silently drop an inbound correlation id.

## Relationship To Backends

Services only *expose* `/metrics` and *push* OTLP. Scraping infrastructure, metrics/traces storage, dashboards, and alerting (Prometheus server, Grafana, Elastic dashboards) are platform-ops concerns outside the service contract. The Elastic stack is the organization's observability platform; OTLP is its first-class ingestion path.
