# SPEC-056 Plan: Studio — A Dedicated Skill-Development Workspace

## Approach

SPEC-056 splits the portal's one **Chat** entry into two — **Chat** for
*operation* sessions and a new **Studio** for *development* sessions — over
**one shared chat core** parameterized by a `mode`, and backs the split with an
additive `session_type` discriminator on the session contract that is **fixed at
birth** and **immutable**. It re-homes authoring controls that already exist
(SPEC-044/045 draft, SPEC-055 declare-target + graduate) and closes a live
document-generation defect (the unfiltered shift-summary picker). It adds **no**
new capability, **no** new policy action, **no** new audit event type, and **no**
change to the graduation/replay trust model. The work groups into five moves that
each stay as close to existing machinery as possible:

1. **One additive discriminator, in lockstep** (R-1) — a `session_type` enum
   (`operation | development`, default `operation`) added to the session contract
   and *every* mirror at once: the two live `agent-session*` JSON schemas, the
   agent-platform Pydantic models and Postgres DDL/mappers, the platform-gateway
   `extra="forbid"` mirror, and the portal TS interfaces. The existing drift
   guards (gateway property-set equality, agent-platform instance validation
   against `additionalProperties:false`) already make a one-sided edit fail
   `make verify`; an explicit enum-value parity assertion closes the vocabulary
   gap the property-name guard cannot see.
2. **Fixed at birth, never inferred, never mutated** (R-1) — `session_type` is an
   explicit field on the create body, written exactly once by the store's create
   path. It is **decoupled from `skill_target`**: a development session may omit a
   target, and declaring one (at birth or mid-session) never sets the type. No
   store or service method mutates it afterwards, and the SPEC-055 declare-target
   route is untouched — it names a scope, it does not write a type.
3. **Two entries, one core** (R-2, R-5) — `App.tsx` gains a `studio` `ViewId` and
   a `STUDIO_ROLES`-gated nav item; **one** `ChatView` renders both,
   `mode`-parameterized. `mode` selects exactly three things — the visible
   authoring controls, the `session_type` written at birth, and the list scope —
   and nothing in the trust path. The SSE stream adapter, the secret-masking /
   change-request projection, and the HITL confirmation-card path are shared and
   asserted identical across both modes by a regression test.
4. **Controls where they belong, no conversion** (R-3) — Chat (`operation`) keeps
   **Draft as skill** and loses the mid-session **Declare target** control; Studio
   (`development`) holds **Declare a target** and **Graduate as skill**. There is
   no "Move to Studio": an operation session's trace is inherently multi-origin,
   so a post-hoc single-target declaration would make graduation deterministically
   refuse (SPEC-055 R-4) — conversion is semantically unsound, not merely awkward.
   The ergonomic Chat→Studio *spawn* bridge is deferred to SPEC-057.
5. **Documents stop mis-filing development work** (R-4) — the shift-summary
   picker lists only `operation` sessions, enforced **server-side** on *both*
   doors — the scoped session-list query the picker consumes *and* a
   `session_type` guard on the shift-summary create path — not merely hidden in
   the client. Incident reports anchor to an `incident_id` (SPEC-043) and are
   unaffected.

Two invariants are load-bearing and pinned by test rather than by review:

- **`session_type` is a birth property, never a projection of later state.** The
  only writer is the store's create path; the Protocol exposes no setter, the
  service layer threads it once at creation, and the declare-target route (the one
  place SPEC-055 lets an operator re-scope a live session) writes the
  `authoring_trace_target` row and **never** the session's type. A test asserts no
  code path promotes, demotes, or converts a session's type post-birth.
- **The security-critical core is one implementation.** `mode` is a surface
  selector, not a fork. The stream/masking/HITL surface for a given transcript is
  byte-identical between modes; only the mode-specific controls differ. A
  divergence fails the suite (R-5 is the invariant, not an aspiration).

## Resolved At Plan Time

The spec's Impact section delegated several concrete shapes to this plan ("the
`session_type` transport", "no stream-schema bump … confirmed at `plan.md`", the
backfill mechanics, the per-entry list scoping). The pre-implementation code read
resolved each, and surfaced two disambiguations the spec's prose left implicit.

### 1. The live session contracts are the `agent-session*` pair, not `session.schema.json`

