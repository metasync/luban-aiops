# SPEC-011 Plan: Observability Connector and Evidence Panels

## Approach

The work divides into three independent tracks that converge at the end:

1. **Contract + trace emission** (R-1, R-2): extend the stream event schema, wire toolkit functions to emit tool trace events via a per-request queue, and merge traces into the SSE stream in the runtime kernel.
2. **Elastic connector** (R-3, R-5): a new connector in tool-gateway following the proven K8s connector pattern — lazy client init, executor-based sync calls, feature-gated registration.
3. **Portal evidence panel** (R-4): parse `tool_call`/`tool_result` stream events and render evidence cards in the portal UI.

Tracks 1 and 3 can proceed in parallel (the portal can be developed against mock events). Track 2 is fully independent until integration testing.

## Design Per Requirement

### R-1: Stream event contract extension for tool traces

- affected files: `shared/shared-contracts/schemas/agent-stream-event.schema.json`
- chosen approach: extend the existing schema's `type` enum with `tool_call` and `tool_result`; add optional properties gated by `oneOf` or `if/then` to keep `additionalProperties: false` enforced
- the `tool_call` frame adds `tool_name`, `parameters`, `call_id`; the `tool_result` frame adds `tool_name`, `call_id`, `status`, `evidence`, `data_summary`, `error`
- alternatives considered: (a) a separate `tool-trace-event.schema.json` alongside the stream event schema — rejected because the portal already parses one schema and splitting creates two contracts to validate; (b) embedding tool traces inside `message_delta` as structured deltas — rejected because it conflates text rendering with tool auditing and breaks the portal's simple delta-appending logic

### R-2: Tool trace emission from the agent runtime

- affected files:
  - `products/agent-platform/src/agent_service/tools/gateway_tools.py` — toolkit functions post to the trace queue
  - `products/agent-platform/src/agent_service/runtime_kernel.py` — `stream_events` creates the queue, merges traces with text events
  - `products/agent-platform/src/agent_service/runtime_settings.py` — new `AGENT_TOOL_DATA_SUMMARY_MAX_CHARS` setting
- chosen approach: a per-request `asyncio.Queue` is created inside `stream_events`. The queue is passed down through `_ensure_toolkit` → `build_toolkit` → `build_toolkit_functions` → each closure. The closure posts `tool_call` before `await invoke_gateway_tool()` and `tool_result` after. `stream_events` uses `asyncio.create_task` to drain the queue and `yield` events in order alongside AgentScope text deltas.
- merge algorithm: wrap the AgentScope `reply_stream` async iterator and the trace queue in `asyncio.wait` with `FIRST_COMPLETED`; yield whichever event arrives first. When the AgentScope iterator completes, drain any remaining trace events.
- alternatives considered: (a) yield tool traces as a post-processing step after the full response — rejected because operators want real-time visibility; (b) emit traces via a separate SSE endpoint — rejected because it doubles the connection count and introduces ordering issues

### R-3: Elastic observability connector

- affected files:
  - `products/tool-gateway/src/tool_gateway/tools/elastic_connector.py` (new) — `ElasticConnector` class with three tool classes
  - `products/tool-gateway/src/tool_gateway/services/gateway_service.py` — register Elastic tools when enabled
  - `products/tool-gateway/src/tool_gateway/runtime_settings.py` — new Elastic settings
- chosen approach: mirror the `KubernetesConnector` pattern exactly:
  - `ElasticConnector` class with lazy `_ensure_client()` returning bool
  - Three `BaseTool` subclasses: `SearchLogsTool`, `GetServiceHealthTool`, `GetActiveAlertsTool`
  - Sync Elastic calls run in `asyncio.get_running_loop().run_in_executor()`
  - Feature gate: `GATEWAY_ELASTIC_ENABLED` (default `false`)
  - Auth: API key preferred (`GATEWAY_ELASTIC_API_KEY`), basic auth fallback (`GATEWAY_ELASTIC_USERNAME`/`GATEWAY_ELASTIC_PASSWORD`)
  - TLS verification toggle: `GATEWAY_ELASTIC_VERIFY_TLS`
