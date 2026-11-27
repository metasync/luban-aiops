# v0.62.0 — Agent-Initiated Clarification (SPEC-080)

Date: 2026-11-27
Release type: minor (a second, **read-only** HITL park *kind* beside the mutating
confirmation — the agent can pose a bounded multiple-choice question mid-turn and
resume on the **session owner's** in-line answer. Opt-in behind
`AGENT_ASKUSER_ENABLED` (default **off**). Additive only: the `agent-stream-event`
contract bumps **v13 → v14** with two platform-owned frames; the audit
`event_type` enum stays **closed at 23**; `execution-request.schema.json` is
byte-unchanged. With the flag off — the default — the unscoped single-agent chat
path stays **byte-identical**.)

## Summary

This release ships
[SPEC-080](../../specs/SPEC-080-agent-initiated-clarification/spec.md), the
agent-initiated clarification capability raised by the agentscope 2.0.9 `AskUser`
headline-feature review and designed in
[the AskUser clarification memo](../../workspace/ask-user-clarification-spike.md).
Until now the platform had exactly one HITL park — the *mutating* confirmation
(SPEC-020/030/031) — and the agent had no way to ask the operator a *question*
(“which cluster?”, “restart or rollback?”, “include the sidecar?”) and resume on
the answer.

A clarification is a **second park kind**, not a confirmation. It **reuses the
mechanism** of the delivered park / resume / expire substrate — the per-session
`ConfirmationRegistry` slot, the park TTL, the `peek_parked`-driven 409 guard, the
`expire_confirmation` → `UserInterruptEvent` abort, the resume-injects-an-event
pattern, and the durable-record-for-re-login pattern (the v0.59.0
`ConfirmationCoordinator` seam) — but **not** the SPEC-031 approval lifecycle: a
clarification has **no approver, no inbox entry, no distinct-human routing, and no
tier / self-approval gate**. The **session owner answers in-line** and it mutates
nothing. It rides agentscope's **external-execution** event pair
(`RequireExternalExecutionEvent` → `ExternalExecutionResultEvent`), which the kernel
did not handle before (it handled only `RequireUserConfirmEvent`).

**Read-only by construction.** `AskUser` is `is_read_only=True` and always-ALLOW:
admitting it to a toolkit executes nothing, mints no new principal / claim /
credential, and cannot widen the mutation surface or bypass the gateway. A
clarification is strictly *less* than the confirmation path. It carries no security
decision, so the parking/resuming turn rides the existing `chat_started` /
`chat_completed` audit — **no new `event_type`** (the SPEC-077 R-5 precedent);
governance attribution (`clarification_asked` / `clarification_answered`) is
deferred.

## What shipped

- **R-1 — A clarification park *kind* on the shared substrate.** A `park_kind`
  discriminator (`"confirmation"` | `"clarification"`) on the parked record; one
  registry slot, one guard, one TTL, two resume branches. A parked clarification
  survives a refresh / re-login via the durable record and is answerable by the
  owner; it never creates an approver-inbox entry, a distinct-human requirement, or
  a self-approval check.
- **R-2 — The kernel's first external-execution handler.** A new branch catches
  `RequireExternalExecutionEvent{reply_id, tool_calls}`, projects the question to the
  wire, registers the park, and ends the stream **without** `message_end` (as a
  confirmation park does) — beside the untouched `RequireUserConfirmEvent` branch.
  The answer builds `execution_results` (prose `output` + `AskUserMetadata{answers}`)
  and injects `ExternalExecutionResultEvent` to re-drive the **same** assistant turn
  in-process; no agentscope event object is serialized to the wire.
- **R-3 — A v2 SSE frame pair (v13 → v14).** Two additive, platform-owned frames in
  `agent-stream-event.schema.json`: `clarification_request` (`clarification_id` + a
  `questions` array of `{question, header, context?, multi_select, options:[{label,
  description}]}`) and `clarification_result` (`clarification_id`, the `answers`, and
  a closed `status` of `answered` / `expired` / `interrupted`).
  `additionalProperties: false` holds, no existing frame changes, and older clients
  ignore an unknown `type`. They are **not** a reuse of `authorization_required` (a
  non-resuming signal); a clarification is a park-resume and needs its own resuming
  pair.
- **R-4 — Park-kind-aware 409 guard + answer endpoint.** A new chat turn while any
  park is pending returns **409** naming the parked kind; the SPEC-022 `has_pending`
  badge covers both kinds (one slot — a confirmation *or* a clarification, never
  both, structurally). `POST /api/v2/sessions/{id}/clarification/answer` (+ the
  gateway `POST /api/v1/sessions/{id}/clarification/answer` proxy) resumes the parked
  clarification; a stale/duplicate answer is race-resilient (the SPEC-031
  `already_resolved` posture) and a TTL-expired clarification closes via the same
  `UserInterruptEvent` path.
