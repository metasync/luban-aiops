# SPEC-020 Plan: HITL Confirmation Bridging — Kernel ASK to Portal Approve/Deny

## Approach

Three products change, each on its existing surface: agent-platform owns the park/registry/resume mechanics inside the runtime kernel and v2 routes (no agentscope types leak across the HTTP boundary); platform-gateway gains one proxied route following the exact chat-route conventions (identity → `enforce_policy` → delegation → proxy → log/audit); the portal gains one inline card in the chat stream. Shared contracts grow additively only. The bridging is keyed entirely off kernel events already emitted by agentscope 2.0.6 — the platform translates, registers, and resumes; it never re-implements permission logic.

## Design Per Requirement

### R-1: Contract growth — confirmation frames and confirm-request schema

- `shared/shared-contracts/schemas/agent-stream-event.schema.json` (title/description bump v3 → v4):
  - `type` enum gains `confirmation_request`, `confirmation_result`.
  - New `confirm_id` (string) field — present on both confirmation frame types.
  - New `pending_calls` field (array of `{call_id, tool_name, parameters}`, `additionalProperties: false` items) — present on `confirmation_request`; carries the parked tool calls as a batch. Singular `tool_name`/`call_id`/`parameters` stay tool-frame-only.
  - Existing `status` enum extends to `["success", "error", "denied", "approved", "expired", "interrupted"]`; description updated to cover `tool_result` and `confirmation_result` frames. `message` carries the kernel permission message on `confirmation_request`.
- New `shared/shared-contracts/schemas/chat-confirm.schema.json`: `{session_id, confirm_id, decision}` with `decision` ∈ {`approve`, `deny`}, `additionalProperties: false`, `$id` per existing convention.
- `agent_service/schemas/v2.py`: `AgentStreamEvent` gains `confirm_id: str | None` and `pending_calls: list | None`; new `AgentChatConfirmRequest` model mirrors the confirm schema. Contract pairs registered in the existing contract-test registry.
- Rejected alternative: a separate confirmation-event schema. The stream contract is the single SSE vocabulary the portal parses; a second schema would fork `streamEventType` handling for no benefit (ADR-0006 permits deliberate growth of this one contract).

### R-2: Agent-platform runtime bridging — park, registry, resume

- New `agent_service/services/hitl_confirmations.py`:
  - `PendingConfirmation` dataclass: `confirm_id`, `session_id`, `user_id`, `reply_id`, `tool_calls` (kernel blocks, held opaquely), `created_at`, `resolved` flag.
  - `ConfirmationRegistry`: per-process in-memory map `session_id → PendingConfirmation` (at most one pending per session). Methods: `register`, `get`, `resolve`, `is_parked(session_id)`, `evict_expired(timeout)`. No persistence — restart empties it (the R-2 fail-safe decision).
  - Module-level singleton `CONFIRMATION_REGISTRY` injected through `runtime_dependencies` for testability.
