# Project Overview

<cite>
**Referenced Files in This Document**
- [README.md](file://README.md)
- [SECURITY.md](file://SECURITY.md)
- [CONTRIBUTING.md](file://CONTRIBUTING.md)
- [Makefile](file://Makefile)
- [agent-platform README.md](file://products/agent-platform/README.md)
- [identity-broker README.md](file://products/identity-broker/README.md)
- [operator-portal README.md](file://products/operator-portal/README.md)
- [tool-gateway README.md](file://products/tool-gateway/README.md)
- [platform GitOps README.md](file://shared/platform-ops/gitops/dev-k8s/README.md)
- [runtime profiles README.md](file://shared/platform-ops/gitops/runtime-profiles/README.md)
- [agent platform app.py](file://products/agent-platform/src/agent_platform/app.py)
- [agent platform main.py](file://products/agent-platform/src/agent_platform/main.py)
- [agent platform providers registry](file://products/agent-platform/src/agent_platform/providers/registry.py)
- [agent platform runtime kernel](file://products/agent-platform/src/agent_platform/runtime_kernel.py)
- [agent platform session service](file://products/agent-platform/src/agent_platform/services/session_service.py)
- [agent platform gateway tools](file://products/agent-platform/src/agent_platform/tools/gateway_tools.py)
- [identity broker app.py](file://products/identity-broker/src/identity_service/app.py)
- [identity broker identity service](file://products/identity-broker/src/identity_service/services/identity_service.py)
- [identity broker token service](file://products/identity-broker/src/identity_service/services/token_service.py)
- [tool gateway app.py](file://products/tool-gateway/src/api_gateway/app.py)
- [tool gateway gateway service](file://products/tool-gateway/src/api_gateway/services/gateway_service.py)
- [tool gateway policy engine](file://products/tool-gateway/src/api_gateway/services/policy_engine.py)
- [tool gateway k8s connector](file://products/tool-gateway/src/api_gateway/tools/k8s_connector.py)
- [tool gateway policy default](file://products/tool-gateway/src/api_gateway/policies/policy-default.yaml)
- [shared contracts schemas README](file://shared/shared-contracts/README.md)
- [observability conventions](file://shared/shared-contracts/observability-conventions.md)
- [dev-k8s base kustomization](file://shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml)
- [dev-k8s agent deployment](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml)
- [dev-k8s identity deployment](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml)
- [dev-k8s tool gateway deployment](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/api-gateway-deployment.yaml)
- [dev-k8s redis deployment](file://shared/platform-ops/gitops/dev-k8s/base/infra/redis-deployment.yaml)
- [openai runtime profile configmap](file://shared/platform-ops/gitops/runtime-profiles/openai/configmap.yaml)
- [dashscope runtime profile configmap](file://shared/platform-ops/gitops/runtime-profiles/dashscope/configmap.yaml)
- [deepseek runtime profile configmap](file://shared/platform-ops/gitops/runtime-profiles/deepseek/configmap.yaml)
</cite>

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
Luban AIOps Platform is an AI-powered operations automation system designed to orchestrate intelligent agents, enforce policies, manage identities, and execute operational tools safely at scale. It provides a microservices-based runtime that integrates with Kubernetes for orchestration, external AI providers (OpenAI, DashScope, DeepSeek), and identity providers via OIDC. The platform emphasizes secure-by-design operations, observability, and GitOps-driven deployments.

Key value propositions:
- Centralized AI agent orchestration with standardized contracts
- Strong identity and authorization model with OIDC integration
- Policy enforcement as code for safe tool execution
- Extensible tool execution framework for Kubernetes and other systems
- End-to-end observability and telemetry
- GitOps-native deployment and configuration management

Target audience:
- Developers building AI-powered automation workflows
- Operators managing production-grade platforms
- Security teams enforcing compliance and governance

**Section sources**
- [README.md](file://README.md)
- [SECURITY.md](file://SECURITY.md)
- [CONTRIBUTING.md](file://CONTRIBUTING.md)

## Project Structure
The platform follows a product-based microservices architecture with shared contracts and GitOps infrastructure:

```mermaid
graph TB
subgraph "Products"
AP["Agent Platform"]
IB["Identity Broker"]
TG["Tool Gateway"]
OP["Operator Portal"]
end
subgraph "Shared"
SC["Shared Contracts"]
OPS["Platform Ops (GitOps)"]
end
subgraph "External"
K8S["Kubernetes API"]
AI["AI Providers<br/>OpenAI/DashScope/DeepSeek"]
IDP["OIDC Identity Provider"]
end
AP --> SC
IB --> SC
TG --> SC
TG --> K8S
AP --> AI
IB --> IDP
OPS --> AP
OPS --> IB
OPS --> TG
```

**Diagram sources**
- [agent-platform README.md](file://products/agent-platform/README.md)
- [identity-broker README.md](file://products/identity-broker/README.md)
- [tool-gateway README.md](file://products/tool-gateway/README.md)
- [shared contracts schemas README](file://shared/shared-contracts/README.md)
- [platform GitOps README.md](file://shared/platform-ops/gitops/dev-k8s/README.md)

**Section sources**
- [agent-platform README.md](file://products/agent-platform/README.md)
- [identity-broker README.md](file://products/identity-broker/README.md)
- [tool-gateway README.md](file://products/tool-gateway/README.md)
- [shared contracts schemas README](file://shared/shared-contracts/README.md)
- [platform GitOps README.md](file://shared/platform-ops/gitops/dev-k8s/README.md)

## Core Components
The platform consists of four primary microservices:

### Agent Platform
- Orchestrates AI agents with provider abstraction
- Manages sessions and runtime context
- Integrates with external AI providers through a unified interface
- Provides tool execution capabilities

### Identity Broker
- Handles OIDC authentication and authorization
- Issues and validates tokens for service-to-service communication
- Manages user and service identities

### Tool Gateway
- Central entry point for all API requests
- Enforces policies before tool execution
- Routes requests to appropriate services
- Integrates with Kubernetes for cluster operations

### Operator Portal
- Web-based interface for platform management
- Provides monitoring and control capabilities

**Section sources**
- [agent-platform README.md](file://products/agent-platform/README.md)
- [identity-broker README.md](file://products/identity-broker/README.md)
- [tool-gateway README.md](file://products/tool-gateway/README.md)
- [operator-portal README.md](file://products/operator-portal/README.md)

## Architecture Overview
The platform implements a layered microservices architecture with clear separation of concerns:

```mermaid
sequenceDiagram
participant Client as "Client Application"
participant Gateway as "Tool Gateway"
participant Auth as "Identity Broker"
participant Agent as "Agent Platform"
participant K8S as "Kubernetes API"
participant AI as "AI Provider"
Client->>Gateway : HTTP Request
Gateway->>Auth : Validate Token
Auth-->>Gateway : Access Granted
Gateway->>Gateway : Policy Enforcement
Gateway->>Agent : Route Request
Agent->>AI : Execute AI Operation
AI-->>Agent : Response
Agent->>K8S : Execute Tool (if needed)
K8S-->>Agent : Result
Agent-->>Gateway : Processed Response
Gateway-->>Client : Final Response
```

**Diagram sources**
- [tool gateway app.py](file://products/tool-gateway/src/api_gateway/app.py)
- [identity broker app.py](file://products/identity-broker/src/identity_service/app.py)
- [agent platform app.py](file://products/agent-platform/src/agent_platform/app.py)

**Section sources**
- [tool gateway app.py](file://products/tool-gateway/src/api_gateway/app.py)
- [identity broker app.py](file://products/identity-broker/src/identity_service/app.py)
- [agent platform app.py](file://products/agent-platform/src/agent_platform/app.py)

## Detailed Component Analysis

### Agent Platform Architecture
The Agent Platform serves as the core AI orchestration engine with provider abstraction and session management:

```mermaid
classDiagram
class AgentApp {
+initialize_providers()
+handle_request(request)
+manage_session(session_id)
}
class RuntimeKernel {
+execute_agent(agent_config)
+manage_context(context)
+handle_errors(error)
}
class ProviderRegistry {
+register_provider(provider)
+get_provider(name)
+list_providers()
}
class SessionService {
+create_session(user_id)
+update_session(session_id, data)
+delete_session(session_id)
}
class GatewayTools {
+execute_tool(tool_name, params)
+validate_permissions(user_id, tool_name)
+log_execution(execution_id)
}
AgentApp --> RuntimeKernel : "uses"
AgentApp --> ProviderRegistry : "manages"
AgentApp --> SessionService : "coordinates"
AgentApp --> GatewayTools : "executes"
```

**Diagram sources**
- [agent platform app.py](file://products/agent-platform/src/agent_platform/app.py)
- [agent platform runtime kernel](file://products/agent-platform/src/agent_platform/runtime_kernel.py)
- [agent platform providers registry](file://products/agent-platform/src/agent_platform/providers/registry.py)
- [agent platform session service](file://products/agent-platform/src/agent_platform/services/session_service.py)
- [agent platform gateway tools](file://products/agent-platform/src/agent_platform/tools/gateway_tools.py)

### Identity Management Flow
The Identity Broker handles OIDC authentication and token management:

```mermaid
sequenceDiagram
participant Client as "Client"
participant IdentityBroker as "Identity Broker"
participant OIDCProvider as "OIDC Provider"
participant Services as "Platform Services"
Client->>IdentityBroker : Login Request
IdentityBroker->>OIDCProvider : Redirect to Auth
OIDCProvider-->>IdentityBroker : Authorization Code
IdentityBroker->>OIDCProvider : Exchange Code for Tokens
OIDCProvider-->>IdentityBroker : Access & Refresh Tokens
IdentityBroker->>IdentityBroker : Generate Internal Token
IdentityBroker-->>Client : JWT Token
Client->>Services : API Call with Token
Services->>IdentityBroker : Validate Token
IdentityBroker-->>Services : User Context
```

**Diagram sources**
- [identity broker app.py](file://products/identity-broker/src/identity_service/app.py)
- [identity broker identity service](file://products/identity-broker/src/identity_service/services/identity_service.py)
- [identity broker token service](file://products/identity-broker/src/identity_service/services/token_service.py)

### Tool Execution Framework
The Tool Gateway provides centralized tool execution with policy enforcement:

```mermaid
flowchart TD
Start([Request Received]) --> ValidateToken["Validate Authentication Token"]
ValidateToken --> TokenValid{"Token Valid?"}
TokenValid --> |No| ReturnError["Return 401 Unauthorized"]
TokenValid --> |Yes| CheckPolicy["Evaluate Policy Rules"]
CheckPolicy --> PolicyAllowed{"Policy Allows?"}
PolicyAllowed --> |No| DenyAccess["Return 403 Forbidden"]
PolicyAllowed --> |Yes| RouteRequest["Route to Target Service"]
RouteRequest --> ExecuteTool["Execute Tool if Required"]
ExecuteTool --> ToolSuccess{"Tool Success?"}
ToolSuccess --> |No| HandleError["Handle Execution Error"]
ToolSuccess --> |Yes| ProcessResponse["Process Response"]
ProcessResponse --> LogMetrics["Log Metrics & Telemetry"]
LogMetrics --> ReturnResponse["Return Response"]
HandleError --> ReturnError
ReturnError --> End([End])
ReturnResponse --> End
DenyAccess --> End
```

**Diagram sources**
- [tool gateway app.py](file://products/tool-gateway/src/api_gateway/app.py)
- [tool gateway gateway service](file://products/tool-gateway/src/api_gateway/services/gateway_service.py)
- [tool gateway policy engine](file://products/tool-gateway/src/api_gateway/services/policy_engine.py)
- [tool gateway k8s connector](file://products/tool-gateway/src/api_gateway/tools/k8s_connector.py)

**Section sources**
- [agent platform app.py](file://products/agent-platform/src/agent_platform/app.py)
- [agent platform runtime kernel](file://products/agent-platform/src/agent_platform/runtime_kernel.py)
- [agent platform providers registry](file://products/agent-platform/src/agent_platform/providers/registry.py)
- [agent platform session service](file://products/agent-platform/src/agent_platform/services/session_service.py)
- [agent platform gateway tools](file://products/agent-platform/src/agent_platform/tools/gateway_tools.py)
- [identity broker app.py](file://products/identity-broker/src/identity_service/app.py)
- [identity broker identity service](file://products/identity-broker/src/identity_service/services/identity_service.py)
- [identity broker token service](file://products/identity-broker/src/identity_service/services/token_service.py)
- [tool gateway app.py](file://products/tool-gateway/src/api_gateway/app.py)
- [tool gateway gateway service](file://products/tool-gateway/src/api_gateway/services/gateway_service.py)
- [tool gateway policy engine](file://products/tool-gateway/src/api_gateway/services/policy_engine.py)
- [tool gateway k8s connector](file://products/tool-gateway/src/api_gateway/tools/k8s_connector.py)

## Dependency Analysis
The platform maintains clear dependency boundaries between services:

```mermaid
graph LR
subgraph "External Dependencies"
K8S["Kubernetes"]
OpenAI["OpenAI"]
DashScope["DashScope"]
DeepSeek["DeepSeek"]
OIDC["OIDC Provider"]
Redis["Redis"]
end
subgraph "Platform Services"
TG["Tool Gateway"]
AP["Agent Platform"]
IB["Identity Broker"]
end
subgraph "Shared Components"
SC["Shared Contracts"]
POL["Policy Engine"]
OBS["Observability"]
end
TG --> K8S
TG --> POL
TG --> OBS
AP --> OpenAI
AP --> DashScope
AP --> DeepSeek
AP --> Redis
IB --> OIDC
IB --> OBS
AP --> SC
TG --> SC
IB --> SC
```

**Diagram sources**
- [agent platform providers registry](file://products/agent-platform/src/agent_platform/providers/registry.py)
- [tool gateway k8s connector](file://products/tool-gateway/src/api_gateway/tools/k8s_connector.py)
- [shared contracts schemas README](file://shared/shared-contracts/README.md)

**Section sources**
- [agent platform providers registry](file://products/agent-platform/src/agent_platform/providers/registry.py)
- [tool gateway k8s connector](file://products/tool-gateway/src/api_gateway/tools/k8s_connector.py)
- [shared contracts schemas README](file://shared/shared-contracts/README.md)

## Performance Considerations
The platform is designed for high-performance operations with several key considerations:

- **Connection Pooling**: Efficient resource utilization through connection pooling for external services
- **Async Processing**: Asynchronous request handling for improved throughput
- **Caching Strategies**: Session caching and response caching where appropriate
- **Resource Limits**: Container resource limits and requests for predictable performance
- **Monitoring**: Comprehensive metrics collection and alerting
- **Scalability**: Horizontal scaling capabilities for all microservices

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and their resolution strategies:

### Authentication Issues
- Verify OIDC provider configuration
- Check token validation settings
- Ensure proper certificate configuration

### Tool Execution Failures
- Review policy engine configurations
- Validate Kubernetes RBAC permissions
- Check tool-specific error logs

### Performance Problems
- Monitor resource utilization
- Analyze request latency patterns
- Review database connection pools

### Observability Setup
- Configure logging levels appropriately
- Set up metrics collection endpoints
- Implement distributed tracing

**Section sources**
- [observability conventions](file://shared/shared-contracts/observability-conventions.md)
- [tool gateway policy engine](file://products/tool-gateway/src/api_gateway/services/policy_engine.py)
- [identity broker token service](file://products/identity-broker/src/identity_service/services/token_service.py)

## Conclusion
Luban AIOps Platform provides a comprehensive solution for AI-powered operations automation through its microservices architecture. The platform successfully addresses the needs of developers, operators, and security teams by offering robust agent orchestration, strong identity management, policy enforcement, and extensible tool execution capabilities. Its GitOps-native approach ensures reliable deployments while maintaining high standards for security and observability.

The platform's design enables organizations to build sophisticated AI-powered automation workflows while maintaining full control over security, compliance, and operational aspects. With support for multiple AI providers and seamless Kubernetes integration, it provides a solid foundation for modern AI operations.

[No sources needed since this section summarizes without analyzing specific files]

## Appendices

### Deployment Architecture
The platform uses GitOps practices with Kubernetes for deployment:

```mermaid
graph TB
subgraph "Git Repository"
Config["Kubernetes Manifests"]
Policies["Policy Definitions"]
Secrets["Secret References"]
end
subgraph "CI/CD Pipeline"
Build["Build & Test"]
Validate["Validate Manifests"]
Deploy["Deploy to Cluster"]
end
subgraph "Kubernetes Cluster"
Namespace["Platform Namespace"]
Agents["Agent Pods"]
Gateway["Gateway Pods"]
Identity["Identity Pods"]
Redis["Redis Cache"]
end
Config --> Build
Policies --> Validate
Secrets --> Deploy
Build --> Validate
Validate --> Deploy
Deploy --> Namespace
Namespace --> Agents
Namespace --> Gateway
Namespace --> Identity
Namespace --> Redis
```

**Diagram sources**
- [dev-k8s base kustomization](file://shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml)
- [platform GitOps README.md](file://shared/platform-ops/gitops/dev-k8s/README.md)

### AI Provider Integration
The platform supports multiple AI providers through a unified interface:

| Provider | Configuration Key | Base URL | Authentication |
|----------|-------------------|----------|----------------|
| OpenAI | OPENAI_API_KEY | api.openai.com | API Key |
| DashScope | DASHSCOPE_API_KEY | dashscope.aliyuncs.com | API Key |
| DeepSeek | DEEPSEEK_API_KEY | api.deepseek.com | API Key |

**Section sources**
- [openai runtime profile configmap](file://shared/platform-ops/gitops/runtime-profiles/openai/configmap.yaml)
- [dashscope runtime profile configmap](file://shared/platform-ops/gitops/runtime-profiles/dashscope/configmap.yaml)
- [deepseek runtime profile configmap](file://shared/platform-ops/gitops/runtime-profiles/deepseek/configmap.yaml)

### Security Model
The platform implements a multi-layered security approach:

- **Authentication**: OIDC-based user authentication
- **Authorization**: Role-based access control with policy enforcement
- **Encryption**: TLS for all communications, encrypted secrets storage
- **Audit Logging**: Comprehensive audit trails for all operations
- **Network Security**: Network policies and service mesh integration

**Section sources**
- [SECURITY.md](file://SECURITY.md)
- [tool gateway policy engine](file://products/tool-gateway/src/api_gateway/services/policy_engine.py)
- [identity broker identity service](file://products/identity-broker/src/identity_service/services/identity_service.py)