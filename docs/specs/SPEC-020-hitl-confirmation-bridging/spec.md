# SPEC-020: HITL Confirmation Bridging — Kernel ASK to Portal Approve/Deny

## Status

- status: `delivered`
- owner: chi
- created: 2026-08-21
- release slice: R4 approval-gated bounded actions — first slice (0.6.0 train)
- related ADRs: ADR-0006 (contract purpose-invariant enforcement — the v2 contract deliberately grows interaction semantics); builds on SPEC-018 Future Scope, SPEC-017 durability, SPEC-013 audit contract, SPEC-019 portal surfaces; promoted from the Exploration Backlog per spike memo `docs/workspace/hitl-bridging-spike.md` (2026-08-21)

## Summary

Map the kernel's `ASK` permission parking onto two new v2 SSE confirmation frames and give the operator portal approve/deny with session suspend/resume through a new confirm endpoint, with confirmer identity delegation and durable audit of decisions. This is the read-to-write bridge that SPEC-018 declares MUST precede any write/mutating tool.

## Motivation

- Non-allow-listed tools park silently today: `GatewayPermissionMiddleware` keeps the ASK default, the kernel emits `RequireUserConfirmEvent`, the stream normalizes it as a generic event and ends, and the tool never runs — with nothing shown to the operator (verified SPEC-018 headless posture). Any gateway tool outside `AGENT_GATEWAY_TOOL_AUTO_ALLOW` is already unreachable this way, and every future mutating tool will be.
- The spike memo (`docs/workspace/hitl-bridging-spike.md`) verified against locked agentscope 2.0.6 that suspend/resume is first-class kernel machinery (`RequireUserConfirmEvent`, `UserConfirmResultEvent`, `UserInterruptEvent`, parked `ToolCallState.ASKING`); the platform only ever feeds `Msg` into `reply_stream` today. Nothing kernel-side needs to be invented.
- Sequencing is mandated, not chosen: SPEC-018 Future Scope requires this bridge before any write/mutating tool ships, and the Exploration Backlog promotion rule (spike memo first, then SPEC number) is satisfied.
- SPEC-019 prepared the surface: the sectioned sidebar and stream-rendering conventions are where the confirmation card and its audit/matrix consistency land.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable acceptance criteria.

### R-1: Contract growth — confirmation frames and confirm-request schema

`agent-stream-event.schema.json` bumps v3 → v4 adding two confirmation frame types, and a new shared contract schema binds the confirm endpoint's request body.

Acceptance criteria:

- `agent-stream-event.schema.json` adds `confirmation_request` and `confirmation_result` to the `type` enum, keeping `additionalProperties: false` discipline. All existing frame types and fields remain byte-stable; `tool_call`/`tool_result` evidence frames are unchanged.
- A `confirmation_request` frame carries `confirm_id`, the pending tool calls as `call_id`/`tool_name`/`parameters` (reusing the existing field names), and the kernel permission message in `message`.
- A `confirmation_result` frame carries `confirm_id` and `status` ∈ {`approved`, `denied`, `expired`, `interrupted`}.
- A new `shared/shared-contracts/schemas/chat-confirm.schema.json` binds the confirm request body: `session_id`, `confirm_id`, and `decision` ∈ {`approve`, `deny`}; nothing else.
- agent-platform contract tests validate the stream frames and confirm request model against the schemas, covering frame validity for both new types and rejection of unknown fields.

### R-2: Agent-platform runtime bridging — park, registry, resume

The streamed chat path translates kernel parking into a `confirmation_request` frame and resumes parked replies through a new confirm endpoint.

Acceptance criteria:

