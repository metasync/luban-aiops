# SPEC-080: Agent-Initiated Clarification (a read-only `AskUser` park/resume beside the HITL confirmation path)

## Status

- status: `approved`
- owner: chi
- created: 2026-11-24
- promoted from: the [AskUser clarification spike](../../workspace/ask-user-clarification-spike.md),
  reviewed by the operator and **promoted to `draft` 2026-11-24**. The memo's seven ratification
  asks (§8) are carried below as **Open Questions** and were **ratified exactly as recommended
  2026-11-25** (`draft → approved`), on which the binding [plan](plan.md) / [tasks](tasks.md) were
  authored (per the README Spec Structure rule and the SPEC-066/069/076/077/078 pattern).
- approved: **2026-11-25** — the operator ratified all seven Open Questions **exactly as recommended**
  (`draft → approved`). Approval authorizes implementation to *begin* — **not** to merge, commit/push,
  deploy, or version-bump (each a separate gate).
- release slice: the **HITL-bridging family** (an extension of
  [SPEC-020](../SPEC-020-hitl-confirmation-bridging/spec.md)/[SPEC-030](../SPEC-030-require-approval-policy-semantics/spec.md)/[SPEC-031](../SPEC-031-approval-inbox-persistent-confirmation/spec.md)/[SPEC-032](../SPEC-032-owner-side-live-decision-sync/spec.md)),
  raised from the [Exploration Backlog](../../agentic-aiops-platform/delivery-roadmap.md#exploration-backlog)
  **"Agent-initiated clarification (`AskUser` tool)"** row (2026-11-01, from the agentscope 2.0.9
  headline-feature review; recorded **not adopted** in the
  [2.0.11 dependency-refresh note](../../agentic-aiops-platform/release-notes/2026-10-31-dependency-refresh-agentscope-2-0-11.md)
  and kept out of scope by [SPEC-071](../SPEC-071-agentscope-model-router/spec.md) Non-Goals).
  Target **v0.62.0** — a **MINOR** bump over v0.61.1 (a new operator-facing capability), per the
  SPEC-070…079 release-train pattern, **pinned on approval 2026-11-25**.
- related ADRs: **none new** — composes delivered HITL machinery and adds a *read-only* park kind;
  touches no control-flow, trust-model, or autonomy ceiling.
  [ADR-0011](../../adr/0011-composition-carries-no-authority.md) (composition carries no authority)
  and [ADR-0017](../../adr/0017-bounded-read-only-multi-agent-orchestration.md) (the autonomy
  ceiling) are **unchanged** — a clarification carries no authority and admits no action.

## Summary

Add a **second, read-only HITL park kind** — *agent-initiated clarification* — beside the existing
mutating *confirmation* park, so the agent can pose a bounded multiple-choice question mid-turn
(agentscope's `AskUser` builtin) and resume on the owner's answer. It **composes** the delivered
park / resume / expire substrate (registry, TTL, 409 guard, `UserInterruptEvent`, the v0.59.0
`ConfirmationCoordinator` seam) and rides agentscope's **external-execution** event pair, which the
kernel does not handle today. A clarification mutates nothing, carries no authority, and cannot
widen the read-only posture.

## Motivation

- **What is missing.** The platform has exactly one HITL park today: the *mutating* confirmation
  ([SPEC-020](../SPEC-020-hitl-confirmation-bridging/spec.md)/[SPEC-030](../SPEC-030-require-approval-policy-semantics/spec.md)/[SPEC-031](../SPEC-031-approval-inbox-persistent-confirmation/spec.md)).
  The agent has **no** way to ask the operator a *question* — "which cluster?", "restart or
  rollback?", "include the sidecar?" — and resume on the answer. It can only proceed, or park a
  mutation for approval.
- **Evidence.** The agentscope 2.0.9 headline-feature review raised `AskUser` (2026-11-01); the
  [2.0.11 refresh](../../agentic-aiops-platform/release-notes/2026-10-31-dependency-refresh-agentscope-2-0-11.md)
  recorded it **deferred** ("needs a new v2 stream frame plus a resume path"), and
  [SPEC-071](../SPEC-071-agentscope-model-router/spec.md) kept it a Non-Goal. The
  [spike](../../workspace/ask-user-clarification-spike.md) is the deferred design work: a repo grep
  finds **zero** platform references to `AskUser`, `RequireExternalExecutionEvent`, or
  `ExternalExecutionResultEvent`, and the kernel handles **only** `RequireUserConfirmEvent`
  (`kernel_confirmations.py:116-119`).
- **Why now.** The spike resolves the backlog's two parked questions (reuse-vs-parallel; the 409
  interaction) and scores the [SPEC-018](../SPEC-018-kernel-middleware-alignment/spec.md) four-point
  adoption gate as **passes** (gate 4 conditioned on projection discipline), with **no new ADR**. It
  is decision-complete enough to draft; the remaining choices are the seven Open Questions below.

## Requirements

> These requirements are **stable as of approval (2026-11-25)**: the seven Open Questions below were
> ratified exactly as recommended and are recorded as the resolved design basis. Requirement IDs
> (`R-1`…) are now stable and map to the binding [tasks](tasks.md).

### R-1: A clarification park *kind* on the shared substrate

A clarification is a **second park kind**, not a confirmation: it **reuses the mechanism** (the
per-session `ConfirmationRegistry` slot, the park TTL, the `peek_parked`-driven 409 guard, the
`expire_confirmation` → `UserInterruptEvent` abort, the resume-injects-an-event pattern, and the
durable-record-for-re-login *pattern*) but **not the SPEC-031 approval lifecycle** (no approver
inbox, no distinct-human routing, no tier / self-approval gating — a clarification has no approver;
the **session owner answers in-line** and it mutates nothing). A `PendingConfirmation`-analogue
carries a `park_kind` discriminator (`"confirmation"` | `"clarification"`); one registry, one guard,
one TTL, two resume branches.

Acceptance criteria:

- A parked clarification and a parked confirmation occupy the **same** one-per-session registry
  slot; the resume path branches on `park_kind`.
- A parked clarification survives a page refresh / re-login via the durable-record pattern (as a
  SPEC-031 card does), and is answerable by the session owner.
- No approval inbox entry, no distinct-human requirement, and no self-approval check is created for
  a clarification.

### R-2: The kernel's first external-execution handler

The kernel catches agentscope's `RequireExternalExecutionEvent{reply_id, tool_calls}` (emitted when
the model calls `AskUser`, which parks the reply), projects the question to the wire (R-3),
registers the park (R-1), and ends the stream **without** `message_end` (as a confirmation park
does). The answer endpoint builds `execution_results: List[ToolResultBlock]` — one block whose
`output` is prose for the model and whose `metadata` is `AskUserMetadata{answers}` — and injects
`ExternalExecutionResultEvent{reply_id, execution_results}` to resume. The resumed stream follows
the v2 contract and belongs to the **same assistant turn**
([SPEC-025](../SPEC-025-evidence-persistence-in-transcripts/spec.md) R-1).

