# SPEC-080 Plan: Agent-Initiated Clarification (a read-only `AskUser` park/resume beside the HITL confirmation path)

> **Binding as of approval 2026-11-25** — all seven Open Questions ratified by the operator exactly
> as recommended. The design basis is the operator-approved
> [AskUser clarification spike](../../workspace/ask-user-clarification-spike.md) §3; the ratified
> resolutions are recorded in [spec.md](spec.md) **Open Questions**. Composes delivered HITL
> machinery and adds a *read-only* park kind; **no new ADR**
> ([ADR-0011](../../adr/0011-composition-carries-no-authority.md) /
> [ADR-0017](../../adr/0017-bounded-read-only-multi-agent-orchestration.md) unchanged).

## Approach

A clarification is a **second park kind** on the **shared** park / resume / expire substrate, not a
confirmation and not a mutation path. The work groups into four stages: (1) the wire contract
(**v13 → v14**), (2) the park substrate + the kernel's **first external-execution handler**, (3) the
park-kind-aware guard + answer endpoint + **opt-in flag-gated** toolkit wiring, and (4) the portal
card + evidence. Every stage holds two invariants byte-identical: the **unscoped single-agent chat
path** (the external-execution branch is inert until an `AskUser` call actually parks a reply) and the
**closed audit `event_type` enum** (a clarification rides the existing turn audit). The deployed
confirmation path (SPEC-020/030/031/032) is untouched — the clarification branch is additive beside it.

## Design Per Requirement

### R-1: A clarification park *kind* on the shared substrate (OQ-1)

- **affected files:** `services/hitl_confirmations.py` (`PendingConfirmation` `:51`,
  `ConfirmationRegistry` `:584`, `register` `:600`, module singleton `:728`),
  `services/confirmation_records.py` (the SPEC-031 durable store), `services/kernel_confirmations.py`.
- **chosen approach:** add a `park_kind` discriminator (`"confirmation"` default | `"clarification"`)
  to `PendingConfirmation` and a `park_kind` param to `register(...)`. The `_by_session`
  one-per-session slot holds **either** kind, so mutual exclusion is **structural**, not guarded. A
  parked clarification carries the projected questions + a `clarification_id` (the analogue of
  `confirm_id`). Durable re-login survival **extends** the SPEC-031 confirmation-record store with the
  same `park_kind` discriminator (a small additive migration) — reusing the store, not forking it.
- **alternatives rejected:** a parallel `PendingClarification` registry (duplicates the TTL/guard/slot
  and risks two parks per session); forcing a clarification through the SPEC-031 approval lifecycle
  (invents an approver for a question — no distinct-human routing, no tier, no self-approval concern).

### R-2: The kernel's first external-execution handler (OQ-1)

- **affected files:** `services/kernel_confirmations.py` (`ConfirmationCoordinator`; the
  `RequireUserConfirmEvent` branch `:116-119`, `resume_confirmation` `:427` → `_resume_confirmation`
  `:465`), `runtime_kernel.py` (event dispatch), `services/kernel_streaming.py` (`TurnStreamer`).
- **chosen approach:** beside the confirmation branch, add a `RequireExternalExecutionEvent` branch
  that detects the parked `AskUser` tool call, projects `AskUserParams` → the `clarification_request`
  wire frame (R-3), registers the park with `kind="clarification"` (R-1), and ends the stream
  **without** `message_end` (as a confirmation park does). Add `resume_clarification(...)` as a
  **sibling** to `resume_confirmation(...)`: it builds `execution_results: List[ToolResultBlock]` — one
  block whose `output` is prose for the model and whose `metadata` is `AskUserMetadata{answers}` — and
  injects `ExternalExecutionResultEvent{reply_id, execution_results}` to re-drive the parked reply in
  the **same assistant turn** ([SPEC-025](../SPEC-025-evidence-persistence-in-transcripts/spec.md) R-1).
  `UserInterruptEvent{reply_id}` aborts either kind, so TTL expiry + operator cancel reuse
  `expire_confirmation`.
