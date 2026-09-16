# Spike: Composition Trust Model — Does a Composite Need Its Own Gate? (SPEC-057 candidate)

Status: spike complete — findings below; ADR-0011 **accepted** 2026-09-16 recording the decision, and SPEC-057 Phase 1 **approved** 2026-09-16 with OQ-1..OQ-5 resolved
Date: 2026-09-16
Roadmap home: Exploration Backlog row "Multi-target skill development — Studio spawn bridge + composition" (`delivery-roadmap.md` row 346), whose named spike question this answers; row 347 ("Generalized non-browser (infra) executable-flow binding") is reframed by §6
Verified against: agent-platform and tool-gateway at 0.37.1 (`30b84ff`), SPEC-051/054/055/056 as delivered; live browser checks on `dev-luban-aiops` at `0.37.1-dev-k8s-b430795`

## 1. Question

Skills are confirmed **single-target**: SPEC-055 R-4 re-validates every step's
observed origin against the one target declared *before* mutating, so a
multi-target operation trace cannot graduate (SPEC-056 `spec.md:403-404`).
Multi-target *workflows* therefore need a composition construct that sequences
single-target skills. Roadmap row 346 names the blocking question:

> how do one-gate binding (SPEC-051), the deviation guard, and blast-radius
> re-validation behave when a runbook sequences sub-skills with *different*
> declared targets — does a composite need its own gate, or does each sub-skill
> keep its own?

Two design questions ride with it, both settled by operator decision during this
spike: is the sub-skill set a **declarative list** or prose guidance, and may a
composition carry **control flow**?

## 2. Findings — verified current state

- **Per-sub-skill re-parking is already what shipped code does; it needs no new
  machinery.** `FlowContext.identity()` returns `(skill_id, origin)`
  (`flow_approvals.py:102-104`) and `FLOW_CONTEXTS` is keyed by `session_id` —
  one context per session (`runtime_kernel.py:1234,1613,1699,1746`). ADR-0007's
  Decision states the consequence directly: subsequent writes are admitted
  "only while the session remains bound to that same flow — a rebind to a
  different flow re-parks". `flow_approvals.py:16-21` goes further and names
  this the mechanism that **eliminates** the ADR-0007 cross-flow trade-off
  rather than merely bounding it. A composite that navigates into sub-skill B
  therefore overwrites the context, fails the identity match, and re-parks the
  next write — with zero composition-aware code.
- **A composite-level gate would require a multi-identity store and would
  weaken the guard.** Holding N sub-skill authorities live at once is exactly
  the cross-flow posture ADR-0007 closed. Any composite gate is a regression
  against a decision already accepted, not a neutral alternative.
- **The step budget is per bound flow, so a composite has no total bound.**
  `GATEWAY_BROWSER_FLOW_MAX_STEPS` is enforced by the gateway per binding and
  mirrored as `FlowContext.steps_used`/`max_steps`. N sub-skills bring N
  budgets. This is the one place where "each sub-skill keeps its own gate"
  leaves a real hole (§5 OQ-1).
- **There is no interpreter to sequence anything.** `FlowState` declares no
  `kind` and no `steps` (SPEC-055, roadmap row 344); `steps[].expect` is a
  display/replay aid and never a security input; the deviation guard reads the
  origin allowlist, declared `risk_class` and step budget only — never element
  semantics. A runbook is therefore guidance to the model plus the existing
  per-bind gates, not an execution plan the platform steps through.
- **Blast-radius re-validation cannot apply to a composite as a unit.** R-4
  compares one recorded declared target against every step's observed origin. A
  runbook spanning targets has no single declared target to compare to, so each
  sub-skill validates itself at its own graduation. This is the structural
  reason skills stay single-target, and it is not fixable by widening R-4.
- **Infra legs already park per-action and fail safe.** SPEC-054 R-2 governs
  unbound writes; SPEC-055 R-5's tests assert the infra fallback. A mixed
  browser+infra composite needs no new gate semantics for its infra legs.
- **The write tier's justification is card informativeness, not commit
  semantics.** A tier review on 2026-09-16 confirmed all six
  `BROWSER_WRITE_TOOLS` (`flow_approvals.py:47-54`) stay write tier.
  `web.type`, `web.select` and `web.upload_file` submit nothing, yet
  downgrading them would be a regression: inside a bound flow only the *first*
  write parks, so the single card would move off the value-setting call (which
  the curated formatter renders as `Select "admin" in "Role"`) and onto
  `Click "Submit button"` — approving a submission without ever showing what
  was submitted. `BROWSER_WRITE_TOOLS` membership is also what routes a call to
  the park/auto-sign branch at all. Shipped as `30b84ff`: all five blanket
  descriptions previously claimed "this mutates the target application", which
  was false for three of them, and each now states its real rationale.
