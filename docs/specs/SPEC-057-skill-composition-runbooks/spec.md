# SPEC-057: Skill Composition — Validated Runbooks of Single-Target Skills

## Status

- status: `approved`
- owner: luban-platform-team
- created: 2026-09-16
- approved: 2026-09-16
- release slice: R5 — Hardening and External Consumption (nineteenth R5 slice,
  targeting v0.40.0 — moved off v0.38.0 at the 2026-09-17 SPEC-058 approval,
  because a composition needs single-target skills to compose; SPEC-058 and
  SPEC-059 delivered that repertoire together in v0.38.0)
- related ADRs: **ADR-0011** (a composition carries no authority; each
  sub-skill keeps its own gate — this spec is its Phase 1 realization),
  **ADR-0007** (one HITL gate per mutating browser flow — extended, never
  reversed; stays `accepted` and unedited), ADR-0009 (graduate sessions into
  replayable executable skills — the sub-skills a composition references),
  ADR-0010 (signed execution envelopes declare authority provenance —
  unchanged; every sub-skill execution still carries its own provenance),
  ADR-0008 (spec delivery traceability gate).
  lineage: extends SPEC-055 (develop-as-you-go graduation — the single-target
  `executable_flow` sub-skills, and R-4 blast-radius re-validation, which is
  single-target by construction and therefore cannot apply to a composite),
  SPEC-056 (Studio — the authoring surface, whose deferred item (b) this spec
  is), SPEC-051 (browser flow HITL gate — the `FlowContext` identity guard
  that supplies per-sub-skill gate boundaries for free), SPEC-054
  (action-level approval — R-2 governs the infra and unbound per-action legs),
  SPEC-049/050 (browser tools and their tiers), SPEC-014 (skills and grounded
  guidance — the ingestion and grounding path a composition rides).
- drafting: from the 2026-09-16 composition-trust-model spike
  (`docs/workspace/composition-trust-model-spike.md`) and ADR-0011 (accepted
  2026-09-16), which together satisfy roadmap row 346's promotion gate. Scoped
  to row 346's **(b)** only — **(a)** the Chat→Studio *spawn* bridge and
  **(c)** assisted trace-extraction stay deferred to a later Phase 2 spec,
  because both are authoring ergonomics that change no gate semantics.

## Summary

Skills are single-target: SPEC-055 R-4 re-validates every step's observed
origin against the one target declared *before* mutating, so a multi-target
operation trace cannot graduate and SPEC-056 confirmed skills stay
single-target. Real incident remediation is nevertheless multi-target — query
A, health-check B, restart C — so operators need a way to express a
*workflow* without widening a skill's authorization scope.

This spec adds a third skill class, `composition`: an ordered, validated list
of single-target sub-skill references. It carries **no authority of its own**.
Each sub-skill keeps its own gate, which needs no new enforcement machinery —
`FlowContext.identity()` is `(skill_id, origin)`, `FLOW_CONTEXTS` holds one
context per session, and ADR-0007 already re-parks when a session rebinds to a
different flow. A composite navigating into its next sub-skill therefore
re-parks on the existing identity guard.

A composition is **not an interpreter and not a transaction**. There is no
control flow, no platform-side sequencing, and no rollback: the ordered list
reaches the model as grounded guidance, the platform enforces nothing about
the order, and a partial failure stops and reports rather than compensating.

## Motivation

- Operators troubleshooting an incident that spans services must today either
  run each single-target skill separately with no recorded relationship
  between them, or write prose runbooks the platform cannot validate. Neither
  gives a reviewer any assurance that the named steps exist, are published, or
  are scoped to one target each.
- The alternative to composition — letting a skill declare several targets —
  is closed by construction. SPEC-055 R-4 compares one declared target against
  every observed origin, so a multi-target skill cannot be graduated, cannot
  be re-validated, and cannot be replayed under a meaningful blast radius.
  Composition is the only route to multi-target workflows that preserves that
  invariant.
