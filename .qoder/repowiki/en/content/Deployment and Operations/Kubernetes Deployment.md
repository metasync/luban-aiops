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
- [deploy.sh](file://shared/platform-ops/gitops/dev-k8s/deploy.sh)
- [dev-k8s-readme.md](file://shared/platform-ops/gitops/dev-k8s/README.md)
- [sync-audit-secrets.sh](file://shared/platform-ops/gitops/sync-audit-secrets.sh)
</cite>

## Update Summary
**Changes Made**
- Enhanced identity broker configuration with expanded OIDC redirect URI handling and canonical hostname requirements
- Updated HTTPRoute setup explanation for development environment with detailed canonical hostname guidance
- Clarified the relationship between primary callback URIs and extra redirect URIs in identity broker configuration
- Added comprehensive documentation for Envoy Gateway integration and wildcard HTTPS listeners
- Enhanced troubleshooting section with identity broker-specific debugging guidance

## Table of Contents
1. Overview
2. Kustomize Structure and Base Configuration
3. Platform Gateway Service
4. Tool Gateway Service
5. Identity Broker Service
6. Agent Platform Service
7. Skills Hub Service
8. Audit Service
9. Operator Portal Service
10. Infrastructure Services
11. Service Discovery and Networking
12. Persistent Storage Configuration
13. Deployment Automation
14. Rollback Procedures
15. Troubleshooting

## Overview

The Luban AIOps Platform uses a Kustomize-based deployment structure that supports both platform-gateway and tool-gateway services independently, along with comprehensive audit trail capabilities. This architectural design replaces the previous single api-gateway deployment with two specialized gateways, each serving distinct responsibilities:

- **Platform Gateway**: Handles user-facing API requests, authentication, authorization, and agent service orchestration
- **Tool Gateway**: Manages tool execution, Kubernetes resource access, and policy enforcement for tool operations
- **Skills Hub**: Provides skill management, ingestion, and query capabilities for AI-powered guidance and runbooks
- **Audit Service**: Centralized audit event ingestion and storage with client authentication

The deployment is organized using Kustomize overlays with a base configuration that includes all core services and their dependencies. All services are deployed with enhanced security contexts to ensure containers run as non-root users with minimal privileges. Additionally, all deployments now use `enableServiceLinks: false` to prevent Kubernetes legacy service-link environment variable injection conflicts, ensuring reliable DNS-based service discovery.

The platform features comprehensive audit trail capabilities through the `sync-audit-secrets.sh` script, which provisions shared audit credentials across all emitting services and automatically restarts affected deployments when audit secrets change.

## Kustomize Structure and Base Configuration

The base Kustomize configuration orchestrates all platform components through a centralized kustomization file that defines common settings, config maps, and resource references.

```mermaid
graph TD
A[Kustomization] --> B[ConfigMap Generator]
A --> C[Resources]
B --> D[Shared Runtime Config]
B --> E[Policy Config]
B --> F[Skills ConfigMaps]
C --> G[Platform Gateway]
C --> H[Tool Gateway]
C --> I[Identity Broker]
C --> J[Agent Platform]
C --> K[Skills Hub]
C --> L[Audit Service]
C --> M[Operator Portal]
C --> N[Infrastructure]
G --> O[Service Account]
H --> P[Service Account + RBAC]
I --> Q[Service Account]
J --> R[Service Account]
K --> S[Service Account]
L --> T[Service Account]
```

**Diagram sources**
- [kustomization.yaml:1-63](file://shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml#L1-L63)

The base configuration creates a unified `platform-runtime-config` ConfigMap from multiple environment fragments:
- Shared runtime settings (`shared/runtime.env`)
- Platform gateway specific settings (`platform-gateway/runtime-config.env`)
- Tool gateway specific settings (`tool-gateway/runtime-config.env`)
- Identity broker settings (`identity-broker/runtime-config.env`)
- Agent platform settings (`agent-platform/runtime-config.env`)
- Skills hub settings (`skills-hub/runtime-config.env`)
- Audit service settings (`audit-service/runtime-config.env`)

Additionally, the configuration generates sample skill source ConfigMaps for SRE alerting and platform runbooks.

**Section sources**
- [kustomization.yaml:6-16](file://shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml#L6-L16)
- [kustomization.yaml:19-36](file://shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml#L19-L36)
- [shared-runtime.env:1-8](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env#L1-L8)

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

**Section sources**
- [platform-gateway-runtime-config.env:1-8](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env#L1-L8)

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
- [tool-gateway-deployment.yaml:1-46](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml#L1-L46)
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
| GATEWAY_TOKEN_AUDIENCE | Token audience identifier | tool-gateway |
| GATEWAY_AUDIT_SERVICE_URL | Audit service endpoint | http://audit-service:8000 |
| GATEWAY_AUDIT_CLIENT_ID | Audit client identifier | tool-gateway |

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
| IDENTITY_TOKEN_AUDIENCE | Token audience | platform-gateway |
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

**Updated** Enhanced security context ensures the agent-platform container runs with minimal privileges, protecting agent runtime operations and session data. The service link configuration ensures reliable DNS-based service discovery without conflicting environment variables.

**Section sources**
- [agent-service-deployment.yaml:1-48](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml#L1-L48)

### Service Configuration

The agent-platform exposes HTTP service for API endpoints consumed by platform-gateway.

**Section sources**
- [agent-service-service.yaml:1-12](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-service.yaml#L1-L12)

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
- [redis-deployment.yaml:1-30](file://shared/platform-ops/gitops/dev-k8s/base/infra/redis-deployment.yaml#L1-30)
- [redis-service.yaml](file://shared/platform-ops/gitops/dev-k8s/base/infra/redis-service.yaml)

## Service Discovery and Networking

The platform uses Kubernetes service discovery for inter-service communication. Each service is exposed through a Kubernetes Service object with consistent naming conventions. The `enableServiceLinks: false` configuration ensures that DNS-based service discovery is used exclusively, preventing conflicts with legacy service-link environment variables.

### Service Architecture

```mermaid
graph LR
A[Browser/Client] --> B[Web UI Service]
B --> C[Platform Gateway Service]
C --> D[Agent Platform Service]
C --> E[Tool Gateway Service]
D --> E
C --> F[Identity Broker Service]
E --> G[Kubernetes API Server]
C --> H[Skills Hub Service]
D --> H
C --> I[Audit Service]
E --> I
F --> I
H --> I
style A fill:#e1f5fe
style B fill:#f3e5f5
style C fill:#fff3e0
style D fill:#e8f5e8
style E fill:#fff8e1
style F fill:#fce4ec
style G fill:#f1f8e9
style H fill:#e0f2f1
style I fill:#ffebee
```

**Diagram sources**
- [platform-gateway-service.yaml:1-12](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/platform-gateway-service.yaml#L1-L12)
- [tool-gateway-service.yaml:1-12](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-service.yaml#L1-L12)
- [agent-service-service.yaml:1-12](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-service.yaml#L1-L12)
- [identity-service-service.yaml:1-12](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-service.yaml#L1-L12)
- [skills-hub-service.yaml:1-11](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/skills-hub-service.yaml#L1-L11)
- [audit-service-service.yaml:1-12](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/audit-service-service.yaml#L1-L12)

### Network Flow

1. **External Access**: Clients connect to Web UI service (port 8080)
2. **API Requests**: Web UI proxies `/api/` requests to platform-gateway service
3. **Authentication**: Platform-gateway communicates with identity-broker for authentication
4. **Agent Operations**: Platform-gateway calls agent-platform service for agent operations
5. **Tool Execution**: Agent-platform calls tool-gateway for tool execution
6. **Skill Queries**: Agent-platform and tool-gateway call skills-hub for skill information
7. **Audit Events**: All services emit audit events to audit-service for centralized logging
8. **Kubernetes Access**: Tool-gateway accesses Kubernetes API server with RBAC permissions

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

## Persistent Storage Configuration

The current development deployment uses ephemeral storage for simplicity. Production deployments should implement persistent storage solutions.

### Current Storage Strategy

- **Redis**: Uses emptyDir for development testing only
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

This performs one-time cleanup of legacy api-gateway objects and deploys the new dual-gateway architecture along with the Skills Hub service and Audit Service.

### Manual Deployment

Individual components can be deployed using standard Kubernetes commands:

```bash
kubectl apply -f shared/platform-ops/gitops/dev-k8s/base/
```

### Audit Secret Provisioning

The enhanced `sync-audit-secrets.sh` script provides comprehensive audit secret management across all platform services:

```bash
# Provision audit secrets for all services
shared/platform-ops/gitops/sync-audit-secrets.sh

# Override the generated secret
AUDIT_INGEST_SECRET=my-secret shared/platform-ops/gitops/sync-audit-secrets.sh

# Skip in CI when secrets are injected externally
SKIP_AUDIT_SECRETS=true make deploy
```

**Key Features:**
- Generates shared audit ingest secret if not provided
- Updates audit-service client registry with all emitter credentials
- Provisions audit client secrets for all emitting services (tool-gateway, platform-gateway, identity-broker, incident-service, skills-hub)
- Automatically restarts all affected deployments to apply new audit credentials
- Preserves existing OTLP headers and other secret values
- Validates rollout status of all restarted deployments

**Updated** The enhanced audit secret provisioning ensures all platform services can emit audit events to the centralized audit-service with consistent authentication. The automatic restart functionality ensures audit credentials are applied immediately without manual intervention.

**Section sources**
- [deploy.sh:1-15](file://shared/platform-ops/gitops/dev-k8s/deploy.sh#L1-L15)
- [dev-k8s-readme.md:253-287](file://shared/platform-ops/gitops/dev-k8s/README.md#L253-L287)
- [sync-audit-secrets.sh:1-137](file://shared/platform-ops/gitops/sync-audit-secrets.sh#L1-L137)

## Rollback Procedures

### Image Rollback

To rollback to a previous image version:

```bash
kubectl rollout undo deployment/platform-gateway
kubectl rollout undo deployment/tool-gateway
kubectl rollout undo deployment/skills-hub
kubectl rollout undo deployment/audit-service
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
```

**Check Security Contexts:**
```bash
kubectl describe pod -l app=platform-gateway -n dev-luban-aiops
kubectl describe pod -l app=tool-gateway -n dev-luban-aiops
kubectl describe pod -l app=skills-hub -n dev-luban-aiops
kubectl describe pod -l app=audit-service -n dev-luban-aiops
kubectl describe pod -l app=identity-service -n dev-luban-aiops
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

**Section sources**
- [dev-k8s-readme.md:289-323](file://shared/platform-ops/gitops/dev-k8s/README.md#L289-L323)