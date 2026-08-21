# SPEC-020 Tasks: HITL Confirmation Bridging — Kernel ASK to Portal Approve/Deny

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Contract growth — confirmation frames and confirm-request schema

- [x] Bump `agent-stream-event.schema.json` v3 → v4: `confirmation_request`/`confirmation_result` types, `confirm_id`, `pending_calls`, extended `status` enum (`shared/shared-contracts/schemas/`)
- [x] Add `chat-confirm.schema.json` (`session_id`, `confirm_id`, `decision`) (`shared/shared-contracts/schemas/`)
- [x] Extend `AgentStreamEvent` (`confirm_id`, `pending_calls`) and add `AgentChatConfirmRequest` (`products/agent-platform/src/agent_service/schemas/v2.py`)
- [x] Extend gateway audit model to accept `confirmation_decided`; update `audit-event.schema.json` enum + payload description (`products/platform-gateway/src/platform_gateway/schemas/`, `shared/shared-contracts/schemas/`)
- [x] Contract tests: new frame types validate, unknown-field rejection, confirm-request binding (`products/agent-platform/tests/`)

## R-2: Agent-platform runtime bridging — park, registry, resume

- [x] New `services/hitl_confirmations.py`: `PendingConfirmation`, `ConfirmationRegistry` (register/get/resolve/is_parked/evict_expired), singleton via runtime dependencies (`products/agent-platform/src/agent_service/services/`)
- [x] `runtime_settings.py`: `hitl_confirm_timeout` from `AGENT_HITL_CONFIRM_TIMEOUT` (default 600, 0 disables) (`products/agent-platform/src/agent_service/runtime_settings.py`)
- [x] `runtime_kernel.stream_events`: translate `RequireUserConfirmEvent` → `confirmation_request` frame + registry entry, end stream without `message_end`; disabled-mode fallthrough (`products/agent-platform/src/agent_service/runtime_kernel.py`)
- [x] `runtime_kernel.resume_confirmation`: lookup/owner/expiry checks, `UserConfirmResultEvent`/`UserInterruptEvent` resume, `confirmation_result` first frame, confirmer token into `DELEGATED_TOKEN`, evidence sink, snapshot after completion (`products/agent-platform/src/agent_service/runtime_kernel.py`)
- [x] `POST /api/v2/chat/confirm` route with 403/404/409/410 mapping; parked-session 409 guard on `chat` and `chat/stream`; `_STREAM_EVENT_TYPES` + normalizer passthrough (`products/agent-platform/src/agent_service/api/v2/routes.py`)
- [x] Tests: registry semantics; park/resume/deny/expire with fake kernel events; route error paths; disabled mode parity (`products/agent-platform/tests/`)

## R-3: Platform-gateway confirm proxy, `chat:confirm` action, and audit

- [x] `ACTION_CHAT_CONFIRM` in `PROTECTED_ACTIONS` (`products/platform-gateway/src/platform_gateway/services/policy_engine.py`)
- [x] `chat_confirm` streaming client: POST upstream with `X-User-ID`/`x-request-id`/delegated bearer; 502 transport, 4xx passthrough (`products/platform-gateway/src/platform_gateway/services/`)
- [x] `POST /api/v1/chat/confirm` route: identity → `enforce_policy` → delegation → proxy → `log_event` → `confirmation_decided` audit emission (`products/platform-gateway/src/platform_gateway/api/routes/chat.py`)
- [x] Tests: policy deny (observer 403), token forwarding, SSE passthrough, 502/4xx mapping, audit payload (`products/platform-gateway/tests/`)

## R-4: Portal confirmation card

- [x] `app.js`: `confirmation_request` → inline card (tools, parameters, message, Approve/Deny); `confirmation_result` locks card; `confirmationPending` flag suppresses "No response received" on parked stream-end (`products/operator-portal/web-ui/app.js`)
- [x] Approve/Deny handler: POST `/api/v1/chat/confirm`, render resumed SSE through existing parser; 410 → expired state; role-based button hiding (`products/operator-portal/web-ui/app.js`)
- [x] `.confirm-card` styles via design tokens; cache-busting query strings bumped (`products/operator-portal/web-ui/styles.css`, `index.html`)

## R-5: Policy, documentation, and verification sync

- [x] `allow-chat-confirm` rule (platform-admin/approver/operator/developer; observer excluded) + header comment; `make sync-policy` (`shared/shared-contracts/policies/policy-default.yaml`)
- [x] Document `chat:confirm` + observer exclusion in `authorization-matrix.md` (`docs/agentic-aiops-platform/`)
- [x] Document `AGENT_HITL_CONFIRM_TIMEOUT` (incl. 0 = disabled) in `configuration-reference.md` (`docs/guides/`)
- [x] Update agent-platform, platform-gateway, and operator-portal READMEs (`products/*/README.md`)
- [x] `make verify` green (all suites, overlays, policy and version gates)

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified
- [x] living state docs updated (see spec `Impact` section)
- [x] `CHANGELOG.md` entry added referencing the spec ID
- [x] spec index in `docs/specs/README.md` updated
- [x] spec status set to `delivered`
