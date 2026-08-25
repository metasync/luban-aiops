# Changelog

All notable changes to this repository are documented in this file.

Platform releases follow semantic versioning (MAJOR.MINOR.PATCH): the root
`VERSION` file is the single source of truth, release trains map to MINOR
bumps, and entries accumulate under `Unreleased` until a release closes
them into a versioned section. Version lockstep across products and the
portal is enforced by `make validate-version`.

Versions prior to 0.1.0 were not numbered; Release 0 foundation work and
Release 1 entries are grouped retrospectively under 0.1.0.

## Unreleased

## 0.14.0 — 2026-08-25

### Added

- **Owner-side live decision sync (SPEC-032)**: the owner's open chat
  window now learns about decisions made elsewhere (the approver inbox,
  a second browser session) without a manual refresh. While a
  confirmation card is pending, the chat view polls the session-detail
  surface on a short interval (5s) and re-seeds the turn timeline the
  moment the state moves — the card flips to its resolution with decider
  attribution and the resumed turn's content becomes visible. The poll
  is bounded and change-gated: it runs only while a card is pending
  (plus a short settle window for the trailing resumed-turn content),
  never while any chat stream is active, stops on its own once the last
  card resolves, and identical responses never rebuild the timeline.
  Portal-only — no backend, contract, or policy changes; the
  `confirmation_result` frame still rides the answering stream as
  before.

### Changed

- Version lockstep bumped to 0.14.0 and per-product `uv.lock` files
  refreshed; `approval-and-hitl.md` and `portal-user-guide.md` document
  the live owner-side sync.

## 0.13.1 — 2026-08-25

### Fixed

- **Confirm race window between claim and stream end (SPEC-031 review)**:
  the durable outcome was written only when the resumed turn finished, so
  a racing approver answering mid-stream got a bare 404 instead of the
  structured outcome. The confirm route now persists the outcome at claim
  time (the claim is single-flight and the decision irrevocable once
  claimed); the resume's safety-net write stays as an idempotent no-op,
  and `mark_resolved` is first-write-wins in both backends.
- **Startup sweep expired every pending row globally (SPEC-031 review)**:
  a sibling replica's restart killed another pod's live park. The sweep
  is now scoped to pending rows older than the HITL confirmation TTL
  (`AGENT_HITL_CONFIRM_TIMEOUT`, default 600s) — a park past its TTL
  answers no confirmation on any replica, so closing it is safe across
  replicas; younger rows stay untouched.

### Changed

- Version lockstep and dependency lockfiles refreshed for the 0.13.1
  patch; changelog, release notes, approval-and-hitl guide, and
  troubleshooting guide wording synced to the TTL-scoped sweep.

## 0.13.0 — 2026-08-25

### Added

- **Approval inbox and persistent confirmation cards (SPEC-031)**: every
  parked confirmation and its resolution are now persisted durably
  (Postgres on the shared `AGENT_STATE_DB_URL` posture; most recent 50
  records per session, cascade-deleted with the session, pending rows
  older than the HITL confirmation TTL flipped to expired on startup) —
  durability is the source of truth for history and restart recovery
  while the in-memory registry stays the hot path. Two surfaces build on
  the record store: the owner's session detail
  gains an additive `confirmations` array so cards survive re-login, page
  reloads, pod restarts, and replica boundaries (decided cards render
  read-only with decider attribution, pending cards stay actionable), and
  designated approvers get a cross-session inbox
  (`GET /api/v1/approvals/inbox`) gated by a new `approvals:list` policy
  action granted to `approver` and `platform-admin` (bundle rule
  `allow-approvers-approvals-list`). Inbox items are metadata only —
  session, owner, parked calls, outcome — never the owner's transcript
  text, listing pending items plus the last 30 days of history (expired
  items included) most recent first. The portal gains an Approvals view
  for decider roles — nav entry with a pending-count badge, 30s/focus
  polling, pending-first list + history — reusing the SPEC-030
  confirmation card component and the existing `chat/confirm` bridge, so
  tier enforcement, self-approval blocking, audit, and
  resume-under-confirmer-token semantics are unchanged.

### Changed

- Confirm races now resolve into a structured outcome instead of an
  opaque error: a decision against an already-resolved confirmation
  answers `409 already_resolved` carrying the winner's status, decider,
  decision, and decided-at timestamp (agent-platform and the gateway
  pass it through unchanged), and the portal flips the losing card to
  that outcome in both the chat transcript and the approvals inbox. The
  outcome is persisted at claim time — the durable write lands the
  moment the single-flight claim succeeds, so a racing approver sees the
  structured 409 even while the winner's resumed turn still streams,
  never an opaque 404.
- The mutating-demo e2e HITL leg asserts the SPEC-031 surfaces: the
  owner's session detail carries the decided card, the approver inbox
  lists the item with its outcome, and a second approve receives the
  `already_resolved` 409.

## 0.12.0 — 2026-08-25

### Added

- **Require-approval policy semantics (SPEC-030)**: `require_approval` is
  now a first-class, enforced policy outcome with approval tiers. The two
  shared policy schemas gain an additive v2 revision (`approval` block with
  `tier_1` / `tier_2`, `decided_by_roles`, tier-defaulted
  `allow_self_approval`; the reserved `approval_tier` decision field is
  activated), and both gateway engines evaluate three outcomes
  (deny > require_approval > allow). Platform-gateway bridges the outcome
  onto `chat:confirm`: parked batches under a `require_approval` rule check
  the confirmer's roles against `decided_by_roles` and block self-approval
  where the tier forbids it — structured 403s, the attempt audited as a
  blocked `confirmation_decided`, the parked call stays parked, and the
  parked-info fetch fails closed. The default bundle ships a `tier_2` rule
  on `tools:mutate` decided by `approver` / `platform-admin`, so mutating
  runs now need an approver distinct from the requester
  (`mutating-demo.sh` exercises the two-identity flow). The live policy
  matrix exposes requirements as an additive third cell state
  (`approval_requirements`), the portal permissions view renders it, and
  confirmation cards gain a tier badge ("operator confirmation" /
  "approver required") with read-only rendering for non-deciders.
- **Settings view restored (SPEC-030 R-6)**: the portal's Settings entry
  now renders a read-only, tabbed Session & Identity panel (Identity,
  Session, Platform panes — sign-in state and claims, the selected
  session, version / API origin / last request id) built as an extensible
  pane container; the SPEC-023 placeholder is removed and no mutable
  controls ship.

### Changed

- Agent-platform relaxes the confirmer-must-own-session restriction on
  `chat/confirm` (a tier_2 approver legitimately decides a foreign
  session) and exposes the parked batch's policy action via a new
  `GET /api/v2/chat/pending-confirmation` endpoint consumed by the
  gateway bridge; approval authorization lives at the platform edge.
- Tool-gateway validates approval blocks loudly at bundle load, then
  skips `require_approval` rules with a warning — the synced default
  bundle stays loadable there and SPEC-021 admission stays allow/deny.
- Default policy bundle grants `approver` the tool execution actions
  (`tools:list` / `tools:invoke` / `tools:mutate`) — a tier_2-approved
  call resumes under the confirmer's delegated token, so the approved
  execution must pass tool-gateway admission. Separation of duties stays
  enforced at the approval gate (tier_2 self-approval is blocked).

### Fixed

- Live cluster validation: incident triage turns now run in a per-turn
  read-only mode — mutating tools are excluded from the triage toolkit,
  so a single-shot triage can no longer park on a mutating call and lose
  the report.
- Live cluster validation: the kernel's structured-output delivery tool
  (`GenerateStructuredOutput`) joins the session-local allow set in the
  permission middleware — schema-shaped replies no longer park on the
  confirmation gate.
- Live cluster validation: `e2e/mutating-demo.sh` HITL leg targets a
  scratch deployment pod (the bounded restart semantic the model accepts)
  and matches the approved execution's `tool_invoked` audit event by
  tool + time window, since audit details are parameter-redacted.

## 0.11.1 — 2026-08-25

### Fixed

- `sync-skills-secrets.sh` no longer wipes `SKILLS_AUDIT_CLIENT_SECRET` from the shared skills-hub runtime secret file when re-provisioning the query credential — the missing key 401'd every skills-hub audit emission until audit sync ran again.

### Changed

- Version lockstep and dependency lockfiles refreshed for the 0.11.1 patch.

## 0.11.0 — 2026-08-25

### Added

- **Skills usage audit trail (SPEC-029)**: skills-hub now emits audit
  events so operators can see which skills are actually used. Every
  authenticated `search` produces a `skill_searched` event (query, limit,
  result count, matched skill ids, optional source/tag filters), every
  `get` produces a `skill_retrieved` event (hit → `success` with
  provenance, miss → `error` with `reason: not_found`), and each sync
  cycle produces one `skills_synced` event per source (accepted/rejected
  counts on success, token-scrubbed error on failure). Emission reuses
  the canonical fire-and-forget emitter (now drift-guarded across four
  services by the parity suite) behind new `SKILLS_AUDIT_SERVICE_URL` /
  `SKILLS_AUDIT_CLIENT_ID` / `SKILLS_AUDIT_CLIENT_SECRET` knobs — an
  empty URL disables it. Query events correlate with the caller's
  `tool_invoked` events: tool-gateway now forwards `x-request-id` to
  skills-hub, so one portal question can be traced end-to-end without
  forwarding user identity. The shared audit-event contract and
  audit-service vocabulary gained the three event types, and
  `sync-audit-secrets.sh` provisions the skills-hub ingest credential.

### Changed

- Documentation review remediation: new operator guides — portal day-2
  usage (`docs/guides/portal-user-guide.md`), add-a-tool contributor
  walkthrough (`docs/guides/adding-a-tool.md`), and user/role
  administration (`docs/guides/user-and-role-administration.md`); CONTRIBUTING
  testing section and stale study README fixed; pydantic pins aligned.
- Test-depth remediation: drift-guard parity suite for modules
  duplicated across services (telemetry, observability, token verifier,
  audit emitter, ingest/query auth); audit-service coverage 80% → 95%
  and incident-service 87% → 92% with new store/telemetry/runtime tests.

### Fixed

- `sync-audit-secrets.sh` now waits for the audit-service rollout to
  finish before restarting the emitter deployments, so an emitter's
  boot-time emission can no longer hit the old pod's registry and 401.

## 0.10.0 — 2026-08-24

### Added

- **Luban-hosted small model provider (SPEC-028)**: a fourth runtime
  provider `luban` wires team-hosted (local/on-prem) OpenAI-compatible
  servers — Ollama, vLLM, llama.cpp `llama-server` — into the existing
  SPEC-024/026/027 catalog machinery with bearer-token authentication.
  New knobs: `LUBAN_API_KEY` (credential gate), `LUBAN_BASE_URL`
  (mandatory — a key without a base URL gates the provider out, since
  self-hosted endpoints have no default endpoint), `LUBAN_MODEL_NAME`
  (provider default), `LUBAN_MODELS` (fixed-point pinning, authoritative
  over live discovery), and `LUBAN_THINKING_ENABLE` (opt-in; thinking
  defaults off for small-model-safe generation). The curated series is
  empty, so pinning or discovery supplies the lineup; the fail-soft
  ladder keeps an offline server degrading to the default model only.
  New operator guide `docs/guides/luban-llm-guide.md` (stack selection,
  token-auth setup, platform wiring, verification, troubleshooting) and
  free-standing reference Ollama manifests under
  `shared/platform-ops/gitops/llm-hosting/` (Deployment/Service/Secret/
  PVC; opt-in, not wired into `dev-k8s` or `make deploy`).

