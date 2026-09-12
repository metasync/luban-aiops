# SPEC-056: Studio — A Dedicated Skill-Development Workspace

## Status

- status: `approved`
- owner: luban-platform-team
- created: 2026-09-12
- approved: 2026-09-12
- release slice: R5 — Hardening and External Consumption (eighteenth R5
  slice, targeting v0.37.0)
- related ADRs: **ADR-0009** (graduate troubleshooting sessions into
  replayable executable skills — Studio becomes the authoring home of the
  declare-target + graduate controls, whose behavior and trust model are
  unchanged), ADR-0008 (spec delivery traceability gate); **no new ADR** —
  this reorganizes existing surfaces and adds one additive contract
  discriminator rather than making a new trust-model decision.
  lineage: extends SPEC-055 (develop-as-you-go skill graduation — the
  declare-target + graduate controls this spec moves into Studio),
  SPEC-044/045 (skill-draft export — the draft control this spec keeps in
  Chat), SPEC-022/023 (multi-session workspace + portal rebuild — the
  session contract and `ViewId` nav this spec extends), SPEC-039/040
  (operations document repository + shift summary — the session picker this
  spec filters), and SPEC-019 (portal transparency — the role-gated nav).
- drafting: memo-free, drafted directly from the 2026-09-08→12 operator
  design discussion (the SPEC-045/046/049 memo-free precedent — the
  discussion is the evidence base). The companion role-vocabulary
  reconciliation (retire the design-only `senior-operator`, document the
  implemented `developer` role) landed separately as a docs-only patch on the
  0.36.3 line and is deliberately **not** part of this spec.

## Summary

The operator portal today drives both regular operations and skill
development through one **Chat** entry, so two different operating models —
different role postures, different artifacts, different document-generation
semantics — share one undifferentiated surface. This spec splits that entry
in two: **Chat** for *operation* sessions and a new **Studio** for
*development* sessions, over **one shared chat core** parameterized by a
`mode`, and backs the split with an additive `session_type` discriminator on
the session contract that is **fixed at birth** and **immutable** — never
changed afterwards, with no in-place conversion between the two entries.

The payoff is the four goals the operator asked for: (1) two distinct entries
so the mental model is explicit; (2) a clean role mapping — Studio is an
authoring power held by `operator`/`approver`/`platform-admin`, and
`developer`/`read-only-observer`/`auditor` keep Chat only; (3) correct
document generation — the shift-summary session picker stops offering
development sessions as operational handover material; (4) blast-radius
control — the security-critical core (SSE stream, secret masking, HITL
confirmation) is shared and asserted identical across both modes, never
forked.

## Motivation

- **One entry, two operating models.** Chat carries read-only operations
  (query, triage, draft knowledge) *and* skill development (declare a target,
  run approved mutations, graduate an executable flow). They have different
  role postures and different artifacts, but the portal presents them as one
  undifferentiated session list.
- **A live document-generation defect.** The shift-summary session picker in
  `views/workspace/DocumentsView.tsx` is **unfiltered** — it lists every
  session, so a develop-as-you-go session appears as shift-summary material.
  A development session is not operational shift work; offering it is wrong
  and there is no `session_type` to filter on today.
- **`session_type` is fluid, not fixed.** The mid-session **Declare target**
  control in `chat/ChatView.tsx` (the SPEC-055 R-4 path) turns an operation
  session into a development session *after* birth, so "what kind of session
  is this" has no stable answer at creation — which is exactly what the
  document filter and the role mapping need.
- **The role mapping is implicit.** `developer` sees Chat but can never
  graduate (`session:skill_graduate` is denied to it), so a development
  session opened by a developer is a dead end; and an operator does
  everything in one entry with no signal that authoring is a distinct,
  higher-trust posture.
- **Why now / why this slice.** SPEC-055 delivered graduation, so the
  authoring surfaces (draft / declare-target / graduate) now exist and can be
  cleanly re-homed. This is squarely the R5 "easier to operate and govern"
  theme: no new capability, just a safer, clearer arrangement of the ones we
  have.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable
acceptance criteria.

### R-1: An additive `session_type` discriminator, fixed at birth and immutable

The session contract gains an additive `session_type` field with two values,
`operation` and `development`, set once at session creation from the entry
point and **never changed afterwards**.

Acceptance criteria:

