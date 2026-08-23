# SPEC-024 Tasks

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.
Design decisions referenced as plan §D-1…§D-8.

## R-1: Credential-gated model catalog

- [x] `model_catalog.py`: `ModelCatalogEntry` + `build_model_catalog(settings)` with per-provider env knobs (`<PROVIDER>_API_KEY` / `_MODEL_NAME` / `_BASE_URL`, `AGENTSCOPE_*` fallback for the active provider), drop-without-key, default flag, module singleton (plan §D-1)
- [x] Unit tests: key fallback matrix, entries dropped without keys, default flag on the active profile, empty catalog allowed; unknown-provider config fails startup (`tests/test_model_catalog.py`)
- [x] Fail-closed selection: an unknown/unavailable model id answers 4xx on chat; no silent fallback (routes, plan §D-2)

## R-2: Model discovery contract

- [x] `shared/shared-contracts/schemas/model-catalog.schema.json` (new, self-contained); agent `GET /api/v2/models` route + response schema (no credentials/base URLs)
- [x] Platform-gateway pass-through `GET /api/v1/models` + `ACTION_MODELS_LIST`, policy rule mirroring the chat scope, mirror model + contract-lockstep tests
- [x] Additive `model` on chat request/response schemas both sides (`AgentChatRequest`/`AgentChatResponse`, gateway `ChatRequest`), relayed verbatim with upstream-4xx pass-through

## R-3: Per-session selection with affinity

- [x] `SessionRecord.model` across all three session-store backends: memory mutate, Redis blob, Postgres additive DDL + mapping + `set_session_model`; legacy records stay readable
- [x] Chat route pins the resolved model (request > pinned > default) at turn start, fail-open; `GET /api/v2/sessions/{id}` exposes `model` additively; `agent-session.schema.json` + gateway mirror in lockstep
- [x] Kernel: `ensure_agent(..., model_id)` rebuild-on-switch with `AgentState` restore; `_build_model(model_id)` via `dataclasses.replace`-derived settings; `stream_events(..., model_id)`; agent cache tuple tracks the bound model id
- [x] `message_end` stream frame carries the resolved model (additive `agent-stream-event.schema.json` field); tests cover switch-rebuild, state restore, and 409-while-parked inheritance (existing `_reject_if_parked`)

## R-4: Audited selection and portal selector

- [x] Gateway audit enrichment: `chat_completed` details gain the resolved model on POST; stream route records the requested model on `chat_started` and tees `message_end.model` into a `chat_completed` event at stream end; agent-side structured logs include the resolved model
- [x] Portal: `src/api/models.ts` + composer antd `Select` (default pre-selected; fixed label with one entry); selection rides the stream request; session switch seeds from `SessionDetail.model`
- [x] Vitest: fetch fallback (selector hides, chat works), single-entry fixed label, selection propagation; `tsc` clean

## Delivery close

- [x] Docs: root `CHANGELOG.md` entry, agent-platform README (catalog + env knobs), platform-gateway README (models route + action), operator-portal README (selector), configuration-reference, authorization-matrix, runtime-profiles README/example secrets (plan §D-8)
- [x] `make verify` green; browser walkthrough: single-entry fixed label, selection round-trip (API-level when only one key configured; live two-model when a second local key exists), audit trail shows the model, session detail shows the pinned model after reload
- [x] Spec status → `delivered`; open questions closed in spec changelog