- **Live model discovery with cached fallback (SPEC-027)**: the model
  catalog now tracks each configured provider's real lineup — a
  lifespan-owned background task queries the provider's OpenAI-compatible
  `/models` endpoint at startup and every
  `AGENT_MODEL_DISCOVERY_REFRESH_SECONDS` (default 1800), applies
  per-provider filters (dated `-YYYY-MM-DD` snapshots and non-chat
  modalities dropped; the provider's default model always force-included),
  and atomically swaps the catalog in place. Failed fetches degrade down a
  fail-soft ladder: in-memory last-good → Postgres-persisted last-good
  (new `model_discovery_cache` table in the sessions database — Redis
  gains no new consumers) → curated series, so restarts stay served from
  cache before the first live fetch lands. A set `<PROVIDER>_MODELS` stays
  authoritative and skips discovery for that provider; new knobs
  `AGENT_MODEL_DISCOVERY_ENABLED` (default true; `false` restores the
  pure curated-series behavior) and `AGENT_MODEL_DISCOVERY_TIMEOUT_SECONDS`
  (default 5). Curated series refreshed to current lineups (DeepSeek V4
  family; DashScope qwen3.7/3.8 decimal generations). Discovery never
  blocks chat or startup — every failure is logged and swallowed. New
  metrics: `agent_model_discovery_refreshes_total{provider,result}`,
  `agent_model_discovery_models{provider}`.

- **Multi-model runtime catalog + profile consolidation (SPEC-026)**:
  every provider with a resolvable API key now joins the model catalog
  with its curated model series — one selectable entry per model
  (entry `id` = model name, sent as `model` on chat requests) instead
  of one entry per provider. An optional `<PROVIDER>_MODELS=a,b,c`
  overrides/restricts a provider's series, and the active provider's
  `AGENTSCOPE_MODEL_NAME` is always force-included as the deploy-time
  default. Legacy provider-name ids (existing session pins) alias to
  that provider's default model; unknown ids stay fail-closed, and
  duplicate model ids across providers fail startup as a
  misconfiguration guard. Runtime profiles are consolidated: the
  per-provider `runtime-profiles/{deepseek,dashscope,openai}` overlays
  are replaced by a single generic `runtime-profiles/default` whose
  `AGENTSCOPE_PROFILE` label is decoupled from `AGENTSCOPE_PROVIDER`
  (additional providers are configured via the active profile's secret,
  not by switching profile directories). The portal model selector now
  groups options by provider.

- **Evidence persistence in session transcripts (SPEC-025)**: agent-service
  now persists `tool_call`/`tool_result` frames per assistant turn into a
  dedicated `session_evidence` store behind the existing
  `AGENT_STATE_STORE_BACKEND` / `AGENT_STATE_DB_URL` knobs. An entry cap
  (`AGENT_EVIDENCE_ENTRY_MAX_CHARS`, default 131,072) truncates oversized
  payloads with an `entry_cap` marker, and a per-session budget
  (`AGENT_EVIDENCE_SESSION_MAX_BYTES`, default 4 MiB) evicts oldest
  `tool_result` data payloads with a `session_budget` marker while keeping
  metadata. `GET /api/v1/sessions/{id}` gains an additive `evidence_turns`
  field (empty list when none stored, `null` when the store is unreadable —
  never a 500); session delete cascades evidence cleanup. The portal
  re-attaches persisted evidence to the matching assistant turns on reload,
  so replayed evidence cards are prop-identical to the live ones and show
  truncation/eviction notes plus the persisted `request_id`. Redaction is
  inherited from the tool-gateway choke point by construction. New counters:
  `evidence_store_writes_total{result}`, `evidence_frames_persisted_total`,
  `evidence_frames_truncated_total{reason}`.
- **Runtime LLM model switching (SPEC-024)**: agent-service derives a
  credential-gated model catalog at startup from per-provider env knobs
  (`<PROVIDER>_API_KEY` / `<PROVIDER>_MODEL_NAME` / `<PROVIDER>_BASE_URL`;
  the active profile's provider additionally falls back to the existing
  `AGENTSCOPE_*` knobs), so a single-provider deployment needs zero new
  configuration and providers without an API key are dropped. Operators
  select a model per chat turn (`"model": "<provider>"` on POST chat,
  `?model=` on the stream); resolution is request > session pin >
  deploy-time default, and unknown ids fail closed (HTTP 422 / an
  `unknown_model` stream error frame — no silent fallback). Selection
  pins onto the session (additive `model` column across the
  memory/Redis/Postgres session stores, exposed additively on
  `GET /api/v1/sessions/{id}`), and switching rebuilds the cached kernel
  agent with full state restore. Discovery rides a new
  `GET /api/v1/models` route (gateway policy action `models:list`,
  mirroring the chat scope) that is discovery-safe by construction —
  no credentials or base URLs leave the runtime. The `message_end` stream
  frame carries the serving model; audit gains the requested model on
  `chat_started` and the serving model on `chat_completed` on both chat
  surfaces (a stream that closes without `message_end` falls back to the
  requested model; parked turns stay unattributed). The portal composer
  gains an extensible selection bar under the message input hosting the
  model selector (the designated mount point for future per-turn
  selections): pre-seeded with the catalog default, a fixed label when
  exactly one model is configured, and fail-open hiding when discovery
  is unavailable; switching sessions re-seeds the selector from the
  session's pinned model.

### Fixed

- **HITL confirm with an evicted model pin**: `/chat/confirm` forwarded
  the raw session pin into the resume path, so a pinned model evicted by
  a discovery refresh (or a key revocation) raised `UnknownModelError`
  mid-stream — tearing the SSE stream and permanently wedging the parked
  session (the pre-claim registry entry never resolved). The confirm
  route now resolves the pin through the same request > pinned > default
  ladder as other turns, degrading a stale pin to the catalog default.
- **Fallback response provider attribution**: the provider-error fallback
  text named the active profile's provider, so a dashscope model failure
  read "provider deepseek failed". The kernel now resolves the turn's
  serving model against the catalog and attributes that provider (model
  id included); without model context the previous wording is kept.
- **Discovery cache bootstrap connection leak**: when the
  `model_discovery_cache` bootstrap DDL failed against a reachable
  Postgres, `PostgresDiscoveryCache` leaked the opened connection on
  every refresh cycle; bootstrap failures now close the connection before
  the fail-soft swallow.

## 0.9.1 — 2026-08-23

### Fixed

- **Chat stream stale-session empty reply**: the gateway answered 200 with
  a zero-frame SSE stream when the agent service rejected an unknown
  session (a stale portal pointer at a deleted session), and the portal
  rendered "(no response received)". The gateway now opens the upstream
  stream eagerly and passes 4xx through (5xx/transport → 502); the portal
  retries once without the session id so the server auto-creates a fresh
  session (legacy first-message flow) and never primes the stream pointer
  with a 404'd session. Regression-tested on both sides.
- **Markdown table header/body disconnect**: the ported renderer split the
  header row and body rows into two stacked tables; a single-pass block
  parser now emits one table with `thead`/`tbody`.

### Changed

- **Folded sidebar is a navigable icon rail**: the portal sidebar folds to
  a 64px icon rail (antd icon-only menu with tooltips) instead of
  disappearing, keeping navigation reachable while folded. Because the
  rail owns its layout space, every view — chat included — aligns
  uniformly to its right and the per-view inset hacks are removed. Rail
  sections render as hairline dividers instead of clipped group titles;
  the expanded sidebar and drawer keep the full Control/Workspace labels
  (SPEC-019 R-1).
- **Sticky request banner**: restyled for prominence and readability —
  accent border and left bar, fully opaque gradient background (no
  transcript bleed-through), bold uppercase label.
- **Pre-login session creation disabled**: the New-session button is
  disabled before sign-in like the composer (the 401 fallback message is
  kept).
- **Evidence card parity**: cards match the chat message width and
  expanded tool results are bounded to a fixed height with a vertical
  scrollbar.
- **Version tag inline** beside the sidebar logo instead of a large chip.
- **Gateway eager-open cleanup hardening**: the chat/confirm stream
  proxies finally-guard the error-body read so a failed read cannot leak
  the httpx response or client.

### Documented

- **SPEC-025 draft**: evidence persistence in session transcripts —
  durable tool-evidence frames with traceability and metrics, and
  replayed evidence cards on reopened sessions. Numbering skips SPEC-024,
  reserved on the delivery roadmap for runtime LLM model switching.

## 0.9.0 — 2026-08-22

### Added — SPEC-023: Portal framework rebuild (multi-session workspace UI on Ant Design X)

- **Framework foundation and build toolchain** (SPEC-023 R-1): the operator
  portal is rebuilt as a Vite + React 18 + TypeScript SPA on antd 6 and Ant
  Design X under `products/operator-portal/web-ui/app/` (Vitest unit suite).
  The image build gains a Node stage that compiles the bundle with the root
  `VERSION` injected as `PLATFORM_VERSION` (asserted by
  `make validate-version`); nginx serves hashed `/assets/*` immutable and the
  SPA shell `no-store`. During the rebuild the SPA shipped at `/next/`
  alongside the vanilla trio; delivery flips the runtime root to the bundle
  and removes the legacy `app.js`/`styles.css`/`index.html` tree.
- **Platform-owned SSE contract adapter** (SPEC-023 R-2): `fetch` +
  `ReadableStream` transport with abort-controller session switching, a
  schema v6 decoder mapped 1:1 from the vanilla dispatch (deltas, tool
  frames, confirmation frames, error frames, truncation-locked cards), and a
  `useChatStream()` hook exposing typed models; fixture tests cover every
  schema v6 event type.
- **Multi-session workspace UI** (SPEC-023 R-3, consuming SPEC-022 Appendix
  A): session panel with titles, relative last-active, and amber *awaiting
  approval* badges (30s poll); switch/resume with transcript load and an
  explicit `transcript_available=false` state; in-UI session delete with 409
  parked refusal and neutral 404; confirmation cards stay anchored to the
  parking session across switches; incidents gain *Continue in chat*
  deep links that pin `incident-<id>` sessions into the panel.
- **Voice input** (SPEC-023 R-4): composer microphone performs browser
  speech-to-text (Web Speech API; no audio stored) and submits turns with
  `input_modality=voice`; a recognition-language selector (en-US / zh-CN,
  browser-locale default, `localStorage` persistence) drives the recognizer
  only and never reaches the backend; confirmation decisions never carry
  modality (Invariant II, test-pinned).
- **View migration parity** (SPEC-023 R-5): audit trail (filters, cursor
  pagination, expandable envelopes, auditor/platform-admin gate),
  permissions matrix, tools and skills inventories, and the incidents
  list/detail/triage/dispatch/report flows are rebuilt on antd primitives
  with the legacy role-scoped visibility and the 15s incident auto-refresh
  preserved.
- **Docs and living state** (SPEC-023 R-6): operator-portal README, operator
  guide, configuration reference, troubleshooting guide, and dev-k8s README
  updated for the rebuilt portal (build step, cache behavior, voice
  availability); 0.9.0 version lockstep across all products.
- **In-release walkthrough fix**: the stream hook completes a turn when the
  stream closes naturally (or is abort-closed by a session switch) without
  a `message_end` frame — live capture showed the kernel may close right
  after the last delta with empty `message_delta` frames; parked
  confirmation turns keep their pending marker (fixture test pins the
  behavior).
- **In-release review remediation** (pre-push code review): the markdown
  renderer escapes quotes and restricts links to `http(s)` targets
  (closes a `javascript:`-link XSS reachable from attacker-influenceable
  replies/summaries; regression-tested); the agent-platform stream route
  passes schema-conformant `risk_level` through on `pending_calls` so the
  portal's mutating-batch badge and per-call risk tags work; stream
  cleanup is ownership-checked (no superseded-stream state wipe on session
  switch); transcript fetch failures are only treated as "empty session"
  on a real 404; stored auth JSON parses defensively.

## 0.8.1 — 2026-08-22

Patch release closing the post-v0.8.0 code review. No API, contract, or
deployment-shape changes; the dev-k8s cluster was rebuilt and redeployed
with the hardened images.

### Fixed — post-v0.8.0 code-review hardening

- **Redis session title is now atomically set-once**: titles live in a
  dedicated `session:title:{id}` key minted with `SET ... NX`, so the
  `touch_session` blob rewrite can no longer clobber a minted title and
  concurrent first turns cannot both win (the Postgres backend was
  already atomic via its `title IS NULL` guard). Adds store-level tests
  for touch/title bookkeeping on both backends.
- **Gateway session-list proxy error posture aligned**: upstream `4xx`
  now passes through unchanged like the get/delete proxies instead of
  surfacing as `502`.
- `select-runtime-profile.sh` rejects `mutating-dev` as an LLM profile
  argument; `has_pending`/`is_parked` deduplicated; the
  delete-vs-in-flight-turn limitation is documented on the delete route
  and in the agent-platform README.

## 0.8.0 — 2026-08-22

### Added — SPEC-022: Multi-session foundations (backend-first)

- **Session workspace lifecycle API (R-1)**: agent-platform gains
  `GET /api/v2/sessions` (caller's own sessions, most-recently-active
  first, capped at 50, each with a `pending_confirmation` flag),
  `GET /api/v2/sessions/{id}` now returns a server-minted title (first
  user turn, 80 chars, set once) and a best-effort transcript
  reconstructed from the kernel state snapshot
  (`transcript_available` marks the explicit fallback), and
  `DELETE /api/v2/sessions/{id}` removes the session plus its state
  snapshot. Unknown or foreign ids answer `404` (anti-enumeration);
  a parked HITL confirmation blocks delete with `409`. Session records
  now carry `last_active_at` and titles in the store.
- **Gateway session proxies**: platform-gateway serves
  `GET /api/v1/sessions` (gated by the new deny-by-default
  `session:list` action) and `DELETE /api/v1/sessions/{session_id}`
  (gated by `session:delete`, emitting a durable `session_deleted`
  audit event); both actions mirror the existing `session:create`
  grants (all five chat-capable roles; `auditor` denied). Upstream
  `4xx` passes through unchanged; transport/5xx map to `502`.
- **Voice-readiness contract (R-2)**: `POST /api/v2/chat` and the
  gateway proxy accept an optional `input_modality` (`text` | `voice`,
  default `text`). It is metadata only — logged and audited, never
  decision-bearing: authorization, tool policy, and HITL gating are
  unchanged, and the confirm surface stays click-gated. Stream schema
  stays at v6; invalid modalities fail with `422` before any upstream
  call.
- **Mutating-dev runtime profile (R-3)**: new
  `shared/platform-ops/gitops/runtime-profiles/mutating-dev/` profile
  promotes the SPEC-021 opt-in into the committed dev posture —
  `GATEWAY_MUTATING_TOOLS_ENABLED=true` is merged into
  `platform-runtime-config` by the dev-k8s overlay and the pod-delete
  RBAC now rides the profile. The profile is wired into `dev-k8s` and
  the root `OVERLAYS` gate; `select-runtime-profile.sh` preserves it
  across LLM provider switches. Base and all LLM profiles stay
  `false`.
- **Docs and matrix (R-4)**: authorization matrix documents the live
  matrix transparency for the session lifecycle actions;
  architecture overview adds `session:list`/`session:delete` (plus the
  previously missing `chat:confirm`/`tools:mutate`) to the Protected
  Actions table and corrects the bundle rule count to twelve;
  troubleshooting gains transcript-fallback and delete-409 symptom
  sections; guides index notes the portal UI follows with the portal
  rebuild spec.

### Fixed — walkthrough findings closed in-release

- **Session detail proxy error posture**: the pre-existing
  `GET /api/v1/sessions/{id}` proxy leaked upstream errors as `500`;
  it now passes upstream `4xx` (unknown/foreign session,
  anti-enumeration 404) through unchanged and maps transport/5xx to
  `502`, matching the new list/delete posture.
- **Audit contract enum drift**: the audit-service `EventType`
  vocabulary was missing `session_deleted` (present in the shared JSON
  schema), so the ingest rejected the whole batch with `400`. The enum
  is synced, and the contract test now pins model/contract enum parity.

## 0.7.0 — 2026-08-21

### Added — SPEC-021: Bounded mutating actions (first approval-gated write tool)

- **First mutating capability, triple-gated**: `k8s.delete_pod` (risk tier
  `write`) deletes one named pod — the bounded "restart" primitive whose
  owning controller recreates it. It registers only when
  `GATEWAY_MUTATING_TOOLS_ENABLED=true` (committed `false`), invokes only
  under the new deny-by-default `tools:mutate` policy action, and never
  executes without a human confirmation through the SPEC-020 HITL bridge.
  Every gate fails closed independently.
- **Risk-tier admission at the tool-gateway (R-1)**: the registry validates
  the `risk_level` vocabulary (`read`/`write`/`admin`) at registration and
  skips non-read tools while the gate is off (absent from discovery,
  `TOOL_NOT_FOUND` on invoke); the invoke path selects the required action
  by risk tier (`tools:invoke` vs `tools:mutate`) with structured 403 +
  metric on deny.
- **Policy bundle (R-4)**: new deny-by-default `tools:mutate` action granted
  to `platform-admin` and `operator` only (`allow-operators-tools-mutate`),
  synced to all four bundle copies; the live permission matrix and both
  gateway policy vocabularies carry the action.
- **HITL invariant for mutating tools (R-3)**: the agent auto-allow surface
  is read-only by construction (naming a mutating tool in
  `AGENT_GATEWAY_TOOL_AUTO_ALLOW` logs a warning and can never grant
  auto-execution); with HITL bridging disabled
  (`AGENT_HITL_CONFIRM_TIMEOUT=0`) mutating tools are excluded from the
  toolkit and each turn carries an explicit system notice instead of a
  silent omission. Stream schema moved v5 → v6: confirmation frames carry
  the optional `risk_level` per pending call, and the portal renders a
  `mutating` badge plus per-call risk tiers (cache-busting bumped).
- **Operator documentation (R-5)**: new Approval and HITL Governance Guide
  (`docs/guides/approval-and-hitl.md`) covering the four-layer approval
  model, auto-allow management, the policy-bundle approval workflow, and the
  HITL knobs; tool guide gains the `k8s.delete_pod` inventory row and
  activation checklist; configuration reference gains the mutating action
  approval chain; troubleshooting gains four SPEC-021 symptoms.
- **Deployment and e2e (R-6)**: dev-k8s commits
  `GATEWAY_MUTATING_TOOLS_ENABLED=false` with a documented opt-in path and a
  separate, out-of-kustomization pod-delete RBAC manifest (pods `delete`
  only); new deterministic smoke test
  `shared/platform-ops/e2e/mutating-demo.sh` asserts the deny-by-default
  posture (or the opt-in chain incl. the observer 403) and an optional HITL
  chat leg (park → approve → audit chain).

## 0.6.1 — 2026-08-21

### Fixed — Durable OTLP ingest credential provisioning

- **OTLP push 401 regression repaired**: five of the seven services
  (audit-service, identity-service, incident-service, platform-gateway,
  skills-hub) were exporting traces/metrics/logs anonymously because
  sibling secret-sync scripts re-applied their runtime Secrets from
  regenerated env files, wiping `OTEL_EXPORTER_OTLP_HEADERS`. All seven
  Secrets now carry the OpenObserve ingest header and push is
  authenticated end to end.
- **`sync-otel-secrets.sh` merges the OTLP header cluster-side** via
  `kubectl patch` (OTEL key only, all other keys preserved) instead of
  rebuilding Secrets from local env files; a missing Secret is created
  with just the header. The agent-platform runtime profile file stays
  authoritative for its own Secret, with the cluster merge as fallback.
- **Sibling sync scripts preserve the header**: the env-file rewrites
  in `sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, and
  `sync-skills-secrets.sh` capture and re-append any existing
  `OTEL_EXPORTER_OTLP_HEADERS` line, so a credential-less `make deploy`
  can no longer resurrect the anonymous-push state.

## 0.6.0 — 2026-08-21

### Added — SPEC-020: HITL confirmation bridging

- **Kernel ASK to portal approve/deny** (SPEC-020): non-allow-listed gateway
  tool batches no longer park silently. agent-platform translates the kernel's
  `RequireUserConfirmEvent` into a `confirmation_request` SSE frame (stream
  schema v3 → v4), parks the reply in an in-memory confirmation registry, and
  resumes it via `POST /api/v2/chat/confirm` (`UserConfirmResultEvent`; the
  confirmer's delegated token rides any resulting tool invocation). The entry
  is claimed pre-header, so a duplicate confirm fails closed with 404.
  Pending confirmations expire after `AGENT_HITL_CONFIRM_TIMEOUT` seconds
  (default 600; `0` disables bridging); an expired park is closed via
  `UserInterruptEvent` on the confirm attempt (410) or the next chat turn,
  never silently evicted; parked sessions reject new chat turns with 409.
- **The allow-list is the only auto-approval surface** (SPEC-018 R-1 hardening):
  the permission middleware now answers every non-allow-listed tool with an
  explicit ASK instead of delegating to AgentScope's `PermissionEngine`, whose
  read-only fast path auto-allows read-only invocations in every mode and was
  silently skipping `AGENT_GATEWAY_TOOL_AUTO_ALLOW` — under the locked
  agentscope 2.0.6 no read-only tool outside the allow-list ever parked.
  Unvetted read-only tools now park as confirmation cards like any other
  ASK-gated batch.
- **Confirmed calls are never re-asked** (SPEC-020 live-check fix): agentscope
  re-traverses the permission middleware chain for calls the operator already
  confirmed (state ALLOWED) and expects the built-in resolution to
  short-circuit them. The middleware now delegates ALLOWED-state calls so an
  approved batch actually executes on resume instead of re-parking the reply
  in an endless approve loop.
- **Portal card status reaches its final state** (SPEC-020 live-check fix):
  the confirmation card's status line now always switches from the
  in-progress "Approving…/Denying…" text to the final outcome once the
  decision is applied; previously only the badge updated and the line stayed
  on "Approving…" forever.
- **Full tool output on evidence cards** (SPEC-020 live-check enhancement):
  stream schema v5 adds an optional `data` field to `tool_result` frames —
  the full tool payload when its serialized size stays within
  `AGENT_TOOL_DATA_MAX_CHARS` (default `32000`; oversized payloads remain
  audit-trail-only). The portal renders it behind a "Show full output"
  expander on the evidence card, so operators can inspect the complete
  result (e.g. all requested log lines) regardless of how the model chooses
  to phrase its reply. Multi-line text fields (such as the `logs` blob from
  `k8s.get_pod_logs`) render as raw log-style blocks with wrapping lines
  instead of one escaped JSON string.
- **Expiry can no longer race an in-flight resume** (post-delivery review
  fix): the TTL cleanup path now claims the registry entry through
  `take_for_expiry` before interrupting, so an approved resume that
  outlives its TTL is never aborted mid-stream and two concurrent expiries
  cannot double-fire; a turn racing such a resume gets a retryable 409.
- **Confirm card always reaches a final state** (post-delivery review fix):
  the portal locks the confirmation card on mid-stream `error` frames and
  when the confirm stream ends without a `confirmation_result`, instead of
  leaving it on "Approving…/Denying…".
- platform-gateway gains `POST /api/v1/chat/confirm` under the new
  deny-by-default `chat:confirm` action (granted to `platform-admin`,
  `approver`, `operator`, `developer`; `read-only-observer` excluded) and
  emits a durable `confirmation_decided` audit event, tee'd off the
  kernel-applied `confirmation_result` frame so only actually-applied
  decisions reach the trail.
- Operator portal chat renders an inline Approve/Deny confirmation card
  (pending tools with collapsible parameters, decision locks the card, 410
  renders as expired) and resumes the stream in place; buttons hide for
  roles without `chat:confirm`.

## 0.5.0 — 2026-08-21

### Added — SPEC-019: Portal transparency and navigation

- **Portal transparency and navigation** (SPEC-019): sectioned sidebar (Chat / Control / Workspace) with auto-hiding sections, live permission matrix endpoint (`GET /api/v1/policy/matrix`) rendered from the enforced policy bundle with server-side role scoping, Permissions view, and read-only Tools and Skills inventory views behind new platform-gateway proxies (new `policy:read` / `skills:read` actions granted to all operational roles); version chip consolidated into the logo row. The Tools catalog table uses fixed column geometry so the short category/risk columns are not starved by the free-form description column.

## 0.4.0 — 2026-08-20

### Added — Platform versioning discipline

- New root `VERSION` file (semver) as the single source
  of truth for the platform version; all products and the portal track it in
  lockstep (`pyproject.toml`, `metadata.py` `SERVICE_VERSION`, portal
  `PLATFORM_VERSION` — all bumped from the stale `0.1.0`).
- New `make validate-version` gate (wired into `make verify`) fails on any
  drift between `VERSION` and the product/portal constants.
- Coordinated image tags now carry the semver prefix
  (`<semver>-<prefix>-<gitsha>`), and this changelog closes entries into
  versioned sections (`0.3.0`, `0.2.0`, `0.1.0`). Versioning policy is
  documented in `CONTRIBUTING.md`.

### Added — SPEC-016: Postgres session store backend

- agent-platform gains a third session store backend:
  `SESSION_STORE_BACKEND=memory|redis|postgres` (unknown values now fail
  startup instead of silently defaulting). The Postgres backend persists
  sessions in a dedicated `sessions` database with idle-TTL semantics
  matching the Redis store (refresh folded into reads, bounded
  opportunistic sweep) and applies its DDL idempotently on startup.
- `SESSION_DB_URL` supplies the DSN (required for `postgres`); unreachable
  databases fail open to the in-memory backend and increment
  `session_store_fallbacks_total`. `session_store_backend` gauge and
  `agent-health.schema.json` learn the `postgres` value.
- dev-k8s switches the deployed overlay from Redis-backed sessions to
  Postgres (`SESSION_REDIS_*` removed; Redis remains for kernel
  coordination only): new `infra/create-sessions-db.sql` initdb entry and
  `sync-sessions-db.sh` for existing clusters, wired into `make deploy`.

### Added — SPEC-017: kernel utilization and conversation durability

- agent-platform now drives the AgentScope kernel's own tuning surfaces
  (R-1): `AGENTSCOPE_MAX_ITERS` (ReAct loop cap),
  `AGENTSCOPE_CONTEXT_TRIGGER_RATIO` (long-term memory trigger),
  `AGENTSCOPE_TOOL_RESULT_LIMIT` (tool result truncation),
  `AGENTSCOPE_TIMEZONE` (runtime-state injection), and
  `AGENTSCOPE_MODEL_MAX_RETRIES` (model retries). Defaults mirror
  agentscope's own, every value is validated at startup, and each
  constructed agent logs its effective configuration once.
- `/api/v2/chat` accepts an optional `response_schema` and returns a
  kernel-validated `structured_output` (R-2): incident-service triage
  turns send the triage-report JSON schema and prefer the structured
  output, with the fenced-block parser retained as fallback; server-minted
  attribution forcing is unchanged. The default system prompt is now
  format-neutral about report delivery.
- Conversation durability (R-3): the kernel-serializable agent state is
  snapshotted after every completed turn and restored on agent
  construction via a new `AgentStateStore`
  (`AGENT_STATE_STORE_BACKEND=memory|postgres`, `AGENT_STATE_DB_URL`,
  `AGENT_STATE_TTL_SECONDS`), sharing the SPEC-016 `sessions` database.
  Snapshot/restore never fails a turn; corrupt rows are discarded with a
  counter. Session deletion also removes persisted state, and `/health`
  surfaces the `agent_state` backend.

### Added — SPEC-018: Kernel middleware alignment

- The agent-platform kernel moves all cross-cutting behavior onto
  AgentScope's supported `MiddlewareBase` hooks and drops the private
  surfaces: the `GatewayFunctionTool` subclass is gone (permission
  decisions now come from `GatewayPermissionMiddleware.on_check_permission`
  with the unchanged `AGENT_GATEWAY_TOOL_AUTO_ALLOW` allow-list), the
  per-request toolkit rebuild and `agent.toolkit` mutation are gone
  (evidence frames now come from `ToolEvidenceMiddleware.on_acting` with a
  request-scoped sink; toolkits are cached per delegated token), and tool
  closures read the delegated token from a contextvar at call time so
  portal token refresh no longer needs an agent rebuild. The
  `agent-stream-event.schema.json` frame contract is unchanged.
- Opt-in kernel capabilities via new settings, each validated at startup:
  `AGENTSCOPE_KERNEL_TRACING` (out-of-box `TracingMiddleware` for OTel
  agent/LLM/tool spans through the existing OTLP pipeline),
  `AGENTSCOPE_REPLY_TOKEN_BUDGET` (+ `_INPUT_TOKEN_WEIGHT` /
  `_OUTPUT_TOKEN_WEIGHT`, out-of-box `ReplyBudgetControlMiddleware`), and
  `AGENTSCOPE_TASK_TOOLS_ENABLED` (built-in `TaskCreate`/`TaskGet`/
  `TaskList`/`TaskUpdate`, persisted through the SPEC-017 agent state
  store). Unset deployments behave exactly as before.
- dev-k8s enables `AGENTSCOPE_KERNEL_TRACING=true` for the deployed
  agent-platform and documents recommended starting values for the
  budget/task-tools opt-ins.
- Delivery includes the utilization re-audit memo
  (`docs/workspace/agentscope-utilization-audit.md`) with the adopted /
  kept-platform-owned / spike-needed decision matrix, the entrypoint
  surface clarification, and the HITL bridging / ASK → DENY future-scope
  carry-forward.

### Changed

- agent-platform upgrades the AgentScope kernel from `2.0.4.post1` to
  `2.0.6`: O(n) stream accumulation and reused OpenAI clients on the
  streaming path, the OTel cross-task detach fix, preserved error state in
  tool responses, and the 2.0.5 agent-loop/permission fixes. The kernel now
  also ships a SQLAlchemy storage backend upstream (`AsyncSQLAlchemyStorage`).

## 0.3.0 — 2026-08-17

### Added — SPEC-015: Incident Triage and Collaboration (Release 3)

- New `shared/shared-contracts/schemas/incident.schema.json` and
  `triage-report.schema.json` (R-1): the canonical incident envelope and the
  structured triage output contract; incident-service models bind to both
  via contract tests.
- New `products/incident-service` product (R-2): FastAPI on the shared
  `base-uv` image mirroring the audit-service chassis. Alertmanager v4
  webhook intake (`INCIDENT_WEBHOOK_TOKEN` bearer, fail-closed 503 when
  unconfigured, `groupKey` fingerprint dedupe, resolution handling), manual
  intake for the portal report form, and an `IncidentStore` protocol with
  in-memory and Postgres backends (`incidents` database). Query auth uses
  the dedicated `INCIDENT_QUERY_CLIENTS` Basic registry plus projected
  workload tokens.
- Operator-initiated triage (R-3): `POST /api/v1/incidents/{id}/triage` runs
  one agent turn in the dedicated `incident-<id>` session, relaying the
  operator's delegated bearer, and captures the outcome as a validated
  fenced `triage-report` JSON block — `triaged` with report and connector
  dispatch, or `triage_failed` with the raw agent text preserved. The agent
  system prompt gains the triage-report output discipline. agent-platform
  gains named-session support (`POST /api/v2/sessions` accepts an optional
  caller-supplied `session_id`, idempotent for the owner); because sessions
  are single-owner, re-triage by a second operator falls back to
  `incident-<id>--<operator>`, and report attribution
  (`session_id`/`generated_at`/`generated_by`) is server-minted, never
  taken from agent output.
- Read-only incident tools (R-4): tool-gateway's `IncidentsConnector`
  registers `incidents.list` / `incidents.get` (Basic-auth httpx transport,
  structured error mapping), gated on `GATEWAY_INCIDENTS_SERVICE_URL`; both
  join `DEFAULT_AUTO_ALLOWED_TOOLS`. No mutating incident tool exists —
  the SPEC-007 read-only invariant holds.
- Connector framework (R-5): config-driven `Connector` registry
  (`INCIDENT_CONNECTORS`, unknown names fail startup) with the built-in
  `audit` sink emitting `incident_triaged` events to audit-service; dispatch
  outcomes persist per incident and never fail the triage path. Slack/Jira
  adapters are documented contract-only.
- Portal and gateway surfaces (R-6/R-7): platform-gateway proxies the
  incident list/get/report/create/triage routes under three new policy
  actions (`incident:read` / `incident:create` / `incident:triage`, bundle
  now eight rules) and relays identity; the operator portal gains the
  Incidents panel (filterable list with auto-refresh, report detail, Run
  triage, Report incident form, Continue in chat, connector dispatch
  outcomes) and the audit view gains the `incident_triaged` type.
- Deployment and demo: dev-k8s overlay for incident-service (deployment,
  service, postgres `incidents` database via initdb ConfigMap),
  `sync-incident-secrets.sh` wired into `make deploy`
  (`SKIP_INCIDENT_SECRETS` opt-out), `sync-audit-secrets.sh` registers
  incident-service as a fourth audit emitter, and
  `shared/platform-ops/e2e/incident-demo.sh` asserts intake auth, dedupe,
  resolution, query visibility, gateway triage, and the audit dispatch.
- Docs: release note
  `docs/agentic-aiops-platform/release-notes/2026-08-17-r3-incident-triage-and-collaboration.md`,
  new [Incident Triage and Collaboration Guide](docs/guides/incident-guide.md)
  (Alertmanager wiring, lifecycle and dedupe semantics, portal workflow,
  triage interpretation, re-triage collaboration), incident symptoms in
  troubleshooting, updated guides (getting-started Incident Triage tour,
  configuration reference, tool configuration, architecture overview),
  product and dev-k8s READMEs.

## 0.2.0 — 2026-08-15

### Added — OpenObserve Telemetry Enablement (SPEC-005 completion)

- The opt-in OTel push pipeline is now live for all six services against the
  in-cluster OpenObserve backend: `OTEL_ENABLED=true` and the org-scoped OTLP
  HTTP endpoint move into the shared ConfigMap, and the six `telemetry.py`
  pipelines switch from OTLP gRPC to OTLP **HTTP/protobuf** (the protocol
  OpenObserve ingests; dependency swapped to
  `opentelemetry-exporter-otlp-proto-http`).
- New **OTLP log bridge**: when enabled, each service attaches an OTel
  `LoggingHandler` to the root logger, mirroring every structured JSON record
  as an OTLP log with automatic trace/span association (via the non-deprecated
  `opentelemetry-instrumentation-logging` handler). JSON stdout remains the
  audit source of truth; OTel's own loggers are detached from the root to
  prevent export-failure recursion. Gating and fail-open semantics unchanged.
- skills-hub sync-loop depth: `skills.sync` spans (source id/type, result,
  accepted count) and `skills.git.checkout` spans (source id, requested ref)
  with checkout errors recorded **after** scrubbing the git token — the
  token-injected clone URL never reaches span attributes or events.
- New `sync-otel-secrets.sh` (wired into `make deploy`): computes the Basic
  auth header from `OO_ROOT_USER_EMAIL`/`OO_ROOT_USER_PASSWORD` and upserts
  `OTEL_EXPORTER_OTLP_HEADERS` into all six runtime-secrets Secrets, then
  restarts the workloads. Unset credentials skip with a clear message — push
  then 401s and fails open. `SKIP_OTEL_SECRETS=true` escape hatch for CI.
- Docs: observability conventions now define the OpenObserve backend, OTLP
  HTTP protocol, and log-bridge semantics; configuration reference documents
  the three `OTEL_*` variables and the header contract per Secret;
  troubleshooting gains a "no data in OpenObserve" section.

### Added — Git-Federated Skill Sources, End to End (R2 gap-closure)

- The skills-hub image now ships `git`: the sync engine shells out to it for
  `type=git` sources, but the base-uv-derived image lacked the binary, so git
  federation could never have worked in-cluster. Git stays out of the shared
  base image.
- `SKILLS_SOURCES` git entries accept an optional `path` — the subdirectory
  within the checkout to ingest (real team repos keep skills next to other
  code). Path-escaping values are rejected at config parse; a missing subpath
  fails the sync with a clear error while the previous snapshot keeps serving.
- dev-k8s wires a production-parity git source (`platform-skills`, tracking
  this repository's `shared/platform-ops/skills`): non-secret `url`/`ref`/
  `path` in the ConfigMap, the PAT only in `skills-hub-runtime-secrets`.
  `sync-skills-secrets.sh` provisions `SKILLS_GIT_TOKENS` when
  `SKILLS_GIT_TOKEN` is exported (never echoed, never committed).
- Operator portal: successful `skills.*` tool calls now render the matched
  skills as **Cited guidance** chips (title + namespaced id) under the
  tool-evidence card, making the guidance behind an answer glanceable.

### Refined — Skills and Grounded Guidance (post-delivery)

- Search prefilter semantics now match the deterministic scorer: query words
  are tokenized and OR-joined into `to_tsquery`, so multi-word queries keep
  partial matches (`plainto_tsquery` previously AND-ed the words and silently
  dropped them); a tokenless query short-circuits to an empty success without
  a database round-trip.
- New read-only `skills.list` tool in tool-gateway (catalog discovery:
  summaries without bodies, source/tag filters, capped offset pagination),
  mapped to the existing `GET /api/v1/skills` endpoint; auto-allowed for the
  agent alongside `skills.search` / `skills.get`, and the system prompt now
  teaches catalog discovery via `skills.list`.
- skills-hub prunes store records whose source is no longer configured at
  startup, so removing a `SKILLS_SOURCES` entry immediately retires its
  skills from search, list, and get.
- New [Skills and Guidance Operations Guide](docs/guides/skills-guide.md):
  day-2 content operations for operators — adding, revising, and removing
  skills and sources (local ConfigMap-backed and git), pre-flight
  validation, verification, metrics, and troubleshooting.

### Added — SPEC-014: Skills and Grounded Guidance

- New `shared/shared-contracts/schemas/skill.schema.json` (R-1): canonical
  skill envelope (`skill_id`, `title`, `description`, `tags`, `version`,
  `source_id`, `source_path`, optional `source_ref` / `source_url`
  attribution, `updated_at`, `body`) plus the `skill-format.md` frontmatter
  convention (size caps, slug rule, and an open-source skill discovery
  appendix). Contract tests bind skills-hub Pydantic models to the schema.
- New `products/skills-hub` product (R-2): FastAPI service mirroring the
  audit-service chassis — frozen-dataclass `SKILLS_*` settings, structured
  logging, `/health`, `/metrics` (incl. `skills_syncs_total{source,result}`),
  federated multi-source ingestion (`local` directories and `git`
  repositories, namespaced `<source_id>/<slug>` ids), per-source atomic sync
  with jitter (a failed sync keeps the prior slice), and a `SkillStore`
  protocol with in-memory and PostgreSQL backends selected via
  `SKILLS_STORE_BACKEND`. Includes a standalone validator CLI
  (`python -m skills_hub.validate <dir>`) for team pre-flight checks.
- Retrieval API (R-3): `GET /api/v1/skills` (source/tag filters, capped
  offset pagination), `GET /api/v1/skills/{skill_id:path}` (full record,
  structured 404), `GET /api/v1/skills/search` (deterministic ranking —
  title ×3 / tags ×2 / body ×1 with `skill_id` tie-break, excerpt ≤ 400
  chars, provenance), and an auth-exempt `/api/v1/skills/status`. Query auth
  uses a dedicated Basic registry `SKILLS_QUERY_CLIENTS` plus projected
  workload tokens — deliberately distinct from the SPEC-013 shared
  ingest/query credential.
- Skills connector in tool-gateway (R-4): read-only `skills.search` /
  `skills.get` tools with Basic-auth httpx transport (10s timeout) and
  structured error mapping (404 → `SKILL_NOT_FOUND`, unreachable →
  `TOOL_EXECUTION_ERROR`); registered only when `GATEWAY_SKILLS_SERVICE_URL`
  is set (unset preserves today's tool surface byte-for-byte). Settings:
  `GATEWAY_SKILLS_SERVICE_URL`, `GATEWAY_SKILLS_CLIENT_ID`,
  `GATEWAY_SKILLS_CLIENT_SECRET`.
- Runbook-aware answers (R-5): `DEFAULT_SYSTEM_PROMPT` gains the skills
  discipline (consult skills for procedure/remediation, cite by title, keep
  guidance separate from live cluster evidence, report no-match honestly);
  `skills.search` / `skills.get` join the default auto-allow list. Portal
  evidence panels render skills frames without changes.
- Deployment and sample content (R-6): dev-k8s deploys `skills-hub` with two
  sample sources — `sre-alerting` (six adapted Prometheus Operator alert
  runbooks, Apache-2.0) and `platform-runbooks` (five adapted Kubernetes
  troubleshooting guides, CC-BY-4.0), each with NOTICE attribution and a
  team contribution README. Postgres gains a `skills` database (initdb
  ConfigMap for fresh clusters; `sync-skills-secrets.sh` idempotently creates
  it and provisions the shared query secret on existing clusters,
  `SKIP_SKILLS_SECRETS=true` opt-out). Deterministic e2e smoke test
  `shared/platform-ops/e2e/skills-demo.sh` asserts source sync, alert-name
  search ranking, and the `skills.search` tool_call/tool_result frame pair in
  a scripted chat; getting-started gains a Skills demo tour (UAT checklist +
  operator training).

### Added — SPEC-013: Durable Audit Trail

- New `shared/shared-contracts/schemas/audit-event.schema.json` (R-1):
  canonical audit-event envelope (`event_id`, `occurred_at`, `event_type`,
  `service`, `request_id`, `subject`, `username`, optional `actor`
  delegation chain, `roles`, optional `session_id`, `outcome`, typed
  `details`); covers `tool_invoked`, `policy_decision`, `token_exchange`,
  `session_created`, `chat_started`, `chat_completed`. Contract tests bind
  emitter and audit-service Pydantic models to the schema.
- Canonical policy bundle: new `audit:read` action granted to `auditor`
  and `platform-admin` only (deny-by-default for all other roles);
  synced to all consumer copies via `make sync-policy`.
- New `products/audit-service` product (R-2): FastAPI service with
  frozen-dataclass `AUDIT_*` settings, structured logging, `/health`,
  `/metrics`, and an `AuditStore` protocol with two backends —
  `InMemoryAuditStore` (dev/tests) and `PostgresAuditStore` (psycopg v3
  async pool, keyset pagination), selected via `AUDIT_STORE_BACKEND`.
- Authenticated non-blocking ingest (R-3): `POST /api/v1/audit/events`
  accepts batches (capped by `AUDIT_MAX_BATCH`), rejects malformed events
  with 400 + counter. Auth via static Basic client registry
  (`AUDIT_INGEST_CLIENTS`) or projected workload tokens
  (`AUDIT_WORKLOAD_*`), mirroring SPEC-008/009 credential vocabulary.
- Fire-and-forget audit emitters (R-3) in tool-gateway, platform-gateway,
  and identity-broker: 2s bounded timeout, failure counted in
  `audit_emits_total`, never blocks or fails the originating request;
  feature-gated by `GATEWAY_AUDIT_SERVICE_URL`,
  `PLATFORM_GATEWAY_AUDIT_SERVICE_URL`, and `IDENTITY_AUDIT_SERVICE_URL`
  (unset preserves log-only behavior exactly). Structured-log emission
  retained alongside.
- Permission-scoped query API (R-4): `GET /api/v1/audit/events` with
  filters (`username`, `session_id`, `request_id`, `event_type`,
  `service`, `since`/`until`), newest-first cursor pagination, verbatim
  envelope round-trip. platform-gateway proxies the route under
  `/api/v1/audit/*` with portal-token verification and
  `enforce_policy("audit:read")` (structured 403 on deny).
- Operator portal audit view (R-5): read-only audit trail function view
  with filter bar, newest-first table, cursor pagination, and expandable
  event envelopes; navigation entry rendered only for `auditor` /
  `platform-admin` roles.
- Operator portal shell: two-column layout replacing the stacked panels —
  left sidebar carries the logo and the function list (Chat, Settings &
  Debug, Audit trail); the main column shows one function at a time with
  state preserved across switches. Narrow screens (≤800px) collapse the
  sidebar into a hamburger-triggered off-canvas drawer (the topbar stays
  above the open drawer so the hamburger always toggles).
- Operator portal sidebar footer: a user card (initials avatar, username,
  icon-only Sign in / Sign out with tooltips; clicking the user opens a
  popup menu showing granted roles, extensible with future user-related
  info) and a platform version card — separated from the function list.
- Operator portal polish: sticky audit-table column headers inside the
  scroll area, `:focus-visible` keyboard focus rings, and
  `prefers-reduced-motion` guards on blinking/spinning animations.
- Retention and bounded growth (R-6): `AUDIT_RETENTION_DAYS` (default 30)
  window eviction + `AUDIT_MAX_EVENTS` hard cap, batched deletes,
  eviction counted in metrics, never blocks ingest; window and store size
  exposed in `/health` / `/metrics`.
- dev-k8s overlay: PostgreSQL StatefulSet + PVC + Service, audit-service
  deployment/service/runtime-config (`AUDIT_STORE_BACKEND=postgres`),
  `sync-audit-secrets.sh` for shared ingest credentials (wired into
  `make deploy` with skip switch), emitter `*_AUDIT_SERVICE_URL` env in
  the three emitting services, policy ConfigMap updated.
- Root Makefile: `audit-service` added to `PYTHON_PRODUCTS`,
  `IMAGE_PRODUCTS`, `.images.env`, and the kind-load list.
- Operator guides updated: audit-service in the architecture topology and
  service inventory, `AUDIT_*` variables in the configuration reference,
  audit-service activation checklist, and troubleshooting entries for
  missing events, ingest 401, and query denial.

### Fixed — SPEC-013: Durable Audit Trail

- `PostgresAuditStore.add` now wraps `details` in `psycopg.types.json.Jsonb`
  before insert; a raw dict is not adaptable for the `JSONB` column and
  every ingest failed with `psycopg.ProgrammingError: cannot adapt type
  'dict'`. Caught during the dev-k8s live test (unit tests exercised the
  in-memory backend); regression test added against the fake psycopg
  driver (audit-service tests 67 → 68).

## 0.1.0 — 2026-08-11

### Added — SPEC-012: Operator Guide and Deployment Documentation

- New operator-facing documentation suite under `docs/guides/`:
  - `getting-started.md` (R-1): prerequisites, build→deploy→verify walkthrough,
    secrets provisioning, end-to-end verification checklist.
  - `configuration-reference.md` (R-2): feature activation matrix, cross-service
    dependency chains (token delegation, identity, tool relay), per-service
    environment variable tables, secret contracts, runtime profiles, policy
    management workflow.
  - `troubleshooting.md` (R-3): symptom-based diagnostics for nine common
    failure modes (access not granted, no tools, login fails, stream stalls,
    policy denied, Elastic not configured, ErrImagePull, policy load failure,
    token expiry).
  - `tool-configuration.md` (R-4): tool inventory (K8s + Elastic), connector
    activation checklists, RBAC configuration, redaction engine reference,
    new-connector extension guide.
  - `architecture-overview.md` (R-5): service topology, request flow, trust
    chain, token delegation, workload identity, RBAC model, with Mermaid
    diagrams.
  - `README.md`: guide index and navigation.
- Root Makefile: added `sync-policy` target (copy canonical `policy-default.yaml`
  to all consumer locations) and `validate-policy` target (validate bundle
  against `policy-rule.schema.json`); `validate-policy` wired into `make verify`.
- New `shared/shared-contracts/scripts/validate_policy.py` validation script.

### Changed — Evidence and audit groups follow their reply inline

- operator-portal: replaced the bottom evidence drawer with per-turn
  collapsible groups rendered inline directly after the agent reply they
  ground. Each question's evidence cards and audit card follow that
  answer; groups stay collapsed by default (the summary line shows the
  counts) and are created lazily on the first tool frame, so purely
  conversational turns leave no empty group.

### Changed — Evidence and audit cards are kept per turn

- operator-portal: evidence and audit cards are no longer wiped when the
  next question is sent. Each chat turn gets its own collapsible group in
  the evidence drawer ("Turn N · HH:MM · counts"), created lazily on the
  first tool frame and bounded to the last 20 turns; the drawer summary
  shows session totals. Logout resets the drawer.

### Changed — Evidence moved to a collapsed drawer; audit card; sticky scroll

- operator-portal: tool evidence no longer renders inline in the chat
  column (it crowded out the streamed answer and fought the auto-scroll).
  It now lives in a dedicated collapsed drawer above the input bar with a
  live summary line ("N calls · X ok · Y denied"), matching the existing
  Settings & Debug drawer idiom.
- Added an "Audit trail · this turn" card assembled from streamed evidence
  (tool, status, executed_at, duration, risk, source) plus request/session
  IDs — self-service inspection of the caller's own turn. The authoritative
  backend audit trail (cross-user, persistent) remains a future spec.
- Sticky smart-scroll: the chat view only follows the stream while the
  reader is near the bottom, so growing evidence no longer yanks the
  viewport away from text being read.

### Fixed — Rotated delegated tokens no longer strand sessions without tools

- agent-platform: delegated tokens rotate mid-session (portal token refresh,
  300s TTL), but tool discovery only ran at agent creation — keyed by
  session — so a rotated token never got tool definitions and every
  subsequent turn injected the no-tools notice until browser refresh.
  `_build_request_toolkit` now discovers with the current token on cache
  miss, and empty discovery results are never cached (both per-request and
  `_ensure_toolkit` paths) so a transient failure can no longer poison the
  cache. `_ensure_toolkit` additionally reuses the discovery result instead
  of discovering twice.

### Fixed — Evidence panel frames, audit log visibility, cluster-wide read access

- agent-platform: the stream event adapter (`AgentStreamEvent` /
  `_normalize_stream_event`) now passes v3 `tool_call`/`tool_result` frames
  through untouched. Previously the pre-v3 Pydantic model coerced every tool
  frame to `message_delta` and stripped all evidence fields, so the portal
  evidence panel never rendered despite kernel and portal support.
- All four Python services: `configure_logging()` now raises the root logger
  to INFO (overridable via `LOG_LEVEL`) at app startup. Uvicorn's WARNING
  default silently discarded every `log_event` record — including the
  `tool_invoked` audit trail and `http_request` middleware events.
  Convention codified in `shared-contracts/observability-conventions.md`.
- dev-k8s: tool-gateway RBAC upgraded from a namespaced Role to a
  cluster-wide read-only ClusterRole (get/list/watch on core, apps, batch,
  networking, and autoscaling resources) so the agent can health-check any
  namespace (e.g. `argocd`). No mutating verbs are granted; tool surface and
  deny-by-default policy remain the enforcement layers.

### Changed — Permission auto-approval narrowed to an explicit allow-list

- agent-platform: the `RequireUserConfirmEvent` bypass now applies only to
  read-only tools on a vetted allow-list (`DEFAULT_AUTO_ALLOWED_TOOLS`,
  overridable via `AGENT_GATEWAY_TOOL_AUTO_ALLOW`), instead of every
  read-only tool. Anything outside the allow-list keeps the interactive ASK
  default. Admission, policy enforcement, and per-invocation audit logging
  by the tool-gateway are unchanged. (L3 security review remediation,
  CWE-862.)

### Added — SPEC-011: Observability Connector and Evidence Panels

- Extended the agent stream event contract (`agent-stream-event.schema.json`,
  v3) with `tool_call` and `tool_result` event types carrying tool name,
  call ID, parameters, status, evidence metadata, and data summary.
- agent-platform: toolkit closures now post `tool_call`/`tool_result` events
  to a per-request `asyncio.Queue`; trace events are drained into the SSE
  stream alongside text deltas. `data_summary` is truncated to
  `AGENT_TOOL_DATA_SUMMARY_MAX_CHARS` (default 2000) with a structured
  marker; full payloads stay in audit logs only.
- tool-gateway: new Elastic observability connector
  (`elastic.search_logs`, `elastic.get_service_health`,
  `elastic.get_active_alerts`) following the Kubernetes connector pattern
  (lazy init, executor-based sync, feature-gated by `GATEWAY_ELASTIC_ENABLED`).
  Auth supports API key (preferred) and basic auth with TLS verification
  toggle. Added `elasticsearch>=8.0,<9.0` dependency.
- operator-portal: evidence panel renders tool call/result cards with status
  badges, collapsible parameters and data summaries, and evidence metadata.
  Panel appears on first `tool_call` event and clears on each new request.
- dev-k8s overlay: `GATEWAY_ELASTIC_ENABLED=false` with commented Elastic env
  var examples in tool-gateway `runtime-config.env`; gated off by default.

### Fixed — Token delegation secrets auto-provisioning

- New `sync-delegation-secrets.sh` script generates a shared client secret,
  creates both `platform-gateway-runtime-secrets` and
  `identity-service-runtime-secrets` K8s secrets, and restarts the affected
  deployments. Previously these optional secrets were not provisioned by
  `make deploy`, causing silent delegation failures — the agent ran without
  tools ("access not granted").
- `make deploy` now calls `sync-delegation-secrets.sh` automatically after
  the overlay apply; set `SKIP_DELEGATION_SECRETS=true` when secrets are
  injected externally (e.g. CI pipelines).
- dev-k8s README: new "Token Delegation Secrets" section with usage,
  verification commands, and skip switch.

### Changed — Observer read-only tool access + anti-fabrication guardrail

- Policy bundle now grants `read-only-observer` the `tools:list` and
  `tools:invoke` actions, aligning the implementation with the authorization
  matrix (observers may perform tier-0 reads, and every registered tool is
  read-only). Previously observers were denied tool discovery (403), which
  left the agent with an empty toolkit and caused it to emit fabricated
  "health check" reports. All four byte-identical copies updated
  (shared-contracts, tool-gateway, platform-gateway, dev-k8s overlay).
- agent-platform system prompt hardened against fabrication: the agent must
  ground every factual claim in real tool output and state explicitly when no
  tools are available or a call fails, instead of inventing metrics/statuses.

### Fixed — Agent toolkit registration (AgentScope 2.x) + deterministic no-tools guard

- agent-platform: gateway tools are now built with the AgentScope 2.x API —
  `FunctionTool` objects passed to `Toolkit(tools=[...])` instead of the
  removed `Toolkit.add()`, which raised `AttributeError` per tool and left
  every session with an empty toolkit (zero tool invocations, fabricated
  health reports). The gateway's `parameters_schema` is bound explicitly
  (closures expose only `**kwargs`) and normalized to the object-with-
  properties shape AgentScope validates.
- agent-platform: deterministic anti-hallucination guard — when a tool
  gateway is configured but zero tools are registered for the turn, the
  kernel injects an explicit "no operational tools" notice into that turn
  instead of relying solely on the standing system prompt.
- agent-platform: gateway tools now auto-approve read-only execution.
  AgentScope 2.x defaults custom function tools to an interactive
  user-confirmation prompt (`RequireUserConfirmEvent`), which a headless SSE
  stream can never answer — the agent stalled and the portal showed "No
  response received". `GatewayFunctionTool` returns ALLOW for read-only
  tools (admission and policy are enforced by the tool-gateway), mirroring
  AgentScope's MCP adapter; non-read-only tools still require confirmation.

### Fixed — Deployment env collisions and portal stream rendering

- All five dev-k8s app deployments set `enableServiceLinks: false`:
  Kubernetes' legacy service-link env vars (e.g.
  `AGENT_SERVICE_PORT=tcp://…`, injected for the same-named Service)
  collided with the services' own port settings and crash-looped
  `agent-service` on startup. Service discovery uses DNS names only.
- operator-portal chat stream rendering fixed: the UI read `payload.event`
  while the gateway/agent stream contract emits `payload.type`, so every
  `message_delta` was dropped and the response area showed
  "[stream completed with no visible text]". The portal now reads `type`
  (with `event` as a legacy alias) and treats stream EOF as completion
  when no `message_end` event arrives.

### Changed — SPEC-010 code-review follow-ups

- platform-gateway `/health/ready` now verifies the policy bundle loads
  (reports a `policy_rules` count when ok; `status: degraded` with
  `policy_error` on `PolicyLoadError` instead of silently reporting ok).
- tool-gateway protected-action vocabulary corrected to the actual routes
  (`tools:list` / `tools:invoke`); regression tests added for the readiness
  degradation path.

### Changed — Shared `base-uv` container base image and non-root enforcement

- New shared Python base image `luban-aiops/base-uv:al2023`
  (`shared/base-images/base-uv/Dockerfile`): Amazon Linux 2023 minimal with
  a pinned uv (`UV_VERSION` ARG, default 0.12.1 — never `latest`), no system
  Python (uv resolves the interpreter from each product's `.python-version`
  during `uv sync`; `UV_PYTHON`/`PYTHON_VERSION` ARG default 3.12 is the
  deterministic fallback), and a non-root `app` user (uid 1000). Built by
  the new `make base-images` target, wired as a prerequisite of `make build`
  (overridable: `make base-images BASE_UV_UV_VERSION=...`).
- All four Python product Dockerfiles (`agent-platform`, `identity-broker`,
  `platform-gateway`, `tool-gateway`) now build `FROM luban-aiops/base-uv:al2023`;
  the env contract, `WORKDIR`, and `USER` move into the base, replacing the
  divergent bookworm-slim and ad-hoc amazonlinux bootstrap.
- operator-portal switches to `nginxinc/nginx-unprivileged:1.27-alpine` and
  listens on 8080 (nginx.conf, deployment containerPort, web-ui Service
  port/targetPort, dev-k8s README port-forward).
- All five app deployments gain a non-root `securityContext`
  (`runAsNonRoot`, `runAsUser` 1000 — 101 for web-ui,
  `allowPrivilegeEscalation: false`, `seccompProfile: RuntimeDefault`).
- Docs: `python-container-strategy.md` records the Option B migration as
  executed; backend layout convention updated.

### Changed — Explicit target platform for image builds

- New `IMAGE_PLATFORM` build parameter (default `linux/amd64`, the deployment
  target) in the root `Makefile` and `mk/image.mk`: applied to
  `make base-images` and forwarded to every product build, so base and product
  images always share one platform. Override per build, e.g.
  `make build IMAGE_PLATFORM=linux/arm64` for native local/kind builds on
  arm64 hosts.

### Changed — Build configuration extracted to `mk/defaults.mk`

- New `mk/defaults.mk` is the single source of truth for overridable build
  settings (`IMAGE_PLATFORM`, `IMAGE_TAG_PREFIX`/`IMAGE_TAG_PROFILE`,
  `REGISTRY`, `AUTO_LOAD_KIND`/`KIND_CLUSTER_NAME`, `BASE_UV_*`), included by
  the root `Makefile` and by `mk/image.mk`, so root-driven and standalone
  product builds resolve identical defaults. All values use `?=`, so
  command-line overrides still win; `mk/` fragments keep processing logic
  only. `IMAGE_TAG` and `IMAGE_CONTEXT` intentionally stay in `mk/image.mk`
  (computed fallback / per-product hook).

### Changed — SPEC-010: Platform Gateway Extraction (ADR-0005)

- Split the former combined gateway into two products with the boundaries
  ADR-0005 assigns: new `products/platform-gateway` owns the portal-facing
  edge (token verification for portal sessions, action policy, chat/session
  proxying, broker delegation client, `/api/v1` portal routes); the existing
  product renames its package `api_gateway` → `tool_gateway` and keeps only
  the tool/connector home (`ToolRegistry`, connectors, `tools:list` /
  `tools:invoke`, redaction choke point, tool audit). HTTP contract shapes,
  deny-by-default policy, and audit fields are unchanged.
- env contract (Q-1): edge settings rename `GATEWAY_*` → `PLATFORM_GATEWAY_*`;
  `GATEWAY_*` stays tool-scoped only (k8s, policy path, redaction, token
  audience, auth knobs, host/port).
- k8s (Q-2): `api-gateway` deployment/service/image rename to
  `platform-gateway`; new `tool-gateway` deployment/service/SA/RBAC with
  image `luban-aiops/tool-gateway`; policy ConfigMap `gateway-policy` →
  `platform-policy` mounted on both services from one shared bundle;
  `deploy-overlay.sh` and root `Makefile` updated (`.images.env` gains
  `PLATFORM_GATEWAY_IMAGE` + `TOOL_GATEWAY_IMAGE`). Portal `nginx.conf`
  proxies to `platform-gateway:8000`.
- identity (Q-3/Q-4): portal platform JWTs change audience `tool-gateway` →
  `platform-gateway` (broker `IDENTITY_TOKEN_AUDIENCE` default, overlay,
  schema note, edge verifier); delegated tokens keep `aud = tool-gateway`.
  The edge registers as a new `platform-gateway` broker client
  (`act.sub = platform-gateway`); the old `tool-gateway` client entry is
  removed.
- guards: both gateways gain route-inventory tests pinning their surfaces
  (edge: `/api/v1/*` portal routes only; tool: health/metrics +
  `/api/v2/tools*` only). Metric names unchanged (`gateway_*` /
  `delegation_*` remain the scrape contract).
- docs: platform-gateway/tool-gateway READMEs, dev-k8s README (incl. the
  one-time `kubectl delete deployment/api-gateway service/api-gateway`
  cleanup), workspace model, product boundaries, layout convention, and
  governance label scheme updated; spec status `delivered`.

### Added — SPEC-009: Pre-Production Hardening (Tool Output Redaction and Workload-Identity Service Tokens)

- Closes the two deadline-bound Release 1 deferrals before the first non-dev
  deployment: SPEC-007 Q-3 (tool-output redaction) and the SPEC-008 R-3
  workload-identity upgrade path.
- tool-gateway: code-owned redaction engine applied at the single
  `invoke_tool` choke point before both the response and the audit log —
  value patterns (JWTs, `Bearer`/`Basic` values, PEM private keys, AWS-style
  key IDs) plus a bounded explicit key list; clean output passes through
  byte-identical. Fail-closed: results whose redacted fraction exceeds
  `GATEWAY_REDACTION_OVERFLOW_FRACTION` (default 0.2) are withheld with a
  `REDACTION_OVERFLOW` error. New `gateway_tool_redacted_spans_total{tool}`
  metric and `redacted_spans` audit field; `GATEWAY_REDACTION_ENABLED`
  (default `true`) is the dev-debugging opt-out.
- identity-broker: the exchange endpoint now also accepts Kubernetes
  projected service-account tokens as the service credential
  (`Authorization: Bearer`), validated against the cluster OIDC issuer JWKS
  (`IDENTITY_WORKLOAD_ISSUER_URL`, empty = feature off) with an audience
  check (`IDENTITY_WORKLOAD_AUDIENCE`) and a workload-subject registry
  (`IDENTITY_WORKLOAD_CLIENTS`); delegated-token claims are identical to the
  static path. Invalid/expired/wrong-audience/unregistered tokens yield 401.
- tool-gateway delegation: `GATEWAY_WORKLOAD_TOKEN_PATH` prefers the
  projected token file (re-read per exchange; kubelet rotates it in place)
  over the static secret; a missing file falls back to the static secret
  with a once-per-process warning. Unsetting the path is the rollback
  switch; the dev path is unchanged.
- docs: dev-k8s README documents the redaction opt-out and the workload-token
  contract (projected volume snippet, issuer/audience env names); the
  gateway `runtime-secrets.example.env` marks the static secret as the dev
  fallback.

### Added — Release 1 (SPEC-008: Service-to-Service Identity)

- Implemented ADR-0004 broker-mediated token delegation, closing SPEC-007 R-4/R-6
  and open questions Q-1/Q-2 and completing Release 1.
- identity-broker: platform JWTs are now audience-bound (`aud`, default
  `["tool-gateway"]`); added `POST /api/v1/auth/exchange` which authenticates a
  registered service credential, verifies the subject token, and mints a
  short-lived delegated token (`sub`/`username`/`roles` copied never elevated,
  `act` naming the caller, `aud` = requested audience, TTL
  `IDENTITY_DELEGATED_TOKEN_TTL_SECONDS` default 300s). New service-client
  registry `IDENTITY_SERVICE_CLIENTS` and `token_exchange_total` metric.
- tool-gateway: verifies token `aud` (`GATEWAY_TOKEN_AUDIENCE`); exchanges the
  verified user token for a delegated token via a per-user TTL cache
  (`delegation_exchange_total`, `delegation_cache_total` metrics) and forwards
  it downstream as `Authorization: Bearer`; exchange failure is non-fatal
  (chat proceeds tool-less). Tool routes derive identity solely from the
  verified token (`identity_context` removed from the invoke contract);
  `GET /api/v2/tools` is authenticated and gated by a new `tools:list` policy
  action; audit logs record both `sub` and `act`.
- agent-platform: relays the delegated token as a bearer token on tool
  discovery and invocation, bound per-user into the toolkit closures (no
  cross-user sharing); removed `identity_context` from the invoke payload;
  no-token path degrades to an empty Toolkit / structured error.
- contracts: `identity-token.schema.json` documents `aud` (required) and `act`
  (optional) with a delegated-token note; `policy-default.yaml` adds
  `tools:list`. Contract tests bind both gateway and identity-broker models to
  the updated schema.
- dev-k8s overlay: sets `GATEWAY_TOKEN_AUDIENCE`, `GATEWAY_SERVICE_CLIENT_ID`,
  `IDENTITY_TOKEN_AUDIENCE`, `IDENTITY_DELEGATED_TOKEN_TTL_SECONDS`; the gateway
  and broker service secrets are provisioned as optional K8s Secrets
  (`api-gateway-runtime-secrets`, `identity-service-runtime-secrets`) and are
  not committed.

### Changed — Single Image Build Path

- Folded `build-images.sh` into `make build`: the root target now builds all
  four product images (delegating to each product's Makefile) with a
  coordinated `IMAGE_TAG`, writes `.images.env` for `make deploy`, and keeps
  the `AUTO_LOAD_KIND` / `KIND_CLUSTER_NAME` kind-load support.
- Removed `shared/platform-ops/gitops/dev-k8s/build-images.sh` and the separate
  `build-images` Make target; `make build` is now the single build path.
- Per-product `build` always tags the local image and adds a registry tag when
  `REGISTRY` is set; `push` re-tags then pushes, so build and push stay
  consistent.
- Updated the dev-k8s README to use `make build` / `make deploy` and corrected
  stale `dev-k8s-transitional` paths to `dev-k8s`.

### Changed — Build & Verification Tooling

- Added a forge-agnostic root `Makefile` (with per-product Makefiles and shared
  `mk/` fragments) consolidating project routines: `verify` (the
  pre-commit/pre-push gate), `test`, `sync`, `lint`, `build`, `push`,
  `overlays`, `deploy`, and `clean`.
- Removed the GitHub Actions workflows (`.github/workflows/ci.yml`,
  `overlays.yml`). The verification gate now lives in `make verify`,
  decoupling the project from GitHub-specific CI; the same checks run
  locally and under any CI provider.
- Updated the SDD enforcement guidance (`docs/specs/README.md`) to name
  `make verify` as the mechanical gate in place of the CI workflows.

### Added — Release 1 (SPEC-007: Tool Execution Framework)

- Added tool execution framework to tool-gateway: `ToolRegistry`, `BaseTool`
  abstraction, and structured `ToolResult` evidence envelope.
- Added Kubernetes read-only connector with four tools: `k8s.list_pods`,
  `k8s.get_pod`, `k8s.get_events`, `k8s.get_pod_logs` (kubernetes-client/python).
- Added `GET /api/v2/tools` (discovery) and `POST /api/v2/tools/invoke`
  (execution) endpoints with policy enforcement and audit logging.
- Added `tools:invoke` policy action granted to platform-admin, operator, and
  developer roles; read-only-observer is excluded.
- Added agent-platform Toolkit integration: when `TOOL_GATEWAY_URL` is
  configured, the AgentScope kernel discovers and registers gateway tools so
  the LLM can autonomously invoke them.
- Added shared contract schemas: `tool-invocation.schema.json` and
  `tool-result.schema.json`.
- Added RBAC (ServiceAccount + Role + RoleBinding) to dev-k8s overlay granting
  tool-gateway read-only access to pods, events, and pods/log.

### Changed — Release 1 Close

- Changed `GATEWAY_REQUIRE_AUTH` default from `false` to `true` in code and
  the dev overlay, completing the outstanding SPEC-001 release-close step.
  Unauthenticated requests to business routes now return `401` by default.
- Added `POST /api/v1/auth/refresh` to identity-broker: exchanges a Keycloak
  refresh_token for a fresh platform JWT, re-fetching userinfo so role changes
  are picked up on refresh.
- Added gateway proxy route `POST /api/v1/auth/refresh` forwarding to
  identity-broker.
- Added silent token refresh in operator-portal: schedules a background refresh
  60 seconds before JWT expiry; on failure, clears the session and prompts
  re-authentication.
- Collapsed the dual GitOps overlay (`dev-k8s-transitional` + `dev-k8s-native`)
  into a single `shared/platform-ops/gitops/dev-k8s` overlay. The
  transitional/native distinction no longer exists at the code level after
  SPEC-002 retired the transitional surface; a single overlay removes
  configuration drift and maintenance overhead.

### Added — Release 1 (SPEC-001 .. SPEC-006)

- Added `SPEC-001` release-1 platform hardening (delivered): gateway authentication
  enforcement behind `GATEWAY_REQUIRE_AUTH`, role propagation in structured logs,
  transitional session integrity (ownership scoping, 404 on unknown session IDs,
  TTL/size-bounded store, per-session agent isolation), typed contract
  enforcement bound to shared-contracts schemas, cached backend resolution with
  bounded outbound timeouts, and the GitHub Actions CI baseline.
- Added `SPEC-002` agent-service contract (delivered): platform-owned
  agent-service contract (ADR-0003) with v2 envelope (`content` replacing
  `response`, simplified stream events, header-based identity), `/api/v2/`
  adapter in agent-platform over the AgentScope kernel, tool-gateway migrated to
  a single agent-service client, retired the transitional `/api/v1/` surface,
  and bidirectional contract tests.
- Added `SPEC-003` identity-trust hardening (delivered): identity-broker now
  issues RSA-signed platform JWTs (`POST /api/v1/auth/token`) and publishes a
  JWKS endpoint (`GET /.well-known/jwks.json`, RFC 7517); the gateway verifies
  tokens locally via PyJWKClient, validates the `iss` claim, and derives
  `X-User-ID` exclusively from verified claims; removed `DEFAULT_USER_ID`
  fallback in favour of explicit `GATEWAY_DEV_USER` with synthetic identity
  logging.
- Added `SPEC-004` deny-by-default policy enforcement (delivered): defined the
  policy contract in shared-contracts (`policy-rule.schema.json`,
  `policy-decision.schema.json`, `policies/policy-default.yaml`) as a strict
  `action_authz` subset of the Tier-1 policy specification; the gateway
  evaluates every business request (`chat`, `session:create`, `session:read`)
  against a versioned role→action bundle, denying by default with a structured
  403 and audit-logging every decision.
- Added `SPEC-005` observability baseline (delivered): metrics naming
  conventions, OTel switch semantics, and `x-request-id` ↔ `trace_id` bridging
  rule in `shared/shared-contracts/observability-conventions.md`; all three
  Python services expose an always-on `/metrics` Prometheus surface plus an
  opt-in OTLP push pipeline gated by `OTEL_ENABLED`; standard HTTP RED metrics,
  domain counters (`agent_sessions_created_total`, `identity_tokens_issued_total`,
  `gateway_policy_decisions_total`, `gateway_token_verification_total`), and
  Prometheus scrape annotations on every deployment manifest.
- Added `SPEC-006` session durability (delivered): Redis-backed session store
  with strategy-pattern interface (`InMemorySessionStore` for dev/CI,
  `RedisSessionStore` for deployed environments); backend selection via
  `SESSION_STORE_BACKEND` env; graceful fallback to in-memory when Redis is
  unreachable; session store backend and readiness reported in `/health`;
  `session_store_backend`, `session_store_errors_total`, and
  `session_store_fallbacks_total` Prometheus metrics.
- Added ADR-0001 (SDD adoption), ADR-0002 (AgentScope 2.0 kernel), and
  ADR-0003 (platform-owned agent-service contract) under `docs/adr/`.
- Added spec-driven development workflow under `docs/specs/` with plan/spec/tasks
  templates and delivered specs for SPEC-001 through SPEC-006.
- Added `docs/agentic-aiops-platform/part-1b-framework-revalidation.md`.

### Added — Release 0

- Added typed provider-specific runtime options for `products/agent-platform`,
  including provider-owned defaults for `dashscope`, `deepseek`, and `openai`.
- Added provider adapters and a provider registry that resolve runtime settings
  into concrete AgentScope chat model implementations.
- Added gateway backend adapters so `products/tool-gateway` can resolve
  `transitional` versus `native` agent-service backends through a shared
  interface.
- Added deterministic local image build and deploy scripts for the GitOps-based
  Kubernetes development overlays under `shared/platform-ops/gitops/`,
  including both `dev-k8s-transitional` and `dev-k8s-native`.
- Added shared runtime profile overlays and selector helpers so provider
  selection stays explicit, reviewable, and Git-diffable in the deployment
  layer.
- Added Dockerfiles for the Release 0 development overlay services and an
  `nginx` proxy baseline for `products/operator-portal`.
- Added a minimal `OIDC` authorization-code callback path across
  `products/operator-portal`, `products/identity-broker`, and
  `products/tool-gateway`.
- Added configurable `OIDC_SCOPES` support so the shared identity flow can work
  against realms that do not expose the default `profile` and `email` scopes.
- Added focused tests for runtime settings, runtime metadata, provider registry
  behavior, and gateway backend resolution.
- Added release notes under `docs/agentic-aiops-platform/release-notes/`.
- Added a Git-tracked Keycloak browser-client reconciliation script for
  `dev-k8s-transitional` so the portal client redirect URIs, PKCE/public-client
  settings, and `preferred_username` / `email` mappers stay durable across
  overlay deploys.

### Changed

- Changed runtime metadata to expose resolved provider, model, base URL, and
  provider option details instead of only raw environment overrides.
- Changed `api-gateway` development overlay configuration to prefer `auto`
  backend resolution rather than pinning `AGENT_BACKEND_MODE` to
  `transitional`.
- Changed the platform-ops layout to use the durable
  `shared/platform-ops/gitops/` root for active operational assets while
  keeping `Release 0` wording in milestone-planning documents.
- Changed the development overlay rollout workflow to use explicit,
  overlay-specific image tags and per-overlay `.images.env` state instead of
  reusing a single static placeholder tag.
- Changed the operator portal browser baseline to default API requests to the
  current origin and route them through the local `nginx` proxy.
- Changed backend package layout across `agent-platform`, `tool-gateway`, and
  `identity-broker` to follow a clearer FastAPI-by-responsibility structure.
- Changed the gateway and portal request path so authenticated bearer identity
  now overrides manually entered user IDs for session and chat operations.
- Changed the GitOps overlay roots to set the deployment namespace explicitly so
  shared runtime-profile config maps are created in the same namespace as the
  services that consume them.
- Changed the committed `dev-k8s-transitional` OIDC baseline to match the live
  shared sandbox `Keycloak` validation path used for `Release 0` closure.

### Fixed

- Fixed a runtime settings mismatch where direct `RuntimeSettings(...)`
  construction could pair a provider with the wrong provider-options type.
- Fixed development cluster rollout ambiguity caused by stale same-tag image reuse.
- Fixed native AgentScope streaming compatibility so incremental reply updates
  preserve all accumulated content blocks instead of dropping earlier blocks.
- Fixed the native overlay image-build wrapper so it is directly executable as
  documented and writes to the correct overlay-specific image-state file.
- Fixed local runtime artifact hygiene by ignoring generated `**/.workspaces/`
  directories.
- Fixed the remaining `Release 0` auth gap by adding identity-broker token
  exchange, portal callback handling, optional identity-service secret
  injection, and structured request/session logs across the core services.
- Fixed fresh-namespace startup for `api-gateway` and `identity-service` by
  ignoring Kubernetes service-link `*_PORT=tcp://...` values when parsing their
  listen ports.
- Fixed the live `Release 0` overlay wiring so `agent-platform-runtime-profile`
  is created in the target namespace instead of `default`.
- Fixed the portal SSO identity contract in the shared sandbox realm by making
  the browser client emit durable `preferred_username` and `email` claims, so
  authenticated identity no longer falls back to the UUID subject value.
- Fixed the remaining `Release 0` documentation drift so the checklist,
  release notes, and closure status now consistently describe `Release 0` as
  completed with only post-closure follow-up items remaining.