- `session_type` is an **additive** enum (`"operation" | "development"`) on
  the session record, defaulting to `operation`. It follows the established
  additive-column convention and is added in **lockstep** across every mirror:
  the `shared/shared-contracts` session JSON schema, agent-platform
  `schemas/api.py` (`SessionRecord`) and `schemas/v2.py`, platform-gateway
  `schemas/api.py` (the `extra="forbid"` session mirror), the Postgres DDL and
  row mappers in agent-platform `services/session_store.py`, and the portal
  `api/sessions.ts` `SessionSummary`/`SessionDetail` interfaces. A contract
  drift guard asserts the field on every mirror (the skills-hub
  one-backend-only lesson).
- A session created from **Chat** is `operation`; a session created from
  **Studio** is `development`. The value is written once at creation and is
  never inferred from ambient state afterwards.
- `session_type` is **immutable**: it is written exactly once at creation and
  no code path changes it afterwards — there is no promotion, no demotion
  (`development → operation`), and no in-place conversion between entries. A
  session's type is a birth property, not a projection of later state. (The
  Chat→Studio bridge an earlier draft contemplated is deferred to SPEC-057 as
  a *spawn* of a new session, never a mutation of this field — see R-3.)
- Legacy sessions (created before this field existed) are backfilled by a
  one-time migration that **infers** `development` for a session already
  holding a declared authoring-trace target and `operation` otherwise (resolved
  OQ-2), and never leaves a session with a null `session_type`.

### R-2: Studio as a distinct, role-gated entry over one shared core

The portal gains a second session entry, **Studio**, beside Chat; both render
the same chat core, parameterized by a `mode`, and Studio is visible only to
the authoring roles.

Acceptance criteria:

- `App.tsx`'s `ViewId` union gains a `studio` member and the sidebar gains a
  **Studio** item; `roles.ts` gains a `STUDIO_ROLES` set equal to the
  authoring roles (`platform-admin`, `approver`, `operator`) — the same set
  that holds `session:skill_graduate` — so `developer`, `read-only-observer`,
  and `auditor` never see the entry (Option A: authoring stays an operational
  power).
- **One** `ChatView` renders both entries, parameterized by
  `mode: "operation" | "development"`. There is no second chat implementation.
- A Studio session is created with `session_type=development` and may name a
  `skill_target` at birth (riding `session:create`, inert per SPEC-055 R-4 —
  it narrows what a later graduation may emit and grants nothing).
- Each entry lists **its own** sessions: Chat lists `operation`, Studio lists
  `development`, via an additive `session_type` filter on `session:list`
  (ownership-scoped exactly as today; anti-enumeration preserved) — each entry
  scoped to its own type (resolved OQ-3).
- The Chat entry's role gating is **unchanged** (broad, as today); only Studio
  is narrowed.

### R-3: Control placement split, no in-place conversion

The authoring controls land where they belong: knowledge-drafting stays in
Chat, and target-declaration and graduation live only in Studio. There is
**no in-place conversion** between the two entries — a session's type is fixed
at birth (R-1).

Acceptance criteria:

- **Chat (`operation` mode) keeps "Draft as skill"** (`session:skill_draft`,
  and `incident:skill_draft` on the incident surface). Drafting emits
  **read-only grounded-guidance knowledge** on the `documents:create` posture
  — it needs no declared target and no authoring trace, and it may summarize a
  session that touched **many** targets (a runbook for a multi-target
  troubleshooting session). This is the natural reusable artifact of an
  operation session, and it belongs to operations, not Studio.
- **Studio (`development` mode) holds "Declare a target" and "Graduate as
  skill"** (`session:skill_graduate`). Graduation emits a **replayable
  single-target executable flow**. The mid-session **Declare target** control
  is **removed from Chat** — it exists only in Studio, so an operation session
  can no longer silently become a development one in place.
- **No "Move to Studio" conversion — and the reason is a trust invariant, not
  convenience.** SPEC-055 R-4 re-validates *every observed origin against the
  one declared target*, and that target must be named *before* mutating (an
  authorization scope, "not a claim fitted to the trace afterwards"). An
  operation session is inherently multi-target (query A, health-check B,
  diagnose C), so its authoring trace spans multiple origins; declaring a
  single target after the fact would make graduation **deterministically
  refuse** (SPEC-055 R-4). Converting an operation session into a development
  one is therefore semantically unsound, not merely awkward, and this spec
  does not offer it. A development session is **born** in Studio with its
  target declared up front and stays single-target.
