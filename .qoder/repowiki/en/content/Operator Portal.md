# Operator Portal

<cite>
**Referenced Files in This Document**
- [App.tsx](file://products/operator-portal/web-ui/app/src/App.tsx)
- [DocumentsView.tsx](file://products/operator-portal/web-ui/app/src/views/control/DocumentsView.tsx)
- [documents.ts](file://products/operator-portal/web-ui/app/src/api/documents.ts)
- [global.css](file://products/operator-portal/web-ui/app/src/theme/global.css)
- [ChatView.tsx](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx)
- [usePendingDecisionPoll.ts](file://products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts)
- [usePendingDecisionPoll.test.ts](file://products/operator-portal/web-ui/app/src/chat/__tests__/usePendingDecisionPoll.test.ts)
- [ComposerSelectionBar.tsx](file://products/operator-portal/web-ui/app/src/chat/ComposerSelectionBar.tsx)
- [ModelSelect.tsx](file://products/operator-portal/web-ui/app/src/chat/ModelSelect.tsx)
- [markdown.ts](file://products/operator-portal/web-ui/app/src/chat/markdown.ts)
- [useChatStream.ts](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts)
- [useChatStreamReseed.test.ts](file://products/operator-portal/web-ui/app/src/stream/__tests__/useChatStreamReseed.test.ts)
- [models.ts](file://products/operator-portal/web-ui/app/src/api/models.ts)
- [transport.ts](file://products/operator-portal/web-ui/app/src/stream/transport.ts)
- [AuthContext.tsx](file://products/operator-portal/web-ui/app/src/auth/AuthContext.tsx)
- [useSessionWorkspace.ts](file://products/operator-portal/web-ui/app/src/sessions/useSessionWorkspace.ts)
- [roles.ts](file://products/operator-portal/web-ui/app/src/roles.ts)
- [tokens.ts](file://products/operator-portal/web-ui/app/src/theme/tokens.ts)
- [version.ts](file://products/operator-portal/web-ui/app/src/version.ts)
- [vite.config.ts](file://products/operator-portal/web-ui/app/vite.config.ts)
- [package.json](file://products/operator-portal/web-ui/app/package.json)
- [index.html](file://products/operator-portal/web-ui/app/index.html)
- [nginx.conf](file://products/operator-portal/nginx.conf)
- [Dockerfile](file://products/operator-portal/Dockerfile)
- [Makefile](file://products/operator-portal/Makefile)
- [README.md](file://products/operator-portal/README.md)
- [web-ui-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-deployment.yaml)
- [web-ui-service.yaml](file://shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-service.yaml)
- [image.mk](file://mk/image.mk)
- [VERSION](file://VERSION)
- [validate_version.py](file://shared/shared-contracts/scripts/validate_version.py)
- [hitl_confirmations.py](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py)
- [2026-08-21-hitl-confirmation-bridging.md](file://docs/agentic-aiops-platform/release-notes/2026-08-21-hitl-confirmation-bridging.md)
- [2026-08-25-owner-side-live-decision-sync.md](file://docs/agentic-aiops-platform/release-notes/2026-08-25-owner-side-live-decision-sync.md)
- [2026-08-25-owner-decision-sync-reseed-patch.md](file://docs/agentic-aiops-platform/release-notes/2026-08-25-owner-decision-sync-reseed-patch.md)
- [2026-08-26-confirmation-card-turn-anchoring.md](file://docs/agentic-aiops-platform/release-notes/2026-08-26-confirmation-card-turn-anchoring.md)
- [2026-08-26-live-check-patch.md](file://docs/agentic-aiops-platform/release-notes/2026-08-26-live-check-patch.md)
- [delivery-roadmap.md](file://docs/agentic-aiops-platform/delivery-roadmap.md)
- [SPEC-032 plan](file://docs/specs/SPEC-032-owner-side-live-decision-sync/plan.md)
- [SPEC-032 spec](file://docs/specs/SPEC-032-owner-side-live-decision-sync/spec.md)
- [SPEC-033 plan](file://docs/specs/SPEC-033-confirmation-card-turn-anchoring/plan.md)
- [SPEC-033 spec](file://docs/specs/SPEC-033-confirmation-card-turn-anchoring/spec.md)
- [transcript.ts](file://products/operator-portal/web-ui/app/src/chat/transcript.ts)
- [transcript.test.ts](file://products/operator-portal/web-ui/app/src/chat/__tests__/transcript.test.ts)
- [AuditView.tsx](file://products/operator-portal/web-ui/app/src/views/audit/AuditView.tsx)
- [IncidentsView.tsx](file://products/operator-portal/web-ui/app/src/views/incidents/IncidentsView.tsx)
- [PermissionsView.tsx](file://products/operator-portal/web-ui/app/src/views/control/PermissionsView.tsx)
- [SkillsView.tsx](file://products/operator-portal/web-ui/app/src/views/control/SkillsView.tsx)
- [ToolsView.tsx](file://products/operator-portal/web-ui/app/src/views/control/ToolsView.tsx)
- [ApprovalsView.tsx](file://products/operator-portal/web-ui/app/src/views/control/ApprovalsView.tsx)
- [approvals.ts](file://products/operator-portal/web-ui/app/src/api/approvals.ts)
- [sessions.ts](file://products/operator-portal/web-ui/app/src/api/sessions.ts)
- [useSpeechRecognition.ts](file://products/operator-portal/web-ui/app/src/voice/useSpeechRecognition.ts)
- [languages.ts](file://products/operator-portal/web-ui/app/src/voice/languages.ts)
- [models.test.ts](file://products/operator-portal/web-ui/app/src/api/__tests__/models.test.ts)
- [markdown.test.ts](file://products/operator-portal/web-ui/app/src/chat/__tests__/markdown.test.ts)
- [useChatStream.test.ts](file://products/operator-portal/web-ui/app/src/stream/__tests__/useChatStream.test.ts)
- [ComposerSelectionBar.test.tsx](file://products/operator-portal/web-ui/app/src/chat/__tests__/ComposerSelectionBar.test.tsx)
- [ConfirmationCard.test.tsx](file://products/operator-portal/web-ui/app/src/chat/__tests__/ConfirmationCard.test.tsx)
- [ApprovalsView.test.tsx](file://products/operator-portal/web-ui/app/src/views/__tests__/ApprovalsView.test.tsx)
</cite>

## Update Summary
**Changes Made**
- Moved Documents navigation from Control group to Workspace section reflecting semantic positioning as daily workflow artifacts
- Enhanced document fetching workflow with separate API calls for full details using AbortController support
- Improved loading states with abort controller support for better user experience during document detail retrieval
- Updated navigation structure to reflect the repositioning of Documents view in the workspace section

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Enhanced Navigation System](#enhanced-navigation-system)
7. [Role-Gated Audit Trail System](#role-gated-audit-trail-system)
8. [Tier-Aware HITL Confirmation Card System](#tier-aware-hitl-confirmation-card-system)
9. [Approvals Inbox and Cross-Session Management](#approvals-inbox-and-cross-session-management)
10. [Operations Document Repository](#operations-document-repository)
11. [Authentication and Security](#authentication-and-security)
12. [Enhanced Markdown Rendering Interface](#enhanced-markdown-rendering-interface)
13. [Real-time Streaming Interface](#real-time-streaming-interface)
14. [Evidence Persistence and Replay System](#evidence-persistence-and-replay-system)
15. [Model Selection and Catalog Integration](#model-selection-and-catalog-integration)
16. [Composer Selection Bar Architecture](#composer-selection-bar-architecture)
17. [Settings View - Session & Identity Panel](#settings-view---session--identity-panel)
18. [Skills Integration and Cited Guidance](#skills-integration-and-cited-guidance)
19. [Permission Matrix and Workspace Resources](#permission-matrix-and-workspace-resources)
20. [Multi-Session Workspace Management](#multi-session-workspace-management)
21. [Voice Input Support](#voice-input-support)
22. [Incident Triage and Deep Linking](#incident-triage-and-deep-linking)
23. [Deployment Guide](#deployment-guide)
24. [UI Customization](#ui-customization)
25. [Accessibility Features](#accessibility-features)
26. [Browser Compatibility](#browser-compatibility)
27. [Troubleshooting Guide](#troubleshooting-guide)
28. [Conclusion](#conclusion)

## Introduction

The Operator Portal is a modern web-based administrative interface designed for platform administration and monitoring within the Luban AIOPS ecosystem. The portal has been completely rebuilt using React 18, TypeScript, and Vite, replacing the previous vanilla JavaScript implementation. It provides operators with a sophisticated two-column shell interface featuring a persistent sidebar for navigation and a main content area for interactive operations. The portal serves as a centralized control plane for platform administrators, offering real-time visibility into system status through an interactive chat interface, comprehensive evidence panels for tool execution tracking, configuration management capabilities, operational controls, and administrative functions necessary for maintaining the AI-powered agent platform infrastructure.

**Updated** The portal now features significantly enhanced human-in-the-loop approval system with improved decision synchronization, arrival presentation polish, approvals view pagination, and session workspace synchronization. The live decision sync system now implements time-based settle windows (300 seconds) instead of tick budgets, providing more reliable synchronization of external decisions to active chat views. **Critical Enhancement**: The approvals inbox now includes client-side pagination for decision history with 10 entries per page, improving usability when managing large volumes of confirmation records. **New Feature**: The session workspace now implements monotonic refresh sequences to prevent race conditions during concurrent decision processing, ensuring data consistency across multiple approval operations. **Enhanced Arrival Presentation**: Improved visual feedback and state management provide better user experience during decision synchronization, with clearer indicators of pending actions and resolution status. **v0.15.0 Enhancement**: All enhancements build upon the existing turn-anchored confirmation system from SPEC-033, ensuring accurate historical context for multi-park sessions while adding these new synchronization and presentation improvements. **v0.18.1 Enhancement**: The markdown rendering system now includes enhanced nested list support with proper ordered/unordered list handling, and pod log quoting improvements that render log excerpts in fenced code blocks for better readability in agent replies. **New Feature**: The portal now includes a complete Operations Document Repository with Documents view interface providing session selection, document creation, publishing, and viewing capabilities for shift summaries and operational documentation.

## Project Structure

The Operator Portal follows a modular React architecture with clear separation of concerns between components, hooks, utilities, and styling:

```mermaid
graph TB
subgraph "React Application (Vite Build)"
A[App.tsx] --> B[ChatView.tsx]
A --> C[AuthContext.tsx]
B --> D[useChatStream.ts]
B --> E[useSessionWorkspace.ts]
B --> F[markdown.ts]
B --> G[transcript.ts]
B --> H[ComposerSelectionBar.tsx]
H --> I[ModelSelect.tsx]
B --> J[usePendingDecisionPoll.ts]
D --> K[transport.ts]
I --> L[decoder.ts]
A --> M[AuditView.tsx]
A --> N[IncidentsView.tsx]
A --> O[PermissionsView.tsx]
A --> P[SkillsView.tsx]
A --> Q[ToolsView.tsx]
A --> R[ApprovalsView.tsx]
A --> S[DocumentsView.tsx]
A --> T[Settings View]
end
subgraph "Enhanced Live Decision Sync System"
J --> U[Bounded Polling 5s Interval]
V[Change Detection] --> W[Fingerprint Comparison]
X[Time-Based Settle Window 300s] --> Y[Visibility/Focus Kick]
Z[Session Detail API] --> AA[Re-seed Timeline via reseedTurns]
end
subgraph "Authoritative Re-seed Mechanism"
AB[reseedTurns Method] --> AC[Same-Session Only Check]
AD[Live Turns Replacement] --> AE[Cache Entry Replacement]
AF[No Stream Abort] --> AG[No Session Pointer Move]
AH[No-Op for Other Sessions] --> AI[Prevents Cache Poisoning]
end
subgraph "Turn-Anchored Confirmation System (SPEC-033)"
AJ[attachConfirmations Function] --> AK[turn_index Validation]
AL[Anchored Target Selection] --> AM[Per-Exchange Anchoring]
AN[Legacy Fallback] --> AO[Newest Turn Anchor]
AP[Synthetic Turn Creation] --> AQ[Empty Transcript Handling]
AR[Pending Record Anchoring] --> AS[confirmationPending Flag]
end
subgraph "Enhanced Approvals Inbox System"
AT[useApprovalsInbox Hook] --> AU[Real-time Polling 30s]
AV[getApprovalsInbox API] --> AW[Cross-session Discovery]
AX[ConfirmationRecord Types] --> AY[Decision Attribution]
AZ[Race Resolution Handling] --> BA[409 Already Resolved]
BB[Client-Side Pagination] --> BC[10 Entries Per Page]
end
subgraph "Monotonic Session Workspace"
BD[useSessionWorkspace Hook] --> BE[Monotonic Refresh Sequence]
BF[refreshSeqRef] --> BG[Prevents Race Conditions]
BH[Pinned Sessions] --> BI[Incident Deep Links]
BJ[Active Session Persistence] --> BK[Session Storage]
BL[Inline Rename Support] --> BM[Session Title Updates]
BN[Session ID Copy] --> BO[Clipboard Integration]
end
subgraph "Operations Document Repository"
BP[DocumentsView Component] --> BQ[Session Selection]
BR[Create Shift Summary Dialog] --> BS[Document Creation]
BT[Document Publishing] --> BU[Published State Management]
BV[Digest Rendering] --> BW[Prose Panel Integration]
BX[Cross-Owner Access] --> BY[Foreign Session Metadata]
end
subgraph "Model Selection System"
BZ[ModelCatalog API] --> CA[getModelCatalog Function]
CB[ComposerSelectionBar] --> CC[Extensible Control Strip]
CD[ModelSelect Component] --> CE[Dynamic Rendering Logic]
CF[Session Model State] --> CG[Pinned Model Persistence]
CH[Fail-Open UX] --> CI[Graceful Degradation]
end
subgraph "Tier-Aware Confirmation System"
CJ[APPROVAL_DECIDER_ROLES] --> CK[Role-Based Badge Display]
CL[Confirmation Tier Detection] --> CM[Operator vs Approver Badges]
CN[Role Verification] --> CO[Approver Permission Checks]
CP[Tier-Aware UI] --> CQ[Visual Status Indicators]
end
subgraph "Settings & Identity Panel"
CR[AuthContext] --> CS[Identity Information Display]
CT[Session Workspace] --> CU[Session Details]
CV[Platform Version] --> CW[Metadata Display]
CX[Read-Only Interface] --> CY[Operational Insights]
end
subgraph "Evidence Persistence System"
CZ[transcriptToTurns] --> DA[EvidenceFrame Mapping]
DB[EvidenceTurn Groups] --> DC[Request ID Attachment]
DD[Truncation Markers] --> DE[Payload Budget Handling]
DF[Live Stream Frames] --> DG[Unified Turn Model]
DH[Replayed Evidence] --> DI[Consistent Rendering]
end
subgraph "Enhanced Navigation System"
DJ[useNarrowViewport Hook] --> DK[Responsive Breakpoint Detection at 992px]
DL[Mobile Menu Button] --> DM[Dynamic ARIA Labels]
DN[Sidebar Collapsible 64px Rail] --> DO[Drawer Integration]
DP[Content Spacing Management] --> DQ[.view-container-inset Class]
end
subgraph "Build & Deployment"
DR[vite.config.ts] --> DS[package.json]
DT[Dockerfile] --> DU[Makefile]
DV[VERSION] --> DW[validate_version.py]
end
subgraph "Backend Services"
DX[Agent Platform] --> DY[HITL Confirmations]
DZ[Platform Gateway] --> EA[Identity Broker]
EB[Tool Gateway] --> EC[Policy Engine]
ED[Document Repository] --> EE[Shift Summaries]
end
end
```

**Diagram sources**
- [App.tsx:56-70](file://products/operator-portal/web-ui/app/src/App.tsx#L56-L70)
- [App.tsx:288-307](file://products/operator-portal/web-ui/app/src/App.tsx#L288-L307)
- [App.tsx:334-357](file://products/operator-portal/web-ui/app/src/App.tsx#L334-L357)
- [ChatView.tsx:720-739](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L720-L739)
- [usePendingDecisionPoll.ts:23-30](file://products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts#L23-L30)
- [usePendingDecisionPoll.ts:51-145](file://products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts#L51-L145)
- [useChatStream.ts:430-441](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L430-L441)
- [transcript.ts:137-165](file://products/operator-portal/web-ui/app/src/chat/transcript.ts#L137-L165)
- [ApprovalsView.tsx:28-31](file://products/operator-portal/web-ui/app/src/views/control/ApprovalsView.tsx#L28-L31)
- [ApprovalsView.tsx:52-183](file://products/operator-portal/web-ui/app/src/views/control/ApprovalsView.tsx#L52-L183)
- [approvals.ts:11-19](file://products/operator-portal/web-ui/app/src/api/approvals.ts#L11-L19)
- [useSessionWorkspace.ts:58-62](file://products/operator-portal/web-ui/app/src/sessions/useSessionWorkspace.ts#L58-L62)
- [DocumentsView.tsx:371-597](file://products/operator-portal/web-ui/app/src/views/control/DocumentsView.tsx#L371-L597)
- [documents.ts:42-89](file://products/operator-portal/web-ui/app/src/api/documents.ts#L42-L89)
- [ComposerSelectionBar.tsx:16-47](file://products/operator-portal/web-ui/app/src/chat/ComposerSelectionBar.tsx#L16-L47)
- [ModelSelect.tsx:18-57](file://products/operator-portal/web-ui/app/src/chat/ModelSelect.tsx#L18-57)
- [models.ts:20-30](file://products/operator-portal/web-ui/app/src/api/models.ts#L20-L30)
- [transcript.ts:55-70](file://products/operator-portal/web-ui/app/src/chat/transcript.ts#L55-L70)
- [sessions.ts:11-42](file://products/operator-portal/web-ui/app/src/api/sessions.ts#L11-L42)
- [useChatStream.ts:245-268](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L245-L268)
- [markdown.ts:67-91](file://products/operator-portal/web-ui/app/src/chat/markdown.ts#L67-L91)
- [markdown.test.ts:59-77](file://products/operator-portal/web-ui/app/src/chat/__tests__/markdown.test.ts#L59-L77)
- [roles.ts:35-35](file://products/operator-portal/web-ui/app/src/roles.ts#L35-L35)
- [ChatView.tsx:295-298](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L295-L298)

**Section sources**
- [App.tsx](file://products/operator-portal/web-ui/app/src/App.tsx)
- [package.json](file://products/operator-portal/web-ui/app/package.json)
- [vite.config.ts](file://products/operator-portal/web-ui/app/vite.config.ts)

## Core Components

The Operator Portal consists of several key React components and hooks that work together to provide a comprehensive administrative interface:

### Frontend Architecture
- **React 18 Components**: Modern component-based architecture with hooks for state management
- **Ant Design Integration**: Professional UI components with dark theme customization
- **Two-Column Shell Layout**: Persistent sidebar with responsive mobile drawer support
- **Enhanced Sectioned Navigation**: Organized navigation with Chat, Control, and Workspace sections
- **Chat-Based Interface**: Real-time streaming responses with turn-based conversation management
- **Inline Per-Turn Evidence System**: Sophisticated turn-scoped evidence grouping with collapsible groups
- **Tier-Aware HITL Confirmation Cards**: Inline approval surfaces for ASK-gated tool executions with Approve/Deny buttons and tier-specific badges
- **Turn-Anchored Confirmation Cards**: Each confirmation card renders under the exchange that parked it, providing accurate historical context
- **Enhanced Approvals Inbox**: Cross-session confirmation management with real-time polling, decision attribution, and client-side pagination
- **Improved Live Decision Sync**: Time-based settle windows with visibility/focus kick mechanisms for reliable external decision synchronization
- **Monotonic Session Workspace**: Prevents race conditions during concurrent decision processing with refresh sequence tracking
- **Composer Selection Bar**: Extensible control strip rendered under message input for model selection and future per-turn controls
- **Model Select Component**: Dynamic model selection with catalog-driven rendering and session persistence
- **Operations Document Repository**: Complete shift summary creation, management, and viewing interface with session selection and cross-owner access
- **Settings & Identity Panel**: Read-only panel displaying identity information, session details, and platform metadata
- **Skills Integration**: Enhanced evidence cards with "Cited guidance" chips displaying matched skills
- **Authentication System**: OIDC integration with automatic token refresh and session management
- **Enhanced Markdown Renderer**: Comprehensive text formatting with XSS prevention, nested list support, and syntax highlighting support
- **Responsive Design**: Dark theme with mobile-first approach and accessibility features

### Backend Integration
- **Streaming API Client**: Robust Server-Sent Events implementation with error handling and reconnection
- **Model Catalog API Client**: Safe discovery of available models via GET /api/v1/models endpoint
- **Enhanced Approvals Inbox API Client**: Cross-session confirmation discovery via GET /api/v1/approvals/inbox endpoint with pagination support
- **Operations Document API Client**: Document repository access via GET/POST/DELETE endpoints for shift summaries
- **Session Detail API Client**: Bounded polling of session detail surface for live decision synchronization with time-based settle windows
- **HITL Confirmation Bridge**: Seamless integration with agent-platform confirmation registry for pending tool approvals
- **Authentication Handler**: Secure integration with identity broker for authentication and authorization
- **Enhanced Session Management**: Multi-session support with transcript caching, workspace persistence, and defensive parsing
- **Error Handling**: Comprehensive error management with user-friendly feedback and recovery for multiple failure types
- **API v6 Compliance**: Backend schema compliance for risk level handling in pending calls

### Enhanced User Interface
- **Persistent Sidebar**: Branding, identity management, and function navigation with Ant Design Menu
- **User Card System**: Avatar display with initials, username badge, and role information
- **Role-Based Navigation**: Conditional visibility based on user roles and permissions
- **Mobile Drawer**: Off-canvas navigation for narrow screens with proper focus management
- **Settings & Debug Panel**: Configuration management and debugging tools with read-only operational insights
- **Enhanced Approvals Inbox Interface**: Dedicated view for managing parked confirmations with provenance metadata, decision history, and client-side pagination
- **Operations Document Interface**: Complete shift summary management with session selection, document creation, publishing, and viewing capabilities
- **Composer Selection Bar**: Extensible control strip with model selector and future per-turn selection capabilities

### Improved Live Decision Sync Implementation
- **Time-Based Settle Windows**: 300-second settle window instead of tick budgets, preventing premature termination during long-running tool executions
- **Visibility/Focus Kick Mechanisms**: Immediate polling when browser tab becomes visible or gains focus, compensating for background tab throttling
- **Bounded Polling**: 5-second interval polling that only activates when confirmation cards are pending or during settle window
- **Change Detection**: Fingerprint-based comparison to detect state changes in session details
- **Session Isolation**: Proper scoping to prevent cross-session data contamination
- **Streaming Protection**: Automatic pause during active streaming to prevent interference
- **Error Resilience**: Graceful handling of network failures while maintaining last-good view

### Monotonic Session Workspace
- **Refresh Sequence Tracking**: Monotonic refresh sequence prevents race conditions when decisions trigger refreshes during ongoing fetches
- **Race Condition Prevention**: Only the newest refresh sequence can apply results, preventing stale data from overwriting fresh confirmation flags
- **Pinned Session Support**: Incident deep-link sessions appear as extra panel entries even before server list catches up
- **Active Session Persistence**: Current session selection persists across page reloads using session storage
- **Inline Rename Support**: Session title updates with validation and error handling
- **Session ID Copy**: One-click clipboard integration for sharing session identifiers

### Operations Document Repository
- **Shift Summary Creation**: Modal dialog for creating immutable shift snapshots with session selection and optional prose generation
- **Document Management**: List view with filtering by scope (mine/published), status tags, and action buttons
- **Cross-Owner Access**: Foreign session metadata inclusion with appropriate permission checks
- **Digest Rendering**: Structured display of session coverage with foreign session indicators
- **Publishing Workflow**: One-way publish operation with duplicate protection and status management
- **Prose Integration**: Optional AI-generated narrative summary with included/failed/not_requested states

**Updated** The interface now includes significantly enhanced human-in-the-loop approval system with improved decision synchronization, arrival presentation polish, approvals view pagination, and session workspace synchronization. The live decision sync system now implements time-based settle windows (300 seconds) instead of tick budgets, providing more reliable synchronization of external decisions to active chat views. **Critical Enhancement**: The approvals inbox now includes client-side pagination for decision history with 10 entries per page, improving usability when managing large volumes of confirmation records. **New Feature**: The session workspace now implements monotonic refresh sequences to prevent race conditions during concurrent decision processing, ensuring data consistency across multiple approval operations. **Enhanced Arrival Presentation**: Improved visual feedback and state management provide better user experience during decision synchronization, with clearer indicators of pending actions and resolution status. **v0.14.1 Patch**: The useChatStream hook still includes the dedicated `reseedTurns` method that provides authoritative same-session timeline updates, preventing cache shadowing issues where stale cached turns would override fresh state during owner-side decision synchronization. **v0.15.0 Enhancement**: The confirmation card system continues to implement proper turn anchoring based on SPEC-033, ensuring each confirmation card renders under the exchange that parked it rather than stacking all cards under the newest turn, providing accurate historical context for multi-park sessions. **v0.18.1 Enhancement**: The markdown rendering system now includes enhanced nested list support with proper ordered/unordered list handling, and pod log quoting improvements that render log excerpts in fenced code blocks for better readability in agent replies. **New Feature**: The Operations Document Repository provides complete shift summary management with session selection, document creation, publishing, and viewing capabilities for operational documentation.

**Section sources**
- [App.tsx:56-70](file://products/operator-portal/web-ui/app/src/App.tsx#L56-L70)
- [App.tsx:288-307](file://products/operator-portal/web-ui/app/src/App.tsx#L288-L307)
- [App.tsx:334-357](file://products/operator-portal/web-ui/app/src/App.tsx#L334-L357)
- [ChatView.tsx:1-790](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L1-L790)
- [usePendingDecisionPoll.ts:1-170](file://products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts#L1-L170)
- [DocumentsView.tsx:1-597](file://products/operator-portal/web-ui/app/src/views/control/DocumentsView.tsx#L1-L597)
- [ComposerSelectionBar.tsx:1-48](file://products/operator-portal/web-ui/app/src/chat/ComposerSelectionBar.tsx#L1-L48)
- [ModelSelect.tsx:1-58](file://products/operator-portal/web-ui/app/src/chat/ModelSelect.tsx#L1-L58)
- [useChatStream.ts:1-454](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L1-L454)
- [transcript.ts:137-165](file://products/operator-portal/web-ui/app/src/chat/transcript.ts#L137-L165)
- [ApprovalsView.tsx:1-388](file://products/operator-portal/web-ui/app/src/views/control/ApprovalsView.tsx#L1-L388)
- [useSessionWorkspace.ts:1-218](file://products/operator-portal/web-ui/app/src/sessions/useSessionWorkspace.ts#L1-L218)

## Architecture Overview

The Operator Portal follows a modern React single-page application architecture built with TypeScript and Vite, providing type safety and enhanced developer experience while maintaining performance and maintainability.

```mermaid
sequenceDiagram
participant User as "Browser"
participant React as "React App"
participant Nav as "Enhanced Navigation"
participant Auth as "Auth Context"
participant PendingSync as "usePendingDecisionPoll"
participant Approvals as "Approvals Inbox"
participant ApprovalsView as "ApprovalsView"
participant Documents as "DocumentsView"
participant CompSel as "ComposerSelectionBar"
participant ModelCat as "Model Catalog API"
participant Stream as "Chat Stream Hook"
participant Transcript as "Transcript Converter"
participant Views as "View Components"
participant Nginx as "Nginx Server (Port 8080)"
participant Gateway as "API Gateway"
participant Agent as "Agent Platform"
participant HITL as "HITL Registry"
participant DocsRepo as "Document Repository"
User->>React : Load React SPA
Note over Nav : useNarrowViewport() detects 992px breakpoint
Nav->>React : Set narrow viewport state
React->>Nav : Render 64px icon rail with dynamic aria-labels
Note over React : Enhanced Navigation with content spacing
React->>Auth : Initialize authentication
Auth->>Gateway : /api/v1/auth/login
Gateway->>Agent : Redirect to OIDC provider
Agent-->>Gateway : Authorization code
Gateway-->>Auth : Access tokens + identity
Note over React : Responsive Content Spacing
React->>Views : Navigate to specific views with proper padding
Note over PendingSync : Enhanced Live Decision Sync Initialization
React->>PendingSync : usePendingDecisionPoll(sessionId, turns, streaming, applyDetail)
PendingSync->>PendingSync : Check for pending confirmation cards
PendingSync->>Gateway : GET /api/v1/sessions/{id} (every 5s)
Gateway->>Agent : Fetch session detail with confirmations
Agent-->>PendingSync : SessionDetail with transcript & confirmations
PendingSync->>PendingSync : Compare fingerprint (transcript length + chars + records)
PendingSync->>Transcript : transcriptToTurns(detail.transcript, detail.evidence_turns, detail.confirmations)
Note over Stream : v0.14.1 reseedTurns Fix
PendingSync->>Stream : chat.reseedTurns(sessionId, re-seeded turns)
Stream->>Stream : Same-session check & authoritative update
Stream->>Stream : Replace both live turns AND cache entry
Stream-->>PendingSync : No-op for other sessions
Note over Approvals : Enhanced Approvals Inbox Initialization
React->>Approvals : useApprovalsInbox(enabled=true for deciders)
Approvals->>Gateway : GET /api/v1/approvals/inbox
Gateway->>Agent : Cross-session confirmation discovery
Agent-->>Approvals : Confirmation records (pending + 30-day history)
Note over Approvals : Real-time Polling (30s interval) + Client-Side Pagination
Approvals->>Approvals : setInterval(refresh, 30000ms)
Approvals->>Approvals : Client-side pagination (10 entries per page)
Note over Documents : Operations Document Repository Initialization
React->>Documents : DocumentsView with workspace integration
Documents->>Gateway : GET /api/v1/documents?scope=mine|published
Gateway->>DocsRepo : List documents with scope filtering
DocsRepo-->>Documents : OperationDocument[] with digest & provenance
Documents->>Documents : CreateShiftSummaryDialog for session selection
Documents->>Gateway : POST /api/v1/documents (create draft)
Gateway->>DocsRepo : Create shift summary with session coverage
DocsRepo-->>Documents : Document with draft state
Note over React : Model Catalog Discovery
React->>ModelCat : GET /api/v1/models
ModelCat-->>React : Model catalog with id/label/provider/default
React->>CompSel : Render ComposerSelectionBar with catalog
CompSel->>CompSel : Collapse if no models available
CompSel->>ModelCat : Mount ModelSelect component
Note over React : Evidence Persistence and Replay
User->>React : Open session with transcript
React->>Transcript : transcriptToTurns(transcript, evidence_turns)
Transcript->>Transcript : Map EvidenceFrames to ToolCall/Result frames
Transcript->>Transcript : Attach request IDs and truncation markers
Note over Transcript : SPEC-033 Turn Anchoring
Transcript->>Transcript : attachConfirmations with turn_index validation
Transcript->>Transcript : Per-exchange anchoring for each confirmation card
Transcript->>Transcript : Legacy fallback for records without turn_index
Transcript-->>React : Unified ChatTurn[] with evidence and anchored confirmations
Note over React : Chat & Streaming with Stale Session Handling
User->>React : Send message via ChatView
Note over React : Missing Ref Check & Stale Session Detection
React->>Stream : useChatStream.send() with selectedModel
Stream->>Gateway : POST /api/v1/chat/stream (with session_id, model)
Gateway-->>Stream : 404 Error (stale session)
Stream->>Stream : Drop session_id & Retry
Stream->>Gateway : POST /api/v1/chat/stream (auto-create)
Gateway->>Agent : Forward request with model selection
Agent-->>Gateway : Stream events
Gateway-->>Stream : SSE stream
Note over React : Incident Deep Linking
User->>React : Click "Continue in chat"
React->>Stream : Pin incident session
Stream->>Gateway : Create/pin incident session
Gateway-->>Stream : Session ID returned
Stream-->>React : Active session updated
Note over React : Tier-Aware Confirmation Processing
User->>React : Trigger ASK-gated tool execution
React->>HITL : Process confirmation request with tier detection
HITL->>HITL : Determine confirmation tier (operator vs approver)
HITL-->>React : Return tier-specific badge and role requirements
React->>React : Display appropriate badge based on confirmation tier
Note over ApprovalsView : Enhanced Decision Processing
User->>ApprovalsView : Click Approve/Deny button
ApprovalsView->>Gateway : POST /api/v1/chat/confirm (decision)
Gateway->>Agent : Submit confirmation decision
Agent-->>Gateway : confirmation_result event
Gateway-->>ApprovalsView : Stream result
ApprovalsView->>ApprovalsView : Update record status and attribution
Note over SessionWorkspace : Monotonic Refresh Sequence
User->>SessionWorkspace : Make decision triggering refresh
SessionWorkspace->>SessionWorkspace : Increment refreshSeqRef
SessionWorkspace->>SessionWorkspace : Only newest sequence applies results
SessionWorkspace-->>User : Prevents race conditions during concurrent decisions
```

**Diagram sources**
- [App.tsx:56-70](file://products/operator-portal/web-ui/app/src/App.tsx#L56-L70)
- [App.tsx:288-307](file://products/operator-portal/web-ui/app/src/App.tsx#L288-L307)
- [App.tsx:334-357](file://products/operator-portal/web-ui/app/src/App.tsx#L334-L357)
- [ChatView.tsx:720-739](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L720-L739)
- [usePendingDecisionPoll.ts:23-30](file://products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts#L23-L30)
- [usePendingDecisionPoll.ts:51-145](file://products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts#L51-L145)
- [useChatStream.ts:430-441](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L430-L441)
- [transcript.ts:137-165](file://products/operator-portal/web-ui/app/src/chat/transcript.ts#L137-L165)
- [ApprovalsView.tsx:28-31](file://products/operator-portal/web-ui/app/src/views/control/ApprovalsView.tsx#L28-L31)
- [ApprovalsView.tsx:52-183](file://products/operator-portal/web-ui/app/src/views/control/ApprovalsView.tsx#L52-L183)
- [approvals.ts:11-19](file://products/operator-portal/web-ui/app/src/api/approvals.ts#L11-L19)
- [useSessionWorkspace.ts:58-62](file://products/operator-portal/web-ui/app/src/sessions/useSessionWorkspace.ts#L58-L62)
- [DocumentsView.tsx:371-597](file://products/operator-portal/web-ui/app/src/views/control/DocumentsView.tsx#L371-L597)
- [documents.ts:42-89](file://products/operator-portal/web-ui/app/src/api/documents.ts#L42-L89)
- [ComposerSelectionBar.tsx:16-47](file://products/operator-portal/web-ui/app/src/chat/ComposerSelectionBar.tsx#L16-L47)
- [ModelSelect.tsx:18-57](file://products/operator-portal/web-ui/app/src/chat/ModelSelect.tsx#L18-57)
- [models.ts:20-30](file://products/operator-portal/web-ui/app/src/api/models.ts#L20-L30)
- [transcript.ts:72-106](file://products/operator-portal/web-ui/app/src/chat/transcript.ts#L72-L106)
- [sessions.ts:52-60](file://products/operator-portal/web-ui/app/src/api/sessions.ts#L52-L60)
- [useChatStream.ts:245-268](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L245-L268)
- [IncidentsView.tsx:219-228](file://products/operator-portal/web-ui/app/src/views/incidents/IncidentsView.tsx#L219-L228)
- [useSessionWorkspace.ts:136-159](file://products/operator-portal/web-ui/app/src/sessions/useSessionWorkspace.ts#L136-L159)
- [useChatStream.ts:191-314](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L191-314)
- [transport.ts:75-100](file://products/operator-portal/web-ui/app/src/stream/transport.ts#L75-L100)
- [ChatView.tsx:295-298](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L295-L298)
- [roles.ts:35-35](file://products/operator-portal/web-ui/app/src/roles.ts#L35-L35)

The architecture emphasizes type safety, component composition, and maintainable state management while providing enterprise-grade functionality for platform operations. The React hooks pattern enables clean separation of concerns and reusable logic across components. **Enhanced with improved live decision sync capabilities** that provide time-based settle windows and visibility/focus kick mechanisms for immediate reflection of external decisions in active chat views through bounded polling with change detection. **Critical Enhancement**: The approvals inbox now includes client-side pagination for decision history with 10 entries per page, improving usability when managing large volumes of confirmation records. **New Feature**: The session workspace now implements monotonic refresh sequences to prevent race conditions during concurrent decision processing, ensuring data consistency across multiple approval operations. **Enhanced Arrival Presentation**: Improved visual feedback and state management provide better user experience during decision synchronization, with clearer indicators of pending actions and resolution status. **Critical Enhancement**: The streaming system includes robust stale session handling with automatic retry logic and missing session reference tracking to prevent errors from deleted or expired sessions. **New Feature**: The ComposerSelectionBar component provides an extensible architecture for model selection and future per-turn controls, improving modularity and maintainability. **Enhanced Feature**: The Settings view provides read-only access to identity information, session details, and platform metadata for operational awareness. **Critical Enhancement**: The tier-aware HITL confirmation system now provides clear visual indicators distinguishing between operator confirmations and approver-required scenarios, improving workflow clarity and user experience. **New Feature**: The Approvals inbox provides cross-session confirmation management with real-time polling, decision attribution, 30-day history browsing, and client-side pagination for designated approvers. **New Feature**: The Operations Document Repository provides complete shift summary management with session selection, document creation, publishing, and viewing capabilities for operational documentation. **v0.14.1 Patch**: The live decision sync system continues to use the authoritative `reseedTurns` method to prevent cache shadowing, ensuring that external decisions are properly synchronized to active chat views without being overridden by stale cached turns. **v0.15.0 Enhancement**: The confirmation card system continues to implement proper turn anchoring based on SPEC-033, ensuring each confirmation card renders under the exchange that parked it rather than stacking all cards under the newest turn, providing accurate historical context for multi-park sessions. **v0.18.1 Enhancement**: The markdown rendering system now includes enhanced nested list support with proper ordered/unordered list handling, and pod log quoting improvements that render log excerpts in fenced code blocks for better readability in agent replies.

## Detailed Component Analysis

### React Application Structure

The main React application implements a component-based architecture with clear separation of concerns:

#### App Component
- **Layout Management**: Ant Design Layout with responsive sidebar and content areas
- **Navigation State**: Active view management with role-based visibility controls
- **Enhanced Mobile Support**: Persistent 64px icon rail with responsive drawer integration
- **Loading States**: Proper loading indicators during authentication and data fetching
- **View Routing**: Dynamic routing to different view components (chat, incidents, audit, permissions, tools, skills, settings, approvals, documents)

#### Enhanced Navigation Implementation
- **useNarrowViewport Hook**: Custom hook for responsive breakpoint detection at 992px
- **Persistent 64px Icon Rail**: Collapsed sidebar that maintains navigation access across all views
- **Drawer Integration**: Mobile-specific off-canvas navigation below lg breakpoint
- **Dynamic ARIA Labels**: Context-aware accessibility labels that change based on viewport and sidebar state
- **Content Spacing Management**: Automatic padding adjustments via .view-container-inset class

#### Enhanced View Components
- **AuditView**: Role-gated audit trail with filtering and pagination
- **IncidentsView**: Incident triage with auto-refresh, manual intake, and detail views
- **PermissionsView**: Live permission matrix display from policy bundle
- **SkillsView**: Browseable skills inventory with source/tag filtering
- **ToolsView**: Read-only tools catalog with risk tier information
- **Enhanced ApprovalsView**: Cross-session confirmation inbox with real-time polling, decision history, and client-side pagination
- **Operations DocumentsView**: Complete shift summary management with session selection, document creation, publishing, and viewing
- **SettingsView**: Read-only Session & Identity panel displaying operational insights

#### Authentication Context
- **OIDC Integration**: Complete OpenID Connect flow with PKCE support
- **Token Management**: Automatic refresh and session persistence
- **Error Handling**: Graceful error handling with user feedback
- **State Management**: Centralized authentication state across components

### Enhanced Live Decision Sync Implementation

The usePendingDecisionPoll hook now provides significantly improved decision synchronization with time-based settle windows:

#### Time-Based Settle Windows
- **300-Second Settling Period**: Extended settle window replaces tick budgets, accommodating long-running tool executions that may exceed previous limits
- **Deadline-Based Termination**: Polling continues until deadline expires or no pending confirmations remain, whichever comes first
- **Automatic Reset**: Every applied change resets the settle window, ensuring slow tool runs followed by late summaries still surface
- **Background Tab Compensation**: Visibility/focus kick mechanisms compensate for background tab throttling

#### Enhanced Change Detection
- **Fingerprint Generation**: Combines transcript length, character count, and confirmation records for change detection
- **Baseline Establishment**: First tick establishes baseline without applying changes, preventing unnecessary timeline rebuilds
- **Efficient Comparison**: Identical responses never rebuild timeline, avoiding scroll disturbance and flicker

#### Improved Session Detail Synchronization
- **Timeline Re-seeding**: Uses same transcriptToTurns path as initial load for consistency
- **Session Isolation**: Proper scoping prevents cross-session data contamination
- **Streaming Protection**: Automatically pauses during active streaming to prevent interference
- **Error Resilience**: Transient failures maintain last-good view while continuing to retry

#### Authoritative Re-seed Mechanism (v0.14.1)
- **reseedTurns Method**: Dedicated method for same-session timeline updates that replaces both live turns and cache entries
- **Session Validation**: No-op for sessions not currently on screen to prevent cache poisoning
- **Stream Safety**: Never aborts streams or moves session pointers during re-seeding
- **Cache Integrity**: Ensures per-tab cache never shadows fresh state from external decisions

### Enhanced Approvals Inbox Implementation

The approvals inbox now includes significant improvements for arrival presentation and pagination:

#### Client-Side Pagination
- **10 Entries Per Page**: History tab displays 10 confirmation records per page, improving readability for large datasets
- **Page Clamping**: Pages automatically clamp when list shrinks due to retention eviction
- **Pagination Controls**: Ant Design Pagination component with proper accessibility attributes
- **History Organization**: Separate tabs for pending items and historical decisions

#### Improved Arrival Presentation
- **Visual Feedback**: Better indication of when decisions are processed and applied
- **Status Updates**: Clear status indicators during decision processing
- **Race Condition Handling**: Structured 409 responses flip losing cards to winner's outcome instead of showing errors
- **Decision Attribution**: Enhanced display of who made decisions and when

#### Enhanced Polling System
- **30-Second Intervals**: Automatic polling keeps inbox synchronized with backend state
- **Window Focus Refresh**: Additional refresh when browser window gains focus
- **Shared State**: Single poll instance shared between sidebar badge and view to prevent duplicate requests
- **Error Resilience**: Maintains last good list on transient failures while displaying error messages

### Monotonic Session Workspace

The session workspace now implements monotonic refresh sequences to prevent race conditions:

#### Refresh Sequence Tracking
- **Monotonic Counter**: refreshSeqRef ensures only the newest refresh sequence can apply results
- **Race Condition Prevention**: Prevents older responses from overwriting fresh pending-confirmation flags
- **Concurrent Decision Support**: Handles cases where decisions trigger refreshes during ongoing fetches

#### Enhanced Session Management
- **Real-Time Updates**: 30-second polling for session list updates
- **Active Session Persistence**: Session selection persists across page reloads
- **Pinned Sessions**: Support for incident deep-link sessions that appear even before server list catches up
- **Delete Operations**: Safe session deletion with conflict resolution for pending confirmations
- **Inline Rename Support**: Session title updates with validation and error handling
- **Session ID Copy**: One-click clipboard integration for sharing session identifiers

### Operations Document Repository

The Documents view provides complete shift summary management with comprehensive session selection and document lifecycle management:

#### Shift Summary Creation
- **Modal Dialog Interface**: CreateShiftSummaryDialog with label input, session selection, and prose options
- **Session Selection**: Multi-select dropdown for own sessions plus text input for foreign session IDs
- **Validation Rules**: Label required, minimum one session, maximum 20 sessions, foreign session permission checks
- **Prose Generation**: Optional AI-generated narrative summary with included/failed/not_requested states

#### Document Management Interface
- **List View**: Tabbed interface for Mine/Published scopes with document cards showing status, provenance, and actions
- **Action Buttons**: View, Publish (for owner drafts), Delete (for owner documents) with appropriate permissions
- **Status Tags**: Document type, state (draft/published), and creation timestamps with relative time formatting
- **Empty States**: Helpful messaging for no documents in either scope

#### Digest Rendering System
- **Structured Display**: DigestPanel shows generated timestamp, requester information, and session coverage
- **Session Coverage**: DigestSessionEntry displays individual session data with foreign session indicators
- **Flexible Rendering**: DigestValue component handles primitives, arrays, and objects with recursive depth support
- **Foreign Session Handling**: Purple tag indicates metadata-only access for foreign sessions

#### Publishing Workflow
- **One-Way Operation**: Publish transitions draft to published state with duplicate protection
- **Status Management**: Success/error handling with appropriate user feedback
- **Scope Refresh**: Automatic refresh after publish operations to update document lists
- **Permission Enforcement**: Owner-only publishing with appropriate error handling

**Updated** The enhanced human-in-the-loop approval system now provides significantly improved decision synchronization with time-based settle windows, arrival presentation polish, approvals view pagination, and session workspace synchronization. The live decision sync system implements 300-second settle windows instead of tick budgets, providing more reliable synchronization of external decisions to active chat views. **Critical Enhancement**: The approvals inbox now includes client-side pagination for decision history with 10 entries per page, improving usability when managing large volumes of confirmation records. **New Feature**: The session workspace now implements monotonic refresh sequences to prevent race conditions during concurrent decision processing, ensuring data consistency across multiple approval operations. **Enhanced Arrival Presentation**: Improved visual feedback and state management provide better user experience during decision synchronization, with clearer indicators of pending actions and resolution status. **v0.14.1 Patch**: The useChatStream hook continues to include the dedicated `reseedTurns` method that provides authoritative same-session timeline updates, preventing cache shadowing issues where stale cached turns would override fresh state during owner-side decision synchronization. **v0.15.0 Enhancement**: The confirmation card system continues to implement proper turn anchoring based on SPEC-033, ensuring each confirmation card renders under the exchange that parked it rather than stacking all cards under the newest turn, providing accurate historical context for multi-park sessions. **v0.18.1 Enhancement**: The markdown rendering system now includes enhanced nested list support with proper ordered/unordered list handling, and pod log quoting improvements that render log excerpts in fenced code blocks for better readability in agent replies. **New Feature**: The Operations Document Repository provides complete shift summary management with session selection, document creation, publishing, and viewing capabilities for operational documentation.

**Section sources**
- [App.tsx:56-70](file://products/operator-portal/web-ui/app/src/App.tsx#L56-L70)
- [App.tsx:288-307](file://products/operator-portal/web-ui/app/src/App.tsx#L288-L307)
- [App.tsx:334-357](file://products/operator-portal/web-ui/app/src/App.tsx#L334-L357)
- [ChatView.tsx:1-790](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L1-L790)
- [usePendingDecisionPoll.ts:1-170](file://products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts#L1-L170)
- [DocumentsView.tsx:1-597](file://products/operator-portal/web-ui/app/src/views/control/DocumentsView.tsx#L1-L597)
- [ComposerSelectionBar.tsx:1-48](file://products/operator-portal/web-ui/app/src/chat/ComposerSelectionBar.tsx#L1-L48)
- [ModelSelect.tsx:1-58](file://products/operator-portal/web-ui/app/src/chat/ModelSelect.tsx#L1-L58)
- [useChatStream.ts:1-454](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L1-L454)
- [transcript.ts:137-165](file://products/operator-portal/web-ui/app/src/chat/transcript.ts#L137-L165)
- [useSessionWorkspace.ts:1-218](file://products/operator-portal/web-ui/app/src/sessions/useSessionWorkspace.ts#L1-L218)
- [ApprovalsView.tsx:1-388](file://products/operator-portal/web-ui/app/src/views/control/ApprovalsView.tsx#L1-L388)

### CSS Styling System

The styling system maintains design consistency while leveraging Ant Design's theming with enhanced navigation support:

#### Design Tokens
- **Dark Theme**: Modern color palette optimized for extended use
- **Typography Scale**: Inter font family with responsive sizing
- **Spacing System**: Consistent margins and padding throughout
- **Animation Effects**: Smooth transitions and loading indicators

#### Component Styles
- **User Card**: Avatar display with initials, username badge, and role information
- **Navigation Items**: Clean button styling with active state indicators
- **Chat Messages**: Distinct styling for user and agent messages
- **Evidence Panels**: Professional collapsible interface with native browser details element behavior
- **Cited Guidance Chips**: Specialized styling for skill citation chips
- **Audit Trail Tables**: Responsive tables with sticky headers and expandable detail rows
- **Enhanced Approvals Inbox**: Dedicated styling for confirmation inbox entries with provenance metadata, decision history, and pagination controls
- **Operations Document Interface**: Styled document cards, digests, and prose panels with appropriate spacing and typography
- **Settings Panel**: Grid-based layout for configuration options and operational insights
- **Mobile Drawer**: Slide-in navigation with backdrop overlay

#### Enhanced Navigation Styling
- **Persistent 64px Icon Rail**: Fixed-width collapsed sidebar with consistent layout anchoring
- **Responsive Breakpoints**: Correct 992px breakpoint for mobile/desktop switching
- **Content Spacing Management**: Automatic adjustment via .view-container-inset class for non-flush views
- **Sidebar Brand Padding**: Proper spacing to prevent content overlap with navigation trigger
- **Chat View Padding**: Specific padding adjustments for flush chat views to avoid header overlap

#### Enhanced Approval Card Styling
- **Warning Border**: Yellow border indicating pending decision required
- **Badge Styling**: Color-coded badges for operator confirmation (blue) and approver required (red)
- **Locked State**: Border changes to standard when confirmation is resolved
- **Action Buttons**: Green approve button and red deny button with hover effects
- **Status Messages**: Clear status indicators for awaiting decision, approving/denying, and final states
- **Pagination Controls**: Styled pagination for decision history with proper spacing and alignment

#### Operations Document Styling
- **Document Cards**: Flexbox-based layout with file icons, titles, status tags, and action buttons
- **Digest Panels**: Structured display with session coverage, foreign session indicators, and nested content
- **Prose Panels**: Collapsible sections for AI-generated narrative with warning alerts for failed generation
- **Create Dialog**: Modal styling with form inputs, validation feedback, and submission states
- **Tabbed Interface**: Styled tabs for mine/published scopes with proper spacing and alignment

#### Approvals Inbox Styling
- **Entry Layout**: Flexbox-based layout for confirmation entries with provenance metadata
- **Meta Information**: Styled spans for session, owner, and parking time display
- **Decision Attribution**: Visual indicators for who made decisions and when
- **Tabbed Interface**: Styled tabs for pending and history sections with proper spacing
- **Empty States**: Appropriate messaging for pending and history sections
- **Loading States**: Spin indicators during inbox refresh operations

#### Composer Selection Bar Styling
- **Flexbox Layout**: Responsive flexbox layout with proper spacing and alignment
- **Item Organization**: Individual selection items with consistent gap and alignment
- **Label Typography**: Secondary typography styling for selection labels
- **Collapse Behavior**: Intelligent collapse when no models are available
- **Future Extensibility**: Design supports additional per-turn selection controls

#### Model Selector Styling
- **Dropdown Styling**: Compact Ant Design Select with borderless variant for seamless integration
- **Fixed Label**: Secondary typography styling for single-model scenarios
- **Disabled States**: Proper disabled styling when streaming or unauthenticated
- **Responsive Behavior**: Adapts to different screen sizes and composer layouts

**Section sources**
- [global.css:66-119](file://products/operator-portal/web-ui/app/src/theme/global.css#L66-L119)
- [global.css:121-132](file://products/operator-portal/web-ui/app/src/theme/global.css#L121-L132)
- [global.css:234-250](file://products/operator-portal/web-ui/app/src/theme/global.css#L234-L250)
- [global.css:365-407](file://products/operator-portal/web-ui/app/src/theme/global.css#L365-L407)
- [global.css:409-444](file://products/operator-portal/web-ui/app/src/theme/global.css#L409-L444)
- [tokens.ts:1-43](file://products/operator-portal/web-ui/app/src/theme/tokens.ts#L1-L43)

## Enhanced Navigation System

The Operator Portal features a sophisticated navigation system with sectioned organization and role-based visibility controls, implemented using Ant Design components with enhanced mobile responsiveness and a persistent 64px icon rail for consistent layout anchoring.

### Sectioned Navigation Architecture

The navigation system organizes functions into logical sections with automatic visibility management:

#### Control Section
- **Incidents**: Incident triage and management interface with auto-refresh
- **Enhanced Approvals**: Cross-session confirmation inbox for designated approvers with pending count badge and pagination
- **Audit Trail**: Durable audit event inspection with role-based access
- **Permissions**: Live permission matrix display showing role-action relationships

#### Workspace Section  
- **Tools**: Read-only catalog of available tools with filtering capabilities
- **Skills**: Browseable inventory of available skills with source and tag filtering
- **Settings**: Read-only Session & Identity panel with operational insights
- **Operations Documents**: Shift summary management with session selection, document creation, publishing, and viewing

#### Automatic Section Visibility
- **Dynamic Hiding**: Sections automatically hide when all their entries are hidden due to role restrictions
- **Role-Based Filtering**: Individual navigation items hidden based on user roles and authentication status
- **Server-Side Enforcement**: All navigation items enforce server-side permissions on every request

### Enhanced Mobile Navigation Implementation

The mobile navigation system provides seamless cross-device experience with a persistent 64px icon rail and enhanced drawer navigation:

#### Persistent 64px Icon Rail
- **Fixed Width**: Maintains consistent layout anchoring across all views with 64px width
- **Icon-Only Mode**: Shows only icons with tooltips when sidebar is collapsed
- **Consistent Anchoring**: Ensures all views align uniformly to the right of the rail
- **Menu Group Titles**: Hidden in collapsed state with visual dividers instead of clipped text

#### useNarrowViewport Hook
- **Responsive Breakpoint Detection**: Custom hook that monitors viewport width changes at 992px breakpoint
- **Media Query Integration**: Uses window.matchMedia for efficient breakpoint detection
- **Event Listener Management**: Proper cleanup of media query event listeners
- **State Management**: Maintains narrow viewport state for conditional rendering

#### Drawer Integration
- **Off-Canvas Navigation**: Slide-in sidebar from left side of screen
- **Proper Width**: 260px width matching desktop sidebar for consistency
- **Close Behavior**: Automatic closing on navigation item selection
- **Backdrop Support**: Semi-transparent backdrop for focus indication

#### Dynamic Accessibility
- **Context-Aware ARIA Labels**: Labels change based on viewport state and sidebar status
- **Screen Reader Support**: Proper labeling for "Open navigation", "Show navigation", and "Hide navigation"
- **Keyboard Navigation**: Full keyboard operability with visible focus indicators

#### Content Spacing Management
- **.view-container-inset Class**: Applied when sidebar is absent or folded for proper content spacing
- **Automatic Padding**: 64px left padding for non-flush views to accommodate navigation trigger
- **Chat View Handling**: Specific padding for session-panel-header in flush chat views
- **Brand Block Adjustment**: Proper padding for sidebar brand block to avoid overlap

### Navigation Implementation Details

The React implementation uses Ant Design Menu with dynamic item generation and enhanced accessibility:

#### Menu Configuration
```typescript
const items = useMemo<MenuProps["items"]>(() => {
  const entries: MenuProps["items"] = [
    { key: "chat", icon: <MessageOutlined />, label: "Chat" },
  ];
  // Control section items...
  // Workspace section items...
  return entries;
}, [roles, signedIn]);
```

#### Dynamic ARIA Labels
- **Narrow Viewport**: "Open navigation" when drawer is closed
- **Desktop Collapsed**: "Show navigation" when sidebar is collapsed
- **Desktop Expanded**: "Hide navigation" when sidebar is expanded
- **Context-Aware**: Labels automatically update based on current state

#### Role-Based Access Control

The navigation system implements comprehensive role-based access control:

#### Required Roles for Different Functions
- **Enhanced Approvals**: Requires "approver" or "platform-admin" roles for inbox access with pagination support
- **Operations Documents**: Available to users with document access permissions for shift summary management
- **Audit Trail**: Requires "auditor" or "platform-admin" roles
- **Incidents**: Requires specific incident-related roles
- **Permissions/Tools/Skills**: Available to all authenticated users
- **Settings**: Available to all users for operational insights
- **Chat**: Available to all users regardless of role

#### Client-Side and Server-Side Enforcement
- **Client-Side Gating**: Immediate visual feedback by hiding unauthorized navigation items
- **Server-Side Validation**: Gateway re-enforces permissions on every API request
- **Graceful Fallback**: Users automatically redirected to chat if they lose required roles

**Updated** The navigation system now provides enhanced mobile experience with a persistent 64px icon rail that maintains consistent layout anchoring across all views, improved responsive behavior with precise 992px breakpoint detection, better menu group title handling in collapsed states with visual dividers instead of clipped text, and enhanced mobile drawer navigation with proper positioning and z-index management. The navigation system maintains accessibility across all views while providing consistent layout anchoring through dynamic aria-labels and proper content spacing management. **Enhanced Feature**: The Enhanced Approvals view is integrated into the control section with pending count badge for decider roles, providing cross-session confirmation management capabilities with client-side pagination and improved arrival presentation. **Enhanced Feature**: The Operations Documents view has been moved to the workspace section, reflecting its semantic positioning as daily workflow artifacts for shift summary management with session selection, document creation, publishing, and viewing capabilities. **Enhanced Feature**: The Settings view is also integrated into the workspace section, providing read-only access to identity information, session details, and platform metadata for operational awareness.

**Section sources**
- [App.tsx:56-70](file://products/operator-portal/web-ui/app/src/App.tsx#L56-70)
- [App.tsx:288-307](file://products/operator-portal/web-ui/app/src/App.tsx#L288-L307)
- [App.tsx:334-357](file://products/operator-portal/web-ui/app/src/App.tsx#L334-L357)
- [global.css:66-119](file://products/operator-portal/web-ui/app/src/theme/global.css#L66-L119)
- [roles.ts:1-34](file://products/operator-portal/web-ui/app/src/roles.ts#L1-L34)

## Role-Gated Audit Trail System

The Operator Portal implements a comprehensive audit trail system with role-based access control and advanced filtering capabilities, integrated into the React component architecture.

### Role-Based Access Control

The audit trail view is protected by role-based access control:

- **Required Roles**: Users must have either "auditor" or "platform-admin" roles to access audit trail
- **Client-Side Gating**: Audit trail navigation item hidden unless user has required roles
- **Server-Side Enforcement**: Gateway re-enforces audit:read permission on every request
- **Automatic View Switching**: If user loses required roles, automatically switches back to chat view

### Audit Trail Interface

The AuditView component provides comprehensive event inspection capabilities:

#### Filter Toolbar
- **Username Filter**: Search by specific username
- **Event Type Filter**: Filter by event types (tool_invoked, policy_decision, token_exchange, etc.)
- **Service Filter**: Filter by originating service (tool-gateway, platform-gateway, identity-service)
- **Date Range Filters**: Since and until datetime-local inputs for temporal filtering
- **Refresh Button**: Reload current filtered results

#### Event Display
- **Table Format**: Clean tabular display with columns for timestamp, type, service, outcome, actor, and request ID
- **Expandable Details**: Click any row to reveal full event envelope JSON
- **Status Indicators**: Color-coded outcomes with negative outcomes highlighted in red
- **Pagination**: Cursor-based pagination with "Load more" button for large result sets

#### Data Management
- **Lazy Loading**: Events loaded only when audit view is activated
- **State Preservation**: Filter selections and loaded data preserved during navigation
- **Error Handling**: Graceful error display with user-friendly messages
- **Loading States**: Visual feedback during data loading operations

### Security Considerations

The audit trail system implements multiple security layers:

- **Role Verification**: Client-side role checking before rendering audit view
- **Server-Side Validation**: Gateway enforces audit:read permission on all requests
- **Request Context**: Includes x-request-id for traceability
- **Authentication Required**: All audit requests require valid authentication tokens

**Section sources**
- [AuditView.tsx:1-250](file://products/operator-portal/web-ui/app/src/views/audit/AuditView.tsx#L1-L250)
- [App.tsx:62-91](file://products/operator-portal/web-ui/app/src/App.tsx#L62-L91)
- [roles.ts:4-12](file://products/operator-portal/web-ui/app/src/roles.ts#L4-L12)

## Tier-Aware HITL Confirmation Card System

The Operator Portal includes comprehensive Human-in-the-Loop (HITL) confirmation bridging that allows operators to approve or deny ASK-gated tool executions directly within the chat interface, implemented with React components and hooks. The system now features tier-aware badge display that clearly distinguishes between operator confirmations and approver-required scenarios, with proper turn anchoring for accurate historical context.

### Tier-Aware Confirmation Architecture

The enhanced HITL system bridges the gap between automated agent tool execution and human oversight with intelligent tier detection:

#### Confirmation Tier Detection
- **Tool Context Analysis**: Automatically analyzes tool type, parameters, and execution context to determine confirmation tier
- **Risk Assessment**: Evaluates operation sensitivity and potential impact for appropriate tier classification
- **Role Requirement Mapping**: Maps confirmation tiers to required user roles and permissions
- **Badge Generation**: Creates appropriate visual indicators (operator confirmation vs approver required)

#### Tier Classification Logic
- **Operator Confirmation**: Standard operator-level actions requiring basic operator permissions
- **Approver Required**: Elevated actions requiring specialized approver permissions beyond operator scope
- **Contextual Intelligence**: Considers tool category, parameter values, and execution environment for tier determination
- **Dynamic Badge Display**: Shows appropriate badge based on determined confirmation tier

#### Confirmation Registry Management
- **In-Memory Storage**: Per-process confirmation registry manages pending confirmations with unique IDs
- **TTL Expiry**: Confirmations expire after a timeout period, preventing indefinite parking
- **Single-Flight Claims**: Atomic claim mechanism prevents duplicate confirmations
- **Owner Verification**: Ensures only the original requester can confirm their own parked calls

#### Stream Continuation Handling
- **SSE Resume**: The confirm endpoint returns a resumed SSE stream containing the remainder of the parked reply
- **Evidence Context Preservation**: Tool frames from the resumed reply attach to the same turn group as the original request
- **Nested Confirmations**: Supports chained confirmations where a resumed turn may park again on another ASK-gated tool
- **Error Recovery**: Handles mid-stream errors, timeouts, and connection issues gracefully

### Enhanced Confirmation Card Interface

The inline confirmation card provides a focused interface for reviewing and deciding on tool executions with tier-aware visual indicators:

#### Tier-Specific Badge Display
- **Operator Confirmation Badge**: Blue tag indicating standard operator-level confirmation required
- **Approver Required Badge**: Red tag indicating elevated approval permissions needed beyond operator scope
- **Visual Distinction**: Clear color coding helps users understand confirmation complexity and required permissions
- **Contextual Information**: Badge text provides immediate understanding of confirmation requirements

#### Card Components
- **Warning Header**: Yellow-bordered card with "Tool confirmation required" title and tier-specific status badge
- **Message Display**: Clear explanation of why confirmation is needed with tier context
- **Tool Details**: Expandable sections showing tool name and parameters for review
- **Action Buttons**: Prominent Approve (green) and Deny (red) buttons for authorized users
- **Status Line**: Real-time status updates showing "Approving…"/"Denying…" during processing

#### Role-Based Visibility
- **Authorized Roles**: platform-admin, approver, operator, developer roles can see and interact with confirmation buttons
- **Read-Only Access**: Other roles see a message indicating they cannot approve or deny tool confirmations
- **Server-Side Enforcement**: Gateway validates chat:confirm permission on every confirmation request

#### Visual Feedback
- **Pending State**: Yellow border and pulsing status indicator while awaiting decision
- **Processing State**: Disabled buttons with "Approving…"/"Denying…" status during decision processing
- **Resolved State**: Border changes to standard gray, buttons disabled, final status displayed
- **Error Handling**: Clear error messages for network failures, timeouts, and permission issues

### Turn-Anchored Confirmation System (SPEC-033)

The confirmation card system continues to implement proper turn anchoring to provide accurate historical context for multi-park sessions:

#### Per-Exchange Anchoring Logic
- **Turn Index Validation**: Records with valid turn_index values anchor to their specific parking turn
- **Legacy Fallback**: Records without usable turn_index (pre-delivery or out-of-range) fall back to newest turn anchoring
- **Synthetic Turn Creation**: Empty or unrecoverable transcripts get synthetic turns to keep parked requests visible
- **Pending Record Handling**: Pending confirmation cards properly set confirmationPending flag on their anchored turn

#### Historical Accuracy
- **Multi-Park Sessions**: Each confirmation card renders under the exchange that parked it, not stacked under newest turn
- **Decision Attribution**: Decided cards from earlier rounds remain visible at their original location
- **Context Preservation**: Operators can see the complete history of confirmation decisions in chronological order

#### Backward Compatibility
- **Additive Field**: turn_index is nullable and optional, preserving existing functionality
- **Fallback Behavior**: Pre-delivery records maintain current behavior by anchoring to most recent turn
- **Test Coverage**: Comprehensive tests validate per-exchange anchoring, pending anchoring, and legacy fallback scenarios

### Backend Integration

The HITL system integrates seamlessly with the agent-platform confirmation registry:

#### Confirmation Lifecycle
1. **Registration**: When kernel parks a reply, agent-platform registers the confirmation in memory with unique ID
2. **Frontend Rendering**: Portal receives confirmation_request frame and renders inline approval card
3. **Decision Processing**: User clicks Approve/Deny, portal sends decision to gateway
4. **Registry Claim**: Agent-platform claims the confirmation atomically to prevent duplicates
5. **Reply Resume**: Kernel resumes parked reply with decision applied (approve executes tools, deny reports refusal)
6. **Stream Continuation**: Resumed reply streams back to portal, updating evidence and completing the interaction

#### Security and Safety
- **Deny-by-Default**: All tool executions require explicit approval unless on auto-allow list
- **Owner Verification**: Only the original requester can confirm their own parked calls
- **TTL Protection**: Expired confirmations fail closed rather than auto-executing
- **Audit Trail**: All confirmation decisions are recorded in durable audit events

### User Experience Benefits

The enhanced HITL confirmation system provides several operational benefits:

#### Enhanced Safety
- **Human Oversight**: Operators can review potentially risky tool executions before they run
- **Contextual Information**: Full tool parameters visible for informed decision-making
- **Immediate Feedback**: Real-time status updates during decision processing
- **Tier Awareness**: Clear indication of confirmation complexity and required permissions

#### Improved Workflow
- **Inline Interface**: No need to switch contexts or navigate away from chat
- **Streamlined Process**: Single-click approval or denial with immediate effect
- **Evidence Integration**: Decisions appear alongside other tool execution evidence
- **Visual Clarity**: Tier-specific badges help users quickly understand confirmation requirements

#### Operational Transparency
- **Clear Status**: Visual indicators show confirmation state throughout the process
- **Audit Trail**: All decisions recorded with timestamps and user context
- **Error Recovery**: Graceful handling of network issues and timeouts
- **Permission Guidance**: Clear indication of what permissions are needed for different confirmation types

**Updated** The HITL confirmation system represents a significant enhancement to the operator portal, enabling safe automation of complex workflows while maintaining human oversight for critical operations. The React implementation provides better state management and component reusability. Backend API v6 schema compliance ensures proper risk level handling in pending calls. **Critical Enhancement**: The tier-aware badge display system continues to clearly distinguish between operator confirmations and approver-required scenarios, improving user experience and workflow clarity with appropriate visual indicators and role-based permission validation. **v0.15.0 Enhancement**: The confirmation card system continues to implement proper turn anchoring based on SPEC-033, ensuring each confirmation card renders under the exchange that parked it rather than stacking all cards under the newest turn, providing accurate historical context for multi-park sessions with comprehensive test coverage for per-exchange anchoring, pending anchoring, and legacy fallback scenarios.

**Section sources**
- [ChatView.tsx:218-297](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L218-L297)
- [useChatStream.ts:284-372](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L284-L372)
- [transcript.ts:137-165](file://products/operator-portal/web-ui/app/src/chat/transcript.ts#L137-L165)
- [global.css:409-444](file://products/operator-portal/web-ui/app/src/theme/global.css#L409-L444)
- [roles.ts:35-35](file://products/operator-portal/web-ui/app/src/roles.ts#L35-L35)
- [ConfirmationCard.test.tsx:56-67](file://products/operator-portal/web-ui/app/src/chat/__tests__/ConfirmationCard.test.tsx#L56-L67)

## Approvals Inbox and Cross-Session Management

The Operator Portal now includes a significantly enhanced Approvals inbox that provides designated approvers with a cross-session queue of parked confirmations plus decision history, implementing SPEC-031 R-5 requirements for persistent confirmation management with improved arrival presentation and pagination support.

### Enhanced Approvals Inbox Architecture

The approvals inbox provides a dedicated interface for managing parked confirmations across multiple sessions with real-time polling, decision attribution, and client-side pagination:

#### Cross-Session Discovery
- **GET /api/v1/approvals/inbox**: Fetches confirmation records for the authenticated user's approved roles
- **Metadata-Only Posture**: Returns session metadata, owner information, and pending calls without exposing transcript text
- **30-Day History Window**: Includes both pending confirmations and historical decisions within the last 30 days
- **Most Recent First**: Results ordered by recency with pending items appearing first

#### Enhanced Real-Time Polling System
- **30-Second Interval**: Automatic polling every 30 seconds to keep inbox synchronized with backend state
- **Window Focus Refresh**: Additional refresh when browser window gains focus to ensure up-to-date information
- **Shared Inbox State**: Single poll instance shared between sidebar badge and view to prevent duplicate requests
- **Error Resilience**: Maintains last good list on transient failures while displaying error messages

#### Client-Side Pagination
- **10 Entries Per Page**: History tab displays 10 confirmation records per page for improved readability
- **Page Clamping**: Pages automatically clamp when list shrinks due to retention eviction
- **Pagination Controls**: Ant Design Pagination component with proper accessibility attributes
- **History Organization**: Separate tabs for pending items and paginated historical decisions

#### Enhanced Arrival Presentation
- **Visual Feedback**: Better indication of when decisions are processed and applied
- **Status Updates**: Clear status indicators during decision processing
- **Race Condition Handling**: Structured 409 responses flip losing cards to winner's outcome instead of showing errors
- **Decision Attribution**: Enhanced display of who made decisions and when

#### Decision Attribution and Race Resolution
- **Decider Tracking**: Records who made each decision with timestamp and decision value
- **Race Condition Handling**: Structured 409 responses with winner's outcome for concurrent approval attempts
- **Already Resolved Detection**: Automatically flips losing cards to winner's outcome instead of showing errors
- **Status Synchronization**: Local state updates immediately followed by server reconciliation

### Enhanced Inbox Entry Components

Each confirmation entry displays provenance metadata and the shared confirmation card interface with improved presentation:

#### Provenance Metadata
- **Session Identification**: Shows session title (or ID fallback) and owner user ID
- **Parking Time**: Displays relative time since confirmation was parked using dayjs formatting
- **Decision Attribution**: For resolved items, shows who decided and when the decision was made

#### Shared Confirmation Card Integration
- **Reuse of ConfirmationCardView**: Leverages existing card component for consistent UI across chat and inbox
- **Decision Surface**: Pending items show Approve/Deny buttons for authorized deciders
- **Read-Only Display**: Resolved items show decision outcome without modification capability
- **Busy State Management**: Prevents duplicate submissions during decision processing

### Enhanced Role-Based Access Control

The approvals inbox is restricted to designated approver roles with comprehensive security enforcement:

#### Client-Side Role Checking
- **APPROVAL_DECIDER_ROLES**: Requires "approver" or "platform-admin" roles for inbox access
- **Navigation Visibility**: Approvals menu item hidden for users without required roles
- **Sidebar Badge**: Pending count badge only shown for authorized users

#### Server-Side Policy Enforcement
- **approvals:list Action**: Gateway enforces policy action on every inbox request
- **Cross-Session Access**: Authorized approvers can view confirmations from any session, not just owned sessions
- **Audit Logging**: All inbox access logged with user identity and role information

### Enhanced Data Models and Types

The approvals system uses well-defined TypeScript interfaces for type safety:

#### ConfirmationRecord Interface
- **confirm_id**: Unique identifier for the confirmation
- **session_id**: Associated session identifier
- **owner_user_id**: Username of the session owner
- **session_title**: Enriched session title (inbox-only field)
- **pending_calls**: Array of tool calls requiring approval with parameters and risk levels
- **status**: Current state (pending, approved, denied, expired)
- **decider_user_id**: Who made the decision (for resolved items)
- **decision**: Value of the decision (approve/deny)
- **decided_at**: Timestamp when decision was made

#### Enhanced Inbox State Management
- **records**: Array of confirmation records from the inbox API
- **loading**: Boolean flag for initial loading state
- **error**: Error message for API failures
- **pendingCount**: Computed count of pending confirmations for sidebar badge
- **busyConfirmId**: Currently being processed confirmation ID
- **refresh**: Manual refresh function
- **decide**: Decision submission function
- **historyPage**: Current page for history pagination
- **historyPages**: Total number of pages for history display

### Enhanced User Experience Features

The approvals inbox provides an intuitive interface for managing confirmations with improved arrival presentation:

#### Visual Organization
- **Pending Section**: Primary section showing confirmations awaiting decisions
- **Paginated History Section**: Secondary section showing resolved confirmations from last 30 days with pagination
- **Empty States**: Helpful messaging when no confirmations exist in either section
- **Loading Indicators**: Spin components during data fetching operations

#### Interactive Elements
- **Manual Refresh**: Button to force refresh of inbox data
- **Decision Buttons**: Prominent Approve (green) and Deny (red) buttons for pending items
- **Status Indicators**: Visual feedback during decision processing
- **Error Alerts**: Warning alerts for API failures and authentication issues
- **Pagination Controls**: Navigation between history pages with proper accessibility

### Testing and Quality Assurance

Comprehensive test coverage ensures reliability of the enhanced approvals functionality:

#### Test Scenarios
- **Rendering Priority**: Verifies pending items appear before history items
- **Provenance Display**: Confirms session, owner, and timing information is shown correctly
- **Decision Attribution**: Tests that resolved items show who made decisions and when
- **Race Condition Handling**: Validates 409 responses flip cards to winner's outcome
- **Role-Based Access**: Tests that non-deciders cannot access the inbox
- **Polling Behavior**: Verifies 30-second polling intervals and window focus refresh
- **Pagination Testing**: Validates client-side pagination works correctly for history display

#### Mock Environment Setup
- **Auth Context Mocking**: Simulates user authentication and role information
- **API Mocking**: Stubs inbox API calls and stream operations
- **Stream Error Simulation**: Tests various error conditions including network failures and authentication errors

**Updated** The enhanced approvals inbox represents a significant improvement to the operator portal, providing designated approvers with comprehensive cross-session confirmation management capabilities including improved arrival presentation, client-side pagination for decision history, and enhanced race condition handling. The implementation includes real-time polling with 30-second intervals, decision attribution with detailed provenance metadata, race-resilient resolution semantics for concurrent approval attempts, and comprehensive role-based access control. **Critical Enhancement**: The inbox maintains metadata-only posture to preserve privacy boundaries while providing sufficient information for informed decision-making. **Critical Enhancement**: Race condition handling ensures exactly one execution per confirmation with structured outcomes for losing parties. **New Feature**: Client-side pagination improves usability when managing large volumes of confirmation records with 10 entries per page in the history tab.

**Section sources**
- [ApprovalsView.tsx:1-388](file://products/operator-portal/web-ui/app/src/views/control/ApprovalsView.tsx#L1-L388)
- [approvals.ts:1-20](file://products/operator-portal/web-ui/app/src/api/approvals.ts#L1-L20)
- [sessions.ts:44-69](file://products/operator-portal/web-ui/app/src/api/sessions.ts#L44-L69)
- [roles.ts:31-35](file://products/operator-portal/web-ui/app/src/roles.ts#L31-L35)
- [App.tsx:101-137](file://products/operator-portal/web-ui/app/src/App.tsx#L101-L137)
- [ApprovalsView.test.tsx:1-242](file://products/operator-portal/web-ui/app/src/views/__tests__/ApprovalsView.test.tsx#L1-L242)

## Operations Document Repository

The Operator Portal now includes a complete Operations Document Repository providing shift summary creation, management, and viewing capabilities for operational documentation and cross-session analysis.

### Document Repository Architecture

The Documents view implements a comprehensive interface for managing immutable shift snapshots with session coverage and optional prose generation:

#### Shift Summary Creation
- **Modal Dialog Interface**: CreateShiftSummaryDialog with label input, session selection, and prose options
- **Session Selection**: Multi-select dropdown for own sessions plus text input for foreign session IDs
- **Validation Rules**: Label required, minimum one session, maximum 20 sessions, foreign session permission checks
- **Prose Generation**: Optional AI-generated narrative summary with included/failed/not_requested states

#### Document Management Interface
- **List View**: Tabbed interface for Mine/Published scopes with document cards showing status, provenance, and actions
- **Action Buttons**: View, Publish (for owner drafts), Delete (for owner documents) with appropriate permissions
- **Status Tags**: Document type, state (draft/published), and creation timestamps with relative time formatting
- **Empty States**: Helpful messaging for no documents in either scope

#### Digest Rendering System
- **Structured Display**: DigestPanel shows generated timestamp, requester information, and session coverage
- **Session Coverage**: DigestSessionEntry displays individual session data with foreign session indicators
- **Flexible Rendering**: DigestValue component handles primitives, arrays, and objects with recursive depth support
- **Foreign Session Handling**: Purple tag indicates metadata-only access for foreign sessions

#### Publishing Workflow
- **One-Way Operation**: Publish transitions draft to published state with duplicate protection
- **Status Management**: Success/error handling with appropriate user feedback
- **Scope Refresh**: Automatic refresh after publish operations to update document lists
- **Permission Enforcement**: Owner-only publishing with appropriate error handling

### API Client Integration

The document repository integrates with backend services through a dedicated API client:

#### Document Operations
- **listDocuments**: Fetch documents with scope filtering (mine/published)
- **createDocument**: Create shift summary drafts with session coverage and prose options
- **publishDocument**: Publish draft documents with duplicate protection
- **deleteDocument**: Remove documents with confirmation dialogs
- **getDocument**: Retrieve individual document details for viewing

#### Data Models
- **OperationDocument**: Complete document structure with digest, provenance, and prose fields
- **DocumentProvenanceSession**: Session coverage information with owner/foreign distinction
- **DocumentCreateRequest**: Payload for creating new shift summaries
- **DocumentListResponse**: Paginated response format for document listings

### User Experience Features

The document repository provides an intuitive interface for operational documentation:

#### Visual Organization
- **Document Cards**: Flexbox-based layout with file icons, titles, status tags, and action buttons
- **Digest Panels**: Structured display with session coverage, foreign session indicators, and nested content
- **Prose Panels**: Collapsible sections for AI-generated narrative with warning alerts for failed generation
- **Tabbed Interface**: Styled tabs for mine/published scopes with proper spacing and alignment

#### Interactive Elements
- **Create Dialog**: Modal with form inputs, validation feedback, and submission states
- **Publish Actions**: One-click publishing with success/error feedback
- **Delete Confirmation**: Danger-styled delete buttons with confirmation dialogs
- **View Drawer**: Side panel for detailed document inspection with digest and prose sections

### Security and Permissions

The document repository implements comprehensive security measures:

#### Access Control
- **Owner Restrictions**: Only document owners can publish or delete their documents
- **Foreign Session Limits**: Foreign session inclusion requires designated approver permissions
- **Cross-Owner Reads**: Published documents readable by users with document access permissions
- **Audit Trail**: All document operations logged with user identity and timestamps

#### Data Protection
- **Immutable Snapshots**: Shift summaries capture immutable session state at creation time
- **Metadata-Only Foreign Access**: Foreign sessions contribute only metadata, not full transcript data
- **Validation Enforcement**: Server-side validation for session IDs, labels, and content constraints
- **Error Handling**: Graceful error handling with user-friendly messages for various failure scenarios

**New Feature**: The Operations Document Repository provides complete shift summary management with session selection, document creation, publishing, and viewing capabilities for operational documentation. The implementation includes modal dialog interfaces, tabbed document lists, structured digest rendering, and comprehensive permission enforcement for cross-session analysis and collaborative documentation workflows.

**Updated** The Documents view has been moved from the Control group to the Workspace section, reflecting its semantic positioning as daily workflow artifacts for shift summary management. The enhanced document fetching workflow now uses separate API calls for full details with AbortController support for improved loading states and better user experience during document detail retrieval.

**Section sources**
- [DocumentsView.tsx:1-597](file://products/operator-portal/web-ui/app/src/views/control/DocumentsView.tsx#L1-L597)
- [documents.ts:1-89](file://products/operator-portal/web-ui/app/src/api/documents.ts#L1-L89)

## Authentication and Security

The Operator Portal implements comprehensive authentication and security features using OpenID Connect (OIDC) protocol with automatic session management, built with React Context for state management.

### OIDC Integration Flow

The authentication system supports complete OIDC flows:

- **Login Initiation**: Redirect to identity provider with PKCE flow
- **Code Exchange**: Secure authorization code exchange for tokens
- **State Validation**: CSRF protection with state parameter verification
- **Session Storage**: Secure token storage in sessionStorage

### Token Management

Automatic token lifecycle management ensures seamless user experience:

- **Access Token Refresh**: Silent refresh 60 seconds before expiration
- **Refresh Token Handling**: Background renewal of expired sessions
- **Graceful Degradation**: Fallback to cached identity when refresh fails
- **Logout Support**: Complete logout with ID token hint

### Security Context

Enhanced security measures protect against common vulnerabilities:

- **Non-root Execution**: Container runs as unprivileged user (UID 101)
- **Security Context**: Proper Kubernetes security policies applied
- **CORS Configuration**: Strict cross-origin request policies
- **Content Security**: Safe HTML rendering with proper escaping

### Identity Management

Flexible identity handling supports various scenarios:

- **Authenticated Users**: Full access with verified identity
- **Demo Mode**: Local development with simulated identities
- **Group Membership**: Role-based access control integration
- **Custom Claims**: Support for organization-specific identity attributes

### User Interface Enhancements

The authentication system integrates seamlessly with the React UI:

- **User Card Display**: Avatar with initials, username badge, and role information
- **Login/Logout Buttons**: Icon-only buttons with tooltip support
- **Role-Based Navigation**: Conditional visibility of audit trail based on user roles
- **Session Persistence**: Automatic session restoration on page reload
- **Disabled States**: Proper disabled states for unauthenticated users in session creation controls

**Updated** The authentication system continues to include enhanced disabled states for unauthenticated users, particularly in session creation controls where the "New" button is properly disabled with appropriate tooltips explaining the requirement to sign in first. This improves user experience by providing clear feedback about action availability. **Enhanced Feature**: The Settings view leverages the existing AuthContext to display identity information, roles, and session details in a read-only format for operational awareness. **Enhanced Feature**: The enhanced approvals inbox integrates with the authentication system to provide role-based access control for designated approvers with secure cross-session confirmation management. **Enhanced Feature**: The Operations Document Repository integrates with authentication to provide role-based access control for document creation, publishing, and viewing operations.

**Section sources**
- [AuthContext.tsx:1-110](file://products/operator-portal/web-ui/app/src/auth/AuthContext.tsx#L1-L110)
- [App.tsx:157-195](file://products/operator-portal/web-ui/app/src/App.tsx#L157-L195)
- [ChatView.tsx:414-427](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L414-L427)

## Enhanced Markdown Rendering Interface

The Operator Portal includes a comprehensive markdown rendering engine that transforms plain text into rich, formatted HTML content for display in the chat interface, implemented as a reusable React utility with enhanced XSS prevention and nested list support.

### Enhanced Security Measures

The renderer continues to implement comprehensive XSS prevention measures:

- **Comprehensive HTML Escaping**: All user input is escaped before processing using escapeHtml function with proper quote escaping
- **Protocol Filtering**: JavaScript and data protocols are blocked to prevent malicious link injection
- **Safe Link Handling**: External links open in new tabs with security attributes
- **XSS Prevention**: No raw HTML injection or script execution
- **Content Sanitization**: Removal of potentially dangerous elements

### Enhanced List Rendering System

The markdown renderer now includes sophisticated nested list support with proper ordered/unordered list handling:

#### Nested List Architecture
- **Stack-Based Processing**: Uses a stack-based approach to track list levels and nesting depth
- **Indentation Detection**: Properly handles indentation levels (two spaces per level, tabs count as one level)
- **Mixed List Support**: Supports mixing ordered and unordered lists within the same block
- **Over-Indentation Handling**: Prevents empty wrapper creation when over-indentation occurs
- **Container Selection**: Each level's container follows its first item's marker type

#### Ordered List Improvements
- **Proper Numbering**: Ordered items are now wrapped in `<ol>` tags with correct numbering
- **Marker Preservation**: Maintains numbered list markers throughout the rendering process
- **Nested Ordering**: Supports nested ordered lists within unordered lists and vice versa
- **List Continuity**: Ensures proper list continuation across nested structures

#### Unordered List Enhancements
- **Bullet Point Support**: Proper bullet point rendering for unordered lists
- **Nested Bullets**: Supports nested bullet points with proper indentation
- **Mixed Nesting**: Allows mixing of ordered and unordered lists within the same structure
- **Semantic Markup**: Generates proper semantic HTML structure for accessibility

### Supported Markdown Features

The renderer supports extensive markdown syntax:

- **Headers**: Six levels of heading hierarchy (h1-h6)
- **Text Formatting**: Bold, italic, strikethrough, and emphasis
- **Enhanced Lists**: Ordered and unordered lists with nested support and proper numbering
- **Code Blocks**: Syntax-highlighted code with language specification
- **Inline Code**: Monospace formatting for inline code snippets
- **Links**: Hyperlinks with external target support (restricted to http(s))
- **Blockquotes**: Nested quote blocks with visual styling
- **Tables**: Structured data presentation with proper header/body separation using thead/tbody structure
- **Horizontal Rules**: Visual separators for content organization

### Enhanced Table Rendering

The table rendering system continues to provide proper semantic structure:

- **Header/Body Separation**: Tables are rendered with distinct `<thead>` and `<tbody>` sections
- **Semantic Markup**: Proper use of `<th>` for headers and `<td>` for data cells
- **Single Table Generation**: All table content rendered in one table element instead of disconnected stacked tables
- **Alignment Support**: Proper handling of alignment markers in table separator rows
- **Consistent Structure**: Eliminates the previous issue of header and body being split into separate tables

### Pod Log Quoting Enhancement

The markdown renderer now includes enhanced support for pod log quoting in agent replies:

#### Fenced Code Block Support
- **Log Line Formatting**: Pod logs are now quoted in fenced code blocks with proper line breaks
- **Raw Line Display**: Logs are displayed as raw lines rather than JSON serialization
- **Scrollable Container**: Fenced code blocks are bound to fixed-height scrollable boxes (280px)
- **Line Break Preservation**: Real line breaks are maintained instead of escaped `\n` sequences

#### Improved Log Display
- **Readability Enhancement**: Log excerpts are now much more readable in agent replies
- **Format Preservation**: Original log formatting is preserved for better analysis
- **Performance Optimization**: Fixed-height containers prevent long log excerpts from pushing content out of view
- **Consistent Styling**: Log blocks follow the same styling patterns as other code blocks

### Security Test Coverage

Comprehensive test coverage ensures XSS prevention effectiveness:

- **JavaScript Protocol Blocking**: Tests verify javascript: URLs are refused and rendered as plain text
- **Data Protocol Blocking**: Tests ensure data: URLs are blocked to prevent HTML injection
- **Quote Escape Testing**: Tests validate quote-based attribute breakout prevention
- **Empty Input Handling**: Tests confirm proper handling of empty input strings
- **Table Structure Validation**: Tests verify proper thead/tbody structure in rendered tables
- **List Rendering Tests**: New tests validate nested list rendering, ordered list numbering, and mixed list support

### Performance Optimization

Efficient rendering ensures smooth user experience:

- **Incremental Processing**: Progressive text updates during streaming
- **DOM Manipulation**: Minimal DOM operations for optimal performance
- **Memory Management**: Proper cleanup of temporary objects
- **String Processing**: Optimized regex patterns for fast parsing

### Styling and Theming

Consistent visual presentation across all rendered content:

- **Theme Integration**: Dark theme with accent colors and proper contrast
- **Code Styling**: Monospace fonts with syntax highlighting support
- **Responsive Design**: Adapts to different screen sizes and orientations
- **Accessibility**: Proper semantic markup for screen readers

**Updated** The markdown rendering system now includes enhanced nested list support with proper ordered/unordered list handling, addressing the v0.18.1 live-check findings where indented sub-bullets were previously dropped to literal "- text" paragraphs. The renderer now properly wraps ordered items in `<ol>` tags and supports nested list structures with mixed ordered and unordered lists. **Critical Enhancement**: Pod log quoting improvements now render log excerpts in fenced code blocks with proper line breaks, replacing the previous JSON-serialized string format that was difficult to read. **Enhanced Security**: The escape-first pipeline continues to provide comprehensive XSS prevention while supporting the enhanced list rendering capabilities. **v0.18.1 Enhancement**: The nested list handling addresses the legacy column-0-only passes that dropped indented sub-bullets, providing proper nesting-aware block processing that maintains list integrity and semantic structure.

**Section sources**
- [markdown.ts:1-171](file://products/operator-portal/web-ui/app/src/chat/markdown.ts#L1-L171)
- [ChatView.tsx:351-367](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L351-L367)
- [markdown.test.ts:1-128](file://products/operator-portal/web-ui/app/src/chat/__tests__/markdown.test.ts#L1-L128)
- [global.css:238-313](file://products/operator-portal/web-ui/app/src/theme/global.css#L238-L313)
- [2026-08-26-live-check-patch.md:21-48](file://docs/agentic-aiops-platform/release-notes/2026-08-26-live-check-patch.md#L21-L48)
- [delivery-roadmap.md:354-360](file://docs/agentic-aiops-platform/delivery-roadmap.md#L354-L360)

## Real-time Streaming Interface

The Operator Portal implements a sophisticated real-time streaming interface using Server-Sent Events (SSE) for live chat responses and tool execution updates, built with React hooks for state management with enhanced error handling.

### Enhanced Streaming Architecture

The streaming system handles real-time communication efficiently with improved error handling:

- **Server-Sent Events**: Native browser API for server-to-client updates
- **Event Parsing**: Robust JSON event parsing with comprehensive error handling
- **Buffer Management**: Efficient text buffer handling for large responses
- **Connection Recovery**: Automatic reconnection on network interruptions
- **Ownership Handling**: Enhanced stream ownership management during session switches to prevent data contamination

### Stale Session Handling Implementation

The streaming system continues to include comprehensive stale session handling to prevent errors from deleted or expired sessions:

#### 404 Error Detection and Recovery
- **Automatic Detection**: When stream opening encounters 404 errors, recognizes stale session references
- **Session Pointer Dropping**: Automatically clears `sessionIdRef.current` to prevent future attempts with stale session
- **Retry Mechanism**: Retries once without session ID to trigger server-side auto-creation
- **Error Propagation**: If retry also fails, surfaces appropriate error to user with detailed messaging

#### Graceful Fallback Strategies
- **Server Auto-Creation**: Falls back to creating new sessions when stale sessions are detected
- **User Experience**: Maintains conversation flow without interrupting user workflow
- **Error Messaging**: Provides clear feedback when operations fail after retry attempts
- **State Management**: Properly manages session state during retry attempts

### Message Type Handling

Different event types are processed appropriately with refined error handling:

- **Message Delta**: Incremental text updates for streaming responses
- **Tool Calls**: Evidence drawer updates for tool execution via renderToolCall function
- **Tool Results**: Completion notifications with status and data via renderToolResult function
- **Stream Completion**: Finalization signals for response ending
- **Confirmation Requests**: HITL approval cards for ASK-gated tool executions
- **Confirmation Results**: Status updates for confirmation decisions
- **Error Types**: Specific handling for network errors, authentication failures, and streaming interruptions

### User Experience Features

Intuitive streaming interface enhances usability:

- **Sticky Smart-scroll**: Intelligent scrolling that respects user reading position
- **Placeholder Handling**: Graceful handling of empty or delayed responses
- **Error Display**: User-friendly error messages for connection issues
- **Loading States**: Visual feedback during streaming operations

### Performance Considerations

Optimized for high-frequency updates:

- **Batch Processing**: Efficient event batching for better performance
- **DOM Updates**: Minimal DOM manipulation for smooth animations
- **Memory Management**: Proper cleanup of streaming resources
- **Network Efficiency**: Connection reuse and request optimization

### Enhanced Streaming Features

The React implementation includes additional streaming enhancements:

- **Thinking Indicator**: Animated placeholder shown while agent processes requests
- **Sidebar Pulse**: Visual indicator in sidebar showing active streaming state
- **Turn Scoping**: Each conversation turn maintains its own evidence context
- **HITL Integration**: Seamless handling of confirmation requests within streaming flow
- **Error Recovery**: Graceful handling of streaming errors with user feedback
- **Session Management**: Multi-session support with per-session turn caching and ownership validation

**Updated** The streaming interface continues to include enhanced stale session handling with automatic 404 error detection, session pointer dropping, and retry logic that falls back to server-side session auto-creation. These improvements continue to ensure more reliable streaming performance and better user experience when dealing with deleted or expired sessions. **Critical Enhancement**: The live decision sync system continues to integrate with the streaming interface to provide immediate reflection of external decisions without interfering with active streaming operations. **v0.14.1 Patch**: The streaming system continues to work seamlessly with the authoritative `reseedTurns` method to ensure that external decisions are properly synchronized without causing stream interference or cache shadowing issues.

**Section sources**
- [useChatStream.ts:195-282](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L195-L282)
- [transport.ts:75-117](file://products/operator-portal/web-ui/app/src/stream/transport.ts#L75-L117)
- [global.css:134-230](file://products/operator-portal/web-ui/app/src/theme/global.css#L134-L230)

## Evidence Persistence and Replay System

The Operator Portal continues to include comprehensive evidence persistence capabilities that allow operators to view persisted tool execution evidence alongside live conversation data, ensuring complete traceability regardless of whether they observe tool executions in real-time or review them from stored transcripts.

### Evidence Persistence Architecture

The evidence persistence system provides unified rendering of both live streamed and replayed evidence through a consistent transcript-to-turn conversion pipeline:

#### Transcript Conversion Pipeline
- **EvidenceFrame Mapping**: Converts stored evidence frames to live stream frame shapes for consistent rendering
- **Request ID Attachment**: Attaches request IDs from evidence groups to turns for traceability
- **Truncation Marker Handling**: Preserves store-added truncation markers for budget-evicted payloads
- **Turn Index Mapping**: Maps evidence groups to assistant turns using deterministic turn_index values

#### Unified Evidence Rendering
- **Consistent Component Path**: Both live stream and replayed evidence use the same EvidencePanel and EvidenceCard components
- **Prop Parity**: Replayed evidence produces identical props to live stream evidence for consistent visual presentation
- **Metadata Preservation**: Risk levels, execution times, and source systems are preserved in replayed evidence
- **Data Handling**: Full data payloads, summaries, and error information are maintained in replayed evidence

### Evidence Frame Structure

The evidence persistence system uses a structured format for storing and retrieving tool execution evidence:

#### EvidenceTurn Structure
- **turn_index**: Deterministic mapping to assistant turn ordinal (0-based)
- **request_id**: Unique identifier for traceability across the system
- **created_at**: Timestamp for evidence group creation
- **frames**: Array of EvidenceFrame objects containing tool_call and tool_result data

#### EvidenceFrame Schema
- **type**: "tool_call" or "tool_result" frame types
- **call_id**: Unique identifier linking related tool calls and results
- **tool_name**: Name of the executed tool
- **parameters**: Tool invocation parameters
- **status**: Execution status (success, error, denied)
- **evidence**: Metadata including execution time, duration, risk level, and source system
- **data**: Full payload data (may be null if evicted by budget)
- **data_summary**: Summary data when full payload is not available
- **error**: Error information with code and message
- **truncated**: Store-added truncation marker with reason and original character count

### Truncation Marker System

The evidence persistence system continues to include comprehensive truncation markers that clearly indicate when payloads have been evicted due to storage budgets:

#### Truncation Reasons
- **entry_cap**: Individual entry size limits exceeded
- **session_budget**: Total session evidence budget exceeded
- **original_chars**: Character count of original payload before truncation

#### Visual Indicators
- **Always Visible**: Truncation markers are always displayed, never silently dropped
- **Contextual Information**: Shows reason for truncation and original payload size when available
- **Budget Eviction**: Clearly indicates when metadata is preserved but data payload was evicted
- **Preview Indication**: Notes that displayed content is partial when truncation occurs

### Evidence Replay Implementation

The evidence replay system continues to ensure consistency between live streaming and session replay:

#### Transcript-to-Turn Conversion
- **transcriptToTurns Function**: Converts SPEC-022 transcript shape into chat turn model
- **Evidence Attachment**: Attaches persisted evidence groups to corresponding assistant turns
- **Out-of-Range Handling**: Safely handles evidence groups that outlive truncated transcripts
- **Frame Mapping**: Converts stored frames to exact live stream frame shapes for prop parity

#### Turn-Anchored Confirmation Integration (SPEC-033)
- **Per-Exchange Anchoring**: Each confirmation card renders under the specific turn that parked it
- **Turn Index Validation**: Records with valid turn_index values anchor to their parking turn
- **Legacy Fallback**: Records without usable turn_index fall back to newest turn anchoring
- **Synthetic Turn Creation**: Empty or unrecoverable transcripts get synthetic turns to keep parked requests visible

#### Test Coverage
- **Frame Shape Validation**: Ensures replayed frames match live stream frame shapes exactly
- **Truncation Marker Preservation**: Verifies truncation markers are preserved in replayed evidence
- **Out-of-Range Handling**: Tests graceful handling of evidence groups beyond transcript bounds
- **Null Evidence Handling**: Validates behavior when evidence store is unavailable or empty
- **Turn Anchoring Tests**: Comprehensive validation of per-exchange anchoring, pending anchoring, and legacy fallback scenarios

### User Experience Benefits

The evidence persistence system continues to provide several operational benefits:

#### Complete Traceability
- **Consistent Evidence**: Same evidence cards whether observed live or reviewed later
- **Request ID Display**: Traceable request IDs for cross-referencing with audit logs
- **Execution Metadata**: Full execution context including timing, risk levels, and source systems
- **Budget Awareness**: Clear indication of payload limitations and truncation reasons

#### Operational Efficiency
- **Historical Review**: Ability to review past tool executions without relying on live observation
- **Incident Investigation**: Complete evidence context for post-incident analysis
- **Training and Onboarding**: Learning from historical tool execution patterns
- **Compliance Auditing**: Complete audit trail of all tool executions with full context

### Integration with Existing Features

The evidence persistence system continues to integrate seamlessly with existing portal features:

#### Session Management
- **Transcript Availability**: Clear indication when sessions have no recorded transcript yet
- **Evidence Availability**: Separate handling for transcript vs. evidence availability
- **Fallback Behavior**: Graceful degradation when evidence store is unavailable
- **Error Handling**: Non-fatal evidence store failures don't prevent session viewing

#### Chat Interface
- **Unified Rendering**: Evidence panels appear identically for live and replayed evidence
- **Interactive Elements**: Parameter expansion, result data viewing, and error display work consistently
- **Status Indicators**: Success, error, and denied statuses are preserved in replayed evidence
- **HITL Integration**: Confirmation cards work consistently for both live and replayed evidence

**Updated** The evidence persistence system continues to represent a significant enhancement to the operator portal, providing complete traceability of tool executions regardless of whether they were observed live or reviewed from stored transcripts. The system continues to include comprehensive truncation markers that clearly indicate payload limitations, request ID display for cross-referencing, and unified rendering that ensures consistent visual presentation. **Critical Enhancement**: The evidence persistence system continues to ensure operators always understand the completeness of displayed evidence through clear truncation markers and budget eviction indicators. **Enhanced Integration**: The live decision sync system continues to work seamlessly with evidence persistence to ensure external decisions are properly reflected in both live and replayed evidence contexts. **v0.15.0 Enhancement**: The confirmation card system continues to implement proper turn anchoring based on SPEC-033, ensuring each confirmation card renders under the exchange that parked it rather than stacking all cards under the newest turn, providing accurate historical context for multi-park sessions with comprehensive test coverage for per-exchange anchoring, pending anchoring, and legacy fallback scenarios.

**Section sources**
- [transcript.ts:1-204](file://products/operator-portal/web-ui/app/src/chat/transcript.ts#L1-L204)
- [sessions.ts:11-42](file://products/operator-portal/web-ui/app/src/api/sessions.ts#L11-L42)
- [transcript.test.ts:312-365](file://products/operator-portal/web-ui/app/src/chat/__tests__/transcript.test.ts#L312-L365)
- [ChatView.tsx:167-243](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L167-L243)

## Model Selection and Catalog Integration

The Operator Portal continues to include comprehensive model selection capabilities that allow operators to choose between different AI models for their conversations, with dynamic catalog integration and session-based persistence.

### Model Catalog Architecture

The model selection system continues to provide a safe, credential-gated interface for discovering available AI models:

#### Catalog Discovery
- **GET /api/v1/models**: Fetches model catalog with id, label, provider, and default flags
- **Fail-Open UX**: Any catalog fetch failure hides the selector while keeping chat functional
- **Credential Safety**: Gateway only exposes safe model metadata - credentials never leave runtime
- **Sparse Payload Handling**: Normalizes incomplete responses to ensure consistent contract

#### Dynamic Rendering Logic
- **Multiple Models**: Renders Ant Design Select dropdown with all available options
- **Single Model**: Shows fixed secondary label displaying the only available model
- **No Models**: Completely hides the selector when catalog is unavailable or empty
- **Default Selection**: Pre-selects catalog default when no session-specific model is set

### Session Model Persistence

The system continues to maintain model selection context per session for consistent conversation experiences:

#### Session State Management
- **Pinned Model**: Each session can have a specific model pinned to it
- **Fallback Logic**: Sessions without pinned models fall back to catalog default
- **Validation**: Selected models are validated against available catalog entries
- **State Isolation**: Model selection doesn't leak between different sessions

#### Chat Integration
- **Composer Integration**: Model selector embedded in chat composer prefix area
- **Send Context**: Selected model included in chat message metadata
- **Disabled States**: Selector disabled during streaming or when unauthenticated
- **Visual Consistency**: Compact borderless select that matches composer styling

### ModelSelect Component Implementation

The ModelSelect component continues to provide a clean, adaptive interface for model selection:

#### Component Props
- **catalog**: Model catalog data from API (null when unavailable)
- **value**: Currently selected model ID (null for fallback)
- **onChange**: Callback for model selection changes
- **disabled**: Boolean flag for disabled state during streaming

#### Rendering Strategy
- **Catalog Unavailable**: Returns null to hide selector completely
- **Single Model**: Renders Typography.Text with secondary styling as fixed label
- **Multiple Models**: Renders Ant Design Select with dropdown options
- **Accessibility**: Proper ARIA labels for screen readers

### API Client and Testing

The model catalog API client continues to provide robust error handling and type safety:

#### API Contract
- **ModelInfo**: Contains id, label, provider, and default boolean
- **ModelCatalogResponse**: Wraps models array with default model identifier
- **Error Handling**: Throws ApiError on non-2xx responses
- **Normalization**: Ensures models array and default field are always present

#### Test Coverage
- **Network Failures**: Tests verify proper error propagation for offline scenarios
- **HTTP Errors**: Tests confirm ApiError thrown for non-2xx responses
- **Full Catalog**: Tests validate complete catalog payload mapping
- **Sparse Payloads**: Tests ensure normalization of incomplete responses

### User Experience Benefits

The model selection system continues to provide several operational advantages:

#### Flexibility
- **Model Choice**: Operators can choose appropriate models for different tasks
- **Context Preservation**: Model selection persists within conversation sessions
- **Graceful Degradation**: System works even when catalog service is unavailable
- **Visual Clarity**: Clear indication of which model is currently active

#### Operational Efficiency
- **Task-Specific Models**: Use specialized models for different operational needs
- **Consistent Workflows**: Maintain model preferences across conversation sessions
- **Quick Switching**: Easy model changes without leaving the chat interface
- **Safety Assurance**: Credential-safe model discovery without exposing secrets

**Updated** The model selection system continues to represent a significant enhancement to the operator portal, providing flexible AI model choices while maintaining robust fail-open behavior and secure credential handling. The system continues to automatically adapt its presentation based on catalog availability and session context, ensuring operators always have appropriate model selection capabilities. **Critical Enhancement**: The fail-open UX continues to ensure chat functionality remains available even when model catalog services are down, preventing operational disruptions.

**Section sources**
- [ModelSelect.tsx:1-58](file://products/operator-portal/web-ui/app/src/chat/ModelSelect.tsx#L1-L58)
- [models.ts:1-31](file://products/operator-portal/web-ui/app/src/api/models.ts#L1-L31)
- [models.test.ts:1-71](file://products/operator-portal/web-ui/app/src/api/__tests__/models.test.ts#L1-L71)
- [ChatView.tsx:582-599](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L582-L599)
- [ChatView.tsx:643-653](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L643-L653)
- [ChatView.tsx:742-746](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L742-L746)
- [ChatView.tsx:814-819](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L814-L819)

## Composer Selection Bar Architecture

The ComposerSelectionBar component continues to represent a significant architectural improvement to the model selection system, providing an extensible control strip architecture that replaces the inline ModelSelect component from the composer prefix.

### Component Architecture

The ComposerSelectionBar continues to serve as a dedicated mount point for model selection and future per-turn controls:

#### Extensible Control Strip Design
- **Modular Architecture**: Provides a flexible container for multiple selection controls
- **SPEC-024 Compliance**: Implements the architectural requirements for runtime model switching
- **Future-Proof Design**: Designed to accommodate additional per-turn selections as specified in the spec
- **Clean Separation**: Separates selection logic from composer layout concerns

#### TypeScript Interfaces
- **ComposerSelectionBarProps**: Comprehensive interface defining catalog, model, onChange handler, and disabled state
- **Type Safety**: Full TypeScript support with proper prop validation
- **Event Handling**: Well-defined callback interface for model change events
- **Optional Properties**: Flexible disabled property for streaming state management

#### Intelligent Collapse Behavior
- **Catalog Validation**: Automatically collapses when no models are available
- **Fail-Open UX**: Maintains compact composer layout when catalog is unavailable
- **Server-Side Resolution**: Turns resolve to deploy-time default when no selection is presented
- **Graceful Degradation**: Ensures chat functionality remains available regardless of catalog status

### Integration with Chat Interface

The ComposerSelectionBar continues to integrate seamlessly with the existing chat architecture:

#### Sender Footer Slot Integration
- **Footer Placement**: Rendered in the Sender component's footer slot for optimal placement
- **Layout Preservation**: Maintains compact composer height when collapsed
- **Responsive Behavior**: Adapts to different screen sizes and composer configurations
- **State Management**: Proper integration with chat streaming and authentication states

#### Model Selection Flow
- **Catalog Propagation**: Receives model catalog data from parent ChatView component
- **Model State Binding**: Maintains bidirectional binding with selected model state
- **Change Event Handling**: Propagates model selection changes up to parent component
- **Disabled State Management**: Respects streaming and authentication states

### CSS Styling and Layout

The component continues to include comprehensive styling for consistent visual presentation:

#### Flexbox Layout System
- **Responsive Design**: Uses flexbox for flexible layout with proper wrapping
- **Consistent Spacing**: Standardized gaps and padding for visual harmony
- **Alignment Control**: Proper vertical and horizontal alignment of selection items
- **Scalable Architecture**: Supports addition of multiple selection controls

#### Styling Classes
- **composer-selection-bar**: Main container with flexbox layout and padding
- **composer-selection-item**: Individual selection item wrapper with alignment
- **composer-selection-label**: Typography styling for selection labels
- **Future Extensibility**: Design accommodates additional selection types

### Testing and Quality Assurance

The component continues to include comprehensive test coverage ensuring reliability:

#### Test Scenarios
- **Collapse Behavior**: Tests for catalog unavailability and empty catalog scenarios
- **Single Model Display**: Tests for fixed label rendering when only one model exists
- **Multi-Model Selection**: Tests for dropdown rendering and selection propagation
- **Event Handling**: Tests for proper onChange callback invocation

#### Mock Environment Setup
- **Browser API Shims**: Proper mocking of matchMedia and ResizeObserver for testing
- **Component Isolation**: Tests focus on component behavior without external dependencies
- **State Validation**: Comprehensive validation of component state and props

### Architectural Benefits

The ComposerSelectionBar continues to provide several architectural advantages:

#### Modularity Improvements
- **Separation of Concerns**: Isolates selection logic from composer layout concerns
- **Reusability**: Component can be reused across different composer implementations
- **Testability**: Isolated component structure enables comprehensive unit testing
- **Maintainability**: Clear boundaries make the code easier to understand and modify

#### Future Extensibility
- **Per-Turn Selections**: Designed to accommodate additional selection controls as specified in SPEC-024
- **Plugin Architecture**: Extensible design allows for third-party selection controls
- **Configuration Driven**: Can be configured for different selection scenarios
- **Backward Compatibility**: Maintains compatibility with existing chat interface

**Updated** The ComposerSelectionBar component continues to represent a significant architectural improvement that enhances modularity and provides a foundation for future per-turn selection capabilities. The component's intelligent collapse behavior continues to ensure optimal user experience while maintaining the compact composer layout. **Critical Enhancement**: The component's extensible design continues to provide a designated mount point for future per-turn selections as referenced in SPEC-024, ensuring the architecture can evolve with changing requirements.

**Section sources**
- [ComposerSelectionBar.tsx:1-48](file://products/operator-portal/web-ui/app/src/chat/ComposerSelectionBar.tsx#L1-L48)
- [ChatView.tsx:860-877](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L860-877)
- [ComposerSelectionBar.test.tsx:1-115](file://products/operator-portal/web-ui/app/src/chat/__tests__/ComposerSelectionBar.test.tsx#L1-L115)
- [global.css:234-250](file://products/operator-portal/web-ui/app/src/theme/global.css#L234-L250)

## Settings View - Session & Identity Panel

The Settings view continues to serve as a read-only Session & Identity panel (R-6) that provides administrators with essential operational insights by displaying identity information, session details, and platform metadata using existing AuthContext and session workspace state.

### Settings View Architecture

The Settings view continues to serve as a centralized operational dashboard that leverages existing platform components to provide comprehensive situational awareness:

#### Identity Information Display
- **User Identity**: Current authenticated user information including username and roles
- **Role Visualization**: Clear display of assigned roles and permissions
- **Session Context**: Current session identification and status
- **Authentication Status**: Real-time authentication state and token validity

#### Session Details Panel
- **Active Session Information**: Current session ID, creation timestamp, and last activity
- **Session History**: Overview of recent sessions and their status
- **Session Statistics**: Activity metrics and usage patterns
- **Session Management**: Read-only access to session lifecycle information

#### Platform Metadata Display
- **Version Information**: Platform version and build information
- **System Status**: Service health indicators and connectivity status
- **Configuration Overview**: Runtime configuration summary
- **Environment Details**: Deployment environment and infrastructure information

### Integration with Existing Systems

The Settings view continues to seamlessly integrate with existing platform components:

#### AuthContext Integration
- **Identity Data**: Direct access to user identity and role information
- **Session State**: Real-time authentication state and token management
- **Error Handling**: Graceful handling of authentication failures
- **State Synchronization**: Automatic updates when authentication state changes

#### Session Workspace Integration
- **Session Data**: Access to current session information and history
- **Activity Tracking**: Monitoring of session activity and usage patterns
- **Resource Utilization**: Overview of session resource consumption
- **Performance Metrics**: Session performance indicators and statistics

### User Interface Design

The Settings view continues to provide a clean, information-dense interface optimized for operational awareness:

#### Dashboard Layout
- **Information Architecture**: Logical grouping of related operational data
- **Visual Hierarchy**: Clear prioritization of critical information
- **Responsive Design**: Adaptable layout for different screen sizes
- **Accessibility**: Screen reader support and keyboard navigation

#### Interactive Elements
- **Real-Time Updates**: Automatic refresh of dynamic information
- **Expandable Sections**: Detailed information available on demand
- **Search and Filter**: Capabilities for finding specific information
- **Export Options**: Ability to export operational data for analysis

### Operational Benefits

The Settings view continues to provide several key operational advantages:

#### Enhanced Situational Awareness
- **Identity Verification**: Quick confirmation of current user identity and permissions
- **Session Monitoring**: Real-time visibility into active sessions and their status
- **Platform Health**: Immediate assessment of platform status and connectivity
- **Troubleshooting Support**: Essential information for diagnosing operational issues

#### Administrative Efficiency
- **Centralized Information**: Single location for essential operational data
- **Quick Diagnostics**: Rapid access to information needed for troubleshooting
- **Audit Support**: Historical context for operational decisions and actions
- **Compliance Reporting**: Data suitable for compliance and audit requirements

### Security Considerations

The Settings view continues to implement appropriate security measures for sensitive operational data:

#### Data Protection
- **Read-Only Access**: No modification capabilities to prevent accidental changes
- **Information Scoping**: Display of only necessary operational information
- **Authentication Requirements**: Access controlled by existing authentication system
- **Audit Logging**: All access to settings view logged for security monitoring

#### Privacy Controls
- **Personal Data Protection**: Appropriate handling of user identity information
- **Session Privacy**: Protection of sensitive session details
- **Configuration Security**: Careful presentation of platform configuration
- **Compliance Adherence**: Alignment with organizational privacy policies

**Updated** The Settings view restoration as a read-only Session & Identity panel (R-6) continues to provide administrators with essential operational insights without introducing new security risks. The view continues to leverage existing AuthContext and session workspace state to display identity information, session details, and platform metadata in a consolidated dashboard format. **Critical Enhancement**: The read-only nature of the panel continues to ensure that operational awareness does not introduce unintended modification capabilities, maintaining the principle of least privilege while providing comprehensive situational awareness.

**Section sources**
- [App.tsx:94-95](file://products/operator-portal/web-ui/app/src/App.tsx#L94-L95)
- [App.tsx:146-152](file://products/operator-portal/web-ui/app/src/App.tsx#L146-L152)
- [App.tsx:328-330](file://products/operator-portal/web-ui/app/src/App.tsx#L328-L330)
- [AuthContext.tsx:19-27](file://products/operator-portal/web-ui/app/src/auth/AuthContext.tsx#L19-L27)
- [useSessionWorkspace.ts:22-35](file://products/operator-portal/web-ui/app/src/sessions/useSessionWorkspace.ts#L22-L35)
- [version.ts:1-2](file://products/operator-portal/web-ui/app/src/version.ts#L1-L2)

## Skills Integration and Cited Guidance

The Operator Portal continues to include comprehensive skills integration with "Cited guidance" chips that provide enhanced operational visibility when skills.* tools successfully execute, implemented as React components.

### Cited Guidance System Architecture

The cited guidance system continues to automatically detect and display matched skills from successful skills.* tool executions:

#### Skill Detection Logic
- **Success Status Check**: Only processes tool results with "success" status
- **Data Summary Validation**: Ensures data_summary exists and is not truncated
- **Tool Type Recognition**: Handles different skills.* tool types (search, list, get)
- **Entry Extraction**: Extracts skill entries based on tool type (matches, skills, or single data)

#### Chip Generation Process
- **Validation Filtering**: Filters out invalid entries without skill_id
- **Title Generation**: Creates user-friendly titles from skill data or falls back to skill_id
- **Element Creation**: Generates clickable chip elements with proper styling
- **Integration**: Seamlessly integrates with existing evidence card system

#### Visual Presentation
- **Chip Design**: Professional chip styling with borders, background, and proper spacing
- **Typography**: Clear title display with monospace font for skill IDs
- **Layout**: Flexbox-based layout with proper wrapping and gaps
- **Responsiveness**: Adapts to different screen sizes and content lengths

### Implementation Details

The cited guidance system continues to be implemented through React components:

#### Evidence Panel Integration
- **Conditional Rendering**: Only renders for skills.* tools with valid citations
- **Duplicate Prevention**: Prevents multiple rendering of same evidence card
- **Element Construction**: Builds DOM structure for cited guidance section
- **Styling Application**: Applies proper CSS classes for visual presentation

### User Experience Benefits

The cited guidance system continues to provide several operational benefits:

#### Enhanced Traceability
- **Skill Reference**: Clear indication of which team-owned guidance was used
- **Namespaced IDs**: Precise identification of specific skill versions
- **Visual Feedback**: Immediate recognition of skills usage in tool execution

#### Improved Operational Visibility
- **Quick Reference**: At-a-glance understanding of guidance sources
- **Click-to-Copy**: Easy copying of skill IDs for further investigation
- **Contextual Information**: Title and ID displayed together for clarity

### Integration with Existing Features
- **Evidence Cards**: Seamless integration with existing evidence system
- **Turn Scoping**: Proper association with conversation turns
- **Status Tracking**: Works alongside existing success/error/denied status indicators

### Styling and Design

The cited guidance chips continue to follow the established design system:

#### Visual Design
- **Color Scheme**: Uses existing design tokens for consistency
- **Typography**: Mix of regular and monospace fonts for readability
- **Spacing**: Proper margins and padding for visual hierarchy
- **Borders**: Subtle borders to distinguish chips from other content

#### Responsive Behavior
- **Flexbox Layout**: Automatic wrapping for multiple chips
- **Text Overflow**: Ellipsis handling for long skill titles
- **Touch Friendly**: Adequate sizing for mobile interaction
- **Screen Reader Support**: Proper ARIA attributes and semantic markup

**Section sources**
- [ChatView.tsx:132-216](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L132-L216)
- [global.css:295-340](file://products/operator-portal/web-ui/app/src/theme/global.css#L295-L340)

## Permission Matrix and Workspace Resources

The Operator Portal continues to provide comprehensive visibility into platform permissions and workspace resources through dedicated views, integrated into the React component architecture.

### Live Permission Matrix

The PermissionsView component continues to display the current role-action matrix evaluated from the enforced policy bundle:

#### Permission Matrix Features
- **Real-Time Updates**: Fetches latest policy bundle from `/api/v1/policy/matrix` endpoint
- **Role-Action Grid**: Tabular display showing which roles can perform which actions
- **Status Badges**: Visual indicators (allow/deny) for each role-action combination
- **Bundle Metadata**: Shows policy version, source, and scope information

#### Implementation Details
- **Automatic Loading**: Loads on view activation to ensure fresh data
- **Error Handling**: Graceful error display with user-friendly messages
- **Status Updates**: Shows count of roles and actions evaluated
- **Server-Side Enforcement**: Gateway re-enforces policy:read permission on every request

### Tools Catalog

The ToolsView component continues to provide a read-only inventory of available tools in the workspace:

#### Tools Catalog Features
- **Complete Tool Listing**: Displays all registered tools with name, description, category, and risk level
- **Empty State Handling**: Shows helpful message when no tools are available
- **Status Indicators**: Shows total count of registered tools
- **Read-Only Access**: No modification capabilities, ensuring safety
- **Confirmation Requirements**: Shows whether confirmation is required or auto-allowed based on risk level

#### Data Source
- **API Endpoint**: `/api/v1/tools` returns array of tool objects
- **Field Mapping**: Maps tool properties to table columns (name, description, category, risk_level)
- **Server-Side Validation**: Gateway enforces tools:list permission on every request

### Skills Inventory

The SkillsView component continues to offer browseable access to available skills with filtering capabilities:

#### Skills Inventory Features
- **Comprehensive Listing**: Shows skill title, source, tags, version, and last updated timestamp
- **Advanced Filtering**: Supports filtering by source and tag parameters
- **Pagination Support**: Handles large skill inventories with limit parameter
- **Total Count Display**: Shows both filtered results and total available skills

#### Filtering System
- **Source Filter**: Filter skills by their source identifier
- **Tag Filter**: Filter skills by associated tags
- **Query Building**: Dynamically constructs URL parameters based on filter values
- **Auto-Refresh**: Re-loads data when filter values change

### Workspace Resource Discovery

The combined workspace views continue to provide comprehensive resource discovery capabilities:

#### Unified Resource View
- **Centralized Access**: All workspace resources accessible from sidebar navigation
- **Consistent Interface**: Uniform table-based display across tools and skills
- **Status Feedback**: Clear status messages indicating resource availability
- **Role-Based Access**: Sign-in required for workspace resource views

#### Security Model
- **Authentication Required**: All workspace views require signed-in session
- **Server-Side Enforcement**: Gateway validates permissions on every request
- **Read-Only Operations**: All workspace views are read-only for safety
- **Policy Compliance**: Views respect current policy bundle and role assignments

**Updated** The workspace resource discovery system continues to provide operators with comprehensive visibility into platform capabilities, enabling better understanding of available tools and skills while maintaining strict security boundaries through role-based access control. Backend API v6 schema compliance continues to ensure proper risk level handling in pending calls. **Enhanced Feature**: The Settings view continues to complement these workspace resources by providing operational context and identity information that helps administrators understand the current operational state. **Enhanced Feature**: The enhanced approvals inbox continues to provide cross-session confirmation management capabilities for designated approvers with role-based access control. **Enhanced Feature**: The Operations Document Repository continues to provide operational documentation capabilities that complement workspace resource discovery with shift summary management and cross-session analysis.

**Section sources**
- [PermissionsView.tsx:1-99](file://products/operator-portal/web-ui/app/src/views/control/PermissionsView.tsx#L1-L99)
- [ToolsView.tsx:1-88](file://products/operator-portal/web-ui/app/src/views/control/ToolsView.tsx#L1-L88)
- [SkillsView.tsx:1-132](file://products/operator-portal/web-ui/app/src/views/control/SkillsView.tsx#L1-L132)
- [App.tsx:62-136](file://products/operator-portal/web-ui/app/src/App.tsx#L62-L136)

## Multi-Session Workspace Management

The Operator Portal continues to include comprehensive multi-session workspace management, allowing operators to maintain multiple concurrent conversations with different contexts and histories, enhanced with defensive session parsing and stale session handling.

### Enhanced Session Workspace Architecture

The session workspace continues to provide a comprehensive interface for managing multiple conversations with improved data integrity:

#### Session List Management
- **Real-Time Updates**: 30-second polling for session list updates
- **Active Session Persistence**: Current session selection persists across page reloads
- **Pinned Sessions**: Support for incident deep-link sessions that appear even before server list catches up
- **Delete Operations**: Safe session deletion with conflict resolution for pending confirmations

#### Transcript Management
- **Lazy Loading**: Sessions load transcripts on demand to optimize performance
- **Caching Strategy**: In-memory caching prevents redundant API calls for the same session
- **History Seeding**: Resumed sessions render like live conversations with proper turn history
- **Transcript Availability**: Clear indication when sessions have no recorded transcript yet
- **Defensive Parsing**: Enhanced parseStored function handles malformed or corrupted session data

### Monotonic Session Workspace Implementation

The session workspace now includes enhanced monotonic refresh sequences to prevent race conditions:

#### Refresh Sequence Tracking
- **Monotonic Counter**: refreshSeqRef ensures only the newest refresh sequence can apply results
- **Race Condition Prevention**: Prevents older responses from overwriting fresh pending-confirmation flags
- **Concurrent Decision Support**: Handles cases where decisions trigger refreshes during ongoing fetches

#### Enhanced Session Management
- **Real-Time Updates**: 30-second polling for session list updates
- **Active Session Persistence**: Session selection persists across page reloads
- **Pinned Sessions**: Support for incident deep-link sessions that appear even before server list catches up
- **Delete Operations**: Safe session deletion with conflict resolution for pending confirmations
- **Inline Rename Support**: Session title updates with validation and error handling
- **Session ID Copy**: One-click clipboard integration for sharing session identifiers

### Stale Session Handling Integration

The session workspace continues to include comprehensive stale session handling to prevent errors from deleted or expired sessions:

#### Missing Reference Tracking
- **missingRef Implementation**: Uses `useRef(new Set<string>())` to track sessions that return 404 errors
- **Prevention Logic**: Known-missing sessions are set to null to prevent stream pointer usage
- **Auto-Creation Flow**: Next message automatically creates fresh session instead of failing
- **State Management**: Proper session state management during stale session detection

#### Error Recovery Strategies
- **Graceful Degradation**: Falls back to empty session when history loading fails
- **User Feedback**: Provides clear error messages for different failure scenarios
- **Recovery Options**: Offers retry mechanisms and alternative actions for failed operations
- **Session Restoration**: Proper restoration of session state after error recovery

### Session Panel Interface

The session panel continues to provide intuitive session management:

#### Session Display
- **Session Titles**: User-friendly titles with fallback to session IDs
- **Activity Indicators**: Last active timestamps with relative time formatting
- **Pending Confirmation Flags**: Visual indicators for sessions with pending confirmations
- **Delete Actions**: Safe deletion with confirmation dialogs

#### Session Operations
- **Create New Sessions**: One-click session creation with automatic activation
- **Session Switching**: Seamless switching between sessions with state preservation
- **Deep Linking**: Support for incident-specific session deep links
- **Error Handling**: Graceful handling of network errors and session conflicts

### Integration with Chat Interface

The session workspace continues to integrate seamlessly with the chat interface:

#### Turn State Management
- **Per-Session Caching**: Each session maintains its own turn history in memory
- **Stream Attachment**: New messages attach to the correct session context
- **Confirmation Anchoring**: HITL confirmations remain bound to their originating sessions
- **State Restoration**: Session state restored when switching back to previously viewed sessions
- **Ownership Validation**: Enhanced stream ownership handling during session switches to prevent data contamination

#### User Experience Benefits
- **Context Preservation**: Each conversation maintains its own context and history
- **Parallel Workflows**: Operators can work on multiple incidents simultaneously
- **Quick Context Switching**: Easy switching between different operational contexts
- **Session Organization**: Clear visual organization of related conversations

**Updated** The multi-session workspace now includes enhanced monotonic refresh sequences to prevent race conditions during concurrent decision processing, ensuring data consistency across multiple approval operations. The session workspace continues to include comprehensive stale session handling with missing reference tracking to prevent errors from deleted or expired sessions. These improvements ensure more reliable session management and better data integrity. **Enhanced Feature**: The Settings view continues to provide operational context that complements session management by displaying current session information and identity details in a consolidated dashboard format. **Enhanced Feature**: The enhanced approvals inbox continues to integrate with session management to provide cross-session confirmation management capabilities for designated approvers. **Enhanced Feature**: The Operations Document Repository continues to integrate with session management to provide cross-session analysis capabilities through shift summary creation and foreign session metadata inclusion. **Critical Enhancement**: The live decision sync system continues to work seamlessly with multi-session management to ensure external decisions are properly synchronized to the correct active session context.

**Section sources**
- [useSessionWorkspace.ts:1-218](file://products/operator-portal/web-ui/app/src/sessions/useSessionWorkspace.ts#L1-L218)
- [ChatView.tsx:389-490](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L389-L490)
- [ChatView.tsx:496-790](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L496-L790)

## Voice Input Support

The Operator Portal continues to include comprehensive voice input support, allowing operators to submit messages using speech recognition while maintaining full compatibility with existing text-based workflows.

### Voice Input Architecture

The voice input system continues to integrate seamlessly with the existing chat interface:

#### Input Modality Support
- **Modality Metadata**: Voice inputs are tagged with `input_modality: "voice"` metadata
- **Backend Recording**: Voice modality is recorded for audit purposes without affecting policy decisions
- **Transcription Handling**: Speech-to-text conversion happens client-side before sending to backend
- **Policy Neutrality**: Voice modality never changes policy enforcement or HITL outcomes

#### User Interface Integration
- **Sender Component**: Ant Design Sender component with built-in voice recording support
- **Visual Indicators**: Clear feedback during voice recording and transcription
- **Fallback Handling**: Graceful degradation when voice input is unavailable
- **Accessibility**: Proper ARIA labels and keyboard navigation support

### Technical Implementation

The voice input system continues to leverage modern web APIs:

#### Speech Recognition
- **Web Speech API**: Browser-native speech recognition for supported browsers
- **Language Detection**: Automatic language detection with fallback to default language
- **Continuous Recognition**: Support for continuous speech recognition during longer inputs
- **Error Handling**: Graceful handling of speech recognition failures

#### Audio Processing
- **Audio Capture**: Direct audio capture from microphone with quality settings
- **Format Conversion**: Automatic format conversion for backend compatibility
- **Compression**: Audio compression for efficient network transmission
- **Privacy**: Client-side processing ensures audio data doesn't leave the browser unnecessarily

### Language Selection and Management

The voice input system continues to include comprehensive language management:

#### Language Configuration
- **Supported Languages**: English (US) and Chinese (Mandarin) with extensible language list
- **Browser Locale Detection**: Automatic language detection based on browser settings
- **Local Storage Persistence**: User's language preference saved in localStorage
- **Fallback Handling**: Graceful fallback to English when preferred language is unavailable

#### Recognition Control
- **Manual Start/Stop**: Explicit control over speech recognition sessions
- **Error Recovery**: Comprehensive error handling with user-friendly messages
- **Resource Management**: Proper cleanup of speech recognition resources
- **Performance Optimization**: Efficient recognition session management

### User Experience Benefits

Voice input continues to provide several operational benefits:

#### Enhanced Productivity
- **Hands-Free Operation**: Operators can input commands while performing other tasks
- **Natural Language**: More natural conversation flow compared to typing
- **Speed**: Faster input for experienced operators familiar with voice commands
- **Accessibility**: Improved accessibility for operators with motor impairments

#### Operational Flexibility
- **Mobile Support**: Better input method for mobile devices with limited keyboard access
- **Emergency Situations**: Quick command entry during critical incidents
- **Multitasking**: Ability to monitor systems while verbally commanding actions
- **Reduced Typing Fatigue**: Alternative input method for extended operational periods

### Security and Privacy Considerations

The voice input system continues to implement appropriate security measures:

#### Privacy Protection
- **Client-Side Processing**: Speech recognition occurs locally in the browser
- **No Audio Storage**: Transcribed text is sent immediately without storing audio
- **Permission Requirements**: Explicit user permission required for microphone access
- **Browser Security**: Leverages browser security model for microphone access

#### Audit and Compliance
- **Input Logging**: All voice inputs logged with modality metadata for audit trails
- **Transparency**: Clear indication when voice input is being used
- **Compliance**: Meets organizational requirements for input method logging
- **Data Minimization**: Only transcribed text stored, not audio recordings

**Section sources**
- [useSpeechRecognition.ts:1-135](file://products/operator-portal/web-ui/app/src/voice/useSpeechRecognition.ts#L1-L135)
- [languages.ts:1-60](file://products/operator-portal/web-ui/app/src/voice/languages.ts#L1-L60)
- [useChatStream.ts:80-85](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L80-L85)
- [transport.ts:31-50](file://products/operator-portal/web-ui/app/src/stream/transport.ts#L31-L50)
- [ChatView.tsx:725-784](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L725-L784)

## Incident Triage and Deep Linking

The Operator Portal continues to include comprehensive incident triage capabilities with automated connector dispatches and seamless deep linking to chat sessions, implemented through the IncidentsView component.

### Incident Management Architecture

The incident management system continues to provide end-to-end incident handling from creation to resolution:

#### Incident List View
- **Auto-Refresh**: 15-second automatic refresh for real-time incident updates
- **Filtering**: Status, severity, and source-based filtering capabilities
- **Manual Intake**: Form-based incident creation with title, summary, severity, and labels
- **Detail Navigation**: Click-to-view incident details with comprehensive information

#### Incident Detail View
- **Comprehensive Information**: Full incident metadata including timestamps, labels, and status
- **Triage Report**: Automated triage analysis with severity assessment and next steps
- **Connector Dispatches**: Track external system integrations and their status
- **Chat Deep Linking**: Seamless transition to chat for continued incident investigation

### Deep Linking Implementation

The deep linking system continues to enable seamless workflow transitions between incidents and chat:

#### Session Pinning
- **Automatic Session Creation**: Incident-specific sessions created when navigating from incidents to chat
- **Session Identification**: Unique session IDs generated for each incident context
- **Context Preservation**: Incident context maintained throughout chat conversation
- **Visual Indicators**: Clear indication of pinned incident sessions in workspace panel

#### Workflow Integration
- **One-Click Transition**: "Continue in chat" button for immediate workflow continuation
- **Context Transfer**: Incident information automatically included in chat context
- **Session Management**: Pinned sessions persist across page reloads and navigation
- **Role-Based Access**: Incident viewing and action capabilities controlled by user roles

### Triage Automation

The triage system continues to provide automated incident analysis and response coordination:

#### Automated Analysis
- **Severity Assessment**: AI-powered severity classification with confidence scoring
- **Evidence Gathering**: Automated collection of relevant system information
- **Hypothesis Generation**: Potential root cause analysis with supporting evidence
- **Next Steps Recommendation**: Actionable recommendations prioritized by urgency

#### Connector Integration
- **External System Dispatch**: Automated notifications to external monitoring and alerting systems
- **Status Tracking**: Real-time status updates for connector communications
- **Error Handling**: Robust error handling with retry logic and failure reporting
- **Audit Trail**: Complete audit logging of all connector interactions

### User Interface Features

The incident management interface continues to provide intuitive operation:

#### List View Features
- **Compact Display**: Efficient listing of multiple incidents with key information
- **Status Visualization**: Color-coded status badges for quick incident assessment
- **Filter Toolbar**: Advanced filtering with status, severity, and source options
- **Bulk Actions**: Capability to perform actions on multiple incidents

#### Detail View Features
- **Rich Information Display**: Comprehensive incident information with expandable sections
- **Interactive Elements**: Clickable elements for triage execution and chat navigation
- **Evidence Presentation**: Formatted display of triage reports and supporting evidence
- **Action Buttons**: Contextual actions based on incident status and user permissions

### Security and Access Control

The incident management system continues to implement comprehensive security measures:

#### Role-Based Access
- **View Permissions**: Separate roles for viewing vs. acting on incidents
- **Action Validation**: Server-side validation of all incident operations
- **Audit Logging**: Complete audit trail of all incident interactions
- **Data Isolation**: Proper scoping of incident data based on user permissions

#### Data Integrity
- **Input Validation**: Comprehensive validation of incident data submissions
- **Conflict Resolution**: Handling of concurrent modifications and race conditions
- **Data Persistence**: Reliable storage of incident data with backup and recovery
- **Audit Compliance**: Full compliance with audit requirements for incident handling

**Section sources**
- [IncidentsView.tsx:1-600](file://products/operator-portal/web-ui/app/src/views/incidents/IncidentsView.tsx#L1-L600)
- [App.tsx:219-228](file://products/operator-portal/web-ui/app/src/App.tsx#L219-L228)
- [useSessionWorkspace.ts:136-159](file://products/operator-portal/web-ui/app/src/sessions/useSessionWorkspace.ts#L136-L159)

## Deployment Guide

### Prerequisites

Before deploying the Operator Portal, ensure you have the following prerequisites:

- **Kubernetes Cluster**: Version 1.20 or higher
- **Helm**: Version 3.x for package management
- **kubectl**: Latest stable version configured for your cluster
- **Nginx Ingress Controller**: For external access routing
- **TLS Certificates**: Valid certificates for HTTPS access
- **Identity Provider**: OIDC-compatible identity provider (Keycloak, Auth0, etc.)
- **Node.js**: Version 22+ for local development

### React Application Build

Build the React application using Vite:

```bash
cd products/operator-portal/web-ui/app
npm install
npm run build
```

### Legacy Application Support

The legacy vanilla JavaScript application remains available for backward compatibility:

```bash
cd products/operator-portal
# Legacy build process
make build
make push
```

### Kubernetes Deployment

Deploy the portal using the provided Kubernetes manifests:

```bash
# Create namespace
kubectl create namespace operator-portal

# Apply deployment
kubectl apply -f shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-deployment.yaml

# Apply service
kubectl apply -f shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-service.yaml
```

### Nginx Configuration

The nginx configuration handles static file serving and reverse proxy setup on port 8080:

- **Static Asset Serving**: Optimized delivery of HTML, CSS, and JavaScript files
- **API Proxying**: Reverse proxy to platform gateway for backend communication
- **Streaming Support**: Configured for long-lived connections and SSE streams with proxy_buffering off
- **Security Headers**: Content Security Policy and other security headers
- **Compression**: Gzip compression for reduced bandwidth usage
- **Non-root Execution**: Runs as unprivileged user for enhanced security
- **Cache Control**: No-store headers for all static assets to prevent caching issues
- **React SPA Routing**: Support for client-side routing with fallback to index.html

### Environment Configuration

Configure environment variables for the portal deployment:

- **API Gateway URL**: Backend API gateway endpoint
- **Authentication Provider**: Identity broker configuration
- **Logging Level**: Debug, info, warning, or error levels
- **Feature Flags**: Enable/disable specific features

### Version Management and Cache Busting

The deployment process continues to include enhanced version management:

- **Platform Version**: PLATFORM_VERSION set to v0.18.1 for consistency across the platform ecosystem
- **Build-Time Injection**: Version injected at build time from root VERSION file
- **Cache-Busting**: Query parameter versioning ensures proper client-side caching behavior
- **Version Validation**: Automated validation ensures all platform components use consistent versions
- **Deployment Coordination**: Coordinated versioning across all platform services

**Updated** The deployment continues to support both the new React/TypeScript application and the legacy vanilla JavaScript implementation, with enhanced HITL confirmation bridging system, improved navigation system with persistent 64px icon rail that maintains consistent layout anchoring across all views, enhanced responsive behavior with precise 992px breakpoint detection, better menu group title handling in collapsed states, enhanced mobile drawer navigation with proper positioning and z-index management, dynamic aria-labels that adapt based on viewport state and sidebar status, and restructured styling with .view-container-inset class for proper content spacing. The nginx configuration remains optimized for streaming support and non-root execution while supporting the new permission matrix and workspace resource endpoints. Enhanced security measures include improved XSS prevention and defensive session parsing. The sticky request banner system and enhanced markdown rendering with proper table structure and nested list support are also supported in the deployment. **Critical Enhancement**: The deployment continues to include support for the enhanced stale session handling system that automatically detects and recovers from deleted or expired sessions, ensuring more reliable chat functionality, and the comprehensive evidence persistence system that provides unified rendering of both live streamed and replayed evidence with request ID display and truncation markers. **Critical Enhancement**: The deployment continues to include support for the model selection system with catalog integration, providing operators with flexible AI model choices while maintaining fail-open behavior when catalog services are unavailable. **New Feature**: The deployment continues to include support for the ComposerSelectionBar component which provides an extensible control strip architecture for model selection and future per-turn controls. **Enhanced Feature**: The deployment continues to include support for the restored Settings view as a read-only Session & Identity panel that provides operational insights using existing AuthContext and session workspace state. **Critical Enhancement**: The deployment continues to include support for the tier-aware HITL confirmation system with badge display that clearly distinguishes between operator confirmations and approver-required scenarios. **New Feature**: The deployment continues to include support for the enhanced Approvals inbox with cross-session confirmation management, real-time polling, decision attribution, 30-day history browsing capabilities, and client-side pagination for designated approvers. **New Feature**: The deployment continues to include support for the complete Operations Document Repository with shift summary creation, session selection, document publishing, and viewing capabilities for operational documentation. **Critical Enhancement**: The deployment continues to include support for the improved live decision sync system that provides time-based settle windows with change detection and settle windows to synchronize external decisions to active chat views without manual refresh. **v0.14.1 Patch**: The deployment continues to include the authoritative `reseedTurns` method that prevents cache shadowing during owner-side decision synchronization, ensuring external decisions are properly reflected in active chat views without being overridden by stale cached turns. **v0.15.0 Enhancement**: The deployment continues to include support for the confirmation card turn anchoring system based on SPEC-033, ensuring each confirmation card renders under the exchange that parked it rather than stacking all cards under the newest turn, providing accurate historical context for multi-park sessions with comprehensive test coverage for per-exchange anchoring, pending anchoring, and legacy fallback scenarios. **v0.18.1 Enhancement**: The deployment continues to include support for the enhanced markdown rendering system with nested list support and proper ordered/unordered list handling, and pod log quoting improvements that render log excerpts in fenced code blocks for better readability in agent replies.

**Section sources**
- [nginx.conf](file://products/operator-portal/nginx.conf)
- [Dockerfile](file://products/operator-portal/Dockerfile)
- [vite.config.ts:14-28](file://products/operator-portal/web-ui/app/vite.config.ts#L14-L28)
- [package.json:9-13](file://products/operator-portal/web-ui/app/package.json#L9-L13)

## UI Customization

The Operator Portal continues to support extensive UI customization to match organizational branding and preferences, with both legacy CSS and React component customization options.

### Theme Customization

- **Color Schemes**: Primary, secondary, and accent colors via CSS custom properties and Ant Design theme configuration
- **Typography**: Font families, sizes, and line heights
- **Layout Options**: Compact, standard, and spacious layouts
- **Dark/Light Mode**: Automatic or manual theme switching

### Branding Elements

- **Logo Integration**: Custom logo placement and sizing
- **Favicon Support**: Custom browser tab icons
- **Page Titles**: Customizable page titles and meta descriptions
- **Watermarking**: Optional watermark overlay for sensitive environments

### Layout Customization

- **Widget Configuration**: Show/hide dashboard widgets
- **Column Layouts**: Adjustable grid layouts for different screen sizes
- **Navigation Structure**: Customizable navigation menus
- **Responsive Breakpoints**: Mobile-first responsive design

### Accessibility Customization

- **High Contrast Mode**: Enhanced contrast for better visibility
- **Screen Reader Support**: ARIA labels and semantic markup
- **Keyboard Navigation**: Full keyboard operability
- **Font Scaling**: Support for increased font sizes

### Enhanced Customization Options

The React implementation continues to provide additional customization points:

- **Component Theming**: Ant Design theme configuration for consistent styling
- **Custom Components**: Extensible component architecture for custom functionality
- **CSS Modules**: Scoped styling for component-specific customization
- **Design Tokens**: Centralized design token management for brand consistency
- **Sidebar Width**: Adjustable sidebar width for different screen densities
- **User Card Layout**: Customizable user card appearance and positioning
- **Navigation Item Styling**: Custom styling for navigation items and active states
- **Mobile Drawer Behavior**: Configurable drawer animation and positioning
- **Section Label Styling**: Customizable appearance for navigation section labels
- **Tier-Aware Confirmation Card Styling**: Customizable appearance for approval cards with tier-specific badges (operator confirmation vs approver required), warning borders, and action buttons
- **Enhanced Approvals Inbox Styling**: Customizable appearance for confirmation inbox entries with provenance metadata, decision attribution, history sections, and pagination controls
- **Operations Document Styling**: Customizable appearance for document cards, digests, prose panels, and create dialogs with appropriate spacing and typography
- **Cited Guidance Styling**: Customizable chip appearance and behavior for skills integration
- **Permission Matrix Styling**: Customizable table styling for permission displays
- **Workspace Resource Styling**: Customizable table layouts for tools and skills catalogs
- **Incident View Styling**: Customizable appearance for incident triage interface with status badges and action buttons
- **Voice Input Styling**: Customizable appearance for voice input controls and language selection
- **Enhanced Navigation Styling**: Customizable appearance for persistent 64px icon rail, hamburger menu button, positioning, and responsive behavior with consistent layout anchoring
- **Sticky Request Banner Styling**: Customizable appearance and behavior for conversation context banners
- **Brand Display Styling**: Customizable inline brand display with platform version tags
- **Stale Session Handling Styling**: Customizable appearance for stale session error messages and recovery indicators
- **Evidence Persistence Styling**: Customizable appearance for evidence cards, truncation markers, and request ID display
- **Model Selection Styling**: Customizable appearance for model selector dropdown, fixed labels, and catalog integration
- **Composer Selection Bar Styling**: Customizable appearance for the extensible control strip with proper flexbox layout and item organization
- **Settings View Styling**: Customizable appearance for the read-only Session & Identity panel with operational insights dashboard
- **Live Decision Sync Styling**: Customizable appearance for pending decision polling indicators and settlement status
- **Authoritative Re-seed Styling**: Customizable appearance for reseedTurns operations and cache replacement indicators
- **Turn-Anchored Confirmation Styling**: Customizable appearance for turn-anchored confirmation cards with proper historical context display
- **Enhanced Markdown Styling**: Customizable appearance for nested lists, ordered list numbering, and fenced code blocks with pod log display

**Section sources**
- [global.css:66-119](file://products/operator-portal/web-ui/app/src/theme/global.css#L66-L119)
- [tokens.ts:1-43](file://products/operator-portal/web-ui/app/src/theme/tokens.ts#L1-L43)

## Accessibility Features

The Operator Portal continues to be designed with accessibility as a first-class concern, ensuring usability for users with disabilities, with enhanced support in the React implementation.

### WCAG Compliance

- **WCAG 2.1 AA Compliance**: Meets Web Content Accessibility Guidelines
- **Semantic HTML**: Proper use of semantic elements and landmarks
- **ARIA Labels**: Comprehensive ARIA attributes for assistive technologies
- **Keyboard Navigation**: Full keyboard operability with visible focus indicators

### Screen Reader Support

- **Descriptive Alt Text**: Meaningful alternative text for images and icons
- **Form Labels**: Properly associated form labels and instructions
- **Error Messages**: Descriptive error messages with suggestions
- **Status Updates**: Live regions for dynamic content updates

### Visual Accessibility

- **Color Contrast**: Minimum 4.5:1 contrast ratio for normal text
- **Text Resizing**: Support for up to 200% text zoom
- **Focus Indicators**: Clear visual focus indicators
- **Reduced Motion**: Respect for user motion preferences

### Cognitive Accessibility

- **Simple Language**: Clear and concise language throughout
- **Consistent Layout**: Predictable navigation and interaction patterns
- **Error Prevention**: Helpful error messages and recovery options
- **Progress Indicators**: Clear feedback for long-running operations

### Enhanced Accessibility Features

The React implementation continues to include additional accessibility improvements:

- **Component Structure**: Proper semantic structure with nav and main landmarks
- **Sidebar Navigation**: Accessible navigation with proper ARIA attributes
- **User Card**: Accessible user identity display with proper labeling
- **Mobile Drawer**: Accessible off-canvas navigation with proper focus management
- **Enhanced Navigation**: Persistent 64px icon rail with dynamic aria-labels that adapt based on viewport state and sidebar status
- **Tier-Aware Confirmation Cards**: Accessible approval interfaces with proper ARIA labels, keyboard navigation, and tier-specific badge announcements
- **Enhanced Approvals Inbox**: Accessible confirmation inbox with proper ARIA labels, keyboard navigation, decision attribution announcements, and pagination controls
- **Operations Document Interface**: Accessible document management with proper ARIA labels, keyboard navigation, and form controls for shift summary creation
- **Audit Trail**: Accessible table with proper headers and expandable details
- **Cited Guidance Chips**: Accessible chip elements with proper labeling and keyboard navigation
- **Permission Matrix**: Accessible table with proper headers and status badges
- **Workspace Resources**: Accessible tables for tools and skills catalogs with proper headers
- **Voice Input**: Accessible voice input with proper feedback and error handling
- **Incident Views**: Accessible incident management interface with proper form labels and status announcements
- **Deep Linking**: Accessible navigation between incidents and chat with proper focus management
- **Sticky Request Banner**: Accessible conversation context maintenance with proper ARIA labels and keyboard navigation support
- **Stale Session Handling**: Accessible error messages and recovery indicators for stale session detection and retry operations
- **Evidence Persistence**: Accessible evidence cards with proper ARIA labels for truncation markers and request ID display
- **Model Selection**: Accessible model selector with proper ARIA labels and keyboard navigation support
- **Composer Selection Bar**: Accessible control strip with proper ARIA labels and keyboard navigation for model selection
- **Settings View**: Accessible read-only Session & Identity panel with proper ARIA labels and keyboard navigation for operational insights
- **Live Decision Sync**: Accessible polling indicators with proper ARIA labels for pending decision synchronization status
- **Authoritative Re-seed**: Accessible reseedTurns operations with proper ARIA labels for cache replacement and timeline updates
- **Turn-Anchored Confirmation**: Accessible turn-anchored confirmation cards with proper ARIA labels and keyboard navigation for historical context display
- **Enhanced Markdown**: Accessible nested list rendering with proper semantic structure and keyboard navigation support

**Section sources**
- [global.css:66-119](file://products/operator-portal/web-ui/app/src/theme/global.css#L66-L119)
- [App.tsx:334-357](file://products/operator-portal/web-ui/app/src/App.tsx#L334-L357)
- [index.html:1-291](file://products/operator-portal/web-ui/app/index.html#L1-L291)

## Browser Compatibility

The Operator Portal continues to support modern web browsers with progressive enhancement for broader compatibility, with the React implementation providing enhanced compatibility through transpilation.

### Supported Browsers

- **Chrome**: Version 90+ (recommended)
- **Firefox**: Version 88+
- **Safari**: Version 14+
- **Edge**: Version 90+
- **Mobile Safari**: iOS 14+
- **Android Chrome**: Android 10+

### Feature Support

- **ES6+ JavaScript**: Modern JavaScript features with polyfills
- **CSS Grid and Flexbox**: Flexible layout systems
- **Web APIs**: Fetch API, Local Storage, Service Workers, Server-Sent Events
- **Media Queries**: Responsive design capabilities
- **Canvas API**: Chart and graph rendering

### Polyfills and Fallbacks

- **CoreJS**: JavaScript feature polyfills for older browsers
- **Autoprefixer**: CSS vendor prefixing for cross-browser compatibility
- **Babel Transpilation**: ES6+ to ES5 transpilation when needed
- **Graceful Degradation**: Essential functionality works across all supported browsers

### Enhanced Feature Compatibility

The React implementation continues to maintain broad browser compatibility:

- **React 18**: Broad browser support with automatic polyfilling
- **TypeScript**: Compiled to compatible JavaScript for target browsers
- **Vite Build**: Optimized bundling with browser-specific optimizations
- **CSS Grid**: Used for two-column layout with fallbacks for older browsers
- **CSS Custom Properties**: Theme customization with fallback values
- **Modern JavaScript**: ES6+ features with appropriate polyfills
- **Responsive Design**: Mobile-first approach with progressive enhancement
- **Enhanced Navigation**: Cross-browser support for persistent 64px icon rail, responsive breakpoints, and drawer functionality
- **Tier-Aware Confirmation Cards**: Inline approval interfaces with tier-specific badge display compatible with all modern browsers
- **Enhanced Approvals Inbox**: Cross-session confirmation management with real-time polling, pagination, and decision attribution compatible with all modern browsers
- **Operations Document Interface**: Cross-browser support for document management with proper fallbacks when API services are unavailable
- **Skills Integration**: Cited guidance chips work across all supported browsers
- **Permission Matrix**: Table-based displays compatible with all modern browsers
- **Workspace Resources**: Standard HTML tables with broad browser support
- **Voice Input**: Graceful degradation when Web Speech API is unavailable
- **Incident Views**: Full browser compatibility for incident management interface
- **Deep Linking**: Cross-browser support for session pinning and navigation
- **Sticky Request Banner**: IntersectionObserver support with graceful fallbacks for older browsers
- **Stale Session Handling**: Cross-browser support for 404 error detection and retry logic with graceful fallbacks
- **Evidence Persistence**: Cross-browser support for evidence replay with proper fallbacks when evidence store is unavailable
- **Model Selection**: Cross-browser support for model catalog integration with graceful degradation when catalog service is unavailable
- **Composer Selection Bar**: Cross-browser support for extensible control strip with proper fallbacks when catalog service is unavailable
- **Settings View**: Cross-browser support for read-only Session & Identity panel with graceful degradation when authentication services are unavailable
- **Live Decision Sync**: Cross-browser support for time-based settle windows with proper fallbacks when session detail API is unavailable
- **Authoritative Re-seed**: Cross-browser support for reseedTurns method with proper fallbacks when cache operations fail
- **Turn-Anchored Confirmation**: Cross-browser support for turn-anchored confirmation cards with proper fallbacks when turn_index is unavailable
- **Enhanced Markdown**: Cross-browser support for nested list rendering and fenced code blocks with proper fallbacks for older browsers

**Section sources**
- [Dockerfile](file://products/operator-portal/Dockerfile)
- [package.json:6-8](file://products/operator-portal/web-ui/app/package.json#L6-L8)

## Troubleshooting Guide

Common issues and their solutions when working with the Operator Portal.

### Connection Issues

**Problem**: Cannot connect to backend services
**Solution**: 
- Verify API gateway URL configuration
- Check network connectivity and firewall rules
- Confirm authentication credentials are valid
- Review nginx configuration for proper routing on port 8080

### Authentication Problems

**Problem**: Login failures or session timeouts
**Solution**:
- Verify identity broker connectivity
- Check token expiration and refresh mechanisms
- Ensure CORS policies allow the portal domain
- Review browser cookie settings and privacy modes

### Performance Issues

**Problem**: Slow dashboard loading or unresponsive interface
**Solution**:
- Check browser developer tools for console errors
- Verify network request timing and response sizes
- Review server-side API performance and database queries
- Optimize image and asset loading strategies

### Deployment Issues

**Problem**: Kubernetes deployment failures
**Solution**:
- Check pod logs for error messages
- Verify resource quotas and limits
- Ensure proper RBAC permissions
- Validate configuration secrets and configmaps
- Confirm non-root execution permissions are properly configured

### Port Configuration Issues

**Problem**: Service not accessible on expected port
**Solution**:
- Verify nginx is listening on port 8080
- Check Kubernetes service port mappings
- Ensure ingress controller routes traffic correctly
- Review firewall rules allowing port 8080

### Streaming Message Issues

**Problem**: Stream completes with no visible text or missing delta events
**Solution**:
- Verify streaming endpoint returns proper event format with 'type' field
- Check that message_delta events contain valid delta content
- Ensure stream completion events are properly handled
- Review browser console for JavaScript errors in streaming logic
- Confirm nginx proxy configuration allows streaming responses

### React Application Issues

**Problem**: React application fails to load or render incorrectly
**Solution**:
- Check browser console for JavaScript errors
- Verify React dependencies are properly installed
- Ensure Vite build completed successfully
- Check for TypeScript compilation errors
- Verify React component imports are correct

### Session Management Issues

**Problem**: Sessions not loading or switching incorrectly
**Solution**:
- Verify session API endpoints are accessible
- Check browser console for session-related errors
- Ensure session storage is properly configured
- Verify session persistence across page reloads
- Check for session conflict errors during deletion
- **Updated**: Check for malformed session data that may be handled by defensive parsing

### Monotonic Session Workspace Issues

**Problem**: Race conditions during concurrent decision processing or stale data overwrites
**Solution**:
- Verify that refreshSeqRef is properly incrementing for each refresh operation
- Check that only the newest refresh sequence can apply results
- Ensure that older responses are properly discarded when newer ones arrive
- Verify that pending confirmation flags are not being overwritten by stale data
- Check browser console for JavaScript errors in monotonic refresh logic
- Test concurrent decision scenarios to verify proper race condition prevention

### Enhanced Live Decision Sync Issues

**Problem**: External decisions not appearing in active chat view or settle window not working correctly
**Solution**:
- Verify that usePendingDecisionPoll hook is properly integrated in ChatView component
- Check that time-based settle window (300 seconds) is functioning correctly
- Ensure that visibility/focus kick mechanisms are working to compensate for background tab throttling
- Verify that fingerprint comparison is detecting state changes properly
- Check browser console for JavaScript errors in pending decision polling logic
- Verify that session detail API (/api/v1/sessions/{id}) is accessible and returns proper data
- Test with external decision sources (approver inbox, other browser sessions) to verify synchronization
- Check that polling pauses during active streaming to prevent interference

### Enhanced Approvals Inbox Issues

**Problem**: Approvals view not loading or confirmation inbox not working
**Solution**:
- Verify user has approver or platform-admin roles for inbox access
- Check that /api/v1/approvals/inbox endpoint is accessible and returns proper data
- Verify that real-time polling is functioning with 30-second intervals
- Check browser console for JavaScript errors in approvals inbox logic
- Ensure that decision attribution is properly recorded and displayed
- Verify that race condition handling works correctly for concurrent approval attempts
- Test that pending count badge updates correctly in navigation sidebar
- **Updated**: Verify that client-side pagination is working correctly for history display with 10 entries per page

### Enhanced Approvals Inbox API Issues

**Problem**: Approvals inbox API returning errors or incomplete data
**Solution**:
- Check that platform gateway has /api/v1/approvals/inbox endpoint configured
- Verify agent-platform confirmation store is running and accessible
- Review browser console for API call errors and network issues
- Ensure proper authentication for approvals inbox requests
- Check that confirmation records include required fields (confirm_id, session_id, owner_user_id, status)
- Verify that 30-day history window is properly implemented
- Test approvals inbox API directly to confirm backend functionality

### Enhanced Approvals Inbox Styling Issues

**Problem**: Approvals inbox layout or styling problems
**Solution**:
- Verify that .approvals-entry class has proper flexbox styling
- Check that .approvals-entry-meta has correct spacing and alignment
- Ensure provenance metadata displays correctly (session, owner, parking time)
- Verify that decision attribution displays properly for resolved items
- Check browser developer tools for CSS specificity issues
- Test responsive behavior on different screen sizes
- Verify proper integration with existing confirmation card styling
- **Updated**: Verify that pagination controls are properly styled and functional

### Operations Document Repository Issues

**Problem**: Documents view not loading or shift summary creation failing
**Solution**:
- Verify that /api/v1/documents endpoint is accessible and returns proper data
- Check that document repository service is running and accessible
- Verify that session selection works correctly with proper session IDs
- Check browser console for JavaScript errors in document management logic
- Ensure that foreign session permission checks are working correctly
- Verify that publish operations handle duplicate protection properly
- Test document creation with valid session IDs and labels
- **Updated**: Verify that digest rendering works correctly for both owner and foreign sessions

### Operations Document API Issues

**Problem**: Document repository API returning errors or incomplete data
**Solution**:
- Check that platform gateway has /api/v1/documents endpoint configured
- Verify document repository service is running and accessible
- Review browser console for API call errors and network issues
- Ensure proper authentication for document operations
- Check that document responses include required fields (document_id, label, state, digest, provenance)
- Verify that session coverage information is properly included in document responses
- Test document repository API directly to confirm backend functionality

### Operations Document Styling Issues

**Problem**: Documents view layout or styling problems
**Solution**:
- Verify that document cards have proper flexbox styling with file icons and action buttons
- Check that digest panels display correctly with session coverage and foreign session indicators
- Ensure that prose panels render properly with collapsible sections and warning alerts
- Verify that create dialog form inputs have proper styling and validation feedback
- Check browser developer tools for CSS specificity issues
- Test responsive behavior on different screen sizes
- Verify proper integration with existing Ant Design components

### Enhanced Navigation Issues

**Problem**: Persistent 64px icon rail not appearing or behaving incorrectly across screen sizes
**Solution**:
- Verify that useNarrowViewport() hook is properly detecting viewport changes at 992px breakpoint
- Check that .mobile-menu-button class has correct display property and fixed positioning
- Ensure z-index values (100) are not conflicting with other elements
- Verify that dynamic aria-labels are updating correctly based on viewport and sidebar state
- Check that .view-container-inset class is properly applied when sidebar is absent or folded
- Review browser console for JavaScript errors in navigation logic
- Test on actual devices or use browser developer tools device emulation

### Enhanced Error Handling Issues

**Problem**: Various error types not handled properly in enhanced approval system
**Solution**:
- **Network Errors**: Check network connectivity and API endpoint availability
- **Authentication Failures**: Verify token validity and refresh mechanisms
- **Streaming Interruptions**: Check SSE connection stability and reconnection logic
- **Session Switching Errors**: Verify stream ownership handling during session transitions
- **Malformed Data**: Check defensive parsing for corrupted session data
- **Backend API Issues**: Verify API v6 schema compliance for risk level handling
- **Navigation Errors**: Check responsive breakpoint handling and drawer initialization
- **Content Spacing Issues**: Verify .view-container-inset class application and proper padding calculations
- **Stale Session Errors**: Check 404 error detection and retry logic for deleted or expired sessions
- **Evidence Persistence Errors**: Check evidence store availability and transcript-to-turn conversion logic
- **Monotonic Refresh Errors**: Check refresh sequence tracking and race condition prevention
- **Settle Window Errors**: Check time-based settle window calculation and visibility/focus kick mechanisms

### Sticky Request Banner Issues

**Problem**: Sticky request banner not appearing or behaving incorrectly
**Solution**:
- Verify IntersectionObserver is properly initialized and observing user message elements
- Check that .turn-request-banner.visible class is being applied when user message scrolls out of view
- Ensure chat-messages container is properly identified for observer root
- Verify CSS styles for sticky positioning and transitions are correctly applied
- Check browser console for JavaScript errors in IntersectionObserver logic
- Test with long conversations to verify banner appears when user message scrolls out of viewport

### Enhanced Markdown Rendering Issues

**Problem**: Markdown not rendering correctly, nested lists not working, or security vulnerabilities detected
**Solution**:
- Verify renderMarkdown function is properly escaping HTML content
- Check that javascript: and data: protocols are being blocked in link processing
- Ensure table rendering produces proper thead/tbody structure instead of disconnected tables
- Review test coverage for XSS prevention and quote escaping
- Check browser console for JavaScript errors in markdown processing
- Verify that all user input is properly escaped before HTML injection
- **Updated**: Verify that nested list rendering is working correctly with proper ordered/unordered list handling
- **Updated**: Check that pod log quoting is properly rendering in fenced code blocks with real line breaks
- **Updated**: Verify that ordered lists are properly wrapped in `<ol>` tags with correct numbering
- **Updated**: Test nested list scenarios to ensure indented sub-bullets are properly nested instead of rendered as literal text

### Enhanced Authentication Issues

**Problem**: Authentication state not properly managing disabled states for unauthenticated users
**Solution**:
- Verify that session creation controls are properly disabled when user is not authenticated
- Check that appropriate tooltips are displayed explaining authentication requirements
- Ensure disabled states are consistently applied across all unauthenticated user interactions
- Review browser console for JavaScript errors in authentication state management
- Test session creation workflow with unauthenticated user to verify proper disabled behavior

### Model Selection Issues

**Problem**: Model selector not appearing or model selection not working
**Solution**:
- Verify /api/v1/models endpoint is accessible and returns proper catalog data
- Check browser console for JavaScript errors in model catalog fetching
- Ensure getModelCatalog function is properly handling API responses
- Verify ModelSelect component is receiving proper catalog data
- Check that selected model is properly included in chat message metadata
- Review network requests to confirm model catalog API calls are successful
- Verify fail-open behavior when catalog service is unavailable

### Model Catalog API Issues

**Problem**: Model catalog API returning errors or incomplete data
**Solution**:
- Check that platform gateway has /api/v1/models endpoint configured
- Verify model catalog service is running and accessible
- Review browser console for API call errors and network issues
- Ensure proper authentication for model catalog requests
- Check that model catalog responses include required fields (id, label, provider, default)
- Verify sparse payload handling for incomplete catalog responses
- Test model catalog API directly to confirm backend functionality

### Composer Selection Bar Issues

**Problem**: ComposerSelectionBar not appearing or collapsing incorrectly
**Solution**:
- Verify that catalog data is properly passed to ComposerSelectionBar component
- Check that catalog.fetch is successful and returns proper model data
- Ensure CSS classes are properly applied for flexbox layout
- Verify that component collapses when catalog is null or empty
- Check browser console for JavaScript errors in component rendering
- Test with different catalog scenarios (empty, single model, multiple models)
- Verify proper integration with Sender component footer slot

### Composer Selection Bar Styling Issues

**Problem**: ComposerSelectionBar layout or styling problems
**Solution**:
- Verify that .composer-selection-bar class has proper flexbox styling
- Check that .composer-selection-item has correct alignment and spacing
- Ensure .composer-selection-label has proper typography styling
- Verify that CSS is properly loaded and not overridden by other styles
- Check browser developer tools for CSS specificity issues
- Test responsive behavior on different screen sizes
- Verify proper integration with Ant Design components

### Model Selection Integration Issues

**Problem**: Model selection not working with ComposerSelectionBar
**Solution**:
- Verify that ModelSelect component is properly imported and used within ComposerSelectionBar
- Check that onChange callback is properly wired to parent component
- Ensure model state is properly managed in ChatView component
- Verify that selected model is included in chat message metadata
- Check for TypeScript compilation errors in component interfaces
- Test model selection flow from UI to backend API

### Settings View Issues

**Problem**: Settings view not displaying correctly or operational insights not available
**Solution**:
- Verify that AuthContext is properly initialized and providing identity information
- Check that session workspace state is accessible and contains current session data
- Ensure platform version information is properly loaded from version.ts
- Verify that the Settings view is properly routed and accessible from navigation
- Check browser console for JavaScript errors in Settings view rendering
- Verify that read-only interface is properly implemented without modification capabilities
- Test identity information display with different user roles and authentication states

### Settings View Integration Issues

**Problem**: Settings view not integrating properly with existing components
**Solution**:
- Verify that AuthContext integration is working correctly for identity display
- Check that session workspace state is properly accessed for session details
- Ensure platform metadata is correctly displayed from version information
- Verify that the read-only nature of the panel is maintained throughout the interface
- Check for proper error handling when authentication or session data is unavailable
- Test the Settings view with different authentication states and user roles
- Verify that the panel provides meaningful operational insights without exposing sensitive information

### Enhanced Race Condition Issues

**Problem**: Concurrent approval attempts causing conflicts or inconsistent state
**Solution**:
- Verify that 409 already_resolved responses are properly handled
- Check that losing cards flip to winner's outcome instead of showing errors
- Ensure that decision attribution shows correct winner information
- Verify that local state updates are reconciled with server state
- Check browser console for JavaScript errors in race condition handling
- Test concurrent approval scenarios to verify proper resolution

### Enhanced Navigation Issues

**Problem**: Enhanced Approvals navigation item not appearing or pending badge not updating
**Solution**:
- Verify that APPROVAL_DECIDER_ROLES is properly configured with approver and platform-admin roles
- Check that useApprovalsInbox hook is enabled for users with required roles
- Verify that pending count calculation is working correctly
- Ensure that navigation visibility logic properly gates approvals menu item
- Check browser console for JavaScript errors in navigation logic
- Test with different user roles to verify proper access control

### Enhanced Live Decision Sync API Issues

**Problem**: Session detail API returning errors or incomplete data for decision sync
**Solution**:
- Check that platform gateway has /api/v1/sessions/{id} endpoint configured
- Verify agent-platform session store is running and accessible
- Review browser console for API call errors and network issues
- Ensure proper authentication for session detail requests
- Check that session detail responses include required fields (transcript, confirmations, evidence_turns)
- Verify that confirmation records include proper status and decision information
- Test session detail API directly to confirm backend functionality

### Enhanced Live Decision Sync Testing Issues

**Problem**: Insufficient test coverage for enhanced pending decision polling functionality
**Solution**:
- Verify that usePendingDecisionPoll.test.ts includes comprehensive test scenarios
- Check that tests cover baseline establishment, change detection, and settle window behavior
- Ensure tests validate streaming protection and session isolation
- Verify that race condition scenarios are properly tested
- Check that transport error handling is covered in test suite
- Test with mock session detail responses to verify proper timeline re-seeding
- **Updated**: Verify that tests cover time-based settle window functionality and visibility/focus kick mechanisms

### Enhanced Error Handling Issues

**Problem**: Various error types not handled properly in enhanced approval system
**Solution**:
- **Network Errors**: Check network connectivity and API endpoint availability
- **Authentication Failures**: Verify token validity and refresh mechanisms
- **Streaming Interruptions**: Check SSE connection stability and reconnection logic
- **Session Switching Errors**: Verify stream ownership handling during session transitions
- **Malformed Data**: Check defensive parsing for corrupted session data
- **Backend API Issues**: Verify API v6 schema compliance for risk level handling
- **Navigation Errors**: Check responsive breakpoint handling and drawer initialization
- **Content Spacing Issues**: Verify .view-container-inset class application and proper padding calculations
- **Stale Session Errors**: Check 404 error detection and retry logic for deleted or expired sessions
- **Evidence Persistence Errors**: Check evidence store availability and transcript-to-turn conversion logic
- **Monotonic Refresh Errors**: Check refresh sequence tracking and race condition prevention
- **Settle Window Errors**: Check time-based settle window calculation and visibility/focus kick mechanisms

### Sticky Request Banner Issues

**Problem**: Sticky request banner not appearing or behaving incorrectly
**Solution**:
- Verify IntersectionObserver is properly initialized and observing user message elements
- Check that .turn-request-banner.visible class is being applied when user message scrolls out of view
- Ensure chat-messages container is properly identified for observer root
- Verify CSS styles for sticky positioning and transitions are correctly applied
- Check browser console for JavaScript errors in IntersectionObserver logic
- Test with long conversations to verify banner appears when user message scrolls out of viewport

### Enhanced Markdown Rendering Issues

**Problem**: Markdown not rendering correctly, nested lists not working, or security vulnerabilities detected
**Solution**:
- Verify renderMarkdown function is properly escaping HTML content
- Check that javascript: and data: protocols are being blocked in link processing
- Ensure table rendering produces proper thead/tbody structure instead of disconnected tables
- Review test coverage for XSS prevention and quote escaping
- Check browser console for JavaScript errors in markdown processing
- Verify that all user input is properly escaped before HTML injection
- **Updated**: Verify that nested list rendering is working correctly with proper ordered/unordered list handling
- **Updated**: Check that pod log quoting is properly rendering in fenced code blocks with real line breaks
- **Updated**: Verify that ordered lists are properly wrapped in `<ol>` tags with correct numbering
- **Updated**: Test nested list scenarios to ensure indented sub-bullets are properly nested instead of rendered as literal text

### Enhanced Authentication Issues

**Problem**: Authentication state not properly managing disabled states for unauthenticated users
**Solution**:
- Verify that session creation controls are properly disabled when user is not authenticated
- Check that appropriate tooltips are displayed explaining authentication requirements
- Ensure disabled states are consistently applied across all unauthenticated user interactions
- Review browser console for JavaScript errors in authentication state management
- Test session creation workflow with unauthenticated user to verify proper disabled behavior

### Authoritative Re-seed Issues (v0.14.1)

**Problem**: External decisions not appearing in active chat view or reseedTurns not working correctly
**Solution**:
- Verify that reseedTurns method is properly integrated in useChatStream hook
- Check that same-session validation is working correctly to prevent cache poisoning
- Ensure that both live turns and cache entries are being replaced during re-seeding
- Verify that reseedTurns is a no-op for sessions not currently on screen
- Check browser console for JavaScript errors in reseedTurns logic
- Verify that ChatView is calling reseedTurns instead of setSession for decision sync
- Test with external decision sources to verify proper timeline updates
- Check that per-tab cache never shadows fresh state from external decisions

### Cache Shadowing Issues (v0.14.1)

**Problem**: Stale cached turns overriding fresh state during owner-side decision synchronization
**Solution**:
- Verify that reseedTurns is being used instead of setSession for decision sync
- Check that setSession cache shadow behavior is documented and understood
- Ensure that reseedTurns replaces both live turns AND cache entries
- Verify that same-session check prevents re-seeding for other sessions
- Check browser console for JavaScript errors in cache management
- Test scenario where setSession would stash current turns and restore stale cache
- Verify that later session switches restore fresh timeline, not shadowed stale one

### Enhanced Troubleshooting for v0.14.1

**Problem**: Various v0.14.1 patch issues affecting live decision sync
**Solution**:
- **reseedTurns Method**: Verify the new authoritative re-seed method is properly implemented and exported
- **Cache Shadowing Prevention**: Ensure reseedTurns prevents stale cached turns from overriding fresh state
- **Same-Session Validation**: Check that reseedTurns only operates on the session currently on screen
- **Cache Entry Replacement**: Verify that both live turns and per-tab cache entries are updated
- **No-Op Behavior**: Confirm reseedTurns is a no-op for sessions not on screen to prevent cache poisoning
- **Integration Testing**: Test complete flow from external decision to timeline update without manual refresh
- **Regression Testing**: Verify existing setSession functionality remains unchanged and working
- **Performance Impact**: Monitor for any performance issues introduced by the new reseedTurns method

### Turn-Anchored Confirmation Issues (SPEC-033)

**Problem**: Confirmation cards not anchoring to correct turns or legacy fallback not working properly
**Solution**:
- Verify that turn_index field is properly populated in confirmation records from backend
- Check that attachConfirmations function is correctly validating turn_index values
- Ensure that per-exchange anchoring is working for records with valid turn_index
- Verify that legacy fallback to newest turn is working for records without usable turn_index
- Check that synthetic turn creation is working for empty or unrecoverable transcripts
- Verify that pending confirmation cards properly set confirmationPending flag on their anchored turn
- Review browser console for JavaScript errors in turn anchoring logic
- Test with multi-park sessions to verify each card anchors to its specific parking turn

### Turn Anchoring Test Issues

**Problem**: Insufficient test coverage for turn anchoring functionality
**Solution**:
- Verify that transcript.test.ts includes comprehensive test scenarios for SPEC-033
- Check that tests cover per-exchange anchoring, pending anchoring, and legacy fallback scenarios
- Ensure tests validate turn_index validation and boundary conditions
- Verify that test coverage includes null, missing, and out-of-range turn_index scenarios
- Check that tests confirm proper behavior for empty transcripts with synthetic turn creation
- Test with mock confirmation records to verify proper anchoring behavior

### Enhanced Error Handling for Turn Anchoring

**Problem**: Various error types not handled properly in turn anchoring system
**Solution**:
- **Invalid turn_index Values**: Check that null, missing, and out-of-range values fall back to legacy anchoring
- **Empty Transcript Handling**: Verify synthetic turn creation works for sessions without transcript turns
- **Boundary Conditions**: Ensure proper handling of turn_index values at transcript boundaries
- **Backend API Issues**: Verify confirmation records include proper turn_index field from agent-platform
- **Frontend Parsing**: Check that turn_index values are properly parsed and validated in transcript.ts
- **Test Coverage**: Ensure comprehensive test coverage for all edge cases and error scenarios

**Updated** Added comprehensive troubleshooting guidance for the enhanced human-in-the-loop approval system with improved decision synchronization, arrival presentation polish, approvals view pagination, and session workspace synchronization. New sections cover enhanced live decision sync troubleshooting for time-based settle windows, visibility/focus kick mechanisms, and improved settle window functionality, comprehensive enhanced approvals inbox troubleshooting for client-side pagination, arrival presentation improvements, and race condition handling, comprehensive monotonic session workspace troubleshooting for refresh sequence tracking and race condition prevention, comprehensive enhanced navigation troubleshooting for persistent 64px icon rail issues, useNarrowViewport() hook problems, responsive breakpoint detection issues, drawer integration problems, dynamic aria-labels not updating correctly, and proper handling of .view-container-inset class for content spacing. Also added guidance for version and cache-related issues introduced by the cache-busting mechanism, and enhanced error handling for different failure types including network errors, authentication failures, and streaming interruptions. New sections cover sticky request banner issues, enhanced markdown rendering problems with proper nested list support, ordered/unordered list handling, pod log quoting in fenced code blocks, enhanced authentication state management for unauthenticated users, comprehensive stale session handling troubleshooting for 404 errors and retry logic failures, evidence persistence troubleshooting for transcript-to-turn conversion and evidence attachment issues, comprehensive model selection troubleshooting for catalog integration and session persistence, comprehensive ComposerSelectionBar troubleshooting for component rendering, styling, and integration issues, comprehensive Settings view troubleshooting for operational insights display and integration with existing components, comprehensive enhanced Approvals inbox troubleshooting for cross-session confirmation management, real-time polling, decision attribution, 30-day history browsing, and client-side pagination, comprehensive race condition troubleshooting for concurrent approval attempts, comprehensive tier-aware confirmation troubleshooting for badge display, role validation, and tier detection issues, comprehensive enhanced live decision sync troubleshooting for time-based settle windows, visibility/focus kick mechanisms, and session detail API integration, comprehensive authoritative re-seed troubleshooting for reseedTurns method, cache shadowing prevention, and v0.14.1 patch issues, comprehensive turn-anchored confirmation troubleshooting for SPEC-033 implementation including per-exchange anchoring, legacy fallback behavior, and comprehensive test coverage validation. **New sections cover Operations Document Repository troubleshooting for document creation, session selection, publishing, and viewing issues, including API connectivity problems, permission checks, digest rendering, and styling issues.**

**Section sources**
- [App.tsx:56-70](file://products/operator-portal/web-ui/app/src/App.tsx#L56-L70)
- [App.tsx:288-307](file://products/operator-portal/web-ui/app/src/App.tsx#L288-L307)
- [App.tsx:334-357](file://products/operator-portal/web-ui/app/src/App.tsx#L334-L357)
- [global.css:66-119](file://products/operator-portal/web-ui/app/src/theme/global.css#L66-L119)
- [ChatView.tsx:1-790](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L1-L790)
- [usePendingDecisionPoll.ts:1-170](file://products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts#L1-L170)
- [usePendingDecisionPoll.test.ts:1-297](file://products/operator-portal/web-ui/app/src/chat/__tests__/usePendingDecisionPoll.test.ts#L1-L297)
- [DocumentsView.tsx:1-597](file://products/operator-portal/web-ui/app/src/views/control/DocumentsView.tsx#L1-L597)
- [documents.ts:1-89](file://products/operator-portal/web-ui/app/src/api/documents.ts#L1-L89)
- [ComposerSelectionBar.tsx:1-48](file://products/operator-portal/web-ui/app/src/chat/ComposerSelectionBar.tsx#L1-L48)
- [ModelSelect.tsx:1-58](file://products/operator-portal/web-ui/app/src/chat/ModelSelect.tsx#L1-L58)
- [models.ts:1-31](file://products/operator-portal/web-ui/app/src/api/models.ts#L1-L31)
- [useChatStream.ts:1-454](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L1-L454)
- [useChatStreamReseed.test.ts:1-66](file://products/operator-portal/web-ui/app/src/stream/__tests__/useChatStreamReseed.test.ts#L1-L66)
- [transcript.ts:137-165](file://products/operator-portal/web-ui/app/src/chat/transcript.ts#L137-L165)
- [transcript.test.ts:312-365](file://products/operator-portal/web-ui/app/src/chat/__tests__/transcript.test.ts#L312-L365)
- [ApprovalsView.tsx:1-388](file://products/operator-portal/web-ui/app/src/views/control/ApprovalsView.tsx#L1-L388)
- [approvals.ts:1-20](file://products/operator-portal/web-ui/app/src/api/approvals.ts#L1-L20)
- [useSessionWorkspace.ts:1-218](file://products/operator-portal/web-ui/app/src/sessions/useSessionWorkspace.ts#L1-L218)
- [IncidentsView.tsx:1-600](file://products/operator-portal/web-ui/app/src/views/incidents/IncidentsView.tsx#L1-L600)
- [useSpeechRecognition.ts:1-135](file://products/operator-portal/web-ui/app/src/voice/useSpeechRecognition.ts#L1-L135)
- [markdown.ts:67-91](file://products/operator-portal/web-ui/app/src/chat/markdown.ts#L67-L91)
- [markdown.test.ts:59-77](file://products/operator-portal/web-ui/app/src/chat/__tests__/markdown.test.ts#L59-L77)
- [useChatStream.test.ts:380-432](file://products/operator-portal/web-ui/app/src/stream/__tests__/useChatStream.test.ts#L380-L432)
- [transcript.ts:55-70](file://products/operator-portal/web-ui/app/src/chat/transcript.ts#L55-L70)
- [transcript.test.ts:109-184](file://products/operator-portal/web-ui/app/src/chat/__tests__/transcript.test.ts#L109-L184)
- [ComposerSelectionBar.test.tsx:1-115](file://products/operator-portal/web-ui/app/src/chat/__tests__/ComposerSelectionBar.test.tsx#L1-L115)
- [ConfirmationCard.test.tsx:56-67](file://products/operator-portal/web-ui/app/src/chat/__tests__/ConfirmationCard.test.tsx#L56-L67)
- [ApprovalsView.test.tsx:1-242](file://products/operator-portal/web-ui/app/src/views/__tests__/ApprovalsView.test.tsx#L1-L242)
- [roles.ts:35-35](file://products/operator-portal/web-ui/app/src/roles.ts#L35-L35)
- [2026-08-26-live-check-patch.md:21-48](file://docs/agentic-aiops-platform/release-notes/2026-08-26-live-check-patch.md#L21-L48)
- [delivery-roadmap.md:354-360](file://docs/agentic-aiops-platform/delivery-roadmap.md#L354-L360)

## Conclusion

The Operator Portal provides a comprehensive, accessible, and customizable web interface for platform administration and monitoring within the Luban AIOPS ecosystem. The complete rebuild using React 18, TypeScript, and Vite delivers enterprise-grade functionality while maintaining simplicity and performance.

**Updated** The recent enhancements include significantly improved human-in-the-loop approval system with enhanced decision synchronization using time-based settle windows (300 seconds) instead of tick budgets, arrival presentation polish with better visual feedback and state management, approvals view pagination with client-side pagination for decision history (10 entries per page), and session workspace synchronization with monotonic refresh sequences to prevent race conditions during concurrent decision processing. The enhanced navigation system continues to provide a persistent 64px icon rail that maintains consistent layout anchoring across all views, improved responsive behavior with precise 992px breakpoint detection, better menu group title handling in collapsed states with visual dividers instead of clipped text, and enhanced mobile drawer navigation with proper positioning and z-index management. The navigation system continues to maintain accessibility across all views while providing consistent layout anchoring through dynamic aria-labels and proper content spacing management. Additional improvements include comprehensive mobile navigation with proper positioning and z-index management, enhanced security measures with improved XSS prevention in markdown rendering through comprehensive quote escaping and protocol filtering, improved session management with defensive parseStored function to handle malformed or corrupted session data, enhanced stream ownership handling during session switches to prevent cross-session data contamination, refined error handling for different failure types including network errors, authentication failures, and streaming interruptions, and backend API v6 schema compliance for risk level handling in pending calls. **Critical Enhancement**: The platform continues to include comprehensive stale session handling with automatic 404 error detection, missing reference tracking, and retry logic that automatically drops stale session references and falls back to server-side session auto-creation, ensuring more reliable chat functionality even when backend sessions become invalid. **Critical Enhancement**: The evidence persistence system continues to provide unified rendering of both live streamed and replayed evidence, ensuring operators see consistent evidence cards with request ID display and truncation markers regardless of evidence source. **Critical Enhancement**: The model selection system continues to provide flexible AI model choices with dynamic catalog integration and session-based persistence, while maintaining fail-open behavior when catalog services are unavailable. **New Feature**: The introduction of the ComposerSelectionBar component continues to provide an extensible control strip architecture that improves modularity and provides a designated mount point for future per-turn selections as referenced in SPEC-024. **Enhanced Feature**: The restoration of the Settings view as a read-only Session & Identity panel (R-6) continues to provide administrators with essential operational insights by displaying identity information, session details, and platform metadata using existing AuthContext and session workspace state. **Critical Enhancement**: The tier-aware HITL confirmation system continues to provide clear visual distinction between operator confirmations and approver-required scenarios with appropriate badge display and role-based permission validation, improving workflow clarity and user experience. **New Feature**: The enhanced Approvals inbox continues to provide designated approvers with comprehensive cross-session confirmation management capabilities including real-time polling, decision attribution, 30-day history browsing with client-side pagination, and race-resilient resolution semantics. **New Feature**: The complete Operations Document Repository provides shift summary creation, session selection, document publishing, and viewing capabilities for operational documentation with cross-session analysis and foreign session metadata inclusion. **Critical Enhancement**: The improved live decision sync system continues to provide time-based settle windows with change detection and settle windows to synchronize external decisions to active chat views without manual refresh, ensuring immediate reflection of decisions made from external sources such as the approver inbox or other browser sessions. **v0.14.1 Patch**: The platform continues to include the authoritative `reseedTurns` method that prevents cache shadowing during owner-side decision synchronization, ensuring that external decisions are properly synchronized to active chat views without being overridden by stale cached turns, with comprehensive test coverage validating race condition handling and streaming protection. **v0.15.0 Enhancement**: The confirmation card system continues to implement proper turn anchoring based on SPEC-033, ensuring each confirmation card renders under the exchange that parked it rather than stacking all cards under the newest turn, providing accurate historical context for multi-park sessions with comprehensive test coverage for per-exchange anchoring, pending anchoring, and legacy fallback scenarios. **v0.18.1 Enhancement**: The markdown rendering system now includes enhanced nested list support with proper ordered/unordered list handling, and pod log quoting improvements that render log excerpts in fenced code blocks for better readability in agent replies, addressing the v0.18.1 live-check findings where indented sub-bullets were previously dropped to literal "- text" paragraphs and ordered lists lost their numbering.

Key strengths of the enhanced portal include its modular React architecture, extensive customization options, strong accessibility features, seamless integration with backend services, comprehensive HITL confirmation bridging capabilities with tier-aware badge display, enhanced skills integration capabilities, improved navigation organization with sectioned grouping and persistent 64px icon rail for consistent layout anchoring, robust multi-session workspace management with monotonic refresh sequences, comprehensive incident triage with automated workflows, voice input support for hands-free operation, seamless deep linking between incidents and collaborative chat sessions, and enhanced mobile navigation with proper responsive behavior below 992px breakpoint. The enhanced security measures ensure protection against XSS attacks while maintaining full functionality. **Critical Enhancement**: The stale session handling system continues to provide robust error recovery for deleted or expired sessions, ensuring reliable chat functionality even in challenging network conditions or backend service issues. **Critical Enhancement**: The evidence persistence system continues to ensure complete traceability of tool executions regardless of whether they were observed live or reviewed from stored transcripts, with comprehensive truncation markers that clearly indicate payload limitations. **Critical Enhancement**: The model selection system continues to provide operators with flexible AI model choices while maintaining robust fail-open behavior and secure credential handling. **New Feature**: The ComposerSelectionBar component continues to provide an extensible architecture for model selection and future per-turn controls, improving modularity and maintainability. **Enhanced Feature**: The Settings view continues to provide read-only operational insights that complement the existing platform capabilities without introducing new security risks. **Critical Enhancement**: The tier-aware confirmation system continues to provide clear visual indicators distinguishing between operator confirmations and approver-required scenarios, improving workflow efficiency and user experience. **New Feature**: The enhanced Approvals inbox continues to provide designated approvers with comprehensive cross-session confirmation management capabilities including real-time polling, decision attribution, 30-day history browsing with client-side pagination, and race-resilient resolution semantics. **New Feature**: The complete Operations Document Repository continues to provide operational documentation capabilities with shift summary creation, session selection, document publishing, and viewing features for cross-session analysis and collaborative documentation workflows. **Critical Enhancement**: The improved live decision sync system continues to provide time-based settle windows with change detection and settle windows to synchronize external decisions to active chat views without manual refresh, ensuring operators see decisions from external sources without manual refresh. **v0.14.1 Patch**: The authoritative `reseedTurns` method continues to provide reliable owner-side live decision sync by preventing cache shadowing, ensuring that external decisions are properly synchronized to active chat views without being overridden by stale cached turns, with comprehensive test coverage validating race condition handling and streaming protection. **v0.15.0 Enhancement**: The turn-anchored confirmation system continues to provide accurate historical context for multi-park sessions by ensuring each confirmation card renders under the exchange that parked it, with comprehensive test coverage validating per-exchange anchoring, pending anchoring, and legacy fallback behavior. **v0.18.1 Enhancement**: The enhanced markdown rendering system continues to provide improved chat interface rendering quality with nested list support and proper ordered/unordered list handling, and pod log quoting enhancements that render log excerpts in fenced code blocks for better readability in agent replies.

**Additional Recent Enhancements:**
- **Sticky Request Banner System**: IntersectionObserver-based conversation context maintenance that keeps user requests visible during long replies and expanded evidence panels
- **Enhanced Markdown Table Rendering**: Proper semantic structure with thead/tbody separation instead of disconnected stacked tables
- **Comprehensive Test Coverage**: Robust XSS prevention testing including protocol filtering, quote escaping, and table structure validation
- **Improved Authentication State Management**: Proper disabled states for unauthenticated users in session creation controls with appropriate tooltips
- **Visual Consistency Improvements**: Inline brand display with platform version tags and full-width evidence panels for better readability
- **Critical Stale Session Handling**: Comprehensive missing reference tracking and automatic retry logic for 404 errors during stream opening, ensuring reliable chat functionality even when backend sessions become invalid
- **Evidence Persistence and Replay**: Unified rendering of both live streamed and replayed evidence with request ID display, truncation markers, and consistent visual presentation
- **Comprehensive Evidence Testing**: Test coverage for evidence frame mapping, truncation marker preservation, and out-of-range handling
- **Model Selection and Catalog Integration**: Dynamic model selector with catalog-driven rendering, session-based persistence, and fail-open UX behavior
- **Model Catalog API Testing**: Comprehensive test coverage for catalog discovery, error handling, and sparse payload normalization
- **ComposerSelectionBar Architecture**: Extensible control strip with intelligent collapse behavior and comprehensive TypeScript interfaces
- **ComposerSelectionBar Testing**: Comprehensive test coverage for collapse scenarios, model selection propagation, and browser API shimming
- **Settings View Restoration**: Read-only Session & Identity panel providing operational insights using existing AuthContext and session workspace state
- **Tier-Aware Confirmation System**: Enhanced HITL confirmation handling with tier detection logic, badge display system, and APPROVAL_DECIDER_ROLES for role-based permission validation
- **Enhanced Approvals Inbox Implementation**: Cross-session confirmation management with real-time polling, decision attribution, 30-day history browsing with client-side pagination, and race-resilient resolution semantics for designated approvers
- **Enhanced Approvals Inbox Testing**: Comprehensive test coverage for pending/history rendering, decision processing, race condition handling, pagination functionality, and role-based access control
- **Operations Document Repository Implementation**: Complete shift summary management with session selection, document creation, publishing, and viewing capabilities for operational documentation
- **Operations Document Repository Testing**: Comprehensive test coverage for document CRUD operations, session selection, foreign session handling, and digest rendering
- **Improved Live Decision Sync Implementation**: Time-based settle windows with visibility/focus kick mechanisms for external decision synchronization, including comprehensive test coverage for race condition handling and streaming protection
- **Authoritative Re-seed Mechanism (v0.14.1)**: Dedicated `reseedTurns` method that prevents cache shadowing during owner-side decision synchronization, with comprehensive test coverage validating same-session validation, cache replacement, and no-op behavior for other sessions
- **Turn-Anchored Confirmation System (SPEC-033)**: Per-exchange anchoring for confirmation cards with turn_index validation, legacy fallback behavior, and comprehensive test coverage for multi-park session accuracy
- **Monotonic Session Workspace**: Refresh sequence tracking to prevent race conditions during concurrent decision processing, ensuring data consistency across multiple approval operations
- **Enhanced Markdown Rendering (v0.18.1)**: Nested list support with proper ordered/unordered list handling, pod log quoting in fenced code blocks, and comprehensive test coverage for XSS prevention and list rendering

Future enhancements may include additional dashboard widgets, advanced analytics capabilities, mobile app integration, expanded customization options, enhanced collaboration features, further improvements to the HITL confirmation system with more sophisticated tier detection algorithms, expanded support for more complex multi-step approval workflows, additional voice input capabilities to meet evolving operational requirements, enhanced incident triage automation, expanded connector integrations, improved collaborative features for multi-operator incident response, and continued focus on mobile navigation optimization and responsive design improvements. Continued focus on security enhancements and user experience improvements will drive future development efforts. **Ongoing Enhancement**: Continued refinement of stale session handling and error recovery mechanisms to ensure maximum reliability in production environments. **Ongoing Enhancement**: Continued improvement of evidence persistence capabilities to provide even more comprehensive traceability and operational insights. **Ongoing Enhancement**: Continued enhancement of model selection capabilities to support more sophisticated model routing and performance optimization. **Ongoing Enhancement**: Continued development of the ComposerSelectionBar architecture to support additional per-turn selection capabilities as specified in SPEC-024. **Ongoing Enhancement**: Continued refinement of the Settings view to provide even more comprehensive operational insights while maintaining read-only security boundaries. **Ongoing Enhancement**: Continued improvement of tier-aware confirmation system with enhanced tier detection accuracy and more granular permission validation. **Ongoing Enhancement**: Continued enhancement of the enhanced Approvals inbox with additional cross-session management capabilities, improved decision workflow automation, and enhanced pagination functionality. **Ongoing Enhancement**: Continued enhancement of the Operations Document Repository with additional document types, enhanced session coverage analysis, and improved collaborative documentation workflows. **Ongoing Enhancement**: Continued refinement of the improved live decision sync system to optimize time-based settle windows, enhance change detection accuracy, and improve visibility/focus kick mechanisms for external decision synchronization. **Ongoing Enhancement**: Continued refinement of the authoritative `reseedTurns` method to ensure maximum reliability in preventing cache shadowing and maintaining timeline consistency during owner-side decision synchronization. **Ongoing Enhancement**: Continued refinement of the turn-anchored confirmation system to ensure maximum accuracy in multi-park session historical context and enhanced test coverage for edge cases. **Ongoing Enhancement**: Continued refinement of the enhanced markdown rendering system to improve nested list handling, pod log quoting, and overall chat interface rendering quality.