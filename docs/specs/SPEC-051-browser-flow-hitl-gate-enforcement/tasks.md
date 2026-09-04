# SPEC-051 Tasks: Browser Flow HITL Gate Enforcement and Password-Reset Sample Reconciliation

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

Per ADR-0008, each acceptance criterion maps to at least one asserting test
(recorded in the "criterion → test" notes below). Phase 1 (governance
artifacts) pauses for operator approval before any code task starts.

## Phase 1: Governance artifacts (draft/proposed) — pause for approval

- [x] ADR-0007 authored `proposed` (`docs/adr/0007-browser-flow-single-hitl-gate.md`)
- [x] ADR-0008 authored `proposed` (`docs/adr/0008-spec-delivery-traceability-gate.md`)
- [x] SPEC-051 triad authored `draft` (`docs/specs/SPEC-051-browser-flow-hitl-gate-enforcement/`)
- [x] Index + roadmap rows added (`docs/adr/README.md`, `docs/specs/README.md`, `docs/agentic-aiops-platform/delivery-roadmap.md`)
- [x] CONTRIBUTING delivery-gate text added (`CONTRIBUTING.md`)
- [x] **Operator approval** (2026-09-04, durable flow-context path) → flipped SPEC-051 `draft → approved`, ADR-0007/0008 `proposed → accepted`, refreshed index rows

## R-1: Platform-enforced flow-unlock — one HITL gate per mutating browser flow

