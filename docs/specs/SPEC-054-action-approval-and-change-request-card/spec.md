# SPEC-054: Action-Level HITL Approval and the Change-Request Confirmation Card

## Status

- status: `delivered`
- owner: luban-platform-team
- created: 2026-09-06
- approved: 2026-09-07
- delivered: 2026-09-07 (v0.35.0)
- release slice: R5 — Hardening and External Consumption (sixteenth R5
  slice, v0.35.0)
- related ADRs: ADR-0007 (enforce one HITL gate per mutating browser flow —
  **extended, not reversed**), ADR-0008 (spec delivery traceability gate),
  ADR-0010 (signed execution envelopes declare their authority provenance —
  **proposed by this spec's R-2**; the trust-model refinement that replaces the
  staleness backstop R-2 removes);
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
risk tier, and a collapsed "Technical details" expander. Four gaps follow:

1. **Unbound browser writes are gated inconsistently, not uniformly.** Five of
   the six write-tier browser tools (`web.click`, `web.type`, `web.select`,
   `web.press_key`, `web.upload_file`) route through `gate_interaction`, which
   hard-denies with `BROWSER_FLOW_NOT_BOUND` when no flow is bound. The sixth,
   `web.evaluate`, routes through `gate_capture` instead — whose flow check
   applies *only when a flow is bound* — so an unbound `web.evaluate` on an
   allowlisted origin **already parks a per-action card and executes on approval
   today**. The platform therefore already has an unbound per-action browser
   write path; the other five tools are the outliers. Interactive web-app
   troubleshooting that mutates ("log in, then click *Confirm reset*") is
   impossible for them unless a skill flow was pre-declared and bound first,
   even though non-browser mutating tools already park per-action
   (SPEC-021/030/037). The blocker is a flow-centric guard, not a trust
   decision.
2. **The action card under-informs the approver.** It names the tool but not
   the *change*: which pod, which user, which target, which value. The
   decision-relevant parameters the operator already supplied sit in a collapsed
   expander, so the approver approves an opaque action rather than a described
   change.
3. **Unbound interactive login is blocked at the read tier.**
   `web.fill_credential` — the credential-set indirection that keeps a password
   out of tool arguments, results, evidence, and the audit trail (SPEC-049 R-5)
   — is read tier but is a ref-addressed `_WebInteractionTool`, so it inherits
   the same `gate_interaction` flow-binding precondition and is denied unbound.
   Relaxing only the *write* tier would leave the motivating scenario broken at
   the login step, and the only remaining way to enter a credential unbound
   would be `web.type` with the **literal secret as a tool argument** — which
   then lands in the parked payload, the confirmation card, the durable
   confirmation record, the audit trail, and the signed `args_digest`. That is a
   direct regression of the SPEC-049 R-5 posture, made *durable* by R-3/R-4.
4. **`BROWSER_FLOW_NOT_BOUND` is load-bearing as a staleness backstop, and
   relaxing it naively fails open.** The two sides of the flow binding can
   diverge: the tool-gateway clears `entry.flow` on a redirect halt, on
   `gate_capture`'s off-allowlist halt, and on a failed just-bound navigate,
   while the kernel's `FLOW_CONTEXTS` is **never cleared** (`_record_flow_context`
   records only on a *successful* navigate carrying a `flow` dict; a plain
   navigate carries none). Within the approval TTL, the kernel's flow-signer
   identity guard still matches the stale context, so the next `web.*` write is
   **auto-signed and ALLOWed with no card at all**. Today the gateway's
   flow-existence deny catches that and refuses the write. It is the *only*
   guard that does: origin match, `risk_class`, and step budget all live inside
   `gate_interaction` **after** the flow-existence check, and none of them apply
   to a session with no bound flow. So gap 1's relaxation cannot be a deletion —
   it must replace that backstop with an explicit one (R-2).

This spec makes **action-level approval first-class**: an explicit
`approval_kind: flow | action` discriminator on the confirmation frame and
durable record (R-1); ad-hoc browser interactions park as **per-action signed
gates** instead of being hard-denied, with the staleness backstop that
`BROWSER_FLOW_NOT_BOUND` was accidentally providing replaced by an explicit,
signed one (R-2); every action card becomes a **change request** that surfaces
the decision-relevant, secret-masked parameters in the approval intention
(R-3); and the card's confirmation `message` is persisted on the durable record
so the approver inbox and a re-loaded owner transcript render the same card the
live stream showed (R-4). It reuses the existing SPEC-020/021/030/037 per-action
approval + signed-execution mechanism — **no new approval mechanism, no new
policy action, no new audit event type**. R-2 does add one trust-model
*refinement*, recorded as ADR-0010: the signed execution envelope declares
**which authority authorized it** (`approval_kind`, the same vocabulary as R-1,
set by the builder that signs and covered by the HMAC), so the enforcement
boundary applies the right guard set instead of inferring it from whether a
flow happens to be bound. The contract changes are additive (`approval_kind` +
an optional `change_request` display projection + a persisted `message` on the
confirmation frame and its durable record; an optional `approval_kind` on the
execution-request envelope).

## Motivation