The repository holds **three** session-shaped schemas. The authoritative live
contracts are `shared/shared-contracts/schemas/agent-session.schema.json`
(session detail, v2, `additionalProperties:false`, `status` enum
`["active","expired"]`) and `agent-session-list.schema.json` (the list envelope,
v2). These are what the gateway `SessionRecord` docstring names as its mirror,
what `test_contracts.py` binds by property-set equality, and what
`test_contract_adapter.py` / `test_session_workspace.py` validate real responses
against. The minimal `session.schema.json` (25 lines, `status` enum
`["active","closed"]`) is **legacy and unbound**: no loader references it, no
parity test binds it, and its `status` vocabulary already diverges from every
live model — so it is *not* a mirror of anything shipped.

**Resolution:** `session_type` lands on `agent-session.schema.json` (detail) and
`agent-session-list.schema.json` (list row) only. The dead `session.schema.json`
is **not** touched — editing an unbound schema would imply a liveness that does
not exist and invite a future reader to sync a fourth surface. **No stream-schema
bump** (`agent-stream-event.schema.json`): `session_type` rides the session
record, never a stream frame — confirmed here as the spec's Impact anticipated.

### 2. The drift guard: existing property/instance guards plus one enum-parity assertion

Lockstep is already mechanically enforced in two directions:

- The gateway's `test_model_properties_match_contract_properties` asserts
  `set(SessionRecord.model_json_schema()["properties"]) ==
  set(agent-session.schema.json["properties"])` — **property-set equality**, so
  adding `session_type` to the schema *forces* it onto the gateway mirror or the
  suite fails.
- The agent-platform validates real responses with `jsonschema.validate(...)`
  against both schemas, whose `additionalProperties:false` *forces* `session_type`
  into the schema the moment an `AgentSession`/`AgentSessionSummary` emits it.

What neither sees is **enum vocabulary drift** — the recalled lesson from the
audit `event_type` and model-catalog `provider` incidents, where a property-name
parity test passed while a new enum value was rejected at runtime.

**Resolution:** add one explicit assertion that the `session_type` enum value-set
in each schema equals the `Literal["operation","development"]` args of every
consuming Pydantic model (gateway `SessionRecord`, agent-platform
`AgentSession`/`AgentSessionSummary`/`AgentSessionCreateRequest`), following the
audit-service `test_model_enum_values_match_contract` precedent. The portal's TS
union is guarded behaviorally (a `development` session routes to Studio, an
`operation` one to Chat), not by a runtime enum check — TS unions are not
inspectable at runtime, and the vitest convention is behavioral.

### 3. `session_type` transport at create: explicit, and decoupled from `skill_target`

SPEC-055's create body already carries an optional inert `skill_target`. The
naive shape — infer `development` from a present `skill_target` — is rejected:
R-1 requires the type be *written once at creation and never inferred from ambient
state*, and R-2 lets a Studio session name a target *optionally* (a development
session with no target yet is legitimate; the operator declares it mid-session in
Studio). Inferring from `skill_target` would also re-couple the type to the very
declaration whose inertness SPEC-055 established.

**Resolution:** an explicit additive `session_type: Literal["operation",
"development"] = "operation"` on `AgentSessionCreateRequest` (agent) and the
gateway `CreateSessionRequest` (which is `extra="forbid"`, so the field must be
declared there to be relayed). The portal sends it per entry: Chat →
`operation`, Studio → `development`. `skill_target` stays orthogonal and inert.
The gateway forwards `session_type` in the upstream create body (omitting it for
the `operation` default preserves the historical no-body shape for the common
Chat case, exactly as `skill_target` is omitted when absent).

### 4. The dual-gate lives at the gateway, the policy boundary (R-6 / OQ-1)

The agent-platform v2 API holds **no role information** (identity is `X-User-ID`;
roles are resolved and enforced at the gateway). Every policy decision in the
platform is the gateway's, so the development-session dual-gate cannot live in the
agent layer.

**Resolution:** in the gateway `create_session_route`, always
`enforce_policy(ACTION_SESSION_CREATE)`; **additionally** `enforce_policy(
ACTION_SESSION_SKILL_GRADUATE)` when `body.session_type == "development"` — the
SPEC-043/045 `documents:create`+`incident:read` route-level dual-gate precedent.
This uses the **existing** `session:skill_graduate` action: **no** new policy
action, **no** `policy-default.yaml` change, **no** bundle content-hash bump, and
**no** new `policy-scenarios.yaml` row (SPEC-055 already covers
`session:skill_graduate` for every role). `make policy-diff` must report **zero**
new grants — that is the assertion this decision leaves behind. The agent layer's
SPEC-055 create docstring ("deliberately not dual-gated") is updated: the
*skill_target declaration* stays inert and un-dual-gated, but *opening a
`development` session* is now gated at the boundary beside it. A non-authoring role
(`developer`, `read-only-observer`, `auditor`) holds `session:create` but not
`session:skill_graduate`, so it can no longer open a dead-end development session
— the tightening R-6 names.

