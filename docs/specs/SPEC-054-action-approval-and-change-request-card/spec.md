# SPEC-054: Action-Level HITL Approval and the Change-Request Confirmation Card

## Status

- status: `draft`
- owner: luban-platform-team
- created: 2026-09-06
- release slice: R5 — Hardening and External Consumption (sixteenth R5 slice;
  provisional, fixed on approval)
- related ADRs: ADR-0007 (enforce one HITL gate per mutating browser flow —
  **extended, not reversed**), ADR-0008 (spec delivery traceability gate);
  lineage: extends SPEC-020 (HITL confirmation bridging), SPEC-021 (bounded
  mutating actions), SPEC-030 (require-approval semantics), SPEC-037 (signed
  execution requests), SPEC-038 (isolated execution worker), SPEC-049/050/051
  (browser web-check tools + flow gate enforcement), SPEC-053 (skill-declared
  step intent)
- predecessor fix: the SPEC-051 R-6 headline-leak patch (the flow headline is
  now gated on the parked batch's browser-write predicate,
  `_tool_names_have_browser_write`, so a non-browser action card no longer
  inherits a lingering flow's headline). This spec makes that gate **explicit**
  via an `approval_kind` discriminator rather than an ambient-context probe.
- companion: ADR-0009 + SPEC-055 (develop-as-you-go skill graduation) — the
  action-approval phase this spec formalizes is the *input* to that graduation
  pipeline. B (this spec) and C (SPEC-055) are the two lifecycle phases; A→B
  does not conflict with C.

## Summary

Today the platform has two approval subjects but only one is first-class in the
confirmation contract. A **flow** approval (a `write`-class browser web-check
flow, bound at `web.navigate(skill_id=…)`) collapses to one gate per SPEC-051
and renders a flow-semantic headline (R-6). An **action** approval (an ad-hoc
mutating tool call such as `k8s.delete_pod`) renders only a bare tool name, a
risk tier, and a collapsed "Technical details" expander. Two gaps follow:

1. **Browser writes cannot be approved per-action at all.** Outside a bound
   flow the tool-gateway hard-denies every `web.*` write with
   `BROWSER_FLOW_NOT_BOUND`, regardless of operator intent — so interactive
   web-app troubleshooting that mutates ("log in, then click *Confirm reset*")
   is impossible unless a skill flow was pre-declared and bound first.
   Non-browser mutating tools already park per-action (SPEC-021/030/037); the
   browser family is the sole exception, and it is a flow-centric guard, not a
   trust decision.
2. **The action card under-informs the approver.** It names the tool but not
   the *change*: which pod, which user, which target, which value. The
   decision-relevant parameters the operator already supplied sit in a collapsed
   expander, so the approver approves an opaque action rather than a described
   change.

This spec makes **action-level approval first-class**: an explicit
`approval_kind: flow | action` discriminator on the confirmation frame and
durable record (R-1); ad-hoc browser writes park as **per-action signed gates**
instead of being hard-denied (R-2); every action card becomes a
**change request** that surfaces the decision-relevant, secret-masked parameters
in the approval intention (R-3); and the card's confirmation `message` is
persisted on the durable record so the approver inbox and a re-loaded owner
transcript render the same card the live stream showed (R-4). It reuses the
existing SPEC-020/021/030/037 per-action approval + signed-execution mechanism
verbatim — **no new trust mechanism, no new policy action, no new audit event
type**. The only contract change is additive (`approval_kind` + an optional
`change_request` display projection + a persisted `message` on the confirmation
frame and its durable record).

## Motivation

- The operator's target operating model is: (1) troubleshoot via chat with
  mutating actions properly approved; (2) turn a troubleshooting session into a
  reusable skill; (3) develop skills by running actions in chat
  ("develop-as-you-go"). Step (1) is impossible in the **web domain** today
  because unbound browser writes are denied at the gateway, not parked. Steps
  (2)/(3) are SPEC-055/ADR-0009; this spec is their prerequisite — a graduated
  flow is authored from a session of *approved per-action mutations*, which must
  first be possible.
- Evidence: `test_click_without_bound_flow_denied` asserts the current
  hard-deny; `GatewayPermissionMiddleware.on_check_permission` ASKs for a
  non-flow browser write, but the gateway refuses it post-approval, so the ASK
  is a dead end for interactive web mutation.
- The just-landed headline-leak fix (a `k8s.delete_pod` card wearing a stale
  "reset password" flow headline) exposed the deeper design gap: the card's
  *kind* is inferred from ambient session state (`FLOW_CONTEXTS`) rather than
  declared. R-1 replaces that inference with an explicit discriminator so
  framing can never again disagree with the batch's nature.
- Why now: this is the action-approval half of the A→B→C program the operator
  approved; it is a prerequisite for the develop-as-you-go operating model and
  a correctness follow-on to the SPEC-051 R-6 headline patch. R5 is the
  hardening release.

## Requirements

### R-1: Explicit `approval_kind` discriminator on the confirmation card

Every parked confirmation declares its kind — `flow` (a bound browser web-check
flow, one gate per SPEC-051) or `action` (an individually-approved mutating tool
call) — on the live confirmation-request frame and the durable confirmation
record. The kind is derived from the **parked batch**, not from ambient session
state, and drives card rendering.

Acceptance criteria:

- The confirmation-request frame carries `approval_kind` ∈ {`flow`, `action`}.
  It is `flow` **iff** the batch carries a browser write *and* a flow is bound
  (the same `_tool_names_have_browser_write` predicate + a non-empty bound
  `FlowContext` that the headline-leak fix uses); otherwise `action`.
- The durable confirmation record persists `approval_kind` so the approvals
  inbox and session detail replay the same kind as the live card (parity with
  the existing `flow_summary` persistence path).
- `flow_summary` is present **iff** `approval_kind == flow`; an `action` card
  never carries a flow headline (the headline-leak class of defect is now
  structurally impossible, not merely gated).
- The portal renders the flow headline for `flow` and the change-request layout
  (R-3) for `action`; a card with neither degrades to today's tool-level
  rendering (no regression).
- Additive contract change only: `approval_kind` (and R-3's `change_request`)
  are optional fields on the confirmation-request frame and the durable record
  schema; a client that ignores them renders today's card.

### R-2: Ad-hoc browser writes park as per-action signed gates

A `web.*` write issued **outside** a bound flow, on an allowlisted origin,
parks a per-action confirmation card and — on approval — executes through the
existing SPEC-037/038 signed path. It is never hard-denied solely for lacking a
bound flow, and never auto-allowed.

Acceptance criteria:

- The tool-gateway no longer returns `BROWSER_FLOW_NOT_BOUND` as a hard deny for
  a write on an **allowlisted** origin; such a write is gated by the kernel's
  per-action ASK and, once approved and signed, executes. (`test_click_without_
  bound_flow_denied` is replaced by a park-then-execute expectation.)
- Each ad-hoc browser write is **individually** approved and signed (its own
  `execution_id`, `args_digest`, `confirm_id`/`decider`) — there is **no**
  flow-unlock for unbound writes, so N interactive writes park N cards. The
  SPEC-051 one-gate collapse applies **only** to a bound flow (unchanged).
- Browser write tools still **never join any auto-allow list**; with bridging off
  (`hitl_confirm_timeout == 0`) an unbound browser write is denied, never
  silently executed (the existing auto-allow invariant test stays green).
- The origin allowlist (`GATEWAY_BROWSER_ALLOW_ORIGINS`) stays
  deny-by-default: a write to a non-allowlisted origin is still refused, with or
  without approval. The gateway deviation guard remains the enforcement boundary
  (ADR-0007 preserved).
- Non-browser mutating tools (`k8s.*`, etc.) are unchanged (they already park
  per-action); bound browser flows are unchanged (they already collapse to one
  gate).

### R-3: The action card is a change request

An `action` card surfaces the decision-relevant, operator-supplied parameters as
a readable **change request** — promoting them from the collapsed "Technical
details" expander into the approval intention — with secret values masked. It is
a **display-only projection** that never alters the signed `args_digest`.

Acceptance criteria:

- The confirmation-request frame carries an optional per-call `change_request`
  display projection: a short human sentence or label→value pairs naming the
  target and the effect (e.g. `Delete pod "scratch-restart-demo" in namespace
  "default"`), assembled from the call's parameters.
- Secret-bearing parameter **values** are masked (`***`) using the existing
  redaction vocabulary (`_is_secret_param` / `_SECRET_QUERY_PARAMS` and the
  `_redact_secret_query` mask-by-default posture, SPEC-049 R-5); the parameter
  *key* is preserved so the approver sees that a secret is involved without
  seeing it. Masking is **by default** — an allow-list of known-safe fields may
  be shown verbatim, everything else masks.
- The projection is built **separately** from the signed parameters, exactly as
  SPEC-050's `display_hint` is: `args_digest` (and therefore the signature and
  gateway verification) is computed over the true parameters and is unchanged by
  the projection. A tampered or absent projection never affects execution.
- The full parameters remain available in the existing collapsed "Technical
  details" expander (the change request complements, not replaces, it).
- Durable and replayed `action` cards render the same change request as the live
  card.
- No new policy action, audit event type, or shared schema beyond the additive
  `approval_kind` / `change_request` fields in R-1.

### R-4: Durable card-message parity

The confirmation card's `message` line — the top-line description the live
`confirmation_request` frame already carries (`_confirmation_message`, which
falls back to `"Tool execution requires your confirmation."`) — is persisted on
the durable confirmation record, so every surface that renders *from that
record* shows the same message as the live operator card. Today `message` is
**frame-only**: it lives on the stream-frame model (`schemas/v2.py`) but not on
the durable `ConfirmationRecordModel`, and `PendingConfirmation` /
`confirmation_records.py` never store it — so `confirmationRecordToCard` maps a
card with no message and the line silently disappears on the approver/admin
inbox **and** on the owner's own transcript after a re-login or reload.

Acceptance criteria:

- The durable confirmation record persists `message`, mirroring the existing
  `flow_summary` persistence path end to end: record-create parameter →
  `message TEXT` column → `ADD COLUMN IF NOT EXISTS` migration → INSERT/SELECT
  in `services/confirmation_records.py` → `ConfirmationRecordModel`
  (`schemas/v2.py`) → API coercion in `api/v2/routes.py`.
- The confirmation-record contract (`agent-session.schema.json`) and the portal
  `ConfirmationRecord` type (`api/sessions.ts`) gain an **optional** `message`;
  `confirmationRecordToCard` (`chat/transcript.ts`) sets `card.message` from it,
  so the inbox card and the re-loaded owner transcript render the same message
  the live card did (the parity intent SPEC-051 R-6 established for
  `flow_summary`).
- The kernel computes the message **once** at park time and feeds both the live
  frame and the durable record from that single value, so the two paths can never
  diverge.
- A record with no persisted message (a legacy row predating the column) degrades
  to today's rendering — no message line, never a broken/empty artifact (no
  regression).
