# SPEC-017 Tasks: Agent Kernel Utilization and Conversation Durability

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Kernel configuration surfaces

- [x] settings fields: `AGENTSCOPE_MAX_ITERS`, `AGENTSCOPE_CONTEXT_TRIGGER_RATIO`, `AGENTSCOPE_TOOL_RESULT_LIMIT`, `AGENTSCOPE_TIMEZONE`, `AGENTSCOPE_MODEL_MAX_RETRIES` with agentscope defaults + range validation (`products/agent-platform/src/agent_service/runtime_settings.py` + `tests/test_runtime_settings.py`)
- [x] `AgentKernel` builds `ReActConfig` / `ContextConfig` / `InjectionConfig` (with `inject_runtime_state`) / `ModelConfig` from settings (`runtime_kernel.py` + `tests/test_runtime_kernel.py`)
- [x] structured log line at agent construction recording effective config values

## R-2: Structured output for triage reports

- [x] v2 chat request gains optional `response_schema`; turn runs with `structured_schema=...`; response carries `structured_output` (`schemas/v2.py`, `api/v2/routes.py`, `runtime_kernel.py` + tests)
- [x] `agent-chat-response.schema.json` gains `structured_output` (`["object", "null"]`) (`shared/shared-contracts/schemas/`)
- [x] platform-gateway `ChatResponse` mirror model gains `structured_output` for contract parity (`products/platform-gateway/src/platform_gateway/schemas/api.py` + `tests/test_contracts.py` green)
- [x] incident-service triage sends `triage-report.schema.json` as `response_schema`, prefers `structured_output`, fenced-block parser as fallback (`products/incident-service/src/incident_service/services/triage.py` + tests)
- [x] system prompt fenced-block discipline replaced with format-neutral instruction; attribution forcing + `triage_failed` semantics unchanged

## R-3: Conversation durability — AgentState persistence

- [x] settings: `AGENT_STATE_STORE_BACKEND` (`memory` | `postgres`), `AGENT_STATE_DB_URL`, `AGENT_STATE_TTL_SECONDS` (+ settings tests)
- [x] `AgentStateStore` protocol + `InMemoryAgentStateStore` + `PostgresAgentStateStore` (`agent_states`: session_id PK, state JSONB, updated_at; idempotent startup DDL; parameterized SQL) (`services/agent_state_store.py` + `tests/test_agent_state_store.py`)
- [x] factory with fail-open fallback (WARNING + `agent_state_fallbacks_total`)
- [x] snapshot after every completed turn (`reply_text` + end of `stream_events`); failures counted, never fail the turn (`runtime_kernel.py`)
- [x] restore on agent construction (cache miss); corrupt row discarded with WARNING + counter
- [x] `delete_state(session_id)` on session deletion (`services/session_service.py`); bounded opportunistic TTL sweep

## R-4: dev-k8s deployment

- [x] sessions database bootstrap hosts the `agent_states` table DDL (applied by agent-platform at startup) (`shared/platform-ops/gitops/dev-k8s/base/infra/`)
- [x] `runtime-config.env`: `AGENT_STATE_STORE_BACKEND=postgres` + `AGENT_STATE_DB_URL`; kernel tuning knobs intentionally unset (`dev-k8s/base/agent-platform/`)
- [x] redis deployment confirmed unchanged (kernel-only, ephemeral by design)

## R-5: Observability, tests, documentation

- [x] metrics: `agent_state_backend` gauge, `agent_state_errors_total`, `agent_state_fallbacks_total` (`core/metrics.py`)
- [x] `/health` gains `agent_state` readiness field; `agent-health.schema.json` updated (`api/v2/routes.py`, `shared/shared-contracts/schemas/`)
- [x] tests green per product incl. structured chat round-trip, triage structured-first + fallback, state snapshot/restore round-trip with corrupt-row discard
- [x] `docs/guides/configuration-reference.md`: kernel knobs + `AGENT_STATE_*` vars
- [x] agent-platform README durability section + kernel knob entries; dev-k8s README agent-state section
- [x] architecture guide notes conversation state durable in Postgres (`docs/guides/architecture-overview.md`)

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified
- [x] living state docs updated (see spec `Impact` section)
- [x] `CHANGELOG.md` entry added referencing the spec ID
- [x] spec index in `docs/specs/README.md` updated
- [x] spec status set to `delivered`
