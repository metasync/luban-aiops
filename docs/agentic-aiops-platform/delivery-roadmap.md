# Delivery Roadmap

## Objective

Define a delivery roadmap for the enterprise-grade agentic AIOps platform where each release:

- is self-contained
- adds one major capability on top of the previous release
- has explicit integration points
- is straightforward for operations teams to verify

This roadmap provides a release-by-release delivery view. Implementation details are tracked in feature specs under `docs/specs/`.

## Roadmap Principles

### 1. One release, one major value theme

Every release should have a clear purpose that operations teams can understand without reading the full platform design.

### 2. Releases should stack, not sprawl

Each release should extend the previous one rather than opening many parallel fronts of partially completed work.

### 3. Validation must happen inside each release

Each release must be verifiable by real user workflows, not only by engineering-level unit or integration tests.

### 4. Integration points should be visible

Each release should name the key service and API boundaries that must work together before the release is considered complete.

### 5. Trust should increase alongside capability

As the platform gains more power, it must also gain stronger identity, policy, approval, and audit behavior.

## Recommended Release Sequence

The roadmap is designed as six stacked releases:

| Release | Theme | Primary User Value | Risk Level |
|---|---|---|---|
| `R0` | Platform Foundation | Usable portal and runtime baseline | low |
| `R1` | Read-Only Operations Copilot | Grounded operational answers | low |
| `R2` | Skills and Grounded Guidance | Team-owned procedural guidance in answers | low |
| `R3` | Incident Triage and Collaboration | Faster and better triage | medium |
| `R4` | Approval-Gated Bounded Actions | Safe operational action through approval | medium-high |
| `R5` | Hardening and External Consumption | Broader adoption and stable reuse | medium |

## Release Details

## R0: Platform Foundation

### Theme

Make the platform real, runnable, and accessible.

### What It Delivers

- Kubernetes-deployed control-plane baseline
- enterprise portal login through `Keycloak`
- API gateway entry
- basic AgentScope runtime
- session handling
- event streaming to the UI

### Why It Comes First

All later releases depend on stable access, session, and serving foundations.

### Integration Points

- `web-ui` <-> `Keycloak`
- `web-ui` <-> `api-gateway`
- `api-gateway` <-> `agent-service`
- `agent-service` <-> session store
- `agent-service` <-> event streaming channel

### How Operations Teams Validate It

- log in through `SSO`
- open the portal successfully
- start a session
- receive a streamed response

### Release Completion Signal

Operations users can reliably access and use the portal in the target environment.

## R1: Read-Only Operations Copilot

### Theme

Give operators grounded answers before giving the platform write capabilities.

### What It Delivers

- service health query flow
- read-only Kubernetes access
- read-only observability access
- evidence-backed responses
- audit for read-only tool access

### Why It Comes Next

This is the first low-risk way to prove platform usefulness.

### Integration Points

- `agent-service` <-> `tool-gateway`
- `tool-gateway` <-> Kubernetes
- `tool-gateway` <-> observability source
- `agent-service` <-> UI evidence panels

### How Operations Teams Validate It

- ask about a service or deployment
- review returned status and supporting evidence
- confirm the system used the correct data sources

### Release Completion Signal

Operators say the platform is useful for real status and diagnostic questions.

## R2: Skills and Grounded Guidance

### Theme

Blend live evidence with team-owned operational knowledge.

### What It Delivers

- Git-based skill ingestion
- Markdown validation
- searchable knowledge retrieval
- runbook-aware answers
- cited skills and sources in the UI

### Why It Comes Next

After live evidence is working, team-owned guidance is the next layer of trust and utility.

### Integration Points

- skill repo <-> `skill-ingestion-service`
- `skill-ingestion-service` <-> `knowledge-service`
- `knowledge-service` <-> `agent-service`
- `agent-service` <-> UI source display

### How Operations Teams Validate It

- add or update a skill in Git
- verify the platform ingests it
- ask a relevant operational question
- confirm the platform cites and uses the expected skill

### Release Completion Signal

Operations teams trust that their own runbooks and skills are entering the answer flow correctly.

## R3: Incident Triage and Collaboration

### Theme

Help operators respond faster and with better context during incidents.

### What It Delivers

- incident or alert intake
- enrichment and correlation
- ranked next-step recommendations
- update flow to ticketing or collaboration systems
- richer incident context in the UI

### Why It Comes Next

This release turns the platform from a query assistant into an incident-support tool.

### Integration Points

- incident source <-> `agent-service`
- `agent-service` <-> `knowledge-service`
- `agent-service` <-> `tool-gateway`
- `agent-service` <-> collaboration or ticket connector
- `web-ui` <-> incident context view

### How Operations Teams Validate It

- feed a real or simulated alert into the platform
- verify the summary, evidence, and next steps
- confirm ticket or collaboration updates are usable

### Release Completion Signal

Operations users report that the platform improves triage quality and speed on sample incidents.

## R4: Approval-Gated Bounded Actions

### Theme

Allow the platform to act safely within explicit approval and policy boundaries.

### What It Delivers

- policy engine
- approval workflow
- approval queue and action cards
- isolated execution worker
- signed execution requests
- first bounded operational actions

### Why It Comes Next

Only after identity, evidence, grounding, and triage are stable should the platform be allowed to take actions.

### Integration Points

- `agent-service` <-> `policy-service`
- `policy-service` <-> `approval-service`
- `approval-service` <-> `web-ui`
- `approval-service` <-> `execution-worker`
- `execution-worker` <-> `tool-gateway`
- `execution-worker` <-> `audit-service`

### How Operations Teams Validate It

- request a bounded action such as `restart-service`
- verify the system returns `require_approval`
- approve the action as an authorized approver
- verify the worker executes and returns results
- confirm the full audit chain is present