- **R-5 — Opt-in, flag-gated wiring.** `AGENT_ASKUSER_ENABLED` (default **off**)
  admits `AskUser` to the toolkit only when set, and registers as the `askuser` entry
  in the SPEC-072 `runtime:flags` inventory. With the flag off the deployed chat path
  emits a byte-identical stream and parks nothing new; the kernel's
  external-execution branch is inert until an `AskUser` call actually parks a reply.
- **R-6 — The v1 `AskUser` surface (full shape minus `preview`).** 1–4 questions ×
  2–4 options, `multi_select`, a ≤12-char `header`, optional `context`, and the
  auto-“Other” free-text answer round-trip through `clarification_result`. The
  single-select-only `preview` field is a named fast-follow, deferred.
- **R-7 — A portal clarification card, owner-answerable in-line.** The chat view
  renders a parked clarification as a card (`ClarificationCardView`) the owner answers
  in-line and submits to the resume endpoint, then renders the resumed same-turn
  stream; the answered card re-renders from `clarification_result` or the durable
  record on re-login. No approver-inbox surface is added.
- **R-8 — Audit rides the existing turn events; the enum stays closed.** No new
  `event_type`; the parking/resuming turn is bracketed by `chat_started` /
  `chat_completed`. The audit-contract drift guard now pins the enum **unchanged at
  23** on both the model and the schema, and the agent-platform contract-boundary
  suite asserts no clarification-specific event type was minted.

## Changed

- **New knob (`agent-platform`).** `AGENT_ASKUSER_ENABLED` (default `false`) —
  documented in the
  [configuration reference](../../guides/configuration-reference.md) (Feature
  Activation Matrix, the `runtime:flags` inventory, and the agent-service env table).
- **Contract bump.** `agent-stream-event.schema.json` **v13 → v14** (additive: two
  frames). `audit-event.schema.json` and `execution-request.schema.json` are
  **unchanged**.
- **Gated live-cluster read-only check (`platform-ops`, `agent-platform`).**
  `e2e/clarification-livecheck.sh` (`--local` mocked / `--live` gated) parks a
  clarification → the owner answers → same-turn resume, asserting **no** mutation,
  **no** dispatch, and **no auto-approval** (zero `execution_requested` /
  `execution_completed` / `confirmation_decided` across the session family) and a
  durable `park_kind=clarification` / `status=answered` card with zero
  `pending_calls`; wired into `make clarification-livecheck` + `make e2e`, with the
  mocked-I/O leg collected by `make test`.
- **Living docs.** The
  [Approval and HITL Governance guide](../../guides/approval-and-hitl.md) gains an
  “Agent-Initiated Clarification” section, the
  [portal user guide](../../guides/portal-user-guide.md) an “Answering an Agent's
  Question” section, the configuration reference documents the flag, and the
  [delivery-roadmap](../delivery-roadmap.md) Exploration Backlog row records the
  adoption. The [specs index](../../specs/README.md) row moves to `delivered` and
  [CHANGELOG.md](../../../CHANGELOG.md) gains the 0.62.0 entry.

## Verification

- Full agent-platform suite green (incl. the clarification park / resume / expire
  legs, the projection, the contract-parity + contract-adapter v14 pins, the
  flag-gating byte-identical proofs, and the mocked live-check); platform-gateway
  green (the answer proxy + route inventory + `ClarificationAnswerAuditTests`);
  audit-service contract suite green (the enum-closed-at-23 drift guard);
  operator-portal Vitest green (`ClarificationCardView` + the stream/transcript
  adapter).
- Root `make verify` green across all legs — every product suite, all seven overlays,
  docs-check (0 unresolved env vars), policy + policy-scenarios (163 api / 42 tools),
  version lockstep at **0.62.0**, secret vocabulary, the delegated
  custody/runtime/multiproc/edge proofs over real docker + TLS, and the long-running
  SPEC-063 `execution-failure-test` campaign run to completion: **795 passed, 2
  deselected, exit 0** in 0:34:41.
- SPEC-018 four-point gate re-affirmed at a posture strictly *less* than the
  confirmation path: (1) deny-by-default + audit held (`AskUser` executes nothing;
  the enum stays closed); (2) identity on the one gateway-forwarded delegated token
  (no new principal / claim / identity edge); (3) read-only posture preserved (a
  clarification carries `questions`/`options`, never a mutating
  `pending_call`/`risk_level`); (4) no agentscope types on the wire (the v14 frames
  are platform-owned projections and the resume event is injected in-process).

## Posture

Read-only and opt-in. A clarification mutates nothing, carries no authority, and
cannot widen the read-only posture or the ADR-0017 ceiling; it never stages,
approves, or dispatches an action. The deployed unscoped single-agent chat path is
**byte-identical** to v0.61.1 when the flag is off (the default), no existing wire
frame changed, no new principal / claim / credential / identity edge is minted, and
the audit `event_type` enum stays closed at 23. The single-select-only `preview`
field, cross-surface / owner-side answer sync (SPEC-032-style), and governance
attribution (`clarification_asked` / `clarification_answered`) remain **separate,
future** work. Commit/tag/push and deployment remain separate gates.