- Additive contract change only; no new policy action, audit event type, or
  schema beyond the optional `message` field.

### R-5: Delivery traceability per ADR-0008

This spec is delivered under the ADR-0008 gate.

Acceptance criteria:

- Every R-1..R-4 acceptance criterion maps to at least one automated test
  recorded in `tasks.md` (kernel frame kind + change-request projection;
  gateway park-not-deny for an allowlisted unbound write; portal rendering of
  both kinds; durable-record message persistence + live/durable card parity;
  contract-drift guard on the additive fields).
- The password-reset sample's `demo.sh` chat leg stays green (the bound-flow
  one-gate path is unchanged); if an interactive per-action browser-write demo
  is added it is exercised in the verification path.
- `CONTRIBUTING.md` and `docs/specs/README.md` carry the ADR-0008 delivery-gate
  text (unchanged from SPEC-051).

## Non-Goals

- **No skill/flow authoring or format change.** Skills still declare
  `risk_class`/`web_target`/`flow_intent` exactly as SPEC-049/053 define; this
  spec adds no frontmatter key. Decoupling `risk_class` from `web_target` is
  SPEC-055/ADR-0009 (C).
- **No graduation, replay, or authoring-trace store.** Turning a session of
  approved per-action mutations into a reusable executable skill is
  SPEC-055/ADR-0009 (C); this spec only makes the per-action mutations
  *possible and well-described*.
