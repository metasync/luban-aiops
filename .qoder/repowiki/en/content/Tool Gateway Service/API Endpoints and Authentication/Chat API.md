# Chat API

<cite>
**Referenced Files in This Document**
- [chat.py](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py)
- [api.py](file://products/platform-gateway/src/platform_gateway/schemas/api.py)
- [gateway_service.py](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py)
- [agent_client.py](file://products/platform-gateway/src/platform_gateway/services/agent_client.py)
- [policy_engine.py](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py)
- [token_verifier.py](file://products/tool-gateway/src/tool_gateway/services/token_verifier.py)
- [router.py](file://products/tool-gateway/src/tool_gateway/api/router.py)
- [app.py](file://tool-gateway/src/tool_gateway/app.py)
- [main.py](file://tool-gateway/src/tool_gateway/main.py)
- [chat-request.schema.json](file://shared/shared-contracts/schemas/chat-request.schema.json)
- [chat-response.schema.json](file://shared/shared-contracts/schemas/chat-response.schema.json)
- [stream-event.schema.json](file://shared/shared-contracts/schemas/stream-event.schema.json)
- [tool-invocation.schema.json](file://shared/shared-contracts/schemas/tool-invocation.schema.json)
- [tool-result.schema.json](file://shared/shared-contracts/schemas/tool-result.schema.json)
- [v2.py](file://products/agent-platform/src/agent_service/schemas/v2.py)
- [test_session_workspace.py](file://products/platform-gateway/tests/test_session_workspace.py)
</cite>

## Update Summary
**Changes Made**
- Enhanced ChatRequest schema documentation with new `input_modality` field supporting text|voice modality values
- Added voice-readiness contract section explaining security invariants and privilege escalation prevention
- Updated request/response patterns to include modality handling throughout the gateway audit trail
- Added examples demonstrating modality propagation and validation behavior
- Updated streaming event types to reflect v6 stream schema with confirmation support
- Enhanced error scenarios to include modality validation failures

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Voice-Readiness Contract](#voice-readiness-contract)
7. [Dependency Analysis](#dependency-analysis)
8. [Performance Considerations](#performance-considerations)
9. [Troubleshooting Guide](#troubleshooting-guide)
10. [Conclusion](#conclusion)

## Introduction
This document provides comprehensive API documentation for the chat endpoints exposed by the Tool Gateway Service. It covers RESTful request/response patterns, WebSocket streaming for real-time responses, and message formatting. It also details the enhanced chat request schema including agent selection, conversation context, tool invocation parameters, and the new voice-readiness contract with optional `input_modality` field. The documentation includes streaming event types, partial response handling, error scenarios, and security invariants that prevent privilege escalation through input modality. Examples are provided for both synchronous and asynchronous chat interactions, along with guidance on rate limiting, message size limits, and performance optimization.

## Project Structure
The Tool Gateway Service exposes chat functionality through HTTP routes that delegate to a gateway service, which interacts with an agent client and enforces policies. Schemas for requests, responses, and streaming events are defined in shared contracts. The system now supports voice-readiness with modality metadata that flows through the audit trail while maintaining security invariants.

```mermaid
graph TB
Client["Client"] --> Router["API Router"]
Router --> ChatRoute["Chat Route"]
ChatRoute --> GatewayService["Gateway Service"]
GatewayService --> PolicyEngine["Policy Engine"]
GatewayService --> AgentClient["Agent Client"]
AgentClient --> AgentRuntime["Agent Runtime"]
AgentRuntime --> Tools["Tool Registry / Tools"]
ChatRoute --> Schemas["Request/Response Schemas"]
ChatRoute --> AuditTrail["Audit Trail (Modality Metadata)"]
```

**Diagram sources**
- [chat.py:36-86](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L36-L86)
- [api.py:9-20](file://products/platform-gateway/src/platform_gateway/schemas/api.py#L9-L20)
- [agent_client.py:92-114](file://products/platform-gateway/src/platform_gateway/services/agent_client.py#L92-L114)

**Section sources**
- [chat.py:36-86](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L36-L86)
- [api.py:9-20](file://products/platform-gateway/src/platform_gateway/schemas/api.py#L9-L20)
- [agent_client.py:92-114](file://products/platform-gateway/src/platform_gateway/services/agent_client.py#L92-L114)

## Core Components
- Chat Route: Defines REST endpoints for chat requests and WebSocket streaming with enhanced modality support.
- Gateway Service: Orchestrates policy checks, session management, and calls to the agent runtime with modality propagation.
- Agent Client: Communicates with the agent runtime over HTTP or streaming protocols, forwarding modality as metadata.
- Policy Engine: Enforces access control and usage policies for chat operations (modality does not affect policy decisions).
- Token Verifier: Validates authentication tokens for secure access.
- Schemas: Define request/response structures and streaming event formats with voice-readiness support.

Key responsibilities:
- Validate incoming chat requests against schemas including modality validation.
- Enforce policies before invoking agents (modality is metadata only, never decision-bearing).
- Stream partial responses via WebSocket events.
- Aggregate final results into structured responses.
- Propagate modality through audit trail for observability without affecting security.

**Section sources**
- [chat.py:36-86](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L36-L86)
- [gateway_service.py:121-153](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L121-L153)
- [agent_client.py:92-114](file://products/platform-gateway/src/platform_gateway/services/agent_client.py#L92-L114)
- [api.py:9-20](file://products/platform-gateway/src/platform_gateway/schemas/api.py#L9-L20)

## Architecture Overview
The chat flow involves routing HTTP requests to the chat endpoint, validating inputs including modality, enforcing policies, invoking the agent runtime, and returning either a complete response or streaming partial updates. Modality flows through the system as metadata only, never affecting policy decisions or security outcomes.

```mermaid
sequenceDiagram
participant Client as "Client"
participant Router as "API Router"
participant ChatRoute as "Chat Route"
participant Gateway as "Gateway Service"
participant Policy as "Policy Engine"
participant Agent as "Agent Client"
participant Runtime as "Agent Runtime"
participant Audit as "Audit Trail"
Client->>Router : POST /api/v1/chat
Router->>ChatRoute : Dispatch request
ChatRoute->>ChatRoute : Validate schema + modality
ChatRoute->>Gateway : Create chat session with modality
Gateway->>Policy : Enforce policy (modality ignored)
Policy-->>Gateway : Decision (same for text/voice)
Gateway->>Agent : Invoke agent with modality metadata
Agent-->>Gateway : Stream events
Gateway-->>ChatRoute : Partial updates
ChatRoute-->>Client : SSE/WebSocket stream
Agent-->>Gateway : Final result
Gateway-->>ChatRoute : Aggregated response
ChatRoute->>Audit : Log modality (metadata only)
ChatRoute-->>Client : JSON response
```

**Diagram sources**
- [chat.py:36-86](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L36-L86)
- [agent_client.py:92-114](file://products/platform-gateway/src/platform_gateway/services/agent_client.py#L92-L114)
- [gateway_service.py:121-153](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L121-L153)

## Detailed Component Analysis

### Chat Endpoints
- REST Endpoint: POST /api/v1/chat accepts a chat request and returns a JSON response with enhanced modality support.
- WebSocket Endpoint: GET /api/v1/chat/stream establishes a real-time connection for streaming partial responses.

Enhanced Request Schema:
- agent_id: Identifier for the target agent.
- messages: Array of conversation messages with role and content.
- tools: Optional list of tool invocation parameters.
- session_id: Optional identifier for conversation continuity.
- metadata: Optional key-value pairs for tracing and analytics.
- **input_modality**: Optional field with enum values ["text", "voice"], defaults to "text". Voice-readiness contract ensures this is metadata only and never affects policy decisions.

Response Schema:
- id: Unique response identifier.
- created_at: Timestamp of response creation.
- choices: Array of generated content items.
- usage: Token usage statistics.
- error: Error details if applicable.

Streaming Events:
- delta: Partial content update.
- tool_call: Tool invocation details.
- tool_result: Result from tool execution.
- done: Indicates completion of the stream.

Error Scenarios:
- Invalid request schema including unknown modality values.
- Policy denial (unaffected by modality).
- Authentication failure.
- Agent runtime errors.

**Updated** Enhanced with voice-readiness contract and modality validation

**Section sources**
- [chat.py:36-86](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L36-L86)
- [api.py:9-20](file://products/platform-gateway/src/platform_gateway/schemas/api.py#L9-L20)
- [chat-request.schema.json:26-31](file://shared/shared-contracts/schemas/chat-request.schema.json#L26-L31)

### Gateway Service
The gateway service orchestrates chat operations by:
- Validating and transforming requests including modality validation.
- Checking policies for authorization and rate limiting (modality does not affect policy decisions).
- Managing sessions for conversation context.
- Invoking the agent client for processing with modality metadata.
- Handling streaming events and aggregating results.
- Emitting audit events with modality information for observability.

**Updated** Now handles modality propagation through the entire request lifecycle while maintaining security invariants

**Section sources**
- [gateway_service.py:121-153](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L121-L153)

### Agent Client
The agent client communicates with the agent runtime using:
- HTTP requests for synchronous responses with modality metadata.
- Streaming connections for real-time updates.
- Error handling and retries for robustness.
- Modality propagation as metadata only (never affects downstream behavior).

**Updated** Now forwards input_modality as metadata to agent runtime per SPEC-022 R-2

**Section sources**
- [agent_client.py:92-114](file://products/platform-gateway/src/platform_gateway/services/agent_client.py#L92-L114)

### Policy Engine
The policy engine enforces:
- Access control based on user roles and permissions (modality has no effect).
- Rate limiting and quota enforcement.
- Custom rules for tool invocation and data access.
- Security invariants ensuring modality cannot be used for privilege escalation.

**Updated** Maintains security invariant that modality never affects policy decisions

**Section sources**
- [policy_engine.py:121-153](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L121-L153)

### Token Verifier
The token verifier ensures:
- JWT validation and expiration checks.
- Scope verification for API access.
- Secure context propagation.

**Section sources**
- [token_verifier.py:58-118](file://products/tool-gateway/src/tool_gateway/services/token_verifier.py#L58-L118)

## Voice-Readiness Contract

The voice-readiness contract (SPEC-022 R-2) establishes critical security invariants for modality handling:

### Core Principles
1. **Metadata Only**: Input modality is metadata only and never changes policy, auto-allow, or HITL outcomes.
2. **Security Invariant**: Modality can never approve or deny a parked confirmation.
3. **Identical Behavior**: Text and voice inputs follow identical policy paths and produce identical results.
4. **Audit Trail**: Modality flows through the audit trail for observability but never affects security decisions.

### Implementation Details
- **Schema Validation**: The `input_modality` field accepts only "text" or "voice" values, defaulting to "text" when absent.
- **Policy Enforcement**: Policy decisions are identical regardless of modality value.
- **Audit Logging**: Modality is recorded in audit events for traceability.
- **Contract Validation**: Unknown modality values are rejected before policy evaluation.

### Security Guarantees
- No privilege escalation through input modality manipulation.
- Consistent behavior across different input modalities.
- Complete audit trail for compliance and debugging.
- Prevention of modality-based bypass attempts.

**Section sources**
- [chat-request.schema.json:26-31](file://shared/shared-contracts/schemas/chat-request.schema.json#L26-L31)
- [chat.py:67-78](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L67-L78)
- [test_session_workspace.py:227-285](file://products/platform-gateway/tests/test_session_workspace.py#L227-L285)

## Dependency Analysis
The chat system has clear dependencies between components with enhanced modality support:
- Chat route depends on gateway service, schemas, and audit emitter for modality logging.
- Gateway service depends on policy engine, agent client, and session management with modality propagation.
- Agent client depends on agent runtime and network libraries, forwarding modality as metadata.
- Policy engine depends on configuration and rule definitions, ignoring modality for decisions.

```mermaid
graph LR
ChatRoute["Chat Route"] --> GatewayService["Gateway Service"]
ChatRoute --> AuditEmitter["Audit Emitter"]
GatewayService --> PolicyEngine["Policy Engine"]
GatewayService --> AgentClient["Agent Client"]
AgentClient --> AgentRuntime["Agent Runtime"]
ChatRoute --> Schemas["Schemas"]
AuditEmitter --> AuditTrail["Durable Audit Trail"]
```

**Diagram sources**
- [chat.py:36-86](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L36-L86)
- [agent_client.py:92-114](file://products/platform-gateway/src/platform_gateway/services/agent_client.py#L92-L114)
- [gateway_service.py:121-153](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L121-L153)

**Section sources**
- [chat.py:36-86](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L36-L86)
- [gateway_service.py:121-153](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L121-L153)
- [agent_client.py:92-114](file://products/platform-gateway/src/platform_gateway/services/agent_client.py#L92-L114)

## Performance Considerations
- Use WebSocket streaming for long-running operations to reduce latency.
- Implement request batching for multiple tool invocations.
- Cache frequently accessed agent configurations.
- Monitor and optimize network timeouts and retry logic.
- Apply rate limiting at the gateway level to prevent overload.
- **Modality Impact**: Modality processing adds minimal overhead as it's handled as metadata only.
- **Audit Trail**: Durable audit logging may add slight latency but provides essential compliance capabilities.

## Troubleshooting Guide
Common issues and resolutions:
- Authentication failures: Verify token validity and scopes.
- Policy denials: Check user permissions and custom rules (modality should not affect these).
- Streaming interruptions: Implement reconnection logic and handle partial responses.
- Agent runtime errors: Log detailed error messages and implement fallback strategies.
- **Modality Validation Errors**: Ensure input_modality is either "text" or "voice"; unknown values will be rejected with 422 status.
- **Audit Trail Issues**: Verify audit service connectivity and storage backend availability.

**Updated** Added modality-specific troubleshooting guidance

**Section sources**
- [token_verifier.py:58-118](file://products/tool-gateway/src/tool_gateway/services/token_verifier.py#L58-L118)
- [policy_engine.py:121-153](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L121-L153)
- [agent_client.py:92-114](file://products/platform-gateway/src/platform_gateway/services/agent_client.py#L92-L114)

## Conclusion
The Tool Gateway Service provides a robust chat API with support for both synchronous and asynchronous interactions, enhanced with voice-readiness capabilities. By leveraging WebSocket streaming, policy enforcement, well-defined schemas, and the voice-readiness contract, it enables efficient and secure communication with agent runtimes while maintaining strict security invariants. The enhanced modality support allows for future voice-based interactions without compromising security or altering existing behavior. Proper implementation of error handling, rate limiting, performance optimizations, and the voice-readiness contract ensures reliable operation in production environments while providing comprehensive audit trails for compliance and debugging purposes.