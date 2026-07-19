# Part 2: Reference Architecture

## Status

Completed.

This document defines the reference architecture for the selected framework from Part 1:

- `AgentScope 2.0`

## Related Documents

This document is complemented by the following supporting documents:

- `part-3-mvp-plan.md` for the first-release delivery scope
- `identity-and-authorization-design.md` for `SSO`, `Keycloak`, `AD`, and identity propagation
- `authorization-matrix.md` for role, environment, and approval boundaries
- `policy-specification.md` for machine-enforceable policy structure

## Architecture Goal

Build an enterprise-grade, Kubernetes-native, agentic AIOps platform for IT operations that:

- supports a `large-model planner + smaller trusted executor` pattern
- integrates with observability and operational systems such as `Elastic`, `ITRS`, ticketing tools, and Kubernetes
- exposes stable APIs for other applications and services through an enterprise API gateway
- integrates the web portal with enterprise `SSO` and federated identity providers such as `Keycloak` backed by `AD`
- enforces strong security boundaries, permissions, and human approval for risky actions
- allows operations teams to manage their own skills and runbooks in Git-managed Markdown repositories

## Core Design Principles

### 1. Treat the platform as a control system, not only a chat system

The web chat UI is important, but the platform should be designed as an operational control plane with audit, approval, policy, and execution isolation.

### 2. Separate reasoning from execution

Use stronger planning models for:

- problem decomposition
- summarization
- evidence synthesis
- action proposal

Use smaller or local trusted models for:

- tool selection within approved boundaries
- tool argument generation
- execution-side reasoning
- on-prem or privileged environment interaction

### 3. Default to bounded autonomy

The agent should be able to act autonomously only within explicit limits. Risky actions should move through approval workflows and isolated execution paths.

### 4. Put protocol and gateway concerns first

The platform should expose stable service interfaces so that external consumers can call it through an enterprise API gateway instead of relying on custom ad hoc wrappers.

### 5. Make skills and knowledge team-owned

Operational knowledge should be maintained by the teams who own the systems, using Git-managed Markdown artifacts with structured metadata and validation.

### 6. Design for Kubernetes from the start

Control-plane services should be horizontally scalable and stateless where possible. Execution environments should be isolated and replaceable.

## Why AgentScope 2.0 Fits This Architecture

The selected reference architecture leans on the following AgentScope 2.0 capabilities:

- `event system` for rich streaming execution and interactive frontends
- `permission system` for bounded tool use and approval gating
- `workspace system` for isolated tool, skill, and MCP execution environments
- `agent service` for REST and SSE exposure with multi-session and multi-tenant support
- `MCP and A2A support` for tool and agent interoperability
- `multi-tenant and multi-session service model` for enterprise serving

These features make AgentScope a suitable runtime kernel, but not the entire platform. Additional platform services are still required around identity, policy, approvals, skill lifecycle, and observability.

## High-Level Platform Shape

The platform is divided into two major planes:

- `control plane`
- `execution plane`

### Control Plane

The control plane is responsible for:

- user interaction
- session orchestration
- planning
- policy enforcement
- approval routing
- knowledge retrieval
- audit and observability
- service exposure through the API gateway

### Execution Plane

The execution plane is responsible for:

- isolated tool execution
- MCP client and server interaction
- access to on-prem and environment-specific systems
- controlled runbook and automation execution
- secure handling of short-lived credentials

## Reference Architecture Layers

### 1. Client Layer

This layer contains:

- `web chat UI`
- `operator dashboards`
- `incident and approval views`
- `service health and evidence panels`
- `external application consumers`

The primary user experience should not be only a chat box. It should combine chat with structured operational context such as:

- affected services
- recent changes and deployments
- correlated alerts
- logs, metrics, and traces summary
- approval cards
- execution timeline

### 2. API Gateway Layer

This sits in front of the platform runtime and is mandatory even though AgentScope can expose native endpoints.

The API gateway should handle:

- authentication and authorization entry
- API versioning
- route standardization
- rate limiting
- quotas
- request validation
- tenant-aware routing
- audit-friendly access logs

Recommended exposed interfaces behind the gateway:

- `REST API`
- `SSE streaming API`
- `OpenAI-compatible endpoints` where useful
- `AG-UI compatible streaming endpoints`
- future `MCP or A2A-facing service endpoints` when needed

### 2A. Identity and Access Federation Layer

This layer should be treated as a first-class enterprise platform component.

Recommended model:

- web portal authenticates users through `OIDC` or `SAML` backed by `Keycloak`
- `Keycloak` federates identity to an external directory such as `Active Directory`
- platform services trust gateway-forwarded identity only after token validation
- group and role claims are normalized into platform authorization attributes

