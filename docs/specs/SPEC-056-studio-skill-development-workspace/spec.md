# SPEC-056: Studio — A Dedicated Skill-Development Workspace

## Status

- status: `draft`
- owner: luban-platform-team
- created: 2026-09-12
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
the session contract that is **fixed at birth** and promoted **one way**.

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

### R-1: An additive `session_type` discriminator, fixed at birth

The session contract gains an additive `session_type` field with two values,
`operation` and `development`, set at session creation from the entry point
and changed only by R-3's one-way promotion.

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
- `session_type` is a **single-writer projection**: the only mutation after
  birth is R-3's one-way "Move to Studio" promotion. There is no demotion
  (`development → operation`) and no other code path writes the field.
- Legacy sessions (created before this field existed) are backfilled per
  OQ-2; the backfill is a one-time migration and never leaves a session with
  a null `session_type`.

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
  (ownership-scoped exactly as today; anti-enumeration preserved). See OQ-4.
- The Chat entry's role gating is **unchanged** (broad, as today); only Studio
  is narrowed.

### R-3: Control placement split and one-way "Move to Studio"

The authoring controls land where they belong: knowledge-drafting stays in
Chat, target-declaration and graduation move to Studio, and an operation
session can be promoted — one way — into Studio.

Acceptance criteria:

- **Chat (`operation` mode) keeps "Draft as skill"** (`session:skill_draft`,
  and `incident:skill_draft` on the incident surface). Drafting is an
  operational knowledge export on the `documents:create` posture — it needs no
  target and no authoring trace, so it belongs to operations, not Studio.
- **Studio (`development` mode) holds "Declare a target" and "Graduate as
  skill"** (`session:skill_graduate`). The mid-session **Declare target**
  control is **removed from Chat** — it exists only in Studio, so an operation
  session can no longer silently become a development one in place.
- Chat gains a one-way **"Move to Studio"** promotion for an operation session
  the operator realizes is really development work. Promotion (a) declares a
  target, (b) flips `session_type` to `development`, and (c) re-homes the
  session out of Chat's list and into Studio's. It is gated by
  `session:skill_graduate` (so only an authoring role may promote) and there
  is **no** move-back.
- Promotion is technically sound on an existing session because the authoring
  trace is captured as a by-product of each approved+signed mutation
  **regardless of any declared target** (SPEC-055 R-2); the declared target is
  what graduation later corroborates against, not what capture needs. A
  promoted session graduates exactly as a born-development one does.
- The single writer of a post-birth `session_type` change is the existing
  declare-target route extended to flip the field — **no new endpoint**
  (OQ-3).

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
  power is graduation should require the graduation grant to open (OQ-1). The
  gateway re-enforces this on every request; the client nav gate is
  convenience, not the boundary.
- **No new policy action and no new audit event type.** Draft, declare-target,
  and graduate keep their SPEC-044/045/055 actions and events verbatim; the
  `session_type` flip rides the existing (deliberately unaudited)
  declare-target posture — a declaration is a scope, not an operational act
  (OQ-5).
- The `developer` role itself is unchanged: kept and documented (the companion
  docs reconciliation), read-mostly, denied Studio.

### R-7: Delivery traceability per ADR-0008

This spec is delivered under the ADR-0008 gate.

Acceptance criteria:

- Every R-1..R-6 acceptance criterion maps to at least one automated test
  recorded in `tasks.md` — the `session_type` contract-drift guard across all
  mirrors; fixed-at-birth + single-writer (no demotion) invariants; Studio nav
  gating per role; the shared-core both-modes-identical regression; the
  shift-summary `operation`-only filter (server-side); the development-session
  dual-gate denial for a non-authoring role; and the one-way promotion
  (declare + flip + re-home) round-trip.
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
- **No demotion and no cross-type session merging.** Promotion is one way
  (`operation → development`); there is no move-back and no composing two
  sessions' traces (SPEC-055's one-session-one-candidate non-goal stands).
