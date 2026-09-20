# Human-in-the-Loop Approvals

<cite>
**Referenced Files in This Document**
- [flow_approvals.py](file://products/agent-platform/src/agent_service/services/flow_approvals.py)
- [hitl_confirmations.py](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py)
- [confirmation_records.py](file://products/agent-platform/src/agent_service/services/confirmation_records.py)
- [policy_engine.py](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py)
- [secret_params.py](file://products/agent-platform/src/agent_service/services/secret_params.py)
- [http_connector.py](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py)
- [kernel_middleware.py](file://products/agent-platform/src/agent_service/services/kernel_middleware.py)
- [policy-default.yaml](file://shared/shared-contracts/policies/policy-default.yaml)
- [chat-confirm.schema.json](file://shared/shared-contracts/schemas/chat-confirm.schema.json)
- [policy-decision.schema.json](file://shared/shared-contracts/schemas/policy-decision.schema.json)
- [approval-and-hitl.md](file://docs/guides/approval-and-hitl.md)
- [SPEC-058-http-service-check-tools/spec.md](file://docs/specs/SPEC-058-http-service-check-tools/spec.md)
- [2026-09-20-post-web-checks-egress-hardening.md](file://docs/agentic-aiops-platform/release-notes/2026-09-20-post-web-checks-egress-hardening.md)
</cite>

## Update Summary
**Changes Made**
- Updated HTTP GET tool security posture to require operator confirmation by default for outbound network egress operations
- Added comprehensive documentation about the security rationale behind requiring explicit approval for outbound network egress
- Enhanced approval workflow documentation to reflect the new hardened default behavior where http.get parks action cards
- Updated configuration guidance to include AGENT_GATEWAY_TOOL_AUTO_ALLOW_EXTRA for opt-in scenarios
- Expanded security considerations section with SSRF protection and defense-in-depth explanations

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
10. Appendices

## Introduction
This document explains how the Agent Platform implements human-in-the-loop (HITL) approval workflows for risky operations. It covers:
- Approval gates that park mutating tool calls until an operator decides
- Confirmation card generation and display hints for browser tools
- Decision synchronization between agents, operators, and the policy engine
- Flow approvals for multi-step browser flows with identity-scoped auto-signing
- **Enhanced HTTP operations with hardened security posture requiring explicit approval for outbound network egress**
- Risk tier classification, tool categorization (read vs write), and escalation paths
- Configuration examples, custom flow considerations, and auditing
- Race condition handling, timeout management, and user experience guidance

**Updated** The platform now implements a hardened security posture where `http.get` requires operator confirmation by default due to the elevated risk class of outbound network egress operations compared to in-cluster reads.

## Project Structure
The HITL system spans several services and shared contracts:
- Agent platform runtime kernel bridges kernel ASK decisions to a confirmation registry and durable records
- Platform gateway enforces policy outcomes including require_approval tiers on the confirm path
- Shared schemas define request/response contracts for confirmations and policy decisions
- Default policy bundle defines roles, actions, and approval tiers
- **HTTP tools with enhanced security validation and approval requirements for outbound egress**

```mermaid
graph TB
subgraph "Agent Platform"
A["Kernel<br/>park/resume"]
B["ConfirmationRegistry<br/>(in-memory)"]
C["ConfirmationRecordStore<br/>(memory/postgres)"]
D["FlowContextStore / FlowApprovalStore"]
E["Secret Parameter Masking"]
F["GatewayPermissionMiddleware<br/>Hardened Auto-Allow"]
end
subgraph "Platform Gateway"
G["Policy Engine<br/>evaluate()"]
H["Confirm Bridge<br/>POST /api/v1/chat/confirm"]
I["HTTP Connector<br/>Security Validation"]
end
subgraph "Shared Contracts"
J["chat-confirm.schema.json"]
K["policy-decision.schema.json"]
L["policy-default.yaml"]
end
A --> B
B --> C
A --> D
F --> A
G --> L
H --> J
G --> K
I --> E
```

**Diagram sources**
- [kernel_middleware.py:96-112](file://products/agent-platform/src/agent_service/services/kernel_middleware.py#L96-L112)
- [hitl_confirmations.py:452-595](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L452-L595)
- [confirmation_records.py:141-245](file://products/agent-platform/src/agent_service/services/confirmation_records.py#L141-L245)
- [flow_approvals.py:124-274](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L124-L274)
- [policy_engine.py:390-444](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L390-L444)
- [secret_params.py:136-153](file://products/agent-platform/src/agent_service/services/secret_params.py#L136-L153)
- [http_connector.py:503-535](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L503-L535)

**Section sources**
- [approval-and-hitl.md:7-90](file://docs/guides/approval-and-hitl.md#L7-L90)

## Core Components
- ConfirmationRegistry: per-process registry of parked confirmations with single-flight claim, TTL expiry, and resolution
- ConfirmationRecordStore: durable persistence of parked and resolved confirmations (memory or Postgres)
- FlowApprovals: session-scoped flow context and approval stores enabling auto-signing within a bounded flow identity and TTL
- PolicyEngine: evaluates role/action against the policy bundle; supports allow/deny/require_approval with tiers
- **GatewayPermissionMiddleware: hardened auto-allow list excluding http.get from built-in defaults due to egress risk**
- Secret Parameter Masking: fail-closed posture with KNOWN_SAFE_FIELDS allow-list and shape-preserving rendering
- HTTP Connector: structured body validation, credential set support, and comprehensive security enforcement
- Schemas: chat-confirm schema for operator decisions; policy-decision schema for evaluation results

Key behaviors:
- Mutating tool calls are parked and surfaced as confirmation cards
- **Outbound network egress operations (http.get) now require explicit operator approval by default**
- The confirm bridge enforces policy tiers before resuming
- Flow approvals scope auto-signed writes to a specific skill/origin binding while alive
- Records survive restarts and support inbox/history views
- HTTP operations include comprehensive security validation and approval requirements

**Section sources**
- [hitl_confirmations.py:47-181](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L47-L181)
- [confirmation_records.py:52-92](file://products/agent-platform/src/agent_service/services/confirmation_records.py#L52-L92)
- [flow_approvals.py:78-122](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L78-L122)
- [policy_engine.py:142-210](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L142-L210)
- [kernel_middleware.py:96-112](file://products/agent-platform/src/agent_service/services/kernel_middleware.py#L96-L112)
- [secret_params.py:136-153](file://products/agent-platform/src/agent_service/services/secret_params.py#L136-L153)
- [http_connector.py:503-535](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L503-L535)

## Architecture Overview
End-to-end flow from agent parking to operator decision and execution, with enhanced security controls for outbound egress:

```mermaid
sequenceDiagram
participant Agent as "Agent Kernel"
participant Perm as "GatewayPermissionMiddleware"
participant Reg as "ConfirmationRegistry"
participant Rec as "ConfirmationRecordStore"
participant GW as "Platform Gateway"
participant Pol as "Policy Engine"
participant Op as "Operator Portal"
participant HTTP as "HTTP Connector"
Note over Agent,Perm : Outbound egress requires explicit approval
Agent->>Perm : Check permission for http.get
Perm-->>Agent : ASK (not auto-allowed by default)
Agent->>Reg : register(session_id, tool_calls, timeout, risk_levels, ...)
Reg-->>Agent : PendingConfirmation(confirm_id)
Agent->>Rec : save_parked(record with pending_calls, action, flow_summary, approval_kind, message)
Agent-->>Op : SSE confirmation_request frame {session_id, confirm_id, payload}
Note over Op : Action card shows outbound egress details
Op->>GW : POST /api/v1/chat/confirm {session_id, confirm_id, decision}
GW->>Pol : evaluate(roles, action="tools : mutate")
Pol-->>GW : {decision : allow|deny|require_approval, approval_tier, approval}
alt require_approval
GW->>Op : 403 with reason (not_a_designated_approver/self_approval)
else allowed
GW->>Reg : claim(session_id, confirm_id)
Reg-->>GW : PendingConfirmation (single-flight)
GW->>Rec : mark_resolved(status=approved/denied, decider_user_id, decision)
GW->>HTTP : execute http.get with validated URL
HTTP-->>GW : ToolResult with response data
GW-->>Agent : resume with approved/denied outcome
end
```

**Diagram sources**
- [kernel_middleware.py:221-305](file://products/agent-platform/src/agent_service/services/kernel_middleware.py#L221-L305)
- [hitl_confirmations.py:468-534](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L468-L534)
- [confirmation_records.py:543-604](file://products/agent-platform/src/agent_service/services/confirmation_records.py#L543-L604)
- [policy_engine.py:390-444](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L390-L444)
- [http_connector.py:556-592](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L556-L592)

## Detailed Component Analysis

### Hardened Auto-Allow List and Outbound Egress Security
**Updated** The platform now implements a hardened security posture where outbound network egress operations require explicit operator approval by default.

- **Removed http.get from built-in defaults**: The `DEFAULT_AUTO_ALLOWED_TOOLS` no longer includes `http.get`, treating outbound egress as a different risk class than in-cluster reads
- **New additive configuration**: `AGENT_GATEWAY_TOOL_AUTO_ALLOW_EXTRA` allows environments to opt individual tools back into auto-approval without restating the entire default list
- **Defense-in-depth approach**: While the kernel allow-list is a HITL bypass switch, the actual egress boundary lives in the tool-gateway's `http_connector` which runs on every call regardless of the kernel allow-list
- **SSRF protection**: The hardening addresses a medium-severity SSRF finding (CWE-918) by ensuring outbound egress receives appropriate human oversight

```mermaid
flowchart TD
Start(["Tool Invocation"]) --> CheckAllow{"In DEFAULT_AUTO_ALLOWED_TOOLS?"}
CheckAllow --> |No| ParkCard["Park for operator approval"]
CheckAllow --> |Yes| CheckExtra{"In AUTO_ALLOW_EXTRA?"}
CheckExtra --> |Yes| AutoAllow["Auto-allow"]
CheckExtra --> |No| ParkCard
ParkCard --> End(["Action Card Created"])
AutoAllow --> End
```

**Diagram sources**
- [kernel_middleware.py:117-138](file://products/agent-platform/src/agent_service/services/kernel_middleware.py#L117-L138)
- [kernel_middleware.py:96-112](file://products/agent-platform/src/agent_service/services/kernel_middleware.py#L96-L112)

**Section sources**
- [kernel_middleware.py:96-112](file://products/agent-platform/src/agent_service/services/kernel_middleware.py#L96-L112)
- [kernel_middleware.py:117-138](file://products/agent-platform/src/agent_service/services/kernel_middleware.py#L117-L138)
- [2026-09-20-post-web-checks-egress-hardening.md:45-89](file://docs/agentic-aiops-platform/release-notes/2026-09-20-post-web-checks-egress-hardening.md#L45-L89)

### Confirmation Registry and Durable Records
- Parking: the kernel registers a PendingConfirmation with tool calls, risk levels, gateway names, browser element map, flow summary, and approval kind
- Display: pending_calls_payload serializes tool calls, injects change_request for action cards, masks secrets, and attaches risk_level/action for policy bridging
- Single-flight: claim marks the entry claimed to prevent double-resume; take_for_expiry claims for cleanup without racing decision paths
- Resolution: resolve clears the entry; mark_resolved persists status, decider, decision, and timestamps
- Persistence: InMemory and Postgres backends share the same interface; Postgres initializes tables, migrates columns, and sweeps stale rows at startup

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
+dict browser_element_map
+dict browser_flow
+string approval_kind
+float created_at
+bool resolved
+bool claimed
+is_expired(timeout) bool
+pending_calls_payload() list
+highest_action() string?
+tool_names() string[]
+flow_summary() dict?
}
class ConfirmationRegistry {
+register(...)
+get(session_id, confirm_id, timeout)
+claim(session_id, confirm_id, timeout)
+take_for_expiry(session_id, confirm_id)
+peek_parked(session_id)
+resolve(session_id, confirm_id)
+is_parked(session_id, timeout) bool
+has_pending(session_id) bool
}
class ConfirmationRecordStore {
<<interface>>
+save_parked(record)
+mark_resolved(session_id, confirm_id, status, decider_user_id, decision)
+load_for_session(session_id) list
+load_record(session_id, confirm_id) dict?
+load_pending_inbox() list
+load_inbox_history(limit, offset) tuple
+delete_session(session_id) bool
+is_ready() bool
}
ConfirmationRegistry --> PendingConfirmation : "manages"
ConfirmationRegistry --> ConfirmationRecordStore : "persists lifecycle"
```

**Diagram sources**
- [hitl_confirmations.py:47-181](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L47-L181)
- [hitl_confirmations.py:452-595](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L452-L595)
- [confirmation_records.py:99-134](file://products/agent-platform/src/agent_service/services/confirmation_records.py#L99-L134)

**Section sources**
- [hitl_confirmations.py:98-181](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L98-L181)
- [hitl_confirmations.py:452-595](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L452-L595)
- [confirmation_records.py:141-245](file://products/agent-platform/src/agent_service/services/confirmation_records.py#L141-L245)
- [confirmation_records.py:492-686](file://products/agent-platform/src/agent_service/services/confirmation_records.py#L492-L686)

### Flow Approvals (Browser Flow Identity and Auto-Signing)
- FlowContext reflects the gateway-bound browser flow identity (skill_id, origin) and metadata used for card headlines and intent
- FlowApproval scopes auto-signing authority to the approved flow identity with a TTL; subsequent writes in the same flow are admitted while identity matches and TTL holds
- Write-tier tools include web.click, web.type, web.select, web.press_key, web.upload_file, web.evaluate, and http.post
- Flow-killing error codes drop both context and approval to prevent stale authority

```mermaid
flowchart TD
Start(["Write Tool Invocation"]) --> CheckTier{"Is tool in write tier?"}
CheckTier --> |No| AutoAllow["Auto-allow read-tier"]
CheckTier --> |Yes| GetCtx["Get FlowContext by session"]
GetCtx --> HasCtx{"Flow bound?"}
HasCtx --> |No| Park["Park for operator approval"]
HasCtx --> |Yes| GetAppr["Get FlowApproval by session"]
GetAppr --> Valid{"Identity matches AND not expired?"}
Valid --> |Yes| Admit["Admit and auto-sign under authority"]
Valid --> |No| KillCheck{"Gateway refusal code?"}
KillCheck --> |Killing| DropStores["Drop FlowContext and FlowApproval"]
DropStores --> Park
KillCheck --> |Not killing| Park
AutoAllow --> End(["Return result"])
Park --> End
Admit --> End
```

**Diagram sources**
- [flow_approvals.py:41-75](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L41-L75)
- [flow_approvals.py:78-122](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L78-L122)
- [flow_approvals.py:167-259](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L167-L259)

**Section sources**
- [flow_approvals.py:41-75](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L41-L75)
- [flow_approvals.py:78-122](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L78-L122)
- [flow_approvals.py:167-259](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L167-L259)

### Policy Engine and Approval Tiers
- Actions include chat, tools:invoke, tools:mutate, chat:confirm, approvals:list, and others
- Outcomes: allow, deny, require_approval; precedence is deny > require_approval > allow
- require_approval carries an approval block with tier (tier_1 or tier_2), decided_by_roles, and optional allow_self_approval
- Only bridged actions (currently tools:mutate) may use require_approval in this slice
- Default bundle enforces tier_2 for mutating execution with designated approvers distinct from requester

```mermaid
flowchart TD
Eval["evaluate(roles, action)"] --> Load["Load bundle rules"]
Load --> Match["Match enabled rules by roles and actions"]
Match --> AnyDeny{"Any deny matched?"}
AnyDeny --> |Yes| Deny["Return deny"]
AnyDeny --> |No| AnyReq{"Any require_approval matched?"}
AnyReq --> |Yes| BestReq["Pick highest priority require_approval"]
BestReq --> ReturnReq["Return require_approval with approval block"]
AnyReq --> |No| AnyAllow{"Any allow matched?"}
AnyAllow --> |Yes| BestAllow["Pick highest priority allow"]
BestAllow --> ReturnAllow["Return allow"]
AnyAllow --> |No| DefaultDeny["Return deny (no match)"]
```

**Diagram sources**
- [policy_engine.py:390-444](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L390-L444)
- [policy-default.yaml:129-152](file://shared/shared-contracts/policies/policy-default.yaml#L129-L152)

**Section sources**
- [policy_engine.py:119-127](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L119-L127)
- [policy_engine.py:142-210](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L142-L210)
- [policy_engine.py:390-444](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L390-L444)
- [policy-default.yaml:129-152](file://shared/shared-contracts/policies/policy-default.yaml#L129-L152)

### Enhanced HTTP Tools with Security Validation
**Updated** HTTP tools now implement comprehensive security measures with enhanced approval requirements for outbound egress operations.

- **Hardened security posture**: `http.get` removed from built-in auto-allow list due to outbound egress risk
- **URL validation**: Refuses secret-bearing query parameters with HTTP_URL_SECRET_NOT_ALLOWED
- **Body validation**: Enforces depth limits, key count limits, and byte size caps before transport
- **Credential set support**: Requires explicit credential set configuration for authenticated requests
- **Structured rendering**: Preserves JSON structure while masking secret-bearing keys
- **Fail-closed masking**: Uses KNOWN_SAFE_FIELDS allow-list where only explicitly whitelisted fields render verbatim
- **Defense in depth**: Multiple layers of protection including connector-level validation and approval-card masking

```mermaid
flowchart TD
Build["Build http.request change request"] --> ValidateURL{"Validate URL"}
ValidateURL --> CheckOrigin{"Origin allowlisted?"}
CheckOrigin --> |No| DenyOrigin["HTTP_ORIGIN_NOT_ALLOWED"]
CheckOrigin --> |Yes| CheckSecret{"Secret in query?"}
CheckSecret --> |Yes| DenySecret["HTTP_URL_SECRET_NOT_ALLOWED"]
CheckSecret --> |No| CheckMethod{"GET or POST?"}
CheckMethod --> |GET| ReadPath["Read-tier validation"]
CheckMethod --> |POST| WritePath["Write-tier validation"]
ReadPath --> Execute["Execute with security bounds"]
WritePath --> Execute
DenyOrigin --> ReturnError["Return structured error"]
DenySecret --> ReturnError
Execute --> ReturnResult["Return ToolResult with evidence"]
```

**Diagram sources**
- [http_connector.py:100-180](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L100-L180)
- [http_connector.py:183-219](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L183-L219)
- [http_connector.py:556-592](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L556-L592)
- [http_connector.py:654-699](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L654-L699)

**Section sources**
- [http_connector.py:100-180](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L100-L180)
- [http_connector.py:183-219](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L183-L219)
- [http_connector.py:556-592](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L556-L592)
- [http_connector.py:654-699](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L654-L699)
- [secret_params.py:136-153](file://products/agent-platform/src/agent_service/services/secret_params.py#L136-L153)

### Confirmation Cards, Change Requests, and Browser Element Hints
- Action cards project decision-relevant parameters into a change_request sibling of parameters so signed digests remain unchanged
- Curated formatters produce effect sentences for critical mutating tools; generic fallback provides masked label/value fields
- Browser tools referencing snapshot elements can show human-readable element descriptions instead of raw refs
- Secrets are masked consistently using secret parameter masking rules
- **HTTP tools provide structured field listings with appropriate masking based on field names and content type**

```mermaid
flowchart TD
Build["Build confirmation payload"] --> ForEach["For each parked call"]
ForEach --> CR{"approval_kind == 'action'?"}
CR --> |Yes| Project["Project change_request (masked)"]
CR --> |No| SkipCR["Skip projection"]
ForEach --> Risk{"Has risk_level?"}
Risk --> |Yes| AddAction["Attach action for policy bridge"]
Risk --> |No| NoAction["No action"]
ForEach --> Hint{"Browser ref tool with element map?"}
Hint --> |Yes| AddHint["Add display_hint for element"]
Hint --> |No| NoHint["No hint"]
Project --> Next["Next call"]
SkipCR --> Next
AddAction --> Next
NoAction --> Next
AddHint --> Next
NoHint --> Next
```

**Diagram sources**
- [hitl_confirmations.py:98-181](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L98-L181)
- [hitl_confirmations.py:195-359](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L195-L359)
- [hitl_confirmations.py:379-409](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L379-L409)

**Section sources**
- [hitl_confirmations.py:98-181](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L98-L181)
- [hitl_confirmations.py:195-359](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L195-L359)
- [hitl_confirmations.py:379-409](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L379-L409)

## Dependency Analysis
- ConfirmationRegistry depends on PendingConfirmation data and exposes single-flight claim/resolve semantics
- ConfirmationRecordStore abstracts memory/postgres backends; Postgres backend includes migration and startup sweep
- FlowApprovals maintains per-session FlowContext and FlowApproval with TTL checks and identity guards
- PolicyEngine consumes the default policy bundle and returns structured decisions including approval blocks
- **GatewayPermissionMiddleware enforces hardened auto-allow list with outbound egress restrictions**
- Secret parameter masking provides fail-closed posture with KNOWN_SAFE_FIELDS allow-list for secure parameter handling
- HTTP Connector implements comprehensive security validation and approval requirements
- Schemas enforce request shapes and decision structures across components

```mermaid
graph LR
Reg["ConfirmationRegistry"] --> Rec["ConfirmationRecordStore"]
Reg --> PC["PendingConfirmation"]
FA["FlowApprovals"] --> FC["FlowContextStore"]
FA --> FP["FlowApprovalStore"]
GW["Platform Gateway"] --> PE["Policy Engine"]
PE --> PB["policy-default.yaml"]
GW --> CS["chat-confirm.schema.json"]
PE --> PD["policy-decision.schema.json"]
SP["Secret Parameter Masking"] --> REG["Confirmation Registry"]
HTTP["HTTP Connector"] --> SP
Perm["GatewayPermissionMiddleware"] --> REG
Perm --> HTTP
```

**Diagram sources**
- [hitl_confirmations.py:452-595](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L452-L595)
- [confirmation_records.py:141-245](file://products/agent-platform/src/agent_service/services/confirmation_records.py#L141-L245)
- [flow_approvals.py:124-274](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L124-L274)
- [policy_engine.py:390-444](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L390-L444)
- [kernel_middleware.py:96-112](file://products/agent-platform/src/agent_service/services/kernel_middleware.py#L96-L112)
- [secret_params.py:136-153](file://products/agent-platform/src/agent_service/services/secret_params.py#L136-L153)
- [http_connector.py:503-535](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L503-L535)

**Section sources**
- [hitl_confirmations.py:452-595](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L452-L595)
- [confirmation_records.py:141-245](file://products/agent-platform/src/agent_service/services/confirmation_records.py#L141-L245)
- [flow_approvals.py:124-274](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L124-L274)
- [policy_engine.py:390-444](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L390-L444)
- [kernel_middleware.py:96-112](file://products/agent-platform/src/agent_service/services/kernel_middleware.py#L96-L112)

## Performance Considerations
- In-memory registries provide low-latency single-flight control; durable records add persistence overhead but ensure resilience
- Postgres queries are bounded by limits and history windows; opportunistic sweeps reclaim old resolved rows
- Flow approvals are per-process and TTL-bounded to avoid long-lived authority; clearing on flow-killing errors prevents stale unlocks
- Card payload construction avoids modifying signed parameters; projections are siblings to preserve digests
- **HTTP tool validation occurs before transport calls to prevent unnecessary network overhead**
- **Hardened auto-allow list reduces unnecessary approval cards for vetted in-cluster operations**
- Shape-preserving masking operates efficiently on nested structures without deep copying entire payloads

## Troubleshooting Guide
Common issues and resolutions:
- Double confirm attempts: ConfirmationRegistry.claim ensures single-flight; duplicate confirms raise NotFound after claim
- Expired parks: ConfirmationExpired indicates TTL breach; cleanup via expire_confirmation resumes interruption
- Stale flow authority: Flow-killing error codes drop both FlowContext and FlowApproval; next write re-parks
- Missing signing key or worker unavailability: Approved resumes fail closed and audit rejection events; no unsigned fallback
- Inbox pagination and history: Use limit/offset for history; pending queue is always complete and sorted newest first
- **HTTP tool approval issues**: Verify URL doesn't contain secret query parameters; check credential set configuration; validate body structure and size limits; ensure origin is allowlisted
- **Outbound egress approval**: New http.get calls will park action cards by default - configure AGENT_GATEWAY_TOOL_AUTO_ALLOW_EXTRA=http.get to restore previous behavior

Operational tips:
- Verify policy bundle SHA-256 on readiness endpoints to confirm enforced configuration
- Confirm AGENT_HITL_CONFIRM_TIMEOUT aligns with expected operator response time
- Ensure approver roles have chat:confirm and approvals:list grants per policy bundle
- **Monitor HTTP tool usage patterns and adjust body size limits based on operational needs**
- **Review outbound egress policies to ensure appropriate human oversight for network operations**

**Section sources**
- [hitl_confirmations.py:496-558](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L496-L558)
- [confirmation_records.py:521-542](file://products/agent-platform/src/agent_service/services/confirmation_records.py#L521-L542)
- [flow_approvals.py:56-75](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L56-L75)
- [approval-and-hitl.md:229-288](file://docs/guides/approval-and-hitl.md#L229-L288)

## Conclusion
The Agent Platform's HITL approval system combines layered enforcement with enhanced security posture:
- Policy engine decisions gate who can decide and at what tier
- Confirmation registry manages parking, single-flight decisions, and TTL
- Durable records persist decisions and support inbox/history surfaces
- Flow approvals enable safe auto-signing within bounded browser flows
- **Hardened security posture requires explicit approval for outbound network egress operations**
- **Defense-in-depth approach ensures multiple layers of protection for sensitive operations**
- Schemas and bundles standardize behavior across components

Together, these mechanisms ensure risky operations execute only with explicit, auditable, and policy-compliant human approval, including sophisticated HTTP operations with comprehensive security validation and enhanced approval requirements for outbound egress.

## Appendices

### Risk Tier Classification and Tool Categorization
- Read-tier tools auto-allow where configured; they never reach flow-unlock
- Write-tier tools include web.click, web.type, web.select, web.press_key, web.upload_file, web.evaluate, and http.post
- web.fill_credential is read-tier and does not park a card; it names its credential set
- web.evaluate takes only expression and no element ref; it is not a ref-taking tool
- **http.get is now read-tier but requires explicit approval by default due to outbound egress risk**
- **http.post requires tools:mutate permission and follows the same approval workflow as other write-tier tools**

**Section sources**
- [hitl_confirmations.py:101-104](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L101-L104)
- [flow_approvals.py:41-54](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L41-L54)
- [kernel_middleware.py:96-112](file://products/agent-platform/src/agent_service/services/kernel_middleware.py#L96-L112)
- [SPEC-058-http-service-check-tools/spec.md:122-115](file://docs/specs/SPEC-058-http-service-check-tools/spec.md#L122-L115)

### Approval Escalation Paths
- tier_1: operator self-approval (default when no require_approval rule)
- tier_2: designated approver distinct from requester; self-approval blocked by default
- Shipped bundle requires tier_2 for tools:mutate with decided_by_roles approver and platform-admin
- **http.get and http.post inherit the same escalation paths as other tools, with http.get requiring explicit approval by default**

**Section sources**
- [policy-default.yaml:129-152](file://shared/shared-contracts/policies/policy-default.yaml#L129-L152)
- [approval-and-hitl.md:189-227](file://docs/guides/approval-and-hitl.md#L189-L227)

### Configuring Approval Policies
- Edit shared/shared-contracts/policies/policy-default.yaml and bump version
- Sync consumer copies and validate with make verify
- Deploy ConfigMap; confirm bundle SHA-256 on readiness endpoints
- Adjust AGENT_GATEWAY_TOOL_AUTO_ALLOW for read-only auto-approval lists
- Set AGENT_HITL_CONFIRM_TIMEOUT to control park lifetime
- **Configure AGENT_GATEWAY_TOOL_AUTO_ALLOW_EXTRA=http.get to restore previous http.get auto-approval behavior**
- Configure HTTP tool settings including body size limits and credential sets

**Section sources**
- [approval-and-hitl.md:118-188](file://docs/guides/approval-and-hitl.md#L118-L188)
- [2026-09-20-post-web-checks-egress-hardening.md:59-89](file://docs/agentic-aiops-platform/release-notes/2026-09-20-post-web-checks-egress-hardening.md#L59-L89)

### Handling Approval Decisions and Auditing
- Operator submits POST /api/v1/chat/confirm with session_id, confirm_id, decision
- Platform gateway evaluates policy and enforces tier constraints
- Durable records capture status, decider, decision, and timestamps
- Audit trail correlates confirmation_decided with execution_requested/completed/rejected
- **HTTP tool approvals include structured information in audit trails with appropriate masking**

**Section sources**
- [chat-confirm.schema.json:1-27](file://shared/shared-contracts/schemas/chat-confirm.schema.json#L1-L27)
- [policy-decision.schema.json:1-60](file://shared/shared-contracts/schemas/policy-decision.schema.json#L1-L60)
- [approval-and-hitl.md:290-333](file://docs/guides/approval-and-hitl.md#L290-L333)

### Implementing Custom Approval Flows
- Extend change_request formatters for new tools to improve card readability
- Add browser element parsing for new snapshot formats if needed
- Ensure new tools declare correct risk_level and integrate with auto-allow lists
- For browser flows, rely on FlowContext/FlowApproval to scope auto-signing safely
- **Follow the http tool pattern for implementing custom HTTP tools with structured validation and security enforcement**

**Section sources**
- [hitl_confirmations.py:195-359](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L195-L359)
- [hitl_confirmations.py:412-449](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L412-L449)
- [flow_approvals.py:78-122](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L78-L122)

### Race Conditions and Timeouts
- Single-flight claim prevents double-resume; take_for_expiry claims for cleanup without interrupting in-flight decisions
- TTL-based expiry closes parked calls; startup sweep expires stale pending rows in Postgres
- Flow approvals expire based on captured TTL; zero disables flow-unlock entirely
- **HTTP tools inherit the same race condition protections as other tools**

**Section sources**
- [hitl_confirmations.py:520-558](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L520-L558)
- [confirmation_records.py:521-542](file://products/agent-platform/src/agent_service/services/confirmation_records.py#L521-L542)
- [flow_approvals.py:189-199](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L189-L199)

### User Experience Considerations
- Action cards present concise effect sentences and masked fields for clarity and safety
- Browser tools show human-readable element descriptions when available
- Owner transcript cards anchor under the parking exchange and poll for live updates
- Approver inbox splits pending and history with pagination and counts
- **HTTP tool approval cards provide structured field listings with clear indication of which fields contain sensitive data**
- **Outbound egress operations now clearly indicate the security rationale for requiring approval**

**Section sources**
- [hitl_confirmations.py:98-181](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L98-L181)
- [approval-and-hitl.md:229-288](file://docs/guides/approval-and-hitl.md#L229-L288)

### HTTP Tool Security and Validation
**Updated** HTTP tools implement comprehensive security measures with enhanced approval requirements for outbound egress operations.

- **Hardened security posture**: `http.get` removed from built-in auto-allow list due to outbound egress risk
- **URL validation**: Refuses secret-bearing query parameters with HTTP_URL_SECRET_NOT_ALLOWED
- **Body validation**: Enforces depth limits, key count limits, and byte size caps before transport
- **Credential set support**: Requires explicit credential set configuration for authenticated requests
- **Structured rendering**: Preserves JSON structure while masking secret-bearing keys
- **Fail-closed masking**: Uses KNOWN_SAFE_FIELDS allow-list where only explicitly whitelisted fields render verbatim
- **Defense in depth**: Multiple layers of protection including connector-level validation and approval-card masking
- **SSRF protection**: Addresses medium-severity SSRF findings through enhanced human oversight

**Section sources**
- [http_connector.py:100-180](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L100-L180)
- [http_connector.py:183-219](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L183-L219)
- [http_connector.py:556-592](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L556-L592)
- [http_connector.py:654-699](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L654-L699)
- [secret_params.py:136-153](file://products/agent-platform/src/agent_service/services/secret_params.py#L136-L153)
- [2026-09-20-post-web-checks-egress-hardening.md:11-44](file://docs/agentic-aiops-platform/release-notes/2026-09-20-post-web-checks-egress-hardening.md#L11-L44)