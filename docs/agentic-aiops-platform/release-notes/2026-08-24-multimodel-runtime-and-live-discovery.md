# v0.10.0 — Multi-Model Runtime: Selection, Evidence, Catalog, Discovery, Self-Hosting

Date: 2026-08-24
Release type: minor (new platform capabilities; additive API surfaces)

## Summary

v0.10.0 closes the multi-model runtime train — five specs that turn the
platform from a single-provider runtime into an operator-selectable,
self-updating multi-model platform:

- **SPEC-024** lets operators pick the serving model per turn, with the
  choice pinned to the session, audited, and surfaced in the portal
  composer.
- **SPEC-025** makes tool evidence durable: `tool_call`/`tool_result`
  frames persist with the transcript and replay prop-identically on
  reopened sessions.
- **SPEC-026** replaces the one-entry-per-provider catalog with a
  per-provider curated model series (model names as entry ids), a series
  override knob, and one consolidated `default` runtime profile instead
  of per-provider profile directories.
- **SPEC-027** feeds the catalog from each provider's live `/models`
  endpoint behind a fail-soft fallback ladder, so the lineup tracks the
  provider without ever blocking chat or startup.
- **SPEC-028** adds a fourth `luban` provider for team-hosted (local/
  on-prem) OpenAI-compatible servers — Ollama, vLLM, llama.cpp — with
  bearer-token auth, a mandatory base URL, an operator hosting guide,
  and reference Ollama K8s manifests; the foundation for the big-small
  LLM collaboration pattern.

A pre-release code and documentation review closed this train: its
findings are remediated here — an evicted model pin wedging parked HITL
confirmations, the fallback error text blaming the wrong provider
(shipped mid-train), a connection leak in the discovery cache's
bootstrap path, and an Ollama readiness probe that would be
401-rejected once bearer-token auth is enforced.

## Change Set

### Added — SPEC-024: Runtime LLM model switching