- **The card content that argument depends on is live-verified for four of six
  write tools.** `web.click` (password-reset chat leg: one gate, signed
  receipt), `web.type` (two runs: `Type into "<input type=text> "username""`),
  and `web.press_key` (two runs covering both `display_hint` branches:
  `Press key "Tab" in "ref 1"` when no snapshot precedes it in the turn, and
  the labelled form when one does). `web.select` and `web.upload_file` are
  **not drivable**: the `browser-dev` profile allowlists exactly one origin
  (`browser-check-target:8080`, `browser.env`) and its six pages contain no
  `<select>` and no `<input type=file>`. Two of six write-tier tools have
  therefore never been demonstrable by the shipped demos — a pre-existing
  sample-infrastructure hole, not a gap introduced here. This supersedes
  `30b84ff`'s statement that no `web.type`, `web.select`, `web.upload_file` or
  `web.press_key` execution reached the gateway.
- **Tool granularity, not binding, is the infra gap.** Card count should track
  assessable decisions, not tool risk labels. Three `k8s.delete_pod` cards for
  three pods is correct behaviour — each card's arguments *are* the action.
  Browser refs are opaque pointers needing `display_hint` resolution; infra
  arguments are self-describing. Generalizing browser flow binding to infra
  would **destroy** information, replacing N self-describing cards with one
  flow-level card carrying less.

## 3. Options weighed

- **Option A — the composite carries its own gate** (one approval covering the
  whole runbook). Rejected: requires a multi-identity authority store, re-opens
  the ADR-0007 cross-flow trade-off, cannot present N sub-skills' worth of
  assessable content on one card, and has no blast-radius story (§2).
- **Option B — each sub-skill keeps its own gate; the composite is a validated,
  ordered sub-skill list with no interpreter.** **Recommended.** No new
  enforcement machinery, because the identity guard already supplies the gate
  boundaries (§2, first finding). The composite adds authoring structure and
  validation, not authority.
- **Option C — prose-only runbook**, no structured list. Rejected by operator
  decision: nothing to validate at ingestion, no way to check a named sub-skill
  exists, is published, and is single-target, and no basis for re-entry from a
  named step.

## 4. Recommended shape (SPEC-057 candidate, Phase 1)

### 4.1 A composition is a declarative, ordered list of sub-skill references

Validated at ingestion: every reference resolves to a published skill, that
skill is single-target and declares its target, and no sub-skill appears twice.
**No control flow** — no branch, no loop, no conditional, no early exit.
Sequencing and validation only. Two reasons: an interpreter would need loops,
and a loop defeats the step budget that is currently the only bound on an
unlocked flow; and there is no interpreter today (§2), so adding one is a
substrate change rather than a feature.

### 4.2 A composite carries no authority of its own

Gate count equals the number of assessable decisions, which equals the number
of distinct sub-skill bindings the run actually encounters. Browser legs get
one gate per sub-skill through the existing identity guard; infra legs stay
per-action under SPEC-054 R-2. Mixed browser+infra composites are **allowed** —
neither leg depends on the other's gate semantics.

### 4.3 A composite is not a transaction

Sub-skill steps are usually idempotent but are not guaranteed to be. On partial
failure the agent reports where it stopped and does not continue; the operator
may re-enter. **Re-entry starts from a named step**, and the completed prefix
is derived from the existing `execution_records` signed receipts rather than
from new composite state — no rollback, and no claim of one.

### 4.4 Phase boundary

Phase 1 is the composition construct, its ingestion validation, and per-step
re-entry. Phase 2 is the **"Continue in Studio" spawn bridge**, deferred
together with **assisted trace-extraction** (which is the spawn bridge's
payload). Rationale: (b) is the trust-model question row 346 actually asks and
is answerable now; (a) and (c) are authoring ergonomics that change no gate
semantics and would widen Phase 1 without reducing its risk.

## 5. Open questions for the spec

