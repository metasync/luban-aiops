# SPEC-055 Plan: Develop-As-You-Go Skill Graduation

## Approach

SPEC-055 is the graduation destination of the A→B→C program (ADR-0009): it turns
a session of individually-approved, already-signed mutations into a **replayable
executable-flow skill** a human reviews and merges, then replays under **one**
HITL gate with every write still signed, audited, receipted, and gateway-guarded.
It is the largest trust-surface change in the program (skills-hub,
agent-platform, tool-gateway, execution-runtime, operator-portal), so the work
groups into five moves that each stay as close to existing machinery as
possible:

1. **Capture what was already approved** (R-1, R-2) — a durable, dual-backend
   `AuthoringTraceStore` populated as a *by-product* of the two signing sites
   that already write `execution_records`. No new trust surface: a step is
   recorded only for a call that was approved **and** signed, and capture is
   best-effort (a trace failure degrades to "no graduation candidate", never
   blocks the mutation).
2. **Harden the seam the trace reads from** (R-7) — the change-request card's
   secret masking becomes fail-closed and the raw secret-bearing `parameters`
   stop riding the stream frame and the durable record for an action card, with
   the signed `args_digest` inputs untouched.
3. **Declare mutating-ness explicitly** (R-3) — an additive executable-flow skill
   class (`kind: executable_flow` + a machine-readable replay step list) with
   `risk_class` decoupled from `web_target`, validated on skills-hub's existing
   ingestion path and stored on **both** skill-store backends.
4. **Graduate deterministically** (R-4) — a session endpoint assembles the
   executable-flow draft from the trace with **no LLM synthesis**, re-validates
   blast radius before producing it, and yields a preview-and-download draft for
   human merge behind one new `session:skill_graduate` action + `skill_graduated`
   audit event.
5. **Replay under one gate** (R-5) — a graduated *browser* executable flow binds
   and one-gates through the **existing** SPEC-051 machinery end-to-end; the
   generalized non-browser (infra `k8s.*`) binding is deferred to its own slice
   (OQ-2), and R-5's non-browser criterion *asserts* the safe per-action
   fallback rather than delivering it.

Nothing here is a new approval mechanism. The park, the card, the signature, the
receipt, the flow authority, the deviation guard, and the audit/policy plumbing
are the SPEC-020/021/030/037/049/051/054 ones. ADR-0007 is **phased** (per-action
for exploration, one-gate for graduated replay), not reversed.

Three invariants are load-bearing and pinned by test rather than by review:

- **The signed `args_digest` is computed from the in-memory parked call, never
  from a display or at-rest surface.** `build_requests` digests
  `call["parameters"]` re-parsed from `PendingConfirmation.tool_calls`
  (`services/execution_signing.py:90,100`), and a parked confirmation never
  survives a restart (`services/hitl_confirmations.py:8-11`; resume after rebuild
  fails closed 404/410). So R-7's masking of the *streamed/persisted* projection
  and R-2's *secret-safe parameterization* of the trace both read the same
  in-memory seam without ever becoming a signing input.
- **Capture is a by-product of an already-signed mutation.** The only two sites
  that write `execution_records` are `_prepare_executions` (per-action,
  `runtime_kernel.py:1226,1268-1296`) and `_sign_flow_execution` (flow-unlock,
  `runtime_kernel.py:1360-1371`); both already run only for an approved+signed
  write. R-2 hooks beside `_persist_execution_request`, so a read-tier call is
  structurally incapable of entering the trace.
- **A field on one store backend only is silently dropped in production.** The
  skills-hub `web_target`/`risk_class`/`flow_intent` lesson
  (`services/skill_store.py:171-182`) applies twice here — the new `skills`
  columns (R-3) and every `authoring_trace` field (R-1) land on **both** the
  in-memory and Postgres backends, and verification targets `postgres` (the
  dev-k8s backend).

## Resolved At Plan Time

The spec delegated five items to this plan (OQ-1..OQ-5 were resolved at approval;
their concrete shape is worked here), and the pre-implementation code read
surfaced the exact reconciliation R-7 named but deferred.

### 1. R-7 persist-vs-redact reconciliation (the spec's explicit `plan.md` decision)

