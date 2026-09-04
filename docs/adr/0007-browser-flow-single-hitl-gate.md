# ADR-0007: Enforce One HITL Gate Per Mutating Browser Flow Platform-Side

## Status

`accepted`

- date: 2026-09-04
- deciders: workspace maintainers
- related specs: SPEC-051 (browser flow HITL gate enforcement), SPEC-049
  (browser web-check tools, R-4/D-3), SPEC-037 (signed execution requests),
  SPEC-038 (isolated execution worker), SPEC-020 (HITL confirmation bridging),
  SPEC-021 (bounded mutating actions), SPEC-030 (require-approval semantics)

## Context

SPEC-049 R-4 declares that a `write`-class browser flow "park[s] one
confirmation card at first interaction through the existing SPEC-020
bridge" and that "[a]pproval unlocks the bound flow's interactions for
that session." Its acceptance criteria require that "[a] `write`-class
flow parks exactly one confirmation card; after approval, the declared
steps execute without further cards." D-3 records the rationale: risk is
declared per flow, not per tool, "with one operator decision per mutating
flow."

SPEC-049 was marked `delivered` (v0.31.0), but only the tool-gateway half
of R-4 was built — flow binding, the origin allowlist, `risk_class`, and
the step-budget deviation guard. The agent-platform kernel never collapsed
the per-write ASKs: `GatewayPermissionMiddleware.on_check_permission`
answers every non-allow-listed write tool with an independent ASK, with no
flow or session memory, and each mutating call requires its own SPEC-037
signed execution envelope built only from a parked→approved card.
tool-gateway does not park or resolve cards and does not gate on flow
approval — that is the kernel's boundary.

The observable "one gate" behavior therefore only ever existed as fragile
skill authoring: a skill that happened to declare exactly one write-tier
interaction parked exactly one card. A live password-reset test on the
deployed v0.32.0 parked an approval card for *every* write-tier browser
interaction, because the sample's flow contained more than one write and
nothing in the platform collapsed them. This is a trust-model question —
how many operator decisions gate a mutating browser flow, what authority
each unlocked execution carries, and what bounds a write after the single
approval — not merely a demo defect.

## Decision

Enforce exactly one HITL gate per mutating browser flow at the platform
level, realizing SPEC-049 R-4/D-3:

- The first write-tier browser interaction in a `write`-class flow parks
  one confirmation card through the existing SPEC-020 bridge. On approval
  the kernel records a flow authority scoped to the session **and the
  approved flow's identity** (`skill_id` + `origin`, drawn from a
  session-scoped `FlowContext` that reflects the gateway-owned flow
  binding). Every subsequent write-tier browser interaction is admitted
  without a further card **only while the session remains bound to that
  same flow** — a rebind to a different flow re-parks — and is **signed by
  the kernel under the approving card's authority** (its own `execution_id`
  and `args_digest`, reusing the card's `confirm_id`/`decider_user_id` and
  the platform signing key), so each unlocked write is still individually
  signed, persisted, audited, and receipted exactly like an approved-card
  execution.
- The tool-gateway **deviation guard remains the enforcement boundary**
  for every unlocked write: origin allowlist, declared `risk_class`, and
  the step budget (`GATEWAY_BROWSER_FLOW_MAX_STEPS`) still bound execution,
  and the session id is forwarded on the write path so the guard applies.
  An interaction outside a bound flow, or past the step budget, never
  executes silently.
- Browser write tools **never join any auto-allow list**. The unlock is
  runtime, operator-granted, session-scoped authority — not a static
  allow-list entry — so the R-4 auto-allow invariant and its regression
  test hold unchanged.
- The session authority is **time-bounded** by a TTL knob
  (`AGENT_BROWSER_FLOW_APPROVAL_TTL`); setting it to `0` disables
  flow-unlock and restores the pre-fix per-action gating.

## Alternatives Considered