- **alternatives rejected:** reusing the confirmation event pair (agentscope parks an external tool
  with a *distinct* pair; the payloads differ); serializing the agentscope event to the wire (gate 4 —
  the resume event is injected **in-process**, never serialized).

### R-3: A v2 SSE `clarification_request` / `clarification_result` frame pair, v13 → v14 (OQ-2)

- **affected files:** [`agent-stream-event.schema.json`](../../../shared/shared-contracts/schemas/agent-stream-event.schema.json),
  agent-platform `schemas/v2.py`, platform-gateway `services/gateway_service.py`, the contract-parity suite.
- **chosen approach:** add `clarification_request` (`clarification_id` + `questions[]{question, header,
  context?, multi_select, options[]{label, description}}`) and `clarification_result`
  (`clarification_id` + `answers[]{question, selected[], other?}` + a closed `status`: `answered` |
  `expired` | `interrupted`) to the `type` enum + their field schemas; bump the title **v13 → v14**;
  `additionalProperties: false` holds; **no existing frame changes**. Mirror both in the agent-platform
  pydantic models (closed `Literal` enum) and the gateway passthrough model, kept in **lockstep** (the
  closed-enum-plus-`Literal` discipline). The auto-"Other" affordance is a **client** behavior, not a
  wire option; `preview` is deferred (R-6).
- **alternatives rejected:** reusing `authorization_required` (SPEC-070 OQ-7 makes it a *non-resuming*
  signal — a clarification **is** a park-resume); a breaking v14 (additive only).

### R-4: Park-kind-aware 409 guard + answer endpoint (OQ-4)

- **affected files:** `api/v2/routes.py` (`_reject_if_parked` `:229`, peek `:246`, 409 `:264-272`, chat
  entries `:359`/`:501`), a new answer endpoint, the gateway proxy route.
- **chosen approach:** `_reject_if_parked` peeks the one slot and **names the parked kind** in the 409
  ("clarification pending: answer or expire the parked question" vs the confirmation wording). Add
  `POST /api/v2/sessions/{id}/clarification/answer` (gateway `POST /api/v1/...` proxy) validating the
  answer against the parked questions and calling `resume_clarification`; race-resilient via the
  SPEC-031 `already_resolved` posture. The SPEC-022 R-1 `has_pending` badge covers both kinds (same slot).
- **alternatives rejected:** relaxing to multi-park concurrency (OQ-4 preserves one-park-per-session).

### R-5: Opt-in, flag-gated wiring; the unscoped path stays byte-identical (OQ-7)

- **affected files:** runtime settings/config, `services/kernel_toolkits.py` (`ToolkitAssembler` /
  `_ensure_toolkit`), the [SPEC-072](../SPEC-072-auto-routing-and-platform-feature-flags/spec.md)
  `runtime:flags` inventory, the dev overlay.
- **chosen approach:** admit `AskUser` to a toolkit **only** behind a default-off runtime feature flag
  (the SPEC-072 posture) — `AGENT_ASKUSER_ENABLED`. With the flag off (or the agent never calling
  `AskUser`) the **unscoped single-agent chat path is byte-identical** — no new frame, park, or event
  handling. The kernel's external-execution branch stays **inert** until an `AskUser` call parks a
  reply. Because `AskUser` is `is_read_only=True` + always-ALLOW, admitting it does **not** widen the
  mutation surface or bypass the gateway — it executes nothing.
- **alternatives rejected:** default-on wiring (OQ-7 keeps v1 opt-in; a default-on flip is a separate
  measurement-gated decision).

### R-6: The v1 `AskUser` feature surface (full shape minus `preview`) (OQ-6)

- **affected files:** the R-2 projection code, the R-3 schema.
- **chosen approach:** project the full `AskUserParams` — `questions[1-4]{question, header ≤12,
  context?, multi_select, options[2-4]{label, description}}` — and round-trip `AskUserMetadata{answers}`
  with `multi_select` + the auto-"Other" free text; validation mirrors agentscope's constraints.
  `preview` (single-select-only side-by-side rendering) is a **named fast-follow**: no `preview` field
  in v14 until the portal component that renders it exists.