SPEC-054 recorded the tension: its Non-Goal "No masking of the raw parameters
already persisted on the durable record" warned that "fixing it means changing
the parked-payload shape that the signed path, the durable record, and the portal
all read." The code read resolves the tension cleanly — **the signed path does not
read the persisted record at all**:

- `resume_confirmation` takes the in-memory `PendingConfirmation` returned by
  `ConfirmationRegistry.claim` (`runtime_kernel.py:1792-1795`); `build_requests`
  iterates `pending.pending_calls_payload()` which re-parses `self.tool_calls`
  (`hitl_confirmations.py:94,102-108`), and `args_digest =
  canonical_digest(call["parameters"])` (`execution_signing.py:100`). The
  Postgres `confirmation_records.pending_calls` JSONB
  (`confirmation_records.py:68,264`) is a **display/audit surface** for the inbox
  and the re-loaded transcript — never a signing input.
- The worker recomputes the digest from the **executed** kwargs (SPEC-037 R-3),
  not from the streamed parameters, so the `confirmation_request` frame's
  `parameters` are display-only too.

**Resolution:** masking is a pure display + persistence projection. For an
`action` card, redact the entry's raw `parameters` **in place** (keys preserved,
secret-bearing values → `***`) on both the stream frame and the durable record,
and present the fail-closed `change_request` projection; `build_requests` /
`canonical_digest` are untouched, so the `args_digest` is byte-identical. Redacting
*values in place* (rather than removing the `parameters` key) keeps the
`pending_calls.items` shape the `additionalProperties: false` stream schema
already declares (`parameters` + `change_request`), so **no contract change** is
needed for R-7. `flow`/legacy cards are unchanged (they render the headline and
carry no `change_request`).

