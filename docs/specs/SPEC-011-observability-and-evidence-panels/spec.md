# SPEC-011: Observability Connector and Evidence Panels

## Status

- status: `delivered`
- owner: workspace maintainers
- created: 2026-08-05
- release slice: `R1` (read-only operations copilot)
- related ADRs: ADR-0002 (AgentScope runtime kernel), ADR-0003 (platform-owned agent service contract)

## Summary

Add an Elastic observability connector to the tool-gateway, extend the agent stream contract with tool trace events, and render an evidence panel in the operator portal — completing the R1 vision of grounded, evidence-backed operational answers.

## Motivation

SPEC-007 through SPEC-010 delivered a fully wired read-only tool execution pipeline: four Kubernetes tools, policy enforcement, identity delegation, deterministic redaction, and audit logging. The agent can observe infrastructure state and the LLM incorporates tool results into its responses. However, three gaps prevent the platform from meeting the R1 completion signal ("operators say the platform is useful for real status and diagnostic questions"):

1. **Single data source**: only Kubernetes is observable. Operators asking "why is service X throwing errors?" need log and metric data from the observability platform (Elastic), not just pod status. The SPEC-007 non-goals explicitly deferred observability connectors to a follow-up spec within R1.

2. **Opaque tool usage**: when the LLM invokes tools, the operator sees only the final text response. There is no visibility into which tools were called, what parameters were used, what data was returned, or how long execution took. The evidence metadata (`executed_at`, `duration_ms`, `risk_level`, `source_system`) is computed and transmitted to the LLM but never surfaces to the human.

3. **No evidence rendering**: the operator portal renders streamed text deltas only. Tool results, evidence provenance, and risk-level signals are invisible — the operator cannot verify that the platform used the correct data sources, which is a key R1 validation criterion.

## Requirements

### R-1: Stream event contract extension for tool traces

The `agent-stream-event.schema.json` contract gains two new event types so tool invocations are visible in the stream.

Acceptance criteria:

- `agent-stream-event.schema.json` adds `tool_call` and `tool_result` to the `type` enum (alongside existing `message_start`, `message_delta`, `message_end`, `error`)
- `tool_call` events carry: `tool_name` (string), `parameters` (object, the LLM-supplied parameters), `call_id` (string, unique within the request, used to correlate with the matching `tool_result`)
- `tool_result` events carry: `tool_name` (string), `call_id` (string, matching the `tool_call`), `status` (`success` | `error` | `denied`), `evidence` (object per `tool-result.schema.json` evidence: `executed_at`, `duration_ms`, `risk_level`, `source_system`), `data_summary` (object or null, a condensed view of the tool result suitable for UI rendering — not the full payload which may be large), `error` (object or null: `code`, `message`)
- both new event types carry `session_id` and `request_id` (existing required fields)
- `additionalProperties: false` is preserved; the schema documents that `tool_call` and `tool_result` frames use optional properties not present on text frames

### R-2: Tool trace emission from the agent runtime

Gateway toolkit functions emit tool trace events so the stream carries a complete audit of tool usage alongside text deltas.

Acceptance criteria:

- a per-request `asyncio.Queue` (the "trace queue") is created when `stream_events` begins
- each gateway toolkit function closure (in `gateway_tools.py`) receives the trace queue and posts a `tool_call` event before invoking the gateway and a `tool_result` event after receiving the response
- `build_toolkit_functions` and `build_toolkit` accept and propagate the trace queue parameter
- `AgentKernel.stream_events` merges trace events from the queue with AgentScope text-delta events in chronological order, yielding both through the same `AsyncIterator`
- the merge is non-blocking: if the trace queue is empty, text events flow without delay; if text events pause (LLM processing), trace events flow immediately
- `data_summary` in `tool_result` trace events is derived by truncating large `data` payloads to a bounded size (max 2000 characters when serialized; configurable via `AGENT_TOOL_DATA_SUMMARY_MAX_CHARS`, default 2000)
- when `tool_gateway_url` is not configured (empty toolkit), no trace events are emitted (existing behavior preserved)
- the trace queue is scoped to a single stream request; it is not shared across sessions or requests

### R-3: Elastic observability connector

A second connector in the tool-gateway provides three read-only Elastic query tools, following the same connector pattern established by the Kubernetes connector.

Acceptance criteria:

