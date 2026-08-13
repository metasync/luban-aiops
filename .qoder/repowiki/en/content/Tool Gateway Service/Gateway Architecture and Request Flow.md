# Gateway Architecture and Request Flow

<cite>
**Referenced Files in This Document**
- [main.py](file://products/tool-gateway/src/api_gateway/main.py)
- [app.py](file://products/tool-gateway/src/api_gateway/app.py)
- [router.py](file://products/tool-gateway/src/api_gateway/api/router.py)
- [routes/chat.py](file://products/tool-gateway/src/api_gateway/api/routes/chat.py)
- [routes/tools.py](file://products/tool-gateway/src/api_gateway/api/routes/tools.py)
- [routes/auth.py](file://products/tool-gateway/src/api_gateway/api/routes/auth.py)
- [routes/identity.py](file://products/tool-gateway/src/api_gateway/api/routes/identity.py)
- [routes/sessions.py](file://products/tool-gateway/src/api_gateway/api/routes/sessions.py)
- [routes/runtime.py](file://products/tool-gateway/src/api_gateway/api/routes/runtime.py)
- [routes/health.py](file://products/tool-gateway/src/api_gateway/api/routes/health.py)
- [dependencies.py](file://products/tool-gateway/src/api_gateway/core/dependencies.py)
- [config.py](file://products/tool-gateway/src/api_gateway/core/config.py)
- [observability.py](file://products/tool-gateway/src/api_gateway/core/observability.py)
- [metrics.py](file://products/tool-gateway/src/api_gateway/core/metrics.py)
- [telemetry.py](file://products/tool-gateway/src/api_gateway/core/telemetry.py)
- [request_context.py](file://products/tool-gateway/src/api_gateway/core/request_context.py)
- [runtime.py](file://products/tool-gateway/src/api_gateway/core/runtime.py)
- [gateway_service.py](file://products/tool-gateway/src/api_gateway/services/gateway_service.py)
- [policy_engine.py](file://products/tool-gateway/src/api_gateway/services/policy_engine.py)
- [token_verifier.py](file://products/tool-gateway/src/api_gateway/services/token_verifier.py)
- [agent_client.py](file://products/tool-gateway/src/api_gateway/services/agent_client.py)
- [delegation_client.py](file://products/tool-gateway/src/api_gateway/services/delegation_client.py)
- [registry.py](file://products/tool-gateway/src/api_gateway/tools/registry.py)
- [base.py](file://products/tool-gateway/src/api_gateway/tools/base.py)
- [k8s_connector.py](file://products/tool-gateway/src/api_gateway/tools/k8s_connector.py)
- [api.py](file://products/tool-gateway/src/api_gateway/schemas/api.py)
- [policy-default.yaml](file://products/tool-gateway/src/api_gateway/policies/policy-default.yaml)
</cite>

## Update Summary
**Changes Made**
- Added delegation client implementation for token exchange operations
- Enhanced token verification with audience claim validation
- Implemented metrics tracking for delegation_exchange_total and delegation_cache_total operations
- Updated architecture diagrams to reflect new delegation flow
- Expanded service orchestration section to include delegation client integration

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Delegation Client Implementation](#delegation-client-implementation)
7. [Enhanced Token Verification](#enhanced-token-verification)
8. [Metrics and Observability](#metrics-and-observability)
9. [Dependency Analysis](#dependency-analysis)
10. [Performance Considerations](#performance-considerations)
11. [Troubleshooting Guide](#troubleshooting-guide)
12. [Conclusion](#conclusion)

## Introduction
This document explains the Tool Gateway Service architecture and request flow patterns. The gateway acts as a centralized API entry point that authenticates requests, enforces policies, routes to downstream services or tools, and returns standardized responses. It is implemented with FastAPI and uses dependency injection for configuration, observability, policy enforcement, token verification, and tool execution. **Updated** The architecture now includes enhanced delegation capabilities for secure token exchange operations and improved metrics tracking for operational visibility.

## Project Structure
The Tool Gateway service is organized into clear layers:
- Entry points: application bootstrap and router registration
- API layer: HTTP routes grouped by domain (chat, tools, auth, identity, sessions, runtime, health)
- Core: configuration, dependency wiring, observability, metrics, telemetry, request context, runtime settings
- Services: orchestration logic including gateway orchestration, policy engine, token verification, agent client, and delegation client
- Tools: tool registry, base abstractions, and concrete connectors (e.g., Kubernetes connector)
- Schemas: shared request/response models
- Policies: default policy definitions

```mermaid
graph TB
subgraph "Entry"
M["main.py"]
A["app.py"]
R["api/router.py"]
end
subgraph "API Routes"
CHAT["api/routes/chat.py"]
TOOLS["api/routes/tools.py"]
AUTH["api/routes/auth.py"]
IDENTITY["api/routes/identity.py"]
SESSIONS["api/routes/sessions.py"]
RUNTIME["api/routes/runtime.py"]
HEALTH["api/routes/health.py"]
end
subgraph "Core"
CFG["core/config.py"]
DEP["core/dependencies.py"]
OBS["core/observability.py"]
MET["core/metrics.py"]
TEL["core/telemetry.py"]
RCX["core/request_context.py"]
RT["core/runtime.py"]
end
subgraph "Services"
GW["services/gateway_service.py"]
POL["services/policy_engine.py"]
TV["services/token_verifier.py"]
AC["services/agent_client.py"]
DC["services/delegation_client.py"]
end
subgraph "Tools"
REG["tools/registry.py"]
BASE["tools/base.py"]
K8S["tools/k8s_connector.py"]
end
M --> A --> R
R --> CHAT
R --> TOOLS
R --> AUTH
R --> IDENTITY
R --> SESSIONS
R --> RUNTIME
R --> HEALTH
CHAT --> DEP
TOOLS --> DEP
AUTH --> DEP
IDENTITY --> DEP
SESSIONS --> DEP
RUNTIME --> DEP
HEALTH --> DEP
DEP --> CFG
DEP --> OBS
DEP --> MET
DEP --> TEL
DEP --> RCX
DEP --> RT
CHAT --> GW
TOOLS --> GW
GW --> POL
GW --> TV
GW --> AC
GW --> DC
GW --> REG
REG --> BASE
REG --> K8S
```

**Diagram sources**
- [main.py](file://products/tool-gateway/src/api_gateway/main.py)
- [app.py](file://products/tool-gateway/src/api_gateway/app.py)
- [router.py](file://products/tool-gateway/src/api_gateway/api/router.py)
- [routes/chat.py](file://products/tool-gateway/src/api_gateway/api/routes/chat.py)
- [routes/tools.py](file://products/tool-gateway/src/api_gateway/api/routes/tools.py)
- [routes/auth.py](file://products/tool-gateway/src/api_gateway/api/routes/auth.py)
- [routes/identity.py](file://products/tool-gateway/src/api_gateway/api/routes/identity.py)
- [routes/sessions.py](file://products/tool-gateway/src/api_gateway/api/routes/sessions.py)
- [routes/runtime.py](file://products/tool-gateway/src/api_gateway/api/routes/runtime.py)
- [routes/health.py](file://products/tool-gateway/src/api_gateway/api/routes/health.py)
- [dependencies.py](file://products/tool-gateway/src/api_gateway/core/dependencies.py)
- [config.py](file://products/tool-gateway/src/api_gateway/core/config.py)
- [observability.py](file://products/tool-gateway/src/api_gateway/core/observability.py)
- [metrics.py](file://products/tool-gateway/src/api_gateway/core/metrics.py)
- [telemetry.py](file://products/tool-gateway/src/api_gateway/core/telemetry.py)
- [request_context.py](file://products/tool-gateway/src/api_gateway/core/request_context.py)
- [runtime.py](file://products/tool-gateway/src/api_gateway/core/runtime.py)
- [gateway_service.py](file://products/tool-gateway/src/api_gateway/services/gateway_service.py)
- [policy_engine.py](file://products/tool-gateway/src/api_gateway/services/policy_engine.py)
- [token_verifier.py](file://products/tool-gateway/src/api_gateway/services/token_verifier.py)
- [agent_client.py](file://products/tool-gateway/src/api_gateway/services/agent_client.py)
- [delegation_client.py](file://products/tool-gateway/src/api_gateway/services/delegation_client.py)
- [registry.py](file://products/tool-gateway/src/api_gateway/tools/registry.py)
- [base.py](file://products/tool-gateway/src/api_gateway/tools/base.py)
- [k8s_connector.py](file://products/tool-gateway/src/api_gateway/tools/k8s_connector.py)

**Section sources**
- [main.py](file://products/tool-gateway/src/api_gateway/main.py)
- [app.py](file://products/tool-gateway/src/api_gateway/app.py)
- [router.py](file://products/tool-gateway/src/api_gateway/api/router.py)

## Core Components
- FastAPI Application: Bootstraps middleware, lifespan events, and global state.
- Router: Mounts domain-specific route modules under versioned prefixes.
- Dependencies: Centralized dependency providers for config, observability, metrics, telemetry, request context, and runtime settings.
- Services:
  - GatewayService: Orchestrates request lifecycle, policy checks, token validation, and tool invocation.
  - PolicyEngine: Loads and evaluates policies against incoming requests.
  - TokenVerifier: Validates tokens and extracts identity context with enhanced audience claim validation.
  - AgentClient: Communicates with downstream agent services when needed.
  - DelegationClient: Handles secure token exchange operations with caching and metrics tracking.
- Tools:
  - Registry: Discovers and manages tool implementations.
  - Base: Abstract interface for tools.
  - K8sConnector: Concrete tool for Kubernetes operations.
- Schemas: Pydantic models for request/response contracts.
- Policies: Default YAML policy definitions used by the policy engine.

Key responsibilities:
- Centralized authentication and authorization via token verification and policy evaluation.
- Consistent request context propagation across layers.
- Observability hooks for tracing, metrics, and structured logging.
- Extensible tool execution framework with pluggable connectors.
- Secure delegation capabilities for cross-service token exchange.

**Section sources**
- [dependencies.py](file://products/tool-gateway/src/api_gateway/core/dependencies.py)
- [gateway_service.py](file://products/tool-gateway/src/api_gateway/services/gateway_service.py)
- [policy_engine.py](file://products/tool-gateway/src/api_gateway/services/policy_engine.py)
- [token_verifier.py](file://products/tool-gateway/src/api_gateway/services/token_verifier.py)
- [agent_client.py](file://products/tool-gateway/src/api_gateway/services/agent_client.py)
- [delegation_client.py](file://products/tool-gateway/src/api_gateway/services/delegation_client.py)
- [registry.py](file://products/tool-gateway/src/api_gateway/tools/registry.py)
- [base.py](file://products/tool-gateway/src/api_gateway/tools/base.py)
- [k8s_connector.py](file://products/tool-gateway/src/api_gateway/tools/k8s_connector.py)
- [api.py](file://products/tool-gateway/src/api_gateway/schemas/api.py)
- [policy-default.yaml](file://products/tool-gateway/src/api_gateway/policies/policy-default.yaml)

## Architecture Overview
The gateway exposes REST endpoints through FastAPI routers. Each request flows through:
- Middleware stack (auth, observability, metrics, request context)
- Route handler (domain-specific logic)
- Dependency-injected services (policy, token verification, gateway orchestration, delegation)
- Tool registry and concrete tool execution
- Response generation with consistent schemas and observability data

```mermaid
sequenceDiagram
participant Client as "Client"
participant FastAPI as "FastAPI App"
participant Router as "Router"
participant Handler as "Route Handler"
participant Deps as "Dependencies"
participant Policy as "PolicyEngine"
participant Token as "TokenVerifier"
participant Gateway as "GatewayService"
participant Delegation as "DelegationClient"
participant Tools as "ToolRegistry"
participant Tool as "Concrete Tool"
participant Agent as "AgentClient"
Client->>FastAPI : "HTTP Request"
FastAPI->>Router : "Dispatch by path"
Router->>Handler : "Invoke endpoint"
Handler->>Deps : "Resolve dependencies"
Handler->>Token : "Verify token with audience validation"
Token-->>Handler : "Identity context"
Handler->>Policy : "Evaluate policy"
Policy-->>Handler : "Decision + metadata"
Handler->>Gateway : "Orchestrate request"
alt Tool-based operation
Gateway->>Tools : "Resolve tool by name"
Tools-->>Gateway : "Tool instance"
Gateway->>Tool : "Execute with validated input"
Tool-->>Gateway : "Result"
else Agent-based operation
Gateway->>Agent : "Call downstream agent"
Agent-->>Gateway : "Response"
end
alt Delegation required
Gateway->>Delegation : "Exchange token for delegated access"
Delegation-->>Gateway : "Delegated token with metrics"
end
Gateway-->>Handler : "Normalized result"
Handler-->>Client : "HTTP Response"
```

**Diagram sources**
- [app.py](file://products/tool-gateway/src/api_gateway/app.py)
- [router.py](file://products/tool-gateway/src/api_gateway/api/router.py)
- [routes/chat.py](file://products/tool-gateway/src/api_gateway/api/routes/chat.py)
- [routes/tools.py](file://products/tool-gateway/src/api_gateway/api/routes/tools.py)
- [routes/auth.py](file://products/tool-gateway/src/api_gateway/api/routes/auth.py)
- [routes/identity.py](file://products/tool-gateway/src/api_gateway/api/routes/identity.py)
- [routes/sessions.py](file://products/tool-gateway/src/api_gateway/api/routes/sessions.py)
- [routes/runtime.py](file://products/tool-gateway/src/api_gateway/api/routes/runtime.py)
- [routes/health.py](file://products/tool-gateway/src/api_gateway/api/routes/health.py)
- [dependencies.py](file://products/tool-gateway/src/api_gateway/core/dependencies.py)
- [policy_engine.py](file://products/tool-gateway/src/api_gateway/services/policy_engine.py)
- [token_verifier.py](file://products/tool-gateway/src/api_gateway/services/token_verifier.py)
- [gateway_service.py](file://products/tool-gateway/src/api_gateway/services/gateway_service.py)
- [delegation_client.py](file://products/tool-gateway/src/api_gateway/services/delegation_client.py)
- [registry.py](file://products/tool-gateway/src/api_gateway/tools/registry.py)
- [base.py](file://products/tool-gateway/src/api_gateway/tools/base.py)
- [k8s_connector.py](file://products/tool-gateway/src/api_gateway/tools/k8s_connector.py)
- [agent_client.py](file://products/tool-gateway/src/api_gateway/services/agent_client.py)

## Detailed Component Analysis

### FastAPI Application Setup and Middleware Stack
- Application initialization includes lifespan management, CORS, and global state setup.
- Middleware order ensures security and observability are applied before routing.
- Request context is attached early to propagate identity and correlation IDs.

```mermaid
flowchart TD
Start(["App Startup"]) --> LoadConfig["Load Configuration"]
LoadConfig --> InitMiddleware["Initialize Middleware Stack"]
InitMiddleware --> RegisterRoutes["Register Domain Routers"]
RegisterRoutes --> AttachDeps["Attach Dependency Providers"]
AttachDeps --> Ready(["Ready to Serve"])
```

**Diagram sources**
- [app.py](file://products/tool-gateway/src/api_gateway/app.py)
- [dependencies.py](file://products/tool-gateway/src/api_gateway/core/dependencies.py)

**Section sources**
- [app.py](file://products/tool-gateway/src/api_gateway/app.py)
- [dependencies.py](file://products/tool-gateway/src/api_gateway/core/dependencies.py)

### Router and Request Routing Mechanisms
- The router mounts domain-specific route modules under versioned prefixes.
- Each route module defines endpoints for its domain (chat, tools, auth, identity, sessions, runtime, health).
- Path-based dispatching maps incoming requests to handlers with typed parameters and response models.

```mermaid
graph LR
Root["/api/v1"] --> Chat["/chat"]
Root --> Tools["/tools"]
Root --> Auth["/auth"]
Root --> Identity["/identity"]
Root --> Sessions["/sessions"]
Root --> Runtime["/runtime"]
Root --> Health["/health"]
```

**Diagram sources**
- [router.py](file://products/tool-gateway/src/api_gateway/api/router.py)
- [routes/chat.py](file://products/tool-gateway/src/api_gateway/api/routes/chat.py)
- [routes/tools.py](file://products/tool-gateway/src/api_gateway/api/routes/tools.py)
- [routes/auth.py](file://products/tool-gateway/src/api_gateway/api/routes/auth.py)
- [routes/identity.py](file://products/tool-gateway/src/api_gateway/api/routes/identity.py)
- [routes/sessions.py](file://products/tool-gateway/src/api_gateway/api/routes/sessions.py)
- [routes/runtime.py](file://products/tool-gateway/src/api_gateway/api/routes/runtime.py)
- [routes/health.py](file://products/tool-gateway/src/api_gateway/api/routes/health.py)

**Section sources**
- [router.py](file://products/tool-gateway/src/api_gateway/api/router.py)
- [routes/chat.py](file://products/tool-gateway/src/api_gateway/api/routes/chat.py)
- [routes/tools.py](file://products/tool-gateway/src/api_gateway/api/routes/tools.py)
- [routes/auth.py](file://products/tool-gateway/src/api_gateway/api/routes/auth.py)
- [routes/identity.py](file://products/tool-gateway/src/api_gateway/api/routes/identity.py)
- [routes/sessions.py](file://products/tool-gateway/src/api_gateway/api/routes/sessions.py)
- [routes/runtime.py](file://products/tool-gateway/src/api_gateway/api/routes/runtime.py)
- [routes/health.py](file://products/tool-gateway/src/api_gateway/api/routes/health.py)

### Request Lifecycle: From Incoming HTTP to Tool Execution
- Authentication: Token verification extracts identity context with enhanced audience claim validation.
- Policy Enforcement: Policy engine evaluates rules against request attributes.
- Orchestration: Gateway service coordinates tool resolution, execution, and delegation operations.
- Tool Execution: Registry resolves tool by name; concrete tool executes operation.
- Response Generation: Normalized response model with observability metadata and metrics tracking.

```mermaid
flowchart TD
Ingress["Incoming HTTP Request"] --> ValidateAuth["Validate Token with Audience"]
ValidateAuth --> ExtractContext["Extract Identity Context"]
ExtractContext --> EvaluatePolicy["Evaluate Policy Rules"]
EvaluatePolicy --> Decision{"Allowed?"}
Decision --> |No| Deny["Return 403 Forbidden"]
Decision --> |Yes| CheckDelegation{"Delegation Required?"}
CheckDelegation --> |Yes| ExchangeToken["Exchange Token via DelegationClient"]
CheckDelegation --> |No| ResolveTool["Resolve Tool by Name"]
ExchangeToken --> RecordMetrics["Record Delegation Metrics"]
RecordMetrics --> ResolveTool
ResolveTool --> ExecuteTool["Execute Tool"]
ExecuteTool --> Normalize["Normalize Response"]
Normalize --> Observe["Record Metrics/Traces"]
Observe --> Respond["Return HTTP Response"]
```

**Diagram sources**
- [routes/tools.py](file://products/tool-gateway/src/api_gateway/api/routes/tools.py)
- [routes/chat.py](file://products/tool-gateway/src/api_gateway/api/routes/chat.py)
- [token_verifier.py](file://products/tool-gateway/src/api_gateway/services/token_verifier.py)
- [policy_engine.py](file://products/tool-gateway/src/api_gateway/services/policy_engine.py)
- [gateway_service.py](file://products/tool-gateway/src/api_gateway/services/gateway_service.py)
- [delegation_client.py](file://products/tool-gateway/src/api_gateway/services/delegation_client.py)
- [registry.py](file://products/tool-gateway/src/api_gateway/tools/registry.py)
- [base.py](file://products/tool-gateway/src/api_gateway/tools/base.py)
- [k8s_connector.py](file://products/tool-gateway/src/api_gateway/tools/k8s_connector.py)
- [agent_client.py](file://products/tool-gateway/src/api_gateway/services/agent_client.py)

**Section sources**
- [routes/tools.py](file://products/tool-gateway/src/api_gateway/api/routes/tools.py)
- [routes/chat.py](file://products/tool-gateway/src/api_gateway/api/routes/chat.py)
- [token_verifier.py](file://products/tool-gateway/src/api_gateway/services/token_verifier.py)
- [policy_engine.py](file://products/tool-gateway/src/api_gateway/services/policy_engine.py)
- [gateway_service.py](file://products/tool-gateway/src/api_gateway/services/gateway_service.py)
- [delegation_client.py](file://products/tool-gateway/src/api_gateway/services/delegation_client.py)
- [registry.py](file://products/tool-gateway/src/api_gateway/tools/registry.py)
- [base.py](file://products/tool-gateway/src/api_gateway/tools/base.py)
- [k8s_connector.py](file://products/tool-gateway/src/api_gateway/tools/k8s_connector.py)
- [agent_client.py](file://products/tool-gateway/src/api_gateway/services/agent_client.py)

### Dependency Injection Patterns
- Centralized dependency providers expose configuration, observability, metrics, telemetry, request context, and runtime settings.
- Route handlers and services receive these dependencies via FastAPI's dependency injection mechanism.
- This pattern ensures testability, configurability, and separation of concerns.

```mermaid
classDiagram
class Dependencies {
+config()
+observability()
+metrics()
+telemetry()
+request_context()
+runtime_settings()
}
class Config {
+load_env()
+get(key)
}
class Observability {
+init_tracer()
+init_logger()
}
class Metrics {
+register_counter()
+increment()
}
class Telemetry {
+record_event()
+flush()
}
class RequestContext {
+set_correlation_id()
+get_identity()
}
class RuntimeSettings {
+get_timeout()
+get_retries()
}
Dependencies --> Config : "provides"
Dependencies --> Observability : "provides"
Dependencies --> Metrics : "provides"
Dependencies --> Telemetry : "provides"
Dependencies --> RequestContext : "provides"
Dependencies --> RuntimeSettings : "provides"
```

**Diagram sources**
- [dependencies.py](file://products/tool-gateway/src/api_gateway/core/dependencies.py)
- [config.py](file://products/tool-gateway/src/api_gateway/core/config.py)
- [observability.py](file://products/tool-gateway/src/api_gateway/core/observability.py)
- [metrics.py](file://products/tool-gateway/src/api_gateway/core/metrics.py)
- [telemetry.py](file://products/tool-gateway/src/api_gateway/core/telemetry.py)
- [request_context.py](file://products/tool-gateway/src/api_gateway/core/request_context.py)
- [runtime.py](file://products/tool-gateway/src/api_gateway/core/runtime.py)

**Section sources**
- [dependencies.py](file://products/tool-gateway/src/api_gateway/core/dependencies.py)
- [config.py](file://products/tool-gateway/src/api_gateway/core/config.py)
- [observability.py](file://products/tool-gateway/src/api_gateway/core/observability.py)
- [metrics.py](file://products/tool-gateway/src/api_gateway/core/metrics.py)
- [telemetry.py](file://products/tool-gateway/src/api_gateway/core/telemetry.py)
- [request_context.py](file://products/tool-gateway/src/api_gateway/core/request_context.py)
- [runtime.py](file://products/tool-gateway/src/api_gateway/core/runtime.py)

### Policy Engine and Token Verifier
- PolicyEngine loads policy definitions (YAML) and evaluates them against request attributes such as method, path, headers, and identity context.
- TokenVerifier validates tokens, decodes claims, and constructs an identity context used by policy evaluation and downstream services with enhanced audience claim validation.

```mermaid
sequenceDiagram
participant Handler as "Route Handler"
participant TV as "TokenVerifier"
participant PE as "PolicyEngine"
participant GC as "GatewayService"
Handler->>TV : "verify_token(request)"
TV-->>Handler : "identity_context (with audience validation)"
Handler->>PE : "evaluate_policy(identity_context, request)"
PE-->>Handler : "decision + metadata"
Handler->>GC : "orchestrate(identity_context, decision)"
```

**Diagram sources**
- [token_verifier.py](file://products/tool-gateway/src/api_gateway/services/token_verifier.py)
- [policy_engine.py](file://products/tool-gateway/src/api_gateway/services/policy_engine.py)
- [gateway_service.py](file://products/tool-gateway/src/api_gateway/services/gateway_service.py)

**Section sources**
- [token_verifier.py](file://products/tool-gateway/src/api_gateway/services/token_verifier.py)
- [policy_engine.py](file://products/tool-gateway/src/api_gateway/services/policy_engine.py)

### Tool Registry and Execution
- ToolRegistry discovers and caches tool implementations based on names provided in requests.
- Base defines the abstract interface for tools; K8sConnector implements Kubernetes operations.
- GatewayService orchestrates tool resolution and execution, normalizing results and handling errors.

```mermaid
classDiagram
class ToolRegistry {
+resolve(name) Tool
+register(name, tool)
+list_tools() list
}
class BaseTool {
+execute(input) Result
+validate_input(input) bool
}
class K8sConnector {
+execute(input) Result
+validate_input(input) bool
}
class GatewayService {
+invoke_tool(name, input) Result
+handle_error(error) Error
}
ToolRegistry --> BaseTool : "manages"
BaseTool <|-- K8sConnector : "implements"
GatewayService --> ToolRegistry : "uses"
```

**Diagram sources**
- [registry.py](file://products/tool-gateway/src/api_gateway/tools/registry.py)
- [base.py](file://products/tool-gateway/src/api_gateway/tools/base.py)
- [k8s_connector.py](file://products/tool-gateway/src/api_gateway/tools/k8s_connector.py)
- [gateway_service.py](file://products/tool-gateway/src/api_gateway/services/gateway_service.py)

**Section sources**
- [registry.py](file://products/tool-gateway/src/api_gateway/tools/registry.py)
- [base.py](file://products/tool-gateway/src/api_gateway/tools/base.py)
- [k8s_connector.py](file://products/tool-gateway/src/api_gateway/tools/k8s_connector.py)
- [gateway_service.py](file://products/tool-gateway/src/api_gateway/services/gateway_service.py)

### Agent Client Integration
- AgentClient provides communication with downstream agent services when tool execution is not applicable.
- It encapsulates retries, timeouts, and error mapping to standardized responses.

```mermaid
sequenceDiagram
participant GS as "GatewayService"
participant AC as "AgentClient"
participant Agent as "Downstream Agent"
GS->>AC : "call_agent(operation, payload)"
AC->>Agent : "HTTP/gRPC call"
Agent-->>AC : "response or error"
AC-->>GS : "normalized result or mapped error"
```

**Diagram sources**
- [agent_client.py](file://products/tool-gateway/src/api_gateway/services/agent_client.py)
- [gateway_service.py](file://products/tool-gateway/src/api_gateway/services/gateway_service.py)

**Section sources**
- [agent_client.py](file://products/tool-gateway/src/api_gateway/services/agent_client.py)
- [gateway_service.py](file://products/tool-gateway/src/api_gateway/services/gateway_service.py)

## Delegation Client Implementation

The delegation client provides secure token exchange capabilities for cross-service authentication and authorization. It handles the complete delegation workflow including token exchange, caching, and comprehensive metrics tracking.

### Key Features
- **Secure Token Exchange**: Implements OAuth 2.0 delegation patterns for secure cross-service communication
- **Caching Layer**: Caches delegated tokens to reduce overhead and improve performance
- **Metrics Tracking**: Tracks delegation operations with detailed metrics for monitoring and analysis
- **Error Handling**: Comprehensive error handling with retry logic and fallback mechanisms
- **Configuration Management**: Supports dynamic configuration for delegation endpoints and policies

### Architecture Components
```mermaid
classDiagram
class DelegationClient {
+exchange_token(client_id, scopes) Token
+get_cached_token(client_id) Token
+invalidate_cache(client_id) void
+record_metrics(operation, status) void
}
class TokenCache {
+get(key) Token
+set(key, token, ttl) void
+delete(key) void
+cleanup_expired() void
}
class MetricsTracker {
+increment_delegation_exchange_total() void
+increment_delegation_cache_total() void
+record_delegation_latency(duration) void
}
class ConfigManager {
+get_delegation_config() Config
+validate_config(config) bool
+reload_config() void
}
DelegationClient --> TokenCache : "uses"
DelegationClient --> MetricsTracker : "uses"
DelegationClient --> ConfigManager : "uses"
```

**Diagram sources**
- [delegation_client.py](file://products/tool-gateway/src/api_gateway/services/delegation_client.py)

### Delegation Workflow
```mermaid
sequenceDiagram
participant Client as "Client"
participant Gateway as "GatewayService"
participant Delegation as "DelegationClient"
participant Cache as "TokenCache"
participant Broker as "Identity Broker"
participant Metrics as "MetricsTracker"
Client->>Gateway : "Request requiring delegation"
Gateway->>Delegation : "exchange_token(client_id, scopes)"
Delegation->>Cache : "get_cached_token(client_id)"
alt Cached token exists
Cache-->>Delegation : "cached_token"
Delegation->>Metrics : "increment_delegation_cache_total()"
Delegation-->>Gateway : "cached_token"
else No cached token
Delegation->>Broker : "request_delegated_token(client_id, scopes)"
Broker-->>Delegation : "delegated_token"
Delegation->>Cache : "set_token(client_id, token, ttl)"
Delegation->>Metrics : "increment_delegation_exchange_total()"
Delegation-->>Gateway : "delegated_token"
end
Gateway-->>Client : "Proceed with delegated access"
```

**Diagram sources**
- [delegation_client.py](file://products/tool-gateway/src/api_gateway/services/delegation_client.py)

**Section sources**
- [delegation_client.py](file://products/tool-gateway/src/api_gateway/services/delegation_client.py)

## Enhanced Token Verification

The token verification system has been enhanced with audience claim validation to ensure tokens are intended for the correct service and prevent token misuse across different services.

### Audience Claim Validation
- **Audience Validation**: Ensures tokens contain the correct `aud` claim matching the gateway service identifier
- **Issuer Verification**: Validates token issuer against configured trusted issuers
- **Scope Validation**: Checks requested scopes against allowed scopes for the service
- **Expiration Handling**: Properly handles token expiration and refresh scenarios

### Enhanced Verification Process
```mermaid
flowchart TD
Start(["Token Received"]) --> Decode["Decode Token Claims"]
Decode --> ValidateAudience{"Valid Audience?"}
ValidateAudience --> |No| Reject["Reject Token - Invalid Audience"]
ValidateAudience --> |Yes| ValidateIssuer{"Valid Issuer?"}
ValidateIssuer --> |No| Reject
ValidateIssuer --> |Yes| ValidateScopes{"Scopes Valid?"}
ValidateScopes --> |No| Reject
ValidateScopes --> |Yes| BuildContext["Build Identity Context"]
BuildContext --> Return["Return Verified Context"]
```

**Diagram sources**
- [token_verifier.py](file://products/tool-gateway/src/api_gateway/services/token_verifier.py)

**Section sources**
- [token_verifier.py](file://products/tool-gateway/src/api_gateway/services/token_verifier.py)

## Metrics and Observability

The gateway now includes comprehensive metrics tracking for delegation operations and enhanced observability across all components.

### Delegation Metrics
- **delegation_exchange_total**: Tracks total number of token exchange operations
- **delegation_cache_total**: Tracks cache hits and misses for delegated tokens
- **delegation_latency_seconds**: Measures time taken for delegation operations
- **delegation_errors_total**: Counts failed delegation attempts with error types

### Enhanced Metrics Implementation
```mermaid
graph TB
subgraph "Metrics Collection"
EXCHANGE["delegation_exchange_total"]
CACHE["delegation_cache_total"]
LATENCY["delegation_latency_seconds"]
ERRORS["delegation_errors_total"]
end
subgraph "Observability"
TRACING["Distributed Tracing"]
LOGGING["Structured Logging"]
MONITORING["System Monitoring"]
end
EXCHANGE --> TRACING
CACHE --> TRACING
LATENCY --> MONITORING
ERRORS --> LOGGING
TRACING --> MONITORING
LOGGING --> MONITORING
```

**Diagram sources**
- [metrics.py](file://products/tool-gateway/src/api_gateway/core/metrics.py)
- [delegation_client.py](file://products/tool-gateway/src/api_gateway/services/delegation_client.py)

### Monitoring Integration Points
- **Prometheus Metrics**: Export metrics in Prometheus-compatible format
- **OpenTelemetry Integration**: Distributed tracing with span context propagation
- **Health Checks**: Comprehensive health check endpoints for service monitoring
- **Alerting Rules**: Predefined alerting rules for critical metrics thresholds

**Section sources**
- [metrics.py](file://products/tool-gateway/src/api_gateway/core/metrics.py)
- [delegation_client.py](file://products/tool-gateway/src/api_gateway/services/delegation_client.py)
- [observability.py](file://products/tool-gateway/src/api_gateway/core/observability.py)

## Dependency Analysis
The gateway exhibits low coupling between layers due to dependency injection and clear interfaces:
- Routes depend on services via dependencies.
- Services depend on policy, token verification, delegation client, and tool registry.
- Tools implement a common base interface enabling pluggable connectors.
- Observability and metrics are injected uniformly across components.

```mermaid
graph TB
Routes["API Routes"] --> Services["Services"]
Services --> Policy["PolicyEngine"]
Services --> Token["TokenVerifier"]
Services --> Delegation["DelegationClient"]
Services --> Registry["ToolRegistry"]
Registry --> Base["BaseTool"]
Base --> K8s["K8sConnector"]
Services --> Agent["AgentClient"]
All["All Components"] --> Obs["Observability/Metrics/Telemetry"]
```

**Diagram sources**
- [router.py](file://products/tool-gateway/src/api_gateway/api/router.py)
- [gateway_service.py](file://products/tool-gateway/src/api_gateway/services/gateway_service.py)
- [policy_engine.py](file://products/tool-gateway/src/api_gateway/services/policy_engine.py)
- [token_verifier.py](file://products/tool-gateway/src/api_gateway/services/token_verifier.py)
- [delegation_client.py](file://products/tool-gateway/src/api_gateway/services/delegation_client.py)
- [registry.py](file://products/tool-gateway/src/api_gateway/tools/registry.py)
- [base.py](file://products/tool-gateway/src/api_gateway/tools/base.py)
- [k8s_connector.py](file://products/tool-gateway/src/api_gateway/tools/k8s_connector.py)
- [agent_client.py](file://products/tool-gateway/src/api_gateway/services/agent_client.py)
- [observability.py](file://products/tool-gateway/src/api_gateway/core/observability.py)
- [metrics.py](file://products/tool-gateway/src/api_gateway/core/metrics.py)
- [telemetry.py](file://products/tool-gateway/src/api_gateway/core/telemetry.py)

**Section sources**
- [router.py](file://products/tool-gateway/src/api_gateway/api/router.py)
- [gateway_service.py](file://products/tool-gateway/src/api_gateway/services/gateway_service.py)
- [policy_engine.py](file://products/tool-gateway/src/api_gateway/services/policy_engine.py)
- [token_verifier.py](file://products/tool-gateway/src/api_gateway/services/token_verifier.py)
- [delegation_client.py](file://products/tool-gateway/src/api_gateway/services/delegation_client.py)
- [registry.py](file://products/tool-gateway/src/api_gateway/tools/registry.py)
- [base.py](file://products/tool-gateway/src/api_gateway/tools/base.py)
- [k8s_connector.py](file://products/tool-gateway/src/api_gateway/tools/k8s_connector.py)
- [agent_client.py](file://products/tool-gateway/src/api_gateway/services/agent_client.py)
- [observability.py](file://products/tool-gateway/src/api_gateway/core/observability.py)
- [metrics.py](file://products/tool-gateway/src/api_gateway/core/metrics.py)
- [telemetry.py](file://products/tool-gateway/src/api_gateway/core/telemetry.py)

## Performance Considerations
- Connection pooling: Ensure HTTP clients (AgentClient, external tool calls, delegation client) use connection pools to reduce latency.
- Caching: Cache tool resolutions, policy decisions, and delegated tokens where appropriate to avoid repeated computation.
- Timeouts and retries: Configure sensible timeouts and retry policies in runtime settings, agent client, and delegation client.
- Concurrency: Leverage FastAPI's async capabilities for I/O-bound operations; avoid blocking calls.
- Metrics and tracing: Instrument hot paths to identify bottlenecks and optimize accordingly.
- Resource limits: Set CPU/memory limits per container and scale horizontally based on metrics.
- **Updated** Delegation cache optimization: Implement intelligent cache eviction policies and pre-warming strategies for frequently accessed tokens.

## Troubleshooting Guide
Common issues and strategies:
- Authentication failures: Verify token format, issuer, and expiration; inspect token verifier logs with audience validation details.
- Policy denials: Review policy definitions and request attributes; ensure identity context is correctly extracted.
- Tool execution errors: Check tool registry entries, input validation, and underlying connector logs.
- Downstream agent errors: Inspect agent client retries, timeouts, and error mappings.
- Delegation failures: Monitor delegation metrics, check cache status, and verify identity broker connectivity.
- Observability gaps: Confirm tracing spans and metrics counters are emitted; validate instrumentation initialization.
- **Updated** Audience validation issues: Verify service identifiers match configured audiences and check token issuance policies.

**Section sources**
- [token_verifier.py](file://products/tool-gateway/src/api_gateway/services/token_verifier.py)
- [policy_engine.py](file://products/tool-gateway/src/api_gateway/services/policy_engine.py)
- [registry.py](file://products/tool-gateway/src/api_gateway/tools/registry.py)
- [agent_client.py](file://products/tool-gateway/src/api_gateway/services/agent_client.py)
- [delegation_client.py](file://products/tool-gateway/src/api_gateway/services/delegation_client.py)
- [observability.py](file://products/tool-gateway/src/api_gateway/core/observability.py)
- [metrics.py](file://products/tool-gateway/src/api_gateway/core/metrics.py)
- [telemetry.py](file://products/tool-gateway/src/api_gateway/core/telemetry.py)

## Conclusion
The Tool Gateway Service provides a robust, extensible, and observable entry point for API requests. Its layered architecture, dependency injection, and policy-driven enforcement enable secure and scalable tool execution. **Updated** The addition of delegation client capabilities enhances cross-service authentication while maintaining security through audience validation and comprehensive metrics tracking. By following the documented request flow and leveraging the provided diagrams, teams can extend functionality, troubleshoot effectively, and maintain high performance and reliability across distributed service architectures.