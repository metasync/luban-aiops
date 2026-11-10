Based on my analysis of the codebase, I can now update the documentation to reflect the addition of the `agent_role` field. Here's the updated documentation:

# Audit Event Model

<cite>
**Referenced Files in This Document**
- [audit-event.schema.json](file://shared/shared-contracts/schemas/audit-event.schema.json)
- [audit.py](file://products/audit-service/src/audit_service/schemas/audit.py)
- [audit_store.py](file://products/audit-service/src/audit_service/services/audit_store.py)
- [SPEC-013 spec.md](file://docs/specs/SPEC-013-durable-audit-trail/spec.md)
- [SPEC-037 spec.md](file://docs/specs/SPEC-037-signed-execution-requests/spec.md)
- [SPEC-075 spec.md](file://docs/specs/SPEC-075-multi-agent-audit-attribution/spec.md)
- [tool-gateway audit_emitter.py](file://products/tool-gateway/src/tool_gateway/services/audit_emitter.py)
- [platform-gateway audit_emitter.py](file://products/platform-gateway/src/platform_gateway/services/audit_emitter.py)
- [agent-service audit_emitter.py](file://products/agent-platform/src/agent_service/services/audit_emitter.py)
- [test_chat_confirm.py](file://products/platform-gateway/tests/test_chat_confirm.py)
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [agent_role.py](file://products/agent-platform/src/agent_service/services/agent_role.py)
</cite>

## Update Summary
**Changes Made**
- Added documentation for the new `agent_role` field supporting multi-agent attribution
- Updated the Core Components section to include the `agent_role` field and its constraints
- Enhanced the Architecture Overview to explain the multi-agent attribution dimension
- Added new section covering the agent-role vocabulary and its relationship to SPEC-075
- Updated examples and validation rules to reflect the byte-identical behavior for single-agent workflows

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Multi-Agent Attribution](#multi-agent-attribution)
7. [Dependency Analysis](#dependency-analysis)
8. [Performance Considerations](#performance-considerations)
9. [Troubleshooting Guide](#troubleshooting-guide)
10. [Conclusion](#conclusion)

## Introduction
This document defines the platform-wide audit event data model used to record activities for compliance and debugging. The canonical envelope is defined by a shared JSON schema and enforced by Pydantic models in the audit service. Emitter services (tool-gateway, platform-gateway, identity-broker, agent-service, skills-hub, incident-service) create events using a consistent builder, then deliver them asynchronously to the audit service, which persists and exposes them via a query API.

The model supports correlation across sessions, requests, approvals, tool executions, and incidents through well-defined fields and per-event-type details payloads. **Updated**: The model now includes an optional `agent_role` field that provides multi-agent attribution while maintaining byte-identical behavior for single-agent workflows.

## Project Structure
Audit-related code spans three layers:
- Shared contract: the authoritative JSON schema that all emitters and consumers bind to.
- Emitters: one per product, building envelopes and delivering them over HTTP without blocking the user path.
- Audit service: validates, stores, and serves audit events with retention and query filters.

```mermaid
graph TB
subgraph "Emitters"
TG["tool-gateway<br/>audit_emitter.py"]
PG["platform-gateway<br/>audit_emitter.py"]
AS["agent-service<br/>audit_emitter.py"]
end
subgraph "Shared Contract"
SCHEMA["audit-event.schema.json"]
end
subgraph "Audit Service"
MODEL["schemas/audit.py"]
STORE["services/audit_store.py"]
end
TG --> |HTTP POST /api/v1/audit/events| STORE
PG --> |HTTP POST /api/v1/audit/events| STORE
AS --> |HTTP POST /api/v1/audit/events| STORE
SCHEMA --> MODEL
SCHEMA --> TG
SCHEMA --> PG
SCHEMA --> AS
```

**Diagram sources**
- [audit-event.schema.json:1-106](file://shared/shared-contracts/schemas/audit-event.schema.json#L1-L106)
- [audit.py:1-118](file://products/audit-service/src/audit_service/schemas/audit.py#L1-L118)
- [audit_store.py:228-278](file://products/audit-service/src/audit_service/services/audit_store.py#L228-L278)
- [tool-gateway audit_emitter.py:1-98](file://products/tool-gateway/src/tool_gateway/services/audit_emitter.py#L1-L98)
- [platform-gateway audit_emitter.py:1-99](file://products/platform-gateway/src/platform_gateway/services/audit_emitter.py#L1-L99)
- [agent-service audit_emitter.py:1-106](file://products/agent-platform/src/agent_service/services/audit_emitter.py#L1-L106)

**Section sources**
- [SPEC-013 spec.md:30-73](file://docs/specs/SPEC-013-durable-audit-trail/spec.md#L30-L73)

## Core Components
The audit event envelope has the following fields:

- event_id: Unique identifier minted by the emitter; correlates stored records with structured logs.
- occurred_at: UTC timestamp when the audited action happened (RFC 3339).
- event_type: Closed vocabulary describing the kind of activity. Includes tool_invoked, policy_decision, token_exchange, session_created, session_deleted, chat_started, chat_completed, confirmation_decided, incident_triaged, skill_searched, skill_retrieved, skills_synced, execution_requested, execution_completed, execution_rejected, document_created, document_published, document_read, skill_draft_generated, incident_skill_draft_generated, skill_graduated, secret_delivered, target_authorization.
- service: Emitting service name (e.g., tool-gateway, platform-gateway, identity-service).
- request_id: Correlation ID for the originating request.
- subject: Token subject (sub) of the user attributed to the event, when applicable.
- username: Human-readable username, when applicable.
- actor: Delegation actor (act.sub), i.e., the service acting on behalf of the user, when applicable.
- delegation_mode: Verified acquisition mode (user_delegated, acting_service, none), omitted for legacy events.
- **agent_role**: Which agent role acted (diagnostician, orchestrator, executor), drawn from the closed SPEC-073 vocabulary. Omitted when absent (no deployed caller binds a role until phase 5); absence is not an assertion. A descriptive attribution dimension beside delegation_mode and subject/username — it narrows no authority (the prescriptive axis is SPEC-074) and never becomes a new principal, claim, or identity edge.
- roles: Roles of the attributed identity at event time, when applicable.
- session_id: Agent session identifier, when the event belongs to a session.
- outcome: Result of the audited action; allowed values are allow, deny, success, error.
- details: Per-event-type payload object carrying additional context. Its shape varies by event_type.

Constraints and validation rules:
- Required fields: event_id, occurred_at, event_type, service, request_id, outcome.
- Additional properties are forbidden at the envelope level; only the listed fields may be present.
- event_type must be one of the enumerated values.
- outcome must be one of the enumerated values.
- delegation_mode must be one of the enumerated values when present.
- **agent_role must be one of the enumerated values (diagnostician, orchestrator, executor) when present.**
- Optional identity fields (subject, username, actor, roles, session_id, delegation_mode, agent_role) are omitted rather than nulled when absent to keep payloads valid against the schema.
- The audit service enforces these constraints via a Pydantic model configured to forbid extra fields and validate types/enums.

Data types:
- Strings for identifiers and names.
- DateTime for occurred_at.
- Array of strings for roles.
- Object for details.

Relationships to other platform concepts:
- Sessions: Many events carry session_id to group activity within a single agent session.
- Tool executions: tool_invoked events describe tool calls; execution_requested/completed/rejected events correlate approvals to actual tool runs.
- Approvals: confirmation_decided events capture human-in-the-loop decisions and link to tool_names and confirm_id.
- Incidents: incident_triaged and incident_skill_draft_generated events tie actions to incident contexts.
- **Multi-agent attribution**: agent_role provides provenance about which agent role performed the action, completing the attribution triple alongside subject/username (on whose behalf) and delegation_mode (under which delegation).

**Section sources**
- [audit-event.schema.json:7-106](file://shared/shared-contracts/schemas/audit-event.schema.json#L7-L106)
- [audit.py:14-118](file://products/audit-service/src/audit_service/schemas/audit.py#L14-L118)
- [audit_store.py:263-341](file://products/audit-service/src/audit_service/services/audit_store.py#L263-L341)

## Architecture Overview
Emission flow:
1. A platform service performs an auditable action.
2. It builds an audit event using its product-specific emitter helper, which sets event_id, occurred_at, service, request_id, outcome, and optional identity/session fields including the optional agent_role.
3. The emitter delivers the event asynchronously over HTTP to the audit service's ingest endpoint. Delivery is fire-and-forget with a short timeout; failures do not block or fail the originating request.
4. The audit service validates the envelope against the shared schema and Pydantic model, persists it, and exposes it via a query API.

```mermaid
sequenceDiagram
participant App as "Platform Service"
participant Emitter as "Product Audit Emitter"
participant Audit as "Audit Service Ingest"
participant Store as "Audit Store"
App->>Emitter : build_audit_event(...)
Emitter-->>App : event dict
Emitter->>Audit : POST /api/v1/audit/events {events : [event]}
Audit->>Store : persist(event)
Store-->>Audit : ok
Audit-->>Emitter : 2xx
Emitter-->>App : non-blocking completion
```

**Diagram sources**
- [tool-gateway audit_emitter.py:29-98](file://products/tool-gateway/src/tool_gateway/services/audit_emitter.py#L29-L98)
- [platform-gateway audit_emitter.py:30-99](file://products/platform-gateway/src/platform_gateway/services/audit_emitter.py#L30-L99)
- [agent-service audit_emitter.py:30-106](file://products/agent-platform/src/agent_service/services/audit_emitter.py#L30-L106)
- [audit_store.py:263-341](file://products/audit-service/src/audit_service/services/audit_store.py#L263-L341)

**Section sources**
- [SPEC-013 spec.md:52-62](file://docs/specs/SPEC-013-durable-audit-trail/spec.md#L52-L62)

## Detailed Component Analysis

### AuditEvent Schema and Enforcement
- The shared JSON schema defines the canonical envelope, required fields, allowed event_type and outcome values, and forbids additional properties.
- The audit service's Pydantic model mirrors the schema, adds strict configuration to forbid extra fields, and provides typed enums for event_type, outcome, and agent_role.
- Row mapping from storage to model ensures roles and details are normalized when read back.

```mermaid
classDiagram
class AuditEvent {
+string event_id
+datetime occurred_at
+EventType event_type
+string service
+string request_id
+string subject
+string username
+string actor
+string[] roles
+string session_id
+Outcome outcome
+DelegationMode delegation_mode
+AgentRole agent_role
+dict details
}
class EventType {
<<enum>>
"tool_invoked"
"policy_decision"
"token_exchange"
"session_created"
"session_deleted"
"chat_started"
"chat_completed"
"confirmation_decided"
"incident_triaged"
"skill_searched"
"skill_retrieved"
"skills_synced"
"execution_requested"
"execution_completed"
"execution_rejected"
"document_created"
"document_published"
"document_read"
"skill_draft_generated"
"incident_skill_draft_generated"
"skill_graduated"
"secret_delivered"
"target_authorization"
}
class Outcome {
<<enum>>
"allow"
"deny"
"success"
"error"
}
class DelegationMode {
<<enum>>
"user_delegated"
"acting_service"
"none"
}
class AgentRole {
<<enum>>
"diagnostician"
"orchestrator"
"executor"
}
AuditEvent --> EventType : "uses"
AuditEvent --> Outcome : "uses"
AuditEvent --> DelegationMode : "uses"
AuditEvent --> AgentRole : "uses"
```

**Diagram sources**
- [audit-event.schema.json:15-106](file://shared/shared-contracts/schemas/audit-event.schema.json#L15-L106)
- [audit.py:14-118](file://products/audit-service/src/audit_service/schemas/audit.py#L14-L118)

**Section sources**
- [audit-event.schema.json:1-106](file://shared/shared-contracts/schemas/audit-event.schema.json#L1-L106)
- [audit.py:1-118](file://products/audit-service/src/audit_service/schemas/audit.py#L1-L118)
- [audit_store.py:263-341](file://products/audit-service/src/audit_service/services/audit_store.py#L263-L341)

### Emitter Pattern Across Services
Each product implements an identical emitter pattern:
- build_audit_event constructs the envelope, setting required fields and conditionally adding identity/session fields including agent_role only when present.
- emit_audit_event sends the event asynchronously on a daemon thread with a bounded timeout; if the audit service URL is unset, emission is a no-op to preserve log-only behavior.
- _deliver posts to /api/v1/audit/events with service credentials; errors are logged and counted but never propagated to the caller.

```mermaid
flowchart TD
Start(["Build Event"]) --> SetRequired["Set event_id, occurred_at,<br/>event_type, service, request_id,<br/>outcome, details"]
SetRequired --> AddOptional{"Identity/session fields present?"}
AddOptional --> |Yes| AttachFields["Attach subject, username,<br/>actor, roles, session_id,<br/>delegation_mode, agent_role"]
AddOptional --> |No| SkipFields["Omit optional fields"]
AttachFields --> Deliver["POST /api/v1/audit/events<br/>fire-and-forget"]
SkipFields --> Deliver
Deliver --> Success{"2xx response?"}
Success --> |Yes| RecordOK["Record metric 'ok'"]
Success --> |No| RecordErr["Record metric 'error'<br/>log warning"]
```

**Diagram sources**
- [tool-gateway audit_emitter.py:29-98](file://products/tool-gateway/src/tool_gateway/services/audit_emitter.py#L29-L98)
- [platform-gateway audit_emitter.py:30-99](file://products/platform-gateway/src/platform_gateway/services/audit_emitter.py#L30-L99)
- [agent-service audit_emitter.py:30-106](file://products/agent-platform/src/agent_service/services/audit_emitter.py#L30-L106)

**Section sources**
- [tool-gateway audit_emitter.py:1-98](file://products/tool-gateway/src/tool_gateway/services/audit_emitter.py#L1-L98)
- [platform-gateway audit_emitter.py:1-99](file://products/platform-gateway/src/platform_gateway/services/audit_emitter.py#L1-L99)
- [agent-service audit_emitter.py:1-106](file://products/agent-platform/src/agent_service/services/audit_emitter.py#L1-L106)

### Event Types and Examples

#### confirmation_decided
Purpose: Records a human-in-the-loop decision on a pending confirmation card.
Key fields:
- event_type: confirmation_decided
- outcome: allow or deny based on the decision
- session_id: links to the session where the confirmation was raised
- details: includes confirm_id, decision, tool_names, and approval metadata when applicable

Example scenario:
- An operator approves or denies a browser write batch. The platform gateway emits confirmation_decided with allow/deny and attaches tool_names such as web.click, web.type, etc.

Validation notes:
- outcome must match the decision semantics.
- details must include confirm_id and decision; tool_names reflect the tools involved in the batch.

**Section sources**
- [test_chat_confirm.py:374-403](file://products/platform-gateway/tests/test_chat_confirm.py#L374-L403)
- [audit-event.schema.json:25-50](file://shared/shared-contracts/schemas/audit-event.schema.json#L25-L50)

#### execution_requested
Purpose: Captures the initiation of a signed execution after approval.
Key fields:
- event_type: execution_requested
- details: includes confirm_id, execution_id, call_id, tool_name, args_digest, decider_user_id, owner_user_id
- request_id: forwarded correlation ID

Example scenario:
- After a confirmation is approved, the runtime prepares and persists a signed execution request and emits execution_requested before invoking the tool.

**Section sources**
- [SPEC-037 spec.md:130-139](file://docs/specs/SPEC-037-signed-execution-requests/spec.md#L130-L139)
- [audit-event.schema.json:86-90](file://shared/shared-contracts/schemas/audit-event.schema.json#L86-L90)

#### execution_completed
Purpose: Records the final status of an execution attempt.
Key fields:
- event_type: execution_completed
- details: includes confirm_id, execution_id, call_id, tool_name, status (succeeded/failed/timeout), duration_ms, request_id
- outcome: success or error based on status

Example scenario:
- After a tool invocation completes, the runtime emits execution_completed with the result and timing information.

**Section sources**
- [runtime_kernel.py:1881-1905](file://products/agent-platform/src/agent_service/runtime_kernel.py#L1881-L1905)
- [SPEC-037 spec.md:130-139](file://docs/specs/SPEC-037-signed-execution-requests/spec.md#L130-L139)

#### execution_rejected
Purpose: Records cases where an execution could not proceed (e.g., signing unavailable, argument digest mismatch, missing request).
Key fields:
- event_type: execution_rejected
- details: includes confirm_id, call_id, tool_name, reason

Example scenario:
- If the execution request cannot be validated or signed, the system emits execution_rejected with a reason.

**Section sources**
- [SPEC-037 spec.md:130-139](file://docs/specs/SPEC-037-signed-execution-requests/spec.md#L130-L139)
- [audit-event.schema.json:86-90](file://shared/shared-contracts/schemas/audit-event.schema.json#L86-L90)

### Relationships to Platform Concepts
- Sessions: Events like session_created, chat_started, chat_completed, and many others carry session_id to associate activity with a specific session.
- Tool executions: tool_invoked events describe individual tool calls; execution_requested/completed/rejected events bridge approvals to concrete tool invocations.
- Approvals: confirmation_decided events capture who decided what and which tools were affected.
- Incidents: incident_triaged and incident_skill_draft_generated events tie operations to incident contexts and reports.

**Section sources**
- [audit-event.schema.json:25-50](file://shared/shared-contracts/schemas/audit-event.schema.json#L25-L50)
- [SPEC-037 spec.md:110-139](file://docs/specs/SPEC-037-signed-execution-requests/spec.md#L110-L139)

## Multi-Agent Attribution

### Agent Role Vocabulary
The audit event model now includes an optional `agent_role` field that provides multi-agent attribution capabilities. This field uses a closed vocabulary of three values:

- **diagnostician**: An agent focused on diagnosis and analysis tasks
- **orchestrator**: An agent responsible for coordination and planning  
- **executor**: An agent authorized to perform execution tasks

The agent-role vocabulary is defined in SPEC-073 and maintained in lockstep across the platform's identity, policy, and audit systems.

### Byte-Identical Behavior
**Critical Design Principle**: The `agent_role` field is designed to maintain byte-identical behavior for single-agent workflows. When no agent role is bound (which is the case for all currently deployed paths), the field is completely omitted from the serialized event payload rather than being set to null. This ensures backward compatibility and preserves existing audit trails unchanged.

The serialization logic automatically removes the `agent_role` field when it is `None`, mirroring the behavior of the `delegation_mode` field.

### Attribution Triple
The `agent_role` field completes the platform's attribution model, providing the third dimension alongside existing fields:

- **Which role acted**: `agent_role` (new)
- **On whose behalf**: `subject`/`username` (existing)
- **Under which delegation**: `delegation_mode` (existing)

This attribution triple enables comprehensive tracking of multi-agent scenarios while maintaining the simplicity of single-agent workflows.

### Query and Filtering Support
The audit service supports filtering by `agent_role` through the query API:

- `GET /api/v1/audit/events?agent_role=diagnostician` - Filter events by diagnostician role
- `GET /api/v1/audit/events?agent_role=orchestrator` - Filter events by orchestrator role  
- `GET /api/v1/audit/events?agent_role=executor` - Filter events by executor role

Invalid agent_role values are rejected at the boundary, ensuring data integrity.

### Storage and Indexing
The audit store includes dedicated infrastructure for the `agent_role` field:

- Database column: `agent_role TEXT` with appropriate indexing
- Index: `idx_audit_agent_role` for efficient filtering
- Migration-safe: Uses `ADD COLUMN IF NOT EXISTS` for safe deployment

**Section sources**
- [audit-event.schema.json:79-83](file://shared/shared-contracts/schemas/audit-event.schema.json#L79-L83)
- [audit.py:54-58](file://products/audit-service/src/audit_service/schemas/audit.py#L54-L58)
- [audit.py:77-91](file://products/audit-service/src/audit_service/schemas/audit.py#L77-L91)
- [audit_store.py:246-248](file://products/audit-service/src/audit_service/services/audit_store.py#L246-L248)
- [agent_role.py:30-50](file://products/agent-platform/src/agent_service/services/agent_role.py#L30-L50)
- [SPEC-075 spec.md:63-86](file://docs/specs/SPEC-075-multi-agent-audit-attribution/spec.md#L63-L86)

## Dependency Analysis
- Emitter modules depend on shared schema conventions and product metadata (SERVICE_NAME) to set service fields consistently.
- The audit service depends on the shared schema for validation and on a store backend for persistence.
- Query filters rely on stored columns matching the envelope fields.
- **Multi-agent attribution dependencies**: The agent-role vocabulary is shared between the agent-platform (identity layer), policy-center (authorization layer), and audit-service (attribution layer), maintaining consistency across the platform.

```mermaid
graph LR
TG["tool-gateway audit_emitter.py"] --> |HTTP| AUD["audit-service ingest"]
PG["platform-gateway audit_emitter.py"] --> |HTTP| AUD
AS["agent-service audit_emitter.py"] --> |HTTP| AUD
AUD --> ST["audit_store.py"]
ST --> DB["PostgreSQL (deployed)"]
AR["agent_role.py"] --> AS
```

**Diagram sources**
- [tool-gateway audit_emitter.py:67-98](file://products/tool-gateway/src/tool_gateway/services/audit_emitter.py#L67-L98)
- [platform-gateway audit_emitter.py:68-99](file://products/platform-gateway/src/platform_gateway/services/audit_emitter.py#L68-L99)
- [agent-service audit_emitter.py:68-106](file://products/agent-platform/src/agent_service/services/audit_emitter.py#L68-L106)
- [audit_store.py:263-341](file://products/audit-service/src/audit_service/services/audit_store.py#L263-L341)
- [agent_role.py:30-119](file://products/agent-platform/src/agent_service/services/agent_role.py#L30-L119)

**Section sources**
- [SPEC-013 spec.md:41-73](file://docs/specs/SPEC-013-durable-audit-trail/spec.md#L41-L73)

## Performance Considerations
- Emission is fire-and-forget with a short timeout; audit service unreachability degrades to local logging and metrics without impacting user-facing latency.
- The audit service should use efficient indexing on frequently filtered columns (username, session_id, request_id, event_type, service, occurred_at, agent_role, delegation_mode) to support portal queries and pagination.
- Retention policies prevent unbounded growth; ensure eviction runs periodically and does not block ingest.
- **Multi-agent attribution performance**: The `agent_role` field is indexed separately (`idx_audit_agent_role`) to support efficient filtering without impacting existing query performance.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and checks:
- Missing events: Verify *_AUDIT_SERVICE_URL is configured in the emitting service; if unset, emission is intentionally a no-op.
- Rejected ingestion: Check HTTP status codes returned by the audit service; 4xx indicates malformed or unauthorized requests.
- Authentication failures: Ensure service credentials are correctly configured for audit ingest.
- Storage errors: Inspect audit service metrics and logs for store errors; Postgres connectivity issues will surface as ingest failures.
- Query limitations: Confirm filter parameters match stored field names and value formats.
- **Agent role issues**: 
  - Invalid agent_role values are rejected at the query boundary
  - The field is omitted (not null) when no role is bound
  - Current deployments have no active agent roles (byte-identical behavior)

**Section sources**
- [tool-gateway audit_emitter.py:67-98](file://products/tool-gateway/src/tool_gateway/services/audit_emitter.py#L67-L98)
- [platform-gateway audit_emitter.py:68-99](file://products/platform-gateway/src/platform_gateway/services/audit_emitter.py#L68-L99)
- [agent-service audit_emitter.py:68-106](file://products/agent-platform/src/agent_service/services/audit_emitter.py#L68-L106)
- [SPEC-013 spec.md:52-73](file://docs/specs/SPEC-013-durable-audit-trail/spec.md#L52-L73)

## Conclusion
The audit event model provides a stable, cross-service contract for recording platform activities. By enforcing a shared schema, consistent emitter patterns, and durable storage, the platform enables reliable compliance reporting, debugging, and operational visibility. Maintaining consistent schemas across services ensures that events remain queryable, correlatable, and actionable across sessions, approvals, tool executions, and incidents.

**Updated**: The addition of the `agent_role` field enhances the platform's ability to attribute actions to specific agent roles while maintaining complete backward compatibility. This enables future multi-agent orchestration scenarios while preserving the simplicity and reliability of current single-agent workflows. The byte-identical design ensures that existing audit trails remain unchanged, and the closed vocabulary approach prevents arbitrary role assignments while enabling controlled expansion as the platform evolves.