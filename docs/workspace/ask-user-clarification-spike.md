# Spike: Agent-Initiated Clarification (`AskUser` tool) — Design Exploration

Status: exploration / design framing (2026-11-24) — **reviewed by the operator and promoted to
`draft` [SPEC-080](../specs/SPEC-080-agent-initiated-clarification/spec.md) 2026-11-24**; body frozen
per the Tier-1 assessment-memo lifecycle. The seven ratification asks (§8) are carried into the draft
spec as its **Open Questions** (recommended, not yet ratified); OQ ratification (`draft → approved`)
is the operator's next gate.
This memo resolves the questions the [Exploration Backlog](../agentic-aiops-platform/delivery-roadmap.md#exploration-backlog)
parked on the **"Agent-initiated clarification (`AskUser` tool)"** row and recommends a
decision-complete shape for a **SPEC-080 candidate**. On its own this memo authorizes **no**
runtime change, **no** new ADR, **no** SPEC number, and **no** implementation; promoting a
`draft` spec is the operator's next gate (§7).
Date: 2026-11-24
Roadmap home: [Exploration Backlog](../agentic-aiops-platform/delivery-roadmap.md#exploration-backlog) — the "Agent-initiated clarification (`AskUser` tool)" row (raised 2026-11-01 from the agentscope 2.0.9 headline-feature review)
Adoption gate: [SPEC-018](../specs/SPEC-018-kernel-middleware-alignment/spec.md) four-point adoption gate (§5) — the load-bearing test this memo scores
Builds on (all delivered): the HITL confirmation family [SPEC-020](../specs/SPEC-020-hitl-confirmation-bridging/spec.md)/[SPEC-030](../specs/SPEC-030-require-approval-policy-semantics/spec.md)/[SPEC-031](../specs/SPEC-031-approval-inbox-persistent-confirmation/spec.md)/[SPEC-032](../specs/SPEC-032-owner-side-live-decision-sync/spec.md); the v0.59.0 `ConfirmationCoordinator` / `TurnStreamer` collaborator seams; the v2 SSE contract [`agent-stream-event.schema.json`](../../shared/shared-contracts/schemas/agent-stream-event.schema.json) (**v13**); the closed audit [`audit-event.schema.json`](../../shared/shared-contracts/schemas/audit-event.schema.json) `event_type` enum (**23 values**)
Evidence baseline: repository at **v0.61.1** (`c84de0c1`); static reading of the agentscope 2.0.11 `AskUser` builtin + event surfaces, the delivered HITL park/resume machinery, and the v2 / audit contracts. **No agent was run, nothing was deployed, no billable call was made in authoring this memo.**

## 1. Question and framing

> The backlog row (verbatim): *"`AskUser` lets the agent pose a multiple-choice question
> mid-turn and resume on the answer — a human-in-the-loop **clarification** companion to the
> existing confirmation/approval HITL (SPEC-020/030/031), distinct from a mutating-action
> park. Adopting it needs a **new v2 SSE frame** (question + options) and a **resume path**
> keyed to the parked question, and must not leak agentscope types through the
> platform-owned contract (gate point 4) or bypass the closed audit `event_type` enum.
> **Spike needed**, answering: does a clarification park reuse the SPEC-031 confirmation
> lifecycle/records and SPEC-032 owner-side sync, or need a parallel one? how does it
> interact with a pending confirmation (the `409 confirmation pending` guard)? **Promotion
> trigger:** a spike memo landing with the frame + resume design."*

The [2.0.11 dependency-refresh release note](../agentic-aiops-platform/release-notes/2026-10-31-dependency-refresh-agentscope-2-0-11.md)
recorded `AskUser` as **not adopted** — "deferred (needs a new v2 stream frame plus a resume
path)" — and [SPEC-071 Non-Goals](../specs/SPEC-071-agentscope-model-router/spec.md) kept it
out of scope. This memo is the deferred spike.

The questions to answer (each resolved in §3):

1. **Reuse vs. parallel park** — does a clarification park reuse the SPEC-031 confirmation
   lifecycle/records + SPEC-032 owner-side sync, or need a parallel mechanism?
2. **The agentscope event mechanism** — which park/resume events does `AskUser` ride, and
   what does the kernel handle today?
3. **The v2 contract shape** — what new SSE frame(s), and how are they kept platform-owned?
4. **The 409 guard interaction** — how does a parked clarification interact with the
   existing `confirmation pending` guard and the one-park-per-session invariant?
5. **The closed audit enum** — does a clarification need a new `event_type`, or ride an
   existing one?
6. **Opt-in posture** — how is the unscoped single-agent chat path kept byte-identical?
7. **v1 feature surface** — which `AskUser` capabilities ship in v1 vs. a fast-follow?

Recommendation summary (each resolved in §3):

- **A parallel park *kind* on the *shared* park/resume/expire substrate.** Reuse the
  registry, TTL, 409 guard, `UserInterruptEvent` abort, and the durable-record-for-re-login
  *pattern* — but **not** the SPEC-031 *approval lifecycle* (no distinct-human approver, no
  approval inbox, no tier / self-approval gating) and **not** the confirmation event pair.
- **`AskUser` rides `RequireExternalExecutionEvent` → `ExternalExecutionResultEvent`**, a
  *different* agentscope park mechanism from confirmation's `RequireUserConfirmEvent` →
  `UserConfirmResultEvent`. The kernel handles **only** the confirmation pair today
  (`kernel_confirmations.py:116-119`); it has **zero** handling for external execution. That
  gap is the real net-new.
- **A new v2 SSE frame pair** — `clarification_request` (questions + options) and
  `clarification_result` (the answers) — bumping the contract **v13 → v14** (additive), as
  **platform-owned projections** of `AskUserParams` / `AskUserMetadata`, never the agentscope
  `ToolCallBlock` / `RequireExternalExecutionEvent` shapes.
- **The 409 guard becomes park-kind-aware.** A parked clarification wedges the session
  identically to a parked confirmation; the one-park-per-session invariant is preserved by a
  shared registry slot carrying a `park_kind` discriminator.
- **No new audit `event_type`** in v1 — a clarification is a read-only, non-mutating, in-turn
  interaction with no security decision, so it rides the existing turn audit
  (`chat_started` / `chat_completed`), mirroring the SPEC-077 R-5 "reuse `chat_completed`,
  enum stays closed" precedent. Governance attribution is flagged as an OQ (§8).
- **Opt-in and intent-gated** — `AskUser` is added to the toolkit behind a flag; the unscoped
  single-agent chat path stays **byte-identical** when the agent never calls it.
- **v1 ships the full `AskUserParams` shape** (1–4 questions, 2–4 options, `multi_select`,
  auto-"Other" free text); the single-select-only `preview` field is a named fast-follow.

The net effect: a SPEC-080 candidate is a **HITL-bridging-family extension** — it adds a
*second, read-only park kind* (clarification) beside the existing mutating park
(confirmation), composing the delivered park/resume/expire substrate and the v0.59.0
`ConfirmationCoordinator` seam. It is **not** a mutation-path, trust-model, or autonomy
change: a clarification mutates nothing and cannot widen the read-only posture.

## 2. What is already delivered (the foundation a clarification park composes)

- **The HITL park / resume / expire substrate (SPEC-020/030/031).** A per-session
  `ConfirmationRegistry` (`hitl_confirmations.py:584`, module singleton `:728`) holding **one
  `PendingConfirmation` per session** (`_by_session`); `register(...)` (`:600`),
  `peek_parked(session_id)` (`:694`, TTL-agnostic — returns the unresolved entry so routes
  distinguish "parked" from "parked-but-expired"), `resolve(...)` (`:706`), `has_pending`
  (`:715`). A park TTL (`hitl_confirm_timeout`); expiry closes the parked reply with a
  `UserInterruptEvent`.
- **The v0.59.0 `ConfirmationCoordinator` seam.** The extracted park/resume/expire
  collaborator (`kernel_confirmations.py`): `resume_confirmation` (`:427`) →
  `_resume_confirmation` (`:465`) builds `ConfirmResult` + `UserConfirmResultEvent` (`:502`)
  and re-drives the parked reply; the resumed stream follows the v2 frame contract and
  belongs to the same assistant turn (SPEC-025 R-1). This is the seam a clarification resume
  would sit beside.
- **The 409 park guard.** `_reject_if_parked` (`api/v2/routes.py:229`) peeks
  `get_confirmation_registry().peek_parked(session_id)` (`:246`) and raises **409
  "confirmation pending"** (`:264-272`) at the chat entry points (`:359`, `:501`); a
  TTL-expired park is closed via `expire_confirmation` and the turn proceeds.
- **Durable records + owner-side sync (SPEC-031 / SPEC-032).** SPEC-031 made the durable
  record store the source of truth so a card survives re-login/restart and feeds the approver
  inbox (30s/focus poll). SPEC-032 lets the owner's open chat poll session detail and
  re-render when a card resolves — *"the resolution frame only rides the answering stream by
  design … SPEC-031 deliberately made the durable record store the source of truth for
  everyone else"* — with **no new backend surface**.
- **The v2 SSE contract (v13).** `agent-stream-event.schema.json`, `additionalProperties:
  false`, closed `type` enum (10): `message_start`, `message_delta`, `message_end`, `error`,
  `tool_call`, `tool_result`, `confirmation_request`, `confirmation_result`,
  `secret_delivery`, `authorization_required`. The `confirmation_result` `status` enum is
  closed too: `success`, `error`, `denied`, `approved`, `expired`, `interrupted`.
- **The closed audit `event_type` enum (23 values).** `audit-event.schema.json` —
  `tool_invoked`, `policy_decision`, `token_exchange`, `session_created`, `session_deleted`,
  `chat_started`, `chat_completed`, `confirmation_decided`, `incident_triaged`,
  `skill_searched`, `skill_retrieved`, `skills_synced`, `execution_requested`,
  `execution_completed`, `execution_rejected`, `document_created`, `document_published`,
  `document_read`, `skill_draft_generated`, `incident_skill_draft_generated`,
  `skill_graduated`, `secret_delivered`, `target_authorization`. (The SOP backlog row's
  "22-value" phrasing is stale — it predates SPEC-070's `target_authorization`.)

**The agentscope surface (2.0.11, read-only inspection).** `AskUser(ToolBase)`
(`agentscope/tool/_builtin/_ask_user.py`): `name="AskUser"`, `is_read_only=True`,
`is_external_tool=True`, `is_concurrency_safe=True`, `is_state_injected=False`, and
`check_permissions(...)` returns `PermissionBehavior.ALLOW` — *"Never asks to ask … a
confirmation in front of it would only be a prompt about a prompt."* Its docstring: *"External
by nature: only whatever is driving the agent can put a question in front of a person, so the
agent **yields the call and waits for the answer to come back rather than executing anything
itself**."* Input `AskUserParams.questions` (1–4, unique texts); each `_Question{question,
header (≤12 chars), context?, options (2–4, unique labels), multi_select=False}`; each
`_Option{label, description, preview?}` (`preview` single-select only). Output
`AskUserMetadata{answers: list[AskUserAnswer]}` → `ToolResultBlock.metadata`; each
`AskUserAnswer{question (verbatim), selected: list[str], other?: str}`. "Other" free-text is
auto-provided.

**The gap a SPEC-080 candidate fills.** agentscope parks an external tool with a *distinct*
event pair — `RequireExternalExecutionEvent{reply_id, tool_calls}` resumed by
`ExternalExecutionResultEvent{reply_id, execution_results: List[ToolResultBlock]}`
(`agentscope/event/_event.py:455`, `:520`) — and `UserInterruptEvent{reply_id}` (`:495`)
aborts **either** park kind. The platform kernel handles **only** `RequireUserConfirmEvent`
(`kernel_confirmations.py:116-119`: `if not isinstance(event, RequireUserConfirmEvent):
return None`); a repo grep finds **zero** platform references to `AskUser`,
`RequireExternalExecutionEvent`, or `ExternalExecutionResultEvent`. So nothing today parks a
clarification, streams a question, or resumes on an answer.

## 3. The design questions — recommended resolutions

### 3.1 Reuse vs. parallel park → **a parallel park *kind* on the *shared* substrate**

**Recommendation:** a clarification is a **second park kind**, not a confirmation. Reuse the
*mechanism*; do not reuse the *approval lifecycle*.

- **Reuse (mechanism):** the per-session registry + one-park-per-session slot, the park TTL,
  the `peek_parked`-driven 409 guard, `expire_confirmation`'s `UserInterruptEvent` abort
  (which agentscope already defines for **both** park kinds), the resume-injects-an-event
  pattern, and the durable-record-for-re-login *pattern* (a parked clarification should
  survive a page refresh exactly as a card does).
- **Do not reuse (approval lifecycle):** SPEC-031's approval inbox, distinct-human approver,
  tier routing, and SPEC-030 self-approval block are built for **segregation of duty over a
  mutation**. A clarification has **no approver** — the **session owner answers in-line** —
  and mutates nothing, so there is no approval to route, no tier, and no self-approval
  concern. Forcing it through the confirmation lifecycle would invent an approver for a
  question.
- **SPEC-032 owner-side sync is not needed in v1.** SPEC-032 exists because a *distinct*
  approver decides elsewhere while the owner watches. A clarification is answered by the
  owner **in the same chat view**, so the answer rides the answering stream (exactly as
  `confirmation_result` rides the answerer's `chat/confirm` stream). Cross-surface answer
  sync is a possible fast-follow (§8 OQ-5), not v1.

**Design consequence:** a `PendingConfirmation`-analogue carries a `park_kind`
(`"confirmation"` | `"clarification"`); the resume path branches on it — confirmation →
`UserConfirmResultEvent`; clarification → `ExternalExecutionResultEvent`. One registry, one
guard, one TTL, two resume branches.

### 3.2 The agentscope event mechanism → **`RequireExternalExecutionEvent` → `ExternalExecutionResultEvent`**

**Recommendation:** adopt agentscope's external-execution park for clarification, and build
the kernel's **first** handler for it.

- On a turn where the model calls `AskUser`, agentscope emits
  `RequireExternalExecutionEvent{reply_id, tool_calls}` and **parks the reply** (the agent
  "yields the call and waits"). The kernel must catch it (a new branch beside
  `kernel_confirmations.py:116-119`), project the question to the wire (§3.3), register the
  park (§3.1), and end the stream **without** `message_end` (as a confirmation park does).
- The answer endpoint builds `execution_results: List[ToolResultBlock]` — one
  `ToolResultBlock` whose `output` is prose for the model and whose `metadata` is
  `AskUserMetadata{answers}` — and injects `ExternalExecutionResultEvent{reply_id,
  execution_results}` to resume. The resumed stream follows the v2 contract and belongs to
  the same assistant turn (SPEC-025 R-1), as a confirmation resume does.
- `UserInterruptEvent{reply_id}` aborts a parked clarification identically (agentscope
  already scopes it to both park kinds), so TTL expiry and operator cancel come for free.

**Why this is the real net-new:** the confirmation path is a template for the *shape*
(park → project → register → resume-by-event-injection), but the *event pair and payload*
differ. This is the kernel's first external-execution park; it must be added without
disturbing the confirmation branch (the unscoped path stays byte-identical, §3.6).

### 3.3 The v2 contract shape → **a new `clarification_request` / `clarification_result` frame pair, v13 → v14, platform-owned**

**Recommendation:** add two frames to `agent-stream-event.schema.json` (additive bump
**v13 → v14**), as **platform-owned projections**, never agentscope types.

- **`clarification_request`** (park frame): `clarification_id` (correlator, analogous to
  `confirm_id`), and a `questions` array projected from `AskUserParams` — each
  `{question, header, context?, multi_select, options: [{label, description}]}`. The
  auto-"Other" affordance is a client behavior, not a wire option. `preview` is deferred
  (§3.7). This is a **projection** of `_Question`/`_Option` into platform JSON — the
  agentscope `RequireExternalExecutionEvent` / `ToolCallBlock` shape never crosses the wire
  (gate 4).
- **`clarification_result`** (resume-echo frame): `clarification_id` and the `answers`
  projected from `AskUserMetadata` — each `{question, selected: [labels], other?}` — plus a
  closed `status` (`answered`, `expired`, `interrupted`), mirroring `confirmation_result`.
- **Additive & backward-compatible:** two new `type` enum values + their fields;
  `additionalProperties: false` holds; older clients ignore an unknown `type` (the same
  posture as `secret_delivery` at v12 and `authorization_required` at v13). No existing frame
  changes.
- **Not a reuse of `authorization_required`:** that frame (SPEC-070 OQ-7) is explicitly *"a
  sibling of a failed tool_result, never a confirmation or execution permit; OAuth completion
  does not resume a tool"* — a **non-resuming** signal. A clarification **is** a park-resume,
  so it needs its own resuming frame pair, not the authorization shape.

### 3.4 The 409 guard interaction → **park-kind-aware guard; one-park-per-session preserved**

**Recommendation:** a parked clarification wedges the session **identically** to a parked
confirmation, and the guard says so.

- `_reject_if_parked` (`routes.py:229`) already peeks the **one** per-session slot. Because
  the registry holds one pending per session (§3.1), a new chat turn while a clarification is
  parked must be rejected the same way — with a message that names the parked kind
  ("clarification pending: answer or expire the parked question") rather than the
  confirmation wording. A TTL-expired clarification is closed via the same
  `expire_confirmation` → `UserInterruptEvent` path, then the turn proceeds.
- **Mutual exclusion is a feature:** a session cannot hold a confirmation *and* a
  clarification at once (one slot). That is correct — the agent is either awaiting approval
  for a mutation or awaiting an answer to a question, never both mid-turn. The shared slot
  makes the invariant structural rather than guarded.
- The session API's `has_pending` badge (SPEC-022 R-1) naturally covers both kinds, since it
  reads the same slot.

### 3.5 The closed audit enum → **no new `event_type` in v1; ride the turn audit**

**Recommendation:** keep the 23-value enum **closed**; a clarification rides the existing
`chat_started` / `chat_completed` turn audit.

- A clarification is **read-only, non-mutating, and carries no security decision** — unlike
  `confirmation_decided` (an approve/deny of a mutation) or `execution_requested`. There is no
  authority provenance to record. The turn that parks and resumes is already bracketed by
  `chat_started` / `chat_completed`.
- This mirrors the **SPEC-077 R-5 precedent**: the wired staging turn audits
  `agent_role="executor"` with **no new `event_type`** — "the gateway reuses
  `chat_completed`". Same discipline: enrich an existing event rather than widen a closed enum.
- **Flagged as an OQ (§8):** if governance later wants clarification *attribution* ("the
  agent asked X; the operator chose Y") as a first-class audit signal, that needs a **new
  enum value** (`clarification_asked` / `clarification_answered`) plus all six emitters — a
  deliberate contract bump, deferred unless a named governance need appears.

### 3.6 Opt-in posture → **flag-gated toolkit addition; unscoped path byte-identical**

**Recommendation:** `AskUser` is **not** wired into any deployed toolkit by default. It is
added behind an opt-in flag (the SPEC-072 runtime-feature-flag posture), so:

- The **unscoped single-agent chat path stays byte-identical** when the flag is off or the
  agent never calls `AskUser` — no new frame, no new park, no new event handling on the wire.
- The kernel's external-execution branch is inert until an `AskUser` call actually parks a
  reply, exactly as the confirmation branch is inert until a mutating call parks.
- Because `AskUser` is `is_read_only=True` and always-ALLOW, admitting it to a toolkit does
  **not** widen the mutation surface or bypass the gateway — it executes nothing (§5).

### 3.7 v1 feature surface → **full `AskUserParams` shape; `preview` a fast-follow**

**Recommendation:** v1 ships 1–4 questions × 2–4 options, `multi_select`, `header`,
`context`, and the auto-"Other" free-text answer — the complete clarification capability.
The single-select-only **`preview`** field (side-by-side mockup/code/config rendering) is a
**named fast-follow**: it is a portal rendering concern orthogonal to the park/resume
mechanism, and deferring it keeps v1's contract surface minimal (no `preview` field until the
portal component that renders it exists).

## 4. Recommended SPEC-080 shape

**Title (proposed):** *SPEC-080: Agent-Initiated Clarification (a read-only `AskUser`
park/resume beside the HITL confirmation path).*

**Delivers:**
- A **clarification park kind** on the shared registry substrate: the kernel's first
  `RequireExternalExecutionEvent` handler, projecting a question to the wire, registering the
  park, and resuming on an injected `ExternalExecutionResultEvent` (§3.1, §3.2).
- A new v2 SSE frame pair `clarification_request` / `clarification_result`, contract
  **v13 → v14** (additive, platform-owned projection) (§3.3).
- A park-kind-aware 409 guard + answer endpoint, one-park-per-session preserved (§3.4).
- An opt-in, flag-gated `AskUser` toolkit addition; unscoped path byte-identical (§3.6).
- The full `AskUserParams` shape minus `preview` (§3.7).
- A portal clarification card (owner-answerable in-line) in the chat view.

**Reuses verbatim (no change):** the `ConfirmationRegistry` slot / TTL / `peek_parked`;
`expire_confirmation` → `UserInterruptEvent`; the durable-record-for-re-login pattern; the
`ConfirmationCoordinator` seam (a sibling resume branch, not a rewrite); the SPEC-025 R-1
same-turn resume framing.

**Invariants held byte-identical:** the unscoped single-agent chat path; the closed audit
`event_type` enum (23 values, no new type in v1); `execution-request.schema.json`; the
tool-gateway `evaluate()` contract; the deployed confirmation path (SPEC-020/030/031/032) —
the clarification branch is additive beside it.

**Likely home:** the HITL bridging family (SPEC-020/030/031/032 extension); agent-platform
kernel + operator-portal + the v2 contract.

**Likely target version:** a MINOR bump over v0.61.1 (a new operator-facing capability), per
the SPEC-070…079 release-train pattern — pinned only on approval.

## 5. Four-point gate check (SPEC-018)

| Gate point | SPEC-080 posture |
|---|---|
| 1. Deny-by-default policy + audit; tool-gateway the only execution surface | **Holds** — `AskUser` is `is_read_only=True`, always-ALLOW, and **executes nothing** at the gateway (the agent yields the call; there is no tool invocation, no mutation). It does not bypass policy because it is not an action. Audit rides the existing turn events; the enum stays closed (§3.5). |
| 2. Identity via the gateway-forwarded delegated token only | **Holds** — the clarification is answered by the authenticated **session owner** over the existing v2 surface; the resume runs under the same delegated token. No new identity edge, no second token. |
| 3. Read-only operational posture | **Holds** — a clarification mutates nothing; it is strictly *less* than the confirmation path (which gates a mutation). It cannot widen autonomy or admit an action. |
| 4. No agentscope types through the v2 contract | **Holds, with a condition** — the new frames are **platform-owned projections** of `AskUserParams` / `AskUserMetadata`; the agentscope `RequireExternalExecutionEvent` / `ToolCallBlock` / `ExternalExecutionResultEvent` shapes stay kernel-internal (the resume event is injected in-process, never serialized to the wire). The v13 → v14 bump is a platform-owned contract change, not an agentscope leak. |

**Verdict:** `AskUser` **passes** the four-point gate (gate 4 conditioned on the projection
discipline). This is a stronger result than the multi-agent surfaces (`TeamPipeline` /
`A2AAgent` / `GoalPipeline`), which **fail** the gate and stay parked behind ADR-0017 — a
clarification is a read-only HITL companion, not an orchestration or autonomy edge. **No new
ADR is expected:** SPEC-080 composes delivered HITL machinery and adds a read-only park kind;
it touches no control-flow, trust-model, or autonomy ceiling (ADR-0011 / ADR-0017 unchanged).

## 6. Non-Goals (recommended for the spec)

- **Any mutation, approval, or autonomy widening.** A clarification is read-only; it never
  stages, approves, or dispatches an action, and it does not touch the ADR-0017 ceiling.
- **Reusing the SPEC-031 approval lifecycle** — no approver inbox, no distinct-human routing,
  no tier / self-approval gating for a question (§3.1).
- **A new audit `event_type` in v1** — the enum stays closed; governance attribution is a
  deferred OQ (§3.5, §8).
- **Cross-surface / owner-side answer sync (SPEC-032-style)** in v1 — the owner answers
  in-line; a second-surface answer is a fast-follow OQ (§8).
- **The `preview` field** in v1 — a portal-rendering fast-follow (§3.7).
- **Leaking agentscope event/tool types onto the wire** — projections only (gate 4).
- **Default-on wiring** — `AskUser` stays opt-in behind a flag; the unscoped path is
  byte-identical (§3.6).
- **Multi-park concurrency** — one park per session (a confirmation *or* a clarification,
  never both) is preserved, not relaxed (§3.4).

## 7. Go / no-go and next decision

- **Go — for a `draft` SPEC-080**, on operator approval. The backlog's questions are resolved
  with recommendations (§3): a parallel read-only park kind on the shared substrate; the
  external-execution event pair with the kernel's first handler; a v13 → v14 additive
  platform-owned frame pair; a park-kind-aware 409 guard; a closed audit enum (no new type);
  opt-in wiring; and a bounded v1 feature surface. It **passes** the four-point gate and needs
  **no new ADR**. It is decision-complete enough to draft.
- **No implementation is authorized by this memo.** Per SDD discipline, promotion to `draft`
  (then OQ ratification → `approved` → plan/tasks authoring) is the operator's call; approval
  authorizes implementation to *begin*, not to merge, commit/push, deploy, or version-bump
  (each a separate gate).
- **Sequencing note:** the roadmap's named multi-agent fast-follow **R2 (multi-step
  remediation plans)** is a *mutation-path* extension of SPEC-078; this clarification park is
  an independent *read-only HITL* extension. They do not conflict and share no code path; the
  operator may sequence either first.

## 8. Ratification asks (Open Questions for the operator)

1. **Park model (§3.1):** approve a **parallel park kind on the shared substrate** (reuse the
   registry/TTL/guard/interrupt + durable-record pattern; **not** the SPEC-031 approval
   lifecycle; **not** SPEC-032 owner-side sync in v1)?
2. **Contract (§3.3):** approve the additive **v13 → v14** `clarification_request` /
   `clarification_result` frame pair as platform-owned projections?
3. **Audit (§3.5):** approve **no new `event_type`** in v1 (ride `chat_started` /
   `chat_completed`), or does governance want a first-class `clarification_asked` /
   `clarification_answered` signal (a deliberate enum bump + six-emitter change)?
4. **Guard (§3.4):** approve the **park-kind-aware 409** + preserved one-park-per-session
   mutual exclusion (a session holds a confirmation *or* a clarification, never both)?
5. **Answer surface (§3.1, §6):** is **owner-in-line** answering sufficient for v1, or is a
   cross-surface / second-tab answer (SPEC-032-style sync) a v1 requirement?
6. **Feature surface (§3.7):** approve shipping the full `AskUserParams` shape minus
   `preview` in v1, with `preview` a named fast-follow?
7. **Wiring (§3.6):** approve **opt-in, flag-gated** wiring with the unscoped path
   byte-identical, and no default-on flip in v1?

## Changelog

- 2026-11-24: initial design exploration. Resolved the Exploration Backlog's
  "Agent-initiated clarification (`AskUser` tool)" questions against the delivered HITL
  substrate (SPEC-020/030/031/032), the v0.59.0 `ConfirmationCoordinator` seam, the v2
  contract (v13), and the closed 23-value audit enum, at v0.61.1 (`c84de0c1`). Recommended: a
  parallel **read-only park kind** on the **shared** registry/TTL/guard/interrupt substrate
  (not the SPEC-031 approval lifecycle, not SPEC-032 owner-side sync in v1); the agentscope
  **`RequireExternalExecutionEvent` → `ExternalExecutionResultEvent`** mechanism with the
  kernel's **first** external-execution handler (today it handles only
  `RequireUserConfirmEvent`, `kernel_confirmations.py:116-119`); an additive **v13 → v14**
  platform-owned `clarification_request` / `clarification_result` frame pair; a
  **park-kind-aware 409** guard preserving one-park-per-session; **no new audit `event_type`**
  in v1 (SPEC-077 R-5 precedent); **opt-in flag-gated** wiring with the unscoped path
  byte-identical; and the full `AskUserParams` shape minus `preview`. Scored the SPEC-018
  four-point gate: **passes** (gate 4 conditioned on projection discipline); **no new ADR**
  expected. Recorded non-goals and seven ratification asks. Assessment only: no runtime
  change, no ADR opened, no SPEC number assigned, no implementation, no deployment.
- 2026-11-24: **promoted to `draft` [SPEC-080](../specs/SPEC-080-agent-initiated-clarification/spec.md)**
  on operator approval. The seven §8 ratification asks are carried into the draft spec as its Open
  Questions (recommended, not yet ratified); the memo body is frozen per the Tier-1 lifecycle.
  Promotion authorizes no implementation, merge, commit/push, deploy, or version bump.