- **OQ-1 (blocking ADR-0011's boundary, not its decision): composite-wide step
  budget.** Each bind brings a fresh `GATEWAY_BROWSER_FLOW_MAX_STEPS`, so a
  long runbook has no total write bound. Either add a composite-level counter
  in the kernel, or bound the total at ingestion by capping sub-skill count.
  The second is cheaper and consistent with §4.1's no-interpreter stance.
- **OQ-2: storage shape.** A further additive field on the v2 skill class, or a
  separate document kind? And does ingesting a composite re-run SPEC-055 R-4
  validation against each referenced sub-skill, or trust their published state?
- **OQ-3: half-state visibility.** When a run stops mid-way, what names the
  completed prefix for the operator? The receipts exist in `execution_records`;
  nothing aggregates them per runbook today.
- **OQ-4: `web.select` / `web.upload_file` demonstration.** Extend
  `browser-check-target-pages.yaml` with a `<select>` and an `<input
  type=file>`, redeploy the `browser-dev` overlay and re-run both demos'
  deterministic legs — or record the hole as an accepted sample-suite
  limitation. Operator decision on 2026-09-16: **accept for now**; the residual
  risk is small because both received the identical rationale rewrite as
  `web.type`, which is live-verified twice.
- **OQ-5: the volume case.** A runbook long enough that N gates *is* the
  usability problem row 347 describes for infra. Does the answer differ between
  browser legs (where one card can legitimately cover a bound flow) and infra
  legs (where it cannot)? If it does not, the fix is tool granularity in both.

## 6. Promotion recommendation

1. Draft **ADR-0011** recording Option B — *a composite carries no authority;
   each sub-skill keeps its own gate* — with the identity-guard finding as its
   decisive evidence and OQ-1 as its recorded open boundary. Row 346 stays
   deferred until ADR-0011 is `accepted`.
2. Promote row 346's **(b)** to **SPEC-057** scoped to Phase 1 (§4). (a) and
   (c) stay deferred behind it.
3. **Rewrite row 347 rather than promote it as written.** Its premise —
   generalize the browser flow binding to infra — is the wrong fix (§2, final
   finding): it would replace N self-describing cards with one card carrying
   less information. Retitle it to infra **tool granularity**: the gap is that
   no `k8s.restart_deployment`-shaped tool matches the operator's decision
   unit, so one decision costs N cards. Keep its existing promotion trigger
   (the first infra executable flow an operator actually graduates and
   replays).
4. Record the sample-suite coverage hole (§2, `web.select` / `web.upload_file`)
   as a backlog row or fold it into OQ-4, so the two undemonstrable write tools
   are visible rather than implicit.

## Changelog

- 2026-09-16: **SPEC-057 approved** by the operator, closing out §6. All five of
  its open questions resolved on the draft's own recommendations, including this
  memo's OQ-1: the composite-wide write bound is a sub-skill **cap** at
  ingestion (`SKILLS_COMPOSITION_MAX_SUB_SKILLS`, default 8) rather than a kernel
  counter, so 8 × `GATEWAY_BROWSER_FLOW_MAX_STEPS` (20) = 160 worst-case unlocked
  browser writes per run, each still individually signed, audited and receipted
  and each sub-skill still gated once. §6's remaining steps are also now done —
  row 347 rewritten to tool granularity and the (c)/(d) browser tier residuals
  given their own backlog row. Implementation (`plan.md`/`tasks.md`) is authored
  next, per the `approved`-spec rule.
- 2026-09-16: **ADR-0011 accepted** by the operator the same day it was drafted,
  unblocking row 346's promotion gate. OQ-1 stays open for SPEC-057 as the
  ADR's recorded accepted trade-off.
- 2026-09-16: §6 step 1 taken — `docs/adr/0011-composition-carries-no-authority.md`
  drafted as `proposed`, recording Option B and leaving OQ-1 (the
  composite-wide step budget) to SPEC-057 as an accepted trade-off rather than
  deciding it here. Row 347's rewrite and SPEC-057's draft remain outstanding.
- 2026-09-16: spike complete. Answered row 346's question with **each
  sub-skill keeps its own gate**, on the evidence that the shipped identity
  guard already re-parks on rebind (ADR-0007, `flow_approvals.py:16-21`) and
  that a composite gate would need the multi-identity store ADR-0007 removed.
  Settled the two design questions (declarative list; no control flow). Reframed
  row 347 from flow-binding generalization to tool granularity. Carried in the
  2026-09-16 browser write-tier review (`2e8f888` press_key card element
  context, `30b84ff` write-tier rationale) and its live verification, including
  the two write tools the sample target cannot exercise.
