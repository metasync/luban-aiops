# SPEC-024: Runtime LLM Model Switching

## Status

- status: `delivered`
- owner: chi
- created: 2026-08-24
- release slice: post-0.9.1 train
- related ADRs: `docs/adr/0002-reaffirm-agentscope-runtime-kernel.md`,
  `docs/adr/0003-platform-owned-agent-service-contract.md`

## Summary

Operators can choose the runtime LLM per session from a portal dropdown
instead of waiting for a deploy-time runtime-profile rollout. The
agent-platform exposes a credential-gated model catalog, sessions pin the
chosen model (with explicit mid-session switching), and every selection is
audited.

## Motivation

- Today the model is fixed at deploy time: the `runtime-profiles`
  kustomize overlays (`dashscope`/`deepseek`/`openai`) set
  `AGENTSCOPE_PROVIDER` / `AGENTSCOPE_MODEL_NAME` / `AGENTSCOPE_BASE_URL`
  and a single `AGENTSCOPE_API_KEY`, so comparing models or recovering
  from a provider outage requires a redeploy of agent-service.
- The delivery roadmap reserves this capability for SPEC-024: "Portal
  dropdown to choose the model per session (default deepseek) instead of
  deploy-time runtime profiles. Requires multi-provider settings/secrets
  in agent-platform, a request-level provider selection, per-session
  affinity, and audit of the chosen model."
- The SPEC-023 rebuild delivered the React/antd composer shell the
  selector lands in, so the portal side is now cheap to build.
- The kernel already constructs agents per session
  (`RuntimeKernel.ensure_agent`) and restores persisted `AgentState`
  (SPEC-017 R-3), so a model change can rebuild the agent without losing
  conversation memory.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable
acceptance criteria.

### R-1: Credential-gated model catalog

The agent-platform resolves a model catalog from configuration: the
deploy-time profile stays the default, and additional providers/models
become selectable when their credentials are configured. A model without
usable credentials is never listed, accepted, or silently substituted.

The catalog contract is per-provider additive environment knobs on top of
the existing `AGENTSCOPE_*` settings (e.g. `OPENAI_API_KEY` /
`OPENAI_MODEL_NAME`, `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL_NAME`); each
configured provider contributes one model-level entry named by its
configured model name (draft-review resolution of Q-1).

Acceptance criteria:

- The catalog derives from environment configuration; each entry carries a
  stable id, label, provider, model name, base URL, and default flag.
- Entries whose API key is absent or empty are excluded from the catalog
  at startup; the deploy-time profile's entry is always present when its
  key is configured, and it is flagged as the default.
- Unknown catalog configuration fails startup with a clear error (same
  posture as `AGENTSCOPE_PROVIDER` validation today).
- Selecting a model that is not in the catalog — via API or otherwise —
  fails closed with a 4xx; there is no silent fallback to the default
  model.

### R-2: Model discovery contract

A read-only discovery endpoint exposes the catalog so the portal can render
the selector without hardcoding models.

Acceptance criteria:

- `GET /api/v2/models` on agent-service returns the enabled catalog
  (id, label, provider, model name, default flag) and never exposes
  credentials or base URLs.
- Platform-gateway relays the endpoint under `/api/v1/models` behind a
  policy action, verbatim like the other pass-through reads.
- The response shape is a shared-contracts schema; contract tests bind
  gateway models to it (same lockstep pattern as session detail).

### R-3: Per-session model selection with affinity

The chat request carries an optional model selection; a session pins the
model it first runs with, and an explicit later change rebuilds the agent
without losing conversation memory (switch-on-demand, draft-review
resolution of Q-2). The pinned model lives on the session-store record so
it survives restarts and precedes any kernel snapshot (resolution of Q-4);
selection resolution order is request model > pinned model > default.

Acceptance criteria:

- `POST /api/v2/chat` accepts an optional `model` field (catalog id);
  unset means "keep the session's pinned model, or the default model for
  a new session".