- `elastic.search_logs` runs a `bool` query with `query_string` + `range` filter on `@timestamp`, returns hits capped by `max_results`
- `elastic.get_service_health` aggregates on `service.name` (ECS field), computing `error_rate` (errors / total), `avg_latency_ms`, and `request_count` over the time range
- `elastic.get_active_alerts` queries an alerts index pattern (configurable via `GATEWAY_ELASTIC_ALERTS_INDEX`, default `.alerts-*`) sorted by severity and recency
- alternatives considered: (a) OpenTelemetry query protocol instead of Elastic-specific — rejected because OTLP is a push protocol, not a query API; the platform needs a pull/query interface; (b) generic "observability" abstraction layer — rejected as premature; one connector first, abstract when a second arrives

### R-4: Operator portal evidence panel

- affected files:
  - `products/operator-portal/web-ui/index.html` — add Evidence section
  - `products/operator-portal/web-ui/app.js` — parse `tool_call`/`tool_result` events, render cards
  - `products/operator-portal/web-ui/styles.css` — evidence card styles
- chosen approach: vanilla JS DOM manipulation (matching the existing portal style — no framework):
  - Add a `<section class="panel" id="evidence-panel">` below Response, hidden by default
  - `streamPrompt()` gains handlers for `tool_call` and `tool_result` event types
  - `tool_call` → create a card element with tool name, parameters JSON, spinner; show the evidence panel
  - `tool_result` → find card by `call_id`, update with status badge, evidence metadata, collapsible `data_summary` JSON
  - Status badges: green for `success`, red for `denied`, amber for `error`
  - Out-of-order handling: if `tool_result` arrives with no matching card, create the card in completed state
- alternatives considered: (a) render tool traces inline within the response text — rejected because it clutters the LLM response and makes evidence non-scannable; (b) separate evidence tab/overlay — rejected because the portal is a single-page shell and tabs add complexity

### R-5: Dev overlay configuration for observability

- affected files:
  - `shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env` — add Elastic env vars
- chosen approach: add `GATEWAY_ELASTIC_ENABLED=false` and commented examples for `GATEWAY_ELASTIC_URL`, `GATEWAY_ELASTIC_API_KEY` — the connector is present in code but gated off in dev
- no new Kubernetes resources needed (Elastic is external to the dev cluster)
- alternatives considered: deploying an Elastic instance in dev — rejected as too heavy for the dev overlay; operators can point at an existing Elastic instance for integration testing

## Sequencing And Dependencies

1. **R-1** (schema) — no dependencies; can start immediately
2. **R-3** (Elastic connector) — no dependencies on R-1/R-2; can proceed in parallel
3. **R-2** (trace emission) — depends on R-1 (needs the schema types defined); can start alongside R-1 with the types agreed
4. **R-5** (dev overlay) — depends on R-3 (needs the env var names finalized)
5. **R-4** (evidence panel) — depends on R-1 (needs the event types); can prototype against mock events before R-2 is complete
6. **Integration testing** — depends on all of the above

## Test Strategy

- unit tests:
  - `agent-platform/tests/`: trace queue creation, trace event emission from toolkit closures, merge ordering in `stream_events`, `data_summary` truncation
  - `tool-gateway/tests/`: `ElasticConnector` tools with mocked `elasticsearch.Elasticsearch` client (success, error, not-configured), parameter validation (time range clamping, max results), lazy client init
  - `tool-gateway/tests/`: existing contract validation tests extended for new Elastic tool definitions
- contract tests:
  - `agent-platform/tests/` or `shared/`: validate emitted stream events (including `tool_call`/`tool_result`) against the updated `agent-stream-event.schema.json`
- integration / overlay validation:
  - `kustomize build` for all overlays (existing `make verify`)
  - portal smoke test: mock SSE stream with tool events, verify evidence panel renders

## Rollout And Migration

- no deployment or configuration changes required for existing services — the Elastic connector is gated off by default
- the stream event schema is backward-compatible: existing `message_start`/`message_delta`/`message_end`/`error` events are unchanged; `tool_call` and `tool_result` are additive
- the portal ignores unknown event types (existing behavior), so an older portal works with a newer agent-platform (tool traces are silently dropped)
- rollback: disable `GATEWAY_ELASTIC_ENABLED` and the stream reverts to text-only events (no `tool_call`/`tool_result` emitted because the toolkit has no Elastic tools to call)