### 5. Legacy backfill: Postgres-only, nullable additive column, idempotent inference (R-1 / OQ-2)

Only the Postgres backend holds durable legacy rows; the in-memory and Redis
backends are ephemeral (a restart is a clean slate), so they need no migration —
their `SessionRecord` Pydantic default (`operation`) is the whole story. The
inference source is the SPEC-055 `authoring_trace_target` table (`session_id`
PRIMARY KEY, one row per session that ever declared a target), which shares the
SPEC-016 `sessions` database, so the join is intra-database.

**Resolution:** follow the house additive-column convention (`title`,
`last_active_at`, `model` are all nullable `ALTER TABLE … ADD COLUMN IF NOT
EXISTS` with the default carried by the Pydantic model, not the DB):

```sql
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS session_type TEXT;
-- OQ-2: infer development for a session already holding a declared
-- authoring-trace target, operation otherwise. Idempotent (NULL rows only),
-- and guarded so it is safe if the trace table is not present yet.
UPDATE sessions SET session_type = 'development'
 WHERE session_type IS NULL
   AND to_regclass('authoring_trace_target') IS NOT NULL
   AND session_id IN (SELECT session_id FROM authoring_trace_target);
UPDATE sessions SET session_type = 'operation' WHERE session_type IS NULL;
```

Nullable-then-backfill (rather than `NOT NULL DEFAULT 'operation'`) is what keeps
the inference **idempotent**: after the `ALTER`, legacy rows are `NULL`, the two
`UPDATE`s classify every one, and a re-run finds no `NULL` rows to touch. New rows
are never `NULL` — the `INSERT` sets `session_type` explicitly — and a defensive
`row[N] or "operation"` in the mapper means a `NULL` read (which cannot occur
post-migration) still degrades to `operation` rather than erroring. The
`to_regclass` guard plus a startup ordering note (the session-store backfill runs
after the authoring-trace DDL) make the join safe regardless of which store
initializes first. R-1's "never leaves a session with a null `session_type`" holds
for every row the migration can see.

### 6. The `INSERT … ON CONFLICT` reclaim sets the type; a live row never changes it

The Postgres `_INSERT_SESSION` reclaims a conflicting row **only** when its idle
TTL has lapsed (`WHERE sessions.last_accessed_at <= now() - ttl`); against a
**live** conflicting row the `DO UPDATE` is a no-op. This is exactly the
immutability boundary: reclaiming an expired row is a *fresh creation* (the old
session is gone), so `session_type = EXCLUDED.session_type` belongs in the `DO
UPDATE SET`; a live named session (SPEC-015 R-3 idempotent re-triage) keeps its
birth type because the `WHERE` guard makes the update a no-op. `create_named_
session`'s post-create re-read stays authoritative for the foreign-owner 404.

### 7. Workspace instantiation: App owns two scoped instances, one per mode

`useSessionWorkspace` is instantiated **once** in `App.tsx` today and shared by
ChatView, IncidentsView, DocumentsView, and SettingsView; it lists *all* sessions
(`listSessions()`, unfiltered) and holds a single `activeSessionId` persisted under
one sessionStorage key. One instance cannot serve two differently-scoped entries.

