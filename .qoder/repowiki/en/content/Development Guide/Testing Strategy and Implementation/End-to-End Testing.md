# End-to-End Testing

<cite>
**Referenced Files in This Document**
- [Makefile](file://Makefile)
- [ansible-mcp-check.sh](file://shared/platform-ops/e2e/ansible-mcp-check.sh)
- [sync-ansible-credentials.sh](file://shared/platform-ops/gitops/sync-ansible-credentials.sh)
- [browser-check-demo.sh](file://shared/platform-ops/e2e/browser-check-demo.sh)
- [documents-demo.sh](file://shared/platform-ops/e2e/documents-demo.sh)
- [incident-demo.sh](file://shared/platform-ops/e2e/incident-demo.sh)
- [mutating-demo.sh](file://shared/platform-ops/e2e/mutating-demo.sh)
- [skills-demo.sh](file://shared/platform-ops/e2e/skills-demo.sh)
- [App.studio.test.tsx](file://products/operator-portal/web-ui/app/src/__tests__/App.studio.test.tsx)
- [sessions.test.ts](file://products/operator-portal/web-ui/app/src/api/__tests__/sessions.test.ts)
- [ConfirmationCard.test.tsx](file://products/operator-portal/web-ui/app/src/chat/__tests__/ConfirmationCard.test.tsx)
- [config.py](file://products/tool-gateway/src/tool-gateway/core/config.py)
- [browser_sessions.py](file://products/tool-gateway/src/tool-gateway/tools/browser_sessions.py)
- [test_browser_connector.py](file://products/tool-gateway/tests/test_browser_connector.py)
</cite>

## Update Summary
**Changes Made**
- Added comprehensive coverage of STRICT_LIVE operator knob for controlled live testing
- Enhanced bearer-redaction validation documentation with improved security guarantees
- Expanded fail-closed error codes documentation covering MCP transport and credential failures
- Added proper signal trapping for temporary credential cleanup in credential provisioning
- Updated Ansible MCP integration testing with enhanced security and reliability measures

## Table of Contents
1. Introduction
2. Project Structure
3. Core Components
4. Architecture Overview
5. Detailed Component Analysis
6. Dependency Analysis
7. Performance Considerations
8. Troubleshooting Guide
9. Conclusion

## Introduction
This document explains the end-to-end testing strategy for the platform, covering full workflow validation across browser automation, document workflows, incident triage, mutating operations, skills management, and Ansible MCP integration. It also documents the React component test suite used to validate portal behavior, including navigation, workspace scoping, approval flows, and session APIs. The framework includes comprehensive security controls with STRICT_LIVE operator knobs, enhanced bearer-redaction validation, expanded fail-closed error codes, and proper signal trapping for temporary credential cleanup. Guidance is provided for environment setup (Kubernetes cluster preparation, service deployment, and test data seeding), authenticated user flows, file uploads, real-time updates, error scenarios, reporting, debugging failed tests, and maintaining reliable suites. Where applicable, performance benchmarking and load testing approaches are outlined to validate scalability under realistic usage patterns.

## Project Structure
The repository provides:
- Shell-based E2E demo scripts under shared/platform-ops/e2e that exercise live services via HTTP and kubectl against a deployed dev cluster, including Ansible MCP integration testing with STRICT_LIVE operator control.
- A React unit/integration test suite under products/operator-portal/web-ui/app/src/__tests__ and related subdirectories that validates UI wiring, state handling, and API client behavior using Vitest and Testing Library.
- A root Makefile that orchestrates builds, deploys, and runs the E2E demos as a single gate.
- Credential provisioning utilities with proper signal trapping for secure temporary file cleanup.

```mermaid
graph TB
DevCluster["Dev Kubernetes Cluster"]
Gateway["Platform Gateway"]
ToolGW["Tool Gateway"]
Identity["Identity Broker"]
Audit["Audit Service"]
SkillsHub["Skills Hub"]
IncidentSvc["Incident Service"]
WebUI["Operator Portal Web UI"]
AnsibleMCP["Ansible MCP Integration"]
WebUI --> Gateway
Gateway --> ToolGW
Gateway --> IncidentSvc
Gateway --> SkillsHub
Gateway --> Audit
ToolGW --> Identity
ToolGW --> Audit
ToolGW --> AnsibleMCP
IncidentSvc --> Audit
```

**Diagram sources**
- [Makefile:171-183](file://Makefile#L171-L183)
- [ansible-mcp-check.sh:1-395](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L1-L395)
- [browser-check-demo.sh:70-133](file://shared/platform-ops/e2e/browser-check-demo.sh#L70-L133)
- [documents-demo.sh:70-124](file://shared/platform-ops/e2e/documents-demo.sh#L70-L124)
- [incident-demo.sh:43-132](file://shared/platform-ops/e2e/incident-demo.sh#L43-L132)
- [mutating-demo.sh:80-152](file://shared/platform-ops/e2e/mutating-demo.sh#L80-L152)
- [skills-demo.sh:40-83](file://shared/platform-ops/e2e/skills-demo.sh#L40-L83)

**Section sources**
- [Makefile:14-34](file://Makefile#L14-L34)
- [Makefile:178-204](file://Makefile#L178-L204)

## Core Components
- E2E demo scripts:
  - Browser web-check smoke test validates tool discovery, origin allowlisting, CDP connectivity, and an optional chat leg with HITL approval.
  - Documents demo validates creation, publish, read-scoping, anti-enumeration, and audit trail for shift summaries.
  - Incident demo validates webhook intake, deduplication, resolution, visibility, operator triage, and audit dispatch.
  - Mutating tools demo validates deny-by-default posture, policy gating, RBAC checks, and an optional HITL flow with signed execution receipts.
  - Skills demo validates source sync status, deterministic search ranking, and agent invocation of skills.search during chat.
  - **NEW**: Ansible MCP integration test validates read-tier tool registration, fail-closed error handling, bearer token redaction, and controlled live testing via STRICT_LIVE operator knob.
- React test suite:
  - App navigation and workspace wiring tests ensure Studio gating, mode-scoped workspaces, and view routing correctness.
  - Session API client tests assert request shapes, error propagation, and session_type scoping.
  - Confirmation card tests assert tier badges, decision surfaces, receipt rendering, redaction, and flow replay behavior.

**Section sources**
- [browser-check-demo.sh:1-59](file://shared/platform-ops/e2e/browser-check-demo.sh#L1-L59)
- [documents-demo.sh:1-38](file://shared/platform-ops/e2e/documents-demo.sh#L1-L38)
- [incident-demo.sh:1-29](file://shared/platform-ops/e2e/incident-demo.sh#L1-L29)
- [mutating-demo.sh:1-63](file://shared/platform-ops/e2e/mutating-demo.sh#L1-L63)
- [skills-demo.sh:1-26](file://shared/platform-ops/e2e/skills-demo.sh#L1-L26)
- [ansible-mcp-check.sh:1-395](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L1-L395)
- [App.studio.test.tsx:1-16](file://products/operator-portal/web-ui/app/src/__tests__/App.studio.test.tsx#L1-L16)
- [sessions.test.ts:1-13](file://products/operator-portal/web-ui/app/src/api/__tests__/sessions.test.ts#L1-L13)
- [ConfirmationCard.test.tsx:1-12](file://products/operator-portal/web-ui/app/src/chat/__tests__/ConfirmationCard.test.tsx#L1-L12)

## Architecture Overview
The E2E scripts drive a realistic user journey by:
- Obtaining tokens from the identity broker and delegating them to tool-gateway where required.
- Interacting with platform-gateway endpoints for sessions, chat streaming, approvals, documents, incidents, and audits.
- Executing cluster-side calls via kubectl exec to reach tool-gateway or service pods directly for control-plane assertions.
- Validating sidecar connectivity (CDP) and feature flags through runtime configuration.
- **NEW**: Managing Ansible MCP integration with controlled live testing and enhanced security controls.

```mermaid
sequenceDiagram
participant Test as "E2E Script"
participant Id as "Identity Broker"
participant GW as "Platform Gateway"
participant TG as "Tool Gateway"
participant AM as "Ansible MCP"
participant Svc as "Service Pod"
participant Aud as "Audit Service"
Test->>Id : Obtain platform token
Id-->>Test : access_token
Test->>GW : Create session / chat stream
GW->>TG : Delegate token / invoke tools
TG->>AM : Ansible MCP integration (if enabled)
TG->>Svc : Execute tool (read/write)
TG-->>GW : Tool result / confirmation_request
GW-->>Test : SSE frames (tool_call/tool_result/confirmation)
Test->>GW : Approve via confirm (if needed)
GW->>Aud : Emit events (confirmation_decided, tool_invoked)
Aud-->>Test : Query durable trail
```

**Diagram sources**
- [ansible-mcp-check.sh:96-133](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L96-L133)
- [browser-check-demo.sh:96-133](file://shared/platform-ops/e2e/browser-check-demo.sh#L96-L133)
- [mutating-demo.sh:111-152](file://shared/platform-ops/e2e/mutating-demo.sh#L111-L152)
- [incident-demo.sh:141-168](file://shared/platform-ops/e2e/incident-demo.sh#L141-L168)
- [skills-demo.sh:91-124](file://shared/platform-ops/e2e/skills-demo.sh#L91-L124)

## Detailed Component Analysis

### E2E Framework and Environment Setup
- Prerequisites:
  - A running Kubernetes cluster with the dev-k8s overlay deployed.
  - Port forwards for identity-service and platform-gateway when running chat legs.
  - Runtime secrets and config maps provisioned (browser credentials, webhook tokens, query clients).
  - **NEW**: Ansible MCP credentials provisioned via sync-ansible-credentials.sh with proper signal trapping.
- Build and deploy:
  - Use the root Makefile targets to build images, render overlays, and deploy the platform.
  - Run samples separately so base overlays remain unmodified.
- Running E2E:
  - The e2e target executes the demo scripts sequentially and reports pass/fail.
  - **NEW**: Includes ansible-mcp-check.sh in the standard E2E suite with controlled live testing.

```mermaid
flowchart TD
Start(["Start"]) --> Build["Build images"]
Build --> Deploy["Deploy dev-k8s overlay"]
Deploy --> Samples["Install sample skills (optional)"]
Samples --> PortFwd["Port-forward services"]
PortFwd --> RunE2E["Run make e2e"]
RunE2E --> Scripts{"Scripts"}
Scripts --> |Skills| SkillsDemo["skills-demo.sh"]
Scripts --> |Incidents| IncDemo["incident-demo.sh"]
Scripts --> |Mutating| MutDemo["mutating-demo.sh"]
Scripts --> |Browser| BrDemo["browser-check-demo.sh"]
Scripts --> |Docs| DocDemo["documents-demo.sh"]
Scripts --> |Ansible MCP| AnsDemo["ansible-mcp-check.sh"]
SkillsDemo --> Report["Report results"]
IncDemo --> Report
MutDemo --> Report
BrDemo --> Report
DocDemo --> Report
AnsDemo --> Report
```

**Diagram sources**
- [Makefile:96-124](file://Makefile#L96-L124)
- [Makefile:181-204](file://Makefile#L181-L204)
- [Makefile:262-276](file://Makefile#L262-L276)

**Section sources**
- [Makefile:178-204](file://Makefile#L178-L204)
- [Makefile:262-276](file://Makefile#L262-L276)
- [browser-check-demo.sh:43-58](file://shared/platform-ops/e2e/browser-check-demo.sh#L43-L58)
- [documents-demo.sh:26-38](file://shared/platform-ops/e2e/documents-demo.sh#L26-L38)
- [incident-demo.sh:16-28](file://shared/platform-ops/e2e/incident-demo.sh#L16-L28)
- [mutating-demo.sh:48-62](file://shared/platform-ops/e2e/mutating-demo.sh#L48-L62)
- [skills-demo.sh:13-25](file://shared/platform-ops/e2e/skills-demo.sh#L13-L25)

### STRICT_LIVE Operator Knob for Controlled Live Testing
- **NEW**: The STRICT_LIVE operator knob provides controlled activation of live external calls in E2E testing.
- Default behavior (STRICT_LIVE=false): CI passes without live external calls, proving registration, fail-closed behavior, and redaction only.
- Operator mode (STRICT_LIVE=true): Turns gated live legs into hard failures when mock targets are not reachable/credentialed.
- Used primarily in Ansible MCP integration testing to distinguish between development and production validation modes.

```mermaid
flowchart TD
A["E2E Test Execution"] --> B{"STRICT_LIVE?"}
B --> |false| C["CI Mode: Skip live legs"]
B --> |true| D["Operator Mode: Fail if live unavailable"]
C --> E["Prove registration + fail-closed + redaction"]
D --> F["Validate live functionality"]
E --> G["Green exit if all offline checks pass"]
F --> H["Fail if mock target unreachable"]
```

**Diagram sources**
- [ansible-mcp-check.sh:55-63](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L55-L63)
- [ansible-mcp-check.sh:219-222](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L219-L222)
- [ansible-mcp-check.sh:284-285](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L284-L285)

**Section sources**
- [ansible-mcp-check.sh:55-63](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L55-L63)
- [ansible-mcp-check.sh:219-222](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L219-L222)
- [ansible-mcp-check.sh:284-285](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L284-L285)

### Enhanced Bearer-Redaction Validation
- **NEW**: Comprehensive bearer token redaction validation ensures sensitive credentials never leak into tool results.
- The Ansible MCP check validates that mock bearer tokens (read from ansible-mock-credentials secret) never appear in any tool-result body.
- Credentials ride in httpx headers only, never in response bodies.
- Enhanced validation catches both direct token leakage and indirect exposure through structured data fields.

```mermaid
sequenceDiagram
participant Test as "E2E Test"
participant Secret as "Secret Store"
participant TG as "Tool Gateway"
participant Mock as "Ansible Mock"
Test->>Secret : Read bearer token
Secret-->>Test : Encoded bearer
Test->>TG : Invoke tool with bearer header
TG->>Mock : HTTP request with bearer header
Mock-->>TG : Tool result (no bearer)
TG-->>Test : Tool result (redacted)
Test->>Test : Assert no bearer in response
```

**Diagram sources**
- [ansible-mcp-check.sh:343-381](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L343-L381)
- [sync-ansible-credentials.sh:15-30](file://shared/platform-ops/gitops/sync-ansible-credentials.sh#L15-L30)

**Section sources**
- [ansible-mcp-check.sh:343-381](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L343-L381)
- [sync-ansible-credentials.sh:15-30](file://shared/platform-ops/gitops/sync-ansible-credentials.sh#L15-L30)

### Expanded Fail-Closed Error Codes
- **NEW**: Comprehensive fail-closed error handling for MCP connector failures without server responses.
- Accepted fail-closed codes: MCP_TRANSPORT_ERROR, MCP_SDK_UNAVAILABLE, CREDENTIAL_SET_NOT_FOUND, CREDENTIAL_SCHEME_UNSUPPORTED.
- Any other error indicates unexpected failure that must not be waved through as "unreachable".
- Ensures clean structured error handling rather than hangs or fabricated successes.

```mermaid
flowchart TD
A["MCP Connection Attempt"] --> B{"Connection Status"}
B --> |Success| C["Proceed with live reads"]
B --> |Failure| D{"Error Code Check"}
D --> |Fail-closed code| E["Skip live leg with note"]
D --> |Unexpected code| F["Fail test immediately"]
E --> G["Continue with offline validations"]
F --> H["Report specific error details"]
```

**Diagram sources**
- [ansible-mcp-check.sh:78-82](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L78-L82)
- [ansible-mcp-check.sh:279-282](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L279-L282)

**Section sources**
- [ansible-mcp-check.sh:78-82](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L78-L82)
- [ansible-mcp-check.sh:279-282](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L279-L282)

### Proper Signal Trapping for Temporary Credential Cleanup
- **NEW**: Robust signal trapping ensures temporary credential files are cleaned up on success, failure, and signals.
- Uses trap cleanup EXIT INT TERM to handle all termination scenarios.
- Prevents sensitive bearer tokens from lingering on disk after script completion.
- Implements idempotent cleanup that can be called multiple times safely.

```mermaid
flowchart TD
A["Script Start"] --> B["Generate Token File"]
B --> C["Register Cleanup Trap"]
C --> D{"Script Execution"}
D --> |Success| E["Cleanup temp files"]
D --> |Failure| F["Cleanup temp files"]
D --> |Signal| G["Cleanup temp files"]
E --> H["Exit cleanly"]
F --> H
G --> H
```

**Diagram sources**
- [sync-ansible-credentials.sh:69-91](file://shared/platform-ops/gitops/sync-ansible-credentials.sh#L69-L91)
- [sync-ansible-credentials.sh:93-108](file://shared/platform-ops/gitops/sync-ansible-credentials.sh#L93-L108)

**Section sources**
- [sync-ansible-credentials.sh:69-91](file://shared/platform-ops/gitops/sync-ansible-credentials.sh#L69-L91)
- [sync-ansible-credentials.sh:93-108](file://shared/platform-ops/gitops/sync-ansible-credentials.sh#L93-L108)

### Browser Automation Testing (Web Tools and CDP)
- Discovery and risk tiers:
  - When disabled, no web.* tools appear; invoke fails closed with TOOL_NOT_FOUND.
  - When enabled, baseline tools are registered with correct risk levels; off-allowlist origins are denied server-side.
- CDP connectivity:
  - The gateway pod must reach the Chromium sidecar's CDP endpoint to navigate, snapshot, screenshot, and interact.
- Optional chat leg:
  - Creates a session, streams a message that triggers web.* tools, parks a confirmation_request for write-tier actions, approves via confirm, and asserts the resumed turn completes with operational outcomes and durable receipts.

```mermaid
sequenceDiagram
participant Script as "browser-check-demo.sh"
participant GW as "Platform Gateway"
participant TG as "Tool Gateway"
participant CDP as "Chromium Sidecar"
Script->>GW : POST /api/v1/sessions
GW-->>Script : session_id
Script->>GW : POST /api/v1/chat/stream?message=...
GW->>TG : Invoke web.navigate/web.snapshot
TG->>CDP : Connect over CDP
CDP-->>TG : Page title / elements
TG-->>GW : Tool result
GW-->>Script : SSE frames (tool_call/tool_result)
Note over Script,GW : If write-tier action -> confirmation_request
Script->>GW : POST /api/v1/chat/confirm {approve}
GW-->>Script : confirmation_result + resumed stream
```

**Diagram sources**
- [browser-check-demo.sh:135-227](file://shared/platform-ops/e2e/browser-check-demo.sh#L135-L227)
- [browser-check-demo.sh:229-343](file://shared/platform-ops/e2e/browser-check-demo.sh#L229-L343)

**Section sources**
- [browser-check-demo.sh:10-41](file://shared/platform-ops/e2e/browser-check-demo.sh#L10-L41)
- [browser-check-demo.sh:140-227](file://shared/platform-ops/e2e/browser-check-demo.sh#L140-L227)
- [browser-check-demo.sh:229-343](file://shared/platform-ops/e2e/browser-check-demo.sh#L229-L343)
- [config.py:17-24](file://products/tool-gateway/src/tool-gateway/core/config.py#L17-L24)
- [browser_sessions.py:285-307](file://products/tool-gateway/src/tool-gateway/tools/browser_sessions.py#L285-L307)
- [test_browser_connector.py:532-555](file://products/tool-gateway/tests/test_browser_connector.py#L532-L555)

### Operations Document Repository Workflow
- Roles and permissions:
  - Observer cannot create documents; owner creates draft citing a session; reader gets 404 until published.
- Draft lifecycle:
  - Draft includes deterministic handover section and counts-only summary; publish flips state and is one-way (re-publish returns conflict).
- Visibility and audit:
  - Published listing is envelope-only with summary; full content fetches are audited; cross-owner reads are recorded.
- Session rename:
  - Owner can rename; foreign callers get 404; auditors get 403 on update attempts.

```mermaid
flowchart TD
A["Create session"] --> B["Create shift-summary draft"]
B --> C{"Reader fetch?"}
C --> |Draft| D["404 anti-enumeration"]
C --> |Published| E["200 with owner attribution"]
B --> F["Publish (one-way)"]
F --> G["Listing shows envelope + summary"]
F --> H["Audit trail: created/published/read"]
```

**Diagram sources**
- [documents-demo.sh:99-178](file://shared/platform-ops/e2e/documents-demo.sh#L99-L178)
- [documents-demo.sh:180-234](file://shared/platform-ops/e2e/documents-demo.sh#L180-L234)

**Section sources**
- [documents-demo.sh:1-38](file://shared/platform-ops/e2e/documents-demo.sh#L1-L38)
- [documents-demo.sh:99-178](file://shared/platform-ops/e2e/documents-demo.sh#L99-L178)
- [documents-demo.sh:180-234](file://shared/platform-ops/e2e/documents-demo.sh#L180-L234)

### Incident Triage and Collaboration
- Webhook intake:
  - Rejects missing/bad bearer tokens; accepts valid payloads to create incidents; duplicates by groupKey; resolves on resolved status.
- Visibility:
  - Platform caller credential can list incidents via the same query surface the portal uses.
- Operator triage:
  - Through platform-gateway, triage produces a validated report and dispatches to audit connector; durable trail carries incident_triaged.

```mermaid
sequenceDiagram
participant AM as "Alertmanager (simulated)"
participant IS as "Incident Service"
participant GW as "Platform Gateway"
participant Aud as "Audit Service"
AM->>IS : POST /webhooks/alertmanager (firing)
IS-->>AM : 201 created
AM->>IS : POST /webhooks/alertmanager (duplicate)
IS-->>AM : 200 updated (same id)
AM->>IS : POST /webhooks/alertmanager (resolved)
IS-->>AM : 200 resolved
GW->>IS : Triage via gateway (operator)
IS-->>GW : Report + connector dispatch
GW->>Aud : Emit incident_triaged
```

**Diagram sources**
- [incident-demo.sh:63-132](file://shared/platform-ops/e2e/incident-demo.sh#L63-L132)
- [incident-demo.sh:141-195](file://shared/platform-ops/e2e/incident-demo.sh#L141-L195)

**Section sources**
- [incident-demo.sh:1-29](file://shared/platform-ops/e2e/incident-demo.sh#L1-L29)
- [incident-demo.sh:63-132](file://shared/platform-ops/e2e/incident-demo.sh#L63-L132)
- [incident-demo.sh:141-195](file://shared/platform-ops/e2e/incident-demo.sh#L141-L195)

### Mutating Operations and HITL Approval
- Deny-by-default posture:
  - Without enabling mutating tools, k8s.delete_pod is absent from discovery and invokes fail closed; service account lacks delete RBAC.
- Opt-in posture:
  - Discovery exposes write-tier tool; observer denied by policy; operator admitted but connector-level errors expected for nonexistent resources.
- HITL leg (opt-in):
  - Chat stream parks confirmation_request with risk_level=write; self-approval rejected; designated approver approves; durable trail records confirmation_decided and tool_invoked; session detail shows approved card with signed receipt; inbox lists decided item; second approve returns already_resolved.

```mermaid
sequenceDiagram
participant Script as "mutating-demo.sh"
participant GW as "Platform Gateway"
participant TG as "Tool Gateway"
participant K8S as "Kubernetes API"
participant Aud as "Audit Service"
Script->>GW : Chat stream requesting k8s.delete_pod
GW->>TG : Policy check (tools : mutate)
TG->>K8S : Attempt delete (nonexistent)
K8S-->>TG : Structured error
TG-->>GW : confirmation_request (risk_level=write)
Script->>GW : Confirm (designated approver)
GW->>Aud : Emit confirmation_decided
GW->>TG : Resume execution
TG->>K8S : Delete pod (managed by controller)
K8S-->>TG : Result
TG-->>GW : Execution receipt (signed)
GW-->>Script : Stream completion + durable surfaces
```

**Diagram sources**
- [mutating-demo.sh:154-244](file://shared/platform-ops/e2e/mutating-demo.sh#L154-L244)
- [mutating-demo.sh:246-504](file://shared/platform-ops/e2e/mutating-demo.sh#L246-L504)

**Section sources**
- [mutating-demo.sh:1-63](file://shared/platform-ops/e2e/mutating-demo.sh#L1-L63)
- [mutating-demo.sh:154-244](file://shared/platform-ops/e2e/mutating-demo.sh#L154-L244)
- [mutating-demo.sh:246-504](file://shared/platform-ops/e2e/mutating-demo.sh#L246-L504)

### Skills Management and Search Ranking
- Source synchronization:
  - Status endpoint verifies both sample sources synced without errors.
- Deterministic ranking:
  - Search for alert name returns the matching runbook first; top match is validated.
- Agent invocation:
  - Chat stream includes skills.search tool_call and corresponding tool_result frame pair.

```mermaid
sequenceDiagram
participant Script as "skills-demo.sh"
participant Hub as "Skills Hub"
participant GW as "Platform Gateway"
Script->>Hub : GET /api/v1/skills/status
Hub-->>Script : Sources synced, last_error null
Script->>Hub : GET /api/v1/skills/search?q=...
Hub-->>Script : Matches (top = expected skill)
Script->>GW : POST /api/v1/chat/stream?message=...
GW-->>Script : SSE frames with skills.search tool_call + tool_result
```

**Diagram sources**
- [skills-demo.sh:40-83](file://shared/platform-ops/e2e/skills-demo.sh#L40-L83)
- [skills-demo.sh:91-124](file://shared/platform-ops/e2e/skills-demo.sh#L91-L124)

**Section sources**
- [skills-demo.sh:1-26](file://shared/platform-ops/e2e/skills-demo.sh#L1-L26)
- [skills-demo.sh:40-83](file://shared/platform-ops/e2e/skills-demo.sh#L40-L83)
- [skills-demo.sh:91-124](file://shared/platform-ops/e2e/skills-demo.sh#L91-L124)

### Ansible MCP Integration Testing
- **NEW**: Comprehensive Ansible MCP integration testing validates read-tier tool registration, fail-closed error handling, and bearer token redaction.
- Control plane checks verify unauthenticated callers are rejected (401).
- Tool discovery validates exactly six read-tier ansible.* tools are registered with risk_level=read.
- Fail-closed negatives tested without server contact: non-admitted mutating verbs return TOOL_NOT_FOUND, missing parameters return INVALID_PARAMETERS.
- Live reads are gated on mock target reachability via health probe, with proper skip logic when unavailable.
- Redaction validation ensures mock bearer tokens never appear in tool result bodies.

```mermaid
sequenceDiagram
participant Script as "ansible-mcp-check.sh"
participant GW as "Platform Gateway"
participant TG as "Tool Gateway"
participant AM as "Ansible MCP Mock"
Script->>GW : Unauthenticated discovery/invoke
GW-->>Script : 401 Unauthorized
Script->>GW : Authenticated discovery
GW-->>Script : Six ansible.* tools (read tier)
Script->>TG : Invoke ansible.get_environment_health
TG->>AM : Health probe
AM-->>TG : healthy/unhealthy
TG-->>Script : Tool result (bearer redacted)
```

**Diagram sources**
- [ansible-mcp-check.sh:138-147](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L138-L147)
- [ansible-mcp-check.sh:232-250](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L232-L250)
- [ansible-mcp-check.sh:269-292](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L269-L292)
- [ansible-mcp-check.sh:343-381](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L343-L381)

**Section sources**
- [ansible-mcp-check.sh:1-395](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L1-L395)

### React Component Testing Approach
- Navigation and workspace wiring:
  - Tests assert Studio entry gating, operation vs development workspace scoping, and view routing correctness.
- Inbox refresh wiring:
  - Decision callback refreshes both workspaces to keep panels current after approvals.
- View parameters:
  - Documents, Incidents, Settings wired to operation workspace; ChatView parameterized by mode.

```mermaid
classDiagram
class App {
+render()
+workspaces
+viewRouting()
}
class AuthContext {
+useAuth()
}
class SessionWorkspace {
+refresh()
+createAndOpen()
+remove()
+rename()
}
App --> AuthContext : "reads roles/session"
App --> SessionWorkspace : "operation & development"
```

**Diagram sources**
- [App.studio.test.tsx:17-32](file://products/operator-portal/web-ui/app/src/__tests__/App.studio.test.tsx#L17-L32)
- [App.studio.test.tsx:104-159](file://products/operator-portal/web-ui/app/src/__tests__/App.studio.test.tsx#L104-L159)
- [App.studio.test.tsx:166-335](file://products/operator-portal/web-ui/app/src/__tests__/App.studio.test.tsx#L166-L335)

**Section sources**
- [App.studio.test.tsx:1-16](file://products/operator-portal/web-ui/app/src/__tests__/App.studio.test.tsx#L1-L16)
- [App.studio.test.tsx:166-335](file://products/operator-portal/web-ui/app/src/__tests__/App.studio.test.tsx#L166-L335)

### API Client and Real-Time Updates
- Session API client:
  - Asserts request paths, body shapes (including session_type and skill_target), and error propagation with structured details.
- Real-time updates:
  - E2E scripts consume SSE streams and assert frame types (tool_call, tool_result, confirmation_request, confirmation_result).
  - React tests mock hooks and verify UI reacts to decisions and workspace changes.

```mermaid
sequenceDiagram
participant UI as "Portal UI"
participant API as "API Client"
participant GW as "Platform Gateway"
UI->>API : createSession(session_type?)
API->>GW : POST /api/v1/sessions
GW-->>API : {session_id, session_type}
API-->>UI : Result or ApiError(detail)
UI->>GW : Subscribe to chat stream
GW-->>UI : SSE frames (tool_call/tool_result/confirmation)
```

**Diagram sources**
- [sessions.test.ts:46-112](file://products/operator-portal/web-ui/app/src/api/__tests__/sessions.test.ts#L46-L112)
- [sessions.test.ts:114-183](file://products/operator-portal/web-ui/app/src/api/__tests__/sessions.test.ts#L114-L183)
- [sessions.test.ts:185-259](file://products/operator-portal/web-ui/app/src/api/__tests__/sessions.test.ts#L185-L259)

**Section sources**
- [sessions.test.ts:1-13](file://products/operator-portal/web-ui/app/src/api/__tests__/sessions.test.ts#L1-L13)
- [sessions.test.ts:46-112](file://products/operator-portal/web-ui/app/src/api/__tests__/sessions.test.ts#L46-L112)
- [sessions.test.ts:114-183](file://products/operator-portal/web-ui/app/src/api/__tests__/sessions.test.ts#L114-L183)
- [sessions.test.ts:185-259](file://products/operator-portal/web-ui/app/src/api/__tests__/sessions.test.ts#L185-L259)

### Confirmation Cards and Signed Receipts
- Tier badges and decision surfaces:
  - Tier_1 (operator confirmation) vs tier_2 (approver required); non-deciders see read-only cards.
- Execution receipts:
  - Decided cards show status, digest-match state, and rejection reasons when present.
- Flow replay:
  - Graduated flows render as a single decision surface with per-call audit context.

```mermaid
flowchart TD
A["Pending call"] --> B{"Risk level?"}
B --> |read| C["Tier 1: operator confirmation"]
B --> |write| D["Tier 2: approver required"]
C --> E["Approve/Deny if role permits"]
D --> F["Approve/Deny only for designated approver"]
E --> G["Execution receipt rendered"]
F --> G
```

**Diagram sources**
- [ConfirmationCard.test.tsx:55-103](file://products/operator-portal/web-ui/app/src/chat/__tests__/ConfirmationCard.test.tsx#L55-L103)
- [ConfirmationCard.test.tsx:105-200](file://products/operator-portal/web-ui/app/src/chat/__tests__/ConfirmationCard.test.tsx#L105-L200)
- [ConfirmationCard.test.tsx:533-621](file://products/operator-portal/web-ui/app/src/chat/__tests__/ConfirmationCard.test.tsx#L533-L621)

**Section sources**
- [ConfirmationCard.test.tsx:1-12](file://products/operator-portal/web-ui/app/src/chat/__tests__/ConfirmationCard.test.tsx#L1-L12)
- [ConfirmationCard.test.tsx:55-103](file://products/operator-portal/web-ui/app/src/chat/__tests__/ConfirmationCard.test.tsx#L55-L103)
- [ConfirmationCard.test.tsx:105-200](file://products/operator-portal/web-ui/app/src/chat/__tests__/ConfirmationCard.test.tsx#L105-L200)
- [ConfirmationCard.test.tsx:533-621](file://products/operator-portal/web-ui/app/src/chat/__tests__/ConfirmationCard.test.tsx#L533-L621)

## Dependency Analysis
- E2E scripts depend on:
  - Identity broker for token issuance and delegation.
  - Platform gateway for sessions, chat streaming, approvals, documents, incidents, and audit queries.
  - Tool gateway for tool discovery and invocation; may connect to CDP sidecar for browser tools.
  - Services (skills-hub, incident-service) for domain-specific capabilities.
  - **NEW**: Ansible MCP integration for read-tier automation tooling.
- React tests depend on:
  - Mocked auth context and session workspace to isolate UI logic.
  - Stubbed fetch to assert API client behavior and error propagation.

```mermaid
graph LR
E2E["E2E Scripts"] --> ID["Identity Broker"]
E2E --> GW["Platform Gateway"]
E2E --> TG["Tool Gateway"]
E2E --> SVC["Domain Services"]
E2E --> AM["Ansible MCP"]
TG --> CDP["CDP Sidecar"]
GW --> AUD["Audit Service"]
ReactTests["React Tests"] --> Mocks["Mocks/Stubs"]
ReactTests --> API["API Client"]
```

**Diagram sources**
- [ansible-mcp-check.sh:96-133](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L96-L133)
- [browser-check-demo.sh:96-133](file://shared/platform-ops/e2e/browser-check-demo.sh#L96-L133)
- [mutating-demo.sh:111-152](file://shared/platform-ops/e2e/mutating-demo.sh#L111-L152)
- [incident-demo.sh:141-168](file://shared/platform-ops/e2e/incident-demo.sh#L141-L168)
- [skills-demo.sh:91-124](file://shared/platform-ops/e2e/skills-demo.sh#L91-L124)
- [App.studio.test.tsx:17-32](file://products/operator-portal/web-ui/app/src/__tests__/App.studio.test.tsx#L17-L32)
- [sessions.test.ts:20-44](file://products/operator-portal/web-ui/app/src/api/__tests__/sessions.test.ts#L20-L44)

**Section sources**
- [ansible-mcp-check.sh:96-133](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L96-L133)
- [browser-check-demo.sh:96-133](file://shared/platform-ops/e2e/browser-check-demo.sh#L96-L133)
- [mutating-demo.sh:111-152](file://shared/platform-ops/e2e/mutating-demo.sh#L111-L152)
- [incident-demo.sh:141-168](file://shared/platform-ops/e2e/incident-demo.sh#L141-L168)
- [skills-demo.sh:91-124](file://shared/platform-ops/e2e/skills-demo.sh#L91-L124)
- [App.studio.test.tsx:17-32](file://products/operator-portal/web-ui/app/src/__tests__/App.studio.test.tsx#L17-L32)
- [sessions.test.ts:20-44](file://products/operator-portal/web-ui/app/src/api/__tests__/sessions.test.ts#L20-L44)

## Performance Considerations
- E2E script timing:
  - Streams and long-running operations use timeouts; tune max-time values for stability under load.
- Browser automation:
  - CDP connection and page interactions can be latency-sensitive; ensure sidecar readiness and resource limits are appropriate.
- **NEW**: Ansible MCP integration:
  - Health probes and live reads should be monitored for latency; consider timeout adjustments for network-bound operations.
- Load testing approach:
  - Reproduce realistic usage by scripting concurrent sessions and tool invocations against the gateway while monitoring audit events and service metrics.
  - Validate throughput and error rates under sustained load; adjust timeouts and concurrency to reflect production patterns.
- Benchmarking:
  - Measure time-to-first-frame, confirmation round-trip, and tool execution latency across different roles and tool categories.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
- Common failures:
  - Unauthenticated requests return 401; ensure tokens are obtained and delegated correctly.
  - Feature flags:
    - Browser tools disabled: expect no web.* tools and TOOL_NOT_FOUND on invoke.
    - Mutating tools disabled: expect absence of k8s.delete_pod and TOOL_NOT_FOUND on invoke.
    - **NEW**: Ansible MCP disabled: expect no ansible.* tools and TOOL_NOT_FOUND on invoke.
  - Origin allowlist:
    - Off-allowlist navigation denied server-side; verify target URL is permitted.
  - HITL bridging:
    - If AGENT_HITL_CONFIRM_TIMEOUT is zero, chat legs requiring HITL cannot run.
  - **NEW**: STRICT_LIVE mode:
    - STRICT_LIVE=true requires mock target to be reachable; otherwise tests fail hard instead of skipping.
  - **NEW**: Credential provisioning:
    - Ensure sync-ansible-credentials.sh has completed successfully before running Ansible MCP tests.
- Debugging steps:
  - Inspect port forwards and service reachability.
  - Check runtime config and secrets for required entries.
  - Query audit events to trace confirmation_decided and tool_invoked events.
  - For browser tools, verify CDP endpoint accessibility from the gateway pod.
  - **NEW**: For Ansible MCP issues, verify ansible-mock-credentials secret exists and contains valid bearer-token.

**Section sources**
- [browser-check-demo.sh:70-94](file://shared/platform-ops/e2e/browser-check-demo.sh#L70-L94)
- [browser-check-demo.sh:135-167](file://shared/platform-ops/e2e/browser-check-demo.sh#L135-L167)
- [browser-check-demo.sh:193-227](file://shared/platform-ops/e2e/browser-check-demo.sh#L193-L227)
- [mutating-demo.sh:100-186](file://shared/platform-ops/e2e/mutating-demo.sh#L100-L186)
- [incident-demo.sh:63-78](file://shared/platform-ops/e2e/incident-demo.sh#L63-L78)
- [documents-demo.sh:99-105](file://shared/platform-ops/e2e/documents-demo.sh#L99-L105)
- [ansible-mcp-check.sh:219-222](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L219-L222)
- [ansible-mcp-check.sh:284-285](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L284-L285)

## Conclusion
The platform's E2E framework combines shell-driven scripts against a live Kubernetes cluster with targeted React tests to validate both system-wide workflows and UI behavior. The scripts enforce security postures (deny-by-default, origin allowlists, policy gates), validate real-time collaboration (HITL approvals, SSE streams), and ensure durability (audit trails, signed receipts). The React suite ensures consistent navigation, workspace scoping, and robust error handling in the portal. 

**Updated**: The comprehensive E2E testing infrastructure improvements include STRICT_LIVE operator knobs for controlled live testing, enhanced bearer-redaction validation ensuring credential safety, expanded fail-closed error codes for robust error handling, and proper signal trapping for secure temporary credential cleanup. These enhancements provide stronger security guarantees and more reliable testing across all platform components, including the new Ansible MCP integration. Together, these layers provide confidence in full-platform functionality, reliability, and safety under realistic usage patterns.

[No sources needed since this section summarizes without analyzing specific files]