- The operator's target operating model is: (1) troubleshoot via chat with
  mutating actions properly approved; (2) turn a troubleshooting session into a
  reusable skill; (3) develop skills by running actions in chat
  ("develop-as-you-go"). Step (1) is impractical in the **web domain** today:
  unbound browser interactions are denied at the gateway rather than parked, so
  an interactive session cannot even reach a login form (gap 3), let alone
  mutate. Steps (2)/(3) are SPEC-055/ADR-0009; this spec is their prerequisite —
  a graduated flow is authored from a session of *approved per-action
  mutations*, which must first be possible.
- Evidence, per gap: (1) `test_click_without_bound_flow_denied` asserts the
  hard-deny for `web.click`, while `web.evaluate`'s guard is `gate_capture`
  (flow-optional) — so the unbound park-then-execute path already exists and is
  exercised for one tool only; `GatewayPermissionMiddleware.on_check_permission`
  ASKs for a non-flow browser write, but the gateway refuses it post-approval,
  so for five of six write tools the ASK is a dead end. (3) The existing
  unbound-`web.fill_credential` denial test asserts the read-tier block, and
  `web.fill_credential` is in `DEFAULT_AUTO_ALLOWED_TOOLS` — the kernel already
  treats it as gate-free, so only the gateway's flow precondition stops it.
  (4) `_record_flow_context` has no clearing path, the gateway clears
  `entry.flow` in three places, and `build_requests` / `build_flow_request` emit
  **byte-identical envelope shapes** — so nothing on the wire distinguishes a
  per-action-approved request from a flow-auto-signed one, which is precisely
  why the flow-existence deny was doing that job implicitly.
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
- The **same vocabulary** is used on the signed execution envelope (R-2 /
  ADR-0010), so one term describes a card's declared kind and the authority that
  actually authorized execution. The two are computed from different facts and
  serve different ends: the card's kind is derived at **park** time from the
  kernel's flow view and drives rendering; the envelope's kind is stamped at
  **sign** time by whichever builder ran and drives enforcement. They agree
  whenever the kernel's flow view is current, which R-2's clearing criterion is
  what guarantees — the card is honest because the authority cannot go stale,
  and execution is fail-closed because the envelope cannot lie.

### R-2: Ad-hoc browser interactions park as per-action signed gates, and flow authority can never outlive the gateway's binding

A `web.*` interaction issued **outside** a bound flow, on an allowlisted origin,
parks a per-action confirmation card and — on approval — executes through the
existing SPEC-037/038 signed path. It is never hard-denied solely for lacking a
bound flow, and never auto-allowed. Because `BROWSER_FLOW_NOT_BOUND` was also
serving as the platform's only staleness backstop (Summary gap 4), this
requirement **replaces** that backstop with two explicit ones — kernel-side
authority clearing and a signed authority-provenance discriminator (ADR-0010) —
rather than simply deleting the deny. Relaxation and replacement ship together;
neither is optional.

Acceptance criteria:

*Park, don't deny:*

- The tool-gateway no longer returns `BROWSER_FLOW_NOT_BOUND` as a hard deny for
  a **write-tier** interaction on an **allowlisted** origin; such a write is
  gated by the kernel's per-action ASK and, once approved and signed, executes.
  (`test_click_without_bound_flow_denied` is replaced by a park-then-execute
  expectation.) This aligns the five `gate_interaction`-routed write tools with
  `web.evaluate`, which already behaves this way.
- The flow-binding precondition is also relaxed for **read-tier ref-addressed
  interactions** — at minimum `web.fill_credential` — so an unbound session can
  reach and complete a login form. Credential entry unbound is **by reference
  only** (`credential_set` + `field`); a read-tier relaxation never admits a
  write without a card, and `web.fill_credential` remains in
  `DEFAULT_AUTO_ALLOWED_TOOLS` (the kernel already treats it as gate-free, so
  only the gateway precondition changes).
- Each ad-hoc browser write is **individually** approved and signed (its own
  `execution_id`, `args_digest`, `confirm_id`/`decider`) — there is **no**
  flow-unlock for unbound writes, so N interactive writes park N cards. The
  SPEC-051 one-gate collapse applies **only** to a bound flow (unchanged).

*Substitute guards (what bounds the unbound path):*

- **Live-origin re-check at interaction time.** With no bound flow, the
  `gate_interaction` origin-match, `risk_class`, and step-budget checks are all
  inapplicable, so the unbound path re-validates the **live** origin against the
  allowlist using `entry.active_target.url` (frame-aware, per SPEC-050 R-9) and
  halts on drift — the same check `gate_capture` already performs for the read
  tier, now applied before an unbound write executes. Without it a client-side
  redirect between `web.navigate` and the interaction would land an approved
  write on a drifted page.
- The origin allowlist (`GATEWAY_BROWSER_ALLOW_ORIGINS`) stays
  deny-by-default: an interaction on a non-allowlisted origin is still refused,
  with or without approval.
- **No step budget bounds the unbound path**, and this spec adds no knob for
  one. Per-action consent *is* the bound: every unbound write parks its own
  card, so blast radius grows only with explicit operator decisions. Bounding an
  accumulated *sequence* under a single gate is C's job — SPEC-055's graduation
  re-validation applies the step budget when a trace becomes a replayable flow.

