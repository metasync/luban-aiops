# ADR-0009: Graduate Troubleshooting Sessions Into Replayable Executable Skills Via a Durable Authoring Trace

## Status

`accepted`

- date: 2026-09-06
- accepted: 2026-09-07
- deciders: workspace maintainers
- related specs: SPEC-055 (develop-as-you-go skill graduation — implements this
  decision), SPEC-054 (action-level HITL approval — the exploration/authoring
  phase that feeds graduation), SPEC-044 (skill authoring export — the
  knowledge-only draft this extends), SPEC-049/050/051 (browser web-check tools
  + flow gate enforcement), SPEC-037/038 (signed execution requests + isolated
  worker), SPEC-014 (skills and grounded guidance); **phases the premise of
  ADR-0007** (one HITL gate per mutating browser flow) rather than superseding
  it.

## Context

The operator wants to promote an operating model: (1) troubleshoot via chat with
mutating actions properly approved; (2) turn a troubleshooting session into a
useful skill; (3) develop skills by running actions/tools in chat instead of
writing them up — "develop-as-you-go." Phase (1) is SPEC-054 (action-level
approval, including ad-hoc browser writes as per-action signed gates). Phases
(2)/(3) — *graduating* a session of approved mutations into a reusable,
replayable skill — have no platform support today, and three facts make the gap
a trust-model question rather than a feature request:

- **The only skill-draft path produces knowledge, not an executable flow.**
  SPEC-044's `skill_draft` emits a Markdown *grounded-guidance* document whose
  `SkillFrontmatter` is `extra="forbid"` with only `title`/`description`/`tags`/
  `version`; it structurally cannot declare `web_target`/`risk_class`/
  `flow_intent`, and SPEC-044 explicitly ships "no execution-path change (no
  mutating tools, no HITL)." A drafted skill is therefore always read-class
  guidance — it can inform an agent but can never *be* a runnable mutating flow.
