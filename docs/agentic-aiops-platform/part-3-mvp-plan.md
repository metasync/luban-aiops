# Part 3: MVP Plan

## Status

Completed.

This document defines the MVP based on the Part 2 reference architecture.

## Related Documents

This MVP plan should be read together with:

- `part-2-reference-architecture.md` for the target platform architecture
- `identity-and-authorization-design.md` for enterprise portal access, `SSO`, and identity propagation
- `authorization-matrix.md` for role, environment, request, and approval boundaries
- `policy-specification.md` for machine-enforceable policy outcomes and approval rules

## MVP Objective

Deliver the first useful and safe release of the enterprise-grade agentic AIOps platform by focusing on:

- operational visibility
- evidence-driven diagnosis
- team-owned skills retrieval
- enterprise `SSO` access to the web portal
- human-approved execution for a very small set of low-risk actions

The MVP should prove that the platform can provide real value to IT operations teams without attempting full autonomous operations.

## MVP Design Intent

The MVP should validate five core assumptions from Part 1 and Part 2:

- `AgentScope 2.0` is a practical runtime kernel for this platform
- the `large planner + smaller trusted executor` pattern is workable
- Git-managed Markdown skills can be operationalized as usable agent knowledge
- a `chat + structured operational context` UI is useful for operators
- policy and approval controls can make limited agentic action safe enough for early enterprise adoption

The MVP should also validate that the enterprise identity and control model is workable in practice through:

- `Keycloak + AD` based portal access
- role and group normalization
- approval attribution
- policy-driven execution gating

## MVP Principles

### 1. Diagnose before acting

The first release should be much stronger at:

- status checks
- incident enrichment
- evidence gathering
- runbook and skill retrieval
- recommendation generation

than at autonomous change execution.

### 2. Keep write actions narrow

The MVP should support only a very small number of approval-gated actions. All other actions should remain read-only or advisory.

### 3. Optimize for one end-to-end workflow

The MVP should be opinionated around a small number of high-value operator flows instead of being a generic agent platform from day one.

### 4. Make trust visible

Operators should be able to see:

- what evidence the agent used
- what tools were called
- what action is being proposed
- why approval is required

### 5. Prefer platform validation over feature breadth

The MVP should validate architecture, control boundaries, and operator usefulness before expanding connectors, actions, or agent counts.

## MVP Scope Summary

### In Scope

- one `web chat UI`
- one `API gateway` entry path
- one enterprise `SSO` path for portal access
- one primary `AgentScope 2.0` runtime service
- one `policy and approval` flow
- one `knowledge and skill ingestion` path
- limited read-only integrations for observability and Kubernetes
- one or two approval-gated low-risk actions
- audit logging and event streaming

### Out of Scope

- full autonomous remediation
- broad write access across enterprise systems
- dynamic unrestricted tool discovery and activation
- multi-tenant enterprise packaging in its full form
- advanced A2A federation with external agent platforms
- full CMDB and topology unification across all systems
- a large marketplace of skills or plugins

## Recommended MVP User Journeys

### Journey 1: Service Health Query

Example:

- operator asks for the current health of an application, service, or deployment

Expected MVP behavior:

- retrieve relevant service metadata
- query monitoring or observability sources
- summarize recent errors, alerts, and performance changes
- return concise status with supporting evidence
- suggest next checks or relevant skills

### Journey 2: Incident Triage and Enrichment

Example:

- operator pastes an alert or selects an incident from the UI

Expected MVP behavior:

- correlate recent logs, metrics, and deployment context
- summarize probable issue scope
- highlight likely affected services or workloads
- retrieve related team-authored skills and runbooks
- recommend ranked next steps

### Journey 3: Approval-Gated Low-Risk Action

Example:

- operator asks to restart a deployment or trigger a pre-approved diagnostic action

Expected MVP behavior:

- gather evidence first
- classify the action through policy
- require human approval before execution
- execute through isolated worker
- stream status and results back to the UI
- record complete audit trail

## Recommended First Actions

The MVP should keep actions intentionally small and safe.

Recommended first action set:

- `restart Kubernetes deployment` in non-production first, then optionally production with approval
- `rollout restart` or equivalent controlled service restart
- `collect diagnostics` such as pod status, events, or recent logs
- `create or update incident ticket comment`

Recommended initial production restriction:

- allow read-only everywhere the connectors support it
- allow action execution only for a very limited, approved subset

## MVP Functional Scope

### 1. Web Experience

Required UI capabilities:

- enterprise login via `SSO`
- chat interface
- session history
- streaming responses through `SSE`
- evidence panels
- approval cards
- execution result panels
- lightweight incident context display