Primary responsibilities:

- user authentication for the web portal
- federation with enterprise account management systems
- token issuance and refresh
- group and role mapping
- tenant and environment scoping inputs for policy decisions
- identity propagation into agent sessions, approvals, and audit logs

### 3. Agent Runtime and Orchestration Layer

This is the `AgentScope 2.0` based core runtime.

Responsibilities:

- maintain sessions and runtime context
- stream execution events
- coordinate planner, specialist, and executor agents
- enforce tool and resource permissions
- interface with workspace backends
- interact with knowledge retrieval and memory components
- pause and resume for approvals or external execution callbacks

Recommended logical agents:

- `planner agent`
- `alert triage agent`
- `correlation agent`
- `diagnosis agent`
- `runbook agent`
- `executor agent`
- `reviewer or safety agent`
- `ticket and communications agent`

### 4. Policy and Approval Layer

This layer should be separate from prompts and agent definitions.

Responsibilities:

- classify actions by risk
- enforce `allow`, `deny`, or `require_approval` outcomes
- evaluate user, role, tenant, environment, and target-system context
- route human approval requests
- record approval decisions and evidence
- control session-level or tool-level overrides where justified

Policy decisions should consider:

- tool type
- target system
- environment such as `dev`, `test`, `prod`
- action category such as `read`, `write`, `restart`, `scale`, `delete`
- change window
- operator role
- incident severity

### 5. Knowledge and Skill Layer

This layer provides the operational knowledge the agents rely on.

It should include:

- runbooks
- SOPs
- Markdown skills
- incident history
- postmortems
- service ownership data
- topology and CMDB data
- change records

This layer should support:

- semantic retrieval
- structured filtering by team, service, environment, and risk
- version-aware retrieval
- evidence packaging for planner and diagnosis agents

### 6. Tool Gateway Layer

This is the normalized integration surface between agents and external systems.

Responsibilities:

- wrap external systems in approved tool contracts
- expose tools through MCP where appropriate
- enforce schema validation
- annotate tools with risk and ownership metadata
- separate read-only tools from action tools
- centralize retries, timeouts, and logging

This layer should include connectors for:

- observability platforms such as `Elastic`, `ITRS`, `Prometheus`, `Grafana`, `OpenTelemetry` backends
- Kubernetes APIs
- ticketing systems such as `Jira` or `ServiceNow`
- collaboration systems such as `Slack` or `Teams`
- CMDB and topology systems
- deployment and change-management systems
- internal enterprise APIs

### 7. Execution Worker Layer

Risky or stateful operations should execute in isolated workers, not directly inside the planner runtime.

Responsibilities:

- execute approved actions
- run diagnostics and automation
- call local or on-prem services
- store execution artifacts and logs
- support retries and compensation hooks

Execution workers can be implemented as:

- dedicated pods
- short-lived Kubernetes Jobs
- sandbox-backed workspaces
- environment-scoped runner pools

### 8. Platform Data and Observability Layer

This layer stores state and provides platform-level visibility.

Core stores typically include:

- session and conversation state
- approval events
- audit logs
- knowledge indexes
- skill metadata index
- execution artifacts
- memory and retrieval indexes

Platform observability should include:

- OpenTelemetry traces
- metrics for runs, approvals, failures, and tool latency
- structured logs
- replay and investigation support

## Proposed Runtime Topology

### Control Plane Services

Recommended core services:

- `web-ui`
- `api-gateway`
- `identity-broker or idp-integration`
- `agent-service`
- `policy-service`
- `approval-service`
- `knowledge-service`
- `skill-ingestion-service`
- `audit-service`
- `session-state-service`
- `event-stream-service`

### Execution Plane Services

Recommended execution-side services:

- `tool-gateway`
- `mcp-broker or mcp-connectivity service`
- `execution-workers`
- `sandbox-manager`
- `connector-specific workers`
- `credential-broker`

## Detailed Component Model

### Web UI

The UI should provide:

- enterprise login through `SSO`
- streaming responses
- evidence cards
- tool call previews
- approval prompts
- operator intervention controls
- command and action results
- incident context panels

Important UX principle:

- show what the agent is doing, not only what it says

### Agent Service

The AgentScope-based agent service should expose:

- session-aware REST endpoints
- SSE endpoints for live execution streams
- resumable runs
- multi-turn session support
- rich event delivery to the frontend

The agent service should not directly embed all business logic. It should orchestrate calls into policy, retrieval, and execution services.

### Workspace and Sandbox Manager

The workspace abstraction should be used as the execution-environment boundary for tools, skills, offloaded context, and MCP processes.

Preferred workspace strategy for this platform:

