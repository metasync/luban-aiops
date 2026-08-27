# API Reference

<cite>
**Referenced Files in This Document**
- [README.md](file://README.md)
- [agent-platform/README.md](file://products/agent-platform/README.md)
- [identity-broker/README.md](file://products/identity-broker/README.md)
- [tool-gateway/README.md](file://products/tool-gateway/README.md)
- [audit-service/README.md](file://products/audit-service/README.md)
- [platform-gateway/src/platform_gateway/api/routes/policy.py](file://products/platform-gateway/src/platform_gateway/api/routes/policy.py)
- [platform-gateway/src/platform_gateway/api/routes/tools.py](file://products/platform-gateway/src/platform_gateway/api/routes/tools.py)
- [platform-gateway/src/platform_gateway/api/routes/skills.py](file://products/platform-gateway/src/platform_gateway/api/routes/skills.py)
- [platform-gateway/src/platform_gateway/api/routes/documents.py](file://products/platform-gateway/src/platform_gateway/api/routes/documents.py)
- [platform-gateway/src/platform_gateway/services/policy_engine.py](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py)
- [platform-gateway/src/platform_gateway/services/policy_matrix.py](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py)
- [platform-gateway/src/platform_gateway/services/tool_gateway_client.py](file://products/platform-gateway/src/platform_gateway/services/tool_gateway_client.py)
- [platform-gateway/src/platform_gateway/services/gateway_service.py](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py)
- [platform-gateway/src/platform_gateway/schemas/api.py](file://products/platform-gateway/src/platform_gateway/schemas/api.py)
- [skills-hub/src/skills_hub/api/routes/skills.py](file://products/skills-hub/src/skills_hub/api/routes/skills.py)
- [tool-gateway/src/tool_gateway/tools/skills_connector.py](file://products/tool-gateway/src/tool_gateway/tools/skills_connector.py)
- [shared/shared-contracts/schemas/policy-matrix.schema.json](file://shared/shared-contracts/schemas/policy-matrix.schema.json)
- [agent-platform/src/agent_service/api/v2/routes.py](file://products/agent-platform/src/agent_service/api/v2/routes.py)
- [agent-platform/src/agent_service/schemas/v2.py](file://products/agent-platform/src/agent_service/schemas/v2.py)
- [agent-platform/src/agent_service/services/evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [agent-platform/src/agent_service/services/operation_documents.py](file://products/agent-platform/src/agent_service/services/operation_documents.py)
- [identity-broker/src/identity_service/api/routes/auth.py](file://products/identity-broker/src/identity_service/api/routes/auth.py)
- [identity-broker/src/identity_service/api/routes/identity.py](file://products/identity-broker/src/identity_service/api/routes/identity.py)
- [identity-broker/src/identity_service/schemas/auth.py](file://products/identity-broker/src/identity_service/schemas/auth.py)
- [identity-broker/src/identity_service/schemas/identity.py](file://products/identity-broker/src/identity_service/schemas/identity.py)
- [tool-gateway/src/api_gateway/api/routes/chat.py](file://products/tool-gateway/src/api_gateway/api/routes/chat.py)
- [tool-gateway/src/api_gateway/api/routes/runtime.py](file://products/tool-gateway/src/api_gateway/api/routes/runtime.py)
- [tool-gateway/src/api_gateway/api/routes/sessions.py](file://products/tool-gateway/src/api_gateway/api/routes/sessions.py)
- [tool-gateway/src/api_gateway/api/routes/tools.py](file://products/tool-gateway/src/api_gateway/api/routes/tools.py)
- [tool-gateway/src/api_gateway/api/routes/auth.py](file://products/tool-gateway/src/api_gateway/api/routes/auth.py)
- [tool-gateway/src/api_gateway/schemas/api.py](file://products/tool-gateway/src/api_gateway/schemas/api.py)
- [platform-gateway/src/platform_gateway/api/routes/audit.py](file://products/platform-gateway/src/platform_gateway/api/routes/audit.py)
- [audit-service/src/audit_service/api/router.py](file://products/audit-service/src/audit_service/api/router.py)
- [audit-service/src/audit_service/api/routes/ingest.py](file://products/audit-service/src/audit_service/api/routes/ingest.py)
- [audit-service/src/audit_service/api/routes/query.py](file://products/audit-service/src/audit_service/api/routes/query.py)
- [audit-service/src/audit_service/api/routes/health.py](file://products/audit-service/src/audit_service/api/routes/health.py)
- [audit-service/src/audit_service/core/metrics.py](file://products/audit-service/src/audit_service/core/metrics.py)
- [audit-service/src/audit_service/schemas/audit.py](file://products/audit-service/src/audit_service/schemas/audit.py)
- [shared-contracts/schemas/chat-request.schema.json](file://shared-contracts/schemas/chat-request.schema.json)
- [shared-contracts/schemas/chat-response.schema.json](file://shared-contracts/schemas/chat-response.schema.json)
- [shared-contracts/schemas/agent-chat-request.schema.json](file://shared-contracts/schemas/agent-chat-request.schema.json)
- [shared-contracts/schemas/agent-chat-response.schema.json](file://shared-contracts/schemas/agent-chat-response.schema.json)
- [shared-contracts/schemas/stream-event.schema.json](file://shared-contracts/schemas/stream-event.schema.json)
- [shared-contracts/schemas/agent-stream-event.schema.json](file://shared-contracts/schemas/agent-stream-event.schema.json)
- [shared-contracts/schemas/session.schema.json](file://shared-contracts/schemas/session.schema.json)
- [shared-contracts/schemas/agent-session.schema.json](file://shared-contracts/schemas/agent-session.schema.json)
- [shared/shared-contracts/schemas/session-evidence.schema.json](file://shared/shared-contracts/schemas/session-evidence.schema.json)
- [shared-contracts/schemas/identity-token.schema.json](file://shared-contracts/schemas/identity-token.schema.json)
- [shared-contracts/schemas/identity-context.schema.json](file://shared-contracts/schemas/identity-context.schema.json)
- [shared-contracts/schemas/tool-invocation.schema.json](file://shared-contracts/schemas/tool-invocation.schema.json)
- [shared-contracts/schemas/tool-result.schema.json](file://shared-contracts/schemas/tool-result.schema.json)
- [shared-contracts/schemas/policy-decision.schema.json](file://shared-contracts/schemas/policy-decision.schema.json)
- [shared-contracts/schemas/policy-rule.schema.json](file://shared-contracts/schemas/policy-rule.schema.json)
- [shared-contracts/schemas/health-response.schema.json](file://shared-contracts/schemas/health-response.schema.json)
- [shared-contracts/schemas/agent-health.schema.json](file://shared-contracts/schemas/agent-health.schema.json)
- [shared-contracts/schemas/agent-runtime-metadata.schema.json](file://shared-contracts/schemas/agent-runtime-metadata.schema.json)
- [shared-contracts/schemas/audit-event.schema.json](file://shared-contracts/schemas/audit-event.schema.json)
</cite>

## Update Summary
**Changes Made**
- Added comprehensive documentation for new operations document repository endpoints (SPEC-039)
- Updated Agent Platform v2 API section with complete document management CRUD operations
- Added session rename endpoint documentation with proper authorization and validation
- Enhanced platform gateway integration for document operations with audit logging
- Added detailed schemas for document creation, listing, publishing, and deletion
- Updated architecture diagrams to reflect document repository integration

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
This document provides a comprehensive API reference for the Luban AIOps Platform, covering REST endpoints for agent interactions, identity management, audit trail management, platform administration, workspace transparency, evidence persistence, and **operations document management**, as well as WebSocket APIs for real-time streaming and long-running operations. It includes HTTP methods, URL patterns, request/response schemas, authentication requirements, error codes, retry strategies, client examples, versioning and deprecation policies, migration guidance, testing strategies, and debugging techniques.

The platform exposes:
- Agent Platform REST APIs (v2) for chat, sessions, runtime metadata, health, **evidence persistence**, and **operations document management**.
- Identity Broker REST APIs for authentication, token issuance, and identity context.
- Tool Gateway REST APIs for chat orchestration, session lifecycle, tool invocation, runtime configuration, and policy enforcement.
- **Platform Gateway REST APIs for workspace transparency including permission matrix, tools catalog, skills inventory, and operations document proxying.**
- Audit Service REST APIs for durable audit trail ingestion, querying, and monitoring.
- Shared JSON Schemas defining contracts across components.

[No sources needed since this section doesn't analyze specific files]

## Project Structure
At a high level, the API surface is implemented across five services:
- Agent Platform: v2 REST endpoints for agent chat, sessions, runtime metadata, health, **evidence persistence**, and **operations document repository**.
- Identity Broker: Authentication, token issuance, and identity context endpoints.
- Tool Gateway: Orchestration layer that enforces policies, manages sessions, invokes tools, and proxies to agents.
- **Platform Gateway: Transparency and discovery layer providing permission matrix, tools catalog, skills inventory, and operations document proxying with proper authorization.**
- Audit Service: Durable audit trail storage with ingestion, querying, and monitoring capabilities.

```mermaid
graph TB
Client["Client"] --> Gateway["Tool Gateway"]
Gateway --> Auth["Identity Broker"]
Gateway --> Agent["Agent Platform"]
Gateway --> Tools["Tool Registry / K8s Connector"]
Gateway --> Policy["Policy Engine"]
Gateway --> Store["Session Store"]
Portal["Operator Portal"] --> PlatformGW["Platform Gateway"]
PlatformGW --> PolicyMatrix["Permission Matrix"]
PlatformGW --> ToolsCatalog["Tools Catalog"]
PlatformGW --> SkillsInventory["Skills Inventory"]
PlatformGW --> Documents["Operations Documents"]
PlatformGW --> AuditService["Audit Service"]
PlatformGW --> ToolGateway["Tool Gateway"]
Agent --> EvidenceStore["Evidence Store"]
Agent --> DocStore["Operation Document Store"]
```

**Diagram sources**
- [platform-gateway/src/platform_gateway/api/routes/policy.py](file://products/platform-gateway/src/platform_gateway/api/routes/policy.py)
- [platform-gateway/src/platform_gateway/api/routes/tools.py](file://products/platform-gateway/src/platform_gateway/api/routes/tools.py)
- [platform-gateway/src/platform_gateway/api/routes/skills.py](file://products/platform-gateway/src/platform_gateway/api/routes/skills.py)
- [platform-gateway/src/platform_gateway/api/routes/documents.py](file://products/platform-gateway/src/platform_gateway/api/routes/documents.py)
- [platform-gateway/src/platform_gateway/services/tool_gateway_client.py](file://products/platform-gateway/src/platform_gateway/services/tool_gateway_client.py)
- [agent-platform/src/agent_service/services/evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [agent-platform/src/agent_service/services/operation_documents.py](file://products/agent-platform/src/agent_service/services/operation_documents.py)

**Section sources**
- [README.md](file://README.md)
- [agent-platform/README.md](file://products/agent-platform/README.md)
- [identity-broker/README.md](file://products/identity-broker/README.md)
- [tool-gateway/README.md](file://products/tool-gateway/README.md)
- [audit-service/README.md](file://products/audit-service/README.md)

## Core Components
- Agent Platform (v2): Provides chat, session, runtime metadata, health, **evidence persistence**, and **operations document repository** endpoints with typed schemas.
- Identity Broker: Issues tokens and resolves identity contexts; used by clients and gateway for authorization.
- Tool Gateway: Central entrypoint for clients; enforces policies, manages sessions, invokes tools, and streams results.
- **Platform Gateway: Workspace transparency service providing permission matrix, tools catalog, skills inventory, and operations document proxying with role-based scoping and authorization.**
- Audit Service: Durable audit trail service providing ingestion, querying, and monitoring capabilities with PostgreSQL backend support.

Key responsibilities:
- Authentication and token handling via Identity Broker.
- Chat orchestration and streaming via Tool Gateway and Agent Platform.
- Session persistence and lifecycle management.
- Tool invocation through a registry and connectors.
- **Workspace transparency with live permission matrix, tools discovery, skills inventory access, and operations document management.**
- **Evidence persistence with bounded storage, truncation markers, and session budget enforcement.**
- **Operations document repository with draft/published states, owner-only visibility, and team-wide sharing.**
- Durable audit trail storage with filtering, pagination, and retention policies.

**Section sources**
- [agent-platform/src/agent_service/api/v2/routes.py](file://products/agent-platform/src/agent_service/api/v2/routes.py)
- [agent-platform/src/agent_service/schemas/v2.py](file://products/agent-platform/src/agent_service/schemas/v2.py)
- [agent-platform/src/agent_service/services/evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [agent-platform/src/agent_service/services/operation_documents.py](file://products/agent-platform/src/agent_service/services/operation_documents.py)
- [identity-broker/src/identity_service/api/routes/auth.py](file://products/identity-broker/src/identity_service/api/routes/auth.py)
- [identity-broker/src/identity_service/api/routes/identity.py](file://products/identity-broker/src/identity_service/api/routes/identity.py)
- [tool-gateway/src/api_gateway/api/routes/chat.py](file://products/tool-gateway/src/api_gateway/api/routes/chat.py)
- [tool-gateway/src/api_gateway/api/routes/sessions.py](file://products/tool-gateway/src/api_gateway/api/routes/sessions.py)
- [tool-gateway/src/api_gateway/api/routes/tools.py](file://products/tool-gateway/src/api_gateway/api/routes/tools.py)
- [tool-gateway/src/api_gateway/api/routes/runtime.py](file://products/tool-gateway/src/api_gateway/api/routes/runtime.py)
- [tool-gateway/src/api_gateway/api/routes/auth.py](file://products/tool-gateway/src/api_gateway/api/routes/auth.py)
- [platform-gateway/src/platform_gateway/api/routes/policy.py](file://products/platform-gateway/src/platform_gateway/api/routes/policy.py)
- [platform-gateway/src/platform_gateway/api/routes/tools.py](file://products/platform-gateway/src/platform_gateway/api/routes/tools.py)
- [platform-gateway/src/platform_gateway/api/routes/skills.py](file://products/platform-gateway/src/platform_gateway/api/routes/skills.py)
- [platform-gateway/src/platform_gateway/api/routes/documents.py](file://products/platform-gateway/src/platform_gateway/api/routes/documents.py)
- [audit-service/src/audit_service/api/routes/ingest.py](file://products/audit-service/src/audit_service/api/routes/ingest.py)
- [audit-service/src/audit_service/api/routes/query.py](file://products/audit-service/src/audit_service/api/routes/query.py)

## Architecture Overview
The Tool Gateway acts as the primary API boundary for client operations. The Platform Gateway provides workspace transparency endpoints for administrative and portal use. Clients authenticate against the Identity Broker, then interact with the appropriate gateway based on their needs. The Gateways enforce policies, persist sessions, delegate execution to the Agent Platform and tool connectors, **persist evidence frames for replay capability**, and **manage operations documents with draft/published states and owner-only visibility**.

```mermaid
sequenceDiagram
participant C as "Client"
participant PG as "Platform Gateway"
participant TG as "Tool Gateway"
participant I as "Identity Broker"
participant A as "Agent Platform"
participant ES as "Evidence Store"
participant DS as "Document Store"
participant T as "Tools"
participant P as "Policy Engine"
participant AS as "Audit Service"
Note over C,PG : Workspace Transparency
C->>PG : "GET /api/v1/policy/matrix"
PG->>P : "Evaluate policy : read"
P-->>PG : "Decision"
PG-->>C : "Permission matrix"
Note over C,A : Operations Document Management
C->>A : "POST /api/v2/documents (create)"
A->>DS : "Persist draft document"
A->>ES : "Load session evidence"
A-->>C : "Created document"
C->>A : "POST /api/v2/documents/{id}/publish"
A->>DS : "Publish document"
A-->>C : "Published document"
Note over C,TG : Client Operations
C->>I : "POST /auth/token"
I-->>C : "{token}"
C->>TG : "POST /chat (Authorization : Bearer {token})"
TG->>P : "Evaluate policy"
P-->>TG : "Decision"
TG->>A : "Forward chat request"
A->>ES : "Persist evidence frames"
A-->>TG : "Stream events"
TG-->>C : "Stream events"
```

**Diagram sources**
- [platform-gateway/src/platform_gateway/api/routes/policy.py](file://products/platform-gateway/src/platform_gateway/api/routes/policy.py)
- [platform-gateway/src/platform_gateway/api/routes/tools.py](file://products/platform-gateway/src/platform_gateway/api/routes/tools.py)
- [platform-gateway/src/platform_gateway/api/routes/skills.py](file://products/platform-gateway/src/platform_gateway/api/routes/skills.py)
- [platform-gateway/src/platform_gateway/api/routes/documents.py](file://products/platform-gateway/src/platform_gateway/api/routes/documents.py)
- [tool-gateway/src/api_gateway/api/routes/chat.py](file://products/tool-gateway/src/api_gateway/api/routes/chat.py)
- [identity-broker/src/identity_service/api/routes/auth.py](file://products/identity-broker/src/identity_service/api/routes/auth.py)
- [agent-platform/src/agent_service/services/evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [agent-platform/src/agent_service/services/operation_documents.py](file://products/agent-platform/src/agent_service/services/operation_documents.py)

## Detailed Component Analysis

### Platform Gateway REST API
**Updated** Workspace transparency and discovery endpoints with proper authorization and scoping, including operations document proxying.

- Permission Matrix
  - GET /api/v1/policy/matrix
  - Description: Retrieve the effective role × action authorization matrix derived from the loaded policy bundle.
  - Authentication: User bearer token with `policy:read` permission.
  - Response schema: See policy-matrix schema with version, source, scope, roles, actions, and matrix fields.
  - Scoping: `platform-admin` receives full matrix; other users receive only their granted roles.
  - Error codes: 200 OK, 401 Unauthorized, 403 Forbidden, 503 Service Unavailable (policy bundle unavailable).

- Tools Catalog
  - GET /api/v1/tools
  - Description: Discover registered tools in the current workspace with read-only access.
  - Authentication: User bearer token with `tools:list` permission.
  - Authorization: Requires delegated token chain for operator authority.
  - Response schema: Array of tool definitions with name, description, category, and risk_level.
  - Error codes: 200 OK, 401 Unauthorized, 403 Forbidden, 503 Service Unavailable (delegated token unavailable or tool gateway not configured).

- Skills Inventory
  - GET /api/v1/skills
  - Description: Browse skills registered in the skills hub with filtering and pagination support.
  - Authentication: User bearer token with `skills:read` permission.
  - Query Parameters: offset (default: 0), limit (default: 100, max: 100), source (optional), tag (optional).
  - Response schema: Object with skills array, total count, offset, and limit.
  - Error codes: 200 OK, 400 Bad Request (invalid parameters), 401 Unauthorized, 403 Forbidden.

- Operations Documents Proxy
  - POST /api/v1/documents
  - Description: Create operations documents through the platform gateway with authorization enforcement.
  - Authentication: User bearer token with `documents:create` permission.
  - Request schema: DocumentCreateRequest with document_type, session_ids, label, include_prose.
  - Response schema: Created document with provenance and digest information.
  - Error codes: 201 Created, 400 Bad Request (validation errors), 401 Unauthorized, 403 Forbidden (insufficient permissions).

  - GET /api/v1/documents
  - Description: List operations documents with scope filtering (mine/published).
  - Authentication: User bearer token with `documents:read` permission.
  - Query Parameters: scope (default: "mine", options: "mine", "published").
  - Response schema: Object with documents array containing owner's drafts and published documents.
  - Error codes: 200 OK, 401 Unauthorized, 403 Forbidden.

  - GET /api/v1/documents/{document_id}
  - Description: Read a specific operations document with owner-only draft access.
  - Authentication: User bearer token with `documents:read` permission.
  - Path Parameters: document_id (required).
  - Response schema: Complete document with provenance, digest, and optional prose.
  - Error codes: 200 OK, 404 Not Found (unknown or foreign draft), 401 Unauthorized, 403 Forbidden.

  - POST /api/v1/documents/{document_id}/publish
  - Description: Publish one's own draft document (one-way operation).
  - Authentication: User bearer token with `documents:write` permission.
  - Path Parameters: document_id (required).
  - Response schema: Published document with timestamp and state change.
  - Error codes: 200 OK, 404 Not Found, 409 Conflict (already published), 401 Unauthorized, 403 Forbidden.

  - DELETE /api/v1/documents/{document_id}
  - Description: Delete one's own document (owner-only operation).
  - Authentication: User bearer token with `documents:delete` permission.
  - Path Parameters: document_id (required).
  - Response schema: Confirmation object with document_id and deleted flag.
  - Error codes: 200 OK, 404 Not Found, 401 Unauthorized, 403 Forbidden.

Security Model
- All endpoints enforce role-based authorization using the platform's policy engine.
- Protected actions: `policy:read`, `tools:list`, `skills:read`, `documents:create`, `documents:read`, `documents:write`, `documents:delete`.
- Request isolation maintained through x-request-id propagation.
- Delegated tokens used for downstream service communication where required.
- Foreign session coverage requires `approvals:list` capability marker.

Error Handling
- 401 Unauthorized for missing or invalid authentication.
- 403 Forbidden when user lacks required permissions.
- 400 Bad Request for invalid query parameters.
- 404 Not Found for unknown resources or foreign draft access attempts.
- 409 Conflict for duplicate operations (e.g., already published documents).
- 503 Service Unavailable for upstream service failures or missing configuration.
- 502 Bad Gateway for transport errors to downstream services.

Retry Strategy
- Implement exponential backoff for transient errors (429, 503).
- Use correlation IDs (x-request-id) for request tracing and debugging.
- Handle upstream service failures gracefully with appropriate error mapping.

**Section sources**
- [platform-gateway/src/platform_gateway/api/routes/policy.py](file://products/platform-gateway/src/platform_gateway/api/routes/policy.py)
- [platform-gateway/src/platform_gateway/api/routes/tools.py](file://products/platform-gateway/src/platform_gateway/api/routes/tools.py)
- [platform-gateway/src/platform_gateway/api/routes/skills.py](file://products/platform-gateway/src/platform_gateway/api/routes/skills.py)
- [platform-gateway/src/platform_gateway/api/routes/documents.py](file://products/platform-gateway/src/platform_gateway/api/routes/documents.py)
- [platform-gateway/src/platform_gateway/services/policy_engine.py](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py)
- [platform-gateway/src/platform_gateway/services/policy_matrix.py](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py)
- [platform-gateway/src/platform_gateway/services/tool_gateway_client.py](file://products/platform-gateway/src/platform_gateway/services/tool_gateway_client.py)
- [platform-gateway/src/platform_gateway/services/gateway_service.py](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py)
- [shared/shared-contracts/schemas/policy-matrix.schema.json](file://shared/shared-contracts/schemas/policy-matrix.schema.json)

### Tool Gateway REST API
Primary endpoints for chat, sessions, tools, runtime, and auth proxying.

- Chat
  - POST /api/v1/chat
  - Description: Start or continue a chat conversation; supports streaming responses.
  - Authentication: Bearer token from Identity Broker.
  - Request schema: See shared chat-request schema.
  - Response schema: See shared chat-response schema; streaming uses stream-event schema.
  - Error codes: Standard HTTP status codes plus domain-specific errors (e.g., policy denied).

- Sessions
  - GET /api/v1/sessions/{session_id}
  - PUT /api/v1/sessions/{session_id}
  - DELETE /api/v1/sessions/{session_id}
  - PATCH /api/v1/sessions/{session_id}/title
  - Description: Manage session state and lifecycle, including title updates.
  - Authentication: Bearer token.
  - Request/response schemas: See session schema.

- Tools
  - POST /api/v1/tools/{tool_name}/invoke
  - Description: Invoke a registered tool with parameters.
  - Authentication: Bearer token.
  - Request/response schemas: See tool-invocation and tool-result schemas.

- Runtime
  - GET /api/v1/runtime/config
  - Description: Retrieve runtime configuration settings.
  - Authentication: Bearer token.
  - Response schema: Configuration object defined by service.

- Auth Proxy
  - POST /api/v1/auth/token
  - Description: Forward authentication requests to Identity Broker.
  - Request/response schemas: See identity-token schema.

Streaming and WebSockets
- WS /api/v1/ws/chat?session_id={id}
- Description: Real-time streaming of chat events and tool results.
- Events: Stream event payloads conform to stream-event schema.

Error Handling
- Common HTTP statuses: 200 OK, 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 409 Conflict, 422 Unprocessable Entity, 429 Too Many Requests, 500 Internal Server Error, 503 Service Unavailable.
- Domain errors: Policy decision failures, tool invocation errors, session conflicts.

Retry Strategy
- Exponential backoff with jitter for transient errors (429, 503).
- Idempotent retries for GET and safe operations; avoid re-sending non-idempotent writes without correlation IDs.
- Use correlation IDs from responses to correlate retries.

**Section sources**
- [tool-gateway/src/api_gateway/api/routes/chat.py](file://products/tool-gateway/src/api_gateway/api/routes/chat.py)
- [tool-gateway/src/api_gateway/api/routes/sessions.py](file://products/tool-gateway/src/api_gateway/api/routes/sessions.py)
- [tool-gateway/src/api_gateway/api/routes/tools.py](file://products/tool-gateway/src/api_gateway/api/routes/tools.py)
- [tool-gateway/src/api_gateway/api/routes/runtime.py](file://products/tool-gateway/src/api_gateway/api/routes/runtime.py)
- [tool-gateway/src/api_gateway/api/routes/auth.py](file://products/tool-gateway/src/api_gateway/api/routes/auth.py)
- [tool-gateway/src/api_gateway/schemas/api.py](file://products/tool-gateway/src/api_gateway/schemas/api.py)
- [shared-contracts/schemas/chat-request.schema.json](file://shared-contracts/schemas/chat-request.schema.json)
- [shared-contracts/schemas/chat-response.schema.json](file://shared-contracts/schemas/chat-response.schema.json)
- [shared-contracts/schemas/stream-event.schema.json](file://shared-contracts/schemas/stream-event.schema.json)
- [shared-contracts/schemas/session.schema.json](file://shared-contracts/schemas/session.schema.json)
- [shared-contracts/schemas/tool-invocation.schema.json](file://shared-contracts/schemas/tool-invocation.schema.json)
- [shared-contracts/schemas/tool-result.schema.json](file://shared-contracts/schemas/tool-result.schema.json)
- [shared-contracts/schemas/identity-token.schema.json](file://shared-contracts/schemas/identity-token.schema.json)

### Agent Platform REST API (v2)
Endpoints for agent chat, sessions, runtime metadata, health, **evidence persistence**, and **operations document repository**.

- Chat
  - POST /api/v2/chat
  - Description: Submit chat messages to an agent; supports streaming.
  - Authentication: Bearer token validated by gateway; direct calls may require token.
  - Request schema: See agent-chat-request schema.
  - Response schema: See agent-chat-response schema; streaming uses agent-stream-event schema.

- Sessions
  - GET /api/v2/sessions/{session_id}
  - PUT /api/v2/sessions/{session_id}
  - DELETE /api/v2/sessions/{session_id}
  - PATCH /api/v2/sessions/{session_id}/title
  - Description: Manage agent-side session state, including owner-only title updates.
  - Request/response schemas: See agent-session schema.

- Runtime Metadata
  - GET /api/v2/runtime/metadata
  - Description: Retrieve runtime capabilities and configuration.
  - Response schema: See agent-runtime-metadata schema.

- Health
  - GET /api/v2/health
  - Description: Readiness and liveness checks.
  - Response schema: See agent-health schema.

**Updated** Session Detail Enhancement (SPEC-025 R-2)
- GET /api/v2/sessions/{session_id} now includes `evidence_turns` field
- Description: Returns persisted tool evidence grouped by assistant turn
- Response enhancement: Adds `evidence_turns: list[EvidenceTurn] | None` field
- Behavior: Empty list when no evidence stored, null when evidence store is unreadable (never 500)
- Evidence Turn Schema: See session-evidence.schema.json for detailed structure

**New** Operations Document Repository (SPEC-039)
- POST /api/v2/documents
  - Description: Create typed operations documents with session provenance and optional AI-generated prose.
  - Authentication: X-User-ID header required; authorization enforced by platform gateway.
  - Request schema: DocumentCreateRequest with document_type, session_ids, label, include_prose.
  - Response schema: Created document with provenance, digest, and optional prose content.
  - Error codes: 201 Created, 400 Bad Request (validation errors), 403 Forbidden (foreign sessions without approvals:list).

- GET /api/v2/documents
  - Description: List documents with scope filtering (mine/published).
  - Authentication: X-User-ID header required.
  - Query Parameters: scope (default: "mine", options: "mine", "published").
  - Response schema: Object with documents array containing owner's drafts and published documents.
  - Error codes: 200 OK, 401 Unauthorized.

- GET /api/v2/documents/{document_id}
  - Description: Read a specific document with owner-only draft access.
  - Authentication: X-User-ID header required.
  - Path Parameters: document_id (required).
  - Response schema: Complete document with provenance, digest, and optional prose.
  - Error codes: 200 OK, 404 Not Found (unknown or foreign draft).

- POST /api/v2/documents/{document_id}/publish
  - Description: Publish one's own draft document (one-way operation).
  - Authentication: X-User-ID header required.
  - Path Parameters: document_id (required).
  - Response schema: Published document with timestamp and state change.
  - Error codes: 200 OK, 404 Not Found, 409 Conflict (already published).

- DELETE /api/v2/documents/{document_id}
  - Description: Delete one's own document (owner-only operation).
  - Authentication: X-User-ID header required.
  - Path Parameters: document_id (required).
  - Response schema: Confirmation object with document_id and deleted flag.
  - Error codes: 200 OK, 404 Not Found.

**Updated** Session Rename Endpoint (SPEC-039 R-7)
- PATCH /api/v2/sessions/{session_id}/title
  - Description: Owner-only session title update, superseding server-minted titles.
  - Authentication: X-User-ID header required.
  - Request schema: SessionTitleUpdateRequest with title field (1-80 characters after trimming).
  - Response schema: Updated AgentSession with new title.
  - Error codes: 200 OK, 400 Bad Request (validation errors), 404 Not Found (unknown/foreign session).

Streaming and WebSockets
- WS /api/v2/ws/chat?session_id={id}
- Description: Real-time streaming of agent events.
- Events: Agent stream event payloads conform to agent-stream-event schema.

Error Handling
- Standard HTTP statuses; domain-specific errors include invalid payload, session not found, provider errors.

Retry Strategy
- Same as Tool Gateway; prefer idempotency keys for reliable retries.

**Section sources**
- [agent-platform/src/agent_service/api/v2/routes.py](file://products/agent-platform/src/agent_service/api/v2/routes.py)
- [agent-platform/src/agent_service/schemas/v2.py](file://products/agent-platform/src/agent_service/schemas/v2.py)
- [agent-platform/src/agent_service/services/evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [agent-platform/src/agent_service/services/operation_documents.py](file://products/agent-platform/src/agent_service/services/operation_documents.py)
- [shared-contracts/schemas/agent-chat-request.schema.json](file://shared-contracts/schemas/agent-chat-request.schema.json)
- [shared-contracts/schemas/agent-chat-response.schema.json](file://shared-contracts/schemas/agent-chat-response.schema.json)
- [shared-contracts/schemas/agent-stream-event.schema.json](file://shared-contracts/schemas/agent-stream-event.schema.json)
- [shared-contracts/schemas/agent-session.schema.json](file://shared-contracts/schemas/agent-session.schema.json)
- [shared/shared-contracts/schemas/session-evidence.schema.json](file://shared/shared-contracts/schemas/session-evidence.schema.json)
- [shared-contracts/schemas/agent-runtime-metadata.schema.json](file://shared-contracts/schemas/agent-runtime-metadata.schema.json)
- [shared-contracts/schemas/agent-health.schema.json](file://shared-contracts/schemas/agent-health.schema.json)

### Identity Broker REST API
Authentication and identity context endpoints.

- Auth
  - POST /auth/token
  - Description: Issue access tokens using credentials or client assertions.
  - Request schema: See identity-token schema.
  - Response schema: Access token payload and metadata.

- Identity Context
  - GET /identity/context
  - Description: Resolve current identity context from token.
  - Authentication: Bearer token.
  - Response schema: See identity-context schema.

- Health
  - GET /health
  - Description: Service health check.
  - Response schema: See health-response schema.

Error Handling
- 400 Bad Request for invalid inputs.
- 401 Unauthorized for missing/invalid tokens.
- 403 Forbidden for insufficient permissions.
- 429 Too Many Requests for rate limiting.
- 5xx for server errors.

Retry Strategy
- Retry on 429 with exponential backoff; do not retry on 400/401/403 unless input changes.

**Section sources**
- [identity-broker/src/identity_service/api/routes/auth.py](file://products/identity-broker/src/identity_service/api/routes/auth.py)
- [identity-broker/src/identity_service/api/routes/identity.py](file://products/identity-broker/src/identity_service/api/routes/identity.py)
- [identity-broker/src/identity_service/schemas/auth.py](file://products/identity-broker/src/identity_service/schemas/auth.py)
- [identity-broker/src/identity_service/schemas/identity.py](file://products/identity-broker/src/identity_service/schemas/identity.py)
- [shared-contracts/schemas/identity-token.schema.json](file://shared-contracts/schemas/identity-token.schema.json)
- [shared-contracts/schemas/identity-context.schema.json](file://shared-contracts/schemas/identity-context.schema.json)
- [shared-contracts/schemas/health-response.schema.json](file://shared-contracts/schemas/health-response.schema.json)

### Audit Service REST API
Durable audit trail service providing ingestion, querying, and monitoring capabilities.

- Event Ingestion
  - POST /api/v1/audit/events
  - Description: Ingest batches of audit events from registered platform services.
  - Authentication: Service identity credential (client_id/client_secret).
  - Request schema: IngestRequest with array of AuditEvent objects.
  - Response schema: Acceptance confirmation with counts.
  - Error codes: 202 Accepted, 400 Bad Request (malformed batch), 401 Unauthorized (auth failure).

- Event Querying
  - GET /api/v1/audit/events
  - Description: Query stored audit events with filtering and keyset cursor pagination.
  - Authentication: Service identity credential (client_id/client_secret).
  - Query Parameters: username, session_id, request_id, event_type, service, since, until, cursor, limit.
  - Response schema: Paginated results with next_cursor for continuation.
  - Error codes: 200 OK, 400 Bad Request (invalid cursor/filter), 401 Unauthorized.

- Health Endpoints
  - GET /health/live
  - Description: Liveness probe returning service status and version.
  - Response schema: Basic health information.

  - GET /health/ready
  - Description: Readiness probe checking store backend availability.
  - Response schema: Detailed readiness status including store backend info.

- Metrics Endpoint
  - GET /metrics
  - Description: Prometheus metrics for monitoring audit service performance.
  - Authentication: None (internal monitoring).
  - Response: Prometheus format metrics data.

Authentication and Security
- All audit endpoints require service identity authentication using client credentials.
- User-level authorization for audit queries is enforced at the Platform Gateway layer.
- Batch size limits enforced to prevent abuse (configurable via AUDIT_MAX_BATCH).

Pagination and Filtering
- Keyset-based pagination using cursor parameter for efficient large dataset traversal.
- Comprehensive filtering by username, session_id, request_id, event_type, service, and time ranges.
- Maximum limit of 200 events per query for performance protection.

Error Handling
- 202 Accepted for successful ingestion (async processing).
- 200 OK for successful queries with paginated results.
- 400 Bad Request for malformed requests or invalid filters.
- 401 Unauthorized for authentication failures.
- 503 Service Unavailable when audit service is not configured (via Platform Gateway).

Retry Strategy
- Implement exponential backoff for transient errors (429, 503).
- Use correlation IDs (x-request-id) for request tracing and debugging.
- Handle pagination gracefully with cursor validation and retry logic.

**Section sources**
- [audit-service/src/audit_service/api/routes/ingest.py](file://products/audit-service/src/audit_service/api/routes/ingest.py)
- [audit-service/src/audit_service/api/routes/query.py](file://products/audit-service/src/audit_service/api/routes/query.py)
- [audit-service/src/audit_service/api/routes/health.py](file://products/audit-service/src/audit_service/api/routes/health.py)
- [audit-service/src/audit_service/core/metrics.py](file://products/audit-service/src/audit_service/core/metrics.py)
- [audit-service/src/audit_service/schemas/audit.py](file://products/audit-service/src/audit_service/schemas/audit.py)
- [platform-gateway/src/platform_gateway/api/routes/audit.py](file://products/platform-gateway/src/platform_gateway/api/routes/audit.py)

### Data Models and Schemas
All schemas are defined under shared-contracts and referenced by services.

- Chat and Streaming
  - chat-request.schema.json
  - chat-response.schema.json
  - stream-event.schema.json
  - agent-chat-request.schema.json
  - agent-chat-response.schema.json
  - agent-stream-event.schema.json

- Sessions
  - session.schema.json
  - agent-session.schema.json
  - **session-evidence.schema.json: New schema for persisted tool evidence with truncation markers and size caps**

- Identity
  - identity-token.schema.json
  - identity-context.schema.json

- Tools
  - tool-invocation.schema.json
  - tool-result.schema.json

- Policy
  - policy-decision.schema.json
  - policy-rule.schema.json
  - **policy-matrix.schema.json: Live permission matrix response with version, source, scope, roles, actions, and matrix fields.**

- Health and Runtime
  - health-response.schema.json
  - agent-health.schema.json
  - agent-runtime-metadata.schema.json

- Audit Trail
  - audit-event.schema.json: Canonical audit event envelope with event_id, occurred_at, event_type, service, request_id, outcome, and details fields.

**Updated** Operations Document Schemas (SPEC-039)
- **DocumentCreateRequest**: Typed document creation with discriminator pattern for future document types
  - document_type: Literal discriminator ("shift_summary" in Phase 1)
  - session_ids: Array of covered sessions (bounded to 20)
  - label: Human-readable document label (1-120 characters)
  - include_prose: Optional AI-generated narrative generation flag

- **SessionTitleUpdateRequest**: Owner-only session title updates
  - title: New session title (1-80 characters after trimming)

- **OperationDocument**: Immutable document record with lifecycle states
  - document_id: Unique identifier
  - document_type: Type discriminator
  - state: Lifecycle state ("draft" or "published")
  - owner_user_id: Document creator
  - label: Human-readable label
  - created_at: Creation timestamp
  - published_at: Publication timestamp (null for drafts)
  - provenance: Session provenance with coverage indicators
  - digest: Content hash and summary
  - prose: Optional generated narrative
  - prose_status: Generation status ("included", "failed", "not_requested")

**Updated** Evidence Turn Schema Details
- `turn_index`: Assistant turn ordinal (0-based) for replay attachment
- `request_id`: Correlation with audit trail tool_invoked events  
- `created_at`: Persistence timestamp assigned by evidence store
- `frames`: Ordered tool_call/tool_result frames with optional truncation markers
- Truncation reasons: `entry_cap` (per-entry size cap), `session_budget` (per-session budget eviction)

**Section sources**
- [shared-contracts/schemas/chat-request.schema.json](file://shared-contracts/schemas/chat-request.schema.json)
- [shared-contracts/schemas/chat-response.schema.json](file://shared-contracts/schemas/chat-response.schema.json)
- [shared-contracts/schemas/stream-event.schema.json](file://shared-contracts/schemas/stream-event.schema.json)
- [shared-contracts/schemas/agent-chat-request.schema.json](file://shared-contracts/schemas/agent-chat-request.schema.json)
- [shared-contracts/schemas/agent-chat-response.schema.json](file://shared-contracts/schemas/agent-chat-response.schema.json)
- [shared-contracts/schemas/agent-stream-event.schema.json](file://shared-contracts/schemas/agent-stream-event.schema.json)
- [shared-contracts/schemas/session.schema.json](file://shared-contracts/schemas/session.schema.json)
- [shared-contracts/schemas/agent-session.schema.json](file://shared-contracts/schemas/agent-session.schema.json)
- [shared/shared-contracts/schemas/session-evidence.schema.json](file://shared/shared-contracts/schemas/session-evidence.schema.json)
- [shared-contracts/schemas/identity-token.schema.json](file://shared-contracts/schemas/identity-token.schema.json)
- [shared-contracts/schemas/identity-context.schema.json](file://shared-contracts/schemas/identity-context.schema.json)
- [shared-contracts/schemas/tool-invocation.schema.json](file://shared-contracts/schemas/tool-invocation.schema.json)
- [shared-contracts/schemas/tool-result.schema.json](file://shared-contracts/schemas/tool-result.schema.json)
- [shared-contracts/schemas/policy-decision.schema.json](file://shared-contracts/schemas/policy-decision.schema.json)
- [shared-contracts/schemas/policy-rule.schema.json](file://shared-contracts/schemas/policy-rule.schema.json)
- [shared-contracts/schemas/health-response.schema.json](file://shared-contracts/schemas/health-response.schema.json)
- [shared-contracts/schemas/agent-health.schema.json](file://shared-contracts/schemas/agent-health.schema.json)
- [shared-contracts/schemas/agent-runtime-metadata.schema.json](file://shared-contracts/schemas/agent-runtime-metadata.schema.json)
- [shared-contracts/schemas/audit-event.schema.json](file://shared-contracts/schemas/audit-event.schema.json)
- [shared/shared-contracts/schemas/policy-matrix.schema.json](file://shared/shared-contracts/schemas/policy-matrix.schema.json)

## Dependency Analysis
The Tool Gateway depends on Identity Broker for authentication and on Agent Platform for execution. Policy engine and session store are integral to the gateway's orchestration flow. **The Platform Gateway depends on the policy engine for authorization and provides transparency endpoints that may proxy to Tool Gateway, Skills Hub, and Operation Document Store. The Agent Platform integrates with the Evidence Store for persistent tool evidence and Operation Document Store for immutable document persistence.**

```mermaid
graph LR
TG["Tool Gateway"] --> IB["Identity Broker"]
TG --> AP["Agent Platform"]
TG --> PE["Policy Engine"]
TG --> SS["Session Store"]
PG["Platform Gateway"] --> PE
PG --> AS["Audit Service"]
PG --> TG
PG --> SH["Skills Hub"]
PG --> OD["Operations Documents"]
AP --> RT["Agent Runtime"]
AP --> ES["Evidence Store"]
AP --> ODS["Operation Document Store"]
IB -.-> AS
ODS -.-> DB["PostgreSQL"]
```

**Diagram sources**
- [platform-gateway/src/platform_gateway/api/routes/policy.py](file://products/platform-gateway/src/platform_gateway/api/routes/policy.py)
- [platform-gateway/src/platform_gateway/api/routes/tools.py](file://products/platform-gateway/src/platform_gateway/api/routes/tools.py)
- [platform-gateway/src/platform_gateway/api/routes/skills.py](file://products/platform-gateway/src/platform_gateway/api/routes/skills.py)
- [platform-gateway/src/platform_gateway/api/routes/documents.py](file://products/platform-gateway/src/platform_gateway/api/routes/documents.py)
- [platform-gateway/src/platform_gateway/services/tool_gateway_client.py](file://products/platform-gateway/src/platform_gateway/services/tool_gateway_client.py)
- [agent-platform/src/agent_service/services/evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [agent-platform/src/agent_service/services/operation_documents.py](file://products/agent-platform/src/agent_service/services/operation_documents.py)

**Section sources**
- [platform-gateway/src/platform_gateway/api/routes/policy.py](file://products/platform-gateway/src/platform_gateway/api/routes/policy.py)
- [platform-gateway/src/platform_gateway/api/routes/tools.py](file://products/platform-gateway/src/platform_gateway/api/routes/tools.py)
- [platform-gateway/src/platform_gateway/api/routes/skills.py](file://products/platform-gateway/src/platform_gateway/api/routes/skills.py)
- [platform-gateway/src/platform_gateway/api/routes/documents.py](file://products/platform-gateway/src/platform_gateway/api/routes/documents.py)
- [platform-gateway/src/platform_gateway/services/policy_engine.py](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py)
- [platform-gateway/src/platform_gateway/services/tool_gateway_client.py](file://products/platform-gateway/src/platform_gateway/services/tool_gateway_client.py)
- [agent-platform/src/agent_service/services/evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [agent-platform/src/agent_service/services/operation_documents.py](file://products/agent-platform/src/agent_service/services/operation_documents.py)

## Performance Considerations
- Prefer streaming over polling for long-running operations to reduce latency and bandwidth.
- Use connection pooling and keep-alive for HTTP clients.
- Implement client-side caching for read-only endpoints where appropriate.
- Batch tool invocations when supported by policies.
- Monitor metrics and traces exposed by services to identify bottlenecks.
- **Use keyset pagination for audit queries to efficiently handle large datasets.**
- **Implement proper batching for audit event ingestion (max 50 events per batch).**
- **Leverage Prometheus metrics for performance monitoring and alerting.**
- **Cache permission matrix responses appropriately given their read-only nature.**
- **Limit skills inventory queries to reasonable page sizes (default 100, max 100).**
- **Monitor evidence store performance with dedicated metrics for frame persistence and truncation events.**
- **Configure appropriate evidence store budgets to balance persistence depth with storage costs.**
- **Optimize operations document queries with proper indexing on owner_user_id and state fields.**
- **Implement document publication caching to reduce database load for frequently accessed published documents.**
- **Use asynchronous audit event emission to avoid blocking document operations.**

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and resolutions:
- 401 Unauthorized: Ensure valid bearer token; refresh tokens as needed.
- 403 Forbidden: Check policy rules and roles; verify identity context.
- 429 Too Many Requests: Implement backoff and reduce request rate.
- 500/503: Inspect service logs; check downstream dependencies (agents, tools, stores).
- Streaming interruptions: Reconnect with last event ID; use idempotency keys.
- **Audit Service Issues: Verify service credentials, check store backend connectivity, monitor retention policies.**
- **Platform Gateway Issues: Check policy bundle loading, delegated token availability, and upstream service configuration.**
- **Evidence Store Issues: Verify evidence store backend availability, check storage budgets, monitor truncation events.**
- **Operations Document Issues: Verify document ownership, check publication states, monitor Provenance integrity.**

Debugging techniques:
- Enable request tracing and correlation IDs.
- Validate payloads against shared schemas before sending.
- Use health endpoints to verify service readiness.
- Capture network traces for WebSocket connections.
- **Monitor audit service metrics for ingestion and query performance.**
- **Use audit event filtering to isolate specific issues or users.**
- **Check policy matrix endpoint to verify authorization configuration.**
- **Validate tools catalog and skills inventory access patterns.**
- **Inspect evidence_turns field in session responses to verify evidence persistence.**
- **Monitor evidence store metrics for frame persistence success rates and truncation events.**
- **Verify document provenance integrity and session coverage validation.**
- **Check document publication workflow and ownership enforcement.**

**Section sources**
- [shared-contracts/schemas/health-response.schema.json](file://shared-contracts/schemas/health-response.schema.json)
- [shared-contracts/schemas/agent-health.schema.json](file://shared-contracts/schemas/agent-health.schema.json)
- [audit-service/src/audit_service/core/metrics.py](file://products/audit-service/src/audit_service/core/metrics.py)
- [platform-gateway/src/platform_gateway/api/routes/policy.py](file://products/platform-gateway/src/platform_gateway/api/routes/policy.py)
- [agent-platform/src/agent_service/services/evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [agent-platform/src/agent_service/services/operation_documents.py](file://products/agent-platform/src/agent_service/services/operation_documents.py)

## Conclusion
The Luban AIOps Platform exposes a cohesive set of REST and WebSocket APIs across Tool Gateway, Agent Platform, Identity Broker, Platform Gateway, and Audit Service. The new transparency endpoints provide operators with visibility into permissions, tools, and skills while maintaining strict authorization controls. **The evidence persistence system (SPEC-025) adds powerful replay capabilities for tool executions with bounded storage, truncation markers, and graceful degradation when stores are unavailable. The operations document repository (SPEC-039) introduces immutable document management with draft/published states, owner-only visibility, and team-wide sharing capabilities.** By adhering to shared schemas, implementing robust retry strategies, leveraging streaming, and utilizing the durable audit trail system, clients can build resilient integrations with comprehensive observability and compliance capabilities. Follow the versioning and migration guidelines to maintain compatibility during upgrades.

[No sources needed since this section summarizes without analyzing specific files]

## Appendices

### API Versioning and Deprecation Policy
- Versioning: Path-based versioning (e.g., /api/v1/, /api/v2/).
- Deprecation: Announce deprecations in release notes; provide parallel versions during transition.
- Migration: Supply migration guides for breaking changes; maintain backward compatibility where feasible.

[No sources needed since this section provides general guidance]

### Client Implementation Examples
- Python: Use httpx for REST and websockets for streaming; implement exponential backoff and correlation IDs.
- JavaScript/Node.js: Use axios/fetch for REST and ws or native WebSocket for streaming; handle reconnect logic.
- Go: Use net/http and gorilla/websocket; implement retry with context cancellation.
- Java: Use OkHttp and Spring WebSocket; manage connection pools and retries.
- **Platform Gateway Clients: Use user bearer tokens with appropriate permissions for transparency endpoints; implement proper error handling for 401/403/503 responses.**
- **Tool Gateway Clients: Use delegated token chains for tools catalog access; handle upstream service failures gracefully.**
- **Evidence-Aware Clients: Handle evidence_turns field gracefully - treat empty arrays as no evidence, null values as degraded service, and validate frame structures for replay functionality.**
- **Operations Document Clients: Implement proper document lifecycle management with draft/published states, handle ownership validation, and manage provenance integrity.**

[No sources needed since this section provides general guidance]

### Testing Strategies
- Contract tests against shared schemas.
- Integration tests mocking downstream services.
- Load tests for streaming endpoints.
- Chaos tests for resilience and retry behavior.
- **Audit Service Tests: Test ingestion batching, query filtering, pagination, and authentication flows.**
- **Platform Gateway Tests: Test permission matrix generation, tools catalog proxying, skills inventory filtering, and authorization enforcement.**
- **Evidence Store Tests: Test persistence round-trips, truncation markers, budget enforcement, and graceful degradation when stores are unavailable.**
- **Operations Document Tests: Test document lifecycle (create/list/get/publish/delete), ownership validation, provenance integrity, and publication workflow.**

[No sources needed since this section provides general guidance]

### Platform Gateway Configuration
- Environment Variables:
  - PLATFORM_GATEWAY_POLICY_PATH: Custom policy bundle path (optional)
  - TOOL_GATEWAY_URL: Tool Gateway service URL for delegation
  - SKILLS_HUB_URL: Skills Hub service URL for inventory access
  - DELEGATION_CLIENT_ID: Client ID for delegated token issuance
  - DELEGATION_CLIENT_SECRET: Client secret for delegated token issuance

- Deployment Configuration:
  - Kubernetes deployment with health probes
  - Prometheus metrics scraping enabled
  - Secret management for credentials
  - Resource limits and security context
  - Policy bundle mounting for custom configurations

**Section sources**
- [platform-gateway/src/platform_gateway/core/config.py](file://products/platform-gateway/src/platform_gateway/core/config.py)
- [platform-gateway/src/platform_gateway/api/routes/policy.py](file://products/platform-gateway/src/platform_gateway/api/routes/policy.py)
- [platform-gateway/src/platform_gateway/api/routes/tools.py](file://products/platform-gateway/src/platform_gateway/api/routes/tools.py)
- [platform-gateway/src/platform_gateway/api/routes/skills.py](file://products/platform-gateway/src/platform_gateway/api/routes/skills.py)
- [platform-gateway/src/platform_gateway/api/routes/documents.py](file://products/platform-gateway/src/platform_gateway/api/routes/documents.py)

### Evidence Store Configuration
- Environment Variables:
  - AGENT_STATE_STORE_BACKEND: Backend selection ("memory" or "postgres")
  - AGENT_STATE_DB_URL: Database connection string for Postgres backend
  - EVIDENCE_ENTRY_MAX_CHARS: Per-entry size cap (default: 131,072 characters)
  - EVIDENCE_SESSION_MAX_BYTES: Per-session storage budget (default: 4,194,304 bytes)

- Storage Backends:
  - Memory: Default backend for development and CI environments
  - Postgres: Production backend sharing database with SPEC-016/017 state store
  - Automatic fallback to memory when Postgres is unavailable

- Retention and Budget Management:
  - Evidence follows session lifetime (cascade delete with sessions)
  - Per-session budget enforcement with oldest-payload eviction
  - TTL refresh on reads mirroring state store pattern
  - Fail-open semantics - persistence failures never fail chat turns

**Section sources**
- [agent-platform/src/agent_service/services/evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [agent-platform/src/agent_service/core/metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)

### Operations Document Store Configuration
- Environment Variables:
  - AGENT_STATE_STORE_BACKEND: Backend selection ("memory" or "postgres")
  - AGENT_STATE_DB_URL: Database connection string for Postgres backend

- Storage Backends:
  - Memory: Default backend for development and CI environments
  - Postgres: Production backend sharing database with SPEC-016/017 state store
  - Automatic fallback to memory when Postgres is unavailable

- Retention and Capacity Management:
  - Per-owner document cap (20 documents per owner, oldest evicted first)
  - 30-day retention policy with opportunistic cleanup
  - One-way lifecycle: draft -> published (owner action only)
  - Fail-open semantics - backend failures degrade to in-memory store

- Indexing and Performance:
  - Composite index on (owner_user_id, created_at) for owner-scoped queries
  - Index on (state, created_at) for published document discovery
  - Optimized queries for list_for_owner and list_published operations

**Section sources**
- [agent-platform/src/agent_service/services/operation_documents.py](file://products/agent-platform/src/agent_service/services/operation_documents.py)