*Staleness backstop (replaces what the deny was doing):*

- **Kernel-side clearing.** The kernel drops `FLOW_CONTEXTS` **and**
  `FLOW_APPROVALS` for a session when it observes a flow-killing gateway result
  (`BROWSER_REDIRECT_NOT_ALLOWED`, `BROWSER_FLOW_DENIED`,
  `BROWSER_FLOW_ORIGIN_DEVIATED`, or a failed flow-binding navigate) — it
  already sees every `tool_result` frame, so this is local to agent-platform.
  Kernel flow authority can no longer outlive the gateway's binding, which keeps
  R-1's card `approval_kind` honest about what will actually be enforced.
- **Signed authority provenance (ADR-0010).** Every execution-request envelope
  carries `approval_kind` ∈ {`action`, `flow`}, stamped by the builder that
  signs it (`build_requests` → `action`; `build_flow_request` → `flow`) and
  therefore **inside the HMAC signature** — it is a signed fact, not an unsigned
  hint. The field is optional on the contract so an envelope predating it still
  verifies; verification logic is unchanged because the signature already covers
  every field present.
- The gateway enforces provenance on the browser write path: a `flow`-provenance
  envelope presented when **no flow is bound** is refused with a new structured
  code (`BROWSER_FLOW_AUTHORITY_STALE`), never reinterpreted as a per-action
  approval — this is the explicit replacement for the accidental backstop. An
  `action`-provenance envelope never satisfies a bound-flow-only guard, so it
  cannot inherit flow-unlock treatment either.
- An approved **unbound** browser write never arms or extends flow-unlock:
  `_record_flow_approval` records nothing when the batch has no bound-flow
  identity, and additionally requires the bound flow's `risk_class == "write"`
  before arming (today it arms on a read-class binding too, producing an
  authority that can never execute — the gateway denies it
  `BROWSER_FLOW_READ_ONLY`). A `flow`-kind card on a read-class binding is
  surfaced as such rather than inviting an approval that must fail.

*Invariants that do not move:*

- Browser write tools still **never join any auto-allow list**; with bridging off
  (`hitl_confirm_timeout == 0`) an unbound browser write is denied, never
  silently executed (the existing auto-allow invariant test stays green).
- Non-browser mutating tools (`k8s.*`, etc.) are unchanged (they already park
  per-action); bound browser flows are unchanged (they still collapse to one
  gate, still TTL-bounded and identity-scoped). ADR-0007 is extended in scope,
  not reversed: one gate per *graduated/bound* flow, one gate per *ad-hoc*
  action.

### R-3: The action card is a change request

An `action` card surfaces the decision-relevant, operator-supplied parameters as
a readable **change request** — promoting them from the collapsed "Technical
details" expander into the approval intention — with secret values masked. It is
a **display-only projection** that never alters the signed `args_digest`.

Acceptance criteria:

- The confirmation-request frame carries an optional per-call `change_request`
  display projection, shaped as a **structured object** rather than a bare
  string: `summary` (a short human sentence naming the target and the effect,
  e.g. `Delete pod "scratch-restart-demo" in namespace "default"`) plus optional
  `fields` (label→value pairs, each flagged `masked`). The portal renders
  `summary` as the lead line and `fields` as a table when present, and falls
  back to today's tool-level rendering when the projection is absent. The
  structured shape is deliberate: SPEC-055's "secret-safe parameterized steps"
  need exactly this vocabulary, so C reuses it instead of migrating a string.
- Assembly is **curated + generic**: a per-tool formatter writes the `summary`
  for the demo-critical mutating tools (`k8s.delete_pod` and the write-tier
  `web.*` family, plus `web.fill_credential` — which shows `credential_set` and
  `field` and **never** a value), and every other tool gets a generic
  label→value projection built from its parameters. No action card regresses
  for want of a curated formatter, and no curated formatter blocks the
  requirement.
- Secret-bearing parameter **values** are masked (`***`) using the existing
  redaction vocabulary (`_is_secret_param` / `_SECRET_QUERY_PARAMS` and the
  `_redact_secret_query` mask-by-default posture, SPEC-049 R-5); the parameter
  *key* is preserved so the approver sees that a secret is involved without
  seeing it. Masking is **by default** — an allow-list of known-safe fields may
  be shown verbatim, everything else masks.
- Name-based masking is necessary but **not sufficient**, so a per-tool
  opaque-value rule accompanies it: a secret in a generically-named field is
  invisible to `_is_secret_param` (`web.type`'s `text` does not match any entry
  in `_SECRET_QUERY_PARAMS`), and the projection is assembled **kernel-side**,
  where the gateway's known-secret value set (`entry.secret_values`, used to
  mask screenshots) is not available. Fields on that per-tool opaque list are
  therefore masked wholesale regardless of name. The structural fix is R-2's
  reference-only credential entry: with `web.fill_credential` reachable unbound,
  a credential never needs to appear as a literal argument in the first place.
- The projection is built **separately** from the signed parameters, exactly as
  SPEC-050's `display_hint` is: `args_digest` (and therefore the signature and
  gateway verification) is computed over the true parameters and is unchanged by
  the projection. A tampered or absent projection never affects execution.
