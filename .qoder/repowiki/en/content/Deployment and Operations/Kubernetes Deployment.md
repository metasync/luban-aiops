# Kubernetes Deployment

<cite>
**Referenced Files in This Document**
- [kustomization.yaml](file://shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml)
- [platform-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/platform-gateway-deployment.yaml)
- [platform-gateway-service.yaml](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/platform-gateway-service.yaml)
- [tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)
- [tool-gateway-service.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-service.yaml)
- [platform-gateway-rbac.yaml](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/rbac.yaml)
- [tool-gateway-rbac.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/rbac.yaml)
- [platform-gateway-runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env)
- [tool-gateway-runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env)
- [shared-runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)
- [agent-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml)
- [identity-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml)
- [web-ui-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-deployment.yaml)
- [web-ui-httproute.yaml](file://shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-httproute.yaml)
- [redis-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/infra/redis-deployment.yaml)
- [skills-hub-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/skills-hub-deployment.yaml)
- [skills-hub-service.yaml](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/skills-hub-service.yaml)
- [skills-hub-runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-config.env)
- [audit-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/audit-service-deployment.yaml)
- [audit-service-runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env)
- [incident-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/incident-service/incident-service-deployment.yaml)
- [execution-runtime-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/execution-runtime/execution-runtime-deployment.yaml)
- [postgres-statefulset.yaml](file://shared/platform-ops/gitops/dev-k8s/base/infra/postgres-statefulset.yaml)
- [postgres-service.yaml](file://shared/platform-ops/gitops/dev-k8s/base/infra/postgres-service.yaml)
- [create-skills-db.sql](file://shared/platform-ops/gitops/dev-k8s/base/infra/create-skills-db.sql)
- [create-incidents-db.sql](file://shared/platform-ops/gitops/dev-k8s/base/infra/create-incidents-db.sql)
- [create-sessions-db.sql](file://shared/platform-ops/gitops/dev-k8s/base/infra/create-sessions-db.sql)
</cite>

## Update Summary
**Changes Made**
- Updated to reflect v0.25.1/v0.25.2 release synchronization with enhanced service discovery and security configurations
- Added comprehensive documentation for execution runtime service and incident service deployments
- Enhanced PostgreSQL infrastructure configuration with database initialization scripts
- Updated service link configuration across all services to prevent environment variable conflicts
- Expanded audit trail capabilities with centralized secret management
- Improved health monitoring and probe configurations for development environments

## Table of Contents
1. Overview
2. Kustomize Structure and Base Configuration
3. Platform Gateway Service
4. Tool Gateway Service
5. Identity Broker Service
6. Agent Platform Service
7. Execution Runtime Service
8. Incident Service
9. Skills Hub Service
10. Audit Service
11. Operator Portal Service
12. Infrastructure Services
13. Service Discovery and Networking
14. Persistent Storage Configuration
15. Deployment Automation
16. Rollback Procedures
17. Troubleshooting

## Overview

The Luban AIOps Platform uses a Kustomize-based deployment structure that supports both platform-gateway and tool-gateway services independently, along with comprehensive audit trail capabilities and execution runtime isolation. This architectural design replaces the previous single api-gateway deployment with two specialized gateways, each serving distinct responsibilities:

- **Platform Gateway**: Handles user-facing API requests, authentication, authorization, and agent service orchestration
- **Tool Gateway**: Manages tool execution, Kubernetes resource access, and policy enforcement for tool operations
- **Execution Runtime**: Provides isolated execution environment for agent workloads with secure handoff mechanisms
- **Incident Service**: Centralized incident management and collaboration capabilities
- **Skills Hub**: Provides skill management, ingestion, and query capabilities for AI-powered guidance and runbooks
- **Audit Service**: Centralized audit event ingestion and storage with client authentication

The deployment is organized using Kustomize overlays with a base configuration that includes all core services and their dependencies. All services are deployed with enhanced security contexts to ensure containers run as non-root users with minimal privileges. Additionally, all deployments now use `enableServiceLinks: false` to prevent Kubernetes legacy service-link environment variable injection conflicts, ensuring reliable DNS-based service discovery.

The platform features comprehensive audit trail capabilities through centralized secret management, which provisions shared audit credentials across all emitting services and automatically restarts affected deployments when audit secrets change.

## Kustomize Structure and Base Configuration

The base Kustomize configuration orchestrates all platform components through a centralized kustomization file that defines common settings, config maps, and resource references.

```mermaid
graph TD
A[Kustomization] --> B[ConfigMap Generator]
A --> C[Resources]
B --> D[Shared Runtime Config]
B --> E[Policy Config]
B --> F[Skills ConfigMaps]
B --> G[PostgreSQL Init Scripts]
C --> H[Platform Gateway]
C --> I[Tool Gateway]
C --> J[Identity Broker]
C --> K[Agent Platform]
C --> L[Execution Runtime]
C --> M[Incident Service]
C --> N[Skills Hub]
C --> O[Audit Service]
C --> P[Operator Portal]
C --> Q[Infrastructure]
H --> R[Service Account]
I --> S[Service Account + RBAC]
J --> T[Service Account]
K --> U[Service Account]
L --> V[Service Account]
M --> W[Service Account]
N --> X[Service Account]
O --> Y[Service Account]
```

**Diagram sources**
- [kustomization.yaml:1-71](file://shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml#L1-L71)

The base configuration creates a unified `platform-runtime-config` ConfigMap from multiple environment fragments including shared runtime settings, service-specific configurations, and infrastructure endpoints. The configuration also generates sample skill source ConfigMaps for SRE alerting and platform runbooks, along with PostgreSQL initialization scripts for database setup.

**Section sources**
- [kustomization.yaml:6-17](file://shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml#L6-L17)
- [kustomization.yaml:18-43](file://shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml#L18-L43)
- [shared-runtime.env:1-12](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env#L1-L12)

## Platform Gateway Service

The platform-gateway service handles user-facing API requests, authentication, authorization, and orchestrates calls to the agent service. It operates as an independent service with its own security context and configuration.

### Deployment Configuration

The platform-gateway deployment runs with dedicated service account permissions and mounts policy configurations for authorization decisions. The deployment includes comprehensive security contexts to ensure secure container execution.

**Key Features:**
- Dedicated ServiceAccount for security isolation
- Prometheus monitoring annotations for observability
- Policy configuration mounted as read-only volume
- Environment variables from shared and platform-specific config maps
- Optional secret mounting for sensitive credentials
- **Security Context**: Non-root execution with UID 1000, privilege escalation disabled, and seccomp profile enabled
- **Service Link Configuration**: `enableServiceLinks: false` prevents legacy service-link environment variable injection conflicts
- **Audit Integration**: Configured to emit audit events to the centralized audit-service with shared credentials

**Updated** Enhanced security context ensures the platform-gateway container runs with minimal privileges, preventing potential security vulnerabilities. The service link configuration ensures reliable DNS-based service discovery without conflicting environment variables. Audit integration provides comprehensive audit trail capabilities for all platform operations.

**Section sources**
- [platform-gateway-deployment.yaml:1-49](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/platform-gateway-deployment.yaml#L1-L49)
- [platform-gateway-rbac.yaml:1-5](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/rbac.yaml#L1-L5)

### Service Configuration

The platform-gateway exposes HTTP service on port 8000 for external client connections.

**Section sources**
- [platform-gateway-service.yaml:1-12](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/platform-gateway-service.yaml#L1-L12)

### Environment Variables

The platform-gateway requires specific configuration for authentication, authorization, and service communication:

| Variable | Description | Example Value |
|----------|-------------|---------------|
| AGENT_SERVICE_URL | Agent service endpoint | http://agent-service:8000 |
| PLATFORM_GATEWAY_DEV_USER | Development user override | demo.operator |
| PLATFORM_GATEWAY_REQUIRE_AUTH | Enable authentication | true |
| PLATFORM_GATEWAY_POLICY_PATH | Policy file location | /etc/luban/policy/policy.yaml |
| PLATFORM_GATEWAY_TOKEN_AUDIENCE | Token audience identifier | platform-gateway |
| PLATFORM_GATEWAY_DELEGATION_AUDIENCE | Delegated token audience | tool-gateway |
| PLATFORM_GATEWAY_SERVICE_CLIENT_ID | Service client identifier | platform-gateway |
| PLATFORM_GATEWAY_AUDIT_SERVICE_URL | Audit service endpoint | http://audit-service:8000 |
| PLATFORM_GATEWAY_AUDIT_CLIENT_ID | Audit client identifier | platform-gateway |
| PLATFORM_GATEWAY_INCIDENT_SERVICE_URL | Incident service endpoint | http://incident-service:8000 |
| PLATFORM_GATEWAY_SKILLS_HUB_URL | Skills hub endpoint | http://skills-hub:8000 |
| PLATFORM_GATEWAY_TOOL_GATEWAY_URL | Tool gateway endpoint | http://tool-gateway:8000 |

**Section sources**
- [platform-gateway-runtime-config.env:1-23](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env#L1-L23)

## Tool Gateway Service

The tool-gateway service manages tool execution, Kubernetes resource access, and policy enforcement specifically for tool operations. It provides a secure boundary between user requests and cluster resources.

### Deployment Configuration

The tool-gateway deployment includes comprehensive RBAC configuration with role-based access control for Kubernetes resources. The deployment includes enhanced security contexts to ensure secure container execution.

**Key Features:**
- Dedicated ServiceAccount with minimal permissions
- Role-based access control for pods, events, and logs
- Prometheus monitoring for operational visibility
- Policy configuration for tool execution rules
- Kubernetes integration enabled by default
- **Security Context**: Non-root execution with UID 1000, privilege escalation disabled, and seccomp profile enabled
- **Service Link Configuration**: `enableServiceLinks: false` prevents legacy service-link environment variable injection conflicts
- **Audit Integration**: Configured to emit audit events to the centralized audit-service with shared credentials

**Updated** Enhanced security context ensures the tool-gateway container runs with minimal privileges, reducing the attack surface for tool execution operations. The service link configuration ensures reliable DNS-based service discovery without conflicting environment variables. Audit integration provides comprehensive audit trail capabilities for all tool operations.

**Section sources**
- [tool-gateway-deployment.yaml:1-49](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml#L1-L49)
- [tool-gateway-rbac.yaml:1-30](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/rbac.yaml#L1-L30)

### Service Configuration

The tool-gateway exposes HTTP service on port 8000 for internal service-to-service communication.

**Section sources**
- [tool-gateway-service.yaml:1-12](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-service.yaml#L1-L12)

### RBAC Configuration

The tool-gateway has granular permissions for Kubernetes resource access:

**Permissions Granted:**
- GET and LIST operations on pods and events
- GET operations on pod logs
- Namespace-scoped role binding for security isolation

**Section sources**
- [tool-gateway-rbac.yaml:7-30](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/rbac.yaml#L7-L30)

### Environment Variables

The tool-gateway requires configuration for authentication, Kubernetes integration, and policy enforcement:

| Variable | Description | Example Value |
|----------|-------------|---------------|
| GATEWAY_DEV_USER | Development user override | demo.operator |
| GATEWAY_REQUIRE_AUTH | Enable authentication | true |
| GATEWAY_POLICY_PATH | Policy file location | /etc/luban/policy/policy.yaml |
| GATEWAY_K8S_ENABLED | Enable Kubernetes integration | true |
| GATEWAY_K8S_NAMESPACE | Target namespace | dev-luban-aiops |
| GATEWAY_MUTATING_TOOLS_ENABLED | Enable mutating tools | false |
| GATEWAY_TOKEN_AUDIENCE | Token audience identifier | tool-gateway |
| GATEWAY_AUDIT_SERVICE_URL | Audit service endpoint | http://audit-service:8000 |
| GATEWAY_AUDIT_CLIENT_ID | Audit client identifier | tool-gateway |
| GATEWAY_SKILLS_SERVICE_URL | Skills service endpoint | http://skills-hub:8000 |
| GATEWAY_INCIDENTS_SERVICE_URL | Incidents service endpoint | http://incident-service:8000 |

**Section sources**
- [tool-gateway-runtime-config.env:1-44](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env#L1-L44)

## Identity Broker Service

The identity-broker service provides authentication and authorization services for the platform, handling OIDC flows and token management.

### Deployment Configuration

The identity-broker deployment includes runtime configuration and optional secrets for OIDC client credentials. The deployment includes enhanced security contexts to ensure secure container execution.

**Key Features:**
- Authentication service for platform users
- OIDC client management
- Token exchange capabilities
- Integration with external identity providers
- **Security Context**: Non-root execution with UID 1000, privilege escalation disabled, and seccomp profile enabled
- **Service Link Configuration**: `enableServiceLinks: false` prevents legacy service-link environment variable injection conflicts
- **Audit Integration**: Configured to emit audit events to the centralized audit-service with shared credentials

**Updated** Enhanced security context ensures the identity-broker container runs with minimal privileges, protecting sensitive authentication operations. The service link configuration ensures reliable DNS-based service discovery without conflicting environment variables. Audit integration provides comprehensive audit trail capabilities for all authentication and authorization operations.

**Section sources**
- [identity-service-deployment.yaml:1-40](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml#L1-L40)

### Service Configuration

The identity-broker exposes HTTP service for authentication endpoints.

**Section sources**
- [identity-service-service.yaml:1-12](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-service.yaml#L1-L12)

### Environment Variables

The identity-broker requires configuration for OIDC integration and audit trail capabilities:

| Variable | Description | Example Value |
|----------|-------------|---------------|
| KEYCLOAK_BASE_URL | Keycloak server URL | https://idp.apps.metasync.cc |
| KEYCLOAK_REALM | Keycloak realm name | luban-aiops |
| OIDC_CLIENT_ID | Client identifier | luban-aiops-portal |
| OIDC_REDIRECT_URI | Primary callback URI | https://aiops.luban.metasync.cc/callback |
| OIDC_POST_LOGOUT_REDIRECT_URI | Primary post-logout redirect | https://aiops.luban.metasync.cc/ |
| OIDC_EXTRA_REDIRECT_URIS | Extra callback URIs for reachability | https://aiops.luban.k8s.orb.local/callback,http://localhost:18080/callback |
| OIDC_EXTRA_POST_LOGOUT_REDIRECT_URIS | Extra post-logout redirects | https://aiops.luban.k8s.orb.local/,http://localhost:18080/ |
| OIDC_SCOPES | OAuth scopes | openid groups |
| IDENTITY_TOKEN_AUDIENCE | Token audience | platform-gateway |
| IDENTITY_DELEGATED_TOKEN_TTL_SECONDS | Delegated token TTL | 300 |
| IDENTITY_AUDIT_SERVICE_URL | Audit service endpoint | http://audit-service:8000 |
| IDENTITY_AUDIT_CLIENT_ID | Audit client identifier | identity-broker |

**Updated** The identity broker configuration now includes expanded OIDC redirect URI handling with clear distinction between primary callback URIs and extra redirect URIs. The `OIDC_REDIRECT_URI` serves as the canonical entrypoint for sign-in flows, while `OIDC_EXTRA_REDIRECT_URIS` provides additional reachability options for different environments.

**Section sources**
- [identity-broker-runtime-config.env:1-19](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-config.env#L1-L19)

## Agent Platform Service

The agent-platform service provides the core agent runtime functionality, including session management, provider integration, and tool execution coordination.

### Deployment Configuration

The agent-platform deployment runs the agent service with appropriate runtime configuration and dependencies. The deployment includes enhanced security contexts to ensure secure container execution.

**Key Features:**
- Agent runtime execution environment
- Session state management
- Provider integration (OpenAI, DeepSeek, DashScope)
- Tool execution coordination via tool-gateway
- **Security Context**: Non-root execution with UID 1000, privilege escalation disabled, and seccomp profile enabled
- **Service Link Configuration**: `enableServiceLinks: false` prevents legacy service-link environment variable injection conflicts
- **Execution Signing**: Supports signed execution requests for security compliance
- **Execution Handoff**: Secure handoff mechanism to execution runtime workers

**Updated** Enhanced security context ensures the agent-platform container runs with minimal privileges, protecting agent runtime operations and session data. The service link configuration ensures reliable DNS-based service discovery without conflicting environment variables. Execution signing and handoff capabilities provide secure boundaries for agent operations.

**Section sources**
- [agent-service-deployment.yaml:1-69](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml#L1-L69)

### Service Configuration

The agent-platform exposes HTTP service for API endpoints consumed by platform-gateway.

**Section sources**
- [agent-service-service.yaml:1-12](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-service.yaml#L1-L12)

## Execution Runtime Service

The execution-runtime service provides isolated execution environments for agent workloads, enabling secure separation of concerns between agent orchestration and actual tool execution.

### Deployment Configuration

The execution-runtime deployment runs with enhanced security contexts and isolated execution capabilities. The deployment includes comprehensive monitoring and health checking for production readiness.

**Key Features:**
- Isolated execution environment for agent workloads
- Secure handoff mechanism from agent-platform
- Resource isolation and security boundaries
- Comprehensive health monitoring and metrics collection
- **Security Context**: Non-root execution with UID 1000, privilege escalation disabled, and seccomp profile enabled
- **Service Link Configuration**: `enableServiceLinks: false` prevents legacy service-link environment variable injection conflicts
- **Health Probes**: Readiness and liveness probes for reliable operation

**Updated** The execution runtime service provides critical isolation boundaries for agent operations, ensuring that potentially unsafe tool executions are contained within secure worker processes. The service link configuration ensures reliable DNS-based service discovery without conflicting environment variables.

**Section sources**
- [execution-runtime-deployment.yaml:1-58](file://shared/platform-ops/gitops/dev-k8s/base/execution-runtime/execution-runtime-deployment.yaml#L1-L58)

### Service Configuration

The execution-runtime exposes HTTP service for secure execution requests from agent-platform.

**Section sources**
- [execution-runtime-service.yaml:1-12](file://shared/platform-ops/gitops/dev-k8s/base/execution-runtime/execution-runtime-service.yaml#L1-L12)

## Incident Service

The incident-service provides centralized incident management and collaboration capabilities for the platform, enabling teams to coordinate responses to operational issues.

### Deployment Configuration

The incident-service deployment includes comprehensive health monitoring, security contexts, and Prometheus scraping annotations for observability. The deployment features robust health probes with appropriate timing configurations.

**Key Features:**
- Prometheus monitoring with scrape annotations for metrics collection
- Comprehensive health probes with tuned timing parameters
- PostgreSQL backend for incident data storage and querying
- Security context with non-root execution and privilege restrictions
- **Security Context**: Non-root execution with UID 1000, privilege escalation disabled, and seccomp profile enabled
- **Service Link Configuration**: `enableServiceLinks: false` prevents legacy service-link environment variable injection conflicts

**Updated** Enhanced security context ensures the incident-service container runs with minimal privileges, protecting sensitive incident data and processing operations. The service link configuration ensures reliable DNS-based service discovery without conflicting environment variables.

**Section sources**
- [incident-service-deployment.yaml:1-58](file://shared/platform-ops/gitops/dev-k8s/base/incident-service/incident-service-deployment.yaml#L1-L58)

### Service Configuration

The incident-service exposes HTTP service on port 8000 for incident management operations.

**Section sources**
- [incident-service-service.yaml:1-12](file://shared/platform-ops/gitops/dev-k8s/base/incident-service/incident-service-service.yaml#L1-L12)

## Skills Hub Service

The skills-hub service provides skill management, ingestion, and query capabilities for AI-powered guidance and runbooks. It serves as the central repository for platform knowledge and operational procedures.

### Deployment Configuration

The skills-hub deployment includes comprehensive health monitoring, security contexts, and Prometheus scraping annotations for observability. The deployment features robust health probes with appropriate timing configurations to handle development environment load variations.

**Key Features:**
- Prometheus monitoring with scrape annotations for metrics collection
- Comprehensive health probes with tuned timing parameters
- PostgreSQL backend for skill storage and querying
- Federated skill sources from local ConfigMap volumes
- Security context with non-root execution and privilege restrictions
- Volume mounts for skill sources and temporary cache storage
- **Security Context**: Non-root execution with UID 1000, privilege escalation disabled, and seccomp profile enabled
- **Service Link Configuration**: `enableServiceLinks: false` prevents legacy service-link environment variable injection conflicts
- **Audit Integration**: Configured to emit audit events to the centralized audit-service with shared credentials

**Updated** Enhanced security context ensures the skills-hub container runs with minimal privileges, protecting skill data and processing operations. The service link configuration ensures reliable DNS-based service discovery without conflicting environment variables. Health probes are configured with generous timing to prevent unnecessary restarts during development environment load spikes. Audit integration provides comprehensive audit trail capabilities for all skill operations including search, retrieval, and synchronization events.

**Section sources**
- [skills-hub-deployment.yaml:1-104](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/skills-hub-deployment.yaml#L1-L104)

### Service Configuration

The skills-hub exposes HTTP service on port 8000 for skill queries and management operations.

**Section sources**
- [skills-hub-service.yaml:1-11](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/skills-hub-service.yaml#L1-L11)

### Health Monitoring and Probes

The skills-hub service implements comprehensive health monitoring with separate readiness and liveness probes:

**Readiness Probe:**
- Endpoint: `/health/ready`
- Initial delay: 5 seconds
- Period: 10 seconds
- Timeout: 5 seconds

**Liveness Probe:**
- Endpoint: `/health/live`
- Initial delay: 10 seconds
- Period: 20 seconds
- Timeout: 5 seconds
- Failure threshold: 4

These configurations provide adequate headroom for development environments where healthy responses may take 2-4 seconds due to system load or VM sleep/wake cycles.

### Prometheus Monitoring

The skills-hub service includes Prometheus scraping annotations for metrics collection:

```yaml
annotations:
  prometheus.io/scrape: "true"
  prometheus.io/path: /metrics
  prometheus.io/port: "8000"
```

This enables automatic metrics discovery and collection by Prometheus instances in the cluster.

### Skill Sources and Storage

The skills-hub service supports federated skill sources through ConfigMap volume mounts:

**Local Skill Sources:**
- SRE Alerting guides mounted at `/skills/sre-alerting`
- Platform Runbooks mounted at `/skills/platform-runbooks`

**Storage Configuration:**
- PostgreSQL database for persistent skill storage
- EmptyDir volume for temporary git-source checkouts at `/var/lib/skills-hub`
- Read-only ConfigMap mounts for skill source files

### Environment Variables

The skills-hub service requires configuration for database connectivity, skill sources, and query authentication:

| Variable | Description | Example Value |
|----------|-------------|---------------|
| SKILLS_STORE_BACKEND | Storage backend type | postgres |
| SKILLS_DB_URL | PostgreSQL connection string | postgresql://audit:audit-dev-local@postgres:5432/skills |
| SKILLS_SYNC_INTERVAL_SECONDS | Sync interval in seconds | 300 |
| SKILLS_DATA_PATH | Data directory path | /var/lib/skills-hub |
| SKILLS_SOURCES | JSON array of skill sources | [{"source_id":"sre-alerting","type":"local","path":"/skills/sre-alerting"}] |
| SKILLS_QUERY_CLIENTS | Query client credentials | tool-gateway=secret-value |
| SKILLS_AUDIT_SERVICE_URL | Audit service endpoint | http://audit-service:8000 |
| SKILLS_AUDIT_CLIENT_ID | Audit client identifier | skills-hub |

**Section sources**
- [skills-hub-runtime-config.env:1-18](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-config.env#L1-L18)

## Audit Service

The audit-service provides centralized audit event ingestion, storage, and querying capabilities for the entire platform. It authenticates incoming audit events from all emitting services using a shared secret registry.

### Deployment Configuration

The audit-service deployment includes comprehensive health monitoring, security contexts, and Prometheus scraping annotations for observability. The deployment features robust health probes with appropriate timing configurations.

**Key Features:**
- Prometheus monitoring with scrape annotations for metrics collection
- Comprehensive health probes with tuned timing parameters
- PostgreSQL backend for audit event storage and querying
- Client authentication registry for audit event ingestion
- Security context with non-root execution and privilege restrictions
- **Security Context**: Non-root execution with UID 1000, privilege escalation disabled, and seccomp profile enabled
- **Service Link Configuration**: `enableServiceLinks: false` prevents legacy service-link environment variable injection conflicts

**Updated** Enhanced security context ensures the audit-service container runs with minimal privileges, protecting sensitive audit data and processing operations. The service link configuration ensures reliable DNS-based service discovery without conflicting environment variables. The audit service maintains a registry of authorized clients that can emit audit events.

**Section sources**
- [audit-service-deployment.yaml:1-58](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/audit-service-deployment.yaml#L1-L58)

### Service Configuration

The audit-service exposes HTTP service on port 8000 for audit event ingestion and querying.

### Environment Variables

The audit-service requires configuration for database connectivity, retention policies, and client authentication:

| Variable | Description | Example Value |
|----------|-------------|---------------|
| AUDIT_STORE_BACKEND | Storage backend type | postgres |
| AUDIT_DB_URL | PostgreSQL connection string | postgresql://audit:audit-dev-local@postgres:5432/audit |
| AUDIT_RETENTION_DAYS | Event retention period | 30 |
| AUDIT_MAX_EVENTS | Maximum events to store | 100000 |
| AUDIT_EVICTION_INTERVAL_SECONDS | Cleanup interval | 3600 |
| AUDIT_INGEST_CLIENTS | Client authentication registry | tool-gateway=secret,platform-gateway=secret,... |

**Section sources**
- [audit-service-runtime-config.env:1-8](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env#L1-L8)

## Operator Portal Service

The operator-portal service provides a web-based interface for platform administration and monitoring.

### Deployment Configuration

The operator-portal deployment serves static web content through nginx with API proxying to platform-gateway. The deployment includes enhanced security contexts with a different user ID optimized for nginx operation.

**Key Features:**
- Static web UI served by nginx
- API proxying to platform-gateway
- OIDC integration for authentication
- Development-friendly local access
- **Security Context**: Non-root execution with UID 101 (nginx user), privilege escalation disabled, and seccomp profile enabled
- **Service Link Configuration**: `enableServiceLinks: false` prevents legacy service-link environment variable injection conflicts

**Updated** Enhanced security context ensures the operator-portal container runs with minimal privileges using the nginx user (UID 101), which is more appropriate for web server operations. The service link configuration ensures reliable DNS-based service discovery without conflicting environment variables.

**Section sources**
- [web-ui-deployment.yaml:1-30](file://shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-deployment.yaml#L1-L30)

### Service Configuration

The operator-portal exposes HTTP service on port 8080 for web access.

**Section sources**
- [web-ui-service.yaml:1-12](file://shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-service.yaml#L1-L12)

### HTTPRoute Configuration

The operator-portal uses Kubernetes Gateway API HTTPRoute for production-like ingress configuration through the shared Envoy Gateway.

**HTTPRoute Setup:**
- **Gateway**: Uses `luban-gateway` in the `gateway` namespace
- **Hostnames**: Supports both `aiops.luban.k8s.orb.local` and `aiops.luban.metasync.cc`
- **Timeout Configuration**: Disables default 15s timeout for long-running SSE streams
- **Backend**: Routes to `web-ui` service on port 8080

**Canonical Hostname Requirements:**
- **Primary Entry Point**: `https://aiops.luban.metasync.cc` is the canonical portal entrypoint
- **Fallback Hostname**: `https://aiops.luban.k8s.orb.local` serves as OrbStack wildcard hostname fallback
- **OIDC Callback**: The identity broker's OIDC callback is pinned to `https://aiops.luban.metasync.cc/callback`
- **Browser Storage**: PKCE pending requests live in per-origin browser storage, requiring consistent hostnames

**Updated** The HTTPRoute configuration now includes detailed explanation of canonical hostname requirements and the relationship between the primary callback URI and extra redirect URIs. The Envoy Gateway's wildcard HTTPS listeners accept routes from all namespaces, simplifying route configuration while maintaining security through hostname validation.

**Section sources**
- [web-ui-httproute.yaml:1-27](file://shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-httproute.yaml#L1-L27)

## Infrastructure Services

### Redis Service

Redis provides in-memory data storage for session state and message coordination between services.

**Deployment Characteristics:**
- Uses emptyDir storage for development simplicity
- Not suitable for production persistence requirements
- Supports inter-service communication patterns
- **Note**: Currently lacks security context enhancements compared to other services

**Section sources**
- [redis-deployment.yaml:1-30](file://shared/platform-ops/gitops/dev-k8s/base/infra/redis-deployment.yaml#L1-L30)
- [redis-service.yaml:1-12](file://shared/platform-ops/gitops/dev-k8s/base/infra/redis-service.yaml#L1-L12)

### PostgreSQL Service

PostgreSQL provides persistent database storage for skills, incidents, and session data across the platform.

**Deployment Characteristics:**
- StatefulSet deployment for data persistence
- PersistentVolumeClaim for data durability
- Database initialization scripts for schema setup
- Service exposure for application connectivity
- **Security Context**: Non-root execution with proper file permissions
- **Database Initialization**: Automated schema creation for skills, incidents, and sessions databases

**Section sources**
- [postgres-statefulset.yaml:1-100](file://shared/platform-ops/gitops/dev-k8s/base/infra/postgres-statefulset.yaml#L1-L100)
- [postgres-service.yaml:1-12](file://shared/platform-ops/gitops/dev-k8s/base/infra/postgres-service.yaml#L1-L12)
- [create-skills-db.sql:1-50](file://shared/platform-ops/gitops/dev-k8s/base/infra/create-skills-db.sql#L1-L50)
- [create-incidents-db.sql:1-50](file://shared/platform-ops/gitops/dev-k8s/base/infra/create-incidents-db.sql#L1-L50)
- [create-sessions-db.sql:1-50](file://shared/platform-ops/gitops/dev-k8s/base/infra/create-sessions-db.sql#L1-L50)

## Service Discovery and Networking

The platform uses Kubernetes service discovery for inter-service communication. Each service is exposed through a Kubernetes Service object with consistent naming conventions. The `enableServiceLinks: false` configuration ensures that DNS-based service discovery is used exclusively, preventing conflicts with legacy service-link environment variables.

### Service Architecture

```mermaid
graph LR
A[Browser/Client] --> B[Web UI Service]
B --> C[Platform Gateway Service]
C --> D[Agent Platform Service]
C --> E[Tool Gateway Service]
D --> F[Execution Runtime Service]
C --> G[Identity Broker Service]
E --> H[Kubernetes API Server]
C --> I[Skills Hub Service]
D --> I
F --> I
C --> J[Audit Service]
E --> J
F --> J
G --> J
I --> J
C --> K[Incident Service]
E --> K
style A fill:#e1f5fe
style B fill:#f3e5f5
style C fill:#fff3e0
style D fill:#e8f5e8
style E fill:#fff8e1
style F fill:#fce4ec
style G fill:#f1f8e9
style H fill:#ffebee
style I fill:#e0f2f1
style J fill:#fff3e0
style K fill:#f3e5f5
```

**Diagram sources**
- [platform-gateway-service.yaml:1-12](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/platform-gateway-service.yaml#L1-L12)
- [tool-gateway-service.yaml:1-12](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-service.yaml#L1-L12)
- [agent-service-service.yaml:1-12](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-service.yaml#L1-L12)
- [execution-runtime-service.yaml:1-12](file://shared/platform-ops/gitops/dev-k8s/base/execution-runtime/execution-runtime-service.yaml#L1-L12)
- [incident-service-service.yaml:1-12](file://shared/platform-ops/gitops/dev-k8s/base/incident-service/incident-service-service.yaml#L1-L12)
- [identity-service-service.yaml:1-12](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-service.yaml#L1-L12)
- [skills-hub-service.yaml:1-11](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/skills-hub-service.yaml#L1-L11)
- [audit-service-service.yaml:1-12](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/audit-service-service.yaml#L1-L12)

### Network Flow

1. **External Access**: Clients connect to Web UI service (port 8080)
2. **API Requests**: Web UI proxies `/api/` requests to platform-gateway service
3. **Authentication**: Platform-gateway communicates with identity-broker for authentication
4. **Agent Operations**: Platform-gateway calls agent-platform service for agent operations
5. **Tool Execution**: Agent-platform calls execution-runtime for isolated execution
6. **Skill Queries**: Agent-platform and tool-gateway call skills-hub for skill information
7. **Incident Management**: Platform-gateway and tool-gateway call incident-service for collaboration
8. **Audit Events**: All services emit audit events to audit-service for centralized logging
9. **Kubernetes Access**: Tool-gateway accesses Kubernetes API server with RBAC permissions

### Service Link Configuration Impact

All services now use `enableServiceLinks: false` to prevent Kubernetes from injecting legacy service-link environment variables (e.g., `AGENT_SERVICE_PORT=tcp://...`, `IDENTITY_SERVICE_HOST=...`). This ensures:

- **Consistent Service Discovery**: All services use DNS-based resolution exclusively
- **No Environment Variable Conflicts**: Prevents collisions between injected variables and application-specific configuration
- **Predictable Behavior**: Eliminates unexpected environment variable injection that could affect service connectivity
- **Cleaner Environment**: Containers only receive explicitly configured environment variables

**Section sources**
- [agent-service-deployment.yaml:19-21](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml#L19-L21)
- [identity-service-deployment.yaml:19-21](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml#L19-L21)
- [web-ui-deployment.yaml:15-17](file://shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-deployment.yaml#L15-L17)
- [platform-gateway-deployment.yaml:19-21](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/platform-gateway-deployment.yaml#L19-L21)
- [tool-gateway-deployment.yaml:19-21](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml#L19-L21)
- [skills-hub-deployment.yaml:19-21](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/skills-hub-deployment.yaml#L19-L21)
- [audit-service-deployment.yaml:19-21](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/audit-service-deployment.yaml#L19-L21)
- [incident-service-deployment.yaml:19-21](file://shared/platform-ops/gitops/dev-k8s/base/incident-service/incident-service-deployment.yaml#L19-L21)
- [execution-runtime-deployment.yaml:19-21](file://shared/platform-ops/gitops/dev-k8s/base/execution-runtime/execution-runtime-deployment.yaml#L19-L21)

## Persistent Storage Configuration

The current development deployment uses ephemeral storage for simplicity. Production deployments should implement persistent storage solutions.

### Current Storage Strategy

- **Redis**: Uses emptyDir for development testing only
- **PostgreSQL**: StatefulSet with persistent volume claims for data durability
- **Session State**: Stored in memory, not persisted across pod restarts
- **Configuration**: Stored in ConfigMaps and Secrets
- **Agent Workspaces**: Uses emptyDir for temporary workspace storage
- **Skills Hub Data**: Uses emptyDir for temporary git-source checkouts; PostgreSQL for persistent skill storage
- **Audit Data**: Uses PostgreSQL for persistent audit event storage
- **Incident Data**: Uses PostgreSQL for persistent incident data storage

### Production Recommendations

For production deployments, consider:
- Redis with persistent volumes or managed Redis service
- Database-backed session storage
- External configuration management
- Backup and disaster recovery procedures
- **Security Considerations**: Ensure persistent volumes are properly secured with appropriate access controls
- **Skills Hub**: Configure PostgreSQL with persistent volumes and backup strategies
- **Audit Service**: Implement proper backup and retention policies for audit data
- **Incident Service**: Configure PostgreSQL with persistent volumes and backup strategies
- **PostgreSQL**: Implement automated backups and point-in-time recovery

## Deployment Automation

### Build Process

The build process creates coordinated images for all platform components:

```bash
make build
```

This generates images with tags like `dev-k8s-<gitsha>` and stores them in `.images.env`.

### Deployment Process

The deployment process applies the complete platform stack:

```bash
make deploy
```

This performs one-time cleanup of legacy api-gateway objects and deploys the new dual-gateway architecture along with the Skills Hub service, Audit Service, Execution Runtime, and Incident Service.

### Manual Deployment

Individual components can be deployed using standard Kubernetes commands:

```bash
kubectl apply -f shared/platform-ops/gitops/dev-k8s/base/
```

### Audit Secret Provisioning

The enhanced audit secret provisioning ensures all platform services can emit audit events to the centralized audit-service with consistent authentication. The automatic restart functionality ensures audit credentials are applied immediately without manual intervention.

**Key Features:**
- Generates shared audit ingest secret if not provided
- Updates audit-service client registry with all emitter credentials
- Provisions audit client secrets for all emitting services (tool-gateway, platform-gateway, identity-broker, incident-service, skills-hub)
- Automatically restarts all affected deployments to apply new audit credentials
- Preserves existing OTLP headers and other secret values
- Validates rollout status of all restarted deployments

## Rollback Procedures

### Image Rollback

To rollback to a previous image version:

```bash
kubectl rollout undo deployment/platform-gateway
kubectl rollout undo deployment/tool-gateway
kubectl rollout undo deployment/skills-hub
kubectl rollout undo deployment/audit-service
kubectl rollout undo deployment/incident-service
kubectl rollout undo deployment/execution-runtime
```

### Configuration Rollback

Revert configuration changes by restoring previous versions of ConfigMaps and Secrets:

```bash
kubectl apply -f shared/platform-ops/gitops/dev-k8s/base/
```

### Audit Secret Rollback

To rollback audit secret changes:

```bash
# Regenerate audit secrets with previous values
AUDIT_INGEST_SECRET=previous-secret shared/platform-ops/gitops/sync-audit-secrets.sh
```

### Emergency Rollback

In case of critical issues, scale down affected services:

```bash
kubectl scale deployment/platform-gateway --replicas=0
kubectl scale deployment/tool-gateway --replicas=0
kubectl scale deployment/skills-hub --replicas=0
kubectl scale deployment/audit-service --replicas=0
kubectl scale deployment/incident-service --replicas=0
kubectl scale deployment/execution-runtime --replicas=0
```

## Troubleshooting

### Common Issues

**Service Connectivity Problems:**
- Verify service DNS resolution within the cluster
- Check network policies that might block inter-service communication
- Validate service ports match between deployment and service definitions
- **Service Link Issues**: If experiencing environment variable conflicts, verify that `enableServiceLinks: false` is set in all deployment specifications

**Authentication Issues:**
- Verify OIDC client configuration in identity-broker
- Check token audiences match between services
- Validate secret values for client credentials
- **Identity Broker Issues**: Ensure `OIDC_REDIRECT_URI` matches the canonical hostname and that extra redirect URIs are properly registered with Keycloak

**RBAC Permission Errors:**
- Review tool-gateway RBAC roles and bindings
- Verify service account names match between deployment and RBAC
- Check namespace scoping for roles and role bindings

**Security Context Issues:**
- If pods fail to start due to security context violations, verify that the container images support running as non-root users
- Check that file permissions in mounted volumes are compatible with the specified user IDs
- Ensure that any custom scripts or entrypoints don't require root privileges

**Audit Service Issues:**
- Verify audit-service is running and accessible
- Check audit-service client registry contains all expected clients
- Validate audit client secrets match between emitters and audit-service
- Monitor audit-service health endpoints for service readiness

**Skills Hub Specific Issues:**
- Verify PostgreSQL connectivity and database schema initialization
- Check skill source ConfigMap mounts and file permissions
- Validate Prometheus scraping configuration for metrics collection
- Monitor health probe endpoints for service readiness

**Execution Runtime Issues:**
- Verify execution-signing-secret and execution-handoff-secret are properly configured
- Check that agent-platform can communicate with execution-runtime service
- Monitor execution-runtime health endpoints for service readiness

**Incident Service Issues:**
- Verify PostgreSQL connectivity and database schema initialization
- Check incident-service health endpoints for service readiness
- Validate incident service client credentials between services

**HTTPRoute and Ingress Issues:**
- Verify Envoy Gateway is running and accessible
- Check that hostnames resolve correctly in your environment
- Validate that the canonical hostname matches the OIDC redirect URI
- Ensure wildcard HTTPS listeners are properly configured in the gateway

### Debugging Commands

**Check Pod Status:**
```bash
kubectl get pods -n dev-luban-aiops
```

**View Service Logs:**
```bash
kubectl logs deployment/platform-gateway -n dev-luban-aiops
kubectl logs deployment/tool-gateway -n dev-luban-aiops
kubectl logs deployment/skills-hub -n dev-luban-aiops
kubectl logs deployment/audit-service -n dev-luban-aiops
kubectl logs deployment/identity-service -n dev-luban-aiops
kubectl logs deployment/incident-service -n dev-luban-aiops
kubectl logs deployment/execution-runtime -n dev-luban-aiops
```

**Verify Service Endpoints:**
```bash
kubectl get endpoints -n dev-luban-aiops
```

**Test Service Connectivity:**
```bash
kubectl run test-pod --image=busybox -n dev-luban-aiops --command -- wget -qO- http://platform-gateway:8000/health
kubectl run test-pod --image=busybox -n dev-luban-aiops --command -- wget -qO- http://skills-hub:8000/health/ready
kubectl run test-pod --image=busybox -n dev-luban-aiops --command -- wget -qO- http://audit-service:8000/health/ready
kubectl run test-pod --image=busybox -n dev-luban-aiops --command -- wget -qO- http://identity-service:8000/health/ready
kubectl run test-pod --image=busybox -n dev-luban-aiops --command -- wget -qO- http://incident-service:8000/health/ready
kubectl run test-pod --image=busybox -n dev-luban-aiops --command -- wget -qO- http://execution-runtime:8000/health/ready
```

**Check Security Contexts:**
```bash
kubectl describe pod -l app=platform-gateway -n dev-luban-aiops
kubectl describe pod -l app=tool-gateway -n dev-luban-aiops
kubectl describe pod -l app=skills-hub -n dev-luban-aiops
kubectl describe pod -l app=audit-service -n dev-luban-aiops
kubectl describe pod -l app=identity-service -n dev-luban-aiops
kubectl describe pod -l app=incident-service -n dev-luban-aiops
kubectl describe pod -l app=execution-runtime -n dev-luban-aiops
```

**Verify Service Link Configuration:**
```bash
kubectl describe pod -l app=agent-service -n dev-luban-aiops | grep enableServiceLinks
kubectl describe pod -l app=identity-service -n dev-luban-aiops | grep enableServiceLinks
kubectl describe pod -l app=web-ui -n dev-luban-aiops | grep enableServiceLinks
kubectl describe pod -l app=platform-gateway -n dev-luban-aiops | grep enableServiceLinks
kubectl describe pod -l app=tool-gateway -n dev-luban-aiops | grep enableServiceLinks
kubectl describe pod -l app=skills-hub -n dev-luban-aiops | grep enableServiceLinks
kubectl describe pod -l app=audit-service -n dev-luban-aiops | grep enableServiceLinks
kubectl describe pod -l app=incident-service -n dev-luban-aiops | grep enableServiceLinks
kubectl describe pod -l app=execution-runtime -n dev-luban-aiops | grep enableServiceLinks
```

**Check Skills Hub Health:**
```bash
kubectl exec -it deployment/skills-hub -n dev-luban-aiops -- curl -s http://localhost:8000/health/ready
kubectl exec -it deployment/skills-hub -n dev-luban-aiops -- curl -s http://localhost:8000/health/live
```

**Check Audit Service Health:**
```bash
kubectl exec -it deployment/audit-service -n dev-luban-aiops -- curl -s http://localhost:8000/health/ready
kubectl exec -it deployment/audit-service -n dev-luban-aiops -- curl -s http://localhost:8000/health/live
```

**Check Identity Broker Health:**
```bash
kubectl exec -it deployment/identity-service -n dev-luban-aiops -- curl -s http://localhost:8000/health/ready
kubectl exec -it deployment/identity-service -n dev-luban-aiops -- curl -s http://localhost:8000/health/live
```

**Check Incident Service Health:**
```bash
kubectl exec -it deployment/incident-service -n dev-luban-aiops -- curl -s http://localhost:8000/health/ready
kubectl exec -it deployment/incident-service -n dev-luban-aiops -- curl -s http://localhost:8000/health/live
```

**Check Execution Runtime Health:**
```bash
kubectl exec -it deployment/execution-runtime -n dev-luban-aiops -- curl -s http://localhost:8000/health/ready
kubectl exec -it deployment/execution-runtime -n dev-luban-aiops -- curl -s http://localhost:8000/health/live
```

**Verify Audit Secret Configuration:**
```bash
kubectl get secret audit-service-runtime-secrets -n dev-luban-aiops -o yaml
kubectl get secret tool-gateway-runtime-secrets -n dev-luban-aiops -o yaml
kubectl get secret platform-gateway-runtime-secrets -n dev-luban-aiops -o yaml
kubectl get secret identity-service-runtime-secrets -n dev-luban-aiops -o yaml
kubectl get secret incident-service-runtime-secrets -n dev-luban-aiops -o yaml
kubectl get secret skills-hub-runtime-secrets -n dev-luban-aiops -o yaml
```

**Verify HTTPRoute Configuration:**
```bash
kubectl get httproute -n dev-luban-aiops
kubectl describe httproute web-ui -n dev-luban-aiops
kubectl get gateway -n gateway
kubectl describe gateway luban-gateway -n gateway
```

**Test Canonical Hostname Resolution:**
```bash
nslookup aiops.luban.metasync.cc
nslookup aiops.luban.k8s.orb.local
curl -v https://aiops.luban.metasync.cc/
curl -v https://aiops.luban.k8s.orb.local/
```

**Check PostgreSQL Database Status:**
```bash
kubectl get statefulset postgres -n dev-luban-aiops
kubectl get pvc -n dev-luban-aiops
kubectl exec -it postgres-0 -n dev-luban-aiops -- psql -U postgres -c "\l"
```

**Section sources**
- [dev-k8s-readme.md:289-323](file://shared/platform-ops/gitops/dev-k8s/README.md#L289-L323)