- [x] Add `services/flow_approvals.py` — `FlowContext`/`FlowContextStore`/`FLOW_CONTEXTS` (session-scoped reflection of the gateway flow binding) plus `FlowApproval` (carrying the approved `skill_id`/`origin`)/`FlowApprovalStore`/`FLOW_APPROVALS` and `BROWSER_WRITE_TOOLS` (`products/agent-platform/src/agent_service/services/flow_approvals.py`)
- [x] Record `FlowContext` from each drained `web.navigate` result in `_drain_trace_queue` (single population point for both live and resumed streams) (`products/agent-platform/src/agent_service/runtime_kernel.py`)
- [x] Add the flow-unlock branch + `flow_signer` to `GatewayPermissionMiddleware` (`products/agent-platform/src/agent_service/services/kernel_middleware.py`)
- [x] Add `_sign_flow_execution` with the identity guard (unlock only while the `FLOW_APPROVALS` identity matches the live `FLOW_CONTEXTS`); wire it as `flow_signer` in `_build_middlewares` (`products/agent-platform/src/agent_service/runtime_kernel.py`)
- [x] Record the flow authority (with the card's `skill_id`/`origin`) on approval in `resume_confirmation` (`products/agent-platform/src/agent_service/runtime_kernel.py`)
- [x] Arm `EXECUTION_REQUESTS`/`EXECUTION_AUDIT_CONTEXT` + trace drain in `stream_events` (inert without an approval) (`products/agent-platform/src/agent_service/runtime_kernel.py`)
- [x] Tests: middleware ALLOW-with-identity-matching-approval / ASK-without / non-browser-ASK / unset-`EXECUTION_REQUESTS`-ASK / identity-mismatch(rebind)-ASK; kernel records-`FlowContext`-from-navigate + records-on-approval + auto-signs-subsequent-write + rebind-re-parks (`products/agent-platform/tests/test_kernel_middleware.py`, `products/agent-platform/tests/test_runtime_kernel.py`)
  - criterion → test: "parks exactly one card; subsequent writes execute without further cards" → `test_runtime_kernel` auto-sign-no-second-card; "rebind to a different flow re-parks (ADR-0007 trade-off eliminated)" → middleware identity-mismatch-ASK + `test_runtime_kernel` rebind-re-park; "no approval → still ASKs" → `test_browser_write_tools_never_auto_allowed_even_if_forced` (stays green) + middleware ASK-without-approval; "non-browser writes unaffected" → middleware `k8s_*`-with-approval-ASK

## R-2: Time-bounded, flow-scoped session authority

- [x] Add `browser_flow_approval_ttl` (`AGENT_BROWSER_FLOW_APPROVAL_TTL`, default 900, `>= 0`) (`products/agent-platform/src/agent_service/runtime_settings.py`)
- [x] Honor the TTL in `FlowApprovalStore.get`; key the authority on session id + approved flow identity (`skill_id`/`origin`) (`products/agent-platform/src/agent_service/services/flow_approvals.py`)
- [x] Tests: TTL expiry returns `None`; `ttl=0` disables unlock; identity-keyed record/get; `clear_all` (`products/agent-platform/tests/test_flow_approvals.py`)
  - criterion → test: "expired approval no longer unlocks" → `test_flow_approvals` TTL-expiry; "`0` disables flow-unlock" → `test_flow_approvals` disabled-posture; "keyed on session + flow identity" → `test_flow_approvals` identity-keying + middleware identity-mismatch-ASK

## R-3: Unlocked writes stay signed, audited, receipted, and gateway-guarded

- [x] Add `build_flow_request(...)` to `services/execution_signing.py` (`products/agent-platform/src/agent_service/services/execution_signing.py`)
- [x] Persist (`_persist_execution_request`) + audit (`execution_requested`) each auto-signed envelope; confirm receipt closure via `_observe_tool_result` (`products/agent-platform/src/agent_service/runtime_kernel.py`)
- [x] Verify (no code change) the gateway deviation guard + session-id forwarding still bound unlocked writes (`products/tool-gateway`, `products/execution-runtime`)
- [x] Tests: `build_flow_request` envelope shape, `verify_envelope` passes, `args_digest == canonical_digest(parameters)`, `confirm_id`/`decider` from the authority (`products/agent-platform/tests/test_execution_signing.py`)
  - criterion → test: "signed under the approving card's authority" → `test_execution_signing` build_flow_request; "persisted + audited" → `test_runtime_kernel` execution_requested-assert; "no new policy/audit/schema" → asserted by the absence of contract/policy edits + `make verify`

## R-4: Password-reset sample reconciled to a single gate on "Confirm reset"

- [x] Remove the reset auto-submit; keep URL pre-fill + login auto-submit (`shared/platform-ops/gitops/runtime-profiles/browser-dev/browser-check-target-pages.yaml`)
- [x] Rewrite the skill to gate on "Confirm reset" (version 1.1 → 1.2) (`samples/web-checks/password-reset/skill/ResetUserPassword.md`)
- [x] Update README + WALKTHROUGH to Design 1 (`samples/web-checks/password-reset/README.md`, `samples/web-checks/password-reset/WALKTHROUGH.md`)
- [x] Assert exactly one `web.click` card with a signed receipt; remove the second-card tolerance (`samples/web-checks/password-reset/demo/demo.sh`)
  - criterion → test: "exactly one card, `web.click`, signed receipt" → `demo.sh` chat leg (the ADR-0008 exercised-sample step); deterministic legs [1/5]-[5/5] still green

## R-5: Delivery traceability per ADR-0008

- [x] `CONTRIBUTING.md` Testing + Design Review Checklist carry the traceability/exercised-sample gate (`CONTRIBUTING.md`)
- [x] `docs/specs/README.md` Enforcement section carries the gate line (`docs/specs/README.md`)
- [x] This `tasks.md` records the criterion → test mapping for R-1..R-4 and R-6 (above)

## R-6: Flow-semantic confirmation card

- [x] `FlowState` gains `title`/`description` fields + `to_dict()` keys (`products/tool-gateway/src/tool_gateway/tools/browser_sessions.py`)
- [x] `bind_flow` populates `title`/`description` from the fetched skill (`products/tool-gateway/src/tool_gateway/tools/browser_connector.py`)
- [x] `_build_confirmation_frame` reads the maintained `FlowContext` (`FLOW_CONTEXTS.get(session_id)`, per R-1 — no park-time walk) into the parked confirmation (`products/agent-platform/src/agent_service/runtime_kernel.py`)
- [x] `PendingConfirmation.browser_flow` field (captured `FlowContext` summary) + card-level `flow_summary` on the confirmation-request frame (`products/agent-platform/src/agent_service/services/hitl_confirmations.py`)
- [x] Decode `flow_summary` → `flowSummary` (`products/operator-portal/web-ui/app/src/stream/decoder.ts`, `.../stream/models.ts`, `.../stream/useChatStream.ts`)
- [x] Render the flow headline above the tool detail in `ConfirmationCardView`; fall back to tool-level when absent (`products/operator-portal/web-ui/app/src/chat/ChatView.tsx`)
- [x] Carry `flow_summary` on the durable record for inbox/session replay (`products/operator-portal/web-ui/app/src/api/sessions.ts`, `.../chat/transcript.ts`)
- [x] Tests: gateway `to_dict`/`bind_flow` title+description; kernel frame `flow_summary` from the maintained `FlowContext` (incl. a flow bound in an earlier turn) + no-flow fallback; portal decoder + `ConfirmationCardView` headline/fallback (`products/tool-gateway/tests/`, `products/agent-platform/tests/test_runtime_kernel.py`, `products/operator-portal/web-ui/app/src/**/__tests__/`)
  - criterion → test: "headline names title/description/origin/risk_class" → kernel frame `flow_summary` assert + portal `ConfirmationCardView` headline render; "tool action retained as secondary detail" → portal card still renders `toolName`/`displayHint`; "no bound flow → tool-level fallback" → kernel no-`flow_summary` + portal fallback; "durable/replayed cards match" → `transcript`/`sessions` `flow_summary` mapping; "no new contract/schema" → absence of `shared/` edits + `make verify`

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified (each mapped to a test above)
- [x] `make verify` green; local redeploy + `RUN_CHAT_LEG=true demo.sh` green (one card, signed receipt); live portal re-check shows a single gate
- [x] living state docs updated (see spec `Impact`): `VERSION` → 0.33.0 + lockstep constants, `CHANGELOG.md`, release note + index, `docs/guides/configuration-reference.md`
- [x] flip the four SDD surfaces atomically: SPEC-051 `spec.md` status → `delivered` + delivery changelog entry; `docs/specs/README.md` row; `delivery-roadmap.md` row; this `tasks.md`
- [x] flip ADR-0007 + ADR-0008 → `accepted` and their `docs/adr/README.md` rows
- [x] `CHANGELOG.md` entry added referencing SPEC-051
- [x] spec status set to `delivered`
