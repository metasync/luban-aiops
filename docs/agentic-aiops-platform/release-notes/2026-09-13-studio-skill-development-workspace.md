# Studio — A Dedicated Skill-Development Workspace (v0.37.0)

Date: 2026-09-13

A release train delivering SPEC-056, the eighteenth R5 slice, drafted memo-free
out of the 2026-09-08→12 operator design discussion (the SPEC-045/046/049
precedent). It splits the operator-portal's one **Chat** entry into two —
**Chat** for *operation* sessions and a new **Studio** for *development*
sessions — over **one shared chat core** parameterized by a `mode`, backed by an
additive `session_type` discriminator on the session contract that is **fixed at
birth and immutable**. The split closes a live defect (the shift-summary picker
listed every session the caller owned, so skill-authoring work could be
mis-filed into an operational handover) and re-homes SPEC-055's authoring
controls. Shared contracts, agent-platform, platform-gateway and the portal are
touched; the other six products move on version lockstep only. **No** new policy
action, **no** policy-bundle change, **no** new audit event type, **no** new
configuration knob, and **no** `samples/` demo. The stream contract stays at v11
and Skill at v2.

## SPEC-056: Studio — a dedicated skill-development workspace

### R-1 — an additive `session_type` discriminator, fixed at birth

- An optional `session_type` enum (`operation | development`, default
  `operation`) is added to **both** authoritative session contracts —
  `agent-session.schema.json` and `agent-session-list.schema.json` — and to
  every mirror in the same change: the agent-platform `SessionRecord` and its
  three store backends, the agent v2 API models, the platform-gateway
  `SessionRecord`/`CreateSessionRequest`, and the portal's `SessionSummary` /
  `SessionDetail`. A create body that omits the field behaves exactly as it did
  before, so no existing caller breaks.
- The legacy `session.schema.json` is deliberately **untouched**. It is the
  unbound v1 surface; widening it would have implied a v1 behaviour change that
  nothing asked for.
- Both Python sides declare the vocabulary once as a named `SessionType` alias
  rather than as three inline `Literal`s (the audit-service `EventType`
  precedent), so a drift guard has exactly one symbol to read per side.
- **A new enum-value parity drift guard.** The property-set-equality assertions
  both contract suites already carried catch a *missing* field but not a
  *diverged vocabulary* — one side could add a third value and every existing
  test would stay green. Each suite now reads the enum out of the schema and
  compares it to the values its models accept, and a companion test proves the
  guard **fires** by re-validating a doctored schema against a narrowed model.
  This is the same class of gap that once let a new audit `event_type` reach
  ingest unaccepted.
- **Immutability has no API surface.** `session_type` is written exactly once,
  on the create path; the `SessionStore` protocol exposes **no setter** for it.
  In the Postgres upsert, `session_type = EXCLUDED.session_type` sits in the
  *expired-reclaim* branch only — reclaiming a dead row is a fresh creation, so
  it takes the new caller's type — and the live-row `WHERE` idle-TTL guard makes
  the whole `DO UPDATE` a no-op, which is the immutability boundary. An
  idempotent re-create of a named session returns the **stored** birth type,
  never the requested one.
- **Decoupled from `skill_target`, never inferred.** The SPEC-055 declare-target
  route — the one place an operator re-scopes a live session — writes the
  authoring-trace target row and never this field, so declaring a target on an
  operation session cannot make it a development one. Inferring the type from a
  declaration would re-couple a birth property to an inert field, and would also
  have made the OQ-2 backfill ambiguous.

### R-2 — each entry lists only its own scope

- An optional `session_type` query parameter on the agent v2 list route is
  forwarded verbatim by the gateway and applied **in the SQL `WHERE` clause** as
  a NULL-tolerant predicate (`%(session_type)s::text IS NULL OR
  COALESCE(session_type, 'operation') = …`). An omitted filter is byte-for-byte
  the legacy query; a supplied one narrows **server-side**, which is the whole
  point — a client cannot coerce the list into surfacing the other type.
  Ownership scoping and the 50-row cap are unchanged, so the anti-enumeration
  posture holds.
- `ViewId` gains `studio`, rendered beside **Chat** for `platform-admin`,
  `approver` and `operator`, and hidden from `developer`, `read-only-observer`
  and `auditor`. **Chat** itself is unchanged for every signed-in role.
- `STUDIO_ROLES` is defined *equal to* the existing `SKILL_GRADUATE_ROLES`
  rather than as a re-typed literal, so the client nav gate and the gateway's
  dual-gate set cannot drift apart.