- **No change to the flow-unlock one-gate behavior** (SPEC-051 R-1/R-2/R-3 stand
  unchanged): a bound `write`-class flow still parks one card and auto-signs
  subsequent writes under that authority, TTL-bounded and identity-scoped.
- **No new trust mechanism.** Per-action browser-write approval reuses the
  SPEC-020/021/030/037 approval + signed-execution model verbatim; the gateway
  deviation guard remains the enforcement boundary (ADR-0007 extended in scope,
  not reversed).
- **No structured per-step plan rendering** (SPEC-049 R-4's literal "declared
  steps") and no machine-readable step list on skills — unchanged from SPEC-051.
- **No parameterized/templated `flow_intent`** (a skill-authored intent with
  runtime-substituted values) — deferred to SPEC-055 (C); R-3's change request
  is assembled at park time from the actual call parameters.

## Impact

- products touched:
  - `products/agent-platform` — confirmation-frame builder sets `approval_kind`
    (reusing `_tool_names_have_browser_write` + the bound-`FlowContext` check)
    and assembles the per-call `change_request` projection from parameters with
    secret masking; `PendingConfirmation` / `pending_calls_payload` carry the
    projection; the durable confirmation record persists `approval_kind` +
    `change_request` + the card `message` (R-4, mirroring `flow_summary`)
    (`runtime_kernel.py`, `services/hitl_confirmations.py`,
    `services/confirmation_records.py`, `schemas/v2.py`, `api/v2/routes.py`).
  - `products/tool-gateway` — the write path parks-not-denies an **allowlisted**
    unbound browser write (relax `BROWSER_FLOW_NOT_BOUND` to a per-action gate);
    the origin allowlist, risk tier, and deviation guard are unchanged; the
    redaction vocabulary (`_is_secret_param` / `_redact_secret_query`) is reused
    (may be lifted to a shared helper) for the change-request mask
    (`tools/browser_connector.py`, `tools/browser_sessions.py`).
  - `products/operator-portal` — decode `approval_kind` + `change_request`;
    render the change-request layout for `action` and the flow headline for
    `flow`, with today's tool-level rendering as the fallback; map the persisted
    `message` in `confirmationRecordToCard` + the `ConfirmationRecord` type so
    the inbox and re-loaded transcript render the same card message (R-4)
    (`web-ui/app/src/stream/decoder.ts`, `.../stream/models.ts`,
    `.../chat/ChatView.tsx`, `.../chat/transcript.ts`, `.../api/sessions.ts`).
  - `products/execution-runtime` — no code change (worker verification already
    accepts kernel-signed per-action envelopes); verify only.
- samples / shared touched: `shared/shared-contracts/schemas/
  agent-stream-event.schema.json` (additive `approval_kind` + `change_request`
  on the confirmation-request frame; additive stream-schema version bump — the
  exact next version number is resolved at implementation against the delivered
  schema, whose title currently reads v9 with SPEC-053's `flow_intent` already
  riding `flow_summary`), and the durable confirmation-record schema
  (`agent-session.schema.json`: additive `approval_kind` + `change_request` +
  `message`, R-4); possibly an interactive per-action browser-write demo under
  `samples/` (optional).
- contracts touched: `agent-stream-event.schema.json` (additive) + the
  confirmation-record contract (additive). No policy (`policy-default.yaml`) or
  audit-event schema change; no new policy action or audit event type.
- identity / policy / audit / execution safety impact: execution safety —
  extends the per-action signed-execution path to the browser tool family for
  unbound writes on allowlisted origins; no identity or policy model change;
  audit rides the existing `confirmation_decided` / `execution_requested` /
  `tool_invoked` / `execution_completed` events.
- living state docs to update on delivery: root `CHANGELOG.md`, `VERSION`
  (+ lockstep constants), `docs/agentic-aiops-platform/release-notes/` (new note
  + index), `docs/guides/configuration-reference.md` (only if a new knob is
  introduced — none planned), `docs/specs/README.md` (SPEC-054 row →
  `delivered`), `docs/agentic-aiops-platform/delivery-roadmap.md` (SPEC-054 row
  → `delivered`).

## Open Questions

- **OQ-1 (ADR cover for R-2):** relaxing `BROWSER_FLOW_NOT_BOUND` widens the set
  of mutations an interactive session can perform on allowlisted web apps (from
  "only pre-declared skill flows" to "any per-action-approved write"). The trust
  *mechanism* is unchanged (operator approves each write; SPEC-037 signs it; the
  gateway guard bounds it), so per `docs/adr/README.md` ("do not write an ADR
  for decisions local to a single spec") this is recorded here rather than in a
  new ADR, and it **extends** ADR-0007 without reversing it. If the operator
  considers the scope widening ADR-worthy in its own right, promote R-2 to a
  short ADR before approval; otherwise ADR-0007 + this spec are the record.
- **OQ-2 (change-request assembly):** R-3's projection is assembled at park time
  from raw parameters by a per-tool formatter. Confirm whether the operator
  wants a generic label→value projection for all tools in B, or a curated
  sentence for the highest-value mutating tools first (`k8s.*`, `web.*` writes)
  with a generic fallback. Recommendation: curated for the demo-critical tools +
  generic label→value fallback, so every action card improves without a
  per-tool blocker.
- **OQ-3 (redaction vocabulary reuse):** confirm the mask-by-default vocabulary
  (`_SECRET_QUERY_PARAMS`) is the right shared basis for R-3, or whether B
  should introduce a broader secret-field allow-list. Recommendation: reuse the
  existing vocabulary, mask-by-default, no new list in B.
- **OQ-4 (informative ASK reason):** the gateway middleware already computes a
  per-tool ASK message — `"<tool> is outside the auto-approve allow-list;
  operator confirmation is required."` (`kernel_middleware.py`) — but it does not
  reach the card today, so `_confirmation_message` falls back to the generic
  constant (confirmed by the live test that surfaced R-4). Once R-4 persists the
  message, B *may* also wire that per-tool reason through so the card explains
  *why* confirmation is needed. That is an enhancement beyond parity; recommend
  deciding at implementation whether to surface the middleware reason verbatim or
  keep the generic line. Scoped as an open question so R-4 stays a pure
  persistence/parity fix.

## Changelog

- 2026-09-06: created as `draft`. Action-approval half of the operator-approved
  A→B→C program (A = the SPEC-051 R-6 headline-leak patch, landed; B = this
  spec; C = ADR-0009 + SPEC-055). Formalizes action-level HITL approval
  (`approval_kind`), extends per-action signed approval to ad-hoc browser writes
  on allowlisted origins (relaxing the flow-centric `BROWSER_FLOW_NOT_BOUND`
  hard-deny), and makes the action card a secret-masked change request. Reuses
  the SPEC-020/021/030/037 mechanism; additive contract change only; extends
  ADR-0007 without reversing it.
- 2026-09-06: folded in **R-4 (durable card-message parity)** from a live-test
  observation during A's (SPEC-051 R-6 headline-leak) validation — the card's
  `message` renders on the live operator stream but vanishes on any durable
  render (the approver/admin inbox and the owner's transcript on re-login)
  because it is frame-only and never persisted on `ConfirmationRecordModel`.
  R-4 persists it mirroring the `flow_summary` path. Chose persist (Option 2)
  over a frontend-only default so the fix survives the day the middleware's
  per-tool ASK reason is surfaced (OQ-4). The traceability requirement
  renumbered R-4 → R-5.