- Roadmap row 346 blocked on the gate question, and the spike found the answer
  already enforced: per-sub-skill gating is what shipped code does. What is
  missing is the *authoring and validation* construct, not trust-model work.
  That makes this a small, additive spec rather than a substrate change.
- Row 347's original premise — generalize browser flow binding to infra so
  infra legs collapse to one gate — was rejected by ADR-0011, because infra
  arguments are self-describing and binding would replace N assessable cards
  with one carrying less. This spec therefore does **not** touch infra flow
  authority: infra legs keep parking per-action under SPEC-054 R-2, which
  fails safe and is already asserted by SPEC-055 R-5's tests.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable
acceptance criteria.

### R-1: A `composition` skill class, additive on the existing contract

The skill contract gains a third `kind` value and one new optional property,
following the established additive convention.

Acceptance criteria:

- `skill.schema.json`'s `kind` enum extends from
  `["knowledge", "executable_flow"]` to include `"composition"`. The key stays
  optional and absent still means `knowledge`, so every existing skill
  validates unchanged.
- One new optional top-level `sub_skills` array property is added. Because the
  schema sets `additionalProperties: False`, this is a schema edit, not a
  passthrough, and it lands in **lockstep** across every mirror: the
  `shared/shared-contracts` schema, skills-hub `schemas/skill.py`, the
  ingestion path in `services/ingestion.py`, and the portal skill types. A
  contract drift guard asserts the property on every mirror.
- Each `sub_skills` item carries a required `skill_id` and an optional `note`
  (≤ 200 characters). `note` is **display-only and never a security input** —
  the same standing `flow_intent` (SPEC-053) and `steps[].expect` (SPEC-055)
  have. Order in the array is the runbook's declared sequence.
- A composition's own `risk_class` is **derived for display only**: `write`
  when any referenced sub-skill declares `risk_class: write`, otherwise
  `read`. It is never read by the deviation guard, the identity guard, or the
  policy engine, and it grants nothing.
- Skill Format version bumps v2 → v3 additively; a v2 consumer that ignores
  `kind` and `sub_skills` still ingests the skill's `body` as grounded
  guidance.

### R-2: Ingestion validation fails closed

A composition is validated when it is ingested, before it can be published or
referenced. Validation failure rejects the skill; it never degrades it to a
knowledge skill silently.

Acceptance criteria:

- Every `sub_skills[].skill_id` **resolves** to an ingested skill that is
  **published**, and that skill is **single-target**: it declares exactly one
  `web_target` (browser) or none (infra), never several.
- Ingestion re-checks **only those two structural facts** — still published,
  still single-target (resolved from OQ-2). It does **not** re-run SPEC-055 R-4
  blast-radius validation: R-4 validated each sub-skill when it graduated, and
  re-litigating that against a stored trace at composition-ingestion time would
  re-open a decision already made. The published-and-single-target re-check is
  what catches the drift that actually matters — a sub-skill later republished
  against a different target.
- **No nesting in Phase 1**: a referenced sub-skill must be `knowledge` or
  `executable_flow`, never `composition`. This removes cycles and unbounded
  depth by construction rather than by detection.
- **No duplicates**: a `skill_id` appears at most once in `sub_skills`.
- A composition declares **no `web_target` of its own** — its scope is the union
  of its sub-skills' scopes, and declaring one would falsely imply a single
  authorization target that SPEC-055 R-4 could not re-validate.
- A composition declares **no `steps` of its own** — there is no interpreter to
  consume them (R-6), and a `steps` list on a composition would imply platform
  sequencing that this spec explicitly does not provide.
- The sub-skill count is bounded by a new `SKILLS_COMPOSITION_MAX_SUB_SKILLS`
  knob (default **8**, resolved from OQ-4). Exceeding it rejects ingestion. This
  is the composite-wide bound R-4's trade-off requires, and its arithmetic is
  `cap × GATEWAY_BROWSER_FLOW_MAX_STEPS` — 8 × 20 = **160** worst-case unlocked
  browser writes per run, each still individually signed, audited and receipted,
  and each sub-skill still gated once. The value is revisited on the first real
  composition an operator authors, since the right number is a property of real
  runbooks rather than of this draft.