- tools registered: `elastic.search_logs`, `elastic.get_service_health`, `elastic.get_active_alerts`
- `elastic.search_logs` parameters: `query` (string, required — Kibana Query Language or simple text), `index` (string, optional, default `*`), `time_range_minutes` (integer, optional, default 15, max 1440), `max_results` (integer, optional, default 50, max 200)
- `elastic.get_service_health` parameters: `service_name` (string, required), `time_range_minutes` (integer, optional, default 15, max 1440)
- `elastic.get_active_alerts` parameters: `severity` (string, optional — `critical` | `warning` | `info`, default all), `max_results` (integer, optional, default 50, max 200)
- connector uses the official `elasticsearch` Python client
- `GATEWAY_ELASTIC_ENABLED` (bool, default `false`) gates connector registration
- `GATEWAY_ELASTIC_URL` (string, required when enabled) sets the Elastic endpoint
- `GATEWAY_ELASTIC_API_KEY` (string, optional) for API-key authentication; falls back to `GATEWAY_ELASTIC_USERNAME` / `GATEWAY_ELASTIC_PASSWORD` basic auth
- `GATEWAY_ELASTIC_VERIFY_TLS` (bool, default `true`) controls TLS verification
- when the connector is not enabled or Elastic is unreachable, tools return a structured `error` result with code `ELASTIC_NOT_CONFIGURED` or `ELASTIC_CONNECTION_ERROR`
- all queries are read-only; no index write, delete, or mapping operations
- connector initializes the client lazily on first tool invocation (same pattern as K8s connector)
- `source_system` in evidence is `"elastic"`

### R-4: Operator portal evidence panel

The operator portal renders tool invocation traces in a dedicated evidence panel alongside the text response.

Acceptance criteria:

- the portal HTML gains an "Evidence" section below the Response section
- when streaming, `tool_call` events render a pending tool invocation card showing: tool name, parameters (formatted as JSON), and a loading indicator
- when the matching `tool_result` event arrives (correlated by `call_id`), the card updates to show: status badge (success/error/denied), evidence metadata (executed_at, duration_ms, risk_level, source_system), and data_summary (formatted as collapsible JSON)
- denied tool results display a distinct visual indicator (e.g., red badge) with the denial reason
- error tool results display the error code and message
- the evidence panel remains empty and hidden when a stream contains no tool invocations
- evidence cards are rendered in chronological order (by `call_id` sequence, which matches invocation order)
- the portal gracefully handles out-of-order events (a `tool_result` arriving before its `tool_call` card is rendered)

### R-5: Dev overlay configuration for observability

The dev-k8s overlay configures the Elastic connector when an Elastic endpoint is available.

Acceptance criteria:

- tool-gateway `runtime-config.env` gains `GATEWAY_ELASTIC_ENABLED`, `GATEWAY_ELASTIC_URL`, and auth settings
- in the dev overlay, `GATEWAY_ELASTIC_ENABLED=false` by default (Elastic is not deployed in the dev cluster); the configuration is present but gated off
- a commented example in `runtime-config.env` documents the settings needed to enable Elastic against an external instance
- `kustomize build` renders without errors with both enabled and disabled configurations
- policy bundle remains unchanged (the `tools:invoke` action already covers all read-only tools regardless of connector)

## Non-Goals

- write or mutating Elastic operations (indexing, deleting documents) — R4 scope
- approval workflow for observability queries — read-only, no approval needed
- Composite "service health" agent tool that internally calls multiple tools — the LLM orchestrates multi-tool reasoning through the existing toolkit
- Elastic alerting rule creation or management — out of platform scope
- Grafana, Prometheus, or Datadog connectors — future specs, same connector pattern
- Full tool result data rendering in the portal (only `data_summary` is shown; full payloads are available in audit logs)
- Historical tool trace persistence or replay — traces live for the duration of the stream only

## Impact

- products touched: `products/tool-gateway/`, `products/agent-platform/`, `products/operator-portal/`, `shared/platform-ops/gitops/dev-k8s/`
- contracts touched: `shared/shared-contracts/schemas/agent-stream-event.schema.json`
- identity / policy / audit / execution safety impact: no new policy actions; existing `tools:invoke` covers Elastic tools; tool trace events carry the same evidence as audit logs but are scoped to the stream
- living state docs to update on delivery: `products/tool-gateway/README.md`, `products/agent-platform/README.md`, `products/operator-portal/README.md`, `CHANGELOG.md`

## Open Questions

### Q-1: How much of the tool result data should the trace event carry?

Full tool payloads can be large (e.g., `k8s.list_pods` on a namespace with hundreds of pods, `elastic.search_logs` with 200 results). Sending the full payload to the browser is wasteful and may leak sensitive data that the LLM context handles differently. The proposed approach is a `data_summary` field truncated to a bounded character limit (default 2000 chars), with the full payload available only in server-side audit logs.

**Proposed resolution:** `data_summary` is `json.dumps(data)[:MAX_CHARS]` with an ellipsis marker when truncated. Operators needing full data can consult audit logs. This keeps the evidence panel useful without creating a data-exfiltration surface.

### Q-2: Should the trace queue be per-session or per-request?

A per-session queue would allow correlating tool calls across turns, but introduces lifecycle complexity (queue cleanup, stale events). A per-request queue is simpler and matches the current stream model where each request is independent.

**Proposed resolution:** per-request queue, created at `stream_events` entry, discarded when the generator exits. Cross-turn correlation is a future concern (R3 incident triage).

## Changelog

- 2026-08-05: created as `draft`