- The curated formatter's effect sentence is also the source of the card's
  informative `message` where one exists, replacing the generic fallback
  constant — so the card explains *what changes* and *why approval is needed*
  from one table. The gateway middleware's ASK string is **not** wired through
  verbatim: it interpolates the *sanitized* tool name (`web_click`), which would
  break the dotted-canonical-tool-name convention, and it explains an
  implementation detail ("outside the auto-approve allow-list") rather than the
  change. Any middleware-derived reason must be canonicalized via
  `gateway_tool_name` first.
- The full parameters remain available in the existing collapsed "Technical
  details" expander (the change request complements, not replaces, it).
- Durable and replayed `action` cards render the same change request as the live
  card.
- No new policy action or audit event type; no shared-schema change beyond the
  additive `approval_kind` / `change_request` fields in R-1.

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
  contract-drift guard on the additive fields). R-2's safety criteria are
  individually pinned, not covered incidentally: provenance stamped per builder
  (`build_requests` → `action`, `build_flow_request` → `flow`) and inside the
  signature; gateway refusal of a `flow`-provenance envelope with no bound flow
  (`BROWSER_FLOW_AUTHORITY_STALE`); kernel clearing of `FLOW_CONTEXTS` +
  `FLOW_APPROVALS` on each flow-killing result; read-tier unbound
  `web.fill_credential` admitted while an unbound write still parks;
  live-origin re-check + halt on drift before an unbound write; no flow-unlock
  arming for an unbound or read-class binding; opaque-value masking for
  `web.type.text`.
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
- **No new approval mechanism.** Per-action browser-write approval reuses the
  SPEC-020/021/030/037 approval + signed-execution model: same park, same card,
  same signature, same receipt. ADR-0007 is extended in scope, not reversed.
  The one addition is *declarative* — the signed envelope states which authority
  authorized it (ADR-0010) — which narrows what an approval can be used for
  rather than granting anything new. Note that the gateway's bound-flow
  deviation guard is **not** the enforcement boundary for the unbound path (no
  flow means no origin-match, `risk_class`, or step-budget check to apply);
  R-2's live-origin re-check plus per-action consent plus the signature are.