### Release Completion Signal

Operations and governance teams agree that bounded actions are sufficiently trustworthy for controlled use.

## R5: Hardening and External Consumption

### Theme

Make the platform easier to operate, govern, and consume beyond the initial user group.

### What It Delivers

- better policy testing and rollout controls
- stronger reliability and observability
- stable API productization
- richer audit reporting
- better internal platform operations visibility

### Why It Comes Last

This release builds on proven operator value and focuses on broader rollout readiness.

### Integration Points

- policy repo <-> CI/CD
- `api-gateway` <-> external consumers
- `audit-service` <-> reporting interface
- all core services <-> dashboards and metrics

### How Operations Teams Validate It

- use stable platform APIs from another internal application
- inspect audit trails for real workflows
- verify policy changes move through promotion safely
- confirm platform stability under realistic usage

### Release Completion Signal

The platform is ready for wider enterprise adoption beyond the initial user group.

## Release Stacking Logic

### Why This Sequence Works

- `R0` creates access and runtime
- `R1` proves read-only value
- `R2` adds team-owned knowledge
- `R3` adds incident workflow value
- `R4` adds safe action capability
- `R5` makes the platform ready for broader production use

This avoids introducing powerful execution features before the platform has earned user trust.

## Exploration Backlog

Candidates identified during the AgentScope utilization audit (post-R3) that
are not yet decision-complete enough for a spec. Each needs a spike before
promotion; until then they stay here.

| Candidate | Question to answer in a spike | Likely home |
|---|---|---|
| MCP exposure of tool-gateway connectors | Can connectors be served as MCP endpoints without bypassing policy enforcement and audit? | own spec after R4 policy surfaces settle |
| Semantic (vector) skill retrieval | Does an Elasticsearch vector store measurably beat skills-hub's scoring search on our corpus? We already run Elastic (SPEC-011). | skills-hub enhancement spec |
| Long-term operator memory | Do agentscope long-term-memory middlewares (mem0/reme) add real triage continuity across sessions, and where would that state live? ReME was evaluated 2026-08-20 and does not fit as-is (file-based vault vs Postgres durability, unaudited LLM write-back, no per-user isolation); a spike needs a governed storage backend, per-tenant scoping, and audit hooks first (see `docs/workspace/agentscope-utilization-audit.md`). | follow-up to SPEC-017 durability |
| Kernel-side SQL storage | When would adopting `AsyncSQLAlchemyStorage` for the kernel app beat platform-owned state snapshots (SPEC-017 R-3)? | revisit if the native entrypoint is ever deployed |
| HITL confirmation bridging | Delivered 2026-08-21 as `SPEC-020-hitl-confirmation-bridging` (kernel ASK → portal approve/deny, `chat:confirm` action, `confirmation_decided` audit). MUST still precede any write/mutating tool. | `docs/specs/SPEC-020-hitl-confirmation-bridging/` |
| ASK → DENY tightening | Resolved 2026-08-21 during SPEC-020 live-check hardening: `GatewayPermissionMiddleware` now answers every non-allow-listed tool with an explicit ASK (parked as a confirmation card) instead of delegating to the built-in engine, whose read-only fast path silently auto-allowed read-only tools; "silently never runs" no longer describes any path. | superseded by SPEC-020 hardening |

Promotion rule: a spike lands its findings as a short memo (workspace docs);
only then does the item get a SPEC number. SPEC-018 (kernel middleware
alignment) was delivered after SPEC-017 and re-confirmed this backlog in its
utilization memo (`docs/workspace/agentscope-utilization-audit.md`).
SPEC-020 (HITL confirmation bridging) was promoted from this backlog on
2026-08-21 after its spike memo landed.

## Validation Model Per Release

Every release should have four validation layers:

- `service validation`
- `workflow validation`
- `control validation`
- `user acceptance validation`

### Service Validation

Checks:

- service health
- API contract behavior
- event streaming
- connector integration

### Workflow Validation

Checks:

- end-to-end operator scenarios
- evidence visibility
- UI usability for the intended release goal

### Control Validation

Checks:

- `SSO`
- identity propagation
- policy decision behavior
- approval and audit integrity

### User Acceptance Validation

Checks:

- operations team can use the release without engineering guidance
- release saves time or improves confidence
- operators trust the outputs enough to adopt the workflow

## Suggested Iteration Rhythm

Use short internal iterations within each release, but treat the release itself as the validation boundary.

Recommended rhythm:

- `design and integration preparation`
- `core implementation`
- `end-to-end workflow completion`
- `operations validation`
- `hardening and release decision`

This keeps releases self-contained while still allowing normal engineering iteration inside them.

## Recommended Release Readiness Checklist

Every release should answer `yes` to these questions before moving on:

- does the release deliver one clear operator-visible capability?
- are the integration points working end to end?
- can operations teams validate the release with a small set of concrete scenarios?
- are logs, traces, and audit records sufficient to investigate problems?
- does the release keep faith with the platform design principles?

## Design Principles Carried Through Delivery

These principles should remain visible in every release:

- `bounded autonomy`
- `diagnose before act`
- `identity before privilege`
- `read before write`
- `explicit approvals for risk`
- `Git-managed team knowledge`
- `API-first and gateway-friendly integration`

## Final Recommendation

Deliver the platform as a sequence of self-contained, vertically integrated releases where each release gives operations teams something specific to try, verify, and trust.

The recommended release progression is:

- `R0` foundation
- `R1` read-only operational value
- `R2` grounded guidance
- `R3` incident triage
- `R4` approval-gated bounded action
- `R5` hardening and external consumption

This roadmap provides the clearest path to building enterprise trust while steadily increasing platform capability.
