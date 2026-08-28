# SPEC-042: Platform Dependency Hygiene Specification

<cite>
**Referenced Files in This Document**
- [spec.md](file://docs/specs/SPEC-042-dependency-hygiene/spec.md)
- [plan.md](file://docs/specs/SPEC-042-dependency-hygiene/plan.md)
- [tasks.md](file://docs/specs/SPEC-042-dependency-hygiene/tasks.md)
- [App.tsx](file://products/operator-portal/web-ui/app/src/App.tsx)
- [DocumentsView.tsx](file://products/operator-portal/web-ui/app/src/views/workspace/DocumentsView.tsx)
- [ChatView.tsx](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx)
- [AuditView.tsx](file://products/operator-portal/web-ui/app/src/views/audit/AuditView.tsx)
- [ApprovalsView.tsx](file://products/operator-portal/web-ui/app/src/views/control/ApprovalsView.tsx)
- [package.json](file://products/operator-portal/web-ui/app/package.json)
- [vite.config.ts](file://products/operator-portal/web-ui/app/vite.config.ts)
- [pyproject.toml](file://products/agent-platform/pyproject.toml)
- [pyproject.toml](file://products/identity-broker/pyproject.toml)
- [pyproject.toml](file://products/platform-gateway/pyproject.toml)
- [pyproject.toml](file://products/tool-gateway/pyproject.toml)
</cite>

## Update Summary
**Changes Made**
- Expanded scope from portal-only to comprehensive platform-wide dependency hygiene
- Added backend Python services dependency management (R-5)
- Included lockfile maintenance across all eight Python products
- Added cryptography cap adjudication process
- Enhanced verification requirements for agentscope kernel updates
- Updated impact assessment to include backend services

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
This document specifies the comprehensive platform dependency hygiene effort for SPEC-042. The scope has been expanded from portal-specific antd migrations to include both frontend and backend dependency management across the entire Luban AIOps platform. The work encompasses migrating deprecated antd v6 APIs in the operator portal, adding deprecation regression guards, performing managed refreshes of major toolchain dependencies including React 19, and re-locking all backend Python services to their latest stable versions within declared ranges.

The spec defines five requirements:
- R-1: Migrate deprecated antd v6 APIs (Drawer width → size; Alert message → title).
- R-2: Add a vitest guard that fails the suite when any antd deprecation warning appears.
- R-3: Managed refresh of portal adopt-set packages with consistent lockfiles and build gates.
- R-4: Adopt React 19 with behavior-preserving changes only.
- R-5: Backend stable-channel lockfile refresh across all eight Python products with cryptography cap adjudication.

Acceptance criteria emphasize zero antd deprecation warnings in test output, green type-checking and builds, unchanged visual/behavioral outcomes, and verified backend service stability after dependency updates.

**Section sources**
- [spec.md:15-62](file://docs/specs/SPEC-042-dependency-hygiene/spec.md#L15-L62)
- [spec.md:63-196](file://docs/specs/SPEC-042-dependency-hygiene/spec.md#L63-L196)

## Project Structure
SPEC-042 targets both the operator portal web application and all backend Python services across the platform. The relevant surfaces include:

**Frontend (Portal):**
- UI shell and navigation drawers: App.tsx
- Views using Alerts and Drawers: DocumentsView.tsx, ChatView.tsx, AuditView.tsx, ApprovalsView.tsx
- Build and test configuration: vite.config.ts
- Dependencies and Node engine constraints: package.json

**Backend (Python Services):**
- Eight Python products with individual pyproject.toml files
- Lockfile maintenance across agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, and tool-gateway
- Cryptography dependency adjudication across six products

```mermaid
graph TB
subgraph "Platform Architecture"
subgraph "Frontend Portal"
App["App.tsx"]
Views["Views & Components"]
Config["Build Config"]
end
subgraph "Backend Services"
AgentPlatform["Agent Platform"]
IdentityBroker["Identity Broker"]
PlatformGateway["Platform Gateway"]
ToolGateway["Tool Gateway"]
OtherServices["Other Services"]
end
end
App --> Views
Views --> Config
AgentPlatform --> OtherServices
IdentityBroker --> OtherServices
PlatformGateway --> OtherServices
ToolGateway --> OtherServices
```

**Diagram sources**
- [App.tsx:1-419](file://products/operator-portal/web-ui/app/src/App.tsx#L1-L419)
- [pyproject.toml:1-38](file://products/agent-platform/pyproject.toml#L1-L38)
- [pyproject.toml:1-33](file://products/identity-broker/pyproject.toml#L1-L33)
- [pyproject.toml:1-34](file://products/platform-gateway/pyproject.toml#L1-L34)
- [pyproject.toml:1-36](file://products/tool-gateway/pyproject.toml#L1-L36)

**Section sources**
- [plan.md:3-15](file://docs/specs/SPEC-042-dependency-hygiene/plan.md#L3-L15)
- [tasks.md:3-76](file://docs/specs/SPEC-042-dependency-hygiene/tasks.md#L3-L76)

## Core Components
The comprehensive dependency hygiene effort spans multiple layers of the platform:

**Frontend Components:**
- Drawer migration: Navigation drawers in App.tsx migrate from width props to size props to eliminate deprecation warnings while preserving pixel widths.
- Alert migration: Multiple views render Alert components migrating from message to title to match antd v6's non-deprecated API.
- Test guard: Vitest setup intercepts console output during runs and fails if any antd deprecation warning is detected.
- Dependency refresh: Adopted versions for antd, TypeScript, Vite, Vitest, jsdom, @types/node, and testing libraries applied consistently.
- React 19 adoption: react/react-dom and their types move to 19.x with peer compatibility already declared by framework dependencies.

**Backend Components:**
- Lockfile refresh: All eight Python products re-lock inside declared ranges to latest stable versions.
- Cryptography adjudication: Review JWT/signing call sites in six products declaring cryptography to determine cap adjustments.
- Agentscope kernel update: Upgrade from 2.0.6 to 2.0.7.post1 with full verification including live HITL/mutating path checks.
- Service stability: Ensure all product test suites remain green under frozen sync conditions.

**Section sources**
- [spec.md:67-196](file://docs/specs/SPEC-042-dependency-hygiene/spec.md#L67-L196)
- [plan.md:17-95](file://docs/specs/SPEC-042-dependency-hygiene/plan.md#L17-L95)
- [tasks.md:3-76](file://docs/specs/SPEC-042-dependency-hygiene/tasks.md#L3-L76)

## Architecture Overview
The platform architecture encompasses both frontend and backend systems with coordinated dependency management:

```mermaid
graph TB
subgraph "Frontend Layer"
Portal["Operator Portal Web UI"]
Antd["Antd 6.x"]
React["React 19.x"]
Vite["Vite 8.x"]
end
subgraph "Backend Layer"
AgentPlatform["Agent Platform"]
IdentityBroker["Identity Broker"]
PlatformGateway["Platform Gateway"]
ToolGateway["Tool Gateway"]
OtherServices["Other Python Services"]
end
subgraph "Shared Dependencies"
FastAPI["FastAPI"]
Pydantic["Pydantic"]
OpenTelemetry["OpenTelemetry"]
Cryptography["Cryptography"]
end
Portal --> Antd
Portal --> React
Portal --> Vite
AgentPlatform --> FastAPI
IdentityBroker --> Cryptography
PlatformGateway --> Cryptography
ToolGateway --> Cryptography
OtherServices --> OpenTelemetry
```

**Diagram sources**
- [package.json:15-33](file://products/operator-portal/web-ui/app/package.json#L15-L33)
- [pyproject.toml:6-21](file://products/agent-platform/pyproject.toml#L6-L21)
- [pyproject.toml:6-19](file://products/identity-broker/pyproject.toml#L6-L19)
- [pyproject.toml:6-20](file://products/platform-gateway/pyproject.toml#L6-L20)
- [pyproject.toml:6-22](file://products/tool-gateway/pyproject.toml#L6-L22)

## Detailed Component Analysis

### Frontend Deprecation Migration
The portal requires migration of deprecated antd v6 APIs across multiple components:

**Drawer Migration:**
- Two navigation drawers in App.tsx migrate from `width={230}` and `width={260}` to `size={230}` and `size={260}`
- Document drawer in DocumentsView.tsx migrates from `width={560}` to `size={560}`
- Layout preservation ensures no visual changes occur during migration

**Alert Migration:**
- Fifteen Alert usages migrate from `message` to `title` across nine view files
- Affected files include App.tsx, ChatView.tsx, DocumentsView.tsx, AuditView.tsx, ApprovalsView.tsx, SkillsView.tsx, ToolsView.tsx, PermissionsView.tsx, and IncidentsView.tsx
- Description props remain unchanged as they are not deprecated

```mermaid
flowchart TD
Start(["Component Render"]) --> CheckProps{"Check for deprecated props"}
CheckProps --> |Drawer width| MigrateWidth["Replace width with size"]
CheckProps --> |Alert message| MigrateMessage["Replace message with title"]
CheckProps --> |No issues| RenderNormal["Render normally"]
MigrateWidth --> VerifyLayout["Verify layout preserved"]
MigrateMessage --> VerifyContent["Verify content preserved"]
VerifyLayout --> End(["Component renders without warnings"])
VerifyContent --> End
RenderNormal --> End
```

**Diagram sources**
- [App.tsx:392-400](file://products/operator-portal/web-ui/app/src/App.tsx#L392-L400)
- [DocumentsView.tsx:1116-1120](file://products/operator-portal/web-ui/app/src/views/workspace/DocumentsView.tsx#L1116-L1120)
- [ChatView.tsx:512-514](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L512-L514)

**Section sources**
- [spec.md:67-86](file://docs/specs/SPEC-042-dependency-hygiene/spec.md#L67-L86)
- [plan.md:19-35](file://docs/specs/SPEC-042-dependency-hygiene/plan.md#L19-L35)
- [tasks.md:3-14](file://docs/specs/SPEC-042-dependency-hygiene/tasks.md#L3-L14)

### Deprecation Regression Guard Implementation
The vitest setup implements a comprehensive guard against future antd deprecations:

**Guard Mechanism:**
- Intercepts console.error and console.warn during test execution
- Scans output for patterns matching `[antd: …] … deprecated`
- Fails the suite at teardown with specific offending warning text
- Allows non-deprecation console output to pass through unchanged

**Verification Process:**
- Initial run confirms zero deprecation warnings
- Temporary reintroduction of deprecated prop proves guard functionality
- Reversion restores clean state with guard active

```mermaid
sequenceDiagram
participant Test as "Test Suite"
participant Guard as "Deprecation Guard"
participant Console as "Console Output"
Test->>Guard : Initialize interception
Console->>Guard : Emit warning/error
Guard->>Guard : Check for antd deprecation pattern
alt Deprecation detected
Guard->>Test : Fail suite with warning details
else No deprecation
Guard->>Console : Pass through output
Console->>Test : Continue execution
end
```

**Diagram sources**
- [vite.config.ts:34-37](file://products/operator-portal/web-ui/app/vite.config.ts#L34-L37)
- [plan.md:36-47](file://docs/specs/SPEC-042-dependency-hygiene/plan.md#L36-L47)

**Section sources**
- [spec.md:87-99](file://docs/specs/SPEC-042-dependency-hygiene/spec.md#L87-L99)
- [plan.md:36-47](file://docs/specs/SPEC-042-dependency-hygiene/plan.md#L36-L47)
- [tasks.md:15-22](file://docs/specs/SPEC-042-dependency-hygiene/tasks.md#L15-L22)

### Backend Lockfile Management
The backend component manages dependency updates across eight Python products:

**Lockfile Refresh Strategy:**
- Each product's uv.lock file regenerates to latest stable version within declared ranges
- Headline updates include agentscope 2.0.6 → 2.0.7.post1, fastapi → 0.141.1, uvicorn → 0.52.4
- No prerelease, beta, or release candidate versions adopted anywhere

**Cryptography Cap Adjudication:**
- Six products declare cryptography>=43.0,<45.0 requiring review
- JWT/signing call sites examined in identity-broker, audit-service, incident-service, platform-gateway, skills-hub, and tool-gateway
- Decision to raise caps to latest stable major or maintain existing bounds based on compatibility

**Service Verification:**
- Full agent-platform suite execution after re-lock
- make verify passes with updated dependencies
- Live check of chat, HITL confirmation, and approved-mutating paths via mutating-demo.sh

```mermaid
flowchart TD
Start(["Backend Re-lock"]) --> AnalyzeRanges["Analyze dependency ranges"]
AnalyzeRanges --> RegenerateLocks["Regenerate uv.lock files"]
RegenerateLocks --> CheckVersions{"Check for prereleases"}
CheckVersions --> |Yes| Reject["Reject prerelease versions"]
CheckVersions --> |No| VerifyCrypto["Review cryptography caps"]
VerifyCrypto --> ReviewCallSites["Review JWT/signing call sites"]
ReviewCallSites --> MakeDecision["Adopt or maintain caps"]
MakeDecision --> RunTests["Execute product test suites"]
RunTests --> VerifyGate["Run make verify"]
VerifyGate --> LiveCheck["Live check critical paths"]
LiveCheck --> Complete(["Backend re-lock complete"])
```

**Diagram sources**
- [pyproject.toml:6-21](file://products/agent-platform/pyproject.toml#L6-L21)
- [pyproject.toml:6-19](file://products/identity-broker/pyproject.toml#L6-L19)
- [plan.md:75-95](file://docs/specs/SPEC-042-dependency-hygiene/plan.md#L75-L95)

**Section sources**
- [spec.md:161-196](file://docs/specs/SPEC-042-dependency-hygiene/spec.md#L161-L196)
- [plan.md:75-95](file://docs/specs/SPEC-042-dependency-hygiene/plan.md#L75-L95)
- [tasks.md:47-64](file://docs/specs/SPEC-042-dependency-hygiene/tasks.md#L47-L64)

### Comprehensive Dependency Adoption
The platform adopts a coordinated approach to dependency updates:

**Frontend Adopt Set:**
- antd: 6.6.1 → latest stable 6.x (patch refresh)
- TypeScript: 5.6.3 → 5.9.x (latest stable 5.x line)
- Vite: 6.4.3 → 8.x (paired with plugin-react 6.x)
- Vitest: 3.2.7 → 4.x (compatible with vite 6/7/8)
- jsdom: 25.0.1 → 30.x (requires node ≥22.22.2)
- React: 18.3.1 → 19.x (peer compatibility already declared)

**Backend Adopt Set:**
- agentscope: 2.0.6 → 2.0.7.post1 (in range >=2.0.4,<3.0)
- fastapi: 0.139.2 → 0.141.1 (in range)
- uvicorn: 0.51.0 → 0.52.4 (in range)
- cryptography: adjudicated per call site compatibility
- redis/elasticsearch: caps parked with documented reasons

**Design Decisions:**
- Latest stable only — no betas, RCs, or dev versions
- Code migration preferred over version pinning
- TypeScript stays on 5.x line for stability
- React 19 adopted due to ready peer surface
- agentscope treated as kernel with enhanced verification

**Section sources**
- [spec.md:100-160](file://docs/specs/SPEC-042-dependency-hygiene/spec.md#L100-L160)
- [spec.md:197-243](file://docs/specs/SPEC-042-dependency-hygiene/spec.md#L197-L243)
- [plan.md:48-74](file://docs/specs/SPEC-042-dependency-hygiene/plan.md#L48-L74)

## Dependency Analysis
The platform maintains coordinated dependencies across frontend and backend systems:

```mermaid
graph LR
subgraph "Frontend Dependencies"
React["react 19.x"]
Antd["antd 6.x"]
Vite["vite 8.x"]
Vitest["vitest 4.x"]
JSDOM["jsdom 30.x"]
TS["typescript 5.9.x"]
end
subgraph "Backend Dependencies"
FastAPI["fastapi 0.141.1"]
Uvicorn["uvicorn 0.52.4"]
AgentScope["agentscope 2.0.7.post1"]
Pydantic["pydantic 2.x"]
Crypto["cryptography <45.0"]
Redis["redis <7.0"]
ES["elasticsearch <9.0"]
end
React --> Portal["Operator Portal"]
Antd --> Portal
Vite --> Portal
Vitest --> Portal
JSDOM --> Vitest
TS --> Portal
FastAPI --> Services["Python Services"]
Uvicorn --> Services
AgentScope --> AgentPlatform["Agent Platform"]
Pydantic --> Services
Crypto --> Security["Security Services"]
Redis --> Cache["Cache Services"]
ES --> Search["Search Services"]
```

**Diagram sources**
- [package.json:15-33](file://products/operator-portal/web-ui/app/package.json#L15-L33)
- [pyproject.toml:6-21](file://products/agent-platform/pyproject.toml#L6-L21)
- [spec.md:110-126](file://docs/specs/SPEC-042-dependency-hygiene/spec.md#L110-L126)

**Section sources**
- [spec.md:110-126](file://docs/specs/SPEC-042-dependency-hygiene/spec.md#L110-L126)
- [spec.md:168-181](file://docs/specs/SPEC-042-dependency-hygiene/spec.md#L168-L181)

## Performance Considerations
The comprehensive dependency hygiene effort considers performance implications across both frontend and backend:

**Frontend Performance:**
- Drawer size migration preserves layout without additional reflows beyond normal prop updates
- Alert title migration does not alter rendering performance characteristics
- Vitest guard adds minimal overhead through console output interception during test runs
- Dependency bumps may improve build times (Vite 8) and test stability (jsdom 30)
- Behavioral parity required for all frontend upgrades

**Backend Performance:**
- Lockfile refresh maintains service performance within established parameters
- Agentscope kernel update includes comprehensive performance verification
- Cryptography updates reviewed for signing operation performance impact
- Redis and Elasticsearch client caps maintained to preserve operational stability

**Cross-Platform Considerations:**
- Coordinated upgrade timing minimizes service disruption
- Frozen sync approach ensures consistent dependency resolution
- Live verification processes validate performance across critical paths

[No sources needed since this section provides general guidance based on the comprehensive scope]

## Troubleshooting Guide
Comprehensive troubleshooting procedures for both frontend and backend dependency issues:

**Frontend Issues:**
- If suite fails due to antd deprecation warnings, inspect console output captured by the guard and locate offending component usage
- If Drawer width-to-size migration causes layout shifts, verify numeric size values match original widths (230, 260, 560)
- If Alert title migration alters appearance, ensure icon and type props remain unchanged and description is preserved where applicable
- If dependency refresh breaks builds, check Vitest config shape changes and plugin-react 6 options; revert to behavior-preserving fixes only
- If React 19 introduces type tightening errors, address them conservatively without changing runtime behavior

**Backend Issues:**
- If lockfile regeneration fails, verify dependency ranges in pyproject.toml files are correctly specified
- If cryptography cap adjudication reveals incompatibilities, review JWT/signing call sites in affected products
- If agentscope update causes issues, run full agent-platform suite plus make verify before investigating further
- If service tests fail after re-lock, compare lockfile changes to identify specific dependency causing regression
- For live check failures, deploy to dev-k8s environment and execute mutating-demo.sh with HITL leg

**Cross-Platform Issues:**
- If version conflicts arise between frontend and backend dependencies, coordinate resolution through the spec's design decisions
- If peer dependency warnings appear, verify compatibility declarations in package.json and pyproject.toml files
- If build gates fail, check both tsc --noEmit and make verify outputs for specific error messages

**Section sources**
- [plan.md:36-47](file://docs/specs/SPEC-042-dependency-hygiene/plan.md#L36-L47)
- [plan.md:75-95](file://docs/specs/SPEC-042-dependency-hygiene/plan.md#L75-L95)
- [tasks.md:15-76](file://docs/specs/SPEC-042-dependency-hygiene/tasks.md#L15-L76)

## Conclusion
SPEC-042 establishes a comprehensive platform-wide dependency hygiene approach that extends far beyond the original portal-only scope. The specification successfully addresses both frontend and backend dependency management through coordinated migration of deprecated antd APIs, implementation of deprecation regression guards, managed refresh of toolchain dependencies including React 19, and systematic re-locking of all backend Python services to their latest stable versions.

The work preserves behavioral integrity while strengthening long-term maintainability across the entire Luban AIOps platform. By adopting a disciplined approach to dependency management that includes cryptography cap adjudication, agentscope kernel updates with enhanced verification, and comprehensive live checking of critical paths, SPEC-042 sets a foundation for sustainable platform evolution.

The expansion from portal-specific to platform-wide scope demonstrates the interconnected nature of modern platform architectures and the importance of coordinated dependency management strategies that consider both user-facing interfaces and backend service stability.

[No sources needed since this section summarizes without analyzing specific files]

## Appendices
**Verification Checklist:**
- Zero antd deprecation warnings in vitest output
- Green tsc --noEmit compilation
- Green production build for portal
- All eight Python product test suites green under frozen sync
- make verify passes with updated dependencies
- Live walkthrough covering sign-in, streamed chat turn, session panel, Approvals, and Documents drawer
- Live check of chat, HITL confirmation, and approved-mutating paths via mutating-demo.sh

**Impact Assessment:**
- Frontend: Operator portal web-ui app and Dockerfile node base pin check
- Backend: All eight Python products' uv.lock files with cryptography cap adjudication
- Contracts: None touched - no route, action, event type, or execution path changes
- Security: Enhanced verification burden for agentscope kernel bump and cryptography cap review
- Operations: Living-state docs require updates including CHANGELOG, release notes, configuration reference, spec index, and delivery roadmap

**Section sources**
- [plan.md:96-116](file://docs/specs/SPEC-042-dependency-hygiene/plan.md#L96-L116)
- [spec.md:266-282](file://docs/specs/SPEC-042-dependency-hygiene/spec.md#L266-L282)
- [tasks.md:65-76](file://docs/specs/SPEC-042-dependency-hygiene/tasks.md#L65-L76)