- Ingestion emits no new audit event type: the existing `skill_ingested` event
  carries the outcome, and a rejection is a failed ingestion like any other.

### R-3: No control flow

A composition expresses sequence and nothing else.

Acceptance criteria:

- The contract provides **no** branch, loop, conditional, retry, or early-exit
  construct, and no such field is accepted on `sub_skills` items. There is no
  vocabulary in which to write control flow, so none can be smuggled in via a
  `note`.
- The rationale is recorded in the schema description: an interpreter would
  need loops, and a loop defeats `GATEWAY_BROWSER_FLOW_MAX_STEPS`, which is
  currently the only bound on an unlocked browser flow.
- A validation test asserts that a composition carrying any unrecognized
  sequencing key is rejected, since `additionalProperties: False` already
  forbids it at the schema level and the test pins that this stays true.

### R-4: A composition carries no authority; each sub-skill keeps its own gate

This is ADR-0011's decision, realized. It requires **no new enforcement
machinery** and adds no kernel trust state.

Acceptance criteria:

- Nothing in agent-platform or tool-gateway reads `sub_skills` to grant,
  widen, or pre-approve anything. A grep-level purity test asserts
  `sub_skills` never reaches `FlowContext`, `FLOW_APPROVALS`, the deviation
  guard, or the policy engine.
- Browser legs gate exactly as they do today: binding sub-skill B via
  `web.navigate(skill_id=…)` overwrites the session's single `FlowContext`, the
  identity `(skill_id, origin)` no longer matches the recorded `FLOW_APPROVALS`
  entry, and the next write-tier call **re-parks**. A test asserts one card per
  distinct sub-skill binding across a two-sub-skill run.
- Infra legs park **per-action** under SPEC-054 R-2, unchanged. A mixed
  browser+infra composition is permitted and its gate count is the sum of its
  browser bindings and its infra writes.
- Gate count equals the number of distinct assessable decisions the run
  encounters — never one per composite. A test asserts that a composition
  produces **more** cards than any single sub-skill run alone, and that no card
  claims authority over a sub-skill it does not name.
- Every execution under every sub-skill's authority is still individually
  signed, persisted, audited, and receipted, with ADR-0010 provenance
  unchanged.

### R-5: Not a transaction — report-and-stop, re-entry from a named step

Acceptance criteria:

- There is **no rollback and no compensation**. A composition that stops
  part-way leaves the targets it already touched in the state it left them, and
  nothing claims otherwise on any surface.
- On a sub-skill failure the agent **reports which sub-skill failed and stops**
  rather than continuing to the next one. Continuing past a failure would
  execute a runbook whose premise no longer holds.
- **Re-entry starts from a named step.** The completed prefix is derived from
  the existing `execution_records` signed receipts for the session — no new
  composite state store, and no persisted runbook-progress record.
- Because receipts are swept at 30 days, re-entry is only derivable inside that
  window; outside it the operator restarts from the beginning. This is stated
  in the operator documentation rather than papered over.

### R-6: Delivery to the agent is grounded guidance, never platform sequencing

Acceptance criteria:

- A composition reaches the model through the existing SPEC-014 grounded
  guidance path: its `body` plus a rendered view of `sub_skills` in declared
  order, each with its `note` and its sub-skill's own title and declared
  target.
- The platform **never** pre-binds a sub-skill, never issues `web.navigate` on
  the model's behalf, and never enforces the declared order. Order is guidance
  with the same standing as `steps[].expect`.
- The rendered guidance names each sub-skill's declared target, so an operator
  reading a transcript can see which target each segment was scoped to.

### R-7: Authorization posture and the Studio authoring surface

Acceptance criteria:

- **No new policy action and no new audit event type.** A composition is a
  skill: it is read under the existing `skills:read` and authored in Studio
  under the existing `session:skill_graduate` posture SPEC-056 established. A
  `make policy-diff` run reports **zero** outcome transitions across all
  (role, action) pairs.