Acceptance criteria:

- A new kernel branch handles `RequireExternalExecutionEvent` **without** disturbing the existing
  `RequireUserConfirmEvent` branch (`kernel_confirmations.py:116-119`).
- `UserInterruptEvent{reply_id}` aborts a parked clarification identically (TTL expiry and operator
  cancel come for free — agentscope already scopes it to both park kinds).
- The resume re-drives the parked reply in-process; no agentscope event object is serialized to the
  wire.

### R-3: A v2 SSE `clarification_request` / `clarification_result` frame pair (v13 → v14)

Add two frames to [`agent-stream-event.schema.json`](../../../shared/shared-contracts/schemas/agent-stream-event.schema.json)
as an **additive** bump **v13 → v14**, as **platform-owned projections** of `AskUserParams` /
`AskUserMetadata` — never the agentscope `RequireExternalExecutionEvent` / `ToolCallBlock` /
`ExternalExecutionResultEvent` shapes.

- **`clarification_request`** (park frame): `clarification_id` (correlator, analogous to
  `confirm_id`) and a `questions` array — each `{question, header, context?, multi_select, options:
  [{label, description}]}`. The auto-"Other" affordance is a **client** behavior, not a wire option.
- **`clarification_result`** (resume-echo frame): `clarification_id`, the `answers` — each
  `{question, selected: [labels], other?}` — and a closed `status` (`answered`, `expired`,
  `interrupted`), mirroring `confirmation_result`.