- **No structured per-step plan rendering** (SPEC-049 R-4's literal "declared
  steps") and no machine-readable step list on skills — unchanged from SPEC-051.
- **No parameterized/templated `flow_intent`** (a skill-authored intent with
  runtime-substituted values) — deferred to SPEC-055 (C); R-3's change request
  is assembled at park time from the actual call parameters.
- **No masking of the raw parameters already persisted on the durable record.**
  R-3 masks the *projection*. The parked `pending_calls` payload persists
  parameter values unmasked today (the SPEC-031 record shape) and still renders
  them in the collapsed "Technical details" expander, so a literal secret passed
  as a tool argument is durable now and remains durable after this spec. This is
  a **pre-existing** gap, not one B introduces; fixing it means changing the
  parked-payload shape that the signed path, the durable record, and the portal
  all read, which is out of proportion to this slice. Recorded explicitly so it
  is not rediscovered as a B regression. The mitigation B does ship is
  structural: R-2 makes reference-only credential entry (`web.fill_credential`)
  reachable unbound, and R-3 masks opaque-value fields in the projection, so the
  case where a literal secret is the *only* way to proceed is removed.
- **No step-budget knob for unbound sessions.** Per-action consent is the bound
  (R-2); an accumulated sequence is budgeted at graduation, which is SPEC-055's
  blast-radius re-validation.

## Impact

- products touched:
  - `products/agent-platform` — confirmation-frame builder sets `approval_kind`
    (reusing `_tool_names_have_browser_write` + the bound-`FlowContext` check)
    and assembles the per-call `change_request` projection from parameters with
    secret masking (curated per-tool formatter table + generic fallback + the
    opaque-value list); `PendingConfirmation` / `pending_calls_payload` carry the
    projection; the durable confirmation record persists `approval_kind` +
    `change_request` + the card `message` (R-4, mirroring `flow_summary`);
    `execution_signing.build_requests` / `build_flow_request` each stamp their
    `approval_kind` **before** signing; `_record_flow_approval` additionally
    requires a `write`-class binding; and a new clearing path drops
    `FLOW_CONTEXTS` + `FLOW_APPROVALS` on flow-killing gateway results
    (`runtime_kernel.py`, `services/execution_signing.py`,
    `services/flow_approvals.py`, `services/hitl_confirmations.py`,
    `services/confirmation_records.py`, `schemas/v2.py`, `api/v2/routes.py`).
  - `products/tool-gateway` — the interaction path parks-not-denies an
    **allowlisted** unbound browser write (relax `BROWSER_FLOW_NOT_BOUND` to a
    per-action gate) and admits read-tier ref-addressed interactions unbound
    (`web.fill_credential`); adds the live-origin allowlist re-check with
    halt-on-drift before an unbound write executes; enforces envelope
    provenance, refusing a `flow`-provenance envelope with no bound flow
    (`BROWSER_FLOW_AUTHORITY_STALE`). The origin allowlist, risk tiers, and the
    bound-flow deviation guard are unchanged. The redaction vocabulary
    (`_is_secret_param` / `_SECRET_QUERY_PARAMS` / `_redact_secret_query`) is
    **reused, not imported**: this workspace has no cross-product Python
    imports, so "shared" means either publishing the vocabulary as *data* under
    `shared/shared-contracts` (validated like the policy bundle) or keeping a
    second copy in agent-platform pinned by a contract-drift test — resolved at
    implementation, recorded in `plan.md`
    (`tools/browser_connector.py`, `tools/browser_sessions.py`).
  - `products/operator-portal` — decode `approval_kind` + `change_request`;
    render the change-request layout (`summary` lead line + optional `fields`
    table) for `action` and the flow headline for `flow`, with today's
    tool-level rendering as the fallback; map the persisted `message` in
    `confirmationRecordToCard` + the `ConfirmationRecord` type so the inbox and
    re-loaded transcript render the same card message (R-4)
    (`web-ui/app/src/stream/decoder.ts`, `.../stream/models.ts`,
    `.../chat/ChatView.tsx`, `.../chat/transcript.ts`, `.../api/sessions.ts`).
  - `products/execution-runtime` — **small change** (corrected at plan time;
    see the 2026-09-07 changelog entry — this bullet originally read "no code
    change; verify only"). The worker's verification (token, required fields,
    HMAC over the canonical JSON of every field present, `args_digest`,
    single-flight on `execution_id`) is unchanged by an additional **optional**
    envelope field: `approval_kind` rides inside the existing signature rather
    than requiring a new verification rule, and provenance semantics remain a
    browser-path concern the worker never evaluates. But the gateway never sees
    the envelope — verification happens in the worker
    (`api/routes/handoff.py`), which then POSTs a plain
    `{tool_name, parameters, request_id, session_id?}` to
    `/api/v2/tools/invoke` (`services/executor.py`) — so R-2's "the gateway
    enforces provenance on the browser write path" requires the worker to
    forward the value it has already verified, mirroring the SPEC-049 R-1
    `session_id` precedent: a **provenance handle, not authority**, treated by
    the gateway as untrusted input whose only permitted effect is a refusal.
- samples / shared touched: `shared/shared-contracts/schemas/
  agent-stream-event.schema.json` (additive `approval_kind` + `change_request`
  on the confirmation-request frame; additive stream-schema version bump — the
  exact next version number is resolved at implementation against the delivered
  schema, whose title currently reads v9 with SPEC-053's `flow_intent` already
  riding `flow_summary`), the durable confirmation-record schema
  (`agent-session.schema.json`: additive `approval_kind` + `change_request` +
  `message`, R-4), and `execution-request.schema.json` (additive **optional**
  `approval_kind`, R-2/ADR-0010 — note that schema declares
  `additionalProperties: false`, so the property must be added explicitly rather
  than merely emitted; it stays out of `required` so envelopes predating it
  remain valid). While in that file, correct the stale `tool_name` description —
  it reads "Sanitized tool name of the parked call", but `pending_calls_payload`
  deliberately emits the **gateway canonical dotted name** (as does
  `build_flow_request`), so both builders agree and only the schema prose is
  wrong. An interactive per-action browser-write demo under `samples/`
  is **recommended** now that R-2 makes the unbound login-then-mutate scenario
  reachable, and if shipped it is exercised in the verification path per
  ADR-0008 (R-5).
- contracts touched: `agent-stream-event.schema.json` (additive) + the
  confirmation-record contract (additive) + `execution-request.schema.json`
  (additive optional). No policy (`policy-default.yaml`) or audit-event schema
  change; no new policy action or audit event type.
- identity / policy / audit / execution safety impact: execution safety —
  extends the per-action signed-execution path to the browser tool family for
  unbound interactions on allowlisted origins, and **narrows** what an existing
  authority can be used for by binding it to its provenance (a flow-auto-signed
  envelope can no longer execute where no flow is bound, which today only fails
  closed by accident). No identity or policy model change; audit rides the
  existing `confirmation_decided` / `execution_requested` / `tool_invoked` /
  `execution_completed` events.
- living state docs to update on delivery: root `CHANGELOG.md`, `VERSION`
  (+ lockstep constants), `docs/agentic-aiops-platform/release-notes/` (new note
  + index), `docs/guides/configuration-reference.md` (only if a new knob is
  introduced — none planned), `docs/specs/README.md` (SPEC-054 row →
  `delivered`), `docs/adr/README.md` (ADR-0010 row → `accepted`), and
  `docs/agentic-aiops-platform/delivery-roadmap.md`. Note on the last: **no
  SPEC-054 row exists to flip** — the R5 section is narrative-only and the
  Exploration Backlog table carries no SPEC-049..055 rows, so approval *adds* a
  backlog row for SPEC-054 (SPEC-021/022 style) and delivery updates it.
  SPEC-055 will owe the same row.

## Open Questions

All four original questions, plus one added during the 2026-09-07 code review,
are **resolved**; the decisions below are binding on `plan.md`. None remains
open.

- **OQ-1 (ADR cover for R-2) — resolved: yes, write ADR-0010, but not for the
  reason originally posed.** The scope widening *alone* would not be ADR-worthy:
  the approval mechanism is unchanged, `docs/adr/README.md` forbids ADRs for
  decisions local to a single spec, and the review established that an unbound
  per-action browser write is **already possible today** via `web.evaluate`
  (guarded by flow-optional `gate_capture`), so R-2 closes an inconsistency in
  shipped behavior rather than widening the trust model. What *is* ADR-worthy is
  the replacement backstop R-2 now requires: stamping **authority provenance**
  into the signed execution envelope is a trust-model rule that constrains
  agent-platform (which builder stamps what), tool-gateway (which guard set
  applies), and SPEC-055's replay path (a graduated flow replays under one-gate
  authority and needs the same distinction), i.e. more than one product and more
  than one spec. Recorded as **ADR-0010 (`proposed`)**; ADR-0007 stays
  `accepted` and is extended, not reversed. Per the immutability rule, the
  "extends ADR-0007" statement lives here and in ADR-0010 — ADR-0007's body is
  **not** edited.