Alternatives rejected: (a) at-rest encryption of `parameters` — heavier and
pointless, since nothing reads at-rest parameters for signing; (b) masking only
the projection and keeping raw parameters (today's SPEC-054 state) — that *is*
finding #1; (c) a split signed-raw/display-masked column pair — unnecessary, the
persisted raw has no signing consumer.

### 2. R-7 fail-closed projection (finding #2)

`_generic_fields` masks via `should_mask = is_secret_param(name) or
is_opaque_value(tool, name)` (`hitl_confirmations.py:225-230`,
`secret_params.py:79-85`) — a **mask-if-known-secret** posture, so a secret under
an off-vocabulary, generically-named key projects as plaintext (fail-open).

**Resolution:** flip the generic projection to **mask-unless-known-safe**. Add a
per-tool `KNOWN_SAFE_FIELDS` allow-list to `secret_params.py` naming the
curated non-secret fields that may render verbatim (`k8s.delete_pod`:
`name`/`namespace`; `web.select`: `value`; `web.fill_credential`:
`credential_set`/`field`; `web.press_key`: `key`; `web.upload_file`: `filename`),
and make `should_mask` return `True` for any field not positively on that
allow-list. The curated formatters (`_cr_*`) already decide their own fields and
are unchanged; only the **generic fallback** flips. This is the same
by-default-mask posture SPEC-054's plan §R-3 described but the implementation
realized as mask-if-known-secret; R-7 completes it.

### 3. Authoring-trace schema + retention (R-1, OQ-1 resolved lifecycle-bound)

**Resolution:** a new `services/authoring_trace.py` mirroring
`services/execution_records.py` verbatim in shape — an `AuthoringTraceStore`
`Protocol`, `InMemoryAuthoringTraceStore`, `PostgresAuthoringTraceStore`, and a
`build_authoring_trace_store()` factory reusing the SPEC-016/017 knobs
(`AGENT_STATE_STORE_BACKEND` / `AGENT_STATE_DB_URL`) with the same fail-open-to-memory
posture. A trace step records: `session_id`, `position` (per-session ordinal),
`tool_name` (canonical dotted), `args` (JSONB, **secret-safe parameterized**),
`execution_id` + `confirm_id` (**references** — the signed receipt/outcome stay in
`execution_records`), `status`, `captured_at`. Lifecycle is
`draft → graduated | discarded` (terminal), **not** time-swept with the 30-day
`RETENTION_WINDOW_DAYS` execution sweep. Two knobs bound it: a per-session step
cap (`AGENT_AUTHORING_TRACE_MAX_STEPS`, default 100 — capture beyond the cap is
dropped best-effort) and an idle-GC that reclaims `draft` traces idle beyond
`AGENT_AUTHORING_TRACE_IDLE_DAYS` (default 180) at startup + opportunistically on
write, the `_SWEEP_EXPIRED` shape. A fixed window tied to the receipt sweep was
rejected (OQ-1) because it reintroduces exactly the loss the dedicated trace
exists to prevent.

### 4. Executable-flow schema shape (R-3, OQ-4 resolved additive under a `kind`)

**Resolution:** `skill.schema.json` advances **Skill v1 → v2** additively — a
`kind` discriminator (`enum: ["knowledge", "executable_flow"]`, absent =
`knowledge`) and a `steps` replay list (ordered `{tool, args, expect?}`, whose
credential values are credential-set **references**, never literals). `risk_class`
stays `enum: ["read","write"]` but its "requires web_target" clause is dropped
from the description and the ingestion rule (`ingestion.py:191-194`). skills-hub:
`kind` + `steps` join `ALLOWED_KEYS` (`ingestion.py:34-48`), the `Skill` model
(`schemas/skill.py`, `extra="forbid"`), and **both** store backends
(`skill_store.py` — `kind TEXT`, `steps JSONB`, idempotent `ALTER TABLE … ADD
COLUMN IF NOT EXISTS`, INSERT + row-map, the `flow_intent` precedent). Ingestion
validates the executable-flow class (step shape, `risk_class: write` when any step
mutates, credential refs resolve to named credential sets) and rejects a malformed
one on the existing `validate_document` path SPEC-044 drafts against. A sibling
schema was rejected (OQ-4): two skill contracts would drift.

### 5. Graduation is deterministic; replay reuses SPEC-051 (R-4/R-5, OQ-2 resolved)

**Resolution (R-4):** a new `services/skill_graduation.py` with
`build_executable_flow_draft(trace)` that renders the ordered trace into an
executable-flow skill Markdown (frontmatter `kind: executable_flow`,
`risk_class: write`, `web_target` for a browser flow, `steps`; body = a
human-readable replay runbook) with **no LLM call** — contrast SPEC-044's
`generate_skill_draft` (`skill_draft.py`), which synthesizes knowledge prose. The
endpoint `POST /api/v2/sessions/{session_id}/skill-graduate` mirrors
`create_skill_draft` (`routes.py:862-905`): gateway-enforced
`session:skill_graduate`, server-side ownership re-check (foreign/unknown → the
structural 404), validation through skills-hub's ingestion path
(`_validate_skill_markdown`), a `skill_graduated` audit event, and a trace
lifecycle flip to `graduated`. Blast-radius re-validation runs **before** the
draft is produced (bounded step count, every origin/target allowlisted,
consistent `risk_class: write`, all credentials resolved to credential-set
references — the SPEC-051 guards); a trace that fails is a deterministic refusal
surfaced to the operator. Ephemeral by construction (nothing persisted but the
lifecycle flip); previewed + downloaded like SPEC-045.

**Resolution (R-5):** a graduated *browser* executable flow, once a human merges
and ingests it, is an ordinary `web_target` + `risk_class: write` skill — so it
binds and one-gates through the **existing** SPEC-051 path with no new executor:
`web.navigate(skill_id=…)` binds the gateway flow, the kernel records
`FlowContext` (`_observe_flow_binding`, `runtime_kernel.py:1391-1415`), the first
write parks a `flow`-kind card, `_record_flow_approval` arms `FLOW_APPROVALS`
(`runtime_kernel.py:1748-1790`, now requiring `risk_class == "write"`), and each
subsequent write auto-signs under `build_flow_request`
(`execution_signing.py:108-149`), gateway-guarded. The `steps` list is the
machine-readable replay contract the agent follows under that one gate; credentials
resolve at replay via `web.fill_credential` credential-set references (never
literals). Per OQ-2 the generalized non-browser (infra `k8s.*`) binding keyed on
skill identity is **deferred to its own slice**; until it lands an infra
executable flow's steps park per-action under SPEC-054 R-2 (fails safe), and R-5's
non-browser criterion *asserts* that fallback rather than delivering the binding.

### 6. Verification-only surfaces (Impact correction candidate)

`execution-request.schema.json` and `execution-runtime` need **no** change: a
browser replay envelope is byte-identical to a hand-authored flow envelope
(`build_flow_request` already stamps `approval_kind: "flow"`, ADR-0010), and the
worker already verifies + forwards it (SPEC-054 stage 3). This holds the spec's
Impact ("verify only unless the infra-binding needs a new envelope variant") — the
infra variant is the deferred 0.36.0-era slice, out of scope here. If delivery
finds otherwise it is flagged for a spec-changelog record, not silently absorbed
(the SPEC-054 §4 precedent).

## Design Per Requirement

### R-1: Durable authoring-trace store

- affected files: `products/agent-platform/src/agent_service/services/authoring_trace.py`
  (new — protocol, `InMemory` + `Postgres` backends, `build_authoring_trace_store`
  factory, module-level `AUTHORING_TRACE_STORE` singleton, mirroring
  `execution_records.py`); `core/config.py` / `runtime_settings.py` (the two new
  knobs); the DDL creates `authoring_trace` in place on first use (idempotent),
  sharing the SPEC-016 `sessions` database.
- chosen approach: every schema field on **both** backends; ordered by
  `(session_id, position)`; a per-session step cap enforced at append; lifecycle
  `draft → graduated | discarded`; idle-GC over `draft` rows only (terminal rows
  are never swept). Best-effort writes (a store failure logs and degrades, never
  raises into the seam).
- alternatives rejected: reusing `execution_records` — rejected (ADR-0009): it
  stores an `args_digest` hash, not replayable arguments, and is swept at 30 days.
  A single-backend store — rejected: the in-memory default would silently drop
  fields in the Postgres dev-k8s deployment (the known pitfall).

### R-2: Authoring-trace capture at the approval seam

- affected files: `runtime_kernel.py` — a `_capture_authoring_step(...)` helper
  called beside `_persist_execution_request` (`:1289-1302`) at **both** signing
  sites: `_prepare_executions` (per-action, `:1268-1270`) and
  `_sign_flow_execution` (flow-unlock, `:1371`); `services/authoring_trace.py`
  (the append); reuse of `services/secret_params.py` for secret-safe
  parameterization at capture.
- chosen approach: capture reads the same in-memory `parameters` the signer
  digests, replaces credential values with credential-set references /
  placeholders (the SPEC-049 R-5 vocabulary + `web.fill_credential` indirection)
  **before** the write, and stores `execution_id`/`confirm_id` references (not the
  receipt). Both approval kinds append, so a mixed session yields one coherent
  ordered trace. Best-effort: wrapped like `_persist_execution_request`, a trace
  failure degrades to "no graduation candidate" and never blocks execution or the
  `execution_records`/receipt path. Read-tier calls never reach these sites, so
  they are never captured.
- alternatives rejected: capturing at park time — rejected: an un-approved or
  denied call must never enter the trace (R-2 is a by-product of an
  *already-approved, already-signed* mutation). Capturing in the worker —
  rejected: the worker has no session-scoped trace store and would duplicate the
  receipt path.

### R-3: Executable-flow skill class with `risk_class` decoupled from `web_target`

- affected files: `shared/shared-contracts/schemas/skill.schema.json` (v1 → v2:
  additive `kind` + `steps`, `risk_class` description de-coupled);
  `products/skills-hub/src/skills_hub/schemas/skill.py` (`kind`, `steps`);
  `services/ingestion.py` (`ALLOWED_KEYS`, relax the `risk_class`-requires-`web_target`
  rule at `:191-194`, validate the executable-flow class + credential-ref
  resolution); `services/skill_store.py` (`kind TEXT`, `steps JSONB` on both
  backends + idempotent ALTERs + INSERT + row-map).
- chosen approach: additive discriminator; a `read`-class skill still never
  executes mutating tools (only a `write`-class executable flow can replay, and
  only under R-5's one gate). Knowledge/guidance skills omit `kind`/`steps` and
  validate exactly as today (no existing skill breaks).
- alternatives rejected: extending SPEC-044's knowledge draft to carry
  `risk_class`/`web_target` inline — rejected (ADR-0009): `SkillFrontmatter` is
  grounded-guidance and `extra="forbid"`; retrofitting execution semantics onto it
  conflates two artifacts and bypasses ingestion validation. A sibling schema —
  rejected (OQ-4).

### R-4: Graduation with blast-radius re-validation and human merge

- affected files: `products/agent-platform/src/agent_service/services/skill_graduation.py`
  (new — `build_executable_flow_draft(trace)` deterministic assembly +
  `revalidate_blast_radius(trace)`); `api/v2/routes.py`
  (`POST /sessions/{session_id}/skill-graduate` mirroring `create_skill_draft`);
  `shared/shared-contracts/policies/policy-default.yaml` (one new
  `session:skill_graduate` action, `roles_any: [platform-admin, approver,
  operator]` — the `session:skill_draft` grant at `:286-290`, observer excluded);
  `shared/shared-contracts/schemas/audit-event.schema.json` (`skill_graduated`
  added to the `event_type` enum at `:27-48` + its `details` documented at `:87`);
  portal: a "Graduate as skill" entry point on the session + the SPEC-045
  rendered/raw preview + Download.
- chosen approach: deterministic over the captured, approved trace (never invents
  a step); re-validates blast radius **before** producing the draft (a failing
  trace is a deterministic refusal, surfaced); produces a **draft for human review
  and merge** (never auto-publish); one distinct action + one distinct audit event
  (OQ-3 — a higher trust level than a knowledge draft, separately authorized and
  audited); the trace lifecycle flips to `graduated`.
- alternatives rejected: reusing `session:skill_draft` — rejected (OQ-3): it would
  let a role authorized only for knowledge drafts produce an executable mutating
  artifact and collapse two trust levels into one audit vocabulary. LLM synthesis
  of steps — rejected (Non-Goal): graduation is deterministic over what actually
  ran and was approved.

### R-5: Replay under one gate, secret-safe and gateway-guarded

- affected files: no new binding for browser replay — it rides the existing
  SPEC-051 path (`runtime_kernel.py` `_observe_flow_binding` / `_record_flow_approval`
  / `_sign_flow_execution`; `flow_approvals.py`; `execution_signing.build_flow_request`;
  `tool-gateway/tools/browser_connector.py` deviation guard). Portal: replay
  surfacing (the flow headline + change-request framing already render). The
  infra binding is **deferred** (OQ-2).
- chosen approach: a graduated browser executable flow replays identically to a
  hand-authored flow — one parked `flow`-kind card, subsequent writes admitted
  under the authority and each individually signed/persisted/audited/receipted;
  the gateway deviation guard (origin allowlist, declared `risk_class`, step
  budget) bounds every replayed write; executable-flow writes **never** join any
  auto-allow list; credentials resolve at replay from the named credential sets.
  R-5's non-browser criterion **asserts** the safe fallback: an infra executable
  flow's steps park per-action (SPEC-054 R-2) and never auto-allow.
- alternatives rejected: shipping the generalized skill-identity binding here —
  rejected (OQ-2, operator-directed): too large for this slice; browser replay
  ships now, the infra binding is its own 0.36.0-era slice, and the per-action
  fallback already fails safe.

### R-6: Delivery traceability per ADR-0008

- affected files: `docs/specs/SPEC-055-…/tasks.md` records ≥1 asserting test per
  R-1..R-5 + R-7 acceptance criterion; any shipped `samples/` graduation demo is
  exercised by its own script in the verification path; `docs/specs/README.md` +
  `CONTRIBUTING.md` already carry the ADR-0008 gate text (verify only).
- chosen approach: an interactive graduation demo under `samples/` **is** shipped
  (author a session → graduate → merge → replay under one gate), because ADR-0008
  requires a shipped sample to be exercised by its own script and the graduation
  path is otherwise unexercised end-to-end.

### R-7: Approval-seam secret-masking hardening

- affected files: `services/secret_params.py` (`KNOWN_SAFE_FIELDS` allow-list +
  `should_mask` flipped to mask-unless-known-safe); `services/hitl_confirmations.py`
  (`_generic_fields` fail-closed; the action-card entry's raw `parameters`
  redacted in place beside the `change_request` projection at `:109-133`);
  `services/confirmation_records.py` + the `runtime_kernel.py` park site (the
  persisted `pending_calls` carries the redacted entry for an action card);
  portal `chat/ChatView.tsx` (the expander presents the `change_request`
  projection, not raw `parameters`, for an action card).
- chosen approach: redaction is a **projection** only — the `canonical_digest(parameters)`
  inputs that form the signed `args_digest` are unchanged (Resolved At Plan Time
  1); masking is fail-closed (Resolved At Plan Time 2); `web.fill_credential`
  stays the reference-only structural floor, and the same discipline extends to
  non-browser action parameters. `flow`/legacy cards unchanged.
- alternatives rejected: see Resolved At Plan Time 1 (at-rest encryption, split
  columns, projection-only-mask) — all rejected there.

## Sequencing And Dependencies

1. **Contracts first** — `skill.schema.json` (v1 → v2: `kind`, `steps`,
   `risk_class` decoupled), `audit-event.schema.json` (`skill_graduated` +
   details), `policy-default.yaml` (`session:skill_graduate`). Everything
   validates against these.
2. **R-7 approval-seam masking** (agent-platform + portal) — depends on nothing
   but stage 1's unchanged `pending_calls` shape; **self-contained and
   independently revertable** (unlike SPEC-054's R-2). Sequenced early because
   R-2's capture reads the seam R-7 hardens.
3. **R-1 AuthoringTraceStore** (agent-platform) — depends on stage 1 for nothing
   (internal store); can proceed in parallel with stage 2.
4. **R-2 capture at the seam** (agent-platform) — depends on stage 3 (the store)
   and reads the seam stage 2 hardened.
5. **R-3 executable-flow skill class** (skills-hub) — depends on stage 1
   (`skill.schema.json` v2); a different product, parallel with stages 2-4.
6. **R-4 graduation** (agent-platform endpoint + deterministic assembly +
   blast-radius re-validation + policy/audit + portal preview/export) — depends on
   stage 3 (the trace to graduate), stage 5 (the skill class to validate against),
   and stage 1 (the action + event).
7. **R-5 replay** (agent-platform verify + tool-gateway guard + portal surfacing;
   assert the infra per-action fallback) — depends on stage 5 (an ingested
   executable-flow skill) and stage 6 (a graduated draft to merge/ingest).
8. **Samples + tests per stage; living-state docs, CHANGELOG, version lockstep,
   and the release note on delivery.** Depends on all.

## Test Strategy

- **agent-platform (`pytest`)**
  - R-1: dual-backend round-trip incl. the `postgres` backend (every field on
    both); the per-session step cap drops capture beyond the bound; lifecycle
    `draft → graduated | discarded`; the idle-GC reclaims `draft` rows and never a
    terminal row; a store failure degrades without raising.
  - R-2: a step is captured only for a signed mutation at **both** sites
    (per-action + flow-unlock); a read-tier call is never captured; a mixed
    session yields one ordered trace; secret values are parameterized at capture
    (no literal reaches the store); a trace-store failure never blocks execution
    or the `execution_records`/receipt write.
  - R-4: `build_executable_flow_draft` is deterministic over a fixed trace (no
    LLM); blast-radius re-validation refuses an over-budget / off-allowlist /
    inconsistent-`risk_class` / unresolved-credential trace and passes a clean one;
    the endpoint emits `skill_graduated`, flips the lifecycle to `graduated`, and
    produces a draft that is **not** published; observer is denied
    (`session:skill_graduate`), operator/approver allowed.
  - R-5: a graduated browser executable flow binds and collapses to **one**
    `flow`-kind gate with each subsequent write individually signed
    (`build_flow_request`) + receipted; an infra executable-flow write parks
    per-action and joins no auto-allow list (the OQ-2 fallback asserted).
  - R-7: an off-vocabulary secret value is masked in the projection (fail-closed);
    a secret-bearing parameter does not stream/render/persist as plaintext for an
    action card; `args_digest` verification still passes after masking (the
    invariant); a `flow`/legacy card is unchanged.
  - contract: a v2 executable-flow skill validates against `skill.schema.json`; a
    `skill_graduated` audit envelope validates against `audit-event.schema.json`.
- **skills-hub (`pytest`)** — `risk_class: write` **without** `web_target`
  ingests (the relaxed rule); a `kind: executable_flow` skill with a valid step
  list ingests and round-trips on **both** store backends; a malformed step list /
  a missing `risk_class: write` on a mutating flow / an unresolvable credential
  reference is rejected; a knowledge skill (no `kind`/`steps`) validates exactly as
  today.
- **tool-gateway (`pytest`)** — the deviation guard (origin allowlist, declared
  `risk_class`, step budget) bounds a replayed executable-flow write identically
  to a hand-authored flow; executable-flow writes are in no auto-allow list; the
  bound-flow behavior is byte-for-byte unchanged.
- **execution-runtime (`pytest`)** — verify only: a browser replay envelope
  (`approval_kind: "flow"`) verifies and forwards unchanged (no code change
  expected; a test pins the no-change invariant).
- **operator-portal (`vitest`)** — the "Graduate as skill" entry point appears for
  an authorized role and not for an observer; the executable-flow draft preview
  renders (rendered + raw) and downloads; the R-7 action-card expander presents
  the `change_request` projection with masked values (`***`) and never a raw
  secret; a `flow`/legacy card renders unchanged.
- **policy** — the SPEC-048 scenario-expectation harness gains a
  `session:skill_graduate` scenario (operator/approver allow, observer deny);
  `make policy-diff` reports the one new (role, action) grant.
- **integration** — `make verify` green (all products, overlays, policy scenarios,
  version lockstep, the secret-vocabulary leg — extended if `KNOWN_SAFE_FIELDS`
  needs a twin check); the graduation `samples/` demo exercised by its own script;
  the password-reset + adhoc-password-reset `demo.sh` chat legs stay green.

## Rollout And Migration

- **deployment/configuration changes:** two new agent-platform knobs —
  `AGENT_AUTHORING_TRACE_MAX_STEPS` (per-session step cap, default 100) and
  `AGENT_AUTHORING_TRACE_IDLE_DAYS` (idle-GC window for `draft` traces, default
  180) — documented in `docs/guides/configuration-reference.md`. One new policy
  action (`session:skill_graduate`) changes the bundle content-hash (SPEC-048
  provenance) and needs a new scenario row; one new audit event type
  (`skill_graduated`) joins the portal Audit filter vocabulary pinned by the
  SPEC-046 drift guard. `authorization-matrix.md` gains the new action.
- **backward compatibility:** additive and fail-safe throughout.
  - Skills without `kind`/`steps` validate and ingest exactly as today; existing
    `skills` rows get NULL `kind`/`steps` → omitted (idempotent `ALTER … ADD
    COLUMN IF NOT EXISTS`).
  - The `authoring_trace` table is created in place on first use; absence of a
    trace is simply "no graduation candidate" (fail-safe), never an error.
  - R-7 redacts *values in place* on the action-card `parameters` (keys and the
    `pending_calls.items` shape preserved), so the stream schema needs no change
    and a `flow`/legacy card is byte-identical; the `args_digest` is unchanged, so
    no re-signing or verification impact and no mixed-version hazard.
  - `execution-request.schema.json` and execution-runtime are unchanged (a browser
    replay envelope is byte-identical to a hand-authored flow envelope).
- **data migration:** none beyond the idempotent `skills` column adds and the new
  `authoring_trace` table.
- **rollback:** revert the delivery commit. The `authoring_trace` table and the
  `skills` `kind`/`steps` columns are harmless if left in place (unused / NULL), so
  no destructive down-migration is required. Rolling back R-7 restores the
  SPEC-054 fail-open projection (the pre-spec posture); rolling back R-1..R-5
  removes the graduation path and leaves per-action approval (SPEC-054) intact.
- **version:** MINOR bump **0.35.0 → 0.36.0** at the delivery gate (a
  backward-compatible feature train, per the house "release trains map to MINOR
  bumps" convention), with `VERSION` + the per-product lockstep constants +
  `uv.lock` re-locks. The OQ-2 infra-binding slice is a **separate** follow-up
  train; the delivery-roadmap's "0.36.0" forward anchor for the SPEC-055-era infra
  work is reconciled to its actual train when that slice is specced.
