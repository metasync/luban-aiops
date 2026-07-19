# Workspace Model

## Objective

Define the repository as a modular workspace for the enterprise-grade agentic AIOps platform.

The workspace model is intended to improve:

- modularity
- maintainability
- ownership clarity
- release independence
- long-term scalability

## Why A Workspace Model Fits This Platform

The platform already contains several independently meaningful product areas:

- operator experience
- agent runtime and orchestration
- identity and access
- policy and approval
- knowledge and skills
- tool connectivity
- isolated execution

Treating these as explicit product projects is more sustainable than keeping them inside one undifferentiated codebase.

## Workspace Design Principles

### 1. Split by product capability

Boundaries should be based on what a module or project is responsible for, not only on language or framework.

### 2. Keep control boundaries explicit

Identity, policy, orchestration, and execution should remain separate so that privileged actions are easier to reason about, audit, and secure.

### 3. Prefer clear contracts over shared internals

Projects should interact through:

- HTTP APIs
- event contracts
- shared schemas
- versioned SDKs where needed

### 4. Keep shared modules small

Only place truly reusable and low-level building blocks in shared modules.

### 5. Support independent releaseability

Not every project must release on its own from day one, but the structure should make that possible later.

### 6. Preserve end-to-end traceability

Even in a modular workspace, the platform must still support full operator-visible and audit-visible traceability.

## Proposed Workspace Layout

```text
luban-aiops/
  products/
    operator-portal/
    agent-platform/
    policy-center/
    identity-broker/
    skills-hub/
    tool-gateway/
    execution-runtime/
  shared/
    shared-contracts/
    shared-sdk/
    platform-ops/
  docs/
    agentic-aiops-platform/
    workspace/
```

## Product Projects

### `operator-portal`

Primary responsibility:

- web portal for operators and approvers

Key concerns:

- `SSO` login
- chat and interaction UX
- approval UI
- evidence presentation
- incident context views
- audit and status visibility

### `agent-platform`

Primary responsibility:

- runtime kernel for agent execution and orchestration

Key concerns:

- AgentScope-based orchestration
- session handling
- conversation state
- event streaming
- agent coordination
- interaction with policy, knowledge, and tool services

### `policy-center`

Primary responsibility:

- authorization, policy evaluation, approval routing, and control logic

Key concerns:

- policy decisions
- approval tiers
- environment and role checks
- action gating
- control outcomes such as `allow`, `deny`, and `require_approval`

### `identity-broker`

Primary responsibility:

- enterprise identity normalization and propagation

Key concerns:

- `Keycloak`
- `AD` federation
- group normalization
- role mapping
- token handling
- identity context propagation

### `skills-hub`

Primary responsibility:

- ingestion and indexing of team-managed Markdown skills

Key concerns:

- Git-based ingestion
- Markdown validation
- metadata normalization
- indexing
- retrieval enrichment for the agent platform

### `tool-gateway`

Primary responsibility:

- standardized connector and tool access layer

Key concerns:

- connector normalization
- `MCP` integration
- observability connectors
- Kubernetes connectors
- ticketing and collaboration connectors
- tool classification and contract enforcement

### `execution-runtime`

Primary responsibility:

- isolated execution of approved bounded actions

Key concerns:

- signed execution requests
- worker isolation
- action-specific adapters
- result capture
- execution audit

## Shared Modules

### `shared-contracts`

Use for:

- API schemas
- event schemas
- approval payloads
- policy request and response models
- audit record schemas

### `shared-sdk`

Use for:

- service clients
- tracing helpers
- auth helpers
- typed event producers or consumers

### `platform-ops`

Use for:

- Kubernetes manifests or Helm charts
- gateway routes
- environment overlays
- shared CI or deployment assets

## Dependency Model

### Allowed Direction

- `operator-portal` depends on published APIs and contracts
- `agent-platform` depends on contracts and calls other product services
- `policy-center` and `identity-broker` act as control authorities
- `execution-runtime` receives only approved and signed execution requests
- shared modules sit at the bottom of the dependency graph

### Avoid

- direct UI-to-worker control paths
- direct planner-to-executor bypasses
- policy logic copied into multiple projects
- scattered identity mapping logic
- large shared utility layers with unclear ownership

## Integration Model

The platform should prefer:

- stable internal APIs for service-to-service calls
- versioned event contracts for streaming and async workflows
- gateway-mediated external exposure
- explicit policy and approval checkpoints before execution

## Release Alignment

This workspace model supports the staged delivery plan already defined in the platform study:

- early releases emphasize `operator-portal`, `agent-platform`, `identity-broker`, and `tool-gateway`
- middle releases add `skills-hub` and deeper incident workflows
- later releases bring in `policy-center` and `execution-runtime` for bounded actions

## Recommended Adoption Path

### Phase 1

Use a single repository workspace with strong internal boundaries.

### Phase 2

Stabilize shared contracts and cross-project APIs.

### Phase 3

Only consider splitting selected projects into separate repositories if:

- ownership is mature
- release cadence differs materially
- dependency contracts are already stable

## Final Recommendation

Treat the repository as a modular workspace with product-oriented projects and small shared modules.

This gives the platform the best balance of:

- clarity
- maintainability
- integration discipline
- future release flexibility