- App owns **two** `useSessionWorkspace` instances — `operation` and
  `development` — and the development instance's polling is gated on
  `STUDIO_ROLES`, so a non-authoring role never issues a development list
  request at all. Incidents, Documents and Settings all stay on the operation
  workspace, and the synthetic pinned incident-triage entry is typed
  `operation`.
- The active-session pointer is **namespaced per mode**
  (`…activeSessionId.operation` / `.development`), so each entry restores its
  own last-open session across reloads and a detour from Studio into Chat and
  back loses neither place.

### R-3 — the authoring controls move to their right homes (Design B)

- An `operation` session shows **Draft as skill** and neither Declare-target nor
  Graduate; a `development` session shows **Declare target** + **Graduate as
  skill** and not Draft.
- There is **no** "Move to Studio" and no conversion in either direction, in the
  UI or in the store. An operational session's steps were approved as incident
  remediation across whatever targets the incident happened to touch, so
  graduating it as a single-target replayable flow would always be refused —
  a conversion button would be a button that always fails.
- The develop-as-you-go opener leaves Chat's session panel entirely and becomes
  Studio's, and its dialog's target is now **optional** (per R-2's "may name a
  `skill_target` at birth"): open the session unscoped and use **Declare target**
  later, and graduation reports that declaration as *fitted to the trace* rather
  than as the scope the session acted under. The dialog's OK button is no longer
  disabled on an empty target.

### R-4 — the shift-summary picker is scoped, and the create path refuses

- The Documents shift-summary picker receives the **operation-scoped**
  workspace, so its options are the server-scoped list rather than a client
  filter of an unscoped one. A test asserts the picker never calls
  `listSessions` itself — the scoping is the workspace's, not the dialog's.
- **A list filter alone leaves the create path open**, so `shift_summary.build_digest`
  now raises a new structural `DevelopmentSessionRejected` when a coverage list
  names a `development` session, which `create_document` maps to a **400** naming
  the offending ids — the same posture as the existing `UnknownSessionError` /
  `ForeignSessionDenied` rejections. It is checked **after** the foreign gate (so
  a session the caller cannot view is denied as foreign first, and its type never
  leaks) and **before** any fact is read (so a request about to be rejected reads
  nothing). Rejected whole rather than silently dropped, which would hide a
  caller mistake.
- Shift summary only: the incident-report path anchors to an `incident_id`, never
  takes `session_ids`, and is untouched. The comparison is an explicit
  `== "development"`, so a legacy NULL row reading back `operation` is never
  falsely rejected.
- This create-path guard is a small, explicit in-scope expansion beyond R-4's
  literal list-query wording, surfaced and approved at plan review (plan §9)
  rather than silently absorbed at delivery.

### R-5 — one shared security-critical core

- Studio is **not** a second chat surface. `ChatView` gains a `mode` prop that
  selects exactly three things: which authoring controls are visible, the birth
  `session_type`, and the list scope — and the last two are properties of the
  workspace instance App hands in, not of anything the component computes.
- `mode` is deliberately **not** threaded into the SSE stream adapter, the
  secret-masking renderer, the change-request projection, or the HITL
  confirmation path, so there is no code path on which the two entries could
  disagree about what an operator is approving. This is the blast-radius control
  on the whole spec: the surface where a credential is masked and a mutation is
  gated is one surface.
- The regression guard is non-vacuous by construction. A fixed transcript — a
  markdown reply, a `tool_call`/`tool_result` pair, and a pending change-request
  card carrying a masked secret — is rendered in **both** modes and the
  transcript surface's `innerHTML` is compared **byte-for-byte**, while a
  companion test asserts the session header *does* differ. A fork of the trust
  path fails the suite; a fork of nothing fails the companion.

### R-6 — the development-session dual-gate, with zero new policy vocabulary

- The gateway's `create_session_route` still enforces `session:create` on every
  request and **additionally** enforces the existing `session:skill_graduate`
  when the body's `session_type` is `development` — the SPEC-043/045 route-level
  dual-gate precedent. The gate lives at the gateway because that is the only
  place holding roles: the agent v2 API sees an `X-User-ID` and nothing else.
- A non-authoring role holds `session:create` but not `session:skill_graduate`,
  so it can no longer open a dead-end Studio session it could never graduate.
- This reuses existing vocabulary end to end: **no** new policy action, **no**
  `policy-default.yaml` / `policy-scenarios.yaml` change, **no** bundle
  content-hash bump, **no** new audit event type. `make policy-diff` reports
  **zero** outcome transitions across all 138 (role, action) pairs, and the
  canonical and candidate bundles hash identically
  (`sha256 ee1f6c5f11f73892e10738ff2d1c0678a76ab463af6e8b9541c51bd89476102b`).
  A test pins the action set and the role→action mapping so a future change
  cannot add a grant silently.
- The birth type rides the existing `session_created` log line as a
  discriminator — never a secret, so it is logged in full, unlike
  `skill_target`, which stays a boolean flag.

### R-7 — delivery traceability without a sample

- Every R-1…R-6 acceptance criterion maps to at least one asserting test in
  `tasks.md`, per ADR-0008.
- **No `samples/` demo ships**, by operator decision at plan review. The split
  adds no new backend capability and no new trust path, so nothing would be
  otherwise-unexercised: it is fully covered by the vitest nav / control /
  shared-core suite, the agent and gateway pytest (dual-gate, list filter,
  create-path guard, backfill, immutability, enum parity), the real-Postgres
  OQ-2 check below, and the Delivery-Gate browser live check. ADR-0008 rule 2
  therefore does not bind. (A Chat/Studio sample shipping no `skill/` directory
  would also have been invisible to `deploy-samples.sh`'s
  `find -type d -name skill` discovery — the SPEC-055 wrinkle.)
- The operator documentation lands in `docs/guides/portal-user-guide.md`: a new
  `## Studio` section beside `## Chat` carrying the Chat-vs-Studio mental model
  as a table (session type, session list, create affordance, session-header
  actions, whether it feeds a shift summary), plus the nav update, the
  `## Sessions` server-side-scoping note, the Draft-as-skill bullet scoped to
  Chat, a "Studio sessions are never shift material" bullet under Documents, and
  a **Studio** column in the "What your roles unlock" table.

## OQ-2: classifying the rows that already exist — and a gate finding

- Postgres-only, additive and nullable:
  `ALTER TABLE sessions ADD COLUMN IF NOT EXISTS session_type TEXT`, followed by
  an inference that classifies every legacy row exactly once. A session that
  already holds a declared `authoring_trace_target` row becomes `development` —
  defaulting it to `operation` would mis-file real authoring work into the very
  picker R-4 exists to protect — and everything else becomes `operation`.
- The default lives on the Pydantic model, not on the column, which is what
  leaves legacy rows NULL long enough to be inferred. The inference is
  **NULL-keyed**, so a re-run finds no row to touch. Memory and Redis are
  ephemeral and need no migration; both Postgres row mappers read
  `session_type or "operation"` defensively.
- **The gate found the `to_regclass` guard was decorative.** As first written,
  the guard was a predicate in the inference's own `WHERE` clause:
  `… WHERE session_type IS NULL AND to_regclass('authoring_trace_target') IS NOT
  NULL AND session_id IN (SELECT … FROM authoring_trace_target)`. PostgreSQL
  resolves the relation inside that `IN (SELECT …)` subquery at
  **parse-analysis time**, before any predicate is evaluated — so on a cluster
  whose SPEC-055 authoring-trace DDL had not run, the statement would abort the
  whole schema bootstrap with `relation "authoring_trace_target" does not exist`
  instead of skipping the inference. That is a hard pod-startup failure in
  precisely the situation the guard existed to make safe, and neither a fake
  driver (which never parses SQL) nor a text assertion on the DDL (which cannot
  tell a guard that *runs* from one that merely *appears in the string*) could
  see it. Only the real-server check did.
- **The fix** moves the inference into a PL/pgSQL `DO` block with dynamic
  `EXECUTE`, so the relation reference is resolved *inside* the `IF` rather than
  up front. The `operation` fallback stays a plain statement — it references no
  conditional relation and must still leave no row NULL when the inference is
  skipped. The unit test was rewritten from "the DDL mentions `to_regclass`" to
  a structural assertion: with `--` commentary stripped, the relation name
  appears **only** inside the deferred `EXECUTE` text and **never** in a static
  statement. It passes against the fixed DDL and fails against the pre-fix form.
- Exercised against a **real Postgres 16.14** (the dev-k8s `postgres-0` pod) via
  `.sqlcheck-spec056-oq2.sql`, which extracts the migration verbatim from
  `session_store._SESSIONS_DDL` rather than retyping it, and runs inside one
  transaction that rolls back. That database was genuinely in the pre-SPEC-056
  legacy shape (seven columns, no `session_type`), so the check ran against real
  legacy rows as well as synthetic fixtures:
  - the two **real** legacy rows classified correctly — the one with a declared
    target → `development`, the one without → `operation`;
  - both synthetic fixtures landed on their inferred branches;
  - `null_rows_remaining = 0`, every value inside the contract enum, and
    `misclassified = 0` against the declared-target predicate;
  - a second run was a no-op (`UPDATE 0`) and did **not** re-infer a row that had
    been hand-flipped to `operation`;
  - with `authoring_trace_target` invisible on the `search_path`, the `DO` block
    skipped cleanly and the fallback classified the row `operation` — no error;
  - after `ROLLBACK` the live database was unchanged (2 rows, no `session_type`
    column, no scratch schema).
- A companion check (`.workspaces/sqlcheck_spec056_driver.py`) drives the same
  DDL through the **production driver path** — one `psycopg` `cursor.execute()`
  of the whole multi-statement string, dollar-quoted `DO` block included —
  against the same server inside a rolled-back transaction, so the nested
  `$$`/`$q$` quoting is proven against the driver that actually runs it at pod
  start.

## Untouched / guarantees

No new policy action, no policy-bundle or content-hash change, no new audit
event type, no new configuration knob (`docs/guides/configuration-reference.md`
is verified unchanged, not edited). No new ADR: ADR-0009 stays `accepted`, since
Studio re-homes its declare-target and graduate controls with the behaviour and
trust model unchanged, and the ADR-0008 requirement-to-test gate is satisfied by
this delivery's task mapping. The SSE stream contract stays at **v11** and the
skill contract at **v2** — `session_type` is a session-record field, not a stream
frame. The secret-masking, change-request projection, HITL confirmation,
deviation-guard and SPEC-037 signed-execution paths are untouched and are
asserted identical across both modes. The Chat→Studio *spawn* bridge, the
composition / runbook-of-skills construct, and assisted trace-extraction stay
deferred to SPEC-057 on the exploration backlog behind a composition-trust-model
ADR plus a spike.

## Verification

Version lockstep **0.36.3 → 0.37.0** across `VERSION`, eight `pyproject.toml`,
eight `metadata.py`, two `__init__.py` literals and eight re-locked `uv.lock`
files; `make validate-version` reports `OK: all product and portal versions match
VERSION=0.37.0`.

`make verify` green (`VERIFY_EXIT=0`) at **2616** product tests — agent-platform
1304, audit-service 138, execution-runtime 73, identity-broker 60,
incident-service 137, platform-gateway 376, skills-hub 184, tool-gateway 344 —
plus four kustomize overlays, 18 policy rules, 137 api scenarios (90 granted
pairs covered), 19 tools scenarios (13 granted pairs covered), version lockstep,
and the three secret-vocabulary legs unchanged (20 substrings, 4 shape patterns,
the `<credential-reference>` marker).

Portal `npm test` green at **400** tests across **32** files (was 361/27 before
this slice) and `npm run build` clean (`tsc --noEmit` + vite). The new suites are
`chat/__tests__/ChatView.mode.test.tsx` (12 — the R-3 control split, the R-3
create-affordance split, and the R-5 both-modes-identical shared core),
`__tests__/App.studio.test.tsx` (23 — nav gating per role, the two mode-scoped
workspaces and gated development polling, the per-entry `mode` and workspace
wiring, the flush layout class), `sessions/__tests__/` (the `mode` scoping and
namespaced active-session key) and the R-4 picker scope in
`views/workspace/__tests__/DocumentsView.test.tsx`.

`make policy-diff` reports **zero** outcome transitions — 138/138 pairs
unchanged on both the api and tools engines, canonical and candidate bundles
hashing identically.

The OQ-2 backfill was exercised against a **real Postgres 16.14**, as detailed
above, and found and fixed a parse-time gap in the `to_regclass` guard that no
fake-driver test could reach.

A drive-by fix ships alongside: the new `ChatView` suite is the first test to
render the whole component, and the portal's zero-tolerance antd deprecation
guard (SPEC-042 R-2) failed the file on `Warning: [antd: Spin] tip is
deprecated`. Two pre-existing call sites — the app's startup spinner and the
transcript loader — now use `description`, which antd 6.6.2 documents as the
replacement. Rendering is unchanged; the guard had simply never been reached
before.
