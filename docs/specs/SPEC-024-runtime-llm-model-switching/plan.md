# SPEC-024 Implementation Plan

Plan for the approved spec. All four open questions were resolved in draft
review (spec §Open Questions); this plan turns those resolutions into a
decision-complete implementation design. No measurement pass is needed:
unlike SPEC-025 there are no sizing unknowns — the work is contract and
wiring over existing machinery (provider registry, session store, audit
tee, pass-through routes).

## Design decisions

### D-1: Catalog module and env contract (R-1)

New `agent_service/services/model_catalog.py`:

```python
@dataclass(frozen=True)
class ModelCatalogEntry:
    id: str            # provider name (one entry per provider, Q-1)
    label: str         # configured model name, e.g. "deepseek-v4-flash"
    provider: RuntimeProvider
    api_key: str
    model_name: str
    base_url: str | None
    default: bool
```

- `build_model_catalog(settings)` derives entries from env at startup:
  for each provider in `SUPPORTED_RUNTIME_PROVIDERS`, key resolution is
  `<PROVIDER>_API_KEY` (e.g. `OPENAI_API_KEY`), falling back to
  `AGENTSCOPE_API_KEY` **only** for the active profile's provider; model
  name / base URL follow the same pattern (`<PROVIDER>_MODEL_NAME` /
  `<PROVIDER>_BASE_URL`, falling back to `AGENTSCOPE_MODEL_NAME` /
  `AGENTSCOPE_BASE_URL` for the active provider, then the provider
  adapter defaults). Entries with an empty/missing key are dropped.
- The active profile's entry is flagged `default=True`; a catalog with
  zero entries is allowed and degrades like `is_configured() == False`
  today (runtime metadata `not_configured`, no-tools notice unchanged).
- Id = provider name keeps the chat field simple (`"model": "openai"`);
  the label carries the model name for the portal dropdown.
- Module singleton `MODEL_CATALOG` built next to `EVIDENCE_STORE`.

### D-2: Kernel model selection (R-3)

`RuntimeKernel`:

- `ensure_agent(session_id, bearer_token, model_id=None)`: the agent
  cache tuple gains the bound model id `(agent, UserMsg, model_id)`. A
  turn whose resolved model differs from the bound one evicts the cached
  agent and rebuilds; `_restore_state` (SPEC-017 R-3) rebuilds memory,
  exactly like the pod-restart path.
- `_build_model(model_id)` derives a replaced `RuntimeSettings`
  (`dataclasses.replace`: provider, api_key, model_name, base_url,
  `provider_options=default_provider_options(provider)`) and calls the
  existing `get_provider(...).build_model(...)`. Provider adapters are
  unchanged.
- `stream_events(...)` gains `model_id: str | None`; resolution order
  (request > pinned > default) happens in the route layer, which owns
  the session record — the kernel receives a concrete catalog id and
  fails closed (structured error frame) on an unknown id.
- Parked sessions never reach model handling: `_reject_if_parked`
  already answers `409` before any chat/stream turn body runs (Q-2).

### D-3: Session-store affinity (R-3, Q-4)

- `SessionRecord` (agent `schemas/api.py`) gains `model: str | None = None`.
- Backends: memory mutates the record; Redis keeps it in the serialized
  blob (pydantic default handles legacy blobs); Postgres gains
  `ALTER TABLE sessions ADD COLUMN IF NOT EXISTS model TEXT` (same
  additive-DDL pattern as `title`/`last_active_at`) plus INSERT/SELECT
  mapping, and a `set_session_model(session_id, model)` store method on
  the protocol.
- The chat route pins the resolved model on the record at turn start
  (next to `mark_session_turn`); pinning is set-once-per-value and
  fail-open like workspace bookkeeping.

### D-4: Contracts (R-2, R-3)

- New `shared/shared-contracts/schemas/model-catalog.schema.json`:
  `{"models": [{id, label, provider, default}], "default": id}` —
  self-contained per the no-cross-file-`$ref` convention; provider is
  an enum of the three supported providers.