- **Deferred to SPEC-057 (not delivered here):** the ergonomic Chat→Studio
  bridge — a **"Continue in Studio"** action that *spawns a fresh* development
  session carrying context from the operation session (never mutates this
  session's `session_type`) — and the **composition / runbook-of-skills**
  construct that sequences single-target skills into a multi-target workflow,
  plus assisted trace-extraction. In SPEC-056 an operator who wants a
  replayable skill simply opens Studio directly and authors it single-target.

### R-4: Document generation filters by `session_type`

Operational document generation stops treating development sessions as
operational material.

Acceptance criteria:

- The **shift-summary** session picker (`DocumentsView.tsx`) lists only
  `operation` sessions. A `development` session is never offered as
  shift-summary material — this closes the live unfiltered-picker defect named
  in Motivation.
- The filter is enforced **server-side** (the session-list query is scoped by
  `session_type`), not only hidden in the client, so the picker cannot be
  coerced into listing a development session.
- **Incident-report** documents are unaffected: they anchor to an `incident_id`
  (SPEC-043), not to the session picker, so the operational record of an
  incident is preserved regardless of any linked session's type.
- No other document type or generation path changes.

### R-5: Shared-core invariant (blast-radius control)

The two entries differ only in surface; the security-critical core is one
implementation, asserted identical across both modes.

Acceptance criteria:

- The SSE stream adapter, the secret-masking / change-request projection
  (SPEC-054 R-3 / SPEC-055 R-7), and the HITL confirmation-card path are
  **shared**, never forked per mode. `mode` selects visible controls, the
  `session_type` written at birth, and the list scope — nothing in the trust
  path.
- A regression test asserts both modes render the **same** core: an identical
  stream/masking/HITL surface for a given transcript, with only the
  mode-specific controls differing. A divergence fails the suite.
- No new executor, no new signing path, no change to the gateway deviation
  guard, the origin allowlist, or the auto-allow exclusion. Graduation and
  replay keep their SPEC-055 guarantees verbatim.

### R-6: Authorization posture — Option A, no new policy vocabulary

Studio is an authoring power; the split introduces no new policy action and no
new audit event type.

Acceptance criteria:

- Studio entry and every authoring control are gated to
  `platform-admin`/`approver`/`operator` — the roles that already hold
  `session:skill_graduate`. `developer`, `read-only-observer`, and `auditor`
  are denied, matching the reconciled authorization matrix.
- Creating a `development` session is gated on the **existing**
  `session:skill_graduate` action (a route-level dual-gate beside
  `session:create`, the SPEC-043/045 `documents:create`+`incident:read`
  precedent) rather than a new action — a session whose only distinguishing
  power is graduation should require the graduation grant to open (resolved
  OQ-1). The gateway re-enforces this on every request; the client nav gate is
  convenience, not the boundary.
- **No new policy action and no new audit event type.** Draft, declare-target,
  and graduate keep their SPEC-044/045/055 actions and events verbatim. There
  is no `session_type` mutation to audit (the field is immutable, R-1);
  declaring a target keeps SPEC-055's deliberately-unaudited posture — a
  declaration is a scope, not an operational act.
- The `developer` role itself is unchanged: kept and documented (the companion
  docs reconciliation), read-mostly, denied Studio.

### R-7: Delivery traceability per ADR-0008

This spec is delivered under the ADR-0008 gate.

Acceptance criteria:

- Every R-1..R-6 acceptance criterion maps to at least one automated test
  recorded in `tasks.md` — the `session_type` contract-drift guard across all
  mirrors; the fixed-at-birth + **immutability** invariants (no code path
  promotes, demotes, or converts a session's type post-birth); Studio nav
  gating per role; the shared-core both-modes-identical regression; the
  shift-summary `operation`-only filter (server-side); and the
  development-session dual-gate denial for a non-authoring role.
- Any shipped `samples/` demo is exercised by its own script in the
  verification path (ADR-0008 exercised-sample rule).
- `docs/specs/README.md` and `CONTRIBUTING.md` carry the ADR-0008
  delivery-gate text (unchanged).

## Non-Goals

- **No fork of the chat surface.** Studio is a `mode` over one `ChatView`, not
  a second implementation (R-5 is the invariant, not an aspiration).
- **No new skill-authoring capability.** Draft, declare-target, and graduate
  already exist (SPEC-044/045/055); this spec **re-homes** them and changes
  neither their behavior nor their trust model.
- **No in-place conversion between entries.** `session_type` is immutable
  (R-1): there is no "Move to Studio", no promotion, no demotion, and no
  merging of two sessions' traces. The Chat→Studio *spawn* bridge, the
  composition / runbook-of-skills construct, and assisted trace-extraction are
  all deferred to **SPEC-057** (SPEC-055's one-session-one-candidate non-goal
  stands meanwhile).
- **No change to the graduation/replay trust model.** Blast-radius
  re-validation, one-gate replay, per-write signing, credential-set
  references, and secret masking are untouched.
- **No new policy action or audit event type** (R-6). OQ-1 resolved to the
  route-level dual-gate on the existing `session:skill_graduate`, so there is
  no dedicated entry action and no policy-bundle change.
- **No rename or removal of the `developer` role.** It is kept and documented;
  the role-vocabulary reconciliation is a separate, already-landed docs patch.
- **No change to Chat's existing role gating** — only Studio is narrowed.

## Impact

- products touched:
  - `products/operator-portal` — `web-ui/app/src/App.tsx` (`ViewId` union +
    nav gating), `roles.ts` (`STUDIO_ROLES`), `chat/ChatView.tsx` (`mode`
    parameterization: drop declare-target/graduate from `operation`, keep
    draft; add declare-target/graduate to `development`; **no** conversion
    control), `sessions/useSessionWorkspace.ts`
    (`createDevelopmentSession`, per-mode list scoping),
    `api/sessions.ts` (`session_type` on the interfaces, `createSession`,
    the list filter), and `views/workspace/DocumentsView.tsx` (shift-summary
    picker filtered to `operation`).
  - `products/agent-platform` — `schemas/api.py` (`SessionRecord`) and
    `schemas/v2.py` (additive `session_type`), `services/session_store.py`
    (Postgres DDL + mappers + backfill), the session-create handler (set
    `session_type` once; the development dual-gate), and the `session:list`
    filter. The declare-target route is unchanged from SPEC-055 — it names a
    target but never writes `session_type`.
  - `products/platform-gateway` — `schemas/api.py` (the `extra="forbid"`
    session mirror gains `session_type`) and the session create/list
    pass-through routes (dual-gate composition + filter forwarding); the
    declare-target pass-through is unchanged.
- samples / shared touched: `shared/shared-contracts/schemas/` (the session
  schema gains the additive `session_type` enum); optionally a `samples/`
  walkthrough showing the Chat/Studio split. **No** `policy-default.yaml`
  action change and **no** `audit-event.schema.json` change (OQ-1 resolved to
  the dual-gate, not a dedicated action).
- contracts touched: the session JSON schema (additive `session_type`) and its
  Pydantic/TS/DDL mirrors, in lockstep behind a drift guard. No stream-schema
  bump is expected (`session_type` rides the session record, not a stream
  frame) — confirmed at `plan.md`.
- identity / policy / audit / execution safety impact: **clarification, not
  expansion**. One additive contract discriminator; the role mapping made
  explicit (Studio = authoring roles, Option A); no new policy action, no new
  audit event type, no change to execution/HITL/masking (R-5 shares the core).
  The development-session dual-gate **tightens** entry (a non-authoring role
  can no longer open a dead-end development session).
- living state docs to update on delivery: root `CHANGELOG.md`, `VERSION`
  (+ lockstep constants), `docs/agentic-aiops-platform/release-notes/`,
  `docs/agentic-aiops-platform/authorization-matrix.md` (the Studio entry +
  development-session gate), `docs/guides/configuration-reference.md` (any new
  knob), `docs/specs/README.md` (SPEC-056 → `delivered`), and
  `docs/agentic-aiops-platform/delivery-roadmap.md`.

## Open Questions

All three were resolved at approval on 2026-09-12, adopting the recommendation
recorded in the draft in every case. The original options are retained so the
decision stays auditable; from here a requirement changes only by agreement,
recorded in the changelog (the `approved`-spec rule).

- **OQ-1 (Studio-entry gating mechanism):** how is development-session
  *creation* restricted to the authoring roles? Options: (a) a route-level
  **dual-gate** on the existing `session:skill_graduate` beside
  `session:create` (no new vocabulary); (b) a **new** dedicated action
  (`session:develop` / `studio:enter`); (c) **no server gate** — rely on the
  client nav plus the already-gated graduation (a developer could open a
  dead-end development session). Recommendation: **(a)** — it enforces the
  mapping server-side with no new policy vocabulary, and a session whose only
  distinguishing power is graduation should require the graduation grant to
  open. (b) adds a bundle version bump + scenarios + four byte-identical
  copies for no extra safety; (c) leaves the mapping client-only.
  **Resolved:** adopt the recommendation — (a) the route-level dual-gate on the
  existing `session:skill_graduate` beside `session:create`, no new policy
  vocabulary. A dedicated action (b) was rejected as a bundle version bump plus
  scenarios plus four byte-identical copies for no extra safety, and no server
  gate (c) was rejected for leaving the mapping client-only.
- **OQ-2 (legacy backfill):** what `session_type` do pre-existing sessions get?
  Options: default every legacy session to `operation`, or **infer**
  `development` for a session that already holds a declared authoring-trace
  target and `operation` otherwise. Recommendation: **infer** — a legacy
  session with a declared target is development work already, and defaulting
  it to `operation` would mis-file it into the shift-summary picker this spec
  exists to protect. The inference is a one-time migration.
  **Resolved:** adopt the recommendation — infer `development` for a legacy
  session that already holds a declared authoring-trace target and `operation`
  otherwise, as a one-time migration. Defaulting every legacy session to
  `operation` was rejected because it would mis-file existing development work
  into the shift-summary picker.
- **OQ-3 (per-entry list scoping):** should Chat and Studio each list only
  their own `session_type`, or should Studio list all sessions? Recommendation:
  **scope each entry to its own type** (an additive `session_type` filter on
  `session:list`) — it keeps the two mental models separate and makes the
  SPEC-057 spawn bridge read as a re-home when it lands. Ownership scoping is
  unchanged.
  **Resolved:** adopt the recommendation — scope each entry to its own
  `session_type` via an additive filter on `session:list`; ownership scoping is
  unchanged. Letting Studio list all sessions was rejected because it would blur
  the two mental models the split exists to separate.

## Changelog

- 2026-09-12: created as `draft`. Drafted memo-free from the 2026-09-08→12
  operator design discussion. Locks the decisions the discussion reached:
  the entry is named **Studio**; authoring stays an operational power
  (**Option A** — `operator`/`approver`/`platform-admin`, `developer` denied);
  `session_type` is **fixed at birth** and promoted **one way** as a
  single-writer projection of the declared target; **Design B** control
  placement (draft stays in Chat, declare-target + graduate move to Studio,
  "Move to Studio" is the bridge); the security-critical core is **shared and
  asserted identical** across modes (blast-radius control); and the
  shift-summary picker **filters to `operation`** (closing a live defect).
  Opens OQ-1..OQ-5, each with a recommendation, for resolution at approval.
  The companion role-vocabulary reconciliation (retire `senior-operator`,
  document `developer`) is intentionally out of scope — it landed as a
  docs-only patch on the 0.36.3 line.
- 2026-09-12 (revised): killed the in-place **"Move to Studio"** promotion and
  made `session_type` strictly **immutable** (R-1). Review against SPEC-055 R-4
  showed a multi-target operation session's trace spans multiple origins, so a
  post-hoc single-target declaration would make graduation **deterministically
  refuse** — conversion is semantically unsound, not merely awkward. Reframed
  R-3 around the two authoring artifacts (a read-only, multi-target-friendly
  **draft** in Chat vs a single-target replayable **graduate** in Studio) and
  confirmed skills stay **single-target** (a multi-target *workflow* is a
  composition of single-target skills, not a multi-target skill). Dropped OQ-3
  (promotion mechanics) and OQ-5 (flip audit); renumbered OQ-4 → OQ-3, leaving
  OQ-1 (entry gating), OQ-2 (backfill), OQ-3 (list scoping). The Chat→Studio
  **spawn** bridge ("Continue in Studio"), the **composition /
  runbook-of-skills** construct, and **assisted trace-extraction** are deferred
  to a new **SPEC-057**, recorded on the delivery-roadmap exploration backlog
  behind a composition-trust-model ADR + spike. Still no new ADR for SPEC-056.
- 2026-09-12: **approved** by the operator. Slice fixed as the eighteenth R5
  slice, targeting v0.37.0. OQ-1..OQ-3 resolved on the draft's own recorded
  recommendations in every case: OQ-1 the route-level dual-gate on the existing
  `session:skill_graduate` (no new policy action, no bundle change), OQ-2 infer
  the legacy backfill from a declared authoring-trace target, and OQ-3 scope
  each entry's list to its own `session_type`. The resolutions are folded into
  R-1/R-2/R-6, Non-Goals, and Impact; no requirement IDs renumbered (stable once
  `approved`). Bookkeeping: `docs/specs/README.md` row `draft` → `approved` and
  the `delivery-roadmap.md` SPEC-056 row → `approved`. Implementation
  (`plan.md`/`tasks.md`) is authored next, not at approval; the multi-target
  follow-on (spawn bridge + composition + assisted trace-extraction) stays
  deferred to SPEC-057.