The UI does not need a full NOC dashboard in the MVP. It needs just enough structure so the operator can trust and understand the agent output.

### 2. API Exposure

The MVP should expose the platform through the API gateway with:

- `REST` request entry
- `SSE` event streaming
- stable session-aware endpoints

This is important so future external systems can integrate without rebuilding the serving model.

### 3. Identity and Access

The MVP should include enterprise portal authentication through:

- `Keycloak` as the primary IdP integration layer
- federation to external account management such as `Active Directory`
- token-based authentication to the UI and API gateway
- normalized user and group claims for downstream policy evaluation

Minimum MVP identity outcomes:

- authenticated portal access
- basic role or group mapping
- user identity visible in approval records
- user identity recorded in audit logs

The detailed identity model for these outcomes is defined in:

- `identity-and-authorization-design.md`
- `authorization-matrix.md`
- `policy-specification.md`

### 4. Agent Runtime

The MVP should start with a small set of logical agents:

- `planner agent`
- `triage or diagnosis agent`
- `runbook or skill agent`
- `executor agent`
- `safety or reviewer agent`

These can initially be implemented with simple orchestration and do not need to become overly autonomous.

### 5. Policy and Approval

The MVP must include:

- risk classification for tool calls
- `allow`, `deny`, and `require_approval` outcomes
- approval request generation
- approval decision capture
- execution resume after approval

Even if simple at first, this is a core MVP capability because it validates the enterprise control model.

The MVP policy flow should consume at least:

- authenticated user ID
- team or group membership
- environment scope

The concrete enforcement shape for this policy flow is defined in:

- `authorization-matrix.md`
- `policy-specification.md`

### 6. Skill Ingestion

The MVP should support:

- one or more Git repositories for Markdown skills
- webhook or scheduled sync
- Markdown validation
- metadata extraction
- indexing into retrieval layer

Suggested minimum metadata:

- skill name
- owning team
- target system or service
- environment scope
- risk level
- tags

### 7. Knowledge Retrieval

The MVP should retrieve from:

- Markdown skills
- runbooks
- service metadata
- recent incident context

Full enterprise document ingestion is not required in the first release.

### 8. Integrations

Recommended initial connector set:

- `Kubernetes`
- one primary observability source such as `Elastic` or another existing monitoring platform
- one ticketing or collaboration integration

Suggested MVP baseline:

- `Kubernetes` for status checks and restart actions
- `Elastic` or chosen monitoring platform for logs and alert evidence
- `Jira`, `ServiceNow`, `Slack`, or `Teams` for notifications or incident updates

## MVP Service Breakdown

The MVP can be delivered with a relatively small set of services.

### Core Services

- `web-ui`
- `api-gateway`
- `keycloak integration or identity broker`
- `agent-service`
- `policy-service`
- `approval-service`
- `knowledge-service`
- `skill-ingestion-service`
- `audit-service`

### Execution Services

- `tool-gateway`
- `execution-worker`

### Supporting Stores

- session store
- knowledge index
- audit log store
- artifact store

## Suggested Technical Shape

### Models

Recommended early model strategy:

- one stronger model for planning and summarization
- one smaller or local trusted model for executor-side tasks

The MVP does not need an elaborate model router. A simple policy-driven model selection strategy is sufficient.

### Workspaces and Execution

Recommended early execution model:

- use AgentScope workspaces or sandbox-backed execution environments
- isolate tool execution from the planner
- use short-lived credentials where possible

### Eventing

Use event streaming for:

- partial responses
- tool status
- approval pending state
- execution completion

## Delivery Phases

### Phase 0: Foundation

Goal:

- make the platform runnable end to end in development and one target Kubernetes environment

Deliverables:

- repository structure
- base deployment manifests or Helm charts
- API gateway route
- `Keycloak` integration for portal login
- basic web UI shell
- basic AgentScope runtime service
- session persistence
- event streaming path

### Phase 1: Read-Only Copilot

Goal:

- deliver a useful read-heavy operational assistant

Deliverables:

- service health query flow
- observability connector
- Kubernetes read-only connector
- runbook and skill retrieval
- evidence-aware answers
- audit logging for requests and tool calls

Success condition:

- operators can ask useful operational questions and receive grounded answers with evidence

### Phase 2: Incident Triage MVP

Goal:

- support alert or incident enrichment and guided diagnosis

Deliverables:

- incident intake flow
- alert enrichment
- correlation of logs, metrics, and recent changes where possible
- ranked next-step recommendations
- ticket or collaboration update integration

Success condition:

- operators can use the platform to shorten triage time and get better first-response context