- local workspace for development only
- container or sandbox-backed workspaces for shared and production deployments
- session-scoped or user-scoped workspaces depending on isolation requirements

For enterprise production use, prefer Kubernetes-friendly workspace backends and avoid unrestricted host-level execution.

### Policy Service

This service should evaluate every tool invocation request before execution.

Suggested outcomes:

- `allow`
- `deny`
- `require_approval`
- `delegate to backend executor`

The last option is important for high-risk actions. It allows the agent to propose an action while the real execution is carried out by a separate backend service after approval.

The policy service should also consume identity attributes such as:

- authenticated user ID
- team membership
- directory groups
- environment entitlements
- privileged-role flags

### Approval Service

This service should:

- create approval requests
- package evidence and proposed arguments
- notify operators
- record approval outcomes
- support expiry and escalation
- resume blocked agent runs after decision

### Skill Ingestion Service

This service manages Git-based Markdown skills from separate team repositories.

Responsibilities:

- poll or receive webhooks from skill repos
- validate Markdown structure and metadata
- check ownership and required fields
- build searchable indexes
- publish approved skill revisions to the knowledge layer

Suggested Markdown skill structure:

- frontmatter:
  - skill name
  - owning team
  - systems covered
  - risk level
  - supported environments
  - prerequisites
  - tags
- content:
  - purpose
  - checks
  - steps
  - rollback guidance
  - escalation conditions
  - expected outcomes

### Knowledge Service

This service should provide:

- vector retrieval
- metadata filtering
- artifact lookup
- version-aware retrieval
- evidence packaging for downstream agents

The agent should not retrieve raw content indiscriminately. Retrieval should be scoped by:

- service
- environment
- team
- incident type
- time window
- approved knowledge sources

## End-to-End Request Flow

### Flow 1: Operational Query

Example:

- operator asks for application or service health

Flow:

1. user calls platform through web UI or external API
2. API gateway authenticates and routes the request
3. agent service loads session and user context
4. planner or triage agent determines which evidence is required
5. tool gateway calls read-only observability and topology tools
6. knowledge service retrieves relevant skills and runbooks
7. runtime streams reasoning, evidence, and summaries back to the UI
8. result is returned with suggested next actions if needed

### Flow 2: Risky Change Request

Example:

- operator asks to restart a service or scale a deployment

Flow:

1. planner agent proposes the action and gathers evidence
2. policy service classifies the tool invocation as approval-required
3. approval service creates an approval request with:
   - target system
   - intended action
   - generated arguments
   - evidence summary
   - rollback notes if available
4. UI shows approval card to authorized operator
5. upon approval, execution worker receives a signed execution request
6. worker executes in isolated environment using short-lived credentials
7. results stream back through the event system
8. audit service records the full chain

### Flow 3: Incident Triage

Example:

- alert arrives from observability platform

Flow:

1. event ingestion service normalizes the alert
2. triage agent enriches it with logs, metrics, topology, and recent changes
3. diagnosis agent forms likely-cause hypotheses
4. runbook agent finds relevant team-authored Markdown skills
5. reviewer or safety agent checks whether proposed actions are allowed
6. operator receives a structured incident summary and ranked next steps
7. optional low-risk actions proceed automatically if policy allows

## Security Architecture

### Trust Zones

Define three trust zones:

- `reasoning zone`
- `control zone`
- `execution zone`

#### Reasoning Zone

Contains:

- planner models
- summarizers
- diagnosis agents

Characteristics:

- may use stronger external models
- should receive sanitized and policy-approved context
- should not hold direct high-privilege credentials

#### Control Zone

Contains:

- agent runtime
- policy service
- approval service
- session state
- audit logging

Characteristics:

- central authority for decisions and flow control
- no direct unrestricted infrastructure mutation

#### Execution Zone

Contains:

- isolated workers
- MCP processes
- connector runners
- privileged automation

Characteristics:

- tightly scoped credentials
- environment isolation
- explicit action logging

### Permission Model

Recommended permission categories:

- `read-only`
- `low-risk write`
- `high-risk action`
- `destructive action`

Suggested policy defaults:

- allow `read-only`
- require approval for `low-risk write` in production
- require strong approval for `high-risk action`
- deny `destructive action` unless explicitly enabled under controlled workflows

### Identity and Credentials

Use enterprise identity integration for:

- SSO
- IdP federation through `Keycloak` or equivalent
- external directory integration such as `AD`
- user-to-role mapping
- group-to-policy mapping
- team scoping
- environment scoping

Recommended web access pattern:

1. user signs in to the portal through `Keycloak`
2. `Keycloak` authenticates directly or federates to `AD`
3. gateway validates the issued token
4. trusted identity claims are forwarded to the platform
5. session state stores the normalized identity context for policy and audit

