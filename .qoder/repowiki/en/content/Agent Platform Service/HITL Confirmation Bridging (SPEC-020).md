# HITL Confirmation Bridging (SPEC-020)

<cite>
**Referenced Files in This Document**
- [spec.md](file://docs/specs/SPEC-020-hitl-confirmation-bridging/spec.md)
- [plan.md](file://docs/specs/SPEC-020-hitl-confirmation-bridging/plan.md)
- [tasks.md](file://docs/specs/SPEC-020-hitl-confirmation-bridging/tasks.md)
- [release-notes.md](file://docs/agentic-aiops-platform/release-notes/2026-08-21-hitl-confirmation-bridging.md)
- [mutating-tool-name-regression.md](file://docs/agentic-aiops-platform/release-notes/2026-08-28-mutating-tool-name-regression.md)
- [multimodel-runtime-and-live-discovery.md](file://docs/agentic-aiops-platform/release-notes/2026-08-24-multimodel-runtime-and-live-discovery.md)
- [approval-inbox-persistent-confirmation.md](file://docs/agentic-aiops-platform/release-notes/2026-08-25-approval-inbox-persistent-confirmation.md)
- [confirmation-race-and-restart-sweep-patch.md](file://docs/agentic-aiops-platform/release-notes/2026-08-25-confirmation-race-and-restart-sweep-patch.md)
- [post-live-check-confirmation-card-flow-headline.md](file://docs/agentic-aiops-platform/release-notes/2026-09-05-post-live-check-confirmation-card-flow-headline.md)
- [action-approval-and-change-request-card.md](file://docs/agentic-aiops-platform/release-notes/2026-09-07-action-approval-and-change-request-card.md)
- [post-live-test-credential-masking-and-hitl-hardening.md](file://docs/agentic-aiops-platform/release-notes/2026-09-11-post-live-test-credential-masking-and-hitl-hardening.md)
- [secret_params.py](file://products/agent-platform/src/agent_service/services/secret_params.py)
- [hitl_confirmations.py](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py)
- [confirmation_records.py](file://products/agent-platform/src/agent_service/services/confirmation_records.py)
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [routes.py](file://products/agent-platform/src/agent_service/api/v2/routes.py)
- [v2.py](file://products/agent-platform/src/agent_service/schemas/v2.py)
- [chat-confirm.schema.json](file://shared/shared-contracts/schemas/chat-confirm.schema.json)
- [agent-stream-event.schema.json](file://shared/shared-contracts/schemas/agent-stream-event.schema.json)
- [agent-session.schema.json](file://shared/shared-contracts/schemas/agent-session.schema.json)
- [policy-default.yaml](file://shared/shared-contracts/policies/policy-default.yaml)
- [skill.py](file://products/skills-hub/src/skills_hub/schemas/skill.py)
- [ingestion.py](file://products/skills-hub/src/skills_hub/services/ingestion.py)
- [browser_connector.py](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py)
- [chat.py](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py)
- [gateway_service.py](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py)
- [policy_engine.py](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py)
- [approvals.py](file://products/platform-gateway/src/platform_gateway/api/routes/approvals.py)
- [ChatView.tsx](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx)
- [decoder.ts](file://products/operator-portal/web-ui/app/src/stream/decoder.ts)
- [models.ts](file://products/operator-portal/web-ui/app/src/stream/models.ts)
- [sessions.ts](file://products/operator-portal/web-ui/app/src/api/sessions.ts)
- [transcript.ts](file://products/operator-portal/web-ui/app/src/chat/transcript.ts)
- [useChatStream.ts](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts)
- [k8s_connector.py](file://products/tool-gateway/src/tool_gateway/tools/k8s_connector.py)
- [config.py](file://products/tool-gateway/src/tool_gateway/core/config.py)
</cite>

## Update Summary
**Changes Made**
- Updated Enhanced Change Request Formatters section to reflect improved web.press_key element context functionality
- Documented the two tests pinning three outcomes: element named from the snapshot map, raw-ref fallback, and no ref supplied
- Updated Troubleshooting Guide with new web.press_key element context troubleshooting scenarios
- Noted in Performance Considerations that the element context is conditional on a ref being supplied
- Updated Conclusion to include the latest enhancement for improved operator understanding of browser interaction flows

## Table of Contents
1. Introduction
2. Project Structure
3. Core Components
4. Architecture Overview
5. Detailed Component Analysis
6. Dependency Analysis
7. Performance Considerations
8. Troubleshooting Guide
9. Conclusion

## Introduction
This document explains the Human-in-the-Loop (HITL) confirmation bridging implemented under SPEC-020, enhanced with SPEC-021's bounded mutating actions, SPEC-030's require-approval tier system, SPEC-031's persistent confirmation registry, SPEC-053's skill-declared step intent, **SPEC-054's action-level approval with change request cards**, and **SPEC-055's secret parameter masking hardening**. The bridge transforms kernel ASK parking into a portal-visible approval flow with tiered governance, durable state management, authored workflow intent, first-class action-level approvals, and **comprehensive secret protection through fail-closed masking**.

Key outcomes:
- Kernel ASK events become SSE confirmation_request frames with risk_level metadata and tier requirements.
- A new confirm endpoint resumes parked replies with approve/deny, enforcing tier-based approval policies.
- Platform-gateway proxies confirm requests under deny-by-default action with tier enforcement.
- Operator portal renders inline approval cards with tier badges, permission messages, and authored intent lines.
- Decisions are recorded in durable audit trail with approval rule context.
- Mutating tools require both chat:confirm approval AND tools:mutate policy authorization.
- **Tiered governance**: tier_1 permits self-approval for routine actions; tier_2 requires separate approver identity.
- **Risk-level action derivation**: Tools automatically map to policy actions based on their risk tier (read/write/admin).
- **Approval bridge**: New pending-confirmation endpoint provides authoritative state for tier enforcement decisions.
- **Persistent state**: Confirmation records survive pod restarts and replica boundaries through Postgres-backed storage.
- **Race resilience**: Concurrent approver attempts resolve to structured outcomes rather than errors.
- **Cross-session discovery**: Designated approvers can discover and act on parked confirmations across sessions via approvals inbox.
- **Owner transcript persistence**: Confirmed decisions persist in owner transcripts after re-login or pod restarts.
- **Flow summary propagation**: Browser-flow headline metadata (skill_id, origin, title, description, risk_class) preserved throughout pipeline from stream frames to final card rendering for consistent workflow framing.
- **Canonical tool name resolution**: Approved mutating tool invocations correctly resolve to gateway registry using canonical dotted names instead of sanitized model-visible names.
- **Skill-declared step intent**: Author-written `flow_intent` displayed as prominent decision line above technical details for browser flow approval workflows.
- **Action-level approval**: Explicit `approval_kind` discriminator distinguishes between flow approvals (bound browser flows) and action approvals (ad-hoc mutations), enabling per-action signed gates for unbound browser writes.
- **Change request cards**: Action approvals surface decision-relevant parameters as readable change requests with secret masking, promoting them from collapsed technical details to the approval intention.
- **Durable card-message parity**: Card confirmation messages persist on durable records so approver inbox and owner transcripts render the same message as live operator cards.
- **Improved headline leak prevention**: Explicit approval kind discrimination prevents non-browser action cards from inheriting stale flow headlines.
- **Secret parameter masking**: Fail-closed security posture ensures all secret-bearing parameters are masked unless explicitly allow-listed as safe, preventing plaintext secrets from appearing in any confirmation surface.
- **Enhanced expired confirmation handling**: Model pinning consistency ensures expired confirmation interrupts reach the correct agent instance with proper model resolution, preventing orphaned turns and transcript wedging.
- **Enhanced web.press_key element context**: Approval cards now include element location information when ref parameter is provided, improving operator understanding of where keypress actions will occur.

**Section sources**
- [spec.md:11-20](file://docs/specs/SPEC-020-hitl-confirmation-bridging/spec.md#L11-L20)
- [release-notes.md:3-35](file://docs/agentic-aiops-platform/release-notes/2026-08-21-hitl-confirmation-bridging.md#L3-L35)
- [mutating-tool-name-regression.md:7-58](file://docs/agentic-aiops-platform/release-notes/2026-08-28-mutating-tool-name-regression.md#L7-L58)
- [multimodel-runtime-and-live-discovery.md:126-136](file://docs/agentic-aiops-platform/release-notes/2026-08-24-multimodel-runtime-and-live-discovery.md#L126-L136)
- [approval-inbox-persistent-confirmation.md:6-51](file://docs/agentic-aiops-platform/release-notes/2026-08-25-approval-inbox-persistent-confirmation.md#L6-L51)
- [post-live-check-confirmation-card-flow-headline.md:1-56](file://docs/agentic-aiops-platform/release-notes/2026-09-05-post-live-check-confirmation-card-flow-headline.md#L1-L56)
- [action-approval-and-change-request-card.md:1-147](file://docs/agentic-aiops-platform/release-notes/2026-09-07-action-approval-and-change-request-card.md#L1-L147)
- [post-live-test-credential-masking-and-hitl-hardening.md:54-169](file://docs/agentic-aiops-platform/release-notes/2026-09-11-post-live-test-credential-masking-and-hitl-hardening.md#L54-L169)
- [SPEC-053 spec.md:19-51](file://docs/specs/SPEC-053-skill-declared-step-intent/spec.md#L19-L51)
- [SPEC-054 spec.md:32-105](file://docs/specs/SPEC-054-action-approval-and-change-request-card/spec.md#L32-L105)
- [SPEC-055 plan.md:331-347](file://docs/specs/SPEC-055-develop-as-you-go-skill-graduation/plan.md#L331-L347)
- [spec.md:17-31](file://docs/specs/SPEC-030-require-approval-policy-semantics/spec.md#L17-L31)
- [spec.md:43-67](file://docs/specs/SPEC-031-approval-inbox-persistent-confirmation/spec.md#L43-L67)

## Project Structure
The feature spans three products plus shared contracts, enhanced with SPEC-021 capabilities, SPEC-030 tier enforcement, SPEC-031 persistent storage, SPEC-053 skill-declared intent, **SPEC-054 action-level approvals**, **SPEC-055 secret masking hardening**, v0.23.1 canonical name resolution, v0.33.1 flow summary propagation, **enhanced expired confirmation handling with model pinning consistency**, and **enhanced web.press_key element context**:
- Agent platform: runtime park/resume, in-memory registry with risk tracking, v2 routes, schemas, settings, durable confirmation records store, and **secret parameter masking with fail-closed security posture**.
- Platform gateway: confirm proxy route, tiered policy enforcement, audit emission, approval validation, and approvals inbox relay.
- Tool gateway: risk-tier admission gate, mutating tool registration, tools:mutate enforcement, and browser flow binding with intent propagation.
- Skills hub: skill envelope validation, ingestion pipeline, and storage backend with flow_intent support.
- Operator portal: confirmation card rendering with tier badges, confirm handler, approvals view, authored intent display, **change request layout with secret masking**, and **enhanced 410 Gone response handling**.
- Shared contracts: stream event schema growth with risk_level, confirm request schema, policy rule with approval tiers, session schema with flow_summary support, and skill schema with flow_intent field.

```mermaid
graph TB
subgraph "Skills Hub"
SH["schemas/skill.py"]
SI["services/ingestion.py"]
SS["services/skill_store.py"]
end
subgraph "Tool Gateway"
BC["tools/browser_connector.py"]
TG["tools/k8s_connector.py"]
TC["core/config.py"]
end
subgraph "Agent Platform"
RK["runtime_kernel.py"]
HC["services/hitl_confirmations.py"]
CR["services/confirmation_records.py"]
SP["services/secret_params.py"]
FA["services/flow_approvals.py"]
R2["api/v2/routes.py"]
S2["schemas/v2.py"]
end
subgraph "Platform Gateway"
GC["api/routes/chat.py"]
GS["services/gateway_service.py"]
PE["services/policy_engine.py"]
AI["api/routes/approvals.py"]
end
subgraph "Operator Portal"
CV["chat/ChatView.tsx"]
DT["stream/decoder.ts"]
MD["stream/models.ts"]
ST["api/sessions.ts"]
TR["chat/transcript.ts"]
UCS["stream/useChatStream.ts"]
end
PG["PostgreSQL"]
SC["shared/shared-contracts/schemas/*"]
POL["shared/shared-contracts/policies/policy-default.yaml"]
SH --> BC
BC --> FA
FA --> RK
RK --> HC
RK --> CR
RK --> SP
CR --> PG
GC -.-> POL
R2 -.-> SC
GS -.-> SC
CV -.-> SC
DT -.-> SC
ST -.-> SC
TR -.-> SC
UCS -.-> SC
TG -.-> TC
AI -.-> AI
```

**Diagram sources**
- [skill.py:15-43](file://products/skills-hub/src/skills_hub/schemas/skill.py#L15-L43)
- [ingestion.py:199-213](file://products/skills-hub/src/skills_hub/services/ingestion.py#L199-L213)
- [browser_connector.py:410-421](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L410-L421)
- [flow_approvals.py:54-97](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L54-L97)
- [runtime_kernel.py:657-794](file://products/agent-platform/src/agent_service/runtime_kernel.py#L657-L794)
- [hitl_confirmations.py:85-208](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L85-L208)
- [confirmation_records.py:214-565](file://products/agent-platform/src/agent_service/services/confirmation_records.py#L214-L565)
- [secret_params.py:1-149](file://products/agent-platform/src/agent_service/services/secret_params.py#L1-L149)
- [routes.py:156-227](file://products/agent-platform/src/agent_service/api/v2/routes.py#L156-L227)
- [v2.py:120-150](file://products/agent-platform/src/agent_service/schemas/v2.py#L120-L150)
- [chat.py:134-175](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L134-L175)
- [gateway_service.py:336-446](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L336-L446)
- [policy_engine.py:335-389](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L335-389)
- [approvals.py:19-51](file://products/platform-gateway/src/platform_gateway/api/routes/approvals.py#L19-L51)
- [ChatView.tsx:370-569](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L370-L569)
- [decoder.ts:39-125](file://products/operator-portal/web-ui/app/src/stream/decoder.ts#L39-L125)
- [models.ts:70-92](file://products/operator-portal/web-ui/app/src/stream/models.ts#L70-L92)
- [sessions.ts:58-85](file://products/operator-portal/web-ui/app/src/api/sessions.ts#L58-L85)
- [transcript.ts:116-133](file://products/operator-portal/web-ui/app/src/chat/transcript.ts#L116-L133)
- [useChatStream.ts:393-407](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L393-L407)

**Section sources**
- [plan.md:3-6](file://docs/specs/SPEC-020-hitl-confirmation-bridging/plan.md#L3-L6)
- [tasks.md:5-41](file://docs/specs/SPEC-020-hitl-confirmation-bridging/tasks.md#L5-L41)

## Core Components
- **Enhanced Confirmation Registry**: In-memory per-process store keyed by session_id with risk tracking and canonical name mapping; supports register, claim, resolve, expiry, and parked checks with risk tier awareness. Single pending confirmation per session with optional risk metadata and gateway name mapping.
- **Durable Confirmation Records Store**: Postgres-backed persistence layer that survives pod restarts and maintains consistency across replicas. Implements bounded storage (50 records per session, 30-day inbox history) with automatic cleanup and stale record handling. Now includes flow_summary JSONB column for browser-flow headline preservation and **approval_kind/change_request/message fields for action-level approvals**.
- **Runtime kernel bridge**: Translates RequireUserConfirmEvent into confirmation_request frame with risk_level payload, registers pending calls with risk mapping and canonical name resolution, ends stream without message_end, and resumes via UserConfirmResultEvent on decision. Now persists confirmation lifecycle to durable store before streaming and includes flow_summary in parked records. **Updated**: Integrates pre-redaction of pending calls before streaming and persistence to prevent secret leakage. **Enhanced**: Uses consistent model pinning for expired confirmation interrupts to ensure they reach the correct agent instance.
- **Flow Context Management**: Tracks browser flow state including skill_id, origin, title, description, risk_class, and now flow_intent for authored intent display. Provides summary() method that emits complete flow context including the new flow_intent field for card rendering.
- **Confirm route (agent platform)**: POST /api/v2/chat/confirm validates ownership, claims entry, handles expired/unknown states, streams resumed reply with confirmation_result first. **Updated**: Now uses degraded model resolution to prevent UnknownModelError exceptions and removed session ownership assertion for tier_2 approvers. **Enhanced**: Persists decision outcomes immediately at claim time for race resilience. **New**: Includes flow_summary coercion for schema compliance. **Critical Enhancement**: When handling expired confirmations (410 Gone), passes the session's pinned model to expire_confirmation to ensure the interrupt reaches the correct agent instance.
- **Pending confirmation endpoint**: GET /api/v2/chat/pending-confirmation provides authoritative parked batch metadata including owner_user_id, derived policy action, and pending_calls with risk levels for gateway tier enforcement.
- **Confirm proxy (platform gateway)**: POST /api/v1/chat/confirm enforces chat:confirm action, obtains delegated token, proxies to agent platform, emits confirmation_decided audit when kernel applies decision. **Enhanced**: Enforces tier-based approval requirements against decided_by_roles using pending confirmation data. **Updated**: Passes through structured 409 responses with detailed resolution information.
- **Approvals inbox API**: GET /api/v1/approvals/inbox provides cross-session discovery for designated approvers with metadata-only items preserving owner scoping.
- **Session detail confirmation cards**: GET /api/v2/sessions/{id} includes additive `confirmations` field with ordered records from durable store, enabling persistent card rendering in owner transcripts. **Enhanced**: Now includes flow_summary for browser-flow headline rendering.
- **Stream event normalization**: `_normalize_stream_event` passes flow_summary through defensive `_coerce_flow_summary` that keeps only contract's fields including flow_intent and degrades non-dict summaries to absent.
- **Portal decoder enhancement**: `toFlowSummary` function parses card-level browser-flow headline from stream frames, returning undefined for non-browser cards so they fall back to plain tool-action rendering. **Updated**: Now includes flowIntent field mapping from flow_intent wire format.
- **Tiered Policy Engine**: Evaluates actions with deny > require_approval > allow precedence, returns ApprovalSpec with tier information for require_approval decisions.
- **Risk-tier admission (tool gateway)**: Enforces tools:mutate policy action for write/admin tools, gates k8s.delete_pod behind GATEWAY_MUTATING_TOOLS_ENABLED.
- **Skill intent validation**: Validates flow_intent frontmatter declarations requiring web_target presence, enforcing 200 character limits and string type constraints.
- **Action-level approval discriminator**: Explicit `approval_kind` field distinguishes between flow approvals (bound browser flows) and action approvals (ad-hoc mutations), enabling per-action signed gates for unbound browser writes on allowlisted origins.
- **Change request projection**: Secret-masked display projection of decision-relevant parameters for action approvals, promoting them from collapsed technical details to readable change requests.
- **Card message persistence**: Confirmation card messages persist on durable records ensuring parity between live operator cards and replayed surfaces.
- **Secret parameter masking**: **Fail-closed security posture** ensures all secret-bearing parameters are masked unless explicitly allow-listed as safe. Uses curated formatters for specific tools and generic fallback masking for unknown parameters. **Updated**: Pre-redaction occurs in runtime kernel before streaming and persistence to prevent any secret leakage.
- **Portal card**: Renders confirmation_request as inline card with tier badges ("operator confirmation" vs "approver required"), tool names, parameters, and permission message; posts to gateway confirm and continues SSE stream after decision. **Enhanced**: Supports persistent card rendering from durable records and Approvals view for designated approvers. **New**: Displays authored intent as prominent decision line above technical details when flow_intent is present. **New**: Renders change request layout for action approvals with secret masking. **Enhanced**: Properly handles 410 Gone responses by settling confirmation cards and preventing stuck UI states.
- **Enhanced web.press_key element context**: The `_cr_web_press_key` function now conditionally includes element location information when a ref parameter is provided, improving operator understanding of where keypress actions will occur. This aligns with the other four members of `browser_ref_tools` (click, type, select, upload_file), which already projected the element label; `web.evaluate` takes no ref and `web.fill_credential` is read-tier, parking no card.

**Section sources**
- [hitl_confirmations.py:34-208](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L34-L208)
- [confirmation_records.py:114-565](file://products/agent-platform/src/agent_service/services/confirmation_records.py#L114-L565)
- [runtime_kernel.py:657-794](file://products/agent-platform/src/agent_service/runtime_kernel.py#L657-L794)
- [routes.py:65-227](file://products/agent-platform/src/agent_service/api/v2/routes.py#L65-L227)
- [routes.py:497-614](file://products/agent-platform/src/agent_service/api/v2/routes.py#L497-L614)
- [v2.py:120-150](file://products/agent-platform/src/agent_service/schemas/v2.py#L120-L150)
- [v2.py:210-242](file://products/agent-platform/src/agent_service/schemas/v2.py#L210-L242)
- [chat.py:134-175](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L134-L175)
- [gateway_service.py:336-446](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L336-L446)
- [policy_engine.py:97-148](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L97-148)
- [approvals.py:19-51](file://products/platform-gateway/src/platform_gateway/api/routes/approvals.py#L19-L51)
- [k8s_connector.py:439-518](file://products/tool-gateway/src/tool_gateway/tools/k8s_connector.py#L439-L518)
- [config.py:75-81](file://products/tool-gateway/src/tool_gateway/core/config.py#L75-L81)
- [decoder.ts:39-125](file://products/operator-portal/web-ui/app/src/stream/decoder.ts#L39-L125)
- [ChatView.tsx:370-569](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L370-L569)
- [flow_approvals.py:54-97](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L54-L97)
- [skill.py:15-43](file://products/skills-hub/src/skills_hub/schemas/skill.py#L15-L43)
- [ingestion.py:199-213](file://products/skills-hub/src/skills_hub/services/ingestion.py#L199-L213)
- [secret_params.py:1-149](file://products/agent-platform/src/agent_service/services/secret_params.py#L1-L149)
- [useChatStream.ts:393-407](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L393-L407)

## Architecture Overview
End-to-end flow from kernel ASK to portal decision and resumed execution, enhanced with tiered approval enforcement, resilient model resolution, persistent state management, canonical tool name resolution, flow summary propagation, skill-declared intent display, **action-level approval discrimination**, **fail-closed secret masking**, **enhanced expired confirmation handling with model pinning consistency**, and **enhanced web.press_key element context**:

```mermaid
sequenceDiagram
participant Skill as "Skill Declaration"
participant Hub as "Skills Hub"
participant GW as "Tool Gateway"
participant AP as "Agent Platform"
participant RK as "Runtime Kernel"
participant Reg as "ConfirmationRegistry"
participant Store as "ConfirmationRecordStore"
participant DB as "PostgreSQL"
participant Portal as "Operator Portal"
Note over Skill : Skill declares flow_intent frontmatter
Skill->>Hub : Ingest skill with flow_intent
Hub->>Hub : Validate flow_intent requires web_target
Hub->>DB : Persist skill with flow_intent
Note over RK : Stream turn begins
RK-->>AP : RequireUserConfirmEvent + risk_levels + flow_summary
AP->>Reg : register(session, user, reply, tool_calls, timeout, risk_levels, gateway_names)
AP->>AP : Build pending_calls_payload() once
AP->>AP : _confirmation_message(pending_calls) - compute message BEFORE redaction
AP->>AP : redact_pending_calls(pending, pending_calls) - fail-closed masking
AP->>Store : save_parked(confirm_id, session_id, owner, pending_calls, action, flow_summary, approval_kind, change_request, message)
Store->>DB : INSERT confirmation_records (with redacted pending_calls JSONB)
AP-->>Portal : data : {type : "confirmation_request", confirm_id, pending_calls[risk_level, canonical_tool_name, change_request], flow_summary{title, description, flow_intent}, approval_kind, message}
Note over Portal : For web.press_key with ref parameter, change_request includes element context
Portal->>GW : POST /api/v1/chat/confirm {session_id, confirm_id, decision}
GW->>GW : enforce_policy("chat : confirm")
alt Decision involves write/admin tool
GW->>GW : evaluate("tools : mutate") - may return require_approval
GW->>GW : check tier enforcement (decided_by_roles)
alt tier_2 self-approval attempt
GW-->>Portal : 403 Forbidden (self_approval)
else tier_1 or approved tier_2
GW->>AP : POST /api/v2/chat/confirm (delegated token)
AP->>Reg : claim(session, confirm_id, timeout)
alt Expired
AP->>AP : _resolve_model(None, session.model) - get pinned model
AP->>RK : expire_confirmation(session, confirm_id, pinned_model)
RK->>RK : ensure_agent(session, None, pinned_model) - use same model
RK-->>AP : UserInterruptEvent to correct agent instance
AP-->>Portal : 410 Gone (properly settled)
else Unknown/Resolved
AP->>Store : load_record(session, confirm_id)
alt Already resolved
AP-->>Portal : 409 already_resolved (structured outcome)
else Unknown
AP-->>Portal : 404 Not Found
else Owner mismatch
AP-->>Portal : Error frame
else OK
AP->>AP : _resolve_model(None, session.model) - degrades stale pins
AP->>Store : mark_resolved(session, confirm_id, status, decider, decision) - claim-time persistence
AP->>RK : resume_confirmation(pending, decision, bearer_token, model_id)
RK-->>AP : Stream starts with confirmation_result(approved|denied)
AP->>Store : mark_resolved(session, confirm_id, status, decider, decision) - safety net
Store->>DB : UPDATE confirmation_records
AP-->>Portal : SSE continuation (tool_call/tool_result/message_*)
GW->>GW : Emit confirmation_decided audit on first confirmation_result
end
end
end
```

**Diagram sources**
- [skill.py:15-43](file://products/skills-hub/src/skills_hub/schemas/skill.py#L15-L43)
- [ingestion.py:199-213](file://products/skills-hub/src/skills_hub/services/ingestion.py#L199-L213)
- [browser_connector.py:410-421](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L410-L421)
- [flow_approvals.py:54-97](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L54-L97)
- [runtime_kernel.py:657-794](file://products/agent-platform/src/agent_service/runtime_kernel.py#L657-L794)
- [runtime_kernel.py:1090-1125](file://products/agent-platform/src/agent_service/runtime_kernel.py#L1090-L1125)
- [runtime_kernel.py:2190-2244](file://products/agent-platform/src/agent_service/runtime_kernel.py#L2190-L2244)
- [confirmation_records.py:407-455](file://products/agent-platform/src/agent_service/services/confirmation_records.py#L407-455)
- [routes.py:156-227](file://products/agent-platform/src/agent_service/api/v2/routes.py#L156-L227)
- [routes.py:497-614](file://products/agent-platform/src/agent_service/api/v2/routes.py#L497-L614)
- [routes.py:277-294](file://products/agent-platform/src/agent_service/api/v2/routes.py#L277-L294)
- [routes.py:395-409](file://products/agent-platform/src/agent_service/api/v2/routes.py#L395-409)
- [gateway_service.py:336-446](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L336-L446)
- [chat.py:134-175](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L134-L175)
- [policy_engine.py:335-389](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L335-389)
- [hitl_confirmations.py:101-199](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L101-L199)
- [decoder.ts:39-125](file://products/operator-portal/web-ui/app/src/stream/decoder.ts#L39-L125)
- [useChatStream.ts:393-407](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L393-L407)

## Detailed Component Analysis

### Enhanced Confirmation Registry (In-Memory State with Risk Tracking and Canonical Name Mapping)
Responsibilities:
- Register pending confirmations per session with TTL awareness and risk level mapping.
- Atomic claim to prevent double-resume.
- Resolve entries after decision or expiry closure.
- Provide parked checks for new-turn rejection.
- Track risk levels per tool call for portal visualization.
- **v0.23.1 Enhancement**: Maintain gateway_names mapping between sanitized model-visible names and canonical dotted names required by gateway registry.
- **New**: Derive policy actions from risk levels using RISK_LEVEL_ACTIONS mapping.

Concurrency and safety:
- Single-flight claim via claimed flag prevents duplicate decisions.
- Expiry path uses take_for_expiry to avoid interrupting in-flight resumes.
- No persistence across restarts; parked state is lost safely.
- Risk levels captured at park time from toolkit discovery.
- **v0.23.1 Enhancement**: Canonical name mapping captured at park time ensures approved tool invocations resolve correctly at gateway registry.

```mermaid
classDiagram
class PendingConfirmation {
+string confirm_id
+string session_id
+string user_id
+string reply_id
+list tool_calls
+dict risk_levels
+dict gateway_names
+float created_at
+bool resolved
+bool claimed
+is_expired(timeout) bool
+pending_calls_payload() list
+highest_action() string?
+tool_names() list
+flow_summary() dict?
}
class ConfirmationRegistry {
+register(session_id, user_id, reply_id, tool_calls, timeout, risk_levels, gateway_names) PendingConfirmation
+get(session_id, confirm_id, timeout) PendingConfirmation
+claim(session_id, confirm_id, timeout) PendingConfirmation
+take_for_expiry(session_id, confirm_id) PendingConfirmation
+peek_parked(session_id) PendingConfirmation?
+resolve(session_id, confirm_id) void
+is_parked(session_id, timeout) bool
}
ConfirmationRegistry --> PendingConfirmation : "manages"
```

**Diagram sources**
- [hitl_confirmations.py:34-208](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L34-L208)

**Section sources**
- [hitl_confirmations.py:85-208](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L85-L208)

### Durable Confirmation Records Store (Postgres Backing)
Responsibilities:
- Persist every parked confirmation and its resolution to PostgreSQL for restart survival and replica consistency.
- Implement bounded storage with session-scoped caps (50 records per session) and inbox history windows (30 days).
- Handle stale pending records on startup by marking them as expired since parked kernel replies cannot survive process restarts.
- Provide best-effort persistence that degrades gracefully when Postgres is unavailable.
- Support cross-session queries for approvals inbox with metadata-only exposure.
- **New**: Include flow_summary JSONB column for browser-flow headline preservation across all surfaces.
- **New**: Add approval_kind, change_request, and message columns for action-level approval support and card message parity.
- **Updated**: Stores redacted pending_calls with fail-closed secret masking applied before persistence.

Storage design:
- Uses same Postgres posture as SPEC-016 session store with shared database connection management.
- Implements opportunistic sweep patterns similar to other stores for efficient cleanup.
- Maintains separation between hot-path in-memory registry and durable record store.
- **Enhanced**: Startup sweep now uses configurable TTL scoping via AGENT_HITL_CONFIRM_TIMEOUT for precise stale record identification.
- **New**: flow_summary column migration handled automatically at startup for backward compatibility.
- **New**: approval_kind, change_request, and message columns added for action-level approval support.
- **Updated**: Redacted parameters stored in pending_calls JSONB to prevent secret leakage in persisted records.

```mermaid
flowchart TD
Park["save_parked(record with flow_summary, approval_kind, change_request, message)"] --> Insert["INSERT confirmation_records (JSONB columns)"]
Insert --> Evict{"Over cap?"}
Evict -- Yes --> Sweep["DELETE oldest records"]
Evict -- No --> Continue["Continue"]
Sweep --> Continue
Continue --> Audit["Sweep old resolved records"]
Audit --> Complete["Complete"]
Resolve["mark_resolved(session, confirm_id, status, decider, decision)"] --> Update["UPDATE confirmation_records"]
Update --> Complete
Startup["initialize(stale_after_seconds)"] --> CloseStale["Close pending records past TTL"]
CloseStale --> Complete
Redact["redact_pending_calls(pending, payload)"] --> MaskParams["Apply fail-closed masking to parameters"]
MaskParams --> StoreRedacted["Store redacted parameters in pending_calls"]
```

**Diagram sources**
- [confirmation_records.py:407-455](file://products/agent-platform/src/agent_service/services/confirmation_records.py#L407-455)
- [confirmation_records.py:233-317](file://products/agent-platform/src/agent_service/services/confirmation_records.py#L233-L317)
- [confirmation_records.py:279-285](file://products/agent-platform/src/agent_service/services/confirmation_records.py#L279-L285)
- [confirmation_records.py:415-431](file://products/agent-platform/src/agent_service/services/confirmation_records.py#L415-L431)
- [hitl_confirmations.py:369-399](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L369-L399)

**Section sources**
- [confirmation_records.py:114-565](file://products/agent-platform/src/agent_service/services/confirmation_records.py#L114-L565)

### Flow Context Management (Browser Flow Intent Tracking)
Responsibilities:
- Track browser flow state including skill_id, origin, title, description, risk_class, and flow_intent for authored intent display.
- Record flow context from gateway bind_flow results with defensive field coercion.
- Provide summary() method that emits complete flow context including flow_intent for card rendering.
- Maintain flow identity (skill_id, origin) for authority scoping and deviation detection.
- Support flow approval tracking with TTL-based authority expiration.

Flow context structure:
- FlowContext dataclass captures all flow metadata including the new flow_intent field.
- record() method reads flow_intent from gateway flow dict with safe string coercion.
- summary() method includes flow_intent in emitted payload for confirmation frames.
- FlowApprovalStore tracks authorizations scoped to flow identity with TTL enforcement.

```mermaid
flowchart TD
BindFlow["Gateway bind_flow result"] --> Record["FlowContext.record(flow_dict)"]
Record --> ExtractFields["Extract skill_id, origin, title, description, flow_intent, risk_class"]
ExtractFields --> CoerceFields["Coerce to safe defaults"]
CoerceFields --> StoreContext["Store in FLOW_CONTEXTS[session_id]"]
StoreContext --> Summary["FlowContext.summary()"]
Summary --> EmitFrame["Emit flow_summary with flow_intent"]
EmitFrame --> CardRender["Portal renders authored intent"]
```

**Diagram sources**
- [flow_approvals.py:54-97](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L54-L97)
- [flow_approvals.py:112-131](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L112-L131)

**Section sources**
- [flow_approvals.py:54-97](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L54-L97)
- [flow_approvals.py:112-131](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L112-L131)

### Runtime Kernel Bridge (Park and Resume with Risk Mapping, Canonical Name Resolution, Flow Summary Propagation, Pre-Redaction, and Enhanced Expired Handling)
Behavior:
- On RequireUserConfirmEvent, builds confirmation_request frame with risk_level payload, registers pending calls with risk mapping and canonical name resolution, yields frame, and ends stream without message_end.
- **Enhanced**: Persists confirmation lifecycle to durable store before streaming confirmation_request frame to client.
- **New**: Includes flow_summary in parked records and confirmation_request frames for browser-flow headline preservation.
- **New**: Adds approval_kind discriminator to distinguish between flow and action approvals.
- **New**: Assembles change_request projection from parameters with secret masking for action approvals.
- **New**: Persists card message for durable parity across surfaces.
- **Updated**: **Pre-redaction integration point**: Applies fail-closed secret masking to pending_calls payload BEFORE streaming to client and BEFORE persisting to durable store, ensuring no plaintext secrets appear anywhere in the confirmation pipeline.
- **Critical Security Enhancement**: Message computation happens BEFORE redaction to ensure the curated effect sentence can read raw parameters, while the streamed and persisted payload carries redacted values.
- resume_confirmation sets delegated token, emits confirmation_result first, then streams resumed reply through normalization/evidence pipeline.
- **Enhanced**: Records resolution outcome to durable store after confirmation_result flows through.
- Handles chained parks: resumed turns can trigger another ASK, emitting a fresh confirmation_request.
- Filters mutating tools when HITL bridging is disabled to maintain honest posture.
- **v0.23.1 Enhancement**: Captures gateway_tool_name mapping from toolkit to ensure canonical names flow through signed execution envelopes.
- **Critical Enhancement**: expire_confirmation now accepts model_id parameter to ensure interrupts reach the correct agent instance with proper model pinning, preventing orphaned turns where parked calls never receive their interrupted result.

```mermaid
flowchart TD
Start(["Stream Event"]) --> CheckASK{"RequireUserConfirmEvent?"}
CheckASK -- No --> Normalize["Normalize event"]
Normalize --> Yield["Yield normalized event"]
CheckASK -- Yes --> BuildFrame["Build confirmation_request frame with risk_level + flow_summary"]
BuildFrame --> DetermineKind{"Determine approval_kind"}
DetermineKind --> FlowCheck{"Browser write + bound flow?"}
FlowCheck -- Yes --> SetFlow["Set approval_kind = 'flow'"]
FlowCheck -- No --> SetAction["Set approval_kind = 'action'"]
SetFlow --> AssembleChangeRequest["Assemble change_request for action approvals"]
SetAction --> AssembleChangeRequest
AssembleChangeRequest --> MapNames["_toolkit_gateway_name_map(toolkit)"]
MapNames --> Register["Register pending confirmation with risk_levels, gateway_names, flow_summary"]
Register --> BuildPayload["Build pending_calls_payload() ONCE"]
BuildPayload --> ComputeMessage["_confirmation_message(payload) - BEFORE redaction"]
ComputeMessage --> RedactPayload["redact_pending_calls(pending, payload) - FAIL-CLOSED MASKING"]
RedactPayload --> Persist["save_parked(confirm_id, session_id, owner, pending_calls, action, flow_summary, approval_kind, change_request, message)"]
Persist --> EndStream["End stream (no message_end)"]
EndStream --> WaitDecision["Await confirm decision"]
WaitDecision --> Resume["resume_confirmation(UserConfirmResultEvent)"]
Resume --> ResultFrame["Emit confirmation_result"]
ResultFrame --> RecordResolution["mark_resolved(status, decider, decision)"]
RecordResolution --> ContinueStream["Stream resumed events"]
ContinueStream --> ChainedASK{"Another ASK?"}
ChainedASK -- Yes --> BuildFrame
ChainedASK -- No --> Complete["Complete turn"]
ExpiredPath["expire_confirmation(session, confirm_id, model_id)"] --> EnsureAgent["ensure_agent(session, None, model_id) - use pinned model"]
EnsureAgent --> Interrupt["Send UserInterruptEvent to correct agent"]
Interrupt --> CleanUp["Clean up parked reply"]
```

**Diagram sources**
- [runtime_kernel.py:555-644](file://products/agent-platform/src/agent_service/runtime_kernel.py#L555-L644)
- [runtime_kernel.py:657-794](file://products/agent-platform/src/agent_service/runtime_kernel.py#L657-L794)
- [runtime_kernel.py:1090-1125](file://products/agent-platform/src/agent_service/runtime_kernel.py#L1090-L1125)
- [runtime_kernel.py:1328-1344](file://products/agent-platform/src/agent_service/runtime_kernel.py#L1328-L1344)
- [runtime_kernel.py:2190-2244](file://products/agent-platform/src/agent_service/runtime_kernel.py#L2190-L2244)
- [hitl_confirmations.py:369-399](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L369-L399)

**Section sources**
- [runtime_kernel.py:657-794](file://products/agent-platform/src/agent_service/runtime_kernel.py#L657-L794)
- [runtime_kernel.py:1090-1125](file://products/agent-platform/src/agent_service/runtime_kernel.py#L1090-L1125)
- [runtime_kernel.py:1328-1344](file://products/agent-platform/src/agent_service/runtime_kernel.py#L1328-L1344)
- [runtime_kernel.py:2190-2244](file://products/agent-platform/src/agent_service/runtime_kernel.py#L2190-L2244)

### Enhanced Change Request Formatters (Curated Tool-Specific Projections)
Responsibilities:
- Provide curated change request projections for demo-critical mutating tools with human-readable effect sentences.
- Apply fail-closed secret masking to sensitive parameters while preserving structural information.
- Handle optional parameters intelligently (e.g., web.press_key only includes element context when ref is provided).
- Align behavior across browser tools for consistent operator experience.

**Updated web.press_key formatter**: The `_cr_web_press_key` function now conditionally includes element location information when a ref parameter is provided, improving operator understanding of where keypress actions will occur. This aligns with the other four members of `browser_ref_tools` (click, type, select, upload_file), which already projected the element label; `web.evaluate` takes no ref and `web.fill_credential` is read-tier, parking no card.

Key behaviors:
- **Conditional element context**: Only includes "in [element]" when ref parameter is present
- **Smart fallback**: Omits element context entirely when no ref is provided (avoids noise)
- **Consistent formatting**: Uses same element label logic as other browser tools
- **Security**: Applies appropriate masking to sensitive parameters

Examples:
- With ref: "Press key 'Enter' in 'Search filters form'"
- Without ref: "Press key 'Escape'" (no element context)
- With raw ref: "Press key 'Enter' in 'ref 4'" (when element map not available)

```mermaid
flowchart TD
Parameters["web.press_key parameters"] --> CheckRef{"Has ref parameter?"}
CheckRef -- Yes --> GetElement["Get element label from display_hint or ref"]
CheckRef -- No --> BareSentence["Create bare sentence: Press key 'X'"]
GetElement --> ElementContext["Add element context: in 'Element Name'"]
ElementContext --> FinalSummary["Final: Press key 'X' in 'Element Name'"]
BareSentence --> FinalSummary
```

**Diagram sources**
- [hitl_confirmations.py:273-285](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L273-L285)

**Section sources**
- [hitl_confirmations.py:273-285](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L273-L285)
- [test_hitl_confirmations.py:359-380](file://products/agent-platform/tests/test_hitl_confirmations.py#L359-L380)

### Secret Parameter Masking (Fail-Closed Security Posture)
Responsibilities:
- **Fail-closed masking**: All secret-bearing parameters are masked unless explicitly allow-listed as safe, preventing plaintext secrets from appearing in any confirmation surface.
- **Curated formatters**: Specific tools get tailored change request projections with appropriate masking (e.g., web.fill_credential shows reference-only, never values).
- **Generic fallback**: Unknown tools get label→value projection with fail-closed masking applied to all parameters.
- **Vocabulary synchronization**: Twin masking vocabularies maintained between agent platform and tool gateway, validated by build system to prevent drift.
- **Display-only projection**: Masking never affects signed parameters or args_digest calculations, maintaining security integrity.

Security posture:
- **Fail-closed by default**: Parameters mask unless positively listed in KNOWN_SAFE_FIELDS allow-list.
- **Name-based masking**: Parameter names containing secret indicators (password, token, secret, etc.) are always masked.
- **Opaque value fields**: Certain tool parameters (like web.type.text) are always masked regardless of parameter name.
- **Safe field allow-list**: Only explicitly whitelisted fields (like k8s.delete_pod.name, k8s.delete_pod.namespace) render verbatim.
- **Twin vocabulary validation**: Build system validates that agent platform and tool gateway masking vocabularies remain synchronized.

```mermaid
flowchart TD
Parameter["Tool Parameter"] --> CheckKnownSafe{"Is in KNOWN_SAFE_FIELDS?"}
CheckKnownSafe -- Yes --> RenderVerbatim["Render verbatim value"]
CheckKnownSafe -- No --> CheckSecretName{"Contains secret indicator?"}
CheckSecretName -- Yes --> MaskValue["Mask to ***"]
CheckSecretName -- No --> CheckOpaque{"Is opaque value field?"}
CheckOpaque -- Yes --> MaskValue
CheckOpaque -- No --> DefaultMask["Default mask (fail-closed)"]
MaskValue --> ApplyMask["Apply *** mask"]
DefaultMask --> ApplyMask
ApplyMask --> Display["Display masked value"]
RenderVerbatim --> Display
```

**Diagram sources**
- [secret_params.py:1-149](file://products/agent-platform/src/agent_service/services/secret_params.py#L1-L149)
- [hitl_confirmations.py:229-349](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L229-L349)

**Section sources**
- [secret_params.py:1-149](file://products/agent-platform/src/agent_service/services/secret_params.py#L1-L149)
- [hitl_confirmations.py:229-349](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L229-L349)

### Stream Event Normalization (Flow Summary Coercion)
Responsibilities:
- Translate kernel stream chunks into contract-conformant events with defensive field validation.
- **New**: Include flow_summary field in AgentStreamEvent schema (v9 → v11) for confirmation_request frames carrying bound browser-flow headlines including flow_intent.
- **New**: Implement `_coerce_flow_summary` function that keeps only contract's fields including flow_intent and degrades non-dict summaries to absent.
- Ensure malformed flow summaries never fail frame's additionalProperties:false validation.
- Maintain backward compatibility for non-browser cards where flow_summary is absent.

Schema evolution:
- Stream contract bumped from v9 to v11 to declare optional flow_intent field in flow_summary and approval_kind/change_request fields.
- Defensive coercion ensures only valid string fields survive transformation.
- Non-dict flow summaries degrade to None, allowing fallback to plain tool-action rendering.

```mermaid
flowchart TD
RawFrame["Kernel Frame"] --> Normalize["_normalize_stream_event()"]
Normalize --> ExtractFields["Extract core fields"]
ExtractFields --> CoerceFlow["Coerce flow_summary"]
CoerceFlow --> Validate{"Is flow_summary dict?"}
Validate -- No --> SetNone["Set flow_summary = None"]
Validate -- Yes --> FilterFields["Filter to contract fields including flow_intent"]
FilterFields --> SchemaConform["Create AgentStreamEvent v11"]
SetNone --> SchemaConform
SchemaConform --> Wire["Wire to Portal"]
```

**Diagram sources**
- [routes.py:497-614](file://products/agent-platform/src/agent_service/api/v2/routes.py#L497-L614)
- [v2.py:120-150](file://products/agent-platform/src/agent_service/schemas/v2.py#L120-L150)

**Section sources**
- [routes.py:497-614](file://products/agent-platform/src/agent_service/api/v2/routes.py#L497-L614)
- [v2.py:120-150](file://products/agent-platform/src/agent_service/schemas/v2.py#L120-L150)

### Skill Intent Validation and Storage
Responsibilities:
- Validate flow_intent frontmatter declarations in skill documents.
- Enforce flow_intent requires web_target declaration (mirroring risk_class validation).
- Limit flow_intent to 200 characters maximum length.
- Persist flow_intent through both in-memory and Postgres skill stores.
- Return flow_intent in full-record responses while maintaining list/search summary shapes.

Validation rules:
- flow_intent must be a non-empty string when present.
- flow_intent requires web_target to be declared in the same skill.
- flow_intent is validated through existing validation framework with precise rejection reasons.
- Both store backends must round-trip flow_intent values without loss.

```mermaid
flowchart TD
Ingest["Skill document ingestion"] --> CheckFlowIntent{"Has flow_intent?"}
CheckFlowIntent -- No --> SkipValidation["Skip flow_intent validation"]
CheckFlowIntent -- Yes --> ValidateType{"Is string and ≤ 200 chars?"}
ValidateType -- No --> Reject["Reject with validation error"]
ValidateType -- Yes --> CheckWebTarget{"Has web_target?"}
CheckWebTarget -- No --> RejectWebTarget["Reject: flow_intent requires web_target"]
CheckWebTarget -- Yes --> Persist["Persist through skill store"]
SkipValidation --> Persist
Persist --> Store["Store in memory + Postgres"]
```

**Diagram sources**
- [skill.py:15-43](file://products/skills-hub/src/skills_hub/schemas/skill.py#L15-L43)
- [ingestion.py:199-213](file://products/skills-hub/src/skills_hub/services/ingestion.py#L199-L213)

**Section sources**
- [skill.py:15-43](file://products/skills-hub/src/skills_hub/schemas/skill.py#L15-L43)
- [ingestion.py:199-213](file://products/skills-hub/src/skills_hub/services/ingestion.py#L199-L213)

### Tiered Policy Engine (SPEC-030 Implementation)
Responsibilities:
- Evaluate actions with deny > require_approval > allow precedence.
- Parse and validate require_approval rules with approval tiers (tier_1, tier_2).
- Return ApprovalSpec with tier information and decided_by_roles for require_approval decisions.
- Enforce tier constraints: tier_1 allows self-approval by default, tier_2 forbids it.
- Validate policy bundles at load time, rejecting malformed approval configurations.

```mermaid
flowchart TD
Evaluate["evaluate(roles, action)"] --> LoadRules["Load policy bundle"]
LoadRules --> MatchRules["Match enabled rules"]
MatchRules --> CheckDeny{"Any deny match?"}
CheckDeny -- Yes --> ReturnDeny["Return deny decision"]
CheckDeny -- No --> CheckApproval{"Any require_approval match?"}
CheckApproval -- Yes --> SelectBest["Select highest priority approval"]
SelectBest --> ReturnApproval["Return require_approval with ApprovalSpec"]
CheckApproval -- No --> CheckAllow{"Any allow match?"}
CheckAllow -- Yes --> ReturnAllow["Return allow decision"]
CheckAllow -- No --> DefaultDeny["Return deny (no matching rule)"]
```

**Diagram sources**
- [policy_engine.py:335-389](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L335-389)

**Section sources**
- [policy_engine.py:97-148](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L97-148)
- [policy_engine.py:183-220](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L183-220)
- [policy_engine.py:335-389](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L335-389)

### Agent Platform Confirm Route
Responsibilities:
- Validate session ownership via existing session lookup.
- Claim registry entry before streaming headers to prevent duplicates.
- Map errors: unknown/resolved -> 404, expired -> 410, owner mismatch -> error frame mid-stream.
- Reject new turns on parked sessions with 409 until resolved or expired.
- **Updated**: Uses degraded model resolution to handle evicted session pins gracefully and removed session ownership assertion for tier_2 approvers.
- **Enhanced**: Returns structured 409 already_resolved response with winner's outcome for concurrent approver races.
- **Critical Enhancement**: Persists decision outcomes immediately at claim time, ensuring racing approvers receive structured 409 responses with detailed resolution information while the winning approver's stream continues uninterrupted.
- **Critical Enhancement**: When handling expired confirmations (410 Gone), passes the session's pinned model to expire_confirmation to ensure the interrupt reaches the correct agent instance, preventing orphaned turns.

```mermaid
sequenceDiagram
participant Client as "Gateway"
participant Route as "POST /api/v2/chat/confirm"
participant Reg as "ConfirmationRegistry"
participant Store as "ConfirmationRecordStore"
participant Kernel as "RuntimeKernel"
Client->>Route : {session_id, confirm_id, decision}
Route->>Route : get_session(owner check relaxed for tier_2)
Route->>Route : _resolve_model(None, session.model) - degrades stale pins
Route->>Reg : claim(session_id, confirm_id, timeout)
alt Expired
Route->>Route : _resolve_model(None, session.model) - get pinned model
Route->>Kernel : expire_confirmation(session, confirm_id, pinned_model)
Kernel->>Kernel : ensure_agent(session, None, pinned_model) - use same model
Kernel-->>Route : UserInterruptEvent to correct agent
Route-->>Client : 410 Gone (properly settled)
else Unknown/Resolved
Route->>Store : load_record(session, confirm_id)
alt Already resolved
Route-->>Client : 409 already_resolved (structured outcome)
else Unknown
Route-->>Client : 404 Not Found
else OK
Route->>Store : mark_resolved(session, confirm_id, status, decider, decision) - claim-time persistence
Route->>Kernel : resume_confirmation(pending, decision, bearer_token, model_id)
Kernel-->>Route : confirmation_result + SSE stream
Route-->>Client : StreamingResponse
end
```

**Diagram sources**
- [routes.py:65-227](file://products/agent-platform/src/agent_service/api/v2/routes.py#L65-L227)
- [routes.py:277-294](file://products/agent-platform/src/agent_service/api/v2/routes.py#L277-L294)
- [routes.py:395-409](file://products/agent-platform/src/agent_service/api/v2/routes.py#L395-409)
- [hitl_confirmations.py:101-199](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L101-L199)
- [runtime_kernel.py:708-794](file://products/agent-platform/src/agent_service/runtime_kernel.py#L708-L794)
- [runtime_kernel.py:2190-2244](file://products/agent-platform/src/agent_service/runtime_kernel.py#L2190-L2244)

**Section sources**
- [routes.py:65-227](file://products/agent-platform/src/agent_service/api/v2/routes.py#L65-L227)
- [routes.py:395-409](file://products/agent-platform/src/agent_service/api/v2/routes.py#L395-409)

### Platform Gateway Confirm Proxy and Tier Enforcement
Responsibilities:
- Enforce policy action chat:confirm (deny-by-default).
- Obtain delegated token and proxy SSE to agent platform.
- **Enhanced**: Evaluate parked call's tool action against bundle for require_approval decisions.
- **Enhanced**: Enforce tier-based approval requirements against decided_by_roles.
- Emit confirmation_decided audit only when kernel-applied confirmation_result flows through.
- Map upstream 4xx passthrough; transport failures map to 502.
- **Updated**: Passes through structured 409 responses with detailed resolution information including reason, status, decider identity, and timestamps.

```mermaid
sequenceDiagram
participant Portal as "Operator Portal"
participant GW as "Platform Gateway"
participant Policy as "Policy Engine"
participant AP as "Agent Platform"
Portal->>GW : POST /api/v1/chat/confirm
GW->>Policy : enforce_policy("chat : confirm")
Policy-->>GW : allow/deny/require_approval
alt Deny
GW-->>Portal : 403 Forbidden
else Allow or require_approval
GW->>Policy : evaluate("tools : mutate")
Policy-->>GW : require_approval with ApprovalSpec
alt require_approval with tier_2
GW->>GW : check if confirmer == session_owner
alt Self-approval attempt
GW-->>Portal : 403 Forbidden (self_approval)
else Approved tier_2 or tier_1
GW->>AP : POST /api/v2/chat/confirm (delegated token)
AP-->>GW : SSE stream starting with confirmation_result
GW->>GW : emit_audit_event("confirmation_decided")
GW-->>Portal : Stream passthrough (including structured 409 responses)
end
end
```

**Diagram sources**
- [chat.py:134-175](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L134-L175)
- [gateway_service.py:336-446](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L336-L446)
- [policy_engine.py:335-389](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L335-389)
- [policy-default.yaml:113-135](file://shared/shared-contracts/policies/policy-default.yaml#L113-L135)

**Section sources**
- [chat.py:134-175](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L134-L175)
- [gateway_service.py:336-446](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L336-L446)

### Tool Gateway Risk-Tier Admission and Browser Flow Binding
Responsibilities:
- Enforce tools:mutate policy action for write/admin tools.
- Gate k8s.delete_pod registration behind GATEWAY_MUTATING_TOOLS_ENABLED.
- Return structured 403 responses with risk_level metadata for denied mutations.
- Maintain backward compatibility with read-only tool surface.
- **New**: Carry flow_intent through browser flow binding to kernel confirmation frames.
- **New**: Park ad-hoc browser writes as per-action signed gates instead of hard-denying them.

Browser flow binding:
- bind_flow method populates FlowState with skill metadata including flow_intent.
- FlowState.to_dict() includes flow_intent in data["flow"] for kernel consumption.
- Deviation guard behavior remains unchanged whether flow_intent is present or absent.
- **New**: Unbound browser writes on allowlisted origins now park for per-action approval instead of being hard-denied.

```mermaid
flowchart TD
Invoke["Tool Invocation"] --> CheckRisk{"risk_level != 'read'?"}
CheckRisk -- No --> InvokeRead["Enforce tools:invoke"]
CheckRisk -- Yes --> CheckGate{"GATEWAY_MUTATING_TOOLS_ENABLED?"}
CheckGate -- No --> ToolNotFound["Return TOOL_NOT_FOUND"]
CheckGate -- Yes --> EnforceMutate["Enforce tools:mutate"]
EnforceMutate --> Decision{"Allow/Deny"}
Decision -- Deny --> Return403["Return 403 with risk_level"]
Decision -- Allow --> CheckBound{"Browser write + bound flow?"}
CheckBound -- Yes --> ExecuteTool["Execute mutating tool"]
CheckBound -- No --> CheckAllowlist{"Allowlisted origin?"}
CheckAllowlist -- Yes --> ParkAction["Park as per-action signed gate"]
CheckAllowlist -- No --> DenyOrigin["Deny non-allowlisted origin"]
ParkAction --> ExecuteTool
ExecuteTool --> BindFlow["bind_flow(skill)"]
BindFlow --> CreateFlowState["Create FlowState with flow_intent"]
CreateFlowState --> ToDict["FlowState.to_dict() includes flow_intent"]
ToDict --> KernelFrame["Carried in data['flow'] to kernel"]
```

**Diagram sources**
- [gateway_service.py:222-263](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L222-L263)
- [config.py:75-81](file://products/tool-gateway/src/tool_gateway/core/config.py#L75-L81)
- [browser_connector.py:410-421](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L410-L421)

**Section sources**
- [k8s_connector.py:439-518](file://products/tool-gateway/src/tool_gateway/tools/k8s_connector.py#L439-L518)
- [config.py:75-81](file://products/tool-gateway/src/tool_gateway/core/config.py#L75-L81)
- [browser_connector.py:410-421](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L410-L421)

### Enhanced Operator Portal Confirmation Card and Approvals View
Responsibilities:
- Render confirmation_request as inline card with tier badges and tool names, parameters, and permission message.
- Hide Approve/Deny buttons for roles without chat:confirm (client-side convenience; server re-enforces).
- Post decision to gateway confirm endpoint and continue SSE stream into same message area.
- Lock card status on confirmation_result or error; handle 410 as expired.
- Display tier badges: "operator confirmation" for tier_1, "approver required" for tier_2 with decider roles.
- **Enhanced**: Support persistent card rendering from durable records and Approvals view for designated approvers.
- **New**: Display authored intent as prominent decision line when flow_intent is present, showing skill intent above technical details.
- **New**: Approvals view for designated approvers with pending/history listing, badge count, and decision panel.
- **New**: Render change request layout for action approvals with secret masking.
- **Enhanced**: Properly handles 410 Gone responses by settling confirmation cards and preventing stuck UI states.

Flow summary rendering:
- `toFlowSummary` function parses card-level browser-flow headline from stream frames.
- Returns undefined for non-browser cards, allowing fallback to plain tool-action rendering.
- Converts snake_case fields to camelCase for portal consumption (skill_id → skillId, etc.).
- Preserves all flow context fields including flow_intent → flowIntent.
- **Updated**: Now maps flow_intent wire field to flowIntent view model for rendered decision line.
- **New**: Parses approval_kind to determine card rendering mode (flow vs action).
- **New**: Renders change request projection for action approvals with secret masking.

```mermaid
flowchart TD
S(["SSE Loop"]) --> Type{"type == confirmation_request?"}
Type -- Yes --> CheckFlow{"Has flow_summary?"}
CheckFlow -- Yes --> CheckIntent{"Has flow_intent?"}
CheckIntent -- Yes --> RenderFlowCard["Render browser-flow card<br/>with headline (title, description, risk_class)<br/>and authored intent line (flow_intent)"]
CheckIntent -- No --> CheckTier{"require_approval with tier?"}
CheckTier -- Yes --> CheckTierType{"tier_1 vs tier_2?"}
CheckTierType -- tier_1 --> RenderTier1Card["Render approval card with 'operator confirmation' badge<br/>Approve/Deny buttons"]
CheckTierType -- tier_2 --> RenderTier2Card["Render approval card with 'approver required' badge<br/>Show decider roles"]
CheckTierType --> Decision{"User clicks Approve/Deny"}
CheckTier -- No --> CheckKind{"approval_kind == 'action'?"}
CheckKind -- Yes --> RenderChangeRequest["Render change request card<br/>with secret-masked parameters"]
CheckKind -- No --> RenderNormalCard["Render normal approval card<br/>Approve/Deny buttons"]
RenderNormalCard --> Decision
RenderChangeRequest --> Decision
Decision --> Post["POST /api/v1/chat/confirm"]
Post --> Stream["Read SSE continuation"]
Stream --> Append["Append to current message stream"]
Type -- No --> Normal["Handle normal events"]
Append --> Done(["Done"])
Normal --> Done
Error410["410 Gone Response"] --> LockCard["Lock card as expired<br/>Set completed=true<br/>Clear confirmationPending"]
LockCard --> Settled(["Settled Turn"])
```

**Diagram sources**
- [decoder.ts:39-125](file://products/operator-portal/web-ui/app/src/stream/decoder.ts#L39-L125)
- [ChatView.tsx:370-569](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L370-L569)
- [useChatStream.ts:393-407](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L393-L407)

**Section sources**
- [decoder.ts:39-125](file://products/operator-portal/web-ui/app/src/stream/decoder.ts#L39-L125)
- [ChatView.tsx:370-569](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L370-L569)
- [useChatStream.ts:393-407](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L393-L407)

## Dependency Analysis
- Contracts:
  - Stream event schema v6 adds confirmation_request and confirmation_result types, confirm_id, pending_calls with optional risk_level, and optional data field on tool_result.
  - Confirm request schema binds session_id, confirm_id, decision.
  - Policy bundle adds tools:mutate action granted to platform-admin and operator roles; observer excluded.
  - **Enhanced**: Policy engine adds require_approval outcome with ApprovalSpec containing tier, decided_by_roles, and allow_self_approval.
  - **New**: Session schema includes additive `confirmations` field for persistent card rendering with flow_summary support.
  - **New**: Stream event schema v9 → v11 adds optional flow_intent on flow_summary for browser-flow headline preservation and approval_kind/change_request fields for action-level approval support.
  - **New**: Skill schema adds optional flow_intent field requiring web_target declaration.
  - **New**: Durable confirmation record schema adds approval_kind, change_request, and message columns for parity across surfaces.
- Services:
  - Agent platform depends on runtime kernel and registry for park/resume semantics with risk tracking and canonical name resolution.
  - **Enhanced**: Agent platform now depends on durable confirmation records store for persistence with best-effort degradation.
  - Platform gateway depends on policy engine, delegation client, and agent client for proxying and audit.
  - **New**: Platform gateway includes approvals inbox route with `approvals:list` policy enforcement.
  - Tool gateway depends on policy engine for tools:mutate enforcement and configuration management.
  - Portal depends on SSE parser and styles for card rendering with tier badges.
  - **New**: Portal includes ApprovalsView component for designated approvers and flow summary decoding.
  - **New**: Skills hub depends on validation framework for flow_intent frontmatter processing.
  - **New**: Secret parameter masking depends on twin vocabulary synchronization between agent platform and tool gateway.

```mermaid
graph LR
SCHEMA["agent-stream-event.schema.json (v11)"] --> ROUTES["api/v2/routes.py"]
CONFIRM_SCHEMA["chat-confirm.schema.json"] --> ROUTES
SESSION_SCHEMA["agent-session.schema.json"] --> ROUTES
SKILL_SCHEMA["skill.schema.json"] --> SKILLSHUB["skills-hub services"]
POLICY["policy-default.yaml"] --> GWSVC["services/gateway_service.py"]
POLICY --> TGSVC["tool-gateway services"]
POLICY --> PE["services/policy_engine.py"]
GWSVC --> CHATROUTE["api/routes/chat.py"]
GWSVC --> APPROVALSROUTE["api/routes/approvals.py"]
ROUTES --> KERNEL["runtime_kernel.py"]
KERNEL --> REGISTRY["hitl_confirmations.py"]
KERNEL --> RECORDS["confirmation_records.py"]
KERNEL --> SECRET["secret_params.py"]
RECORDS --> POSTGRES["PostgreSQL"]
CHATROUTE --> GWSVC
CHATROUTE --> SCHEMA
TGSVC --> CONFIG["core/config.py"]
PE --> DECISION["PolicyDecision with ApprovalSpec"]
DECODER["stream/decoder.ts"] --> PORTAL["Portal UI"]
PORTAL -.-> SESSION_SCHEMA
SKILLSHUB --> BROWSERCONN["browser_connector.py"]
BROWSERCONN --> FLOWCTX["flow_approvals.py"]
FLOWCTX --> KERNEL
SECRET -.-> VALIDATE["validate_secret_vocabulary.py"]
USESTREAM["useChatStream.ts"] -.-> PORTAL
```

**Diagram sources**
- [agent-stream-event.schema.json:1-160](file://shared/shared-contracts/schemas/agent-stream-event.schema.json#L1-L160)
- [chat-confirm.schema.json:1-27](file://shared/shared-contracts/schemas/chat-confirm.schema.json#L1-L27)
- [agent-session.schema.json:127-138](file://shared/shared-contracts/schemas/agent-session.schema.json#L127-L138)
- [skill.py:15-43](file://products/skills-hub/src/skills_hub/schemas/skill.py#L15-L43)
- [policy-default.yaml:42-54](file://shared/shared-contracts/policies/policy-default.yaml#L42-L54)
- [policy-default.yaml:113-135](file://shared/shared-contracts/policies/policy-default.yaml#L113-L135)
- [routes.py:230-320](file://products/agent-platform/src/agent_service/api/v2/routes.py#L230-L320)
- [gateway_service.py:336-446](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L336-L446)
- [chat.py:134-175](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L134-L175)
- [approvals.py:19-51](file://products/platform-gateway/src/platform_gateway/api/routes/approvals.py#L19-L51)
- [runtime_kernel.py:657-794](file://products/agent-platform/src/agent_service/runtime_kernel.py#L657-L794)
- [hitl_confirmations.py:85-208](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L85-L208)
- [confirmation_records.py:214-565](file://products/agent-platform/src/agent_service/services/confirmation_records.py#L214-L565)
- [secret_params.py:1-149](file://products/agent-platform/src/agent_service/services/secret_params.py#L1-L149)
- [config.py:75-81](file://products/tool-gateway/src/tool_gateway/core/config.py#L75-L81)
- [policy_engine.py:97-148](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L97-148)
- [decoder.ts:39-125](file://products/operator-portal/web-ui/app/src/stream/decoder.ts#L39-L125)
- [useChatStream.ts:393-407](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L393-L407)

**Section sources**
- [agent-stream-event.schema.json:1-160](file://shared/shared-contracts/schemas/agent-stream-event.schema.json#L1-L160)
- [chat-confirm.schema.json:1-27](file://shared/shared-contracts/schemas/chat-confirm.schema.json#L1-L27)
- [agent-session.schema.json:127-138](file://shared/shared-contracts/schemas/agent-session.schema.json#L127-L138)
- [skill.py:15-43](file://products/skills-hub/src/skills_hub/schemas/skill.py#L15-L43)
- [policy-default.yaml:42-54](file://shared/shared-contracts/policies/policy-default.yaml#L42-L54)
- [policy-default.yaml:113-135](file://shared/shared-contracts/policies/policy-default.yaml#L113-L135)

## Performance Considerations
- In-memory registry avoids persistent overhead but means parked confirmations do not survive process restarts; this is intentional and safe.
- Claim-based single-flight prevents duplicate resumption and reduces contention.
- SSE passthrough minimizes transformation cost; only first confirmation_result triggers audit emission.
- Tool evidence data is bounded by middleware caps to keep streams responsive.
- Risk-level mapping is computed once at toolkit construction and cached per token.
- Mutating tool gating prevents unnecessary policy evaluation for read operations.
- **Model resolution caching**: Degraded model resolution happens once per confirm request, avoiding repeated catalog lookups.
- **Policy evaluation caching**: Policy bundle is loaded once and cached per configuration path, reducing evaluation overhead.
- **Tier validation**: Approval tier validation occurs at bundle load time, not per-request, minimizing runtime overhead.
- **Dual-store pattern**: In-memory registry remains hot path for performance-critical claim/resume operations, while Postgres store provides durability with best-effort persistence that doesn't block core flows.
- **Bounded storage**: Confirmation records use session-scoped caps (50 per session) and time-window based inbox history (30 days) to prevent unbounded growth.
- **Opportunistic cleanup**: Stale record cleanup and old resolved record sweeping piggyback on write operations to minimize background overhead.
- **Metadata-only inbox**: Cross-session discovery exposes only metadata fields, preserving owner privacy and reducing data transfer costs.
- **Claim-time persistence**: Immediate outcome persistence at claim time eliminates race conditions while maintaining high performance through best-effort degradation.
- **v0.23.1 Enhancement**: Canonical name mapping is captured once at park time from toolkit, avoiding repeated lookups during confirmation processing.
- **v0.33.1 Enhancement**: Flow summary coercion is lightweight, filtering only five string fields and degrading non-dict values efficiently.
- **SPEC-053 Enhancement**: Flow intent validation occurs during skill ingestion, not per-request, minimizing runtime overhead for confirmation processing.
- **SPEC-053 Enhancement**: Flow intent is stored as simple string field in JSONB, avoiding complex parsing during confirmation rendering.
- **SPEC-054 Enhancement**: Approval kind determination uses efficient predicate checks rather than expensive ambient context probes.
- **SPEC-054 Enhancement**: Change request projection is built separately from signed parameters, avoiding signature recalculation overhead.
- **SPEC-054 Enhancement**: Secret masking uses existing vocabulary reuse, avoiding new redaction logic overhead.
- **SPEC-055 Enhancement**: Fail-closed masking is optimized with allow-list checking and substring matching, minimizing computational overhead while providing strong security guarantees.
- **SPEC-055 Enhancement**: Pre-redaction occurs once per confirmation park, avoiding redundant masking operations during streaming and persistence.
- **SPEC-055 Enhancement**: Vocabulary validation runs at build time, not runtime, preventing performance impact during confirmation processing.
- **Enhanced Expired Handling**: Model pinning consistency in expired confirmation handling prevents costly agent rebuilds and ensures interrupts reach the correct agent instance efficiently.
- **web.press_key element context is conditional**: the label is projected only when a ref parameter is present, so a keypress with no element targeting still renders the bare sentence rather than naming a location the model never supplied.

## Troubleshooting Guide
Common issues and resolutions:
- 409 Conflict on new chat turns: Indicates a parked confirmation exists; answer or wait for expiry before sending a new message.
- 410 Gone on confirm: Confirmation expired; close parked calls and retry with a new turn.
- 404 Not Found: Unknown or already-resolved confirm_id; verify session and confirm_id match.
- 403 Forbidden: Missing chat:confirm role; ensure identity has required role per policy.
- Mid-stream error frame: Owner mismatch between registry and session; re-authenticate and retry.
- Mutating tool absent from discovery: Verify GATEWAY_MUTATING_TOOLS_ENABLED is set to true and RBAC permissions are configured.
- 403 on mutating tool invocation: Ensure tools:mutate policy action is granted to the user's role.
- No confirmation card appears: Check AGENT_HITL_CONFIRM_TIMEOUT setting; when 0, mutating tools are excluded from toolkit entirely.
- **Stuck confirmation with evicted model pin**: If a session had a pinned model that was later evicted by discovery refresh or key revocation, the confirm route now automatically degrades to the catalog default instead of raising UnknownModelError mid-stream.
- **Self-approval blocked**: When tier_2 approval is required, operators cannot approve their own parked calls; use an approver or platform-admin identity.
- **Invalid policy bundle**: Check for malformed require_approval rules; tier_2 cannot have allow_self_approval=true, and require_approval must be on bridged actions only.
- **Missing pending confirmation**: Use GET /api/v2/chat/pending-confirmation to inspect parked batch metadata including owner_user_id and derived policy action for troubleshooting tier enforcement issues.
- **Persistent confirmation not visible**: Check if Postgres backend is available; confirmation records fall back to in-memory when Postgres is unavailable.
- **Concurrent approver conflicts**: Multiple approvers attempting the same confirmation will receive structured "already_resolved" responses instead of errors.
- **Expired cards appearing**: Stale pending records are marked as expired on startup since parked kernel replies cannot survive process restarts.
- **Approvals inbox not accessible**: Verify user has `approvals:list` permission; only `approver` and `platform-admin` roles can access the inbox.
- **Owner transcript missing cards**: Check if session detail includes `confirmations` field; cards should appear even after re-login or pod restarts.
- **Race condition confusion**: Structured 409 responses include winner's outcome; losing approvers can see who decided and when.
- **Startup sweep issues**: Verify AGENT_HITL_CONFIRM_TIMEOUT is properly configured; startup sweep uses this value to identify stale pending records for closure.
- **Postgres initialization failures**: Check AGENT_STATE_STORE_BACKEND and AGENT_STATE_DB_URL configuration; service falls back to in-memory store when Postgres is unavailable.
- **v0.23.1 Fix**: TOOL_NOT_FOUND errors for approved mutating tool invocations are now resolved by using canonical dotted names (e.g., `k8s.delete_pod`) instead of sanitized model-visible names (e.g., `k8s_delete_pod`) in the signed execution envelope.
- **v0.33.1 Issue**: Live operator confirmation card missing browser-flow description while approver inbox shows it; check that flow_summary is properly propagated through stream normalization and that AgentStreamEvent schema includes flow_summary field.
- **Flow summary not rendering**: Verify that flow_summary coercion is working correctly and that only the five contract fields (skill_id, origin, title, description, risk_class) are being passed through.
- **SPEC-053 Issues**: 
  - **Flow intent not displaying**: Check that skill declares flow_intent frontmatter and that web_target is also declared.
  - **Flow intent validation errors**: Verify flow_intent is a non-empty string ≤ 200 characters and skill has web_target declared.
  - **Browser flow card missing intent**: Ensure flow_intent is carried through browser flow binding and kernel confirmation frames.
  - **Portal not showing intent line**: Check that decoder maps flow_intent to flowIntent and ChatView renders the authored intent line.
- **SPEC-054 Issues**:
  - **Action approval not parking**: Verify browser write is on allowlisted origin; non-allowlisted origins are still hard-denied.
  - **Change request not displaying**: Check that change_request projection is being assembled from parameters with proper secret masking.
  - **Card message missing on replay**: Verify message field is persisted on durable records and that legacy records degrade gracefully.
  - **Headline leak on action cards**: Ensure approval_kind is explicitly set to 'action' for non-browser flows, preventing flow headline inheritance.
  - **Ad-hoc browser writes still denied**: Check that origin is on allowlist and that bridging is enabled (AGENT_HITL_CONFIRM_TIMEOUT > 0).
- **SPEC-055 Issues**:
  - **Secrets appearing in plaintext**: Verify fail-closed masking is working correctly; check that parameters are not in KNOWN_SAFE_FIELDS allow-list.
  - **Change request showing unmasked values**: Ensure curated formatters are applying appropriate masking for sensitive fields like web.type.text.
  - **Vocabulary validation failures**: Check that agent platform and tool gateway masking vocabularies are synchronized; run make verify to validate.
  - **Pre-redaction not occurring**: Verify runtime kernel is calling redact_pending_calls before streaming and persistence.
  - **Durable records containing secrets**: Check that post-redaction storage is capturing redacted parameters, not original values.
- **Enhanced Expired Confirmation Issues**:
  - **Orphaned turns**: When approval cards expire, ensure the system properly interrupts the specific agent instance that created the parked reply using the correct pinned model to prevent orphaned turns where parked calls never receive their interrupted result.
  - **Model pinning inconsistency**: Verify that expired confirmation handling passes the session's pinned model to expire_confirmation to ensure interrupts reach the correct agent instance.
  - **Frontend stuck states**: Check that 410 Gone responses are properly handled in the frontend to settle confirmation cards and prevent stuck UI states.
  - **Agent rebuild issues**: Ensure that expired confirmation interrupts use the same model resolution ladder (request > pinned > default) as resume paths to prevent agent rebuilds that lose parked replies.
- **Enhanced web.press_key Issues**:
  - **Element context missing**: Verify that ref parameter is provided when element context is expected; element context is only included when ref is present.
  - **Incorrect element label**: Check that display_hint is properly computed from browser element map; falls back to raw ref when element map entry is not available.
  - **Unexpected element context**: Ensure ref parameter is not accidentally included when element targeting is not desired; web.press_key without ref should show bare sentence.
  - **Test coverage gaps**: Verify tests cover both scenarios: with ref (element context included) and without ref (bare sentence).

Operational checks:
- Verify AGENT_HITL_CONFIRM_TIMEOUT > 0 to enable bridging; set to 0 to restore legacy silent-park behavior.
- Confirm policy bundle includes allow-chat-confirm and allow-operators-tools-mutate rules for intended roles.
- Inspect audit trail for confirmation_decided events to validate applied decisions.
- Check tool discovery endpoints to verify mutating tools are registered when enabled.
- Verify GATEWAY_MUTATING_TOOLS_ENABLED configuration in tool-gateway deployment.
- **Monitor model catalog health**: Ensure discovery refreshes don't leave sessions with invalid pinned models; the system should automatically degrade to defaults.
- **Validate policy bundle**: Use make validate-policy to ensure require_approval rules are properly configured.
- **Check tier enforcement**: Verify that tier_2 approvals require separate approver identities in production environments.
- **Use pending confirmation endpoint**: Leverage GET /api/v2/chat/pending-confirmation to debug tier enforcement issues by examining parked batch metadata and derived policy actions.
- **Verify Postgres connectivity**: Check AGENT_STATE_STORE_BACKEND and AGENT_STATE_DB_URL configuration for confirmation record persistence.
- **Monitor confirmation record store**: Use confirmation record store is_ready() method to verify Postgres availability.
- **Check for stale pending records**: After pod restarts, verify that any orphaned pending records were properly marked as expired.
- **Test approvals inbox**: Verify GET /api/v1/approvals/inbox returns metadata-only items for authorized approvers.
- **Validate owner transcript cards**: Check GET /api/v2/sessions/{id} includes confirmations field with persistent card data.
- **Verify startup sweep configuration**: Ensure AGENT_HITL_CONFIRM_TIMEOUT is properly set for accurate stale record identification during startup.
- **Monitor structured 409 responses**: Check that concurrent approver attempts receive detailed resolution information including decider identity and timestamps.
- **v0.23.1 Verification**: Verify that approved mutating tool invocations execute successfully by checking that the signed execution envelope contains canonical dotted tool names (e.g., `k8s.delete_pod`) rather than sanitized names (e.g., `k8s_delete_pod`).
- **v0.33.1 Verification**: Verify that flow_summary is properly included in confirmation_request frames and that the portal decoder correctly parses browser-flow headlines for consistent workflow framing.
- **SPEC-053 Verification**: Verify that skills with flow_intent declarations validate successfully and that browser flow cards display the authored intent line prominently above technical details.
- **SPEC-054 Verification**: Verify that ad-hoc browser writes on allowlisted origins park for per-action approval instead of being hard-denied, and that change request cards display secret-masked parameters appropriately.
- **SPEC-055 Verification**: Verify that all secret-bearing parameters are masked in confirmation cards, durable records, and stream frames; check that fail-closed masking prevents plaintext secrets from appearing anywhere in the confirmation pipeline.
- **Enhanced Expired Confirmation Verification**: Verify that expired confirmation handling properly passes model pins to ensure interrupts reach the correct agent instance and prevent orphaned turns.
- **Frontend 410 Handling Verification**: Verify that 410 Gone responses properly settle confirmation cards and clear stuck UI states.
- **Vocabulary Synchronization**: Run `make verify` to ensure agent platform and tool gateway masking vocabularies remain synchronized; address any validation failures immediately.
- **Enhanced web.press_key Verification**: Verify that web.press_key approval cards include element context when ref parameter is provided, improving operator understanding of where keypress actions will occur.

**Section sources**
- [routes.py:65-94](file://products/agent-platform/src/agent_service/api/v2/routes.py#L65-L94)
- [routes.py:156-227](file://products/agent-platform/src/agent_service/api/v2/routes.py#L156-L227)
- [routes.py:277-294](file://products/agent-platform/src/agent_service/api/v2/routes.py#L277-L294)
- [routes.py:497-614](file://products/agent-platform/src/agent_service/api/v2/routes.py#L497-L614)
- [routes.py:578-601](file://products/agent-platform/src/agent_service/api/v2/routes.py#L578-L601)
- [routes.py:395-409](file://products/agent-platform/src/agent_service/api/v2/routes.py#L395-409)
- [gateway_service.py:336-396](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L336-L396)
- [approvals.py:19-51](file://products/platform-gateway/src/platform_gateway/api/routes/approvals.py#L19-L51)
- [policy-default.yaml:42-54](file://shared/shared-contracts/policies/policy-default.yaml#L42-L54)
- [policy-default.yaml:113-135](file://shared/shared-contracts/policies/policy-default.yaml#L113-L135)
- [config.py:75-81](file://products/tool-gateway/src/tool_gateway/core/config.py#L75-L81)
- [multimodel-runtime-and-live-discovery.md:126-136](file://docs/agentic-aiops-platform/release-notes/2026-08-24-multimodel-runtime-and-live-discovery.md#L126-L136)
- [policy_engine.py:211-215](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L211-L215)
- [confirmation_records.py:399-405](file://products/agent-platform/src/agent_service/services/confirmation_records.py#L399-L405)
- [confirmation_records.py:415-431](file://products/agent-platform/src/agent_service/services/confirmation_records.py#L415-L431)
- [routes.py:370-410](file://products/agent-platform/src/agent_service/api/v2/routes.py#L370-L410)
- [mutating-tool-name-regression.md:18-58](file://docs/agentic-aiops-platform/release-notes/2026-08-28-mutating-tool-name-regression.md#L18-L58)
- [post-live-check-confirmation-card-flow-headline.md:12-56](file://docs/agentic-aiops-platform/release-notes/2026-09-05-post-live-check-confirmation-card-flow-headline.md#L12-L56)
- [post-live-test-credential-masking-and-hitl-hardening.md:54-169](file://docs/agentic-aiops-platform/release-notes/2026-09-11-post-live-test-credential-masking-and-hitl-hardening.md#L54-L169)
- [SPEC-053 spec.md:83-108](file://docs/specs/SPEC-053-skill-declared-step-intent/spec.md#L83-L108)
- [SPEC-053 plan.md:34-58](file://docs/specs/SPEC-053-skill-declared-step-intent/plan.md#L34-L58)
- [SPEC-054 spec.md:117-143](file://docs/specs/SPEC-054-action-approval-and-change-request-card/spec.md#L117-L143)
- [secret_params.py:1-149](file://products/agent-platform/src/agent_service/services/secret_params.py#L1-L149)
- [hitl_confirmations.py:369-399](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L369-L399)
- [runtime_kernel.py:2190-2244](file://products/agent-platform/src/agent_service/runtime_kernel.py#L2190-L2244)
- [useChatStream.ts:393-407](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L393-L407)
- [hitl_confirmations.py:273-285](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L273-L285)
- [test_hitl_confirmations.py:359-380](file://products/agent-platform/tests/test_hitl_confirmations.py#L359-L380)

## Conclusion
SPEC-020 delivers a robust, auditable HITL bridge that transforms kernel ASK parking into a portal-driven approval workflow, enhanced with SPEC-021's bounded mutating actions, SPEC-030's require-approval tier system, SPEC-031's persistent confirmation registry, SPEC-053's skill-declared step intent, **SPEC-054's action-level approval with change request cards**, and **SPEC-055's secret parameter masking hardening**. It enforces policy at the gateway, preserves session integrity, and records decisions durably with tier context and authored workflow intent. The design keeps the kernel unchanged, relies on existing agentscope machinery, and scales to future write/mutating tools by gating them behind the same confirmation surface with risk-tier enforcement.

The integration provides a seven-layer security model: deny-by-default policy bundle actions, tool risk tiers with tools:mutate admission gate, agent auto-allow list exclusion for mutating tools, mandatory HITL confirmation with tier enforcement, approval tier validation ensuring appropriate approver identities, skill-declared intent providing clear operator understanding of what each approval actually achieves, and **fail-closed secret masking ensuring no plaintext secrets appear in any confirmation surface**. This ensures that no mutating action can execute without explicit human approval at the correct governance level, maintaining the platform's operational safety guarantees while enabling powerful automated remediation capabilities with clear, authored intent communication.

**Critical Enhancement**: The recent SPEC-030 implementation introduces tiered approval governance where tier_1 permits operator self-confirmation for routine destructive actions (like service restarts), while tier_2 requires designated approvers distinct from the requester for critical destructive actions. This addresses the governance gap where any chat:confirm holder could previously confirm any parked mutating call, including their own. The tier system enforces separation of duties through policy configuration rather than code special cases, making approval governance flexible, auditable, and enforceable.

**Critical Enhancement**: The recent fix addresses a major wedge scenario where evicted model pins could cause UnknownModelError exceptions mid-stream, permanently stalling parked sessions. By implementing the same degraded resolution ladder used by other turns (request > pinned > default), the /chat/confirm route now gracefully handles stale session pins by falling back to catalog defaults when pinned models become unavailable due to discovery refreshes or key revocations. This ensures continuous operation even during model catalog changes.

**Critical Enhancement**: The SPEC-031 persistent confirmation registry ensures that parked calls and their resolutions survive agent-platform pod restarts and remain consistent across replicas. The dual-store architecture maintains high-performance in-memory registry for hot-path operations while providing durable Postgres-backed storage for restart recovery and cross-replica consistency. Best-effort persistence degrades gracefully when Postgres is unavailable, never blocking core confirmation flows.

**Critical Enhancement**: Race condition handling has been significantly improved with structured 409 responses instead of opaque 404 errors. When multiple approvers attempt to confirm the same parked call simultaneously, the system now provides detailed resolution information including the winner's decision, decider identity, and timestamp. This eliminates ambiguity and enables better debugging of concurrent approval scenarios.

**Critical Enhancement**: Startup sweep logic now uses configurable TTL scoping via AGENT_HITL_CONFIRM_TIMEOUT for precise identification of stale pending records. This ensures that only records that have genuinely exceeded their confirmation timeout are marked as expired, preventing premature closure of active confirmations while cleaning up truly orphaned records.

**Critical Enhancement**: Immediate outcome persistence at claim time provides better durability guarantees. The winning approver's decision is persisted to the durable store before the resumed stream begins, ensuring that racing approvers receive structured 409 responses with complete resolution details while the winner's stream continues uninterrupted.

**Critical Enhancement**: **Enhanced expired confirmation handling with model pinning consistency** ensures that when approval cards expire, the system properly interrupts the specific agent instance that created the parked reply using the correct pinned model. This prevents orphaned turns where parked calls never receive their interrupted result. The fix implements consistent model resolution (request > pinned > default) for expired confirmation interrupts, ensuring they reach the correct agent instance rather than rebuilding on provider defaults.

**Critical Enhancement**: **Improved kernel interrupt routing for parked replies** ensures that expired confirmation interrupts use the same model pinning logic as resume paths, preventing agent rebuilds that would lose parked replies. The runtime kernel's expire_confirmation method now accepts model_id parameter to maintain consistency with the ensure_agent resolution ladder.

**Critical Enhancement**: **Frontend stream management fixes for 410 Gone responses** properly settle confirmation cards when expired, clearing stuck UI states and preventing infinite loading loops. The frontend now recognizes 410 Gone responses and settles the turn appropriately, ensuring operators see clear feedback about expired confirmations.

**v0.23.1 Critical Enhancement**: The canonical tool name resolution fix resolves TOOL_NOT_FOUND errors for approved mutating tool invocations by implementing a gateway_names mapping between sanitized model-visible names (e.g., `k8s_delete_pod`) and canonical dotted names (e.g., `k8s.delete_pod`) required by the gateway registry. This ensures that the signed execution envelope carries the correct tool name that the gateway registry can resolve, fixing the regression where approved mutating calls would fail at the final invocation step despite passing all previous approval and verification gates.

**v0.33.1 Critical Enhancement**: Flow summary propagation now preserves browser-flow headline metadata (skill_id, origin, title, description, risk_class) throughout the entire pipeline from stream frames to final card rendering. This ensures consistent workflow framing across both live operator cards and durable confirmation records, addressing a live test issue where the operator's confirmation card rendered without its browser-flow description while the approver inbox card showed it correctly. The fix includes AgentStreamEvent schema updates (v9 → v11), defensive flow_summary coercion, and portal decoder enhancements to parse and display the headline consistently.

**SPEC-053 Critical Enhancement**: Skill-declared step intent adds an optional `flow_intent` frontmatter field to skills that displays as a prominent plain-text decision line above technical details in browser flow approval cards. This addresses the UX issue where operators saw raw DOM labels and technical arguments instead of authored statements describing what the gated mutation actually achieves. The implementation carries flow_intent through the entire pipeline from skill declaration → skills-hub validation → tool-gateway flow binding → kernel confirmation frames → portal card rendering, ensuring consistent display of the skill author's intent statement.

**SPEC-054 Critical Enhancement**: Action-level approval makes ad-hoc browser writes first-class approval subjects alongside pre-declared flows. The explicit `approval_kind` discriminator distinguishes between flow approvals (bound browser flows with one-gate collapse) and action approvals (per-action signed gates for individual mutations), eliminating the structural ambiguity that caused headline leaks. Ad-hoc browser writes on allowlisted origins now park for per-action approval instead of being hard-denied, enabling interactive web-app troubleshooting workflows.

**SPEC-054 Critical Enhancement**: Change request cards transform action approvals from opaque tool invocations into readable change requests. Decision-relevant parameters are promoted from collapsed technical details to the approval intention with secret masking, allowing operators to understand exactly what they're approving. The projection is display-only and never affects the signed parameters, maintaining security while improving decision quality.

**SPEC-054 Critical Enhancement**: Durable card-message parity ensures that confirmation card messages persist on durable records, so the approver inbox and owner transcripts render the same message as live operator cards. This fixes the issue where card messages would disappear on replayed surfaces, maintaining consistent user experience across all approval surfaces.

**SPEC-055 Critical Enhancement**: **Fail-closed secret parameter masking** represents a fundamental security improvement to the HITL confirmation system. All secret-bearing parameters are now masked unless explicitly allow-listed as safe, preventing plaintext secrets from appearing in any confirmation surface including live streams, durable records, and operator portals. The fail-closed approach ensures that unknown or off-vocabulary secrets are always masked, eliminating the possibility of secret leakage through newly discovered parameter names or custom tool implementations.

**SPEC-055 Critical Enhancement**: **Pre-redaction integration points** in the runtime kernel ensure that secret masking occurs before any data leaves the kernel boundary. The pending_calls payload is built once, the card message is computed from raw parameters (before redaction), and then fail-closed masking is applied to the payload before streaming to clients and persisting to durable storage. This architectural decision ensures that no plaintext secrets can escape the kernel, regardless of downstream processing or storage failures.

**SPEC-055 Critical Enhancement**: **Twin vocabulary synchronization** between agent platform and tool gateway ensures consistent masking behavior across all confirmation surfaces. The build system validates that both components maintain identical masking vocabularies, preventing drift that could lead to inconsistent secret handling. This validation catches configuration errors early in the development cycle rather than allowing them to reach production.

**New Capability**: The addition of the pending-confirmation endpoint, RISK_LEVEL_ACTIONS mapping, and approvals inbox enables sophisticated approval workflows where the platform gateway can make informed tier enforcement decisions based on authoritative parked batch metadata, including the original session owner and derived policy actions from tool risk levels.

**New Capability**: The approvals inbox provides cross-session discovery for designated approvers with metadata-only exposure, enabling operators to manage parked confirmations across multiple sessions without exposing owner transcript content.

**New Capability**: Persistent confirmation cards in owner transcripts survive re-login, page reloads, pod restarts, and replica boundaries, providing complete auditability of approval workflows with decider attribution and timestamps.

**New Capability**: Flow summary propagation ensures that browser-bound web-check flows carry consistent workflow context (skill intent, origin, risk class) from the initial ASK through to final card rendering, enabling operators to understand the broader workflow context beyond individual tool actions.

**New Capability**: Skill-declared step intent provides authors with a way to communicate the purpose of gated mutations to operators through authored intent statements, improving approval decision quality and reducing cognitive load when reviewing complex browser automation workflows.

**New Capability**: Action-level approval extends the per-action signed-execution mechanism to the browser tool family for unbound writes on allowlisted origins, enabling interactive web-app troubleshooting while maintaining the same security guarantees as non-browser mutations.

**New Capability**: Change request projection promotes decision-relevant parameters from collapsed technical details to readable change requests with secret masking, improving operator understanding of what they're approving without compromising security.

**New Capability**: Explicit approval kind discrimination prevents non-browser action cards from inheriting stale flow headlines, structurally eliminating the headline leak class of defects rather than merely gating them.

**New Capability**: Fail-closed secret masking provides comprehensive protection against secret leakage across all confirmation surfaces, ensuring that plaintext secrets never appear in live streams, durable records, operator portals, or audit trails.

**New Capability**: Enhanced expired confirmation handling with model pinning consistency prevents orphaned turns by ensuring expired confirmation interrupts reach the correct agent instance with proper model resolution, maintaining system reliability and preventing stuck sessions.

**New Capability**: Improved frontend stream management for 410 Gone responses provides better user experience by properly settling expired confirmation cards and preventing stuck UI states, giving operators clear feedback about confirmation status.

**New Capability**: **Enhanced web.press_key element context** improves operator understanding of where keypress actions will occur by including element location information when ref parameter is provided. This aligns web.press_key with the other four members of `browser_ref_tools` (click, type, select, upload_file), which already projected the element label — all five ref-taking write tools now name the element. `web.evaluate` takes no ref and `web.fill_credential` is read-tier, so neither is comparable.

[No sources needed since this section summarizes without analyzing specific files]