- **OQ-2 (change-request assembly) — resolved: curated + generic fallback, with
  a structured projection.** Per-tool formatters write the `summary` for the
  demo-critical mutating tools; every other tool gets a generic label→value
  projection, so no action card regresses and no formatter blocks the slice. The
  projection is an object (`summary` + optional `fields[]`, each flagged
  `masked`) rather than a bare string — marginally more schema and portal work,
  but SPEC-055's secret-safe parameterized trace steps need exactly this shape,
  so it is built once. See R-3.
- **OQ-3 (redaction vocabulary reuse) — resolved: reuse it, mask-by-default, no
  new secret-field allow-list, plus a per-tool opaque-value rule.** The review
  found name-based masking insufficient on its own: `_is_secret_param` cannot
  see a secret in a generically-named field (`web.type`'s `text` matches nothing
  in `_SECRET_QUERY_PARAMS`), and the projection is assembled kernel-side where
  the gateway's known-secret value set is unavailable. So the existing vocabulary
  stays the basis, and fields on a small per-tool opaque list mask wholesale
  regardless of name. "Lifting to a shared helper" is **not** available — no
  cross-product Python imports exist here — so reuse means shared-contracts
  *data* or a pinned duplicate; resolved at implementation (see Impact).
- **OQ-4 (informative ASK reason) — resolved: folded into R-3, and the
  middleware string is not wired through verbatim.** R-4 stays a pure
  persistence/parity fix. The informative reason comes from R-3's curated
  formatter table (the same sentence that describes the change), which is
  decision-useful, rather than from `kernel_middleware`'s ASK message — that
  string interpolates the **sanitized** tool name (`web_click`), which would
  break the dotted-canonical-tool-name convention, and it explains an
  implementation detail ("outside the auto-approve allow-list") instead of the
  change. Any middleware-derived reason must be canonicalized via
  `gateway_tool_name` first.
