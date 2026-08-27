# SPEC-039 Plan: Shift-Summary Artifacts

## Approach

Build vertically in agent-platform (digest assembly → store → routes),
then the gateway pass-through and policy action, then the portal view.
The trusted digest is pure data assembly over the four existing stores
— no new infrastructure; the only genuinely new runtime dependency is
the optional prose generation, which reuses the runtime kernel's LLM
client behind a digest-only prompt contract. Everything degrades:
unreadable stores mark their digest section `unavailable`, failed
prose yields a digest-only artifact.

## Design Per Requirement

### R-1: Deterministic digest assembly

- affected files: `products/agent-platform/src/agent_service/services/shift_summary.py`
  (new), consuming `session_store`, `confirmation_records`,
  `execution_records`, `evidence_store`
- chosen approach: a `build_digest(requester_user_id, session_ids,
  can_view_foreign)` function that, per session, resolves ownership
  via the session store and branches into full-digest (own) or
  metadata-level digest (foreign, gated by the caller's
  `approvals:list` flag passed in from the route). Counts and records
  are copied verbatim; every entry carries its source record ids.
- alternatives rejected: assembling the digest in platform-gateway
  (the stores live in agent-platform; the gateway stays a policy +
  pass-through boundary) and digest-on-read (the artifact must be an
  immutable snapshot, not a live view).

### R-2: Policy-gated generation API

- affected files: `products/agent-platform/src/agent_service/api/v2/routes.py`,
  `products/agent-platform/src/agent_service/schemas/v2.py`,
  `products/platform-gateway/src/platform_gateway/api/routes.py`
  (pass-through), `products/platform-gateway/src/platform_gateway/services/policy_engine.py`
  consumers, `shared/shared-contracts/schemas/shift-summary.schema.json` (new),
  `shared/shared-contracts/policies/policy-default.yaml`
- chosen approach: agent route validates the bounded input (≤20
  session ids, label cap), calls the digest builder, persists via the
  store, emits the audit event, returns the artifact. Gateway mirrors
  the route behind `enforce_policy("shifts:summarize")` exactly like
  the approvals inbox pass-through; the default bundle grants the
  action to `operator`, `approver`, `platform-admin`.
- alternatives rejected: a dedicated summarization service (no demand
  for a separate deployment; agent-platform already owns the stores
  and the LLM client).

### R-3: Durable artifact store

- affected files: `products/agent-platform/src/agent_service/services/shift_summary_store.py`
  (new), Postgres DDL in the shared initdb path used by the
  confirmation/execution record tables, agent settings knob
  reusing `AGENT_STATE_STORE_BACKEND`/`AGENT_STATE_DB_URL`
- chosen approach: memory + Postgres backends behind one interface,
  mirroring `confirmation_records` (immutable rows, per-owner cap
  with oldest-eviction, TTL sweep on startup and access). Reuses the
  existing state-store backend knob — no new configuration surface.
- alternatives rejected: a separate backend knob (adds config
  surface for no isolation benefit) and storing artifacts in the
  session store (sessions expire independently; artifacts must keep
  their own retention).

### R-4: Optional clearly-labeled prose layer

- affected files: `products/agent-platform/src/agent_service/services/shift_summary_prose.py`
  (new)
- chosen approach: serialize the assembled digest to a bounded JSON
  prompt ("recap these facts for a relieving operator; state only
  what the facts contain"), call the runtime's configured default
  model client with a hard timeout, attach the result with
  `prose_status=included`. Any exception/time-out sets
  `prose_status=failed` and the artifact ships digest-only.
- alternatives rejected: feeding transcripts to the model (defeats
  the fabrication posture) and per-artifact model selection (no
  demand; the catalog picker stays a chat-surface concern).

### R-5: Audit event

- affected files: reuse the canonical fire-and-forget emitter module
  (parity family) from agent-platform; new event type
  `shift_summary_generated`
- chosen approach: emit after store persistence succeeds with
  requester, covered ids split own/foreign, per-source counts, prose
  status; forward `x-request-id` per the SPEC-029 convention.
- alternatives rejected: auditing reads/deletes — the artifact is the
  requester's own record and no cross-user read path exists (Q-2
  resolution).

### R-6: Portal shift-summaries view

- affected files: `products/operator-portal/web-ui/` (new Shift
  summaries view wired into the navigation beside Approvals)
- chosen approach: request dialog with the own-session picker
  (session list surface) plus an explicit foreign-id input, artifact
  list, and an artifact page rendering digest tables first with the
  prose in a collapsed, labeled panel; reuse the antd dark-theme
  custom properties and existing fetch/error patterns.
- alternatives rejected: embedding summaries in the Approvals view
  (different mental model; Approvals stays decision-centric).

## Sequencing And Dependencies

1. Contract first — `shift-summary.schema.json` + policy action in the
   canonical bundle (`make sync-policy`) — depends on nothing
2. Digest builder + store (R-1, R-3) with unit tests — depends on 1
3. Agent routes + audit emission (R-2 backend, R-5) — depends on 2
4. Prose layer (R-4) — depends on 2
5. Gateway pass-through + policy-matrix tests (R-2) — depends on 1, 3
6. Portal view (R-6) — depends on 5
7. Docs, version, delivery bookkeeping — depends on all

## Test Strategy

- unit tests: digest assembly (own vs foreign tiers, degraded
  stores), store caps/TTL/sweep and parity between backends, prose
  prompt contract (digest-only input), fail-soft degradation
- contract tests: artifact responses validate against
  `shift-summary.schema.json`; policy-matrix tests cover
  `shifts:summarize` grants/denials in platform-gateway
- integration / overlay validation: `make verify` (all suites,
  overlays, policy validation, version lockstep); delivery-gate live
  check generates an artifact over real sessions on the dev cluster
  including a foreign session under the approver role

## Rollout And Migration

- deployment: no new services; agent-platform and platform-gateway
  images plus the portal static bundle; policy bundle re-synced; no
  new secrets
- backward compatibility: purely additive surface (new routes, new
  schema, new action); existing session/approval surfaces untouched
- rollback: drop the policy action (instant denial) and revert the
  images; the `shift_summaries` table stays inert