- Studio is the authoring home, consistent with SPEC-056's Design B: a
  composition is a development artifact, so it is created in a `development`
  session and never in Chat.
- The portal Skills viewer renders `sub_skills` as an ordered list with each
  sub-skill's title, declared target and `note`, reusing the SPEC-052
  rendered/raw pattern; the raw view shows the frontmatter verbatim.
- Read-only observers and auditors see compositions under their existing
  read posture and gain no authoring power.

### R-8: Delivery traceability per ADR-0008

Acceptance criteria:

- Every R-1..R-7 criterion above maps to at least one automated test asserting
  it, recorded in `tasks.md` at delivery.
- A `samples/` demo **is required** (resolved from OQ-5, under ADR-0008 rule 2:
  a demo is owed when it exercises something otherwise unexercised). It composes
  the **existing** single-target web-check skills — password-reset and one
  other — and asserts multi-binding re-park end to end, which nothing in the
  suite covers today. It also gives R-4's gate-count assertion a live leg rather
  than a unit test alone.

## Non-Goals

- **No interpreter.** Nothing steps through `sub_skills`; the model drives, the
  platform gates.
- **No control flow.** No branch, loop, conditional, retry or early exit (R-3).
- **No composite-level gate.** Rejected by ADR-0011: it would need the
  multi-identity authority store ADR-0007 removed.
- **No rollback, compensation, or saga semantics** (R-5).
- **No nested compositions** in Phase 1 (R-2).
- **No aggregate half-state surface** (resolved from OQ-3). The completed prefix
  of a stopped run is derivable from `execution_records` signed receipts, but
  nothing aggregates it per composition and no new view is added; R-5's
  report-and-stop message names the failed sub-skill in the transcript instead.
  A dedicated surface is promoted only if operators ask for one.
- **No Chat→Studio spawn bridge and no assisted trace-extraction** — row 346's
  (a) and (c), deferred to Phase 2 behind this spec.
- **No multi-target graduation.** SPEC-055 R-4 stays single-target; a
  composition is authored, not graduated from a multi-origin trace.
- **No infra flow binding.** Row 347 is reframed to tool granularity; this spec
  does not generalize `FlowContext` beyond the browser.
- **No change to ADR-0007 or ADR-0010 semantics**, no new executor, and no
  change to the signed-envelope shape.

## Impact

- **shared-contracts**: `skill.schema.json` — additive `kind` enum value plus
  one new optional `sub_skills` property; Skill Format v2 → v3.
- **skills-hub**: `schemas/skill.py` mirror, `services/ingestion.py`
  validation (R-2), one new `SKILLS_COMPOSITION_MAX_SUB_SKILLS` knob.
- **agent-platform**: grounded-guidance rendering of `sub_skills` (R-6). **No
  kernel trust-state change** — `flow_approvals.py`, the confirmation registry
  and the signing paths are untouched, and R-4 asserts they stay that way.
- **operator-portal**: Studio authoring surface and Skills viewer rendering
  (R-7).
- **platform-gateway**: unchanged; existing skill proxies carry the additive
  field.
- **tool-gateway**: unchanged; the deviation guard never learns about
  compositions.
- **audit-service**: unchanged; no new event type.

## Open Questions

All five were resolved at approval on 2026-09-16, adopting the recommendation
recorded in the draft in every case. The original options are retained so the
decision stays auditable; from here a requirement changes only by agreement,
recorded in the changelog (the `approved`-spec rule).

- **OQ-1: storage shape.** A third `kind` on the existing skill record (as
  drafted) versus a separate document kind beside `shift_summary` and
  `incident_report`. **Recommendation: the third `kind`.** Sub-skills are
  referenced by `skill_id`, so the composition belongs in the same namespace
  and rides the same ingestion, publication, and grounding paths; a document
  kind would duplicate all three and could not be referenced as a skill.