- **OQ-5 (added 2026-09-07: does the mask obligation extend to the raw
  persisted parameters?) — resolved: no, out of scope, recorded as a known
  pre-existing gap.** R-3 masks the projection only; `pending_calls` persists
  parameter values unmasked today and still renders them in "Technical details",
  so a literal secret passed as an argument is durable before and after B.
  Fixing it means changing the parked-payload shape that the signed path, the
  durable record, and the portal all read. Recorded in Non-Goals with B's
  structural mitigation (reference-only credential entry reachable unbound) so
  it is not rediscovered as a B regression.

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
- 2026-09-07: revised against a code review of the delivered guard topology;
  status stays `draft` (no `plan.md`/`tasks.md` authored — SDD Phase-1 pause).
  Four changes. **(1) R-2 rewritten from a relaxation into a
  relaxation-plus-replacement.** The review found `BROWSER_FLOW_NOT_BOUND` is
  load-bearing as the platform's *only* staleness backstop: the gateway clears
  `entry.flow` in three places while the kernel's `FLOW_CONTEXTS` is never
  cleared, so within the approval TTL the flow-signer identity guard still
  matches a stale context and auto-signs the next `web.*` write with **no card
  at all** — and the origin-match, `risk_class`, and step-budget guards all sit
  *after* the flow-existence check, so none of them catch it. Deleting the deny
  alone would therefore fail open. R-2 now requires, in the same slice:
  kernel-side clearing of `FLOW_CONTEXTS` + `FLOW_APPROVALS` on flow-killing
  results, and a signed **authority-provenance** discriminator on the execution
  envelope (`approval_kind`, stamped by whichever builder signs, inside the
  HMAC) that the gateway enforces with a new `BROWSER_FLOW_AUTHORITY_STALE`
  refusal. `build_requests` and `build_flow_request` emit byte-identical
  envelopes today, which is why the deny was doing this job implicitly.
  **(2) R-2 scope widened to the read tier.** `web.fill_credential` is read tier
  but is a ref-addressed `_WebInteractionTool`, so it inherits the same
  flow-binding precondition; relaxing writes only would leave the motivating
  login-then-mutate scenario broken and push credential entry toward `web.type`
  with a literal secret in the arguments, the card, the durable record, the
  audit trail, and `args_digest`. Unbound credential entry is now
  reference-only. R-2 also names the substitute guard the unbound path actually
  gets (`gate_capture`-style live-origin re-check on `entry.active_target.url`,
  halt on drift) and states plainly that no step budget bounds it — per-action
  consent is the bound, and SPEC-055 budgets the accumulated sequence at
  graduation. **(3) R-3 projection is structured** (`summary` + optional
  `fields[]` with a `masked` flag) rather than a bare string, so SPEC-055's
  secret-safe parameterized steps reuse it; assembly is curated + generic
  fallback; and a per-tool opaque-value rule covers what name-based masking
  cannot (`web.type.text` matches nothing in `_SECRET_QUERY_PARAMS`, and the
  kernel cannot see the gateway's known-secret value set). **(4) Corrections.**
  The Motivation claim that browser writes cannot be approved per-action at all
  was wrong — `web.evaluate` routes through flow-optional `gate_capture` and
  already parks-then-executes unbound, so R-2 closes an inconsistency in shipped
  behavior; "may be lifted to a shared helper" is unavailable (no cross-product
  Python imports in this workspace); `_record_flow_approval` arms on a
  read-class binding today, producing an authority that can never execute, so
  arming now requires `risk_class == "write"`. OQ-1..OQ-4 resolved, OQ-5 added
  and resolved into Non-Goals, `execution-request.schema.json` added to Impact
  (`additionalProperties: false`, so the optional field must be declared), and
  the delivery-roadmap claim corrected — no SPEC-054 row exists to flip, so
  approval adds one. ADR-0010 drafted as `proposed` alongside this revision.
- 2026-09-07: **approved** by the operator with no further requirement changes,
  and ADR-0010 accepted the same day — which is what unblocks R-2's paired
  relaxation and replacement. Slice fixed as the sixteenth R5 slice.
  Bookkeeping: `docs/specs/README.md` row `draft` → `approved`, and a new
  `delivery-roadmap.md` Exploration Backlog row **added** (none existed to flip).
  The deferred clean v0.34.1 image build/deploy rides this spec's delivery —
  dev-k8s currently runs the dirty tag
  `0.34.0-dev-k8s-123c4b6-dirty-20260906161715`. R-1..R-5 are now frozen and
  change only by agreement recorded here; `plan.md` and `tasks.md` are authored
  next.
- 2026-09-07: **Impact correction, agreed by the operator's "go and proceed"** —
  no requirement text changed. The pre-implementation code read behind `plan.md`
  found the `products/execution-runtime` Impact bullet factually wrong: it read
  "no code change; verify only", but R-2's acceptance criterion that *the
  gateway* enforces authority provenance cannot be met by the gateway alone,
  because **the gateway never receives the signed envelope**. Verification lives
  in the worker (`api/routes/handoff.py`), which then POSTs a plain
  `{tool_name, parameters, request_id, session_id?}` to
  `/api/v2/tools/invoke`; the only `signature` string anywhere in
  `products/tool-gateway/src/` is an entry in `_SECRET_QUERY_PARAMS`. The bullet
  now reads "small change": the worker forwards the `approval_kind` it has
  already verified inside the HMAC, mirroring the SPEC-049 R-1 `session_id`
  precedent verbatim in framing ("a correlation handle, not authority") and
  preserving `api/routes/tools.py`'s documented rule that body-carried data is
  never trusted as identity. The check is **one-directional and fail-closed** —
  a declared kind can only ever add a refusal, never remove one, and the guard
  set applied is still selected by the gateway's own flow binding — so the
  forwarded value is untrusted input with no authority. `verify_envelope` and
  the signature shape are unchanged; R-2's criteria all still hold as written.
  Full reasoning and the rejected alternatives (gateway infers provenance from
  its own state; kernel-side clearing alone, which ADR-0010 already rejects as
  *sufficient*; a new signed header on the invoke hop) are in `plan.md`
  §"Resolved At Plan Time" 4. Two other plan-time resolutions of items this spec
  delegated to implementation, recorded here for completeness: the stream schema
  advances **v9 → v11** (retro-fitting the v10 clause SPEC-053 shipped but never
  recorded, since `schemas/v2.py` already declared v10), and it additionally
  declares `display_hint` on `pending_calls.items`, which SPEC-050 emits and the
  portal reads but which was never added to a schema declaring
  `additionalProperties: false` — a latent contract violation R-3's realistic
  parked-frame tests would otherwise trip on.
- 2026-09-07: **delivered** (v0.35.0, sixteenth R5 slice). All five
  requirements shipped across the staged plan. **R-1** — the
  `approval_kind: flow | action` discriminator is computed on one kernel
  branch (`"flow" if browser_flow else "action"`) with `flow_summary` present
  iff `"flow"`, so a card's kind and its headline can never disagree (the
  structural fix behind the v0.34.1 SPEC-051 R-6 headline-leak patch); stream
  schema advanced **v9 → v11**, retro-fitting the v10 clause SPEC-053 shipped
  but never recorded and declaring the latent `display_hint` on
  `pending_calls.items`. **R-2** — the gateway now parks unbound allowlisted
  browser writes as per-action signed gates instead of hard-denying
  `BROWSER_FLOW_NOT_BOUND`, shipped together with the paired fail-closed
  replacements: kernel clearing of `FLOW_CONTEXTS`/`FLOW_APPROVALS` wherever
  the gateway clears its own binding, reference-only unbound
  `web.fill_credential` (gap-3), and the **ADR-0010** signed
  authority-provenance discriminator that the execution-runtime worker
  forwards (verified inside the HMAC, untrusted-as-identity) and the gateway
  enforces one-directionally with a new `BROWSER_FLOW_AUTHORITY_STALE`
  refusal. **R-3** — the display-only secret-masked `change_request`
  projection (`{summary, fields[]}`) is assembled as a *sibling* of
  `parameters`, never inside, so `canonical_digest(parameters)`/`args_digest`
  stays byte-identical. **R-4** — the card `message` is computed once at park
  time and persisted on the durable record for inbox/re-login replay parity.
  **R-5** — the operator-portal decodes all three fields and renders the flow
  headline, the change-request layout, or today's tool-level fallback
  data-drivenly. A new `validate_secret_vocabulary.py` leg joins `make verify`
  (the agent-platform and tool-gateway secret-parameter tuples agree, 20
  substrings). Shipped with an unbound per-action browser-write sample
  (`samples/web-checks/adhoc-password-reset/` — a no-`web_target` runbook, so
  the session is platform-enforced unbound and every write parks its own
  card) whose `demo.sh` exercises the path per **ADR-0008**. No new policy
  actions, no new audit event types; additive contract change only
  (`execution-request.schema.json` plus the confirmation frame/record).
  `make verify` green (all product pytest, kustomize overlays, policy rules
  and scenarios, version lockstep, the new secret-vocabulary leg); portal
  `npm test` 303 and `npm run build` clean; version lockstep **0.35.0** across
  `VERSION` + 8 `pyproject.toml` + 8 `metadata.py` + 2 `__init__.py` + 8
  `uv.lock` re-locks.
