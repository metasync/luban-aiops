# Tool Execution Schemas

<cite>
**Referenced Files in This Document**
- [tool-invocation.schema.json](file://shared/shared-contracts/schemas/tool-invocation.schema.json)
- [tool-result.schema.json](file://shared/shared-contracts/schemas/tool-result.schema.json)
- [execution-request.schema.json](file://shared/shared-contracts/schemas/execution-request.schema.json)
- [execution-receipt.schema.json](file://shared/shared-contracts/schemas/execution-receipt.schema.json)
- [base.py](file://products/tool-gateway/src/tool_gateway/tools/base.py)
- [registry.py](file://products/tool-gateway/src/tool_gateway/tools/registry.py)
- [tools.py](file://products/tool-gateway/src/tool_gateway/api/routes/tools.py)
- [authorization.py](file://products/tool-gateway/src/tool_gateway/schemas/authorization.py)
- [routes.py](file://products/agent-platform/src/agent_service/api/v2/routes.py)
- [execution_signing.py (agent-platform)](file://products/agent-platform/src/agent_service/services/execution_signing.py)
- [execution_signing.py (execution-runtime)](file://products/execution-runtime/src/execution_runtime/services/execution_signing.py)
</cite>

## Update Summary
**Changes Made**
- Added documentation for the new `authorization_required` field in the tool-result schema
- Updated Tool Result Schema section to cover TARGET_AUTHORIZATION_REQUIRED error handling
- Added new Authorization Required Signal section explaining the owner-scoped routing metadata
- Updated examples and workflows to include authorization-required scenarios
- Enhanced error handling documentation with the new reserved error code

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Dependency Analysis](#dependency-analysis)
7. [Performance Considerations](#performance-considerations)
8. [Troubleshooting Guide](#troubleshooting-guide)
9. [Conclusion](#conclusion)
10. [Appendices](#appendices)

## Introduction
This document defines the schemas and execution workflows for tool invocation, results, and distributed execution envelopes across the platform. It explains:
- How tools are invoked with validated parameters and identity context
- How tool results are structured, including success, error, policy-denied, and authorization-required outcomes
- How signed execution requests and receipts provide tamper-evident audit trails across workers
- How evidence is attached to tool results for provenance and UI rendering
- How authorization-required signals carry opaque owner-scoped routing metadata for first-use OAuth flows
- Examples of calls, result formats, error scenarios, and end-to-end workflows

## Project Structure
The tool execution surface spans shared JSON schemas and product services:
- Shared schemas define the contract between components
- The tool gateway exposes discovery and invocation endpoints and enforces policies
- The agent platform builds signed execution requests when approvals resume
- The execution runtime verifies incoming requests and signs receipts after execution

```mermaid
graph TB
subgraph "Shared Contracts"
A["tool-invocation.schema.json"]
B["tool-result.schema.json"]
C["execution-request.schema.json"]
D["execution-receipt.schema.json"]
end
subgraph "Tool Gateway"
E["tools.py<br/>Routes"]
F["registry.py<br/>Dispatch"]
G["base.py<br/>ToolResult + Evidence"]
H["authorization.py<br/>AuthorizationRequired"]
end
subgraph "Agent Platform"
I["execution_signing.py<br/>Build requests/receipts"]
J["routes.py<br/>Stream events"]
end
subgraph "Execution Runtime"
K["execution_signing.py<br/>Verify requests / sign receipts"]
end
A --> E
B --> G
C --> I
D --> K
E --> F
F --> G
G --> H
I --> K
J --> H
```

**Diagram sources**
- [tool-invocation.schema.json:1-35](file://shared/shared-contracts/schemas/tool-invocation.schema.json#L1-L35)
- [tool-result.schema.json:1-93](file://shared/shared-contracts/schemas/tool-result.schema.json#L1-L93)
- [execution-request.schema.json:1-71](file://shared/shared-contracts/schemas/execution-request.schema.json#L1-L71)
- [execution-receipt.schema.json:1-47](file://shared/shared-contracts/schemas/execution-receipt.schema.json#L1-L47)
- [tools.py:1-51](file://products/tool-gateway/src/tool_gateway/api/routes/tools.py#L1-L51)
- [registry.py:1-89](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L1-L89)
- [base.py:1-148](file://products/tool-gateway/src/tool_gateway/tools/base.py#L1-L148)
- [authorization.py:1-33](file://products/tool-gateway/src/tool_gateway/schemas/authorization.py#L1-L33)
- [routes.py:620-680](file://products/agent-platform/src/agent_service/api/v2/routes.py#L620-L680)
- [execution_signing.py (agent-platform):1-175](file://products/agent-platform/src/agent_service/services/execution_signing.py#L1-L175)
- [execution_signing.py (execution-runtime):1-93](file://products/execution-runtime/src/execution_runtime/services/execution_signing.py#L1-L93)

**Section sources**
- [tools.py:1-51](file://products/tool-gateway/src/tool_gateway/api/routes/tools.py#L1-L51)
- [registry.py:1-89](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L1-L89)
- [base.py:1-148](file://products/tool-gateway/src/tool_gateway/tools/base.py#L1-L148)
- [authorization.py:1-33](file://products/tool-gateway/src/tool_gateway/schemas/authorization.py#L1-L33)
- [routes.py:620-680](file://products/agent-platform/src/agent_service/api/v2/routes.py#L620-L680)
- [execution_signing.py (agent-platform):1-175](file://products/agent-platform/src/agent_service/services/execution_signing.py#L1-L175)
- [execution_signing.py (execution-runtime):1-93](file://products/execution-runtime/src/execution_runtime/services/execution_signing.py#L1-L93)

## Core Components
- Tool Invocation Schema: Defines the request envelope sent to the tool gateway, including tool name, parameters, identity context, and a unique request ID.
- Tool Result Schema: Defines the response envelope returned by tools, including status, data, evidence, optional error details, and optional authorization-required metadata.
- Execution Request Schema: Signed envelope created when an approved parked tool call resumes; binds approver intent to executed arguments via a digest and HMAC signature.
- Execution Receipt Schema: Signed envelope written after execution completes; closes the corresponding request with a mapped outcome and a digest of the tool result.

Key implementation anchors:
- Tool registry dispatches invocations and returns structured errors for unknown or failing tools
- Base tool utilities build evidence and standardized error/denied results
- Agent platform signs execution requests and receipts using canonical JSON and HMAC-SHA256
- Execution runtime verifies incoming requests and signs receipts, ensuring fail-closed behavior without a signing key
- Authorization-required signals carry opaque owner-scoped routing metadata for first-use OAuth flows

**Section sources**
- [tool-invocation.schema.json:1-35](file://shared/shared-contracts/schemas/tool-invocation.schema.json#L1-L35)
- [tool-result.schema.json:1-93](file://shared/shared-contracts/schemas/tool-result.schema.json#L1-L93)
- [execution-request.schema.json:1-71](file://shared/shared-contracts/schemas/execution-request.schema.json#L1-L71)
- [execution-receipt.schema.json:1-47](file://shared/shared-contracts/schemas/execution-receipt.schema.json#L1-L47)
- [registry.py:1-89](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L1-L89)
- [base.py:1-148](file://products/tool-gateway/src/tool_gateway/tools/base.py#L1-L148)
- [authorization.py:1-33](file://products/tool-gateway/src/tool_gateway/schemas/authorization.py#L1-L33)
- [execution_signing.py (agent-platform):1-175](file://products/agent-platform/src/agent_service/services/execution_signing.py#L1-L175)
- [execution_signing.py (execution-runtime):1-93](file://products/execution-runtime/src/execution_runtime/services/execution_signing.py#L1-L93)

## Architecture Overview
End-to-end flow from approval to execution and receipt:

```mermaid
sequenceDiagram
participant Client as "Caller"
participant Gateway as "Tool Gateway"
participant Registry as "ToolRegistry"
participant Tool as "BaseTool.execute"
participant Agent as "Agent Platform"
participant Worker as "Execution Runtime"
Client->>Gateway : POST /api/v2/tools/invoke<br/>tool-invocation schema
Gateway->>Gateway : Resolve identity & enforce policy
Gateway->>Registry : invoke(name, parameters, identity)
Registry->>Tool : execute(parameters, identity)
Tool-->>Registry : ToolResult (success/error/denied/auth-required)
Registry-->>Gateway : ToolResult
Gateway-->>Client : HTTP response with tool-result schema
Note over Agent,Worker : For parked/mutating flows, execution proceeds via signed envelopes
Agent->>Worker : execution-request schema (signed)
Worker->>Worker : Verify signature & args_digest
Worker->>Worker : Execute tool under bounded authority
Worker-->>Agent : execution-receipt schema (signed)
```

**Diagram sources**
- [tools.py:24-51](file://products/tool-gateway/src/tool_gateway/api/routes/tools.py#L24-L51)
- [registry.py:65-89](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L65-L89)
- [base.py:35-148](file://products/tool-gateway/src/tool_gateway/tools/base.py#L35-L148)
- [execution-signing (agent-platform):70-149](file://products/agent-platform/src/agent_service/services/execution_signing.py#L70-L149)
- [execution-signing (execution-runtime):64-93](file://products/execution-runtime/src/execution_runtime/services/execution_signing.py#L64-L93)

## Detailed Component Analysis

### Tool Invocation Schema
- Purpose: Envelope for invoking a registered tool through the tool gateway.
- Required fields: tool_name, request_id
- Optional fields: parameters (tool-specific), identity_context (sub, username, roles)
- Validation:
  - tool_name must match a registered tool
  - parameters shape is defined per tool's parameters_schema
  - identity_context is forwarded from gateway authentication and not trusted from body
- Usage:
  - Callers send this envelope to the gateway's invoke endpoint
  - The gateway resolves identity from the bearer token and enforces policy before dispatch

Example call outline:
- Method: POST
- Path: /api/v2/tools/invoke
- Body: tool-invocation schema
- Headers: Authorization (bearer token), optional x-request-id

**Section sources**
- [tool-invocation.schema.json:1-35](file://shared/shared-contracts/schemas/tool-invocation.schema.json#L1-L35)
- [tools.py:38-51](file://products/tool-gateway/src/tool_gateway/api/routes/tools.py#L38-L51)

### Tool Result Schema
- Purpose: Structured response envelope returned by tool invocation.
- Required fields: tool_name, status, evidence
- Status values: success, error, denied
- Fields:
  - data: present on success
  - evidence: includes executed_at, duration_ms, risk_level, source_system
  - error: present on error or denied; includes code and message
  - authorization_required: present only on TARGET_AUTHORIZATION_REQUIRED errors; carries opaque owner-scoped routing metadata
- Evidence building:
  - Use the base utility to construct evidence with current UTC time, measured duration, declared risk level, and source system
- Error handling:
  - Unknown tools return TOOL_NOT_FOUND
  - Exceptions during execution return TOOL_EXECUTION_ERROR
  - Policy denials return POLICY_DENIED with appropriate risk_level
  - Missing/expired/revoked grants return TARGET_AUTHORIZATION_REQUIRED with authorization_required metadata

**Updated** Added support for the new authorization_required field that carries owner-scoped routing metadata for first-use OAuth flows.

Example result outlines:
- Success: status=success, data populated, evidence present
- Error: status=error, error.code/message, evidence present
- Denied: status=denied, error.code=message POLICY_DENIED, evidence present
- Authorization Required: status=error, error.code=TARGET_AUTHORIZATION_REQUIRED, authorization_required with challenge_id and target

**Section sources**
- [tool-result.schema.json:1-93](file://shared/shared-contracts/schemas/tool-result.schema.json#L1-L93)
- [base.py:35-148](file://products/tool-gateway/src/tool_gateway/tools/base.py#L35-L148)
- [registry.py:65-89](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L65-L89)

### Authorization Required Signal
- Purpose: Specialized error signal indicating that user-delegated authorization is required before proceeding with the operation.
- Trigger conditions: Missing, expired, or revoked OAuth grant for the target system
- Structure:
  - status: "error"
  - error.code: "TARGET_AUTHORIZATION_REQUIRED" (reserved code)
  - error.message: Safe human-readable text naming the target by its configured display label
  - authorization_required: Opaque owner-scoped routing metadata containing:
    - challenge_id: UUID v4 handle for the pending authorization transaction
    - target: Configured target display label (not an endpoint URL)
    - expires_at: Optional timestamp when the challenge stops being actionable
- Security properties:
  - Never contains credentials, verifiers, tokens, or provider URLs
  - Validated against strict schema constraints
  - Owner-scoped to prevent cross-user access
- Flow:
  - Tool implementations detect missing/expired grants and return this specialized error
  - Agent platform streams authorization_required events to the portal
  - Portal uses challenge_id to initiate first-use OAuth authorization flow

**New Section** Documentation for the new authorization-required signal that enables first-use OAuth authorization flows.

**Section sources**
- [tool-result.schema.json:50-92](file://shared/shared-contracts/schemas/tool-result.schema.json#L50-L92)
- [base.py:11-11](file://products/tool-gateway/src/tool_gateway/tools/base.py#L11-L11)
- [base.py:71-80](file://products/tool-gateway/src/tool_gateway/tools/base.py#L71-L80)
- [authorization.py:24-30](file://products/tool-gateway/src/tool_gateway/schemas/authorization.py#L24-L30)
- [routes.py:622-631](file://products/agent-platform/src/agent_service/api/v2/routes.py#L622-L631)

### Execution Request Schema
- Purpose: Signed envelope built when a parked confirmation resumes with approval; one per approved parked tool call.
- Required fields: execution_id, confirm_id, call_id, session_id, owner_user_id, decider_user_id, tool_name, args_digest, requested_at, signature
- Optional field: approval_kind ("action" or "flow")
- Security properties:
  - args_digest is SHA-256 hex of canonical JSON of parked arguments
  - signature is HMAC-SHA256 hex over canonical JSON of all other fields
  - approval_kind is stamped before signing so it is covered by the HMAC
- Construction:
  - Agent platform builds these envelopes on approval resume
  - Flow-based auto-unlocks use a different builder that stamps approval_kind="flow"

Verification at the worker:
- Signature verification against the platform execution-signing key
- args_digest recomputation from executed arguments and mismatch rejection
- Fail-closed if signing key is missing

**Section sources**
- [execution-request.schema.json:1-71](file://shared/shared-contracts/schemas/execution-request.schema.json#L1-L71)
- [execution_signing.py (agent-platform):70-149](file://products/agent-platform/src/agent_service/services/execution_signing.py#L70-L149)
- [execution_signing.py (execution-runtime):1-19](file://products/execution-runtime/src/execution_runtime/services/execution_signing.py#L1-L19)

### Execution Receipt Schema
- Purpose: Signed envelope written after the executed tool result lands; closes one execution request.
- Required fields: execution_id, status, outcome_digest, request_id, completed_at, signature
- Mapping:
  - status maps from tool result outcome to succeeded/failed/timeout
  - outcome_digest is SHA-256 hex of canonical JSON of the tool result
- Construction:
  - Built by both agent platform and execution runtime depending on path
  - Uses same canonicalization and HMAC scheme as requests

Audit trail:
- request_id joins the receipt to the resumed stream's audit trail
- outcome_digest enables integrity checks without storing full results

**Section sources**
- [execution-receipt.schema.json:1-47](file://shared/shared-contracts/schemas/execution-receipt.schema.json#L1-L47)
- [execution_signing.py (agent-platform):152-175](file://products/agent-platform/src/agent_service/services/execution_signing.py#L152-L175)
- [execution_signing.py (execution-runtime):70-93](file://products/execution-runtime/src/execution_runtime/services/execution_signing.py#L70-L93)

### Tool Registry and Dispatch
- Responsibilities:
  - Register tools with validated risk levels
  - Refuse mutating tools unless explicitly allowed
  - Dispatch invocations by name and return structured ToolResult envelopes
- Error handling:
  - Unknown tool names produce a structured error result
  - Exceptions during tool execution are caught and converted to structured error results
- Risk tiers:
  - read/write/admin vocabulary enforced at registration
  - Mutating tools gated behind configuration

**Section sources**
- [registry.py:1-89](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L1-L89)
- [base.py:9-13](file://products/tool-gateway/src/tool_gateway/tools/base.py#L9-L13)

### Evidence and Error Utilities
- Evidence construction:
  - Captures executed_at (UTC ISO), duration_ms, risk_level, source_system
- Standardized results:
  - make_error_result: creates error ToolResult with evidence and error object
  - make_denied_result: creates policy-denied ToolResult with honest risk_level
- BaseTool interface:
  - Implementations must measure execution time and build evidence via provided utilities
- Authorization validation:
  - ToolResult.to_dict() validates that authorization_required is only present with TARGET_AUTHORIZATION_REQUIRED errors
  - AuthorizationRequired model enforces strict schema constraints and rejects secret fields

**Updated** Enhanced with authorization_required validation and AuthorizationRequired model integration.

**Section sources**
- [base.py:83-148](file://products/tool-gateway/src/tool_gateway/tools/base.py#L83-L148)
- [authorization.py:24-30](file://products/tool-gateway/src/tool_gateway/schemas/authorization.py#L24-L30)

## Dependency Analysis
High-level dependencies among components:

```mermaid
graph LR
Schemas["Shared Schemas"] --> Gateway["Tool Gateway Routes"]
Gateway --> Registry["ToolRegistry"]
Registry --> Base["BaseTool + ToolResult"]
Base --> AuthSchema["AuthorizationRequired"]
Agent["Agent Platform Signing"] --> Runtime["Execution Runtime Signing"]
Runtime --> Receipts["Execution Receipts"]
Base --> Results["Tool Results"]
AuthSchema --> StreamEvents["Stream Events"]
```

**Diagram sources**
- [tools.py:1-51](file://products/tool-gateway/src/tool_gateway/api/routes/tools.py#L1-L51)
- [registry.py:1-89](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L1-L89)
- [base.py:1-148](file://products/tool-gateway/src/tool_gateway/tools/base.py#L1-L148)
- [authorization.py:1-33](file://products/tool-gateway/src/tool_gateway/schemas/authorization.py#L1-L33)
- [routes.py:620-680](file://products/agent-platform/src/agent_service/api/v2/routes.py#L620-L680)
- [execution_signing.py (agent-platform):1-175](file://products/agent-platform/src/agent_service/services/execution_signing.py#L1-L175)
- [execution_signing.py (execution-runtime):1-93](file://products/execution-runtime/src/execution_runtime/services/execution_signing.py#L1-L93)

**Section sources**
- [tools.py:1-51](file://products/tool-gateway/src/tool_gateway/api/routes/tools.py#L1-L51)
- [registry.py:1-89](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L1-L89)
- [base.py:1-148](file://products/tool-gateway/src/tool_gateway/tools/base.py#L1-L148)
- [authorization.py:1-33](file://products/tool-gateway/src/tool_gateway/schemas/authorization.py#L1-L33)
- [routes.py:620-680](file://products/agent-platform/src/agent_service/api/v2/routes.py#L620-L680)
- [execution_signing.py (agent-platform):1-175](file://products/agent-platform/src/agent_service/services/execution_signing.py#L1-L175)
- [execution_signing.py (execution-runtime):1-93](file://products/execution-runtime/src/execution_runtime/services/execution_signing.py#L1-L93)

## Performance Considerations
- Canonical JSON and HMAC operations are lightweight but should be avoided in hot paths where possible; they are used only around critical envelopes.
- Evidence duration_ms measurement should be efficient; avoid heavy logging inside tight loops.
- Registry lookups are O(1) dictionary access; ensure tool registrations occur at startup.
- Streaming responses should minimize payload sizes; evidence contains only necessary provenance metadata.
- Authorization-required metadata is small and validated once per response; no performance impact on normal flows.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and resolutions:
- Unknown tool name:
  - Symptom: TOOL_NOT_FOUND in tool result
  - Resolution: Ensure the tool is registered and the name matches exactly
- Tool execution exception:
  - Symptom: TOOL_EXECUTION_ERROR with message from exception
  - Resolution: Inspect tool implementation logs and parameter validation
- Policy denial:
  - Symptom: POLICY_DENIED with reason
  - Resolution: Review permissions and mutation gating; adjust policy or authorization
- Missing signing key:
  - Symptom: Handoff fails closed; no unsigned execution occurs
  - Resolution: Provision the execution-signing key in the environment
- Args digest mismatch:
  - Symptom: Rejection due to args_digest_mismatch
  - Resolution: Ensure executed arguments match the parked arguments seen by the approver
- Authorization required error:
  - Symptom: TARGET_AUTHORIZATION_REQUIRED with authorization_required metadata
  - Resolution: Complete the first-use OAuth authorization flow using the provided challenge_id
- Invalid authorization metadata:
  - Symptom: ValueError about authorization metadata requiring reserved error result
  - Resolution: Ensure authorization_required is only present with status="error" and error.code="TARGET_AUTHORIZATION_REQUIRED"

**Updated** Added troubleshooting for authorization-required scenarios and metadata validation errors.

**Section sources**
- [registry.py:65-89](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L65-L89)
- [execution_signing.py (agent-platform):29-34](file://products/agent-platform/src/agent_service/services/execution_signing.py#L29-L34)
- [execution_signing.py (execution-runtime):29-34](file://products/execution-runtime/src/execution_runtime/services/execution_signing.py#L29-L34)
- [base.py:71-80](file://products/tool-gateway/src/tool_gateway/tools/base.py#L71-L80)

## Conclusion
The tool execution framework standardizes how tools are invoked, how results are returned, and how distributed execution is secured with signed envelopes. The shared schemas define a clear contract, while the tool gateway and signing services enforce policy, identity, and integrity. Evidence and receipts provide auditable provenance for every action, enabling transparency and compliance. The new authorization-required signal enables seamless first-use OAuth authorization flows while maintaining security boundaries and preventing credential leakage.

[No sources needed since this section summarizes without analyzing specific files]

## Appendices

### Example Workflows

#### Direct Tool Invocation
- Caller sends a tool-invocation envelope to the gateway
- Gateway resolves identity and enforces policy
- Registry dispatches to the tool implementation
- Tool returns a tool-result envelope with evidence

```mermaid
sequenceDiagram
participant C as "Caller"
participant GW as "Tool Gateway"
participant R as "Registry"
participant T as "Tool"
C->>GW : Invoke tool
GW->>R : Lookup and dispatch
R->>T : Execute
T-->>R : ToolResult
R-->>GW : ToolResult
GW-->>C : Response
```

**Diagram sources**
- [tools.py:38-51](file://products/tool-gateway/src/tool_gateway/api/routes/tools.py#L38-L51)
- [registry.py:65-89](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L65-L89)

#### Approval-Resumed Execution with Signed Envelopes
- Approver resumes a parked confirmation
- Agent platform builds a signed execution request with args_digest and approval_kind
- Execution runtime verifies signature and args_digest, executes tool, and signs a receipt

```mermaid
sequenceDiagram
participant AP as "Agent Platform"
participant ER as "Execution Runtime"
participant T as "Tool"
AP->>ER : execution-request (signed)
ER->>ER : Verify signature & args_digest
ER->>T : Execute tool
T-->>ER : ToolResult
ER-->>AP : execution-receipt (signed)
```

**Diagram sources**
- [execution_signing.py (agent-platform):70-149](file://products/agent-platform/src/agent_service/services/execution_signing.py#L70-L149)
- [execution_signing.py (execution-runtime):64-93](file://products/execution-runtime/src/execution_runtime/services/execution_signing.py#L64-L93)

#### First-Use OAuth Authorization Flow
- Tool detects missing/expired OAuth grant
- Returns TARGET_AUTHORIZATION_REQUIRED with authorization_required metadata
- Agent platform streams authorization_required event to portal
- Portal initiates OAuth flow using challenge_id
- User completes authorization, tool can proceed on retry

```mermaid
sequenceDiagram
participant T as "Tool"
participant GW as "Tool Gateway"
participant AP as "Agent Platform"
participant Portal as "Portal UI"
T->>GW : ToolResult with TARGET_AUTHORIZATION_REQUIRED
GW->>AP : Stream authorization_required event
AP->>Portal : Display authorization card
Portal->>Portal : Initiate OAuth flow with challenge_id
Portal->>Portal : User completes authorization
Portal->>T : Retry tool call with authorized session
```

**Diagram sources**
- [tool-result.schema.json:50-92](file://shared/shared-contracts/schemas/tool-result.schema.json#L50-L92)
- [routes.py:622-631](file://products/agent-platform/src/agent_service/api/v2/routes.py#L622-L631)
- [authorization.py:24-30](file://products/tool-gateway/src/tool_gateway/schemas/authorization.py#L24-L30)