- **OQ-2: re-validation depth at ingestion.** Re-run SPEC-055 R-4 blast-radius
  validation against each referenced sub-skill, or trust its published state?
  **Recommendation: trust published state, but re-check the two structural
  facts** — that each sub-skill is still published and still single-target.
  R-4 validated each sub-skill when it graduated, and re-running it against a
  stored trace at composition-ingestion time would re-litigate a decision
  already made, while a *published-and-single-target* re-check catches the
  drift that actually matters (a sub-skill later republished with a different
  target).
- **OQ-3: half-state visibility.** When a run stops mid-way, what surface names
  the completed prefix? The receipts exist in `execution_records`, but nothing
  aggregates them per composition today. **Recommendation: defer the aggregate
  view** and let R-5's report-and-stop message name the failed sub-skill in the
  transcript, promoting a dedicated surface only if operators ask.
- **OQ-4: the sub-skill cap value.** The cap is the only composite-wide bound,
  and its arithmetic is `cap × GATEWAY_BROWSER_FLOW_MAX_STEPS` (default **20**,
  `tool-gateway/core/config.py:21`) worst-case unlocked browser writes per run —
  so the drafted default of 8 admits 160, each still individually signed,
  audited and receipted, and each sub-skill still gated once. **Recommendation:
  ship 8** and revisit on the first real composition an operator authors, since
  the right number is a property of real runbooks rather than of this draft.
- **OQ-5: is a `samples/` demo required?** Under ADR-0008 rule 2 a demo is owed
  only if it exercises something otherwise unexercised. A two-sub-skill
  composition would be the first end-to-end multi-binding re-park assertion in
  the suite, which argues for shipping it. **Recommendation: ship it**, and
  note that it also gives R-4's gate-count assertion a live leg rather than a
  unit test alone.

## Changelog

- 2026-09-16: drafted from the composition-trust-model spike memo and ADR-0011
  (accepted the same day), scoped to roadmap row 346's (b) — the composition
  construct, its ingestion validation, and per-step re-entry. Row 346's (a)
  spawn bridge and (c) assisted trace-extraction stay deferred to Phase 2.
  Eight requirements; the trust-model work is deliberately absent because
  ADR-0011 found it already enforced by the shipped `FlowContext` identity
  guard, so R-4 asserts that nothing new is added rather than specifying new
  machinery. Carries five open questions with recommendations, including the
  composite-wide sub-skill cap that closes the spike memo's OQ-1 trade-off.
- 2026-09-16: **approved** by the operator. Slice fixed as the nineteenth R5
  slice, targeting v0.38.0. OQ-1..OQ-5 resolved on the draft's own recorded
  recommendations in every case: OQ-1 a third skill `kind` rather than a
  separate document kind, OQ-2 trust published state but re-check
  published-and-single-target only, OQ-3 defer the aggregate half-state view,
  OQ-4 ship the sub-skill cap at 8 (8 × 20 = 160 worst-case unlocked browser
  writes per run), OQ-5 the `samples/` demo is required. The resolutions are
  folded into R-2, R-8, Non-Goals and the Open Questions preamble; no
  requirement IDs renumbered (stable once `approved`). Bookkeeping:
  `docs/specs/README.md` row `draft` → `approved` and the
  `delivery-roadmap.md` row 346 entry → `approved`. Implementation
  (`plan.md`/`tasks.md`) is authored next, not at approval.
- 2026-09-17: release slice retargeted v0.38.0 → **v0.40.0** by agreement, with
  no requirement changed. SPEC-058 (`http.get`/`http.post`) and SPEC-059 (the
  `acme-admin` sample app and its four single-target skills) were approved the
  same day and take v0.38.0 and v0.39.0: R-8's `samples/` demonstration needs a
  repertoire of *published single-target skills* to compose, and until SPEC-059
  the only candidates are three copies of the same password-reset mutation
  wearing different approval clothes. Sequencing this slice last is what makes
  its demo real rather than synthetic.
- 2026-09-17: SPEC-059 shipped alongside SPEC-058 in **v0.38.0**, collapsing
  its planned v0.39.0 slot. The earlier entry records the approval-time plan;
  this spec remains approved and targeted at v0.40.0.