- When `agent.reply_stream` yields `RequireUserConfirmEvent` during a streamed turn, the runtime emits one `confirmation_request` frame, registers the pending confirmation in an in-memory per-session registry keyed by `confirm_id` (holding `reply_id` and the parked `tool_calls`), and ends the stream without a `message_end` frame.
- `POST /api/v2/chat/confirm` accepts the R-1 body and resumes the parked reply by feeding `UserConfirmResultEvent` into `agent.reply_stream`: approval confirms every parked tool call all-or-nothing (v1 decision), denial feeds `confirmed=False` so the agent reasons about the refusal and the turn continues to a normal `message_end`.
- The resumed stream follows the same v2 frame contract and begins with the matching `confirmation_result` frame; the delegated token set for the resumed turn is the confirmer's bearer token, so the tool-gateway sees the approving identity on any resulting invocation.
- Pending confirmations expire after `AGENT_HITL_CONFIRM_TIMEOUT` seconds (default 600); a confirm attempt after expiry returns 410 and closes the parked calls via `UserInterruptEvent`. Setting the timeout to 0 disables bridging and restores today's silent-park posture.
- A confirm request is rejected with 403 unless the requesting user owns the session; unknown or already-resolved `confirm_id` returns 404.
- A session with a pending confirmation rejects new chat turns with 409 until the confirmation is resolved (approved, denied, or expired).
- The pending registry does not survive process restart: after an agent rebuild, previously parked confirmations are treated as expired — a parked tool call never auto-runs and never silently disappears without the expiry path being reachable.
- The blocking `POST /chat` path keeps today's headless posture unchanged (no confirmation flow).

### R-3: Platform-gateway confirm proxy, `chat:confirm` action, and audit

platform-gateway proxies the confirm endpoint under a new deny-by-default policy action and records decisions in the durable audit trail.

Acceptance criteria:

- `POST /api/v1/chat/confirm` resolves request identity, enforces the new `chat:confirm` action through `enforce_policy`, obtains a delegated token from the confirmer's credentials (delegation-client pattern), and proxies to agent-platform `POST /api/v2/chat/confirm`; the resumed SSE stream is passed through. Upstream outages map to 502; upstream 4xx (403/404/409/410) passes through.
- `policy-default.yaml` gains a `chat:confirm` rule granting the action to `platform-admin`, `approver`, `operator`, and `developer`; `read-only-observer` is denied by default, per the bundle's own convention ("when chat gains a mutating capability, that capability gets its own action name and observer is denied it").
- `audit-event.schema.json` gains one new `event_type`, `confirmation_decided`, with payload carrying `session_id`, `confirm_id`, tool names, and the decision. platform-gateway emits it on approve and deny (emitter-side, post-identity-resolution, like `chat_completed`). Request and expiry states are recorded in agent-platform structured logs, not the durable trail.
- The confirm route follows the existing chat route conventions for request-id correlation, structured logging, and identity handling.

### R-4: Portal confirmation card

The operator portal chat view renders parked confirmations as an inline approval card and resumes the stream from the confirm response.

Acceptance criteria:

- On `confirmation_request`, the chat view renders a card in the message stream showing the pending tool name(s), parameters, and the permission message, with Approve and Deny buttons. Buttons are hidden for signed-in identities holding only roles without `chat:confirm` (client-side convenience; the server re-enforces).
- Approve/Deny posts to the gateway confirm endpoint and renders the returned SSE continuation into the same message stream; the card locks into its decided state. A 410 response renders the card as expired; 409 on a concurrent turn renders as the standard chat error state.
- A stream ending after `confirmation_request` (no `message_end`) does not render the "No response received" fallback.
- `styles.css`/`app.js` cache-busting query strings are bumped.

### R-5: Policy, documentation, and verification sync

The new action, setting, and audit event are synchronized through the platform's policy/docs discipline and verified end-to-end.

Acceptance criteria:

- `make sync-policy` refreshes the packaged policy copies and the dev-k8s ConfigMap; `make validate-policy` passes with the new rule.
- `docs/agentic-aiops-platform/authorization-matrix.md` documents `chat:confirm` and its role grants, noting the observer exclusion.
- `docs/guides/configuration-reference.md` documents `AGENT_HITL_CONFIRM_TIMEOUT` (including the 0 = disabled semantics).
- `make verify` is green: all product suites (including new agent-platform bridging tests and platform-gateway proxy/audit tests), all overlays render, policy and version gates pass.

## Non-Goals

- Any write/mutating gateway tool — this spec is the bridge only; the first bounded actions land in subsequent R4 slices that depend on it.
- The platform approval workflow: policy-center `require_approval` routing, the approval queue, and execution-runtime belong to later R4 slices. Kernel `ASK` confirmation and policy-level approval are different layers (see spike memo §3.4); this spec must not grow the approval queue.
- ASK → DENY tightening — stays the declared follow-up to this spec (SPEC-018 Future Scope).
- Confirmation flow on the blocking chat path or incident-service triage — both keep the headless posture.
- Durable parked state across restarts — the registry is in-memory by decision; restart means expiry.
- Any agentscope.app runtime dependency — its HITL projectors remain reference-only per SPEC-018 R-7.