**Resolution:** the hook gains a `mode: "operation" | "development"` parameter
(default `operation`) that (a) scopes `listSessions(signal, mode)` →
`GET /api/v1/sessions?session_type=<mode>`, (b) makes `createAndOpen` /
`createDevelopmentSession` write `session_type=<mode>`, and (c) **namespaces the
active-session key** (`luban.portal.activeSessionId.<mode>`) so Chat and Studio
never fight over the active pointer. `App` owns **two** instances:
`operationWorkspace` (Chat, and reused by Incidents/Documents/Settings — all of
which deal in operation sessions) and `developmentWorkspace` (Studio). The
development instance's polling is gated on `authenticated &&
hasAnyRole(roles, STUDIO_ROLES)`, so a non-Studio role never polls a list it could
never populate. Cost: two 30s pollers for a Studio role, one for everyone else —
accepted, and bounded by the same cap the single poller already had.

Rejected: one workspace holding both lists and partitioning client-side — that
would violate R-4's server-side-scoping requirement (the picker must not be
coercible into *listing* a development session) and duplicate the active-session
state machine. Rejected: a mode-switchable single list — the active view would
have to drive a refetch on every nav, thrashing the poll cadence.

### 8. Create-affordance and control split follow the mode (R-3)

The `SessionPanel` shows two create buttons today ("New" one-click + "Skill"
develop-as-you-go target-at-birth dialog). Post-split, the create affordances are
mode-dependent:

- **Chat (`operation`):** only "New" — a one-click `operation` session. The
  develop-as-you-go "Skill" opener is **removed from Chat** (a development session
  is born in Studio, never converted from Chat — R-3).
- **Studio (`development`):** the create path opens the target-at-birth dialog
  (target **optional**, per R-2), writing `session_type=development`. The SPEC-055
  dialog is reused verbatim; only its home moves.

The open-session header controls render by mode: `operation` → `DraftAsSkillButton`
only; `development` → `DeclareSkillTargetButton` + `GraduateAsSkillButton`. The
mid-session **Declare target** control is thereby removed from Chat (R-3) with no
change to its route (still `session:skill_graduate`, still first-declaration-wins,
still deliberately unaudited). The develop-as-you-go dialog's `createDevelopment
Session` already exists; it gains the explicit `session_type=development`.

### 9. R-4 enforcement is the scoped list query **plus** a create-path type-check

DocumentsView's shift-summary picker (`views/workspace/DocumentsView.tsx`, the
"Pick sessions from your workspace" `Select`) sources its options from
`workspace.sessions`. Passing DocumentsView the **operation-scoped** workspace
means the picker lists only operation sessions, and because that scope comes from
`GET /api/v1/sessions?session_type=operation` it is enforced **server-side** —
exactly R-4's "cannot be coerced into listing a development session".

**Resolution (revised at plan review — the create path is now guarded too):** the
list scoping above is R-4's primary mechanism, but it is not the only door into a
shift summary. `POST /api/v1/documents` (`document_type: "shift_summary"`) takes a
caller-supplied `session_ids` list, and `services/shift_summary.py`'s
`build_digest` re-checks each id for **existence** (a nonexistent id →
`UnknownSessionError` → a structural **400** that reveals nothing about ownership)
and **ownership / capability** (a foreign session → `ForeignSessionDenied` → **403**
unless the caller holds `approvals:list`, which admits it at a metadata-only tier) —
but **not** for `session_type`. So a hand-crafted create naming a `development`
session the caller owns (or covers) would be digested as operational handover
material: the very mis-filing R-4's Motivation calls wrong, reachable around the
picker. R-4's letter scopes the *list query*, but its stated requirement —
"operational document generation stops treating development sessions as
operational material" — is served by rejecting at the create path too, and the same
"server-side, not only hidden in the client" logic that forces the list scope
argues for it. **Decision (operator-approved at plan review):** `build_digest`
gains a `session_type` guard — a `development` id in a shift-summary coverage list
is **rejected** (a new structural error mapped to a 4xx beside the existing unknown
/ foreign mappings, matching their "reject before reading any fact" posture), never
silently dropped. It is **shift_summary-only**: the incident-report path
(`incident_report.py`'s `_session_section`) derives coverage from the incident's
linked session, never takes `session_ids`, and is untouched (R-4). A legacy
`NULL`-type row reads back `operation` (the stage-2 mapper default), so the guard
never falsely rejects pre-SPEC-056 work. This is a small, explicit in-scope
expansion beyond R-4's literal list-query wording — surfaced and approved here
rather than silently absorbed at delivery (the SPEC-054 §4 discipline the original
deferral cited).

## Design Per Requirement

### R-1: An additive `session_type` discriminator, fixed at birth and immutable

- affected files: `shared/shared-contracts/schemas/agent-session.schema.json` +
  `agent-session-list.schema.json` (additive `session_type` enum, default
  `operation`); agent-platform `schemas/api.py` (`SessionRecord`), `schemas/v2.py`
  (`AgentSession`, `AgentSessionSummary`, `AgentSessionCreateRequest`),
  `services/session_store.py` (Protocol + all three backends' `create_session`,
  the `_SESSIONS_DDL` CREATE + idempotent ALTER + OQ-2 backfill, `_INSERT_SESSION`
  / `_GET_SESSION` / `_LIST_USER_SESSIONS` column lists, the two row mappers, and
  an optional `session_type` filter on `list_sessions_by_user`),
  `services/session_service.py` (`create_session` / `create_named_session` /
  `ensure_session` / `list_sessions` thread the type); platform-gateway
  `schemas/api.py` (`SessionRecord` mirror + `CreateSessionRequest`); portal
  `api/sessions.ts` (`SessionSummary` + `SessionDetail` + `createSession` +
  `listSessions`).
- chosen approach: one explicit enum written once by the store's create path;
  default `operation` carried by the Pydantic model; decoupled from `skill_target`
  (Resolved §3); nullable additive Postgres column + idempotent inference backfill
  (Resolved §5); reclaim-sets/live-preserves (Resolved §6); no setter anywhere, and
  the declare-target route never writes it. Lockstep is enforced by the existing
  property-set-equality + instance-validation guards plus one new enum-parity
  assertion (Resolved §2).
- alternatives rejected: inferring `development` from `skill_target` presence —
  rejected (Resolved §3): it re-couples the type to an inert field and violates
  "never inferred from ambient state". A `NOT NULL DEFAULT 'operation'` column —
  rejected (Resolved §5): it destroys the `IS NULL` idempotency handle the
  inference needs. Touching the legacy `session.schema.json` — rejected (Resolved
  §1): it is unbound. A runtime promotion path — rejected (R-1 immutability; the
  Chat→Studio bridge is a SPEC-057 *spawn*).

### R-2: Studio as a distinct, role-gated entry over one shared core

- affected files: portal `App.tsx` (`ViewId` union + a `STUDIO_ROLES`-gated
  **Studio** nav item + the second workspace instance + `<ChatView mode=…>` for
  both entries + the flush-content className for `studio`), `roles.ts`
  (`STUDIO_ROLES`), `chat/ChatView.tsx` (`mode` prop), `sessions/
  useSessionWorkspace.ts` (`mode` param, per-mode list scoping + namespaced active
  id), `api/sessions.ts` (the `session_type` list filter + create body);
  platform-gateway `api/routes/sessions.py` (`list_sessions_route` gains a
  `session_type` query param) + `services/gateway_service.py` + `services/
  agent_client.py` (forward the filter); agent-platform `api/v2/routes.py`
  (`list_sessions_route` filter, `create_session` sets the type).
- chosen approach: `STUDIO_ROLES` = `{platform-admin, approver, operator}` — the
  exact set that already holds `session:skill_graduate` (defined equal to
  `SKILL_GRADUATE_ROLES`, so the two cannot drift); Chat's gating unchanged
  (broad); one `ChatView`, `mode`-parameterized; each entry lists its own type via
  an additive, ownership-preserving `session_type` filter (anti-enumeration
  unchanged). Two scoped workspace instances (Resolved §7).
- alternatives rejected: a second chat implementation — rejected (R-5, Non-Goal).
  Studio listing all sessions — rejected (OQ-3): it blurs the two mental models the
  split exists to separate. Narrowing Chat's gating — rejected (R-2: only Studio is
  narrowed). A client-only list partition — rejected (Resolved §7): it violates
  R-4's server-side scoping.

### R-3: Control placement split, no in-place conversion

- affected files: portal `chat/ChatView.tsx` (render `DraftAsSkillButton` in
  `operation` only; `DeclareSkillTargetButton` + `GraduateAsSkillButton` in
  `development` only; remove the develop-as-you-go "Skill" opener from Chat's
  `SessionPanel`; no conversion control). No backend route change — the
  declare-target and graduate routes are unchanged from SPEC-055.
- chosen approach: `mode` selects the visible controls (Resolved §8); draft stays
  the operation artifact (read-only grounded guidance, multi-target-friendly);
  declare-target + graduate are the development artifacts (single-target
  replayable flow). No "Move to Studio" — an operation session's multi-origin trace
  would make graduation deterministically refuse (SPEC-055 R-4).
- alternatives rejected: an in-place conversion — rejected (R-1 immutability +
  R-3 trust invariant: conversion is semantically unsound). Keeping declare-target
  in Chat — rejected (R-3: it is the mid-session path that turns an operation
  session into a development one, which the split exists to prevent). The
  Chat→Studio *spawn* bridge / composition / assisted trace-extraction — deferred to
  SPEC-057 (Non-Goal).

### R-4: Document generation filters by `session_type`

- affected files: portal `views/workspace/DocumentsView.tsx` (receives the
  operation-scoped workspace, so the shift-summary picker lists operation
  sessions); agent-platform `services/session_store.py` + `api/v2/routes.py` (the
  server-side `session_type` list filter that scopes the picker's source query),
  and `services/shift_summary.py` (`build_digest`) + the `api/v2/routes.py`
  `create_document` handler (the create-path `session_type` guard). No change to
  the incident-report path or any other document type.
- chosen approach: server-side scoping on **both** doors into a shift summary —
  the list query the picker consumes (the same additive `session_type` filter R-2
  uses) and the `documents:create` path (`build_digest` rejects a `development`
  id, mapped to a structural 4xx), so the picker consumes a scoped list *and* the
  API cannot be hand-crafted around it (Resolved §9). Incident reports anchor to
  `incident_id` (SPEC-043) and are untouched.
- alternatives rejected: a client-only filter of an unscoped list — rejected (R-4:
  "not only hidden in the client"). Leaving the create path unguarded — rejected at
  plan review (Resolved §9): a hand-crafted `session_ids` list mis-files a
  development session around the picker. **Silently dropping** a development id
  from coverage — rejected in favour of an explicit reject: dropping hides a caller
  mistake, while the reject matches the existing `UnknownSessionError` /
  `ForeignSessionDenied` posture.

### R-5: Shared-core invariant (blast-radius control)

- affected files: no production fork. `chat/ChatView.tsx` keeps one
  `useChatStream` adapter, one secret-masking / change-request projection
  (SPEC-054 R-3 / SPEC-055 R-7), and one HITL confirmation-card path; `mode`
  branches only the control set, the birth `session_type`, and the list scope. One
  new vitest regression asserts both modes render the same core.
- chosen approach: `mode` is a surface selector; the trust path never reads it. A
  test renders a fixed transcript through both modes and asserts an identical
  stream/masking/HITL surface, with only the mode-specific controls differing — a
  divergence fails the suite.
- alternatives rejected: any per-mode branch in the stream/masking/HITL code —
  rejected (R-5). A new executor, signing path, gateway deviation guard, origin
  allowlist, or auto-allow exclusion change — none (Non-Goal; graduation/replay keep
  their SPEC-055 guarantees verbatim).

### R-6: Authorization posture — Option A, no new policy vocabulary

- affected files: platform-gateway `api/routes/sessions.py` (the create-route
  dual-gate); `roles.ts` (`STUDIO_ROLES`); `docs/agentic-aiops-platform/
  authorization-matrix.md` (the Studio entry + the development-session create
  gate). **No** `policy-default.yaml`, **no** `policy-scenarios.yaml`, **no**
  `audit-event.schema.json` change.
- chosen approach: the route-level dual-gate on the existing
  `session:skill_graduate` (Resolved §4); the client nav gate is convenience, the
  gateway is the boundary; draft/declare-target/graduate keep their SPEC-044/045/055
  actions and events verbatim; there is no `session_type` mutation to audit (the
  field is immutable). `developer` is unchanged — kept, documented, denied Studio.
- alternatives rejected: a new dedicated action (`session:develop` /
  `studio:enter`) — rejected (OQ-1): a bundle version bump + scenarios + four
  byte-identical copies for no extra safety. No server gate — rejected (OQ-1): it
  leaves the mapping client-only and lets a developer open a dead-end development
  session.

### R-7: Delivery traceability per ADR-0008

- affected files: `docs/specs/SPEC-056-…/tasks.md` records ≥1 asserting test per
  R-1..R-6 acceptance criterion; **no** `samples/` walkthrough ships (see chosen
  approach); `docs/guides/portal-user-guide.md` gains the Chat/Studio operator
  section; `docs/specs/README.md` + `CONTRIBUTING.md` already carry the ADR-0008
  gate text (verify only).
- chosen approach: the acceptance-criteria → test mapping in the Delivery Gate is
  the traceability artifact. **No `samples/` walkthrough ships** (operator decision
  at plan review) — unlike SPEC-055's graduation demo, the split adds no new
  backend capability or trust path, so it is fully exercised by the vitest
  nav/control/shared-core suite, the agent + gateway pytest (dual-gate, list
  filter, create-path guard, backfill, immutability, parity), the real-Postgres
  OQ-2 check, and the delivery-gate browser live check; there is no
  otherwise-unexercised path a sample would prove, so ADR-0008 rule 2 does not
  bind. Operator-facing documentation of the Chat/Studio mental model lands instead
  as a **portal user-guide** section, the lighter and maintained home for it.

## Sequencing And Dependencies

1. **Contracts first** — `agent-session.schema.json` + `agent-session-list.schema
   .json` gain the additive `session_type` enum (default `operation`); the
   enum-parity drift-guard assertion lands with them. Everything validates against
   these, and the property-set-equality guard makes the gateway mirror edit
   non-optional from this point.
2. **agent-platform store + models** (R-1) — `SessionRecord` / `AgentSession` /
   `AgentSessionSummary` / `AgentSessionCreateRequest` gain `session_type`;
   `session_store.py` gains it on the Protocol + all three backends' create, the
   DDL (CREATE + nullable ALTER + OQ-2 backfill), the INSERT/GET/LIST column lists,
   the two mappers, and the optional list filter; `session_service.py` threads it.
   Depends on stage 1.
3. **agent-platform handlers** (R-1/R-2/R-4) — v2 `create_session` sets the type
   once; `list_sessions_route` accepts + applies the `session_type` filter;
   `read_session` / rename carry it on the `AgentSession`; `shift_summary.
   build_digest` rejects a `development` id for a shift summary and
   `create_document` maps it to a structural 4xx (the R-4 create-path guard).
   Depends on stage 2.
4. **platform-gateway** (R-1/R-2/R-6) — `SessionRecord` + `CreateSessionRequest`
   mirrors gain the field; `create_session_route` composes the dual-gate;
   `list_sessions_route` accepts the `session_type` query param; `gateway_service`
   + `agent_client` forward the body field and the query param. Depends on stage 1
   (mirror parity) and stage 3 (the upstream accepts the field + filter).
5. **portal contract + workspace** (R-1/R-2) — `api/sessions.ts` gains
   `session_type` on both interfaces and threads it through `createSession` /
   `listSessions`; `useSessionWorkspace` gains the `mode` param (per-mode list
   scoping, per-mode create, namespaced active-session key, `operation`-typed
   pinned entries). Depends on stage 4.
6. **portal nav + ChatView + DocumentsView** (R-2/R-3/R-4/R-5) — `App.tsx`
   (`ViewId` + `studio`, `STUDIO_ROLES`-gated nav, two workspace instances,
   `<ChatView mode=…>`); `roles.ts` (`STUDIO_ROLES`); `ChatView.tsx` (`mode`
   parameterization: control split, create-affordance split, shared core);
   `DocumentsView.tsx` (operation-scoped picker). Depends on stage 5.
7. **Tests per stage; living-state docs, the portal user-guide Chat/Studio
   section, CHANGELOG, version lockstep, and the release note on delivery.** No
   `samples/` demo ships (R-7). Depends on all. The OQ-2 backfill is verified
   against a real Postgres at the delivery gate (the SPEC-055 `.sqlcheck`
   precedent).

## Test Strategy

- **shared-contracts / cross-product (`pytest`)**
  - R-1: a session carrying `session_type` validates against both
    `agent-session.schema.json` and `agent-session-list.schema.json`; the
    enum-parity assertion proves the schema enum equals every consuming Pydantic
    `Literal` (the vocabulary-drift lesson); the gateway property-set-equality guard
    now includes `session_type` on both sides.
- **agent-platform (`pytest`)**
  - R-1: `session_type` round-trips on **all three** backends (memory, Redis,
    Postgres) and defaults to `operation`; create writes it exactly once; **no**
    store or service method mutates it post-create (the Protocol has no setter);
    the declare-target route writes the trace target and leaves `session_type`
    untouched (immutability).
  - R-1 (backfill): a legacy `NULL`-`session_type` row with an
    `authoring_trace_target` entry migrates to `development`, one without migrates
    to `operation`, no row is left `NULL`, and a second run is a no-op
    (idempotent); the `to_regclass` guard is safe when the trace table is absent.
  - R-2/R-4: `list_sessions_by_user` with `session_type="operation"` excludes
    development rows and vice-versa; an omitted filter returns all (backward
    compat); ownership scoping and the cap are unchanged.
  - R-4 (create path): `build_digest` rejects a `development` id in a shift-summary
    coverage list (a structural 4xx matching the unknown / foreign posture), accepts
    an all-`operation` set, leaves the incident-report path untouched, and accepts a
    legacy `NULL`-type row (mapper default `operation`).
  - R-1: v2 `create_session` with `session_type="development"` persists
    `development`; `read_session` and the list rows carry the type.
- **platform-gateway (`pytest`)**
  - R-6 (dual-gate): a `development` create is **denied (403)** to a role holding
    `session:create` but not `session:skill_graduate` (`developer`,
    `read-only-observer`, `auditor`) and **allowed** for `operator` / `approver` /
    `platform-admin`; an `operation` create needs only `session:create` for every
    role that holds it. The upstream body carries `session_type`.
  - R-2: `list_sessions_route` forwards the `session_type` query param upstream
    verbatim; `make policy-diff` reports **zero** new grants (no bundle change).
- **operator-portal (`vitest`)**
  - R-2: the **Studio** nav item renders for `STUDIO_ROLES` and is absent for
    `developer` / `read-only-observer` / `auditor`; **Chat** renders for every
    signed-in role (gating unchanged). `ViewId` includes `studio`.
  - R-3: `operation` mode renders **Draft as skill** and neither Declare-target nor
    Graduate; `development` mode renders **Declare a target** + **Graduate as
    skill** and not Draft; Chat's `SessionPanel` has no develop-as-you-go opener,
    Studio's does.
  - R-4: the DocumentsView shift-summary picker lists only `operation` sessions
    (a development session is never an option).
  - R-5 (shared core): a fixed transcript renders an **identical** stream /
    secret-masking / change-request / HITL-confirmation surface in both modes, with
    only the mode-specific controls differing — a divergence fails.
  - R-1/R-2: `useSessionWorkspace(mode)` scopes `listSessions` to
    `?session_type=<mode>`, namespaces the active-session key per mode, and
    `createDevelopmentSession` sends `session_type=development`; a pinned incident
    entry is typed `operation`.
- **integration** — `make verify` green (all products, overlays, policy rules +
  scenarios **unchanged**, version lockstep, the secret-vocabulary leg unchanged);
  the OQ-2 backfill exercised against a real Postgres 16 at the delivery gate; no
  `samples/` demo ships (R-7), so there is no sample script to exercise; the
  existing password-reset + graduation `demo.sh` legs stay green (the split must
  not regress the operation-session chat path they drive).

## Rollout And Migration

- **deployment/configuration changes:** **none new.** No policy action, no bundle
  content-hash change, no audit event type, and no new environment knob — the
  dual-gate reuses `session:skill_graduate`, and the backfill is code, not config.
  `docs/agentic-aiops-platform/authorization-matrix.md` gains the **Studio** entry
  and the development-session create gate (documenting that opening a `development`
  session requires `session:skill_graduate` beside `session:create`);
  `docs/guides/configuration-reference.md` is unchanged (no new knob).
- **backward compatibility:** additive and fail-safe throughout.
  - A create body without `session_type` yields an `operation` session, so an
    un-updated client (or the historical one-click path) behaves exactly as today.
  - The `session_type` list filter is optional; omitted returns all sessions
    (legacy behavior), so the endpoint is unchanged for a caller that does not send
    it.
  - Legacy Postgres rows are backfilled (development where a target was declared,
    operation otherwise); memory/Redis are ephemeral and need no migration. A
    defensive mapper default means a `NULL` read (impossible post-migration) still
    degrades to `operation`.
  - `session_type` is additive on both schemas with `additionalProperties:false`,
    so it ships in lockstep with the models (Resolved §2) and no stream frame
    changes. The platform deploys as one VERSION, so there is no mixed-version
    portal/backend hazard.
  - A shift-summary create naming a `development` session is now rejected (the R-4
    create-path guard, Resolved §9) — a tightening, not a regression: no client
    could name a `development` session before this release (the type did not
    exist), and a legacy session backfilled to `development` was development work
    R-4 exists to keep out of shift material.
- **data migration:** the idempotent Postgres `session_type` column add + OQ-2
  inference backfill (Resolved §5). No destructive down-migration.
- **rollback:** revert the delivery commit. The `session_type` column is harmless
  if left in place (unused by the rolled-back code), so no down-migration is
  required. Rolling back removes the Studio entry and the control split; Chat
  reverts to holding all three authoring controls (the SPEC-055 posture) and listing
  all sessions, and the shift-summary picker reverts to unfiltered. The backfilled
  `session_type` values are inert without the split.
- **version:** MINOR bump **0.36.3 → 0.37.0** at the delivery gate (a
  backward-compatible feature train, per the house "release trains map to MINOR
  bumps" convention and the spec's fixed R5 slice anchor), with `VERSION` + the
  per-product lockstep constants (`pyproject.toml`, `metadata.py`, the two
  `__init__.py` literals) + `uv.lock` re-locks. `make validate-version` must report
  OK across every product and the portal.