- The pinned model is persisted on the session record so pod restarts and
  the session-detail view stay consistent; `GET /api/v2/sessions/{id}`
  exposes the current model additively.
- Changing the pinned model on a later turn rebuilds the session's agent
  with the new model and restores the persisted `AgentState` — the
  conversation continues, only the model changes.
- A model switch against a session with a parked HITL confirmation is
  refused with `409`, same posture as a chat against a parked session.
- A model change never bypasses HITL gating, permission middleware, or
  tool policy: a parked confirmation still resumes under its own rules,
  and the model field is metadata only for authorization purposes.

### R-4: Audited selection and portal selector

Model selection is traceable in the audit trail and reachable from the
portal composer. The audit shape is enrichment, not a new event type:
`chat_started` / `chat_completed` payloads carry the resolved model so
every turn is attributed (draft-review resolution of Q-3).

Acceptance criteria:

- The resolved model of each chat turn is recorded in the `chat_started`
  and `chat_completed` audit payloads and queryable through the existing
  audit view; the closed event-type enum is unchanged.
- The portal composer offers a model selector sourced from the discovery
  endpoint, pre-selected to the default model; choosing another model
  applies it from the next turn onward.
- When the catalog has exactly one enabled model, the selector renders a
  fixed label instead of a dropdown (nothing to choose).

## Non-Goals

- Bring-your-own API keys or per-user credentials (identity delegation
  stays broker-mediated per SPEC-008).
- Per-turn model switching or mixing models inside one turn.
- Model parameter tuning surfaces (temperature, reasoning effort, …):
  those stay deploy-time per-provider options.
- Cost tracking, quota, or rate-limit management per model.
- Token-consumption observability (per-turn/per-model input/output token
  accounting): out of scope here by draft-review decision; it is a
  follow-up spec candidate that can build on this spec's model
  attribution in the audit payloads.
- Retiring the runtime-profile overlays: they remain the deploy-time
  source of the default model and credentials.

## Impact

- products touched: `products/agent-platform` (settings/catalog, provider
  registry, kernel model selection + agent rebuild, models route, chat +
  session schemas), `products/platform-gateway` (pass-through route,
  policy action, mirror models), `products/operator-portal` (composer
  selector), `shared/platform-ops/gitops` (dev-k8s secrets for additional
  providers)
- contracts touched: new models schema under
  `shared/shared-contracts/schemas`; additive field on the chat request
  and session detail schemas
- identity / policy / audit / execution safety impact: one new read
  policy action for model discovery; the model field never influences
  authorization, HITL, or auto-allow; selection is audited
- living state docs to update on delivery: root `CHANGELOG.md`,
  agent-platform / platform-gateway / operator-portal READMEs,
  configuration-reference, authorization-matrix, operator guide

## Open Questions

All four open questions were resolved in draft review (2026-08-24) and
folded into the requirements above:

- Q-1 (catalog contract): per-provider additive env knobs, one
  model-level entry per configured provider → R-1.
- Q-2 (switch semantics): switch on demand with agent rebuild + state
  restore; `409` while a HITL confirmation is parked → R-3.
- Q-3 (audit shape): enrich `chat_started` / `chat_completed` payloads
  with the resolved model; no new event type → R-4.
- Q-4 (affinity home): the session-store record, resolved ahead of any
  kernel snapshot → R-3.

## Changelog

- 2026-08-24: created as `draft` from the delivery-roadmap reservation;
  numbering was reserved by SPEC-023/SPEC-025 delivery notes.
- 2026-08-24: draft review resolved Q-1…Q-4 (folded into R-1/R-3/R-4);
  token-consumption observability deferred to a follow-up spec candidate
  and listed as a non-goal.
- 2026-08-24: approved by owner; implementation proceeds per `tasks.md`.
- 2026-08-24: delivered — R-1…R-4 implemented per `plan.md` (catalog,
  discovery contract, per-session affinity + kernel rebuild, audited
  selection + portal selector); all open questions remain closed.
