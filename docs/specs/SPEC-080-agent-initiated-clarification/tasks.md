# SPEC-080 Tasks: Agent-Initiated Clarification (a read-only `AskUser` park/resume beside the HITL confirmation path)

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

> **Binding as of approval 2026-11-25.** Derived from [plan.md](plan.md); all seven Open Questions were
> ratified exactly as recommended. Approval authorizes implementation to **begin** — **not** to merge,
> commit/push, deploy, or version-bump (each a separate gate). Target version **v0.62.0**, bumped only
> at the release gate.

## R-3: v2 SSE frame pair, v13 → v14 (contract first)

- [ ] Add `clarification_request` + `clarification_result` to the `type` enum + field schemas; bump the
  title v13 → v14; `additionalProperties: false` holds; no existing frame changes
  (`shared/shared-contracts/schemas/agent-stream-event.schema.json`)
- [ ] Mirror both frames in the agent-platform pydantic models with a closed `Literal` enum
  (`products/agent-platform/src/agent_service/schemas/v2.py`)
- [ ] Mirror the gateway passthrough model
  (`products/platform-gateway/src/platform_gateway/services/gateway_service.py`)
- [ ] Contract-parity test binds the gateway model to the v14 schema (the packaged contract-parity suite)

## R-1: A clarification park kind on the shared substrate

- [ ] Add `park_kind` to `PendingConfirmation` + a `park_kind` param to `register(...)`; the
  one-per-session slot holds either kind (`products/agent-platform/src/agent_service/services/hitl_confirmations.py`)
- [ ] Carry the projected questions + `clarification_id` on a parked clarification (same file)
- [ ] Extend the SPEC-031 durable record store with the `park_kind` discriminator + an additive migration
  (`products/agent-platform/src/agent_service/services/confirmation_records.py`; migration under `shared/shared-contracts/`)
- [ ] Unit: `park_kind` slot + mutual exclusion; the durable record survives a simulated re-login
  (`products/agent-platform/tests/`)

## R-2: The kernel's first external-execution handler

- [ ] Add the `RequireExternalExecutionEvent` branch beside `kernel_confirmations.py:116-119` — detect the
  parked `AskUser`, project → `clarification_request`, register the park, end the stream without
  `message_end` (`products/agent-platform/src/agent_service/services/kernel_confirmations.py`)
- [ ] Add `resume_clarification(...)` as a sibling to `resume_confirmation(...)` (`:427`) — build
  `execution_results` (prose `output` + `AskUserMetadata`), inject `ExternalExecutionResultEvent`,
  re-drive the same turn (same file)
- [ ] Reuse `expire_confirmation` → `UserInterruptEvent` for TTL expiry + operator cancel of a parked clarification
- [ ] Unit: park → project → register → resume-by-injection; expire/cancel; the confirmation branch stays
  byte-identical (`products/agent-platform/tests/`)

## R-4: Park-kind-aware 409 guard + answer endpoint

- [ ] `_reject_if_parked` names the parked kind in the 409
  (`products/agent-platform/src/agent_service/api/v2/routes.py:229`)
- [ ] Add `POST /api/v2/sessions/{id}/clarification/answer` → `resume_clarification`, race-resilient
  (`already_resolved`) (`products/agent-platform/src/agent_service/api/v2/routes.py`)
- [ ] Gateway proxy route (`products/platform-gateway/src/platform_gateway/`)
- [ ] Unit: 409 for both kinds; the answer validates against the parked questions; a duplicate/stale
  answer → `already_resolved` (`products/agent-platform/tests/`)

## R-5: Opt-in, flag-gated wiring

- [ ] Add `AGENT_ASKUSER_ENABLED` (default **off**) to runtime settings
  (`products/agent-platform/src/agent_service/` config/settings)
- [ ] Admit `AskUser` to the toolkit only when the flag is on
  (`products/agent-platform/src/agent_service/services/kernel_toolkits.py`)
- [ ] Register the flag in the SPEC-072 `runtime:flags` inventory; the dev overlay opts in
  (`shared/platform-ops/gitops/dev-k8s/`)
- [ ] Unit: flag off ⇒ the unscoped chat path is byte-identical (no new frame/park/event)
  (`products/agent-platform/tests/`)

## R-6: The v1 `AskUser` feature surface (full shape minus `preview`)

- [ ] Project the full `AskUserParams` (`questions[1-4]`, `header ≤12`, `context?`, `multi_select`,
  `options[2-4]`) minus `preview` (`products/agent-platform/src/agent_service/services/kernel_confirmations.py`)
- [ ] Round-trip `AskUserMetadata{answers}` with `multi_select` + the auto-"Other" free text
- [ ] Unit: the projection + validation mirror the agentscope constraints; no `preview` field exists in v14

## R-7: A portal clarification card, owner-answerable in-line

- [ ] Render the owner-answerable clarification card (questions, options, `multi_select`, "Other")
  (`products/operator-portal/web-ui/app/src/chat/ClarificationCard.tsx`, a sibling to `ConfirmationCard.tsx`)
- [ ] Handle `clarification_request` / `clarification_result` in the SSE adapter
  (`products/operator-portal/web-ui/app/src/stream/useChatStream.ts`)
- [ ] Submit the answer to the R-4 endpoint; render the resumed same-turn stream
  (`products/operator-portal/web-ui/app/src/chat/ChatView.tsx`)
- [ ] Re-render the answered card from the durable record on re-login
- [ ] Portal Vitest tests for the card + adapter (`products/operator-portal/web-ui/app/src/chat/__tests__/`)

## R-8: Audit rides the turn events; the enum stays closed

- [ ] Assert no new `event_type`; the parking/resuming turn is bracketed by `chat_started` /
  `chat_completed` (`products/agent-platform/tests/`)
- [ ] The audit-contract drift guard passes with the enum unchanged at 23 values
  (`shared/shared-contracts/`)

## Evidence — four-point gate + gated live-check

- [ ] A gated billable live-check mirroring the confirmation live-check: park a clarification → the owner
  answers → same-turn resume; assert **no** mutation, **no** dispatch, **no** auto-approval
  (`shared/platform-ops/e2e/`)
- [ ] Map the four-point gate per point (deny-by-default + audit; delegated-token identity; read-only
  posture; no agentscope types on the wire) in this file's evidence at delivery

## Delivery Gate

- [ ] all acceptance criteria in `spec.md` verified (each `R-x` maps to ≥1 asserting test — ADR-0008)
- [ ] living state docs updated (see spec `Impact`: the guide layer, the roadmap Exploration Backlog row,
  a dated release note)
- [ ] `CHANGELOG.md` entry added referencing SPEC-080
- [ ] spec index in `docs/specs/README.md` flipped to `delivered`
- [ ] spec status set to `delivered`; target version **v0.62.0** bumped at the separate release gate
- [ ] root `make verify` green (incl. the 795-case SPEC-063 execution-failure campaign)
- [ ] commit/push, deployment, and the version bump remain separate gates (not authorized by approval)
