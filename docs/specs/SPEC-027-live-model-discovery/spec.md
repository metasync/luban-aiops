# SPEC-027: Live Model Discovery with Cached Fallback

## Status

- status: `approved`
- owner: chi
- created: 2026-08-24
- release slice: post-0.9.1 train
- related ADRs: `docs/adr/0002-reaffirm-agentscope-runtime-kernel.md`,
  `docs/adr/0003-platform-owned-agent-service-contract.md`
- extends: `docs/specs/SPEC-026-multi-model-runtime-catalog/spec.md`
  (which lifted the "dynamic model discovery" non-goal)

## Summary

SPEC-026 ships a curated model series per provider — a short, hand-maintained
list that drifts as providers release and retire models (DeepSeek's
`deepseek-chat`/`deepseek-reasoner` names were discontinued in July 2026;
DashScope moved to decimal generations like `qwen3.8-max`). SPEC-027 makes
the catalog self-refreshing: agent-service queries each configured provider's
OpenAI-compatible `GET /models` endpoint and serves the live list, with a
fail-soft fallback ladder (live fetch -> in-memory last-good ->
Postgres-persisted last-good -> curated series) so discovery failures never
degrade chat.

## Motivation

- Curated lists go stale: provider lineups change every few months, and a
  stale list either hides new flagships or offers discontinued names that
  fail at chat time.
- Operators asked for the full list their API key entitles them to,
  without a code change or secret re-sync for every provider release.
- All three supported providers expose an OpenAI-compatible `/models`
  endpoint behind the same API key already used for chat — no new
  credentials, no new egress.

## Requirements

### R-1: Live discovery per configured provider

For every provider whose API key resolves (SPEC-024/026 credential gate),
agent-service fetches `<base_url>/models` with the bearer key and offers
the returned models as catalog entries (id = model name, unchanged).

Acceptance criteria:

- The endpoint is the resolved base URL (adapter default or
  `<PROVIDER>_BASE_URL`) with a trailing `/models` appended; the request
  carries `Authorization: Bearer <key>` and a bounded timeout
  (`AGENT_MODEL_DISCOVERY_TIMEOUT_SECONDS`, default 5).
- The credential gate is unchanged: providers without a resolvable key are
  never queried and contribute nothing.
- The active provider's resolved default model is always force-included
  even if the live list would omit it (SPEC-026 R-1 invariant).

### R-2: Fallback ladder (fail-soft)

Discovery never blocks or degrades chat. When a fetch fails, the provider's
models come from the best available source in order:

1. the live fetch result,
2. the in-memory last-good list (survives transient fetch failures),
3. the Postgres-persisted last-good list (survives pod restarts),
4. the adapter's curated series (SPEC-026 behavior).

Acceptance criteria:

- Every successful fetch updates both the in-memory and the Postgres
  cache; the Postgres cache lives in the sessions DB (`SESSION_DB_URL`),
  table `model_discovery_cache(provider, models, updated_at)`,
  bootstrapped idempotently (`CREATE TABLE IF NOT EXISTS`).
- All cache read/write failures are logged and swallowed; Redis gains no
  new consumers — it stays dedicated to the AgentScope kernel message bus
  (ADR-0003 framework-swap hygiene).
- A provider that fails live discovery at startup with no cached data
  still serves its curated series.

### R-3: Periodic refresh with atomic catalog swap

The catalog is refreshed at startup (best-effort) and periodically
thereafter (`AGENT_MODEL_DISCOVERY_REFRESH_SECONDS`, default 1800), so new
provider models appear without a redeploy.

Acceptance criteria:

- A FastAPI lifespan background task performs the initial fetch and the
  refresh loop, and is cancelled on shutdown.
- Each successful refresh rebuilds the catalog entries and atomically swaps
  the module-level `MODEL_CATALOG` reference; kernel and route call sites
  are unchanged.
- Models removed mid-flight resolve through the existing unresolvable-id
  fallback to the catalog default; legacy provider-name aliases are
  rebuilt on every swap.

### R-4: Snapshot and modality filtering

Provider `/models` payloads contain dated snapshots and non-chat models;
the catalog offers only chat-capable current models.

Acceptance criteria:

- Each provider adapter supplies a discovery filter predicate; dated
  snapshot ids (`-YYYY-MM-DD`) and non-chat modalities (embeddings,
  rerank, audio, image, tts, translation, moderation) are dropped.
- DashScope additionally restricts to chat-capable qwen families.
- A filter that would drop the provider's default model never does
  (force-include invariant, R-1).

### R-5: Override precedence and enable knob

`<PROVIDER>_MODELS` keeps its SPEC-026 R-4 semantics and wins over
discovery; `AGENT_MODEL_DISCOVERY_ENABLED=false` restores pure
curated-series behavior.

Acceptance criteria:

- When `<PROVIDER>_MODELS` is set, discovery is skipped for that provider
  (deterministic pinning); the override list is served as-is (plus the
  force-included default).
- With discovery disabled, the catalog is byte-equivalent to SPEC-026.

### R-6: Refreshed curated series

The curated fallback lists are refreshed to the providers' current
lineups (verified 2026-08-24):

- deepseek: `deepseek-v4-flash`, `deepseek-v4-pro`,
  `deepseek-v4-flash-vision-exp` — the discontinued
  `deepseek-chat`/`deepseek-reasoner` names leave the series, but the
  SPEC-026 alias map keeps legacy pins resolving to the provider default.
- dashscope: `qwen-plus`, `qwen-max`, `qwen3.8-max`, `qwen3.7-plus`,
  `qwen3.7-flash`, `qwen-turbo`.
- openai: confirmed against the live endpoint during implementation.

## Non-Goals

- Model capability metadata (context window, pricing, modality badges) —
  `/models` payloads are id-centric and inconsistent across providers.
- User-initiated manual refresh (periodic loop suffices).
- Discovery for providers beyond deepseek/dashscope/openai.
- Persisting discovery results outside the sessions DB.

## Impact

- products touched: `products/agent-platform` (settings, provider
  adapters, new `services/model_discovery.py`, catalog rebuild/swap,
  app lifespan, metrics)
- contracts touched: none (catalog envelope unchanged); docs:
  configuration-reference, agent-platform README, runtime-profiles
  secrets example, CHANGELOG
- new observability: `model_discovery_refreshes_total{provider,result}`,
  `model_discovery_models{provider}` gauge

## Open Questions

All resolved in plan review (2026-08-24):

- Q-1 (cache substrate): Postgres (sessions DB), not Redis — Redis stays
  coupled exclusively to the AgentScope kernel message bus so a future
  framework swap migrates only the bus -> R-2.
- Q-2 (refresh cadence): startup + periodic loop, default 30 min -> R-3.
- Q-3 (list hygiene): per-provider filter predicates plus the existing
  `<PROVIDER>_MODELS` override as the per-deploy escape hatch -> R-4, R-5.

## Changelog

- 2026-08-24: created and approved; extends SPEC-026 whose curated-series
  catalog, credential gating, alias map, and portal grouping are reused
  unchanged here.