Acceptance criteria:

- Two new `type` enum values plus their fields; `additionalProperties: false` holds; **no existing
  frame changes**; older clients ignore an unknown `type` (the `secret_delivery`-at-v12 /
  `authorization_required`-at-v13 posture).
- The frames are **not** a reuse of `authorization_required` (SPEC-070 OQ-7 — a *non-resuming*
  signal); a clarification **is** a park-resume and needs its own resuming pair.
- A contract-parity test binds the gateway model to the v14 schema.

### R-4: Park-kind-aware 409 guard + answer endpoint; one-park-per-session preserved

`_reject_if_parked` (`api/v2/routes.py:229`) already peeks the one per-session slot; a new chat turn
while a clarification is parked is rejected **identically**, with a message naming the parked kind
("clarification pending: answer or expire the parked question"). A TTL-expired clarification is
closed via the same `expire_confirmation` → `UserInterruptEvent` path, then the turn proceeds. A
session **cannot** hold a confirmation *and* a clarification at once (one slot) — mutual exclusion
is structural, not guarded.

Acceptance criteria:

- A second chat turn while any park is pending returns **409** naming the parked kind.
- The SPEC-022 R-1 `has_pending` session badge covers both kinds (it reads the same slot).
- An answer endpoint resumes the parked clarification; a stale/duplicate answer is race-resilient
  (the SPEC-031 `already_resolved` posture).

### R-5: Opt-in, flag-gated wiring; the unscoped path stays byte-identical

`AskUser` is **not** wired into any deployed toolkit by default; it is added behind an opt-in flag
(the [SPEC-072](../SPEC-072-auto-routing-and-platform-feature-flags/spec.md) runtime-feature-flag
posture). When the flag is off, or the agent never calls `AskUser`, the **unscoped single-agent chat
path stays byte-identical** — no new frame, no new park, no new event handling on the wire. Because
`AskUser` is `is_read_only=True` and always-ALLOW, admitting it to a toolkit does **not** widen the
mutation surface or bypass the gateway — it executes nothing.

Acceptance criteria:

- With the flag off, the deployed chat path emits a byte-identical stream and parks nothing new.
- The kernel's external-execution branch is inert until an `AskUser` call actually parks a reply.
- The flag defaults **off**; no default-on flip ships in v1.

### R-6: The v1 `AskUser` feature surface (full shape minus `preview`)

v1 ships the complete clarification capability: **1–4 questions** × **2–4 options**, `multi_select`,
`header` (≤12 chars), `context`, and the auto-"Other" free-text answer. The single-select-only
**`preview`** field (side-by-side mockup / code / config rendering) is a **named fast-follow** — a
portal-rendering concern orthogonal to the park/resume mechanism; deferring it keeps v1's contract
surface minimal.

Acceptance criteria:

- The wire `questions`/`options` shape projects the full `AskUserParams` minus `preview`.
- `multi_select` and the auto-"Other" free-text answer round-trip through `clarification_result`.
- No `preview` field exists in v14 (added only with the portal component that renders it).

### R-7: A portal clarification card, owner-answerable in-line

The operator-portal chat view renders a parked clarification as a card the **session owner** answers
in-line (question(s), options, `multi_select`, and an "Other" free-text affordance), submits the
answer to the resume endpoint (R-4), and renders the resumed same-turn stream. The card survives a
page refresh (R-1 durable record).

Acceptance criteria:

- The card renders from `clarification_request` and posts an answer that resumes the turn.
- The answered card re-renders from `clarification_result` (or the durable record on re-login).
- No approver inbox surface is added (a clarification is owner-answered, not approver-routed).

