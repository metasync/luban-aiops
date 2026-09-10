# SPEC-055: Develop-As-You-Go Skill Graduation

## Status

- status: `delivered`
- owner: luban-platform-team
- created: 2026-09-06
- approved: 2026-09-07
- delivered: 2026-09-09 (v0.36.0)
- release slice: R5 — Hardening and External Consumption (seventeenth R5
  slice, v0.36.0)
- implementation start: was gated on SPEC-054 reaching `delivered` (B before
  C). `plan.md`/`tasks.md` were authored at that point rather than at
  approval, because this spec's capture seam and replay binding are built on
  the `approval_kind` discriminator and per-action parking that SPEC-054
  ships.
- related ADRs: **ADR-0009** (graduate troubleshooting sessions into replayable
  executable skills via a durable authoring trace — **implemented by this
  delivery**, stays `accepted`),
  ADR-0007 (one HITL gate per mutating browser flow — **phased**, a graduated
  flow replays under one gate), ADR-0008 (spec delivery traceability gate);
  lineage: extends SPEC-044 (skill authoring export — knowledge-only draft),
  SPEC-045 (draft preview), SPEC-049/050/051 (browser web-check tools + flow
  gate enforcement), SPEC-037/038 (signed execution requests + isolated worker),
  SPEC-014 (skills and grounded guidance), and **depends on SPEC-054**
  (action-level HITL approval — the exploration/authoring phase that produces the
  mutations this spec graduates; **R-7 also hardens SPEC-054 R-3's
  change-request projection at the approval seam**)
- sequencing: the A→B→C program is complete. A (the SPEC-051 R-6 headline-leak
  patch) landed at v0.34.1; B (SPEC-054, the action-approval prerequisite)
  landed at v0.35.0; C (this spec + ADR-0009, the graduation destination) is
  this delivery at v0.36.0. A→B did not conflict with C.
- deferred follow-up: **OQ-2's generalized non-browser (infra `k8s.*`) flow
  binding** is not delivered here — an infra executable flow's steps park
  per-action under SPEC-054 R-2, which fails safe and is asserted as such by
  R-5's tests. It is anchored to its own follow-up train in
  `delivery-roadmap.md`.

## Summary

The operator's operating model is: (1) troubleshoot via chat with mutating
actions properly approved (SPEC-054); (2) turn a troubleshooting session into a
useful skill; (3) develop skills by running actions in chat rather than writing
them up — "develop-as-you-go." This spec delivers (2) and (3): a **graduation
pipeline** that turns a session of individually-approved, already-signed
mutations into a **replayable executable-flow skill** reviewed and merged by a
human, then replayed under **one** HITL gate with every write still signed,
audited, receipted, and gateway-guarded.

Three pieces, per ADR-0009:

- a durable, replay-oriented **authoring-trace store** (separate from the 30-day
  `execution_records` receipt sweep) capturing the ordered, **secret-safe
  parameterized** step sequence as a by-product of each approved mutation;
