---
kind: business_term
name: Business Glossary
category: business_term
scope:
    - '**'
---

### SDD
- Definition：Spec-Driven Development - the project's development methodology where features are implemented through formal specifications (SPEC-XXX documents) that define requirements, acceptance criteria, and tasks before implementation begins. Each spec follows a lifecycle from draft → approved → delivered, with delivery gates ensuring quality standards.
- Aliases：spec-driven development、SPEC-XXX

### ADR
- Definition：Architecture Decision Record - formal documentation of architectural decisions made during development, following a template that captures context, decision, consequences, and status. ADRs follow a lifecycle from proposed → accepted and serve as immutable records of design rationale.
- Aliases：architecture decision record、ADR-000X

### Identity Broker
- Definition：The identity-broker service acts as the platform's internal identity provider, handling SSO authentication, identity federation, group normalization, and identity propagation. It issues JWT tokens signed with RSA keys and serves JWKS endpoints for token verification by other services.
- Aliases：identity-service、broker

### Tool Gateway
- Definition：The api-gateway service provides normalized tool and connector access, including MCP (Model Context Protocol) integration and external system connectivity. It enforces policies, validates identities, and routes tool invocations to appropriate execution backends.
- Aliases：api-gateway、gateway

### Agent Platform
- Definition：The agent-platform service provides the agent runtime, orchestration, session handling, and streaming capabilities. It implements the platform-owned agent-service contract and currently uses AgentScope as its underlying orchestration kernel.
- Aliases：agent-service、runtime

### Operator Portal
- Definition：The web-based interface for operators, approvers, and auditors to manage the platform. It includes silent token refresh functionality (~60s before expiry via POST /api/v1/auth/refresh) and provides administrative controls for the agentic AIOps platform.
- Aliases：web-ui、portal

### dev-k8s Overlay
- Definition：The Kubernetes deployment overlay for the development environment, managed through kustomize. It configures all platform services, Redis infrastructure, and networking for local development and testing purposes.
- Aliases：dev overlay、development k8s

### Runtime Profile
- Definition：Environment-specific configuration sets for different AI model providers (dashscope, deepseek, openai). Each profile contains ConfigMaps and example secrets that customize the agent-platform behavior for specific model backends.
- Aliases：profile、runtime-config

### Release 0/1
- Definition：Major release milestones in the platform's evolution. Release 0 established the platform foundation, while Release 1 delivered SPEC-001 through SPEC-006 including agent-platform, identity-broker, tool-gateway, and operator-portal implementations.
- Aliases：R0、R1、release milestone
