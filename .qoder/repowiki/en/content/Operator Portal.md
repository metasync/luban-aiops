# Operator Portal

<cite>
**Referenced Files in This Document**
- [README.md](file://products/operator-portal/README.md)
- [Dockerfile](file://products/operator-portal/Dockerfile)
- [Makefile](file://products/operator-portal/Makefile)
- [nginx.conf](file://products/operator-portal/nginx.conf)
- [index.html](file://products/operator-portal/web-ui/app/index.html)
- [main.tsx](file://products/operator-portal/web-ui/app/src/main.tsx)
- [App.tsx](file://products/operator-portal/web-ui/app/src/App.tsx)
- [AuthContext.tsx](file://products/operator-portal/web-ui/app/src/auth/AuthContext.tsx)
- [client.ts](file://products/operator-portal/web-ui/app/src/api/client.ts)
- [ChatView.tsx](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx)
- [SettingsView.tsx](file://products/operator-portal/web-ui/app/src/views/control/SettingsView.tsx)
- [AuditView.tsx](file://products/operator-portal/web-ui/app/src/views/audit/AuditView.tsx)
- [AuditSummaryPanel.tsx](file://products/operator-portal/web-ui/app/src/views/audit/AuditSummaryPanel.tsx)
- [constants.ts](file://products/operator-portal/web-ui/app/src/views/audit/constants.ts)
- [AuditView.test.tsx](file://products/operator-portal/web-ui/app/src/views/__tests__/AuditView.test.tsx)
- [tokens.ts](file://products/operator-portal/web-ui/app/src/theme/tokens.ts)
</cite>

## Update Summary
**Changes Made**
- Updated audit trail section to reflect v0.29.2 critical hook ordering fix for render stability during sign-out/token refresh scenarios
- Added documentation for enhanced type safety with DrilldownPatch type for compile-time enforcement of drill-down invariants
- Enhanced testing coverage section with comprehensive regression tests for hook order preservation
- Updated troubleshooting guide with v0.29.2 specific stability improvements
- Updated conclusion to include latest hook ordering hardening and type safety enhancements

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
The Operator Portal is the operator-facing web application for platform administration and monitoring. It provides a modern SPA shell with role-based navigation, chat-driven interactions, incident triage, approval workflows, enhanced audit trail viewing with tabbed interface, permissions inspection, and workspace resource browsing. The portal authenticates via OIDC through the identity broker, proxies API calls to the platform gateway, and serves a static bundle via nginx with immutable asset caching and SPA fallback.

Key capabilities include:
- Chat and streaming responses with tool evidence and inline human-in-the-loop confirmations
- Incident management with triage reports and live runs
- Approval queue with pending decision badges and actions
- **Enhanced read-only audit trail with sophisticated tabbed interface (Events and Summary tabs), shared filter toolbar, CSV export with truncation warnings, comprehensive summary analytics with drill-down capabilities, and critical hook ordering stability for sign-out/token refresh scenarios**
- Permissions matrix view sourced from policy enforcement
- Workspace views for tools and skills catalogs
- Settings & Debug panel showing session, identity, and platform component health

**Section sources**
- [README.md:1-137](file://products/operator-portal/README.md#L1-L137)

## Project Structure
The Operator Portal product ships a multi-stage Docker image that builds a Vite/React SPA and serves it with nginx. The runtime exposes port 8080, serves hashed assets immutably, keeps index.html no-store for immediate rollouts, and proxies /api/ and /health/ to the platform gateway.

```mermaid
graph TB
Browser["Browser"] --> Nginx["Nginx (port 8080)"]
Nginx --> |Static SPA| Assets["/assets/* (immutable cache)"]
Nginx --> |SPA fallback| Index["/index.html (no-store)"]
Nginx --> |Proxy| Gateway["Platform Gateway (8000)"]
subgraph "Build"
Node["Node build (Vite/React)"] --> Dist["/usr/share/nginx/html"]
end
Nginx --> Dist
```

**Diagram sources**
- [Dockerfile:1-29](file://products/operator-portal/Dockerfile#L1-L29)
- [nginx.conf:1-43](file://products/operator-portal/nginx.conf#L1-L43)

**Section sources**
- [Dockerfile:1-29](file://products/operator-portal/Dockerfile#L1-L29)
- [nginx.conf:1-43](file://products/operator-portal/nginx.conf#L1-L43)
- [Makefile:1-14](file://products/operator-portal/Makefile#L1-L14)

## Core Components
- Application shell and routing: React app root, theme provider, auth provider, and view router with sidebar sections and responsive drawer.
- Authentication: OIDC login flow, token refresh scheduling, and session persistence; roles drive UI visibility and feature gating.
- API client: Centralized fetch wrapper adding bearer tokens and request IDs, with configurable gateway URL override.
- Chat workspace: Session list, message composer, model selector, voice input, streaming SSE transport, tool evidence rendering, and HITL confirmation cards.
- Control views: Approvals inbox, **enhanced audit trail with sophisticated tabbed interface and critical hook ordering stability**, permissions matrix, settings & debug, incidents triage.
- Workspace views: Tools catalog and skills inventory with filters.
- Theme and accessibility: Dark theme tokens mirrored into CSS custom properties; ARIA labels and keyboard-friendly controls.

**Section sources**
- [App.tsx:1-422](file://products/operator-portal/web-ui/app/src/App.tsx#L1-L422)
- [AuthContext.tsx:1-110](file://products/operator-portal/web-ui/app/src/auth/AuthContext.tsx#L1-L110)
- [client.ts:1-101](file://products/operator-portal/web-ui/app/src/api/client.ts#L1-L101)
- [ChatView.tsx:1-200](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L1-L200)
- [SettingsView.tsx:1-200](file://products/operator-portal/web-ui/app/src/views/control/SettingsView.tsx#L1-L200)
- [AuditView.tsx:1-469](file://products/operator-portal/web-ui/app/src/views/audit/AuditView.tsx#L1-L469)
- [tokens.ts:1-43](file://products/operator-portal/web-ui/app/theme/tokens.ts#L1-L43)

## Architecture Overview
The portal follows a thin-client architecture:
- Frontend: React SPA built with Vite, served by nginx with immutable asset caching and SPA fallback.
- Auth: OIDC via identity broker; access tokens are attached to requests.
- Backend integration: All API calls go through nginx proxy to the platform gateway, which enforces policies and delegates to agent-platform, policy-center, and other services.

```mermaid
sequenceDiagram
participant U as "User Browser"
participant N as "Nginx"
participant G as "Platform Gateway"
participant I as "Identity Broker"
participant A as "Agent Platform"
U->>N : GET /index.html
N-->>U : index.html (no-store)
U->>I : Start OIDC login
I-->>U : Redirect back with code
U->>N : POST /api/v1/auth/refresh
N->>G : Proxy /api/*
G-->>U : Access token + identity
U->>G : GET /api/v1/models, sessions, etc.
G->>A : Forward authenticated requests
A-->>G : Responses
G-->>U : JSON responses
```

**Diagram sources**
- [nginx.conf:8-28](file://products/operator-portal/nginx.conf#L8-L28)
- [AuthContext.tsx:40-71](file://products/operator-portal/web-ui/app/src/auth/AuthContext.tsx#L40-L71)
- [client.ts:65-92](file://products/operator-portal/web-ui/app/src/api/client.ts#L65-L92)

## Detailed Component Analysis

### Application Shell and Navigation
- Two-column layout with collapsible sidebar and off-canvas drawer on narrow screens.
- Role-based menu items grouped under Control and Workspace sections; section headers hide when all entries are hidden.
- User card shows initials, username, roles, sign-in/sign-out buttons, and platform version chip.

```mermaid
flowchart TD
Start(["App mount"]) --> Boot{"Booting?"}
Boot --> |Yes| Spinner["Show spinner"]
Boot --> |No| Sidebar["Render sidebar with role-gated items"]
Sidebar --> View{"Active view?"}
View --> |chat| Chat["ChatView"]
View --> |incidents| Incidents["IncidentsView"]
View --> |approvals| Approvals["ApprovalsView"]
View --> |audit| Audit["AuditView"]
View --> |permissions| Permissions["PermissionsView"]
View --> |tools| Tools["ToolsView"]
View --> |skills| Skills["SkillsView"]
View --> |settings| Settings["SettingsView"]
```

**Diagram sources**
- [App.tsx:287-422](file://products/operator-portal/web-ui/app/src/App.tsx#L287-L422)

**Section sources**
- [App.tsx:1-422](file://products/operator-portal/web-ui/app/src/App.tsx#L1-L422)

### Authentication and Session Management
- OIDC login initiated from UI; callback completed at startup; existing sessions restored from storage.
- Token refresh scheduled before expiry; failures clear session and prompt re-authentication.
- Roles extracted from identity context and used to gate UI features and API calls.

```mermaid
sequenceDiagram
participant C as "Client"
participant AC as "AuthProvider"
participant OB as "OIDC Broker"
C->>AC : Mount App
AC->>OB : completeLoginFromCallback()
alt Callback present
OB-->>AC : Session
AC->>AC : scheduleTokenRefresh()
else No callback
AC->>AC : loadAuthSession()
AC->>OB : refreshAuthenticatedIdentity()
OB-->>AC : Identity + token
end
Note over AC : On refresh failure -> clear session and show error
```

**Diagram sources**
- [AuthContext.tsx:31-85](file://products/operator-portal/web-ui/app/src/auth/AuthContext.tsx#L31-L85)

**Section sources**
- [AuthContext.tsx:1-110](file://products/operator-portal/web-ui/app/src/auth/AuthContext.tsx#L1-L110)

### API Client and Request Correlation
- Centralized request function attaches x-request-id and Authorization header when signed in.
- Gateway URL can be overridden via local storage key for development/debugging.
- Errors are wrapped in ApiError with status and message.

```mermaid
flowchart TD
Call["requestJson(path, options)"] --> Headers["Build headers<br/>x-request-id + Bearer"]
Headers --> Fetch["fetch(gateway + path)"]
Fetch --> Ok{"response.ok?"}
Ok --> |No| Throw["Throw ApiError(status, message)"]
Ok --> |Yes| Json["Parse JSON and return"]
```

**Diagram sources**
- [client.ts:38-92](file://products/operator-portal/web-ui/app/src/api/client.ts#L38-L92)

**Section sources**
- [client.ts:1-101](file://products/operator-portal/web-ui/app/src/api/client.ts#L1-L101)

### Chat Workspace and Streaming
- Session workspace manages multiple sessions, titles, last-active timestamps, and pinned incident sessions.
- Model selector integrates with /api/v1/models; selection persists per session.
- Voice input uses Web Speech API with language preference persisted locally.
- Tool evidence rendered as collapsible cards with status badges and optional full output expander.
- Inline HITL confirmation cards post decisions to /api/v1/chat/confirm; server-side enforcement applies.

```mermaid
sequenceDiagram
participant U as "User"
participant CV as "ChatView"
participant ST as "Stream Adapter"
participant GW as "Gateway"
U->>CV : Send prompt
CV->>ST : Open SSE stream
ST->>GW : POST /api/v1/chat (with model, session)
GW-->>ST : Stream events (tool_call, tool_result, text)
ST-->>CV : Update transcript, render evidence, show confirmation cards
U->>CV : Approve/Deny (HITL)
CV->>GW : POST /api/v1/chat/confirm
GW-->>CV : Resume stream with decision
```

**Diagram sources**
- [ChatView.tsx:1-200](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L1-L200)

**Section sources**
- [ChatView.tsx:1-200](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L1-L200)
- [README.md:43-126](file://products/operator-portal/README.md#L43-L126)

### Enhanced Audit Trail with Critical Hook Ordering Stability
**Updated** The audit trail view has been completely redesigned with an advanced tabbed interface that provides both detailed event inspection and comprehensive summary analytics with interactive drill-down capabilities. The v0.29.2 release includes critical React hook ordering fixes that resolve render stability issues during sign-out and token refresh scenarios, ensuring consistent behavior even when authentication state changes while the view remains mounted.

#### Advanced Tabbed Interface Architecture
- **Shared Filter Toolbar**: Both Events and Summary tabs share a common filter interface for username, event type, outcome, service, and time range filtering
- **Events Tab**: Displays cursor-paginated audit events with expandable verbatim envelopes showing full event details
- **Summary Tab**: Shows deterministic envelope-column aggregates with collapsible sections, interactive drill-down, and comprehensive analytics

#### Critical Hook Ordering Fix (v0.29.2)
- **Hook Order Preservation**: All hooks must run before the `!allowed` early return to maintain stable rendering during authentication state changes
- **Sign-Out Stability**: Resolves render instability when users sign out or tokens refresh while the audit view remains mounted
- **Conditional Rendering Safety**: Ensures React's rules of hooks are followed even when role gates change dynamically
- **Test Coverage**: Comprehensive regression tests verify hook order preservation across authentication state transitions

#### Enhanced Type Safety
- **DrilldownPatch Type**: Compile-time enforcement of drill-down invariants ensures type-safe filter merging
- **Type-Safe Filter Merging**: Prevents runtime errors when drilling down from summary to events with merged filters
- **Interface Contracts**: Strict TypeScript interfaces define the shape of drill-down patches and filter parameters

#### Key Features
- **Role-Based Access**: Requires auditor or platform-admin roles with server-side enforcement
- **Structured Error Handling**: Provides actionable error messages for different failure scenarios (403, 502, 503)
- **CSV Export**: Server-side blob download with Content-Disposition filename support and truncation warnings
- **Real-time Filtering**: Filters apply consistently across both tabs with lazy loading for summary data
- **Interactive Drill-Down**: Click any aggregate value to navigate to Events tab with merged filters using type-safe patches
- **Collapsible Sections**: Four bucket tables organized in antd Collapse component with default expansion
- **Proportion Visualization**: Percentage values with simplified one-decimal display (v0.29.1: progress bars removed)
- **Decision Chain Visualization**: New statistic row showing total events and four decision-chain steps

```mermaid
flowchart TD
FilterToolbar["Shared Filter Toolbar"] --> EventsTab["Events Tab"]
FilterToolbar --> SummaryTab["Summary Tab"]
FilterToolbar --> ExportBtn["Export CSV Button"]
EventsTab --> EventTable["Event Table with Pagination"]
EventTable --> ExpandableRows["Expandable Event Envelopes"]
SummaryTab --> StatisticRow["Statistic Row<br/>Total + Decision Chain"]
StatisticRow --> CollapsibleSections["Collapsible Sections<br/>(antd Collapse)"]
CollapsibleSections --> BucketTables["Bucket Tables<br/>by Event Type, Outcome, Service, Actors"]
BucketTables --> ProportionDisplay["Proportion Display<br/>One-decimal percentage only<br/>(v0.29.1: no progress bars)"]
BucketTables --> FixedWidthColumns["Fixed-width columns<br/>Right-aligned count & share<br/>(v0.29.1 improvement)"]
BucketTables --> Drilldown["Interactive Drill-Down<br/>to Events with Merged Filters<br/>(Type-safe DrilldownPatch)"]
ExportBtn --> BlobDownload["Server-side Blob Download"]
BlobDownload --> TruncationWarning["Truncation Warning if Applied"]
HookOrderFix["v0.29.2 Hook Ordering Fix<br/>Stable rendering during auth changes"] --> AllTabs["All Tabs Maintain Stability"]
```

**Diagram sources**
- [AuditView.tsx:98-469](file://products/operator-portal/web-ui/app/src/views/audit/AuditView.tsx#L98-L469)
- [AuditSummaryPanel.tsx:115-210](file://products/operator-portal/web-ui/app/src/views/audit/AuditSummaryPanel.tsx#L115-L210)

#### Summary Panel Components
- **Headline Statistics**: Total events count plus four decision-chain step counters (confirmation_decided, execution_requested, execution_completed, execution_rejected)
- **Collapsible Analytics**: Four bucket tables organized by event type, outcome, service, and top actors
- **Interactive Elements**: Every aggregate value is clickable for drill-down to filtered Events view
- **Visual Indicators**: Simplified proportion display with one-decimal percentages (v0.29.1: removed progress bars for cleaner presentation)
- **Fixed Layout**: Right-aligned numeric columns with fixed widths (88px each) for count and share, ensuring consistent table layout (v0.29.1 enhancement)
- **Zero-State Handling**: Empty posture when no events match current filters

#### Constants Management and Drift Guard
- **Centralized Constants**: Event types, emitter services, and outcomes moved to dedicated `constants.ts` file
- **Schema Drift Protection**: Vitest tests ensure constants remain synchronized with shared audit-event schema
- **Outcome Filter Integration**: New outcome select dropdown follows the same drift-guard pattern as other filters
- **Maintainable Configuration**: Single source of truth for audit-related configuration

**Section sources**
- [AuditView.tsx:1-469](file://products/operator-portal/web-ui/app/src/views/audit/AuditView.tsx#L1-L469)
- [AuditSummaryPanel.tsx:1-207](file://products/operator-portal/web-ui/app/src/views/audit/AuditSummaryPanel.tsx#L1-L207)
- [constants.ts:1-49](file://products/operator-portal/web-ui/app/src/views/audit/constants.ts#L1-L49)
- [AuditView.test.tsx:83-95](file://products/operator-portal/web-ui/app/src/views/__tests__/AuditView.test.tsx#L83-L95)

### Settings, Health, and Debug
- Identity pane shows sign-in state, username, roles, subject, and groups.
- Session pane displays active session and workspace session count.
- Platform pane probes gateway health endpoints and runtime metadata to display component readiness and versions.

```mermaid
flowchart TD
Load["Open Settings"] --> Identity["Render Identity Pane"]
Load --> Session["Render Session Pane"]
Load --> Platform["Probe /health/ready and /api/v1/runtime"]
Platform --> Status{"Ready?"}
Status --> |Yes| Ready["Display ready/degraded/not ready"]
Status --> |No| Unavailable["Display unavailable"]
```

**Diagram sources**
- [SettingsView.tsx:1-200](file://products/operator-portal/web-ui/app/src/views/control/SettingsView.tsx#L1-L200)
- [nginx.conf:19-28](file://products/operator-portal/nginx.conf#L19-L28)

**Section sources**
- [SettingsView.tsx:1-200](file://products/operator-portal/web-ui/app/src/views/control/SettingsView.tsx#L1-L200)

### Deployment and Runtime Configuration
- Multi-stage build compiles SPA and copies dist into nginx image.
- Nginx serves immutable cached assets and SPA fallback; proxies /api/ and /health/ to gateway.
- Makefile defines image name and context; includes shared image rules.

```mermaid
graph LR
Dev["Developer Machine"] --> Build["npm ci && npm run build"]
Build --> Image["docker build -t web-ui ."]
Image --> Run["docker run -p 8080:8080"]
Run --> Nginx["Nginx serving SPA"]
Nginx --> GW["platform-gateway:8000"]
```

**Diagram sources**
- [Dockerfile:11-29](file://products/operator-portal/Dockerfile#L11-L29)
- [nginx.conf:1-43](file://products/operator-portal/nginx.conf#L1-L43)
- [Makefile:1-14](file://products/operator-portal/Makefile#L1-L14)

**Section sources**
- [Dockerfile:1-29](file://products/operator-portal/Dockerfile#L1-L29)
- [nginx.conf:1-43](file://products/operator-portal/nginx.conf#L1-L43)
- [Makefile:1-14](file://products/operator-portal/Makefile#L1-L14)

## Dependency Analysis
- UI layer depends on antd and Ant Design X components for layout, menus, tables, and chat bubbles.
- App shell composes AuthProvider and theme provider around the root component.
- Views depend on API client for data fetching; roles determine visibility and actions.
- Nginx routes static assets and proxies API traffic to the gateway.

```mermaid
graph TB
Main["main.tsx"] --> App["App.tsx"]
App --> Auth["AuthContext.tsx"]
App --> Views["Views (Chat, Incidents, Approvals, Audit, Permissions, Tools, Skills, Settings)"]
Views --> API["client.ts"]
API --> Nginx["nginx.conf proxy"]
Nginx --> Gateway["Platform Gateway"]
```

**Diagram sources**
- [main.tsx:1-18](file://products/operator-portal/web-ui/app/src/main.tsx#L1-L18)
- [App.tsx:1-422](file://products/operator-portal/web-ui/app/src/App.tsx#L1-L422)
- [client.ts:1-101](file://products/operator-portal/web-ui/app/src/api/client.ts#L1-L101)
- [nginx.conf:1-43](file://products/operator-portal/nginx.conf#L1-L43)

**Section sources**
- [main.tsx:1-18](file://products/operator-portal/web-ui/app/src/main.tsx#L1-L18)
- [App.tsx:1-422](file://products/operator-portal/web-ui/app/src/App.tsx#L1-L422)
- [client.ts:1-101](file://products/operator-portal/web-ui/app/src/api/client.ts#L1-L101)
- [nginx.conf:1-43](file://products/operator-portal/nginx.conf#L1-L43)

## Performance Considerations
- Immutable asset caching: Content-hashed assets under /assets/ are served with long-lived immutable cache headers to improve repeat load performance.
- SPA fallback: index.html is served with no-store to ensure immediate rollout without stale shell issues.
- Streaming: Long-lived SSE connections use proxy_read_timeout configured to support extended operations.
- Client-side state: Session workspace minimizes redundant network calls by maintaining local session lists and pinning incident sessions.
- **Lazy Loading**: Summary tab data is fetched only when the tab is activated, reducing initial page load time.
- **Efficient Filtering**: Shared filter state prevents redundant API calls when switching between tabs.
- **Optimized Rendering**: Collapsible sections reduce initial DOM complexity while providing rich interactivity.
- **Progressive Enhancement**: Zero-state handling prevents unnecessary computations when no data is available.
- **v0.29.1 Layout Optimization**: Fixed-width columns eliminate dynamic width recalculation overhead and prevent layout shifts during table rendering.
- **v0.29.2 Hook Stability**: Critical hook ordering fixes eliminate render instability during authentication state changes, improving perceived performance and reliability.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
- Authentication errors: AuthContext surfaces authError messages; check OIDC callback completion and token refresh behavior.
- API failures: ApiError wraps non-ok responses with status and message; verify gateway reachability and bearer token presence.
- Gateway override: Use local storage key to redirect API calls during development or debugging.
- Health checks: Settings panel probes gateway health endpoints; if unavailable, inspect nginx proxy configuration and upstream service status.
- **Audit View Issues**: Check role permissions (auditor/platform-admin required); verify audit service availability; review structured error messages for specific failure scenarios.
- **CSV Export Problems**: Monitor truncation warnings; verify server-side export limits; check Content-Disposition headers for proper filename handling.
- **Summary Tab Issues**: Verify lazy loading behavior; check filter state synchronization; ensure collapse component renders correctly.
- **Drill-Down Navigation**: Confirm filter merging logic; verify Events tab loads with correct merged parameters; check cursor reset behavior.
- **v0.29.1 Table Layout Issues**: If audit summary tables show wrapping or misalignment, verify browser viewport width and antd table configuration; the fixed-width columns should prevent wrapping but may require minimum container width.
- **v0.29.2 Hook Ordering Issues**: If audit view exhibits unstable rendering during sign-out or token refresh, verify that all hooks execute before the role gate early return; check that authentication state changes don't cause unexpected unmounting.
- **Type Safety Issues**: Ensure DrilldownPatch type usage is correct when implementing custom drill-down functionality; verify filter merging maintains type safety.

**Section sources**
- [AuthContext.tsx:40-85](file://products/operator-portal/web-ui/app/src/auth/AuthContext.tsx#L40-L85)
- [client.ts:8-16](file://products/operator-portal/web-ui/app/src/api/client.ts#L8-L16)
- [client.ts:25-36](file://products/operator-portal/web-ui/app/src/api/client.ts#L25-L36)
- [nginx.conf:8-28](file://products/operator-portal/nginx.conf#L8-L28)
- [AuditView.tsx:69-85](file://products/operator-portal/web-ui/app/src/views/audit/AuditView.tsx#L69-L85)
- [AuditView.test.tsx:83-95](file://products/operator-portal/web-ui/app/src/views/__tests__/AuditView.test.tsx#L83-L95)

## Conclusion
The Operator Portal delivers a secure, role-aware admin interface with rich operational features including chat-driven troubleshooting, incident triage, approvals, **comprehensive audit trail with sophisticated tabbed interface and advanced analytics**, and platform health diagnostics. Its deployment model combines a modern SPA with efficient nginx serving and robust proxying to backend services, enabling scalable and maintainable operator workflows. The recent complete redesign of the audit trail provides operators with powerful event inspection capabilities, interactive drill-down navigation, and comprehensive summary analytics for understanding system behavior and identifying patterns through collapsible sections, simplified proportion visualization, and decision-chain tracking. The v0.29.1 hardening further improves the user experience by removing progress bars from share columns and implementing fixed-width columns for more stable and readable table layouts. The v0.29.2 critical hook ordering fix ensures render stability during sign-out and token refresh scenarios, while enhanced type safety with DrilldownPatch provides compile-time enforcement of drill-down invariants, making the audit trail more reliable and maintainable.

[No sources needed since this section summarizes without analyzing specific files]

## Appendices

### Deployment Instructions
- Build and run:
  - Build the image using the product Makefile; the image name is web-ui and the context includes the repository root for VERSION injection.
  - Run the container exposing port 8080; configure reverse proxy or ingress to route to the container.
- Nginx configuration:
  - Static assets under /assets/ are immutable-cacheable.
  - /index.html is no-store with SPA fallback.
  - /api/ and /health/ are proxied to the platform gateway.

**Section sources**
- [Makefile:1-14](file://products/operator-portal/Makefile#L1-L14)
- [Dockerfile:11-29](file://products/operator-portal/Dockerfile#L11-L29)
- [nginx.conf:1-43](file://products/operator-portal/nginx.conf#L1-L43)

### Integration Points
- Identity broker: OIDC login, token refresh, and logout flows.
- Platform gateway: Proxies all /api/ calls; enforces policies and delegates to agent-platform and other services.
- Agent platform: Provides chat sessions and streaming responses.
- Policy center: Supplies approval queue and decision state surfaced in Approvals and Permissions views.
- **Audit service**: Provides durable audit trail with events, summary analytics, CSV export capabilities, and comprehensive filtering support.

**Section sources**
- [README.md:127-133](file://products/operator-portal/README.md#L127-L133)

### UI Customization and Accessibility
- Theme: Dark theme tokens defined in tokens.ts and applied via antd ConfigProvider; CSS custom properties mirror tokens for consistent styling.
- Accessibility: ARIA labels on navigation and user actions; keyboard-friendly menus and controls; responsive layout adapts to narrow screens with a drawer.
- **Enhanced Audit Interface**: Sophisticated tabbed interface provides intuitive navigation between detailed events and comprehensive summary analytics; shared filter toolbar ensures consistent user experience across tabs; collapsible sections improve information density while maintaining accessibility; v0.29.1 improvements provide more stable table layouts with fixed-width columns; v0.29.2 hook ordering ensures stable rendering during authentication state changes.

**Section sources**
- [tokens.ts:1-43](file://products/operator-portal/web-ui/app/src/theme/tokens.ts#L1-L43)
- [App.tsx:395-418](file://products/operator-portal/web-ui/app/src/App.tsx#L395-L418)
- [AuditView.tsx:298-361](file://products/operator-portal/web-ui/app/src/views/audit/AuditView.tsx#L298-L361)

### Browser Compatibility
- Uses modern browser APIs such as Web Speech API for voice input and standard fetch/SSE patterns.
- SPA relies on ES modules and modern JavaScript features; ensure browsers support ES modules and required APIs.

**Section sources**
- [README.md:43-65](file://products/operator-portal/README.md#L43-L65)
- [index.html:1-14](file://products/operator-portal/web-ui/app/index.html#L1-L14)

### Enhanced Audit Trail Features
**Completely Redesigned** The audit trail has been completely redesigned with advanced interactive features, further hardened in v0.29.1 for improved table stability and readability, and v0.29.2 for critical hook ordering stability during authentication state changes.

#### Sophisticated Tabbed Interface
- **Events Tab**: Cursor-paginated table of audit events with expandable verbatim envelopes
- **Summary Tab**: Comprehensive aggregates with collapsible sections, interactive drill-down, and visual analytics
- **Shared Filter Toolbar**: Consistent filtering across both tabs for username, event type, outcome, service, and time ranges

#### Interactive Drill-Down System
- **Click-to-Navigate**: Any aggregate value in Summary tab triggers drill-down to Events tab
- **Merged Filters**: Drill-down merges selected dimension into current filters without resetting existing filters
- **Automatic Refresh**: Events tab automatically reloads with merged filter parameters
- **Cursor Reset**: Navigation resets pagination cursor for clean starting point
- **Type-Safe Patches**: DrilldownPatch type ensures compile-time enforcement of valid filter combinations

#### Advanced Summary Analytics
- **Headline Statistics**: New statistic row showing total events plus four decision-chain steps (confirmation_decided, execution_requested, execution_completed, execution_rejected)
- **Collapsible Sections**: Four bucket tables organized using antd Collapse component with default expansion
- **Proportion Visualization**: One-decimal percentage display only (v0.29.1: removed progress bars for cleaner presentation)
- **Fixed-Width Columns**: Right-aligned count and share columns with 88px fixed width for stable layout (v0.29.1 enhancement)
- **Interactive Elements**: All aggregate values are clickable for drill-down navigation
- **Zero-State Handling**: Empty posture when no events match current filters

#### Enhanced Filtering and Controls
- **Outcome Select Dropdown**: New outcome filter following drift-guard pattern with schema synchronization
- **Drift Guard Protection**: Automated tests ensure filter options stay synchronized with shared audit-event schema
- **Real-time Updates**: Filter changes apply immediately across both tabs with optimized API calls

#### CSV Export Functionality
- Server-side blob download with proper Content-Disposition filename handling
- Truncation warnings when export limits are exceeded (AUDIT_EXPORT_MAX_ROWS)
- Structured error handling for permission denials and service unavailability

#### Critical Hook Ordering Stability (v0.29.2)
- **Hook Order Preservation**: All hooks execute before role gate early returns to maintain stable rendering
- **Authentication State Changes**: Resolves render instability during sign-out and token refresh scenarios
- **Comprehensive Test Coverage**: Regression tests verify hook order preservation across authentication state transitions
- **Consistent Behavior**: Ensures React's rules of hooks are followed even when role gates change dynamically

**Section sources**
- [AuditView.tsx:98-469](file://products/operator-portal/web-ui/app/src/views/audit/AuditView.tsx#L98-L469)
- [AuditSummaryPanel.tsx:1-207](file://products/operator-portal/web-ui/app/src/views/audit/AuditSummaryPanel.tsx#L1-L207)
- [constants.ts:1-49](file://products/operator-portal/web-ui/app/src/views/audit/constants.ts#L1-L49)
- [AuditView.test.tsx:83-95](file://products/operator-portal/web-ui/app/src/views/__tests__/AuditView.test.tsx#L83-L95)
- [AuditView.test.tsx:174-226](file://products/operator-portal/web-ui/app/src/views/__tests__/AuditView.test.tsx#L174-L226)