- `runtime_kernel.stream_events`: after the existing event normalization, detect `RequireUserConfirmEvent` (via `normalize_event` type `require_user_confirm`): when `settings.hitl_confirm_timeout > 0`, build the `confirmation_request` frame dict (`type`, `confirm_id` = UUID4, `pending_calls` from the event's `tool_calls`, `message` from the kernel decision message), register it, yield the frame, and end the stream (no `message_end`). When disabled (timeout 0), fall through to today's behavior.
- New kernel method `resume_confirmation(session_id, confirm_id, decision, user_name, bearer_token) -> AsyncIterator[dict]`:
  - lookups: unknown/resolved `confirm_id` → 404; owner mismatch → 403; expired → emit `confirmation_result(expired)`, feed `UserInterruptEvent` into `reply_stream` and drain internally, then 410 at the route.
  - approval builds `UserConfirmResultEvent` with `ConfirmResult(confirmed=True, tool_call=tc)` for every parked call (all-or-nothing v1); denial builds the same with `confirmed=False`.
  - sets `DELEGATED_TOKEN` to the confirmer's bearer token and `TOOL_EVIDENCE_SINK` to a fresh queue, yields `confirmation_result(approved|denied)` first, then streams the resumed `reply_stream` through the same normalization/evidence path; registry entry resolved in `finally`; `_snapshot_state` after completion as today.
- `api/v2/routes.py`:
  - `POST /chat/confirm` → resolve `X-User-ID`, `get_session` (ownership), registry checks, `StreamingResponse` over `resume_confirmation`. Error mapping to HTTPException 403/404/409/410.
  - `chat_stream` and blocking `chat` gain a pre-turn guard: `CONFIRMATION_REGISTRY.is_parked(session_id)` → 409 (streamed route raises before opening the response).
  - `_STREAM_EVENT_TYPES` gains the two new types; `_normalize_stream_event` passes `confirm_id`/`pending_calls` through.
- `runtime_settings.py`: `hitl_confirm_timeout: int` from `AGENT_HITL_CONFIRM_TIMEOUT` (default 600, 0 disables) — per-service `AGENT_*` env vocabulary.

### R-3: Platform-gateway confirm proxy, `chat:confirm` action, and audit

- `api/routes/chat.py`: `POST /api/v1/chat/confirm` — identical structure to `chat_stream_route`: resolve identity, `enforce_policy(settings, identity, "chat:confirm", request_id)`, `obtain_delegated_token`, `log_event`, `emit_audit_event(build_audit_event("confirmation_decided", ..., payload={session_id, confirm_id, decision}))`, then pass through the upstream SSE.
- `services/gateway_service.py` + `agent_client`: `chat_confirm(...)` streaming POST to `{agent_platform_url}/api/v2/chat/confirm` with the same header conventions (`X-User-ID`, `x-request-id`, delegated bearer); 502 on transport error, 4xx passthrough.
- `services/policy_engine.py`: `ACTION_CHAT_CONFIRM = "chat:confirm"` added to `PROTECTED_ACTIONS`.
- `audit-event.schema.json` enum gains `confirmation_decided`; payload description extended (session_id, confirm_id, decision). Request/expiry states deliberately stay in agent-platform structured logs.

### R-4: Portal confirmation card

- `app.js` chat stream loop: `confirmation_request` → `renderConfirmationCard(payload)` appended to the message stream (tool names, parameters as a muted `<pre>`, permission message, Approve/Deny buttons); sets a `confirmationPending` flag so stream-end without `message_end` skips the "No response received" fallback. `confirmation_result` → locks the matching card into its status badge.
- Approve/Deny handler: `fetch POST /api/v1/chat/confirm` with the auth session's access token, then reads the response body through the same SSE parser, appending the continuation into the current message. 410 → card renders expired; 409/other → standard chat error line.
- Buttons hidden when the resolved identity's roles lack any of the `chat:confirm`-granted roles (client-side convenience only; mirrors SPEC-019 gating posture).
- `styles.css`: `.confirm-card` styling reusing design tokens and `status-badge` conventions; cache-busting query strings bumped in `index.html`.

### R-5: Policy, documentation, and verification sync

- `policy-default.yaml`: new `allow-chat-confirm` rule (priority 100) granting `chat:confirm` to `platform-admin`, `approver`, `operator`, `developer`; header comment noting observer exclusion per the bundle's own convention. `make sync-policy` refreshes packaged copies + dev-k8s ConfigMap.
- Docs: `authorization-matrix.md` (`chat:confirm` row + observer exclusion), `configuration-reference.md` (`AGENT_HITL_CONFIRM_TIMEOUT` incl. 0 = disabled), product READMEs (agent-platform, platform-gateway, operator-portal).
- dev-k8s: no new env required (default 600 applies); overlay ConfigMap changes ride `make sync-policy` only.

## Sequencing And Dependencies

1. Contracts: stream schema v4, chat-confirm schema, audit enum, policy rule — depends on nothing; unblocks all test binding.
2. Agent-platform: registry + kernel bridge + settings + routes — depends on stage 1.
3. Agent-platform tests (registry unit, kernel bridge with fake kernel events, route 403/404/409/410 paths, contract binding) — depends on stage 2.
4. Platform-gateway: route + client + action + audit emission + tests (fake-httpx pattern from incidents/tools proxy suites) — depends on stages 1–2.
5. Portal: card rendering + confirm handler + styles — depends on stage 4.
6. Policy sync, docs, delivery gate (`make verify`) — depends on all.

## Test Strategy

- Unit (agent-platform): registry register/resolve/expiry/single-pending semantics; `stream_events` emits `confirmation_request` and parks on a fake `RequireUserConfirmEvent`; `resume_confirmation` approve/deny/expired paths with a fake agent whose `reply_stream` accepts `UserConfirmResultEvent`/`UserInterruptEvent`; parked-session 409 guard on both chat routes; disabled mode (timeout 0) keeps legacy behavior.
- Contract: `AgentStreamEvent` frames for both new types validate against schema v4; unknown-field rejection; `AgentChatConfirmRequest` validates against `chat-confirm.schema.json`; gateway audit model validates the new enum value.
- Unit (platform-gateway): confirm route — identity resolution, policy deny 403 for observer, delegated token forwarded, SSE passthrough, 502 on transport error, 4xx passthrough, `confirmation_decided` emission payload.
- Integration / overlay validation: `kustomize build` all overlays (policy ConfigMap carries the new rule after sync), `make validate-policy`, `make validate-version`, full `make verify`.
- Live validation path (optional, post-merge): register a deliberately non-allow-listed read-only gateway tool, ask a question that invokes it, approve in the portal, confirm the evidence frames and audit trail show the full chain.

## Rollout And Migration

- Backward compatible: frames are additive; old portal builds simply ignore unknown frame types (degraded but safe — parked stream ends, no false output). Portal and backends ship in the same release train, so the window is a single deploy.
- Enablement: default-on with 600s TTL; no dev-k8s env change needed.
- Rollback: set `AGENT_HITL_CONFIRM_TIMEOUT=0` on agent-platform to restore today's silent-park posture without code rollback; the new policy action is inert when no confirm traffic flows.

## Decisions

- Single pending confirmation per session (registry keyed by session_id) — matches the kernel's one-parked-reply-per-session model and makes the 409 guard trivial.
- Expiry is enforced lazily at confirm time plus `evict_expired` on new registrations — no background timers in the runtime.
- The confirm response is itself the resumed SSE stream (not a 200 JSON + separate stream endpoint) — one round trip, and the portal reuses its existing SSE parser untouched.
- `confirmation_request` ends the stream without `message_end` rather than with a synthetic one — `message_end` semantics stay "turn completed", which audit and UI completion detection rely on.
- All-or-nothing multi-call confirmation in v1; the frame carries the full `pending_calls` batch so a future per-call UI is a portal-only change.