## Impact

- products touched: `products/agent-platform` (runtime kernel, v2 routes, schemas, settings, middleware, tests), `products/platform-gateway` (confirm route, gateway service, audit emitter, tests), `products/operator-portal/web-ui` (index.html/app.js/styles.css)
- contracts touched: `shared/shared-contracts/schemas/agent-stream-event.schema.json` (v3 → v4), `shared/shared-contracts/schemas/audit-event.schema.json` (new enum value), new `shared/shared-contracts/schemas/chat-confirm.schema.json`, `shared/shared-contracts/policies/policy-default.yaml` (new rule)
- identity / policy / audit / execution safety impact: one new deny-by-default action (`chat:confirm`, observer excluded); confirmer identity rides the delegated token into any resulting tool invocation; one new durable audit event type; no new execution surface — tool execution remains exclusive to the tool-gateway
- living state docs to update on delivery: `CHANGELOG.md`, `docs/specs/README.md` index, `docs/agentic-aiops-platform/authorization-matrix.md`, `docs/guides/configuration-reference.md`, `products/agent-platform/README.md`, `products/platform-gateway/README.md`, `products/operator-portal/README.md`, delivery-roadmap Exploration Backlog row

## Open Questions

- none (decisions captured in draft discussion 2026-08-21, carrying the spike memo §4 resolutions: parked state is in-memory with expiry-on-restart as the fail-safe; multi-call confirmations are all-or-nothing in v1; denial feeds the refusal back to the agent rather than ending the turn; parked sessions reject concurrent turns with 409; the durable trail records decisions only — request/expiry live in structured logs; `chat:confirm` granted to all chat roles except read-only-observer)

## Changelog

- 2026-08-21: created as `draft`; promoted from the Exploration Backlog after the spike memo landed (`docs/workspace/hitl-bridging-spike.md`)
- 2026-08-21: approved by owner; `plan.md` written, implementation starting
- 2026-08-21: delivered. Recorded deviations: (1) R-2's "403 unless owner" is implemented as the house anti-enumeration convention — foreign or unknown sessions answer 404, with `ConfirmationOwnerMismatch` as a defensive mid-stream error frame; (2) R-3's `confirmation_decided` emission is tee'd off the kernel-applied `confirmation_result` frame during SSE passthrough (rather than a route-level emit), so only decisions the kernel actually applied reach the durable trail and the `confirmation_result` frame echoes `pending_calls` for the tool names.
- 2026-08-21: post-delivery review hardening: the confirm route now claims the registry entry before headers go out (duplicate confirms fail closed with 404 instead of double-resuming the parked batch), and TTL expiry is never silently evicted — an expired park is closed via `UserInterruptEvent` on the confirm attempt or the next chat turn. All acceptance criteria verified; `make verify` green.
- 2026-08-21: live-check hardening: a live run showed that non-allow-listed read-only tools never parked — agentscope's `PermissionEngine` read-only fast path auto-allows read-only invocations in every mode, silently bypassing the platform allow-list the spec's premise relied on. `GatewayPermissionMiddleware` now answers every non-allow-listed tool with an explicit ASK instead of delegating to the engine, making the allow-list the only auto-approval surface and restoring the bridging trigger for all ASK-gated batches.
- 2026-08-21: live-check fix (approve loop): once the explicit ASK fired, approving re-parked the reply forever — agentscope re-traverses the permission middleware chain for confirmed calls (state ALLOWED) and expects the built-in resolution to short-circuit them, but the explicit-ASK path re-asked and re-parked on every resume. The middleware now delegates ALLOWED-state calls to the built-in resolution so an approved batch executes on resume.
- 2026-08-21: live-check hardening (portal + evidence transparency): the confirmation card's status line now always reaches its final state once a decision is applied (previously it stayed on "Approving…" while only the badge updated); stream schema bumps v4 → v5 adding an optional `data` field on `tool_result` frames — the full tool payload within `AGENT_TOOL_DATA_MAX_CHARS` — rendered by the portal as a "Show full output" expander so operators see the complete tool result even when the reply summarizes it.