- 2026-09-07: **post-delivery fix, folded into v0.35.0** (no requirement text
  changed) — the `dev-k8s` browser live check of the unbound per-action sample
  (`samples/web-checks/adhoc-password-reset/`) surfaced a defect in the N-card
  path R-2 makes reachable. R-2's criterion that "N interactive writes park N
  cards", each **individually** approved and signed, requires a second unbound
  write to park a card its approver is actually allowed to decide. But when an
  approver's decision resumes a turn that then parks *another* per-action card,
  `resume_confirmation` passed the approver's identity as the resumed turn's
  `user_name`, so the re-parked card was attributed `owner_user_id = <approver>`.
  The platform-gateway's SPEC-030 R-3 tier check then saw `owner == approver` and
  blocked that same approver from deciding the next card with a `self_approval`
  403 (tier_2 forbids self-approval) — so a second unbound write could never be
  approved by the approver who cleared the first. It is newly reachable only
  because R-2 relaxed unbound writes from a hard `BROWSER_FLOW_NOT_BOUND` deny
  into a per-action park, so a resumed turn could park again at all. Fix (kernel
  + route only): `resume_confirmation` now takes the session owner separately
  (`owner_user_name`, threaded from `session.user_id` by the confirm route) and
  attributes any re-parked card to the requester, while the approver stays the
  decider of the card they answered (its resolution, signed executions, and flow
  authority); it defaults to the decider for an ownerless session, preserving the
  prior attribution. No contract, policy, audit, or portal change; R-1..R-5 stand
  as written. Pinned by three regression tests (kernel re-park owner attribution,
  the ownerless-session default, and the confirm-route wiring); `make verify`
  green (agent-platform 857). Recorded in the root `CHANGELOG.md` under
  0.35.0 → Fixed.
- 2026-09-07: **forward cross-reference (no requirement text changed; R-1..R-5
  stand as delivered/frozen)** — the change-request secret-masking gap this spec
  recorded and deferred is now scheduled. The Non-Goal "**No masking of the raw
  parameters already persisted on the durable record**" + OQ-5 (the
  "**pre-existing** gap" where `pending_calls` persists parameter values
  unmasked and the "Technical details" expander renders them), together with the
  generic-projection fail-open the R-3 assembly leaves for an off-vocabulary
  secret value, are picked up by **SPEC-055 R-7 (approval-seam secret-masking
  hardening)**, folded into that `approved` spec post-approval on 2026-09-07 by
  operator agreement. A post-delivery code & doc review re-confirmed both as the
  same pre-existing gap (not a B regression), which is why they land as the
  source-side complement of SPEC-055 R-2's secret-safe trace capture rather than
  a standalone spec — SPEC-055 R-2 already parameterizes secrets at the approval
  seam reusing the same SPEC-049 R-5 vocabulary, and R-3's structured
  `{summary, fields[]}` projection was built "so SPEC-055's secret-safe
  parameterized steps reuse it." R-7 inherits the parked-payload-shape tension
  this spec named (the signed `args_digest` reads the raw `parameters`) and works
  it in SPEC-055's `plan.md`. Recorded here so the deferral is not rediscovered
  as unresolved; the two items ship on SPEC-055's timeline, not an interim
  0.35.x patch (both non-blocking defense-in-depth over the reference-only
  `web.fill_credential` floor R-2 shipped).