- an **executable-flow skill class** declaring `risk_class: write` **decoupled
  from `web_target`** (so any mutating skill — browser *or* infra — declares
  mutating-ness explicitly, the mechanism the operator asked for, mirroring a
  tool's risk attribute) and carrying a machine-readable replay step list;
- a **graduation + replay** path that re-validates the captured sequence's blast
  radius before promotion, produces a **draft for human merge** (never
  auto-publish), and replays the graduated flow under SPEC-051's one-gate
  authority with credentials resolved from **credential-set references**, never
  baked literals.

This is the largest trust-surface change in the program (skills-hub,
agent-platform, tool-gateway, execution-runtime), so it is its own spec under
ADR-0009 with per-requirement tests (ADR-0008), sequenced **after** SPEC-054.
It also folds in **R-7**, a source-side hardening of the SPEC-054 change-request
card's secret masking at the approval seam — the record and projection R-2's
secret-safe trace capture reads from — so the secret-safety guarantee holds
end-to-end, not only in the derived trace (added post-approval; see Changelog).

## Motivation

- The only skill-draft path today (SPEC-044 `skill_draft`) emits a *knowledge*
  Markdown whose `SkillFrontmatter` is `extra="forbid"` with only
  `title`/`description`/`tags`/`version` — it structurally cannot declare
  `web_target`/`risk_class`/`flow_intent`, and SPEC-044 ships "no execution-path
  change (no mutating tools, no HITL)." A drafted skill is always read-class
  guidance: it can inform an agent but can never *be* a runnable mutating flow.
  The operating model's steps (2)/(3) are therefore impossible today.
- Mutating-ness cannot be declared outside the browser: `risk_class: read|write`
  exists but ingestion rejects it without a `web_target`
  (`services/ingestion.py` — "risk_class requires a web_target declaration"), so
  a non-browser mutating skill (one that runs `k8s.*`) cannot declare that it
  mutates. The operator explicitly asked for "a mechanism to ensure this just
  like the tool design where we have a risk attribute to explicitly indicate
  instead of inferring."
- The capture substrate is a receipt sweep, not a replay trace: `execution_records`
  is ordered by `requested_at` and each row is individually signed with a
  receipt, but it stores an `args_digest` (a hash for signature verification),
  **not** replayable plaintext arguments, and it is swept at 30 days
  (`RETENTION_WINDOW_DAYS=30`). "Develop now, graduate later" outlives that
  window and needs the arguments, not their digest — hence the operator's choice
  of a **dedicated authoring trace** over retention-bounded reuse.
- Why now: SPEC-054 makes per-action mutations (including ad-hoc browser writes)
  possible and well-described; this spec is the destination that makes them
  *reusable*. Sequenced after B so the authoring phase exists to graduate from.
- Why R-7 rides along (added post-approval): the SPEC-054 delivery review
  surfaced that the change-request card masks only its **display** projection —
  raw secret-bearing `parameters` still persist in `pending_calls`, ride the
  stream frame, and render in the portal expander, and the generic projection
  fails **open**. R-2 already depends on a secret-safe approval seam (it
  parameterizes secrets at capture so a literal never reaches the trace store),
  so hardening the seam's own record and projection is the same concern, not a
  separate one — splitting it into its own spec would divide one approval-seam
  secret-safety surface (and the same redaction vocabulary) across two specs.

## Requirements

### R-1: Durable authoring-trace store

A dual-backend (`InMemory` + `Postgres`) store captures, per chat session, the
ordered sequence of approved mutating steps as a **replay-oriented trace**,
separate from the `execution_records` receipt sweep, with an authoring-scoped
lifecycle.

Acceptance criteria:

- An `AuthoringTraceStore` protocol with `InMemory` and `Postgres` backends and a
  `build_*_store` factory, mirroring `execution_records`/`confirmation_records`.
  Any schema field exists on **both** backends (the skills-hub
  `web_target`/`risk_class` lesson: a field on one backend only is silently
  dropped in production); verification targets `postgres` (the dev-k8s backend).
- A trace step records: the ordered position, the canonical tool name, the
  **secret-safe parameterized** arguments (credential values replaced by
  placeholders / credential-set references — never literals), and **references**
  to the originating `execution_id`/`confirm_id` (it does not duplicate the
  signed receipt or outcome, which stay in `execution_records`).
- The trace has an authoring-scoped lifecycle — `draft → graduated | discarded`
  — and a retention policy **independent of** the 30-day execution sweep (a
  session authored now is still graduable after the receipts are swept).
- The trace is keyed by `session_id` and bounded (a per-session step cap so an
  unbounded session cannot grow an unbounded trace).

### R-2: Authoring-trace capture at the approval seam

The trace is populated as a **by-product of an already-approved, already-signed
mutation** — no new trust surface and no capture of un-approved actions.

Acceptance criteria:

- Capture happens at the same resume/receipt seam that writes
  `execution_records`, so a step is recorded only for a mutating call that was
  approved (per-action, SPEC-054) or admitted under a flow authority (SPEC-051)
  **and** signed. Read-tier calls are never captured.
- Both approval kinds contribute: an ad-hoc per-action browser/infra write
  (SPEC-054 R-2) and a write inside a bound flow (SPEC-051) each append their
  step, so a mixed troubleshooting session yields one coherent ordered trace.
- Capture is best-effort and fail-safe: a trace-store failure degrades to
  "no graduation candidate" and never blocks the mutation's execution or its
  `execution_records`/receipt path.
- Secret values are parameterized **at capture time** (reusing the SPEC-049 R-5
  redaction vocabulary and the `web.fill_credential` / credential-set
  indirection), so a literal secret is never written to the trace store.

### R-3: Executable-flow skill class with `risk_class` decoupled from `web_target`

Skills gain an **executable-flow** class that declares mutating-ness explicitly
and carries a machine-readable replay step list, distinct from SPEC-014/044
grounded-guidance knowledge.

Acceptance criteria:

- `risk_class: read|write` is accepted **without** a `web_target` (the ingestion
  rule "risk_class requires a web_target declaration" is relaxed), so a
  non-browser mutating skill (e.g. `k8s.*`) can declare `risk_class: write`.
  Existing browser flows (`web_target` + `risk_class`) are unchanged.
- The skill contract (`skill.schema.json`, Skill v1) gains an **additive**
  executable-flow representation: a skill `kind` (or equivalent discriminator)
  and a machine-readable **replay step list** (ordered tool + parameterized-args
  steps with credential-set references). Knowledge/guidance skills omit it and
  validate exactly as today (Skill v1 → v2, additive; no existing skill breaks).
- skills-hub ingestion validates the executable-flow class (step-list shape,
  declared `risk_class: write` when any step mutates, credential references
  resolve to named credential sets) and rejects a malformed one, reusing the
  existing validation path SPEC-044 drafts against.
- A `read`-class skill still never executes mutating tools; only a `write`-class
  executable flow can replay mutations, and only under R-5's one gate.

### R-4: Graduation with blast-radius re-validation and human merge

An operator graduates a session's authoring trace into an executable-flow skill
**draft**; graduation re-validates safety and never auto-publishes.

Acceptance criteria:

- A graduation entry point on the session (analogous to SPEC-044's
  `POST /api/v2/sessions/{session_id}/skill-draft`) assembles the executable-flow
  skill draft **deterministically** from the authoring trace (no LLM synthesis
  of steps beyond what was actually approved and captured).
- Graduation **re-validates blast radius** before producing the draft: bounded
  step count, every target/origin allowlisted, a consistent declared
  `risk_class: write`, and all credentials resolved to credential-set references
  — the same guards SPEC-051 applies to a hand-authored flow. A trace that fails
  re-validation is not graduable (deterministic refusal, surfaced to the
  operator).
  - "target/origin" is two distinct things, and both are recorded rather than
    inferred (stage-6a refinement in `tasks.md`): the **declared target** is the
    web target the operator names when opening a develop-as-you-go session —
    declared *before* mutating, so it is an authorization scope rather than a
    claim fitted to the trace afterwards — and the **observed origin** is what the
    gateway reported each captured mutation actually landed on. Re-validation
    checks every observed origin against the declared target, so this criterion is
    substantiated by evidence. A step with no observed origin is *unverified*, not
    drifted, and refuses.
- Graduation produces a **draft for human review and merge** — previewed
  (rendered + raw) and downloaded/exported like the SPEC-045 draft preview, for
  contribution to the team's Git skills repo. The platform never auto-publishes
  an executable mutating skill (preserves SPEC-044's "the platform drafts, humans
  merge").
- Graduation is gated by a policy action and audited. Because it produces an
  executable *mutating* artifact (higher trust than SPEC-044's knowledge draft),
  it uses **one new policy action** (e.g. `session:skill_graduate`) and **one new
  audit event type** (e.g. `skill_graduated`), role-gated to operator/approver
  (not observer), following the SPEC-044/045 precedent. The graduated trace's
  lifecycle flips to `graduated`.
  - Declaring the target is the first half of that one capability, not a second
    one, so it rides the same `session:skill_graduate` action (the
    `documents:create` precedent). The exception is declaring at *birth* on
    session create, which rides `session:create` alone: it is inert — it grants
    nothing and only narrows what a later graduation may emit — and dual-gating
    it would refuse session creation itself over an inert field.

### R-5: Replay under one gate, secret-safe and gateway-guarded

A graduated, ingested executable flow replays under SPEC-051's one-gate
authority, with every write still signed and bounded.

Acceptance criteria:

- Replaying a `write`-class executable flow binds a flow authority and parks
  **one** confirmation card (the flow headline + change-request framing from
  SPEC-051 R-6 / SPEC-054 R-3); subsequent writes in the flow are admitted under
  that authority, each **individually signed** (SPEC-037 `build_flow_request`),
  persisted, audited, and receipted — identical to a hand-authored flow.
- The gateway deviation guard (origin allowlist, declared `risk_class`, step
  budget) bounds every replayed write; a replay past budget or off-allowlist
  fails closed. Executable-flow writes **never join any auto-allow list**.
- Credentials are resolved **at replay time** from the named credential sets the
  step references — a graduated skill is shareable and replayable precisely
  because it carries **no** literal secret.
- **Non-browser replay binding:** because today's flow binding
  (`FlowContext`/`web.navigate(skill_id=…)`) is browser-specific, replaying a
  non-browser executable flow (`k8s.*`) needs a flow-binding analog so its steps
  collapse to one gate. This spec delivers that binding for the infra case (see
  OQ-2); until it lands, only browser executable flows replay under one gate and
  an infra executable flow's steps park per-action (SPEC-054), which still fails
  safe.

### R-6: Delivery traceability per ADR-0008

This spec is delivered under the ADR-0008 gate.

Acceptance criteria:

- Every R-1..R-5 and R-7 acceptance criterion maps to at least one automated
  test recorded in `tasks.md` (authoring-trace store dual-backend round-trip
  incl. the `postgres` backend; capture-only-on-signed-mutation; secret
  parameterization at capture; `risk_class`-without-`web_target` ingestion;
  executable-flow schema validation; graduation blast-radius refusal + happy
  path + draft-not-published; one-gate replay with per-write signing +
  credential-set resolution; R-7 fail-closed projection masking +
  no-plaintext-secret on the stream/render surface + `args_digest` invariant
  preserved after masking).
- Any shipped `samples/` graduation demo is exercised by its own script in the
  verification path (ADR-0008 exercised-sample rule).
- `docs/specs/README.md` and `CONTRIBUTING.md` carry the ADR-0008 delivery-gate
  text (unchanged).

### R-7: Approval-seam secret-masking hardening (change-request record + projection)

*(Folded in post-approval — see Changelog 2026-09-07 — picking up the
change-request secret-masking gaps SPEC-054 recorded and deferred (re-confirmed
by its delivery review). It is the source-side
complement of R-1/R-2: those keep a literal secret out of the **derived**
authoring trace; R-7 keeps it out of the **approval-seam record and the
change-request projection** the trace is captured from, reusing the same
SPEC-049 R-5 redaction vocabulary and `web.fill_credential` / credential-set
indirection. Appended after R-6 because requirement IDs are stable once a spec
is `approved` — no renumbering.)*

SPEC-054 R-3 masks secrets in the change-request card's **display projection**
(`change_request`), but the raw `parameters` still persist in the confirmation
record's `pending_calls`, ride the `confirmation_request` stream frame, and
render in the portal "Technical details" expander unmasked; and the projection's
generic field-masking fails **open** (a secret value under an off-vocabulary key
projects as plaintext). **Both are gaps SPEC-054 recorded and deferred, not
regressions it introduced:** its Non-Goals carry "**No masking of the raw
parameters already persisted on the durable record**" (a "**pre-existing** gap…
fixing it means changing the parked-payload shape that the signed path, the
durable record, and the portal all read"), its OQ-5 resolved the same question
to "no, out of scope," and R-3's structured `{summary, fields[]}` projection was
built "so SPEC-055's secret-safe parameterized steps reuse it." R-7 is the
requirement that picks up that recorded deferral — closing both without
disturbing the signed-execution invariant, and inheriting exactly the
parked-payload-shape tension SPEC-054 named (worked in `plan.md`).

Acceptance criteria:

- **Fail-closed projection masking.** The change-request projection masks a
  parameter value conservatively when the redaction vocabulary does not
  positively classify it as non-secret — closing the `_generic_fields` fail-open
  path so a generically-named secret (an off-vocabulary key) is masked, not
  projected as plaintext. *(Delivery-review finding #2.)*
- **No literal secret on the streamed/rendered change-request surface.** The
  `confirmation_request` frame's display projection and the portal expander
  present the secret-redacted `change_request` projection, not raw secret-bearing
  `parameters`, for an action card. *(Finding #1, stream + render legs.)*
- **Signed-execution invariant preserved.** Redaction is a **projection** only:
  the `canonical_digest(parameters)` inputs that form the signed `args_digest`
  (SPEC-037) are unchanged, so resume-time digest verification and signing are
  unaffected — masking never mutates the signed copy. *(Finding #1's hard
  constraint.)*
- **Persisted-record exposure bounded.** The persisted `pending_calls` retains
  only what the signed-execution mechanism requires; a secret-bearing value that
  must persist raw for signing is bounded by the reference-only floor below and
  is never additionally echoed into a display surface. The exact
  persist-vs-redact reconciliation (projection split vs at-rest handling) is a
  `plan.md` decision. *(Finding #1, persistence leg.)*
- **Reference-only credential entry remains the structural floor.**
  `web.fill_credential` (a credential-set reference) stays the only path that
  introduces a secret into a browser flow, so a literal secret never reaches
  `web.type`/`parameters` in the first place; R-7 is defense-in-depth over that
  already-reference-only design and extends the same discipline to non-browser
  action parameters.
- Regression tests pin: (a) an off-vocabulary secret value is masked in the
  projection (fail-closed), (b) a secret-bearing parameter does not stream/render
  as plaintext for an action card, and (c) `args_digest` verification still
  passes after masking (invariant). Mapped in R-6 per ADR-0008.

## Non-Goals

- **No auto-publish / auto-execute of a graduated skill.** Graduation yields a
  human-reviewed draft; a human merges it into the Git skills repo and it is
  ingested like any skill before it can replay.
- **No change to SPEC-044's knowledge-draft path.** Knowledge/guidance export
  remains the default for non-executable skills; the executable-flow class is
  additive and opt-in.
- **No LLM synthesis of un-approved steps.** Graduation is deterministic over the
  captured, approved trace; it never invents a step the session did not actually
  run and get approved.
- **No cross-session trace merging / no shared trace library** in this spec (one
  session → one candidate flow). Composition of multiple traces is a follow-up.
- **No weakening of the signed-execution invariant, the origin allowlist, or the
  auto-allow exclusion** — replayed writes are as individually signed and
  gateway-guarded as hand-authored ones (ADR-0007 preserved, phased).
- **No reversal of ADR-0007.** Per-action cards remain wrong *for a mature/
  graduated flow*; this spec phases per-action (exploration, SPEC-054) against
  one-gate (graduated replay).

## Impact

- products touched:
  - `products/skills-hub` — the executable-flow skill class + `risk_class`
    decoupled from `web_target` in ingestion validation; `skill.schema.json`
    additive bump (skill `kind` + replay step list); validation of the step list
    + credential-set references (`services/ingestion.py`, `schemas/skill.py`).
  - `products/agent-platform` — the `AuthoringTraceStore` (dual-backend) +
    capture at the resume/receipt seam + the graduation endpoint (deterministic
    assembly + blast-radius re-validation) + the replay binding (incl. the
    non-browser flow-binding analog) (`services/`, `runtime_kernel.py`,
    `api/routes/`, `schemas/v2.py`); **R-7** hardens the change-request
    projection + persisted-record secret masking (`services/hitl_confirmations.py`
    `_generic_fields` fail-closed, `services/secret_params.py` vocabulary,
    `services/confirmation_records.py` `pending_calls` projection) with the
    signed `args_digest` inputs unchanged.
  - `products/tool-gateway` — the replay deviation guard for a graduated flow
    (reuses the origin/`risk_class`/step-budget guard); credential-set resolution
    at replay for infra steps (`tools/browser_connector.py`, `tools/`).
  - `products/execution-runtime` — signed replay envelopes (reuses SPEC-037/038;
    verify only unless the infra-binding needs a new envelope variant).
  - `products/operator-portal` — the graduation entry point on a session
    ("Graduate as skill"), the executable-flow draft preview (rendered + raw,
    SPEC-045 pattern), and replay surfacing (`web-ui/app/src/**`); **R-7**
    presents the secret-redacted `change_request` projection (not raw
    `parameters`) in the chat card expander (`web-ui/app/src/chat/ChatView.tsx`).
- samples / shared touched: `shared/shared-contracts/schemas/skill.schema.json`
  (additive executable-flow class); `shared/shared-contracts/policies/
  policy-default.yaml` (one new `session:skill_graduate` action + role
  bindings); `shared/shared-contracts/schemas/audit-event.schema.json` (one new
  `skill_graduated` event type); an optional `samples/` graduation demo.
- contracts touched: `skill.schema.json` (additive), `policy-default.yaml` (one
  new action), `audit-event.schema.json` (one new event type). The authoring
  trace is an **internal** agent-platform store (not a shared contract).
- identity / policy / audit / execution safety impact: **trust-model expansion**
  (ADR-0009) — a new executable-skill class that replays captured mutations under
  one gate; one new policy action + one new audit event type; execution safety
  preserved (every replayed write individually signed, gateway-guarded, never
  auto-allowed); secrets externalized to credential-set references. **R-7**
  tightens the same secret-safety posture at the approval seam (no new policy
  action, no new audit event type; the signed `args_digest` and execution-safety
  invariants are preserved — masking is projection-only).
- living state docs to update on delivery: root `CHANGELOG.md`, `VERSION`
  (+ lockstep constants), `docs/agentic-aiops-platform/release-notes/`,
  `docs/guides/configuration-reference.md` (any new knob: trace retention, step
  cap), `docs/agentic-aiops-platform/authorization-matrix.md` (new action),
  `docs/specs/README.md` (SPEC-055 → `delivered`), `docs/adr/README.md`
  (ADR-0009 → `accepted`), `docs/agentic-aiops-platform/delivery-roadmap.md`.

## Open Questions

All five were resolved at approval on 2026-09-07, adopting the recommendation
recorded in the draft in every case. The original options are retained so the
decision stays auditable; from here a requirement changes only by agreement,
recorded in the changelog (the `approved`-spec rule).

- **OQ-1 (trace retention):** what is the authoring-trace retention/lifecycle
  bound? Options: retain until explicitly graduated/discarded (unbounded, needs
  a cap + GC), or a longer fixed window (e.g. 180 days) independent of the
  30-day receipt sweep. Recommendation: retain until `graduated | discarded` with
  a per-session step cap and a configurable idle-GC, so a candidate is not lost
  to the receipt sweep but never grows unbounded.
  **Resolved:** adopt the recommendation — lifecycle-bound
  (`draft → graduated | discarded`), never time-bound to the receipt sweep, with
  the R-1 per-session step cap plus a configurable idle-GC knob documented in the
  configuration reference on delivery. A fixed window was rejected because it
  reintroduces precisely the loss the dedicated trace exists to prevent.
- **OQ-2 (non-browser replay binding):** the flow-binding/one-gate machinery
  (`FlowContext`, `build_flow_request`, the gateway deviation guard) is
  browser-specific today. How should an **infra** executable flow (`k8s.*`) bind
  and collapse to one gate — a generalized flow-binding keyed on the skill
  identity rather than `web.navigate`, or a browser-only replay in this spec with
  infra replay deferred? Recommendation: generalize the binding key to the skill
  identity so both domains replay under one gate; if that proves too large, ship
  browser replay in SPEC-055 and defer infra replay to a follow-up (infra steps
  meanwhile park per-action via SPEC-054, which fails safe).
  **Resolved:** take the deferred half of the recommendation, per the operator's
  direction at approval — this spec ships **browser** replay under one gate, and
  the generalized binding keyed on skill identity (what an infra `k8s.*`
  executable flow needs) is targeted at **0.36.0** as its own slice. Until it
  lands, an infra executable flow's steps park per-action under SPEC-054 R-2,
  which fails safe and is already the shipped posture. R-5's "non-browser replay
  binding" criterion is therefore scoped to *asserting* that safe fallback, not
  to delivering the generalized binding.
- **OQ-3 (graduation action reuse):** should graduation reuse SPEC-044's
  `session:skill_draft` (since it is also a session→skill draft) or add a distinct
  `session:skill_graduate`? Recommendation: a **distinct** action + audit event,
  because graduating an executable *mutating* artifact is a higher-trust
  operation than drafting knowledge and should be separately authorized and
  audited.
  **Resolved:** adopt the recommendation — one distinct `session:skill_graduate`
  action and one distinct `skill_graduated` audit event, role-gated to
  operator/approver and never observer. Reusing `session:skill_draft` was
  rejected because it would let a role authorized only for knowledge drafts
  produce an executable mutating artifact, and would collapse two different trust
  levels into one audit vocabulary.
- **OQ-4 (executable-flow schema shape):** the exact replay-step-list schema
  (ordered `{tool, args-with-credential-refs, expect?}`) and whether it lives in
  `skill.schema.json` (Skill v2) or a sibling schema. Recommendation: additive
  fields in `skill.schema.json` under a `kind: executable_flow` discriminator,
  validated by skills-hub ingestion.
  **Resolved:** adopt the recommendation — additive fields in
  `skill.schema.json` under a `kind: executable_flow` discriminator (Skill v1 →
  v2), validated by skills-hub ingestion on the existing path, with the replay
  step list as an ordered `{tool, args, expect?}` array whose credential values
  are credential-set **references** and never literals. A sibling schema was
  rejected: two skill contracts would drift, and ingestion already validates one
  document shape.
- **OQ-5 (trace ownership):** confirm the authoring trace is agent-platform-owned
  (capture is at the kernel seam) while the graduated artifact is skills-hub-owned
  (ingested skill) — i.e. the trace is transient authoring state and the skill is
  the durable output. Recommendation: yes; the trace is not a shared contract.
  **Resolved:** adopt the recommendation — the trace is agent-platform-owned
  transient authoring state and is **not** a shared contract; the graduated skill
  is the durable, skills-hub-owned output. This preserves the no-cross-product-
  import invariant: skills-hub never reads the trace, it ingests the drafted
  Markdown like any other skill.

## Changelog

- 2026-09-06: created as `draft`. The graduation destination of the
  operator-approved A→B→C program, implementing ADR-0009: a durable
  authoring-trace store (the operator's chosen dedicated-trace option over
  retention-bounded reuse), an executable-flow skill class with `risk_class`
  decoupled from `web_target`, deterministic human-merge graduation with
  blast-radius re-validation, and one-gate secret-safe replay. Sequenced after
  SPEC-054 (the action-approval phase it graduates from); phases ADR-0007 rather
  than reversing it.
- 2026-09-07: **approved** by the operator, and ADR-0009 accepted the same day.
  Slice fixed as the seventeenth R5 slice. OQ-1..OQ-5 resolved on the draft's own
  recorded recommendations, with one operator-directed scoping call: OQ-2 ships
  browser replay under one gate here and targets the generalized non-browser
  (infra `k8s.*`) flow binding at **0.36.0**, so R-5's non-browser criterion
  asserts the safe per-action fallback (SPEC-054 R-2) rather than delivering the
  generalized binding. No requirement text changed. Bookkeeping:
  `docs/specs/README.md` row `draft` → `approved`, `docs/adr/README.md` ADR-0009
  `proposed` → `accepted`, and a new `delivery-roadmap.md` Exploration Backlog row
  added. Implementation remains **sequenced after SPEC-054**: `plan.md`/`tasks.md`
  are authored once B is `delivered`, not at approval.
- 2026-09-07 (post-approval scope addition): folded into a new **R-7
  (approval-seam secret-masking hardening)** the two change-request
  secret-masking gaps SPEC-054 explicitly recorded and deferred (its Non-Goal
  "No masking of the raw parameters already persisted on the durable record" +
  OQ-5, re-confirmed by the SPEC-054 delivery review), by operator agreement per
  the `approved`-spec rule that a requirement changes only by agreement recorded
  here. Findings: **#1** raw secret-bearing `parameters` persist in
  `pending_calls`, ride the `confirmation_request` stream frame, and render in
  the portal expander behind the masked `change_request` projection; **#2** the
  projection's generic field-masking (`_generic_fields`) fails **open** for an
  off-vocabulary secret value. Rationale for folding rather than a standalone
  SPEC-056: R-1/R-2/R-5 already own secret-safety at the approval seam (R-2
  parameterizes secrets at capture reusing the SPEC-049 R-5 redaction vocabulary
  + `web.fill_credential`/credential-set indirection; R-5's one-gate replay
  builds on the SPEC-054 R-3 change-request framing), so the findings are the
  **source-side complement** of that guarantee — the same surface, vocabulary,
  and files; a separate spec would split one concern across two. R-7 states the
  invariant (fail-closed masking; no plaintext secret on the stream/render
  surface; signed `args_digest` preserved; reference-only `web.fill_credential`
  floor) and defers the persist-vs-redact reconciliation — the raw `parameters`
  feed `canonical_digest` = the signed `args_digest` (SPEC-037) — to `plan.md`.
  Bookkeeping: R-6's traceability list broadened to R-1..R-5 **+ R-7**; Summary,
  Motivation, and Impact note the addition; `docs/specs/README.md` and
  `delivery-roadmap.md` SPEC-055 rows broadened (adds "extends SPEC-054 R-3"
  lineage). No requirement IDs renumbered (stable once `approved`); R-7 is
  appended with a placement note. `plan.md`/`tasks.md` remain unauthored
  (SPEC-054 is now `delivered`), so R-7 folds in **before** planning. The two
  findings are non-blocking defense-in-depth and ship on SPEC-055's timeline
  rather than an interim 0.35.x patch.
- 2026-09-08: `plan.md` + `tasks.md` **authored** — the workflow gate cleared
  when SPEC-054 reached `delivered` at v0.35.0 (the Status block's B-before-C
  precondition). `plan.md` resolves the items the approved spec delegated,
  foremost the **R-7 persist-vs-redact reconciliation**: a pre-implementation
  code read confirmed the signed `args_digest` is computed at resume from the
  in-memory `PendingConfirmation` (`build_requests` re-parses `tool_calls`),
  never from the persisted `confirmation_records.pending_calls` JSONB nor the
  stream frame, and a parked confirmation never survives a restart — so masking
  is a pure display + persistence projection (redact an action card's raw
  parameter values in place) with **no contract change** and a byte-identical
  `args_digest`. It also pins the R-1 dual-backend trace store
  (`draft → graduated | discarded`, two knobs), the R-3 Skill v1 → v2 additive
  executable-flow class, R-4 deterministic no-LLM graduation, and R-5
  browser-only replay (OQ-2 defers the infra binding). `tasks.md` lays out eight
  stages with an R-1..R-7 → asserting-test delivery gate (ADR-0008).
  Bookkeeping: `docs/specs/README.md` row `approved` → `in-progress`.
  **Implementation started; status → `in-progress`.**
- 2026-09-09: **delivered** (v0.36.0, seventeenth R5 slice). All seven
  requirements shipped across the eight-stage plan; no requirement text
  changed. **R-1** — `AuthoringTraceStore` (`Protocol` + `InMemory` +
  `Postgres` + factory), every schema field on both backends, lifecycle
  `draft → graduated | discarded` with retention independent of the 30-day
  execution sweep, a per-session cap and an idle-GC that never sweeps a
  terminal row. **R-2** — capture at both signing sites (per-action and
  flow-unlock) beside `_persist_execution_request`, gated on
  `RISK_LEVEL_ACTIONS[tier] == "tools:mutate"` so it fails **closed** on an
  unclassified tier (being signed is not being a mutation: an unvetted read
  tool parks, is approved and is signed like any write), best-effort and
  fail-safe, with secrets parameterized at capture and `delete_session`
  cascading the trace. **R-3** — `skill.schema.json` **v1 → v2** (additive
  `kind`/`steps`), `risk_class` accepted without a `web_target`, ingestion
  validation on the existing `validate_document` path, `kind TEXT` + `steps
  JSONB` on both store backends, and `skill-format.md` v1 → v2 beside the
  schema. Two tightenings recorded in `tasks.md`: `risk_class: write` is
  required **unconditionally** for `kind: executable_flow`, and a `web.*` step
  still requires a `web_target`. **R-4** — the stage-6a refinement stands as
  delivered: the **declared target** (`authoring_trace_target`) and the
  **observed origin** (`authoring_trace.flow_origin`) are two recorded things,
  the origin captured at the receipt seam for a `succeeded` result only and the
  declaration stored as origin **and path** with query, fragment and userinfo
  stripped. `POST /api/v1/sessions/{id}/skill-graduate` renders the draft
  deterministically — no model call, no skeleton — after
  `revalidate_blast_radius` (five guards) runs and refuses `409` naming every
  guard the trace failed; gated by the new `session:skill_graduate` action,
  audited once as `skill_graduated`, lifecycle flipped to `graduated`, and
  never auto-published. **R-5** — verification, not construction: a graduated
  browser flow binds through the existing SPEC-051 path, and its `steps` list is
  never an input to its own gate, guaranteed structurally twice over
  (`bind_flow` reads five named fields and takes its budget from the gateway
  knob; `FlowState` declares no `kind`/`steps` at all). Credentials resolve at
  replay from credential-set references; executable-flow writes join no
  auto-allow list. A review finding hardened `_sign_flow_execution` with its own
  `BROWSER_WRITE_TOOLS` guard, so the function enforces the browser-only scope
  its contract always claimed rather than relying on its single gated call
  site. **R-6** — the R-1..R-7 → asserting-test mapping is recorded in
  `tasks.md`, and `samples/web-checks/skill-graduation/` (`README.md` +
  `WALKTHROUGH.md` + `demo/demo.sh`, six deterministic legs plus four opt-in
  chat acts) exercises the loop in the verification path; the two sibling
  web-check demos are byte-identical and green. **R-7** — `should_mask` flipped
  to fail closed against a curated `KNOWN_SAFE_FIELDS` allow-list, an `action`
  card's raw `parameters` redacted in place at the park site, on the durable
  record and on the stream frame, the portal expander presenting the masked
  projection, `web.evaluate.expression` added to `OPAQUE_VALUE_FIELDS` with the
  nesting walker taking the tool name, and the signed `args_digest` proven
  byte-identical with and without redaction. **OQ-2 did not ship** and is
  re-anchored to its own `delivery-roadmap.md` backlog row rather than silently
  carried: an infra executable flow's steps park per-action under SPEC-054 R-2,
  which fails safe and is asserted. Three new knobs
  (`AGENT_AUTHORING_TRACE_MAX_STEPS` 100, `AGENT_AUTHORING_TRACE_IDLE_DAYS`
  180, `AGENT_SKILL_GRADUATION_MAX_STEPS` 20) are documented in
  `docs/guides/configuration-reference.md`, and `authorization-matrix.md`
  carries the new action. `make verify` green at 0.36.0 (2424 python tests
  across the eight products — agent-platform 1142, tool-gateway 336,
  platform-gateway 354, skills-hub 184, audit-service 138, incident-service
  137, execution-runtime 73, identity-broker 60 — four kustomize overlays, 18
  policy rules, 137 api + 19 tools scenarios with every granted pair covered,
  version lockstep, and all three secret-vocabulary agreements); portal
  `npm test` 342 across 29 files and `npm run build` clean; version lockstep
  **0.36.0** across `VERSION` + 8 `pyproject.toml` + 8 `metadata.py` + 2
  `__init__.py` + 8 `uv.lock` re-locks. Landing the portal suite took one
  test-harness fix recorded in the release note (a React 19 + jsdom
  scheduler-teardown race that made a fully passing vitest run exit non-zero);
  it touches no product behavior, which is why it is not in `CHANGELOG.md`.
  Bookkeeping: `docs/specs/README.md` row `in-progress` → `delivered`,
  `delivery-roadmap.md` row rewritten to `Delivered 2026-09-09 (0.36.0)` with
  the new OQ-2 backlog row, `docs/adr/README.md` ADR-0009 stays `accepted`,
  this Status block, and a `## 0.36.0` section in `CHANGELOG.md` plus the dated
  release note. **Status → `delivered`.**
- 2026-09-09: **post-delivery fix, folded into v0.36.0** (no requirement text
  changed) — the `dev-k8s` browser live check that closes this spec's delivery
  gate found three defects in the R-6 sample
  (`samples/web-checks/skill-graduation/`). All three are in the sample and none
  in the platform, so the deployed `0.36.0-dev-k8s-6c45e21` images are
  unaffected and no rebuild followed — neither `demo.sh` nor the walkthrough
  ships inside an image. **(1)** The act-1 prompt asked the model to click
  "Sign in", which the target's legacy-SSO auto-login makes impossible: it hides
  the form and navigates to the user list within 100 ms of both credential
  fields holding a value, so the click failed on a detached element. The model
  recovered and completed both resets, but the failed write stayed in the trace
  with no observed origin, and R-4 refuses to graduate an unverified step — the
  guard behaving exactly as specified, against a prompt that guaranteed it would
  fire. Both chat prompts and their two `WALKTHROUGH.md` mirrors now let the
  page redirect itself. The two sibling web-check demos were already reconciled
  to gate on "Confirm reset" with the login left read-tier, so this aligns the
  new sample with a posture the repo held rather than inventing one. **(2)** Act
  3 made its skill-detail `GET` exactly once, against the service the act had
  just restarted, and `rollout status` returning does not mean the Service
  endpoints have finished propagating: the call answered `502` "skills hub
  unavailable" — the gateway's honest mapping of an httpx transport error, so
  nothing reached skills-hub — reproducibly, 3 runs out of 3 in a controlled
  probe, recovering on the second attempt even when the inventory call
  immediately before it had answered `200` on its first try. It is now
  bounded-retried on `502`/`503` only, mirroring the inventory retry beside it,
  so a `404`/`401`/`403` — a real answer about that skill — still fails at once.
  **(3)** `WALKTHROUGH.md` step 1 sent the reader to a `svc/web-ui` localhost
  port-forward to sign in, but the identity-broker starts every login at
  `OIDC_REDIRECT_URI`, which `shared/platform-ops/gitops/dev-k8s/README.md`
  documents as making the canonical origin the only one where sign-in
  round-trips; step 1 now names that origin and says why a localhost tab stays
  signed out. The same stale instruction stands in the two sibling web-check
  walkthroughs, which predate this spec and are flagged rather than fixed here.
  R-1..R-7 stand as written. The live check then passed end to end — six
  deterministic legs and four acts, ending on the contrast the sample exists to
  show (2 per-action cards authored ad hoc, 1 flow card replayed for the same
  work) — and R-7's masking was confirmed on all three legs by a separate probe,
  because this sample deliberately parks no secret-bearing card for the demo to
  observe. Recorded in the root `CHANGELOG.md` under 0.36.0 → Fixed.
