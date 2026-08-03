# Product Boundaries

## Objective

Define the responsibility boundaries, integration points, and ownership model for each product project in the workspace.

## Boundary Principles

### 1. Each product should solve one primary platform problem

A product may expose multiple APIs or internal modules, but it should still have one clear reason to exist.

### 2. Control responsibilities should not be blurred

Identity, policy, orchestration, and execution should remain separate so that trust boundaries stay visible.

### 3. UI should not own backend rules

The `operator-portal` should render decisions and flows, but policy and authorization should remain authoritative in backend services.

### 4. Execution should not bypass policy

No execution path should exist that allows a worker or tool adapter to skip policy or approval checks.

### 5. Knowledge should be reusable, not embedded

Runbooks and Markdown skills should flow through a dedicated knowledge path instead of being copied into agent prompts manually.

## Product Responsibility Matrix

| Product | Primary Responsibility | Owns | Does Not Own |
|---|---|---|---|
| `operator-portal` | operator-facing UX | login UX, chat UX, evidence views, approval UX | policy decisions, identity normalization, direct execution |
| `agent-platform` | agent runtime and orchestration | session state, orchestration flow, event streaming, reasoning integration | policy authority, identity authority, direct privileged execution |
| `policy-center` | authorization and approval control | policy evaluation, approval rules, control outcomes | UI rendering, identity federation, connector logic |
| `identity-broker` | identity normalization | `SSO`, token normalization, role mapping, group mapping | policy decisions, portal UX, execution logic |
| `skills-hub` | skill lifecycle and retrieval support | ingestion, validation, indexing, metadata, skill retrieval support | live tool execution, policy logic |
| `platform-gateway` | portal-facing API edge | portal token verification, action policy for portal routes, chat/session proxying, token delegation | connector logic, tool execution, policy authority |
| `tool-gateway` | connector standardization | tool contracts, system connectors, `MCP` integration, tool classification | approval logic, session orchestration, portal UX, portal-facing routes |
| `execution-runtime` | bounded action execution | isolated workers, execution adapters, result reporting | approval authority, identity normalization, UX logic |

## Product Interfaces

### `operator-portal`

Consumes:

- portal auth endpoints
- chat and session APIs
- approval APIs
- audit and status APIs

Publishes:

- user interactions
- approval responses
- UI events where needed

### `agent-platform`

Consumes:

- identity context
- policy decisions
- knowledge retrieval
- tool access

Publishes:

- session APIs
- conversation and event streams
- requests for policy evaluation
- requests for execution after approval

### `policy-center`

Consumes:

- normalized identity context
- action requests
- environment and resource context

Publishes:

- control decisions
- approval requests
- approval state changes

### `identity-broker`

Consumes:

- upstream identity provider tokens and claims

Publishes:

- normalized identity context
- role mappings
- service-consumable identity claims

### `skills-hub`

Consumes:

- Git repository events or scheduled sync input

Publishes:

- indexed skill metadata
- retrieval responses
- validation outcomes

### `platform-gateway`

Consumes:

- portal bearer tokens and identity-broker verification material
- agent-platform session and chat APIs
- delegated-token exchange from `identity-broker`

Publishes:

- portal-facing `/api/v1` routes (auth, sessions, chat, runtime)
- proxied streaming responses
- delegated tokens to downstream services

### `tool-gateway`

Consumes:

- tool invocation requests
- connector credentials through secure runtime mechanisms

Publishes:

- normalized tool responses
- tool metadata
- connector health and execution status

### `execution-runtime`

Consumes:

- approved signed execution requests

Publishes:

- execution status
- execution results
- execution audit artifacts

## Ownership Model

### Recommended Ownership Groups

- `operator-portal`
  - frontend or user experience team
- `agent-platform`
  - agent platform or orchestration team
- `policy-center`
  - platform security or control-plane team
- `identity-broker`
  - identity and platform access team
- `skills-hub`
  - knowledge platform or operations enablement team
- `platform-gateway`
  - platform security or platform edge team
- `tool-gateway`
  - integrations or platform connectors team
- `execution-runtime`
  - automation or operations execution team

In smaller organizations, several of these may be owned by one platform team at first, but the boundaries should still remain explicit.

## Boundary Rules

### Rule 1

`operator-portal` may request actions, but it does not authorize them.

### Rule 2

`agent-platform` may propose actions, but it does not directly execute privileged operations.

### Rule 3

`policy-center` is authoritative for action outcomes such as:

- `allow`
- `deny`
- `require_approval`
- `allow_with_conditions`

### Rule 4

`identity-broker` is authoritative for normalized user identity and group-to-role mapping.

### Rule 5

`tool-gateway` is authoritative for connector standardization and tool contract enforcement.

### Rule 6

`execution-runtime` only executes approved and signed requests.

## Integration Patterns

### Synchronous

Use for:

- chat requests
- policy evaluation
- identity normalization
- retrieval requests

### Asynchronous

Use for:

- event streaming
- approval state changes
- skill ingestion events
- execution progress updates

## Release Fit

### Early Releases

Primary products:

- `operator-portal`
- `agent-platform`
- `identity-broker`
- `platform-gateway`
- `tool-gateway`

### Middle Releases

Primary additions:

- `skills-hub`
- deeper incident workflows across `agent-platform` and `tool-gateway`

### Later Releases

Primary additions:

- `policy-center`
- `execution-runtime`

## Verification Questions

Use these questions to validate whether a product boundary is healthy:

- does this product have one clear reason to exist?
- can its interfaces be described clearly?
- can ownership be assigned without confusion?
- can it evolve without tightly coupling to unrelated products?
- does it preserve the platform trust model?

## Final Recommendation

Keep the platform split into explicit product projects with strict control boundaries and published contracts.

This makes the workspace easier to understand, easier to maintain, and safer to evolve as enterprise requirements grow.
