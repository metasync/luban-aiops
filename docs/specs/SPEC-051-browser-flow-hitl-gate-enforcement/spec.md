# SPEC-051: Browser Flow HITL Gate Enforcement and Password-Reset Sample Reconciliation

## Status

- status: `delivered`
- owner: luban-platform-team
- created: 2026-09-04
- delivered: 2026-09-04 (v0.33.0)
- release slice: R5 — Hardening and External Consumption (thirteenth R5
  slice, v0.33.0)
- related ADRs: ADR-0007 (enforce one HITL gate per mutating browser flow
  platform-side), ADR-0008 (spec delivery traceability gate); lineage:
  completes SPEC-049 R-4/D-3 (browser web-check tools), extends SPEC-050
  (browser tools expansion and samples), SPEC-037 (signed execution
  requests), SPEC-038 (isolated execution worker), SPEC-020 (HITL
  confirmation bridging), SPEC-021 (bounded mutating actions), SPEC-030
  (require-approval semantics)

## Summary

SPEC-049 R-4 specified that a `write`-class browser flow parks exactly one
confirmation card and that "approval unlocks the bound flow's interactions
for that session," but only the tool-gateway half (flow binding, origin
allowlist, `risk_class`, step-budget deviation guard) was implemented; the
agent-platform kernel never collapsed the per-write ASKs, so every
write-tier browser interaction parks its own card. A live password-reset
test on v0.32.0 exposed this. This spec completes R-4 platform-side — one
operator decision per mutating browser flow, with each unlocked write still
signed, persisted, audited, receipted, and gateway-guarded — and reconciles
the password-reset sample so its single gate lands on the destructive
"Confirm reset" action rather than on authentication. It also makes that
single card **flow-semantic** (R-6): the card names the workflow the operator
is approving — the bound skill's declared title, description, target origin,
and risk class — instead of a bare tool action like `web.click`, realizing the
second half of SPEC-049 R-4 ("the card names the skill, target origin, and
declared steps"). It adds **no new policy actions, no new audit event types,
and no new shared-contract schemas**.

## Motivation

- Today `GatewayPermissionMiddleware.on_check_permission` answers every
  non-allow-listed write tool with an independent ASK, with no flow or
  session memory, and each mutating call requires its own SPEC-037 signed
  execution envelope built only from a parked→approved card. tool-gateway
  owns the flow model and enforces the deviation guard, but does not park or
  resolve cards.
- Evidence: a live password-reset demo/test on the deployed v0.32.0 parked
  an approval card for *every* write-tier browser interaction, contradicting
  SPEC-049 R-4's acceptance criterion and D-3's "one operator decision per
  mutating flow." Investigation confirmed R-4's flow-unlock was never
  implemented in the kernel and that SPEC-050 did **not** regress it (its
  only kernel change was adding read-tier tools to the auto-allow list).
- A second, independent defect compounds it: the password-reset sample is
  internally inconsistent — the skill/README/WALKTHROUGH name the admin
  sign-in click as the single write, while the target pages auto-submit both
  the login and the reset, and the pages' own comment says the gate belongs
  on "Confirm reset." The contradiction makes the model improvise extra
  writes, and the demo script was patched to *tolerate* a second card
  instead of fixing the cause.
- A third facet compounds the operator's confusion: even a single card is
  **tool-level** today. `pending_calls_payload` renders only the tool name, an
  element display hint, and a risk tier, so the operator is asked to approve
  `web.click` on `<button> "Sign in"` with no indication of the workflow it
  belongs to. SPEC-049 R-4 also required the card to name "the skill, target
  origin, and declared steps" — a second unimplemented half of R-4. Approving a
  named workflow ("Reset User Password in Admin Portal") is the operator-facing
  point of per-flow approval; approving an opaque tool action is not.
- Why now: this is a trust-model correctness gap in a delivered capability,
  surfaced by operator use. R5 is the hardening release, and ADR-0007/
  ADR-0008 record the decision and the delivery-gate control that would have
  caught it.

## Requirements

### R-1: Platform-enforced flow-unlock — one HITL gate per mutating browser flow

The agent-platform kernel enforces SPEC-049 R-4: the first write-tier
browser interaction in a `write`-class flow parks exactly one confirmation
card through the existing SPEC-020 bridge; on approval the kernel records a
flow authority scoped to the chat session **and the approved flow's identity**
(`skill_id` + `origin`), and every subsequent write-tier browser interaction
is admitted without a further card **only while the session remains bound to
that same flow**. The kernel maintains this flow identity as a session-scoped
`FlowContext` updated from each `web.navigate` result (the gateway-owned flow
binding it reflects), so the authority is scoped to a real flow, not to the
session alone.

Acceptance criteria:

- A `write`-class browser flow parks exactly one confirmation card; after
  approval, subsequent write-tier browser interactions in the same flow
  execute without parking further cards.
- The authority is scoped to the approved flow's identity: if the session
  rebinds to a *different* `write`-class flow (a new `skill_id`/`origin`), the
  next write-tier interaction re-parks a fresh card rather than auto-signing
  under the earlier approval — the ADR-0007 cross-flow-rebind trade-off is
  **eliminated**, not merely bounded.
- After denial, further interactions in the flow are refused (unchanged
  SPEC-049 behavior).
- An interaction outside any bound flow, or past the step budget, still
  parks its own per-action confirmation (or is denied when bridging is off)
  and never executes silently.
- Browser write tools never join any auto-allow list: with no recorded flow
  approval a browser write still ASKs (the existing
  `test_browser_write_tools_never_auto_allowed_even_if_forced` invariant
  stays green).
- Non-browser mutating tools (`k8s.*`, etc.) are unaffected by flow-unlock
  and continue to gate per SPEC-021/030/037.

### R-2: Time-bounded, flow-scoped session authority

The recorded flow authority is scoped to the chat session and the approved
flow's identity, and bounded by a configurable TTL; it can be disabled.

Acceptance criteria:

- A new knob `AGENT_BROWSER_FLOW_APPROVAL_TTL` (default `900` seconds,
  `>= 0`) bounds how long a recorded flow approval unlocks writes; an
  expired approval no longer unlocks (the next write parks again).
- Setting the TTL to `0` disables flow-unlock and restores the pre-fix
  posture (every browser write parks its own card).
- The authority is keyed on the chat session id **and the approved flow's
  identity** (`skill_id` + `origin`, the same handles the gateway flow binding
  uses), carrying no independent privilege beyond unlocking that flow's
  browser writes for that session.

### R-3: Unlocked writes stay signed, audited, receipted, and gateway-guarded

Every write admitted under a flow authority carries the same
execution-safety guarantees as an approved-card execution.

Acceptance criteria:

- Each unlocked write is signed by the kernel under the approving card's
  authority (fresh `execution_id`, the call's own `args_digest`, reusing the
  card's `confirm_id`/`decider_user_id` and the platform signing key) and
  handed off through the existing SPEC-037/038 path.
- Each unlocked write is persisted (`execution_requested`) and audited
  through the existing execution events, and produces a receipt on
  completion — identical to an approved-card execution.
- The tool-gateway deviation guard (origin allowlist, declared `risk_class`,
  step budget `GATEWAY_BROWSER_FLOW_MAX_STEPS`) still bounds every unlocked
  write; the session id is forwarded on the write path so the guard applies.
- No new policy action, audit event type, or shared-contract schema is
  introduced.

### R-4: Password-reset sample reconciled to a single gate on "Confirm reset"

The `samples/web-checks/password-reset` sample demonstrates exactly one HITL
gate, landing on the destructive reset action, with skill, target pages,
README, WALKTHROUGH, and demo script in agreement.

Acceptance criteria:

- The target pages auto-submit the admin login (read-tier authentication)
  but the reset form pre-fills from the URL and does **not** auto-submit; the
  sole write-tier interaction is the `web.click` on "Confirm reset."
- The skill (`ResetUserPassword.md`) declares the single write as the
  "Confirm reset" click and describes login as read-tier; its version is
  bumped.
- README and WALKTHROUGH describe the gate as landing on "Confirm reset,"
  not on sign-in; the sequence diagram and key-observations match.
- `demo.sh` asserts exactly one confirmation card whose execution is the
  `web.click` with a signed receipt; the second-card tolerance is removed.
- The deterministic legs still pass and the chat leg runs green end-to-end
  on the canonical deployment.

### R-5: Delivery traceability per ADR-0008

This spec is delivered under the ADR-0008 gate.

Acceptance criteria:

- Every R-1..R-4 and R-6 acceptance criterion maps to at least one automated
  test (or, for the sample demo, the `demo.sh` chat leg) recorded in
  `tasks.md`.
- The password-reset sample demo is exercised as part of the verification
  path (its `demo.sh` chat leg), satisfying ADR-0008's exercised-sample
  rule.
- `CONTRIBUTING.md` and `docs/specs/README.md` carry the ADR-0008
  delivery-gate text.

### R-6: Flow-semantic confirmation card

The single confirmation card a `write`-class browser flow parks describes the
**workflow** the operator is approving — the bound skill's declared intent —
not merely the tool action that triggered it. This realizes the second half of
SPEC-049 R-4 ("the card names the skill, target origin, and declared steps"),
which was never implemented: today `pending_calls_payload` renders only the
tool name, an element display hint, and a risk tier.

Scope (operator-approved): **flow headline + tool detail** — a prominent card
headline assembled from the bound flow's skill metadata, with the triggering
tool action retained as secondary detail. No skill-format change.

Acceptance criteria:

- The card headline names the workflow using the bound skill's declared
  metadata — `title`, `description`, target `origin`, and `risk_class` — so
  the operator approves e.g. "Reset User Password in Admin Portal" rather than
  a bare `web.click`.
- The triggering tool action (tool name + element display hint) is retained on
  the same card as secondary detail; the flow headline does not replace it.
- The headline is assembled from existing skill frontmatter already carried on
  `web.navigate`'s `data["flow"]`: the gateway surfaces `title`/`description`
  on that flow dict, and the kernel renders the card from the same
  session-scoped `FlowContext` that R-1 keys on — **maintained as running
  state** updated from each `web.navigate` result, not scraped from frame
  history at park time — so the card is authoritative and correct across turns
  and regardless of frame ordering. No new contract, policy action, audit event
  type, or shared schema.
- When no flow is bound (a per-action confirmation outside any flow, per R-1),
  the card falls back to today's tool-level rendering — no regression.
- Durable and replayed cards (approvals inbox, session detail) render the same
  headline as the live card.

## Non-Goals

- No change to tool-gateway step-budget exhaustion behavior (an over-budget
  unlocked write is denied by the gateway rather than re-parked; documented
  in ADR-0007).
- No new policy actions, audit event types, or shared-contract schemas
  (rides SPEC-020/037 envelopes and `tool_invoked` / `execution_requested` /
  `confirmation_decided`).
- No skill-format or authoring change for the R-6 headline: it is assembled
  from frontmatter that already exists (`title`, `description`, `web_target`,
  `risk_class`) and already rides `web.navigate`'s `data["flow"]`.
- No structured per-step plan rendering on the card (SPEC-049 R-4's literal
  "declared steps"): skills declare no machine-readable step list today (steps
  live in the tutorial prose), so rendering them needs a skill-format change
  touching the skills contract and ingestion path — a larger blast radius than
  this gate fix warrants. Deferred to a follow-up spec; R-6 names the skill,
  title, description, target origin, and risk class.
- No durable or cross-process flow-approval or flow-context store (both are
  per-process, session-scoped — the authority TTL-bounded; a restart drops
  them, re-parks the next write, and re-renders the card tool-level, all of
  which fail safe).
- No re-opening of SPEC-049 (delivered/frozen); this spec completes its R-4
  by reference.
- No retroactive re-validation of other delivered specs against ADR-0008 (a
  follow-up sweep is advisable but out of scope).

## Impact

- products touched: `products/agent-platform` (kernel middleware, runtime
  kernel, execution signing, runtime settings, new flow-approvals service and
  a session-scoped flow-context store — the latter the single source for both
  R-1 flow identity and the R-6 card; plus R-6 — a `PendingConfirmation`
  flow-summary field and the confirmation-frame `flow_summary`); `products/tool-gateway` (**R-6 code
  change** — `FlowState` gains `title`/`description`, populated at `bind_flow`
  from the fetched skill and exposed in `to_dict()` so they ride the existing
  `web.navigate` `data["flow"]`; the R-1/R-3 deviation guard and session-id
  forwarding are unchanged — verify only); `products/operator-portal` (**R-6
  code change** — decode `flow_summary` and render the flow headline on the
  confirmation card, keeping the tool action as secondary detail);
  `products/execution-runtime` (no code change — worker verification already
  accepts kernel-signed envelopes; verify only).
- samples / shared touched: `samples/web-checks/password-reset` (skill,
  README, WALKTHROUGH, demo.sh),
  `shared/platform-ops/gitops/runtime-profiles/browser-dev/browser-check-target-pages.yaml`.
- contracts touched: none.
- identity / policy / audit / execution safety impact: execution safety —
  introduces a kernel-signed execution envelope under a session-scoped flow
  authority (ADR-0007); no identity or policy model change; audit rides
  existing execution events.
- living state docs to update on delivery: root `CHANGELOG.md`, `VERSION`
  (+ lockstep constants), `docs/agentic-aiops-platform/release-notes/` (new
  note + index), `docs/guides/configuration-reference.md` (new TTL knob),
  `docs/specs/README.md` (SPEC-051 row → `delivered`), `docs/adr/README.md`
  (ADR-0007/0008 → `accepted`),
  `docs/agentic-aiops-platform/delivery-roadmap.md` (SPEC-051 row →
  `delivered`).

## Open Questions

- none

## Changelog

- 2026-09-04: created as `draft`.
- 2026-09-04: added R-6 (flow-semantic confirmation card) at the
  operator-approved "flow headline + tool detail" scope; corrected Impact —
  `products/tool-gateway` and `products/operator-portal` now carry R-6 code
  changes (reversing the earlier "tool-gateway verify only" note).
- 2026-09-04: adopted the durable flow-context path on operator review —
  R-1/R-2 authority scoped to flow identity (`skill_id` + `origin`) via a
  session-scoped kernel `FlowContext` maintained from `web.navigate` results
  (eliminates the ADR-0007 cross-flow-rebind trade-off rather than bounding
  it); R-6 renders from that maintained state instead of a park-time frame
  walk; structured "declared steps" rendering deferred to a follow-up spec (no
  skill-format change here).
- 2026-09-04: approved by the operator (durable flow-context path); status
  `draft → approved`; ADR-0007/ADR-0008 `proposed → accepted`; Phase 2
  implementation begins against the approved artifacts.
- 2026-09-04: delivered in v0.33.0. R-1/R-2/R-3 implemented kernel-side
  (`services/flow_approvals.py` session-scoped `FlowContext`/`FlowApproval`
  stores, `build_flow_request` signed-envelope builder, the
  `browser_flow_approval_ttl` knob, the middleware flow-unlock branch +
  `flow_signer`, and `_sign_flow_execution`'s identity guard); R-6 shipped
  across the gateway (`FlowState.title`/`description` on `web.navigate`'s
  `data["flow"]`), the kernel confirmation frame (`flow_summary`, durably
  persisted on `confirmation_records`), and the portal card (flow headline
  above the tool detail); R-4 reconciled the password-reset sample to a
  single gate on "Confirm reset". Verified: `make verify` green at 0.33.0;
  live `dev-k8s` redeploy + `RUN_CHAT_LEG=true demo.sh` proved one card with
  every write-tier execution auto-signed under it (a live-Postgres smoke
  confirmed `flow_summary` persists as real JSONB); the live portal re-check
  showed a single approval gate headlined "Reset User Password in Admin
  Portal". Status `approved → delivered`.