- **No change to the graduation/replay trust model.** Blast-radius
  re-validation, one-gate replay, per-write signing, credential-set
  references, and secret masking are untouched.
- **No new policy action or audit event type** (R-6); if OQ-1 resolves to a
  dedicated entry action instead of the dual-gate, that is the single
  exception and is recorded in the changelog at approval.
- **No rename or removal of the `developer` role.** It is kept and documented;
  the role-vocabulary reconciliation is a separate, already-landed docs patch.
- **No change to Chat's existing role gating** — only Studio is narrowed.

## Impact

- products touched:
  - `products/operator-portal` — `web-ui/app/src/App.tsx` (`ViewId` union +
    nav gating), `roles.ts` (`STUDIO_ROLES`), `chat/ChatView.tsx` (`mode`
    parameterization: drop declare-target/graduate from `operation`, keep
    draft, add "Move to Studio"; add declare-target/graduate to
    `development`), `sessions/useSessionWorkspace.ts`
    (`createDevelopmentSession`, per-mode list scoping),
    `api/sessions.ts` (`session_type` on the interfaces, `createSession`,
    the list filter), and `views/workspace/DocumentsView.tsx` (shift-summary
    picker filtered to `operation`).
  - `products/agent-platform` — `schemas/api.py` (`SessionRecord`) and
    `schemas/v2.py` (additive `session_type`), `services/session_store.py`
    (Postgres DDL + mappers + backfill), the session-create handler (set
    `session_type`; the development dual-gate), the declare-target route (flip
    `session_type` — the single writer), and the `session:list` filter.
  - `products/platform-gateway` — `schemas/api.py` (the `extra="forbid"`
    session mirror gains `session_type`) and the session create/list/
    declare-target pass-through routes (dual-gate composition + filter
    forwarding).
- samples / shared touched: `shared/shared-contracts/schemas/` (the session
  schema gains the additive `session_type` enum); optionally a `samples/`
  walkthrough showing the Chat/Studio split. **No** `policy-default.yaml`
  action change and **no** `audit-event.schema.json` change under the R-6
  recommendation (OQ-1 could add one action).
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

Unresolved points that block `approved` status; must be empty before approval.
Each carries a recommendation so the decision stays auditable.

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
- **OQ-2 (legacy backfill):** what `session_type` do pre-existing sessions get?
  Options: default every legacy session to `operation`, or **infer**
  `development` for a session that already holds a declared authoring-trace
  target and `operation` otherwise. Recommendation: **infer** — a legacy
  session with a declared target is development work already, and defaulting
  it to `operation` would mis-file it into the shift-summary picker this spec
  exists to protect. The inference is a one-time migration.
- **OQ-3 ("Move to Studio" mechanics):** does promotion need a new endpoint?
  Options: extend the existing declare-target route to also flip
  `session_type` (single writer), or add a dedicated promotion endpoint.
  Recommendation: **extend the declare-target route** — it is already
  `session:skill_graduate`-gated and already the moment a target is named, so
  making it the sole post-birth writer of `session_type` keeps one writer and
  no new surface. The portal "Move to Studio" button calls it.
- **OQ-4 (per-entry list scoping):** should Chat and Studio each list only
  their own `session_type`, or should Studio list all sessions? Recommendation:
  **scope each entry to its own type** (an additive `session_type` filter on
  `session:list`) — that is what makes "Move to Studio" read as a re-home, and
  it keeps the two mental models separate. Ownership scoping is unchanged.
- **OQ-5 (audit of the type flip):** does a `session_type` promotion warrant an
  audit event? Options: emit one, or ride the existing deliberately-unaudited
  declare-target posture. Recommendation: **ride the existing posture** — no
  new audit event type. SPEC-055 established that declaring a target is a
  scope, not an operational act (the declare-target route is unaudited at the
  gateway and `session_created` records only a boolean
  `skill_target_declared`); a promotion is the same kind of scope change, and
  the graduation it enables is already audited as `skill_graduated`.

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