### R-8: Audit rides the existing turn events; the enum stays closed

A clarification is **read-only, non-mutating, and carries no security decision**, so it rides the
existing `chat_started` / `chat_completed` turn audit — **no new `event_type`** in v1
([`audit-event.schema.json`](../../../shared/shared-contracts/schemas/audit-event.schema.json) stays
at its closed **23** values). This mirrors the
[SPEC-077](../SPEC-077-operator-diagnose-to-act-bridge/spec.md) R-5 precedent ("reuse
`chat_completed`; the enum stays closed"). Governance attribution is an Open Question (OQ-3).

Acceptance criteria:

- No new value is added to the audit `event_type` enum in v1.
- The parking/resuming turn is bracketed by the existing `chat_started` / `chat_completed` events.
- The audit-contract drift guard still passes (enum unchanged).

## Non-Goals

- **Any mutation, approval, or autonomy widening.** A clarification is read-only; it never stages,
  approves, or dispatches an action, and does not touch the ADR-0017 ceiling.
- **Reusing the SPEC-031 approval lifecycle** — no approver inbox, no distinct-human routing, no
  tier / self-approval gating for a question (R-1).
- **A new audit `event_type` in v1** — the enum stays closed; governance attribution is OQ-3.
- **Cross-surface / owner-side answer sync (SPEC-032-style) in v1** — the owner answers in-line; a
  second-surface answer is OQ-5.
- **The `preview` field in v1** — a portal-rendering fast-follow (R-6).
- **Leaking agentscope event / tool types onto the wire** — platform-owned projections only (gate 4).
- **Default-on wiring** — `AskUser` stays opt-in behind a flag; the unscoped path is byte-identical
  (R-5).
- **Multi-park concurrency** — one park per session (a confirmation *or* a clarification, never
  both) is preserved, not relaxed (R-4).

## Impact

- products touched: `products/agent-platform` (kernel external-execution branch beside
  `kernel_confirmations.py`; the `api/v2` answer endpoint + park-kind-aware 409 guard),
  `products/operator-portal` (the chat-view clarification card), `products/platform-gateway` (the v2
  proxy passthrough for the new frames/endpoint).
- contracts touched: [`agent-stream-event.schema.json`](../../../shared/shared-contracts/schemas/agent-stream-event.schema.json)
  **v13 → v14** (additive: two frames). [`audit-event.schema.json`](../../../shared/shared-contracts/schemas/audit-event.schema.json)
  **unchanged** (enum stays closed at 23). `execution-request.schema.json` **unchanged**.
- identity / policy / audit / execution safety impact: **none** — read-only; no new identity edge
  (the owner answers over the existing v2 surface under the same delegated token); no new policy
  action; no new audit `event_type`; no execution / mutation path. The tool-gateway `evaluate()`
  contract and the deployed confirmation path (SPEC-020/030/031/032) are unchanged — the
  clarification branch is **additive beside** them.
- four-point gate ([SPEC-018](../SPEC-018-kernel-middleware-alignment/spec.md)): **passes** — (1)
  deny-by-default + audit held (`AskUser` executes nothing; the enum stays closed); (2) identity via
  the gateway-forwarded delegated token only; (3) read-only posture preserved (strictly *less* than
  the confirmation path); (4) no agentscope types on the wire — the new frames are platform-owned
  projections and the resume event is injected in-process (gate 4 conditioned on that projection
  discipline).
- living state docs to update on delivery: the operator/user guide layer (`docs/guides/`) for the
  clarification card + flag; the [Exploration Backlog](../../agentic-aiops-platform/delivery-roadmap.md#exploration-backlog)
  row (mark adopted); a dated release note; `CHANGELOG.md`; the Spec Index row status flip.

## Open Questions

> All seven were **ratified by the operator exactly as recommended 2026-11-25** (`draft → approved`),
> on which the binding [plan](plan.md) / [tasks](tasks.md) were authored. Each is recorded below as the
> **resolved design basis** (per the SPEC-077/078 pattern); the section is retained for traceability
> rather than emptied.

- **OQ-1 — Park model (R-1).** Ratify a **parallel park kind on the shared substrate** (reuse the
  registry / TTL / guard / interrupt + the durable-record *pattern*; **not** the SPEC-031 approval
  lifecycle; **not** SPEC-032 owner-side sync in v1)? **Resolved (ratified 2026-11-25): yes** — one
  registry slot with a `park_kind` discriminator; the approval lifecycle is not reused (a clarification
  has no approver; the owner answers in-line).
- **OQ-2 — Contract (R-3).** Ratify the additive **v13 → v14** `clarification_request` /
  `clarification_result` frame pair as platform-owned projections? **Resolved (ratified 2026-11-25):
  yes** — two new `type` values; `additionalProperties: false` holds; no existing frame changes.
- **OQ-3 — Audit (R-8).** Ratify **no new `event_type`** in v1 (ride `chat_started` /
  `chat_completed`), or does governance want a first-class `clarification_asked` /
  `clarification_answered` signal (a deliberate enum bump + six-emitter change)? **Resolved (ratified
  2026-11-25): no new type in v1** — the enum stays closed at 23 (the SPEC-077 R-5 precedent); revisit
  only on a named governance need.
- **OQ-4 — Guard (R-4).** Ratify the **park-kind-aware 409** + preserved one-park-per-session mutual
  exclusion (a session holds a confirmation *or* a clarification, never both)? **Resolved (ratified
  2026-11-25): yes** — mutual exclusion is structural via the shared slot.
- **OQ-5 — Answer surface (R-1, R-7).** Is **owner-in-line** answering sufficient for v1, or is a
  cross-surface / second-tab answer (SPEC-032-style sync) a v1 requirement? **Resolved (ratified
  2026-11-25): owner-in-line for v1** — cross-surface sync is a named fast-follow.
- **OQ-6 — Feature surface (R-6).** Ratify shipping the full `AskUserParams` shape **minus
  `preview`** in v1, with `preview` a named fast-follow? **Resolved (ratified 2026-11-25): yes** —
  `preview` is deferred until the portal component that renders it exists.
- **OQ-7 — Wiring (R-5).** Ratify **opt-in, flag-gated** wiring with the unscoped path
  byte-identical, and **no default-on flip** in v1? **Resolved (ratified 2026-11-25): yes** —
  `AGENT_ASKUSER_ENABLED` defaults off; a default-on flip is a separate measurement-gated decision.

## Changelog

- 2026-11-24: created as `draft`, promoted from the operator-reviewed
  [AskUser clarification spike](../../workspace/ask-user-clarification-spike.md). Carries the
  recommended shape (a parallel read-only park kind on the shared registry/TTL/guard/interrupt
  substrate; the kernel's first `RequireExternalExecutionEvent` → `ExternalExecutionResultEvent`
  handler; an additive v13 → v14 platform-owned `clarification_request` / `clarification_result`
  frame pair; a park-kind-aware 409 guard preserving one-park-per-session; a closed audit enum with
  no new `event_type` in v1; opt-in flag-gated wiring with the unscoped path byte-identical; and the
  full `AskUserParams` shape minus `preview`) as R-1…R-8, and the spike's seven ratification asks as
  **Open Questions** (recommended, **not yet ratified**). Four-point gate scored **passes**; **no new
  ADR**. Provisional target v0.62.0, pinned only on approval. Promotion authorizes no implementation.
- 2026-11-25: **approved** — the operator ratified all seven Open Questions **exactly as recommended**
  (`draft → approved`); the seven are recorded above as the resolved design basis and R-1…R-8 are now
  stable. The binding [plan](plan.md) / [tasks](tasks.md) are authored (contract-first sequencing:
  v14 frames → park substrate → the kernel external-execution handler → the guard/answer endpoint →
  flag-gated toolkit + v1 surface → the portal card → audit/evidence). Target **v0.62.0** pinned on
  approval. Approval authorizes implementation to *begin* — not to merge, commit/push, deploy, or
  version-bump (each a separate gate).