- `agent-session.schema.json`: additive `model` (string|null) next to
  `evidence_turns`; gateway `SessionRecord` mirror gains it in lockstep
  (the property-alignment contract test enforces this).
- `AgentChatRequest` / gateway `ChatRequest` gain optional `model`;
  `AgentChatResponse` gains `model: str | None` (the resolved model).
- `agent-stream-event.schema.json`: additive `model` string on
  `message_end` frames (schema description bump; the kernel emits the
  resolved model id so the gateway tee can capture it).

### D-5: Routes (R-2)

- agent-service `GET /api/v2/models`: returns the catalog minus
  credentials/base URLs; no auth change (X-User-ID like other v2 reads);
  always 200, empty list when nothing is configured.
- platform-gateway `GET /api/v1/models`: new pass-through route +
  `ACTION_MODELS_LIST = "models:list"`; policy rule mirrors the chat
  scope (operators + observers). Mirror model in `schemas/api.py` +
  contract-lockstep tests.
- `POST /api/v1/chat` body and `GET /api/v1/chat/stream` query gain
  optional `model`; relayed to agent-service verbatim; upstream 4xx for
  an unknown model passes through (existing 4xx pass-through posture).

### D-6: Audit enrichment (R-4, Q-3)

- `POST /api/v1/chat`: `chat_completed` audit details gain
  `model` from the upstream response.
- Stream route: `chat_started` details gain `model` = the *requested*
  model (null when unset); the frame tee (which already walks frames for
  `confirmation_decided`) captures the resolved model from `message_end`
  and emits a `chat_completed` audit event at normal stream end so
  streamed turns — the portal's primary path — are attributed too. No
  new event types; the closed enum is untouched.
- agent-platform structured logs include the resolved model on chat
  events as well.

### D-7: Portal selector (R-4)

- New `src/api/models.ts`: `ModelCatalog` types + fetch against
  `GET /api/v1/models`.
- ChatView composer: antd `Select` beside the send control, options
  from the catalog, pre-selected to `default`; with exactly one entry it
  renders as a fixed label. Selection rides on
  `useChatStream`'s stream request as the `model` parameter.
- Session switch seeds the selector from `SessionDetail.model`;
  `models.ts`/`sessions.ts` types gain the additive field.
- Vitest: catalog fetch fallback (endpoint error → selector hides,
  chat still works), single-entry fixed label, selection propagation.

### D-8: dev-k8s wiring

- Committed overlays are unchanged: the active deepseek profile feeds
  the default catalog entry via existing `AGENTSCOPE_*` knobs.
- `runtime-profiles/*/runtime-secrets.example.env` document the
  additive `<PROVIDER>_API_KEY` / `<PROVIDER>_MODEL_NAME` knobs for
  enabling extra models locally; a local (ignored) `runtime-secrets.env`
  with a second provider's key enables a live two-model walkthrough
  when available. With one entry, the walkthrough verifies the
  fixed-label posture and API-level selection round-trip.

## Verification plan

- agent-platform: catalog unit tests (key fallback matrix, drop-without-
  key, default flag), kernel rebuild-on-switch + state-restore test,
  unknown-model fail-closed test, session-store model column tests
  (memory/redis/postgres fake), models route tests, schema validation in
  session-workspace tests.
- platform-gateway: pass-through + contract-lockstep tests, policy rule
  test, audit details assertions (requested vs resolved model), stream
  tee capture test.
- portal: Vitest per D-7; `tsc` clean.
- `make build` then `make verify`; deployed walkthrough: single-entry
  fixed label, selection via API when a second local key exists, audit
  trail shows the model, session detail shows the pinned model after
  reload.

## Assumptions

- agentscope model construction is per-agent (verified: `build_model`
  returns a fresh model instance), so rebuild-on-switch carries no
  hidden shared state.
- The stream tee already inspects every frame, so capturing
  `message_end.model` adds no new pass over the stream.
- No version bump: additive contracts only (SPEC-024 rides the 0.9.x
  train; release closure decides the number).
