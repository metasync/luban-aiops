# SPEC-011 Tasks: Observability Connector and Evidence Panels

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Stream event contract extension for tool traces

- [x] Extend `agent-stream-event.schema.json` `type` enum with `tool_call` and `tool_result` (`shared/shared-contracts/schemas/agent-stream-event.schema.json`)
- [x] Add `tool_call` optional properties: `tool_name`, `parameters`, `call_id` (`shared/shared-contracts/schemas/agent-stream-event.schema.json`)
- [x] Add `tool_result` optional properties: `tool_name`, `call_id`, `status`, `evidence`, `data_summary`, `error` (`shared/shared-contracts/schemas/agent-stream-event.schema.json`)
- [x] Document new event types in schema `$defs` or descriptions (`shared/shared-contracts/schemas/agent-stream-event.schema.json`)
- [x] Add contract validation test for `tool_call` and `tool_result` events (`products/agent-platform/tests/`)

## R-2: Tool trace emission from the agent runtime

- [x] Add `AGENT_TOOL_DATA_SUMMARY_MAX_CHARS` setting to `RuntimeSettings` (env var, default 2000) (`products/agent-platform/src/agent_service/runtime_settings.py`)
- [x] Extend `build_toolkit_functions` to accept a trace queue parameter and emit `tool_call`/`tool_result` events from each closure (`products/agent-platform/src/agent_service/tools/gateway_tools.py`)
- [x] Extend `build_toolkit` to accept and propagate a trace queue (`products/agent-platform/src/agent_service/tools/gateway_tools.py`)
- [x] Implement `data_summary` truncation: `json.dumps(data)[:MAX_CHARS]` with ellipsis marker (`products/agent-platform/src/agent_service/tools/gateway_tools.py`)
- [x] Update `_ensure_toolkit` to accept and pass a trace queue (`products/agent-platform/src/agent_service/runtime_kernel.py`)
- [x] Implement per-request trace queue creation and merge in `stream_events` using `asyncio.wait` FIRST_COMPLETED (`products/agent-platform/src/agent_service/runtime_kernel.py`)
- [x] Unit test: toolkit closure emits `tool_call` before invocation and `tool_result` after (`products/agent-platform/tests/`)
- [x] Unit test: `stream_events` yields trace events interleaved with text deltas in chronological order (`products/agent-platform/tests/`)
- [x] Unit test: `data_summary` truncation respects `AGENT_TOOL_DATA_SUMMARY_MAX_CHARS` (`products/agent-platform/tests/`)
- [x] Unit test: no trace events emitted when `tool_gateway_url` is not configured (`products/agent-platform/tests/`)

## R-3: Elastic observability connector

- [x] Add Elastic settings to `RuntimeSettings`: `GATEWAY_ELASTIC_ENABLED`, `GATEWAY_ELASTIC_URL`, `GATEWAY_ELASTIC_API_KEY`, `GATEWAY_ELASTIC_USERNAME`, `GATEWAY_ELASTIC_PASSWORD`, `GATEWAY_ELASTIC_VERIFY_TLS`, `GATEWAY_ELASTIC_ALERTS_INDEX` (`products/tool-gateway/src/tool_gateway/runtime_settings.py`)
- [x] Implement `ElasticConnector` class with lazy `_ensure_client()` (`products/tool-gateway/src/tool_gateway/tools/elastic_connector.py`)
- [x] Implement `SearchLogsTool` with query/index/time_range_minutes/max_results parameters (`products/tool-gateway/src/tool_gateway/tools/elastic_connector.py`)
- [x] Implement `GetServiceHealthTool` with service_name/time_range_minutes parameters (`products/tool-gateway/src/tool_gateway/tools/elastic_connector.py`)
- [x] Implement `GetActiveAlertsTool` with severity/max_results parameters (`products/tool-gateway/src/tool_gateway/tools/elastic_connector.py`)
- [x] Register Elastic tools in `gateway_service.py` when `GATEWAY_ELASTIC_ENABLED=true` (`products/tool-gateway/src/tool_gateway/services/gateway_service.py`)
- [x] Add `elasticsearch` to `pyproject.toml` optional or required dependencies (`products/tool-gateway/pyproject.toml`)
- [x] Unit test: `SearchLogsTool` success with mocked client, parameter clamping (time_range, max_results) (`products/tool-gateway/tests/`)
- [x] Unit test: `GetServiceHealthTool` success and aggregation result (`products/tool-gateway/tests/`)
- [x] Unit test: `GetActiveAlertsTool` success with severity filter (`products/tool-gateway/tests/`)
- [x] Unit test: all three tools return `ELASTIC_NOT_CONFIGURED` when client not initialized (`products/tool-gateway/tests/`)
- [x] Unit test: all three tools return `ELASTIC_CONNECTION_ERROR` on client exception (`products/tool-gateway/tests/`)
- [x] Unit test: lazy client initialization with API key and basic auth fallback (`products/tool-gateway/tests/`)

## R-4: Operator portal evidence panel

- [x] Add "Evidence" section to `index.html` below Response, hidden by default (`products/operator-portal/web-ui/index.html`)
- [x] Add evidence card CSS styles: status badges (success/error/denied), loading spinner, collapsible JSON (`products/operator-portal/web-ui/styles.css`)
- [x] Extend `streamPrompt()` to handle `tool_call` events: create card with tool name, parameters JSON, spinner (`products/operator-portal/web-ui/app.js`)
- [x] Extend `streamPrompt()` to handle `tool_result` events: update card by `call_id` with status, evidence, data_summary (`products/operator-portal/web-ui/app.js`)
- [x] Handle out-of-order events: `tool_result` without matching card creates completed card (`products/operator-portal/web-ui/app.js`)
- [x] Show evidence panel when first `tool_call` arrives, keep hidden when stream has no tool calls (`products/operator-portal/web-ui/app.js`)
- [x] Clear evidence panel on new stream request (`products/operator-portal/web-ui/app.js`)

## R-5: Dev overlay configuration for observability

- [x] Add `GATEWAY_ELASTIC_ENABLED=false` and commented Elastic env var examples to tool-gateway runtime-config.env (`shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env`)
- [x] Verify `kustomize build` renders without errors (`shared/platform-ops/gitops/`)

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified
- [x] living state docs updated (see spec `Impact` section):
  - [x] `products/tool-gateway/README.md` — document Elastic connector and configuration
  - [x] `products/agent-platform/README.md` — document tool trace events and data summary setting
  - [x] `products/operator-portal/README.md` — document evidence panel
  - [x] `CHANGELOG.md` — Unreleased entry referencing SPEC-011
- [x] spec index in `docs/specs/README.md` updated with SPEC-011
- [x] `make verify` green (all product tests + all overlay renders)
- [x] spec status set to `delivered`