### R-7: A portal clarification card, owner-answerable in-line (OQ-5)

- **affected files:** operator-portal `chat/ChatView.tsx`, a `chat/ClarificationCard.tsx` sibling to the
  SPEC-031 `chat/ConfirmationCard.tsx`, `stream/useChatStream.ts` (the v14 SSE adapter), portal Vitest tests.
- **chosen approach:** render a parked clarification as an **owner-answerable** card in the chat view
  (questions, options, `multi_select`, an "Other" free-text affordance), submit to the R-4 answer
  endpoint, and render the resumed same-turn stream. The answered card re-renders from
  `clarification_result`, or from the durable record on re-login (R-1). **No** approver-inbox surface
  (owner-answered in-line).
- **alternatives rejected:** cross-surface / second-tab answer sync (SPEC-032-style) — a deferred
  fast-follow (OQ-5), not v1.

### R-8: Audit rides the existing turn events; the enum stays closed (OQ-3)

- **affected files:** none new (verify no emitter change); the audit-contract drift guard.
- **chosen approach:** a clarification is read-only, non-mutating, and carries no security decision, so
  it rides the existing `chat_started` / `chat_completed` turn audit — **no new `event_type`** (the enum
  stays closed at 23), mirroring the [SPEC-077](../SPEC-077-operator-diagnose-to-act-bridge/spec.md) R-5
  precedent. The audit-contract test asserts the enum is unchanged. Governance attribution
  (`clarification_asked` / `clarification_answered`) is deferred (OQ-3) pending a named need.

## Sequencing And Dependencies

1. **Contract v14 (R-3)** — schema + agent-platform/gateway models + parity test. Depends on nothing.
2. **Park substrate (R-1)** — `park_kind` discriminator + durable-store extension/migration. Depends on
   nothing (the `clarification_id` shape aligns with R-3).
3. **Kernel handler (R-2)** — depends on stages 1–2.
4. **Guard + answer endpoint (R-4)** — depends on stages 1–3.
5. **Flag-gated toolkit + v1 surface (R-5, R-6)** — depends on stage 3.
6. **Portal card (R-7)** — depends on stages 1 and 4.
7. **Audit + evidence (R-8)** — verified across all stages; the four-point-gate mapping + the gated
   live-check land last.

## Test Strategy

- **unit tests:** the kernel external-execution branch (park → project → register → resume-by-injection;
  expire/cancel via `UserInterruptEvent`); the registry `park_kind` slot + mutual exclusion; the 409
  guard for **both** kinds; the answer endpoint's race-resilience (`already_resolved`); flag-off ⇒
  byte-identical unscoped path; the `AskUserParams` projection + validation (R-6).
- **contract tests:** `agent-stream-event` **v14** parity (gateway model ↔ schema); the audit
  `event_type` enum-unchanged drift guard; `additionalProperties: false` holds.
- **integration / overlay validation:** the dev overlay flag render (`AGENT_ASKUSER_ENABLED`); a **gated
  billable live-check** mirroring the confirmation live-check (park a clarification → the owner answers
  → same-turn resume; assert **no** mutation, **no** dispatch, **no** auto-approval); the four-point-gate
  mapping asserted per point.

## Rollout And Migration

- **deployment / configuration:** a default-off runtime flag (`AGENT_ASKUSER_ENABLED`); the dev overlay
  opts in for validation. **No default-on flip in v1.**
- **migration:** an additive extension to the SPEC-031 durable confirmation-record store (a `park_kind`
  discriminator column) — backward compatible; existing confirmation rows default to `"confirmation"`.
- **backward compatibility:** v14 is additive; older clients ignore an unknown `type` (the
  `secret_delivery`-at-v12 / `authorization_required`-at-v13 posture); no existing frame changes; the
  deployed confirmation path (SPEC-020/030/031/032) is untouched.
- **rollback:** flag off — the external-execution branch is inert and the unscoped path is
  byte-identical; the additive migration needs no rollback.