- **Mutating-ness cannot be declared outside the browser.** `risk_class:
  read|write` exists (matching the operator's requested "explicit mechanism like
  the tool risk attribute") but ingestion rejects it without a `web_target`, so
  a non-browser mutating skill (e.g. one that runs `k8s.*`) cannot declare that
  it mutates. There is no executable-skill class for infra mutations at all.
- **The capture substrate is a receipt sweep, not a replay trace.** Every
  approved mutation is already durably captured — `execution_records` (ordered
  by `requested_at`, each individually signed with a receipt) and
  `confirmation_records` (with parameters). But `execution_records` stores an
  `args_digest` (a hash for signature verification), **not** replayable
  plaintext arguments, and it is swept at 30 days (`RETENTION_WINDOW_DAYS=30`).
  "Develop-as-you-go, graduate later" outlives that window and needs the
  arguments, not their digest.

ADR-0007 rejected per-action confirmation cards *for a mature flow* (they
violate one-gate-per-flow). The operator's model does not reverse that: it says
per-action approval is right for **exploration/authoring** (SPEC-054) and
one-gate is right for a **graduated, replayed flow** (SPEC-051). These are
lifecycle phases, not competing designs. What is missing — and what forces a new
decision — is the **bridge**: how a session of individually-approved mutations
becomes a single-gate replayable skill without weakening the signed-execution
invariant or leaking secrets.

## Decision

Introduce a **graduation pipeline** that turns an authored session into a
replayable executable skill, spanning skills-hub, agent-platform, tool-gateway,
and execution-runtime:

- **A durable, replay-oriented authoring trace**, captured as a by-product of
  each already-approved, already-signed mutation (at the resume/receipt seam),
  stored **separately from the 30-day `execution_records` sweep** with an
  authoring-scoped lifecycle (`draft → graduated | discarded`). It records the
  ordered step sequence with **secret-safe parameterization** — credentials as
  placeholders / credential-set references (the `web.fill_credential` /
  SPEC-049 R-5 indirection), never literal secret values — and **references**
  the existing `execution_id`/`confirm_id` rather than duplicating receipts.
  (The operator chose the dedicated-trace option over drafting within the
  retention window.)
- **An executable-flow skill class** that a graduated trace becomes: it declares
  `risk_class: write` **decoupled from `web_target`** (so any mutating skill —
  browser *or* infra — can declare mutating-ness via the same explicit mechanism
  as a tool's risk attribute) and carries a machine-readable replay step list.
  Graduation produces a **draft for human review and merge** — never an
  auto-published mutating skill (preserves SPEC-044's "the platform drafts,
  humans merge").
- **Replay under one gate.** A graduated executable flow inherits SPEC-051's
  one-gate-per-flow authority: the operator approves the flow once, and each
  replayed write is still individually **signed, persisted, audited, and
  receipted** (SPEC-037/038) and still bounded by the gateway deviation guard
  (origin allowlist, `risk_class`, step budget). Graduation does **not** create
  an auto-allow path.
- **Graduation re-validates blast radius.** Because one approval now unleashes a
  captured *sequence* of N mutations, promotion from trace to executable skill
  must re-validate that the sequence is safe under a single gate (bounded step
  count, allowlisted origins/targets, declared `risk_class`) before it can be
  replayed — the same guards SPEC-051 applies to a hand-authored flow.

## Alternatives Considered

- **Draft within the 30-day retention window from the existing
  `execution_records`** — rejected: those records store an `args_digest` (a
  hash), not the plaintext arguments a replay needs, and they are swept at 30
  days, so a session authored now may be un-graduable later. The operator
  explicitly preferred a dedicated authoring trace over the retention-bounded
  reuse.
- **Extend SPEC-044's knowledge draft to carry `risk_class`/`web_target`
  inline** — rejected: `SkillFrontmatter` is `extra="forbid"` and produces
  grounded-guidance Markdown, not an executable flow; retrofitting execution
  semantics onto the knowledge export conflates two distinct artifacts and
  bypasses skills-hub's ingestion validation. Graduation is a new artifact class,
  not a richer knowledge draft.
- **Keep `risk_class` gated behind `web_target` and graduate browser flows
  only** — rejected: the operating model includes non-browser mutating
  troubleshooting (`k8s.*`, etc.); a browser-only graduation cannot represent an
  infra-mutating skill, and the operator asked for an explicit mutating-ness
  mechanism general enough to match the tool risk attribute.
- **Auto-generate and auto-publish an executable skill from a session** —
  rejected: violates the human-merge principle (SPEC-044) and the fail-closed
  posture; an auto-published mutating skill would replay destructive actions
  with no human review of the blast radius.
- **One ADR spanning action-approval (B) and graduation (C)** — rejected:
  `docs/adr/README.md` requires one decision per ADR and forbids ADRs for
  decisions local to a single spec. The action-approval phase (SPEC-054) reuses
  the existing SPEC-020/021/030/037 mechanism and extends ADR-0007 without a new
  decision, so only the graduation trust model is recorded here.
- **Reverse ADR-0007 to allow per-action cards everywhere** — rejected: ADR-0007
  is correct for a *graduated* flow (one gate, bounded blast radius). This
  decision **phases** it — per-action for exploration, one-gate for replayed
  maturity — leaving ADR-0007 accepted and intact for the replay phase.

## Consequences

- realizes the develop-as-you-go operating model: a matured troubleshooting
  session becomes a reusable, one-gate, signed-replay executable skill, and
  mutating-ness is declared explicitly (`risk_class: write`) on **any** skill,
  browser or infra — the mechanism the operator asked for, mirroring the tool
  risk attribute.
- **New durable store, dual-backend.** The authoring trace needs an
  `InMemory` + `Postgres` store pair (like `execution_records` /
  `confirmation_records`). The known trap applies: a schema field added to only
  one backend is **silently dropped in production**, so both must change and
  verification must target `postgres` (the dev-k8s backend), not the in-memory
  default.
- **Expanded trust surface across four services.** A new executable-skill class
  + replay semantics touch skills-hub (ingestion/schema for the new class +
  decoupled `risk_class`), agent-platform (trace capture, graduation, replay
  binding), tool-gateway (replay deviation guard), and execution-runtime (signed
  replay envelopes) — a larger blast radius than any single prior spec, tracked
  as its own SPEC-055 with per-requirement tests under ADR-0008.
- **Replay blast radius is the central risk.** One approval unleashing a captured
  sequence means graduation must re-validate safety (step budget, origin/
  `risk_class` guard, TTL) exactly as SPEC-051 bounds a hand-authored flow; the
  gateway deviation guard remains the enforcement boundary and browser/infra
  writes still never auto-allow.
- **Secrets are externalized by construction.** A graduated skill is shareable
  and replayable only because credentials are placeholders / credential-set
  references, never baked literals — reusing the SPEC-049 R-5 redaction and
  `web.fill_credential` indirection.
- follow-up: SPEC-055 specifies the authoring-trace schema + retention, the
  executable-flow skill schema, the graduation + re-validation path, and the
  replay binding; ADR-0007 stays `accepted` (phased, not superseded); SPEC-044's
  knowledge-draft path is unchanged and remains the default for non-executable
  guidance.
