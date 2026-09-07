# SPEC-055: Develop-As-You-Go Skill Graduation

## Status

- status: `approved`
- owner: luban-platform-team
- created: 2026-09-06
- approved: 2026-09-07
- release slice: R5 — Hardening and External Consumption (seventeenth R5 slice)
- implementation start: gated on SPEC-054 reaching `delivered` (B before C).
  `plan.md`/`tasks.md` are authored at that point, not at approval, because this
  spec's capture seam and replay binding are built on the `approval_kind`
  discriminator and per-action parking that SPEC-054 ships.
- related ADRs: **ADR-0009** (graduate troubleshooting sessions into replayable
  executable skills via a durable authoring trace — this spec implements it),
  ADR-0007 (one HITL gate per mutating browser flow — **phased**, a graduated
  flow replays under one gate), ADR-0008 (spec delivery traceability gate);
  lineage: extends SPEC-044 (skill authoring export — knowledge-only draft),
  SPEC-045 (draft preview), SPEC-049/050/051 (browser web-check tools + flow
  gate enforcement), SPEC-037/038 (signed execution requests + isolated worker),
  SPEC-014 (skills and grounded guidance), and **depends on SPEC-054**
  (action-level HITL approval — the exploration/authoring phase that produces the
  mutations this spec graduates)
- sequencing: A (the SPEC-051 R-6 headline-leak patch) landed; B (SPEC-054) is
  the action-approval prerequisite; C (this spec + ADR-0009) is the graduation
  destination. A→B does not conflict with C.

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

- Every R-1..R-5 acceptance criterion maps to at least one automated test
  recorded in `tasks.md` (authoring-trace store dual-backend round-trip incl.
  the `postgres` backend; capture-only-on-signed-mutation; secret
  parameterization at capture; `risk_class`-without-`web_target` ingestion;
  executable-flow schema validation; graduation blast-radius refusal + happy
  path + draft-not-published; one-gate replay with per-write signing +
  credential-set resolution).
- Any shipped `samples/` graduation demo is exercised by its own script in the
  verification path (ADR-0008 exercised-sample rule).
- `docs/specs/README.md` and `CONTRIBUTING.md` carry the ADR-0008 delivery-gate
  text (unchanged).

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
    `api/routes/`, `schemas/v2.py`).
  - `products/tool-gateway` — the replay deviation guard for a graduated flow
    (reuses the origin/`risk_class`/step-budget guard); credential-set resolution
    at replay for infra steps (`tools/browser_connector.py`, `tools/`).
  - `products/execution-runtime` — signed replay envelopes (reuses SPEC-037/038;
    verify only unless the infra-binding needs a new envelope variant).
  - `products/operator-portal` — the graduation entry point on a session
    ("Graduate as skill"), the executable-flow draft preview (rendered + raw,
    SPEC-045 pattern), and replay surfacing (`web-ui/app/src/**`).
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
  auto-allowed); secrets externalized to credential-set references.
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