- Credential-gated model catalog derived at startup from per-provider env
  knobs (`<PROVIDER>_API_KEY` / `_MODEL_NAME` / `_BASE_URL`, with the
  active profile's `AGENTSCOPE_*` knobs as fallback); providers without
  a key are dropped, and a single-provider deployment needs zero new
  configuration.
- Per-turn selection (`"model"` on POST chat, `?model=` on the stream);
  resolution order request > session pin > deploy-time default; unknown
  ids fail closed (HTTP 422 / an `unknown_model` stream error frame —
  never a silent fallback).
- Selection pins onto the session (additive `model` column across the
  memory/Redis/Postgres session stores, exposed additively on session
  detail); switching rebuilds the cached kernel agent with full state
  restore.
- `GET /api/v1/models` behind the new `models:list` gateway policy
  action — discovery-safe by construction (no credentials or base URLs
  leave the runtime).
- `message_end` carries the serving model; audit gains the requested
  model on `chat_started` and the serving model on `chat_completed` on
  both chat surfaces.
- Portal composer gains an extensible selection bar hosting the model
  selector: catalog default pre-seed, fixed label when exactly one model
  is configured, fail-open hiding when discovery is unavailable, and
  re-seeding from the session pin on switch.

### Added — SPEC-025: Evidence persistence in session transcripts

- `tool_call`/`tool_result` frames persist per assistant turn into a
  `session_evidence` store behind the existing
  `AGENT_STATE_STORE_BACKEND` / `AGENT_STATE_DB_URL` knobs.
- Bounded by construction: a per-entry cap
  (`AGENT_EVIDENCE_ENTRY_MAX_CHARS`, default 131,072) truncates oversized
  payloads with an `entry_cap` marker; a per-session budget
  (`AGENT_EVIDENCE_SESSION_MAX_BYTES`, default 4 MiB) evicts oldest
  `tool_result` payloads with a `session_budget` marker while keeping
  metadata.
- Additive `evidence_turns` on `GET /api/v1/sessions/{id}` (empty list
  when none stored, `null` when the store is unreadable — never a 500);
  session delete cascades evidence cleanup.
- The portal re-attaches persisted evidence to the matching assistant
  turns on reload — replayed cards are prop-identical to the live ones,
  including truncation/eviction notes and the persisted `request_id`.
- Redaction is inherited from the tool-gateway choke point by
  construction. New counters: `evidence_store_writes_total{result}`,
  `evidence_frames_persisted_total`,
  `evidence_frames_truncated_total{reason}`.

### Added — SPEC-026: Multi-model runtime catalog & profile consolidation

- Every provider with a resolvable API key joins the catalog with its
  curated model series — one selectable entry per model (entry `id` =
  model name) instead of one entry per provider; curated series
  refreshed to current lineups (DeepSeek V4 family; DashScope qwen3.7/3.8
  decimal generations).
- `<PROVIDER>_MODELS=a,b,c` overrides/restricts a provider's series and
  is authoritative over discovery; the active provider's
  `AGENTSCOPE_MODEL_NAME` is always force-included as the deploy-time
  default.
- Legacy provider-name ids (existing session pins) alias to the
  provider's default model; duplicate model ids across providers fail
  startup as a misconfiguration guard.
- GitOps runtime profiles consolidate: per-provider
  `runtime-profiles/{deepseek,dashscope,openai}` overlays are replaced
  by one generic `runtime-profiles/default` whose `AGENTSCOPE_PROFILE`
  label is decoupled from `AGENTSCOPE_PROVIDER`.
- The portal model selector groups options by provider.

### Added — SPEC-027: Live model discovery with cached fallback

- A lifespan-owned background task queries each configured provider's
  OpenAI-compatible `/models` endpoint at startup and every
  `AGENT_MODEL_DISCOVERY_REFRESH_SECONDS` (default 1800), applies
  per-provider filters (dated `-YYYY-MM-DD` snapshots and non-chat
  modalities dropped; the provider default always force-included), and
  atomically swaps the catalog in place.
- Failed fetches degrade down a fail-soft ladder: in-memory last-good →
  Postgres-persisted last-good (new `model_discovery_cache` table in the
  sessions database) → curated series, so restarts stay served from
  cache before the first live fetch lands. Redis gains no new consumers
  (ADR-0003).
- Knobs: `AGENT_MODEL_DISCOVERY_ENABLED` (default true; `false` restores
  the pure curated-series behavior) and
  `AGENT_MODEL_DISCOVERY_TIMEOUT_SECONDS` (default 5). Discovery never
  blocks chat or startup — every failure is logged and swallowed.
- New metrics: `agent_model_discovery_refreshes_total{provider,result}`,
  `agent_model_discovery_models{provider}`.
- Operational posture shipped with delivery: DashScope pinned to
  fixed-point generation ids (no rolling tier aliases, so audit
  attribution names the exact model); the pinned `DASHSCOPE_MODELS`
  override skips discovery for that provider by design.

### Added — SPEC-028: Luban-hosted small model provider

- A fourth runtime provider `luban` wires team-hosted (local/on-prem)
  OpenAI-compatible servers — Ollama, vLLM, llama.cpp `llama-server` —
  into the existing catalog machinery with bearer-token authentication,
  reusing SPEC-024 selection/pinning and SPEC-027 discovery unchanged.
- Knobs: `LUBAN_API_KEY` (credential gate), `LUBAN_BASE_URL` (mandatory
  — a key without a base URL gates the provider out, since self-hosted
  endpoints have no default endpoint), `LUBAN_MODEL_NAME` (provider
  default), `LUBAN_MODELS` (fixed-point pinning, authoritative over
  discovery), `LUBAN_THINKING_ENABLE` (opt-in; thinking defaults off
  for small-model-safe generation).
- The curated series is empty, so pinning or live discovery supplies
  the lineup; the fail-soft ladder keeps an offline server degrading to
  the default model only. The provider enum in the agent-service
  contract and the shared model-catalog JSON schema are locked against
  drift by a new parity test.
- New operator guide `docs/guides/luban-llm-guide.md` (stack selection,
  token-auth setup, platform wiring, K8s hosting, verification,
  troubleshooting) and free-standing reference Ollama manifests under
  `shared/platform-ops/gitops/llm-hosting/` (Deployment/Service/
  Secret/PVC; opt-in, not wired into `dev-k8s` or `make deploy`).

### Fixed (pre-release review findings)

- **HITL confirm with an evicted model pin (major)**: `/chat/confirm`
  forwarded the raw session pin into the resume path, so a pinned model
  evicted by a discovery refresh (or a key revocation) raised
  `UnknownModelError` mid-stream — tearing the SSE stream and
  permanently wedging the parked session, because the registry entry is
  claimed before headers go out and only resolved inside the generator.
  The confirm route now resolves the pin through the same request >
  pinned > default ladder as other turns, degrading a stale pin to the
  catalog default. Regression-tested.
- **Fallback response provider attribution**: the provider-error
  fallback text named the active profile's provider, so a dashscope
  model failure read "provider deepseek failed". The kernel now resolves
  the turn's serving model against the catalog and attributes that
  provider (model id included); without model context the previous
  wording is kept. Regression-tested.
- **Discovery cache bootstrap connection leak**: when the
  `model_discovery_cache` bootstrap DDL failed against a reachable
  Postgres, `PostgresDiscoveryCache` leaked the opened connection on
  every refresh cycle; bootstrap failures now close the connection before
  the fail-soft swallow. Regression-tested.
- **Ollama readiness probe under token auth (minor)**: the reference
  `llm-hosting` deployment's `httpGet` readiness probe would be
  401-rejected by the kubelet once `OLLAMA_API_KEY` is enforced (the
  probe originates outside Ollama's auth-exempt localhost path). The
  probe is now an `exec` of `ollama list`, which talks to the server
  over localhost.

## Validation

- Full agent-platform suite green (422 tests, including the SPEC-028
  gating/parity/discovery tests); platform-gateway suite green
  (194 tests); `make verify` gate green (all products, overlay renders,
  policy validation, version lockstep).
- Live-verified in dev-k8s: startup discovery fetched both providers (55
  models before pinning), restart served from the Postgres cache tier,
  metrics report `result="live"` / `result="override"` per provider;
  after the DashScope fixed-point pin the catalog serves exactly the
  pinned lineup, and portal turns were attributed to the serving model in
  the audit trail (`details.model`).
- SPEC-028 live-verified end-to-end in dev-k8s: the reference Ollama
  stack runs in an `llm-hosting` namespace with a real bearer token;
  `qwen3:1.7b` appears in `/api/v2/models` under `provider: "luban"`
  with discovery metrics at `result="live"`, a portal turn on the luban
  model completed, and the audit trail attributes `model=qwen3:1.7b`.
- L3 deep security reviews at each push gate returned zero findings.

## Upgrade Notes

- No breaking changes: legacy provider-name model ids keep working via
  aliases, session pins survive, and a single-provider deployment needs
  zero new configuration.
- New knobs (all optional): `AGENT_MODEL_DISCOVERY_ENABLED`,
  `AGENT_MODEL_DISCOVERY_REFRESH_SECONDS`,
  `AGENT_MODEL_DISCOVERY_TIMEOUT_SECONDS`, `<PROVIDER>_MODELS`,
  `AGENT_EVIDENCE_ENTRY_MAX_CHARS`, `AGENT_EVIDENCE_SESSION_MAX_BYTES`,
  and the SPEC-028 `LUBAN_*` set (`LUBAN_API_KEY`, `LUBAN_BASE_URL`,
  `LUBAN_MODEL_NAME`, `LUBAN_MODELS`, `LUBAN_THINKING_ENABLE`) — see
  `docs/guides/luban-llm-guide.md` for the self-hosting walkthrough.
- Deployments running per-provider runtime-profile overlays should move
  to the consolidated `runtime-profiles/default` profile.