- add the write-tier browser tools to the kernel's static auto-allow list
  — rejected: an auto-allowed mutating call has no signed execution
  envelope, so it fails closed at the SPEC-037/038 handoff
  (`REASON_REQUEST_MISSING` → `EXECUTION_REJECTED`); allow-listing either
  breaks the fail-closed signed-execution invariant or silently no-ops,
  and it violates R-4's explicit "browser interaction tools can never join
  any auto-allow list."
- keep per-action confirmation cards (the observed behavior) — rejected:
  violates R-4's one-gate acceptance criterion and D-3's "one operator
  decision per mutating flow," and burdens operators with repeated
  approvals for a single logical mutation.
- leave the one-gate behavior as skill-authoring discipline only (status
  quo) — rejected: unenforced and fragile; it depends on every future skill
  declaring exactly one write, and it already regressed in the live reset
  demo. The platform must enforce the invariant, not hope authors preserve
  it.
- collapse the gate inside tool-gateway (gate on `flow.approved`) —
  rejected: the gateway neither parks nor resolves confirmation cards (the
  kernel/SPEC-020 boundary) and has no authority to sign execution
  envelopes; collapsing there would split the trust decision across two
  services. The gateway stays the deviation-guard boundary; the kernel owns
  the approval→unlock decision.
- scope the flow authority to the session id only (an earlier draft of this
  record) — rejected on the durability review: it leaves a cross-flow
  auto-sign window (a rebind to a *different* `write`-class flow rides the
  earlier approval), bounded only by the gateway guard and the TTL. Scoping
  the authority to the approved flow's identity (`skill_id` + `origin`) via a
  kernel-maintained `FlowContext` eliminates that window at the source for
  modest extra per-process state; the operator chose this durable path over
  the lighter bounded one.

## Consequences

- realizes SPEC-049 R-4/D-3 as shipped platform behavior: one operator
  decision per mutating browser flow, with every unlocked write still
  signed, persisted, audited, receipted, and gateway-guarded; the
  auto-allow invariant and its test stay intact; non-browser mutating tools
  (`k8s.*`, etc.) are unaffected.
- the single gate is **flow-semantic** (SPEC-051 R-6): the card names the
  bound workflow — the skill's declared title, description, target origin, and
  risk class, surfaced from the gateway flow binding via `web.navigate`'s
  `data["flow"]` — with the triggering tool action kept as secondary detail.
  The operator approves "Reset User Password in Admin Portal," not a bare
  `web.click` on a "Sign in" button, realizing the second half of SPEC-049
  R-4 ("the card names the skill, target origin, and declared steps"). What an
  operator is asked to approve is part of the trust model, so it is recorded
  here rather than left to the spec alone.
- cross-flow rebind is **eliminated, not merely bounded** — because the
  authority is scoped to the approved flow's identity (`skill_id` + `origin`)
  via the kernel's session-scoped `FlowContext`, a session that rebinds to a
  *different* `write`-class flow no longer matches, so its next write re-parks
  rather than auto-signing. An earlier session-only design left this as an
  accepted trade-off (bounded only by the gateway origin + step-budget guard
  and the TTL); the durable flow-identity scope removes it at the source. The
  kernel still does not *own* the flow — the gateway remains the enforcement
  boundary and `FlowContext` is only a reflection of the binding the gateway
  already emits on `web.navigate` — so the two-service split holds.
- step-budget exhaustion: an unlocked write past budget is auto-signed then
  **denied** by the gateway (`BROWSER_FLOW_EXHAUSTED`) rather than re-parked
  — a minor deviation from R-4's "escalates to ASK" letter that fails
  closed. Changing gateway exhaustion behavior is out of scope.
- follow-up: this record becomes the checked-in decision that supersedes
  the auto-extracted planning-time note "Enforce a single write-tier HITL
  gate per mutating browser flow," which captured the intent but was never
  realized in platform code. Implementation is tracked by SPEC-051.