### Phase 3: Approval-Gated Actions

Goal:

- enable one or two low-risk actions safely

Deliverables:

- policy classification
- approval request workflow
- isolated execution worker
- one approved restart or diagnostic action
- execution result streaming
- full audit trail for approvals and execution

Success condition:

- operators can approve and run a bounded action through the platform with visible evidence and full traceability

## Suggested Milestone Sequence

### Milestone 1

- basic UI
- API gateway route
- SSO login through `Keycloak`
- AgentScope runtime
- session and SSE working

### Milestone 2

- Kubernetes read-only connector
- observability read-only connector
- service health flow

### Milestone 3

- skill ingestion from Git
- knowledge retrieval
- runbook-aware answers

### Milestone 4

- incident triage flow
- external incident or collaboration update

### Milestone 5

- policy service
- approval cards in UI
- isolated low-risk execution

## Suggested Team Deliverables

### Platform Team

- runtime service
- API gateway integration
- SSO and IdP integration
- UI shell
- deployment automation
- observability and audit plumbing

### Operations Domain Teams

- Markdown skills and runbooks
- connector validation for owned systems
- approval and risk policy input
- operator acceptance feedback

### Security and Governance Stakeholders

- access model review
- SSO and group mapping review
- permission boundary validation
- audit review
- production rollout conditions

## Recommended MVP Success Metrics

### Usability Metrics

- percentage of operator questions answered with useful evidence
- operator satisfaction for incident triage support
- time to first meaningful response

### Operational Metrics

- reduction in manual triage time
- reduction in time spent locating the right runbook or skill
- percentage of proposed actions that are approved versus rejected

### Safety Metrics

- number of blocked unsafe actions
- number of action attempts outside allowed scope
- number of approval or audit failures
- authentication or authorization failures for protected routes

### Platform Metrics

- agent response latency
- tool call latency
- SSE stream reliability
- connector failure rate

## Recommended Non-Goals for MVP

The MVP should not attempt to prove:

- generalized autonomous IT operations
- self-healing production infrastructure at scale
- organization-wide tool coverage
- complete knowledge ingestion across all enterprise documents
- advanced multi-agent federation across many teams or domains

## Major Risks and Mitigations

### Risk 1: Over-scoping the first release

Mitigation:

- limit to a few operator journeys
- keep integrations narrow
- defer broad action support

### Risk 2: Weak knowledge quality

Mitigation:

- start with team-owned curated skills
- require metadata and validation
- prefer freshness and ownership-aware retrieval

### Risk 3: Unsafe action execution

Mitigation:

- require approval
- isolate execution
- keep initial action list very small
- enforce explicit risk categories

### Risk 4: UI feels like an untrusted chatbot

Mitigation:

- show evidence
- show tool calls
- show approval reasoning
- avoid opaque answers

### Risk 5: Connector complexity slows delivery

Mitigation:

- start with only one observability source
- start with Kubernetes plus one ticketing or collaboration system
- add connectors only after the first workflow works well

### Risk 6: Identity integration delays MVP delivery

Mitigation:

- start with one IdP path through `Keycloak`
- federate only one external directory source first
- keep early group mapping simple
- defer advanced tenant-specific identity models until after MVP

## Recommended MVP Decision

The MVP should be positioned as an `incident and operations copilot with bounded action capability`, not as a fully autonomous operations platform.

That means the first release should be strongest at:

- operational Q and A
- evidence gathering
- incident enrichment
- runbook and skill retrieval
- approval-gated low-risk actions

This is the fastest path to proving platform value while preserving enterprise trust.

## Suggested Next Step After MVP

If the MVP succeeds, the next expansion areas should be:

- broader observability and CMDB integration
- richer incident graph and dependency reasoning
- more robust approval policies
- more action types with environment-aware controls
- stronger multi-team and multi-tenant support
- richer API productization for external consumers

## Final Recommendation

Build the MVP around a single strong end-to-end path:

- operator asks about service health or an incident
- platform gathers evidence from observability and Kubernetes
- platform retrieves Git-managed team skills
- platform proposes next steps
- platform executes only a very small number of approval-gated low-risk actions

This is the best MVP shape for validating the architecture, enterprise controls, and operator usefulness of the proposed agentic AIOps platform.

## Traceability

This MVP is intentionally aligned to the wider document set:

- framework selection comes from `part-1-decision-matrix.md`
- architecture comes from `part-2-reference-architecture.md`
- identity and access controls come from `identity-and-authorization-design.md`
- authorization boundaries come from `authorization-matrix.md`
- machine-enforceable policy behavior comes from `policy-specification.md`