Recommended identity propagation pattern:

- approval requests include requester identity and group context
- execution requests carry a signed actor identity reference
- audit events store both human requester and system executor identities
- privileged actions remain attributable to the initiating operator

Execution workers should use:

- short-lived credentials
- workload identity where possible
- no long-lived credentials embedded in prompts or workspace files

### Audit Requirements

Audit records should capture:

- who initiated the request
- what context and evidence were retrieved
- what tool calls were proposed
- what policy decision was made
- who approved or denied
- what execution result occurred
- what final operator-visible result was returned

## Git-Based Markdown Skills Architecture

### Ownership Model

Each operations team should manage one or more dedicated Git repositories containing Markdown skills and runbooks.

Benefits:

- clear ownership
- normal pull request review workflow
- Git history and traceability
- independent updates by teams

### Platform Workflow

Recommended lifecycle:

1. team updates a skill in its Git repository
2. repository CI validates structure and metadata
3. merge to approved branch triggers webhook
4. skill ingestion service fetches changed revision
5. parser validates metadata and content structure
6. knowledge service indexes the approved revision
7. new revision becomes available to retrieval

### Governance

The platform should support:

- team ownership validation
- signed or controlled source branches
- optional approval for production-scope skills
- environment-specific skill availability
- rollback to prior skill revisions

## MCP and A2A Integration Model

### MCP Usage

Use `MCP` primarily for:

- standardized tool exposure
- data and resource access
- connector interoperability

Recommended MCP pattern:

- platform-managed MCP connectors for approved systems
- MCP servers or clients attached to workspaces or tool gateway services
- no auto-executable discovery without policy classification

### A2A Usage

Use `A2A` for:

- collaboration across agent domains
- integrating specialized external agents
- future federation with other enterprise agent systems

Recommended rule:

- discovery may be dynamic
- activation must still be policy-controlled and tenant-scoped

## Knowledge and RAG Architecture

The retrieval stack should index:

- Markdown skills
- runbooks
- SOPs
- incident tickets
- postmortems
- service metadata
- topology and dependency data
- recent changes and deployments

Recommended retrieval pipeline:

1. classify request or incident type
2. gather metadata filters
3. retrieve semantically relevant artifacts
4. re-rank based on ownership, freshness, environment, and risk
5. package evidence for the agent

Avoid sending the full corpus into the planner. Always retrieve and filter first.

## Kubernetes Deployment Model

### Namespace Strategy

A practical starting model is:

- shared namespace for control-plane services
- separate namespaces for execution workers by environment
- optional tenant-specific namespaces for regulated or large customers

### Deployment Patterns

Recommended patterns:

- stateless Deployments for control-plane APIs
- Stateful or external managed backends for session and retrieval stores
- Jobs or dedicated worker Deployments for execution tasks
- ingress or service mesh in front of the API gateway

### Scalability Model

Scale independently:

- UI and API ingress
- agent runtime services
- retrieval services
- execution workers
- connector workers

Autoscaling triggers can include:

- request rate
- active sessions
- queued approvals
- queued execution jobs
- tool invocation latency

## Recommended Initial Boundaries

For the first production architecture, keep these boundaries explicit:

- planner agent cannot directly run privileged tools
- execution workers cannot bypass policy service
- approval service is required for risky production actions
- skill ingestion is separate from runtime inference
- API gateway is the front door for external consumers

## Recommended Architecture Decision

Use `AgentScope 2.0` as the runtime kernel in a layered architecture consisting of:

- `web and API access layer`
- `agent orchestration layer`
- `policy and approval layer`
- `knowledge and skills layer`
- `tool gateway layer`
- `isolated execution layer`
- `platform data and observability layer`

This architecture best matches the enterprise AIOps goals established in Part 1 while preserving strong control boundaries and future extensibility.

## Implementation Notes for Part 3

Part 3 should turn this reference architecture into a realistic MVP. The MVP should not attempt to build every capability in this document.

Recommended MVP focus:

- one chat UI
- one API gateway path
- one agent runtime service
- one policy and approval flow
- a minimal skill-ingestion pipeline
- a small number of observability and Kubernetes connectors
- read-heavy diagnostics plus a very small set of approval-gated actions

## References

- AgentScope 2.0 overview: https://docs.agentscope.io/versions/2.0.2/en
- AgentScope 2.0 release blog: https://java.agentscope.io/v2/en/blogs/agentscope-v2-release.html
- AgentScope workspace docs: https://docs.agentscope.io/versions/2.0.2/en/building-blocks/workspace
- AgentScope repository: https://github.com/agentscope-ai/agentscope
