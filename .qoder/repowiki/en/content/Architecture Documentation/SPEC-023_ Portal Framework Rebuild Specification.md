# SPEC-023: Portal Framework Rebuild Specification

<cite>
**Referenced Files in This Document**
- [spec.md](file://docs/specs/SPEC-023-portal-framework-rebuild/spec.md)
- [plan.md](file://docs/specs/SPEC-023-portal-framework-rebuild/plan.md)
- [tasks.md](file://docs/specs/SPEC-023-portal-framework-rebuild/tasks.md)
- [spike.md](file://docs/workspace/portal-framework-rebuild-spike.md)
- [Dockerfile](file://products/operator-portal/Dockerfile)
- [nginx.conf](file://products/operator-portal/nginx.conf)
- [transport.ts](file://products/operator-portal/web-ui/app/src/stream/transport.ts)
- [decoder.ts](file://products/operator-portal/web-ui/app/src/stream/decoder.ts)
- [useChatStream.ts](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts)
- [useSessionWorkspace.ts](file://products/operator-portal/web-ui/app/src/sessions/useSessionWorkspace.ts)
- [ChatView.tsx](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx)
- [languages.ts](file://products/operator-portal/web-ui/app/src/voice/languages.ts)
- [useSpeechRecognition.ts](file://products/operator-portal/web-ui/app/src/voice/useSpeechRecognition.ts)
- [markdown.ts](file://products/operator-portal/web-ui/app/src/chat/markdown.ts)
- [markdown.test.ts](file://products/operator-portal/web-ui/app/src/chat/__tests__/markdown.test.ts)
- [chat.py](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py)
- [routes.py](file://products/agent-platform/src/agent_service/api/v2/routes.py)
- [session_service.py](file://products/agent-platform/src/agent_service/services/session_service.py)
- [session_store.py](file://products/agent-platform/src/agent_service/services/session_store.py)
- [test_session_service.py](file://products/agent-platform/tests/test_session_service.py)
- [transport.test.ts](file://products/operator-portal/web-ui/app/src/stream/__tests__/transport.test.ts)
- [decoder.test.ts](file://products/operator-portal/web-ui/app/src/stream/__tests__/decoder.test.ts)
- [languages.test.ts](file://products/operator-portal/web-ui/app/src/voice/__tests__/languages.test.ts)
- [package.json](file://products/operator-portal/web-ui/app/package.json)
- [App.tsx](file://products/operator-portal/web-ui/app/src/App.tsx)
- [DocumentsView.tsx](file://products/operator-portal/web-ui/app/src/views/workspace/DocumentsView.tsx)
- [ApprovalsView.tsx](file://products/operator-portal/web-ui/app/src/views/control/ApprovalsView.tsx)
- [AuditView.tsx](file://products/operator-portal/web-ui/app/src/views/audit/AuditView.tsx)
- [SkillsView.tsx](file://products/operator-portal/web-ui/app/src/views/control/SkillsView.tsx)
- [ToolsView.tsx](file://products/operator-portal/web-ui/app/src/views/control/ToolsView.tsx)
- [SPEC-042 spec.md](file://docs/specs/SPEC-042-portal-dependency-hygiene/spec.md)
- [SPEC-042 plan.md](file://docs/specs/SPEC-042-portal-dependency-hygiene/plan.md)
- [SPEC-042 tasks.md](file://docs/specs/SPEC-042-portal-dependency-hygiene/tasks.md)
</cite>

## Update Summary
**Changes Made**
- Added comprehensive dependency hygiene measures from SPEC-042 including antd v6 API migration and deprecation regression guard
- Updated React 19 migration with zero behavioral changes while maintaining all existing functionality
- Enhanced build toolchain with managed component refresh including Vite 8, TypeScript 5.9.x, Vitest 4.x, and jsdom 30.x
- Implemented comprehensive antd deprecation fixes across navigation drawers and alert components
- Extended security hardening with deprecation regression testing to prevent future maintenance debt accumulation

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Dependency Analysis](#dependency-analysis)
7. [Performance Considerations](#performance-considerments)
8. [Security Hardening](#security-hardening)
9. [Troubleshooting Guide](#troubleshooting-guide)
10. [Conclusion](#conclusion)
11. [Appendices](#appendices)

## Introduction
SPEC-023 rebuilds the operator portal as a React + TypeScript application built with Vite and styled via Ant Design X, while preserving the existing nginx-static serving model and all backend contracts. The rebuild delivers the multi-session workspace UI defined by SPEC-022 Appendix A, adds voice input as a composition surface, migrates existing views (Chat, Control, Workspace), and enforces Invariant II that human-in-the-loop approvals remain click-gated. No backend, policy, or audit behavior changes are introduced; this is a presentation-layer rebuild with a platform-owned SSE contract adapter isolating wire protocol knowledge.

**Updated** All four stages of progressive rollout are now complete with comprehensive security hardening measures including XSS vulnerability fixes in markdown rendering, robust session handling improvements, enhanced API contract validation for v6 schema compliance, and comprehensive testing coverage for security scenarios. Stage 1 (Portal Foundation) provides the build toolchain and theme system, Stage 2 (Platform-Owned SSE Contract Adapter) delivers transport and frame decoding with full test coverage, Stage 3 (Session Workspace UI) implements the complete multi-session management interface with streaming infrastructure, and Stage 4 (Voice Input) provides speech recognition with graceful degradation and consistent `input_modality` parameter propagation across all chat endpoints.

**Enhanced** The portal framework has been further strengthened by SPEC-042 which extends the foundation with dependency hygiene measures, antd deprecation fixes, and React 19 migration while maintaining zero behavioral changes. This includes comprehensive antd v6 API migration, deprecation regression guards, and managed component refreshes across the entire dependency tree.

## Project Structure
The portal currently ships as vanilla HTML/CSS/JS served by nginx. SPEC-023 introduces a new web-ui source tree under `products/operator-portal/web-ui/` with a multi-stage Docker build that produces content-hashed static assets. Nginx continues to proxy `/api/` to the platform gateway and serve SPA fallback through `try_files`.

```mermaid
graph TB
subgraph "Operator Portal"
NGINX["nginx.conf<br/>proxy /api/ → gateway"]
STATIC["Static assets<br/>index.html + hashed bundles"]
WEBUI["React App<br/>Vite + TypeScript"]
end
subgraph "Platform Gateway"
GW_CHAT["/api/v1/chat*"]
GW_SESSIONS["/api/v1/sessions*"]
GW_STREAM["/api/v1/chat/stream<br/>+ input_modality"]
end
subgraph "Agent Service"
AG_STREAM["/api/v2/chat/stream<br/>+ input_modality"]
end
NGINX --> STATIC
NGINX --> WEBUI
NGINX --> GW_CHAT
NGINX --> GW_SESSIONS
NGINX --> GW_STREAM
GW_STREAM --> AG_STREAM
```

**Diagram sources**
- [nginx.conf:8-17](file://products/operator-portal/nginx.conf#L8-L17)
- [Dockerfile:13-31](file://products/operator-portal/Dockerfile#L13-L31)
- [chat.py:90-143](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L90-L143)
- [routes.py:135-165](file://products/agent-platform/src/agent_service/api/v2/routes.py#L135-L165)

**Section sources**
- [Dockerfile:1-29](file://products/operator-portal/Dockerfile#L1-L29)
- [nginx.conf:1-32](file://products/operator-portal/nginx.conf#L1-L32)
- [plan.md:19-34](file://docs/specs/SPEC-023-portal-framework-rebuild/plan.md#L19-L34)

## Core Components
- **Stage 1 - Portal Foundation**: Complete build toolchain with Vite, React 18, TypeScript, and Ant Design X theming system
- **Stage 2 - Platform-Owned SSE Contract Adapter**: Single module owning transport (`fetch` + `ReadableStream`) and frame-to-model mapping for schema v6 events with comprehensive test coverage
- **Stage 3 - Session Workspace UI**: Multi-session workspace panel with title, last-active time, pending-confirmation badge support, switch/resume functionality, and incident deep links
- **Stage 4 - Voice Input**: Speech recognition using Web Speech API with language selection, graceful degradation, and consistent `input_modality` parameter propagation
- View migration: Chat, Control (audit, permissions, tools, skills), and Workspace (incidents) migrated with role-scoped visibility preserved

**Updated** All four stages are now production-ready with full test coverage, complete streaming infrastructure supporting voice-readiness parity across both POST and streaming chat endpoints, and comprehensive security hardening measures including XSS protection and robust session handling.

**Enhanced** The foundation has been further strengthened by SPEC-042 with dependency hygiene measures including antd v6 API migration, React 19 upgrade, and comprehensive deprecation regression guards that prevent future maintenance debt accumulation.

Acceptance criteria and detailed behaviors are specified per requirement in the spec and plan documents.

**Section sources**
- [spec.md:57-182](file://docs/specs/SPEC-023-portal-framework-rebuild/spec.md#L57-L182)
- [plan.md:36-90](file://docs/specs/SPEC-023-portal-framework-rebuild/plan.md#L36-L90)
- [tasks.md:5-43](file://docs/specs/SPEC-023-portal-framework-rebuild/tasks.md#L5-L43)

## Architecture Overview
The rebuild keeps the same runtime deployment shape: nginx serves static assets and proxies API calls to the platform gateway. The key architectural change is a thin adapter layer between the React UI and the gateway's streaming endpoints, insulating components from stream schema details.

**Updated** The four-stage progressive rollout is now complete with comprehensive security hardening, providing a robust streaming infrastructure with consistent `input_modality` parameter propagation across the entire request chain, from gateway streaming endpoint to agent service, with full voice input support and XSS protection.

**Enhanced** The architecture has been further hardened by SPEC-042 with dependency hygiene measures that ensure long-term maintainability through automated deprecation detection and managed component refresh cycles.

```mermaid
sequenceDiagram
participant UI as "React UI"
participant Voice as "Voice Input"
participant Adapter as "SSE Contract Adapter"
participant Markdown as "Markdown Renderer"
participant Nginx as "Nginx"
participant GW as "Platform Gateway"
participant Agent as "Agent Platform"
Voice->>UI : Speech recognition (Web Speech API)
UI->>Adapter : Start chat stream (message, session_id, input_modality)
Adapter->>Nginx : GET /api/v1/chat/stream?input_modality=voice
Nginx->>GW : Forward request with Bearer token + input_modality
GW->>GW : Log & audit input_modality metadata
GW->>Agent : Proxy chat stream with input_modality
Agent-->>GW : Stream frames (schema v6)
GW-->>Nginx : SSE frames
Nginx-->>Adapter : ReadableStream frames
Adapter->>Adapter : Map frames → typed models
Adapter->>Markdown : Sanitize content (escape-first)
Markdown-->>Adapter : XSS-safe HTML
Adapter-->>UI : Typed deltas, evidence, confirmations
```

**Diagram sources**
- [chat.py:90-143](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L90-L143)
- [routes.py:135-165](file://products/agent-platform/src/agent_service/api/v2/routes.py#L135-L165)
- [nginx.conf:8-17](file://products/operator-portal/nginx.conf#L8-L17)
- [markdown.ts:1-88](file://products/operator-portal/web-ui/app/src/chat/markdown.ts#L1-L88)
- [spike.md:93-113](file://docs/workspace/portal-framework-rebuild-spike.md#L93-L113)

## Detailed Component Analysis

### Stage 1: Portal Foundation and Build Toolchain
**Completed** The foundation stage provides the complete build infrastructure including Vite + React 18 + TypeScript setup, multi-stage Docker build process, and Ant Design X theming system.

- **Build System**: Vite builds React + TypeScript into content-hashed assets under `dist/`; Dockerfile gains a Node build stage and retains nginx runtime
- **Theme System**: Dark theme rebuilt from current `:root` CSS custom properties into Ant Design design tokens (`XProvider` theme), preserving slate palette and layout language
- **Version Management**: `PLATFORM_VERSION` injected at build time from root `VERSION`; validator updated to assert it at its new home
- **Serving Strategy**: Nginx serves `index.html` with `no-store` and may cache hashed assets immutably; SPA fallback remains via `try_files`

**Enhanced** The build toolchain has been significantly upgraded by SPEC-042 with modern dependencies including Vite 8.x, TypeScript 5.9.x, Vitest 4.x, and React 19.x while maintaining zero behavioral changes. The managed component refresh ensures all dependencies stay current with proper version lockstep.

```mermaid
flowchart TD
Dev["Source Tree<br/>web-ui/src/*"] --> Build["Vite Build<br/>content-hash assets"]
Build --> Dist["dist/<br/>hashed JS/CSS + index.html"]
Dist --> Image["Multi-stage Docker image<br/>node build → nginx runtime"]
Image --> Deploy["Nginx serves static + proxies /api/"]
```

**Diagram sources**
- [plan.md:19-34](file://docs/specs/SPEC-023-portal-framework-rebuild/plan.md#L19-L34)
- [Dockerfile:13-31](file://products/operator-portal/Dockerfile#L13-L31)
- [nginx.conf:19-41](file://products/operator-portal/nginx.conf#L19-L41)

**Section sources**
- [plan.md:19-34](file://docs/specs/SPEC-023-portal-framework-rebuild/plan.md#L19-L34)
- [spec.md:57-81](file://docs/specs/SPEC-023-portal-framework-rebuild/spec.md#L57-L81)
- [tasks.md:5-12](file://docs/specs/SPEC-023-portal-framework-rebuild/tasks.md#L5-L12)

### Stage 2: Platform-Owned SSE Contract Adapter
**Completed** The adapter stage delivers a complete streaming infrastructure with transport, decoder, and comprehensive test coverage.

- **Transport Layer**: `transport.ts` wraps `fetch` with `response.body.getReader()` and an abort controller to support switching sessions mid-stream
- **Frame Decoder**: `decoder.ts` parses SSE frames and maps event types to typed models (agent deltas, evidence items, confirmation cards, terminal states)
- **Hook Interface**: `useChatStream.ts` exposes typed models to views with session management and turn caching
- **Test Coverage**: Comprehensive unit tests covering every schema v6 event type, truncation behavior, and modality parameter handling

```mermaid
flowchart TD
Start(["Receive SSE Frame"]) --> Type{"Event Type?"}
Type --> |agent_delta| Delta["Emit AgentDelta"]
Type --> |tool_result| Evidence["Emit EvidenceItem<br/>with full-output expander"]
Type --> |confirmation_request| Confirm["Emit ConfirmationCard"]
Type --> |confirmation_result| Resolve["Resolve Confirmation"]
Type --> |close/truncation| Terminal["Emit StreamTerminal"]
Delta --> Next["Next Frame"]
Evidence --> Next
Confirm --> Next
Resolve --> Next
Terminal --> End(["Stream Complete"])
```

**Diagram sources**
- [plan.md:36-50](file://docs/specs/SPEC-023-portal-framework-rebuild/plan.md#L36-L50)
- [spec.md:83-107](file://docs/specs/SPEC-023-portal-framework-rebuild/spec.md#L83-L107)

**Section sources**
- [plan.md:36-50](file://docs/specs/SPEC-023-portal-framework-rebuild/plan.md#L36-L50)
- [spec.md:83-107](file://docs/specs/SPEC-023-portal-framework-rebuild/spec.md#L83-L107)
- [tasks.md:14-19](file://docs/specs/SPEC-023-portal-framework-rebuild/tasks.md#L14-L19)

### Stage 3: Session Workspace UI
**Completed** The workspace stage implements the complete multi-session management interface with all required features.

- **Session Panel**: Lists sessions via `GET /api/v1/sessions`, capped at 50, showing title, relative last-active time, and amber badge when `pending_confirmation` is true
- **Switch/Resume**: Loads transcript via `GET /api/v1/sessions/{id}` (or explicit history-unavailable state), repoints active stream and confirm endpoints, persists active session id per tab, and closes previous streams
- **New/Delete Operations**: New session uses existing create path; delete requires in-UI confirmation and returns 409 for parked confirmations; 404 responses do not reveal ownership
- **Incident Deep Links**: Opens additional sessions in the panel rather than replacing the active one

```mermaid
sequenceDiagram
participant UI as "Workspace Panel"
participant SessionService as "Session Service"
participant Nginx as "Nginx"
participant GW as "Platform Gateway"
UI->>Nginx : GET /api/v1/sessions
Nginx->>GW : Forward with Bearer
GW->>SessionService : List sessions (owner validation)
SessionService-->>GW : Sessions list (cap 50, pending_confirmation)
GW-->>Nginx : Sessions list (cap 50, pending_confirmation)
Nginx-->>UI : Render panel + badges
UI->>Nginx : GET /api/v1/sessions/{id}
Nginx->>GW : Forward with Bearer
GW->>SessionService : Get session (owner validation)
SessionService-->>GW : Transcript or {transcript_available : false}
GW-->>Nginx : Transcript or {transcript_available : false}
Nginx-->>UI : Load transcript or history-unavailable state
```

**Diagram sources**
- [useSessionWorkspace.ts:59-86](file://products/operator-portal/web-ui/app/src/sessions/useSessionWorkspace.ts#L59-L86)
- [ChatView.tsx:473-515](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L473-L515)
- [session_service.py:19-61](file://products/agent-platform/src/agent_service/services/session_service.py#L19-L61)

**Section sources**
- [spec.md:108-135](file://docs/specs/SPEC-023-portal-framework-rebuild/spec.md#L108-L135)
- [plan.md:52-64](file://docs/specs/SPEC-023-portal-framework-rebuild/plan.md#L52-L64)
- [tasks.md:21-27](file://docs/specs/SPEC-023-portal-framework-rebuild/tasks.md#L21-L27)

### Stage 4: Voice Input and Invariant II
**Completed** Voice input implementation provides speech recognition with graceful degradation and maintains security invariants.

- **Speech Recognition**: Composer integrates Ant Design X Sender speech input; voice turns send `input_modality: "voice"` while text turns default to `text`
- **Language Selection**: Offers supported locales (minimum `en-US` and `zh-CN`), defaults to browser locale when available, falls back to `en-US`, and persists locally
- **Security Guarantee**: Invariant II enforced - no voice-driven path can approve or deny; confirmation decisions remain button-only on confirmation cards
- **Graceful Degradation**: Detects Web Speech API availability; hides/disables affordance when unsupported

```mermaid
flowchart TD
Start(["Voice Capture"]) --> Recognize["Web Speech API<br/>recognize(lang)"]
Recognize --> Text["Compose text payload"]
Text --> Send["POST /api/v1/chat<br/>input_modality: 'voice'"]
Send --> Policy["Policy evaluation unchanged"]
Policy --> HITL{"Parked confirmation?"}
HITL --> |Yes| Card["Render confirmation card<br/>buttons only"]
HITL --> |No| Continue["Resume stream"]
Card --> Decision["User clicks approve/deny<br/>POST /api/v1/chat/confirm"]
Decision --> Resume["Resume session stream"]
Resume --> Audit["Audit trail includes<br/>input_modality metadata"]
```

**Diagram sources**
- [spec.md:137-159](file://docs/specs/SPEC-023-portal-framework-rebuild/spec.md#L137-L159)

**Section sources**
- [spec.md:137-159](file://docs/specs/SPEC-023-portal-framework-rebuild/spec.md#L137-L159)
- [plan.md:66-79](file://docs/specs/SPEC-023-portal-framework-rebuild/plan.md#L66-L79)
- [tasks.md:29-34](file://docs/specs/SPEC-023-portal-framework-rebuild/tasks.md#L29-L34)

### Voice-Readiness Parity Implementation
**Completed** R-4 implementation provides consistent voice-readiness support across both POST and streaming chat endpoints through the `input_modality` parameter.

- **Gateway Streaming Endpoint**: `GET /api/v1/chat/stream` accepts `input_modality` query parameter (`text`|`voice`, default `text`) mirroring POST `/api/v1/chat`'s body field
- **Agent Service Streaming Endpoint**: `GET /api/v2/chat/stream` accepts `input_modality` query parameter with identical semantics
- **Metadata-Only Semantics**: Modality is recorded on audit/log surfaces but never changes policy, auto-allow, or HITL outcomes
- **Audit Trail Generation**: Both `chat_started` and `chat_completed` events include `input_modality` in their details for complete conversation provenance

```mermaid
flowchart TD
Client["Client Request"] --> GW["Gateway /api/v1/chat/stream"]
GW --> Audit["Log & Audit<br/>input_modality metadata"]
GW --> Agent["Agent Service /api/v2/chat/stream"]
Agent --> Kernel["Kernel Processing"]
Kernel --> Response["Stream Response"]
Response --> Client
Audit -.-> Provenance["Complete Conversation<br/>Provenance Tracking"]
```

**Diagram sources**
- [chat.py:90-143](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L90-L143)
- [routes.py:135-165](file://products/agent-platform/src/agent_service/api/v2/routes.py#L135-L165)

**Section sources**
- [chat.py:90-143](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L90-L143)
- [routes.py:135-165](file://products/agent-platform/src/agent_service/api/v2/routes.py#L135-L165)
- [transport.ts:31-49](file://products/operator-portal/web-ui/app/src/stream/transport.ts#L31-L49)
- [transport.test.ts:40-47](file://products/operator-portal/web-ui/app/src/stream/__tests__/transport.test.ts#L40-L47)

### Build Toolchain and Serving
**Completed** The build system provides content-hashed assets with immutable caching and proper SPA fallback handling.

- **Vite Build**: Builds React + TypeScript into content-hashed assets under `dist/`; Dockerfile gains a Node build stage and retains nginx runtime
- **Cache Strategy**: Nginx serves `index.html` with `no-store` and may cache hashed assets immutably; SPA fallback remains via `try_files`
- **Version Injection**: `PLATFORM_VERSION` injected at build time from root `VERSION`; validator updated to assert it at its new home

**Enhanced** The build toolchain has been significantly upgraded by SPEC-042 with modern dependencies including Vite 8.x, TypeScript 5.9.x, Vitest 4.x, and React 19.x while maintaining zero behavioral changes. The managed component refresh ensures all dependencies stay current with proper version lockstep.

```mermaid
flowchart TD
Dev["Source Tree<br/>web-ui/src/*"] --> Build["Vite Build<br/>content-hash assets"]
Build --> Dist["dist/<br/>hashed JS/CSS + index.html"]
Dist --> Image["Multi-stage Docker image<br/>node build → nginx runtime"]
Image --> Deploy["Nginx serves static + proxies /api/"]
```

**Diagram sources**
- [plan.md:19-34](file://docs/specs/SPEC-023-portal-framework-rebuild/plan.md#L19-L34)
- [Dockerfile:13-31](file://products/operator-portal/Dockerfile#L13-L31)
- [nginx.conf:19-41](file://products/operator-portal/nginx.conf#L19-L41)

**Section sources**
- [plan.md:19-34](file://docs/specs/SPEC-023-portal-framework-rebuild/plan.md#L19-L34)
- [spec.md:57-81](file://docs/specs/SPEC-023-portal-framework-rebuild/spec.md#L57-L81)
- [tasks.md:5-12](file://docs/specs/SPEC-023-portal-framework-rebuild/tasks.md#L5-L12)

### View Migration and Role-Scoped Visibility
**Completed** All existing portal views have been migrated with parity to current functionality and role-scoped visibility preserved.

- **View Migration**: Chat, Control (audit, permissions, tools, skills), and Workspace (incidents) views migrated with parity to current functionality
- **Navigation**: Sectioned navigation auto-hides based on token roles and policy matrix; audit view remains auditor/platform-admin only
- **Authentication**: Keycloak OIDC login/logout, token refresh, and per-request `Bearer` behavior are unchanged

**Enhanced** All views have been updated to use non-deprecated antd v6 APIs including Drawer `size` property instead of `width`, and Alert `title` property instead of `message`, ensuring zero deprecation warnings in the test suite.

**Section sources**
- [spec.md:161-182](file://docs/specs/SPEC-023-portal-framework-rebuild/spec.md#L161-L182)
- [plan.md:81-90](file://docs/specs/SPEC-023-portal-framework-rebuild/plan.md#L81-L90)
- [tasks.md:36-43](file://docs/specs/SPEC-023-portal-framework-rebuild/tasks.md#L36-L43)

### Voice Language Resolution and Recognition
**Completed** Voice language selection provides explicit operator choice with browser locale detection and persistent storage.

- **Language Selector**: Supports minimum English (`en-US`) and Mandarin (`zh-CN`) with constant-driven configuration
- **Browser Integration**: Defaults to browser locale when available, falls back to `en-US`, persists selection in localStorage
- **Recognition Wrapper**: Web Speech API wrapper with graceful error handling and capability detection
- **Security Isolation**: Language selection affects only client-side recognition, never sent to backend or audit trail

```mermaid
flowchart TD
Start(["Voice Language Selection"]) --> Browser["Detect Browser Locale"]
Browser --> Supported{"Supported Code?"}
Supported --> |Yes| Use["Use Browser Locale"]
Supported --> |No| Fallback["Fallback to en-US"]
Use --> Persist["Persist to localStorage"]
Fallback --> Persist
Persist --> Recognize["Web Speech API<br/>recognize(selected_lang)"]
Recognize --> Text["Transcribed Text"]
```

**Diagram sources**
- [languages.ts:23-41](file://products/operator-portal/web-ui/app/src/voice/languages.ts#L23-L41)
- [useSpeechRecognition.ts:81-123](file://products/operator-portal/web-ui/app/src/voice/useSpeechRecognition.ts#L81-L123)

**Section sources**
- [languages.ts:1-60](file://products/operator-portal/web-ui/app/src/voice/languages.ts#L1-L60)
- [useSpeechRecognition.ts:1-135](file://products/operator-portal/web-ui/app/src/voice/useSpeechRecognition.ts#L1-L135)
- [ChatView.tsx:487-511](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L487-L511)

## Dependency Analysis
The rebuild depends on existing gateway endpoints and shared contracts without introducing new backend dependencies.

**Updated** The four-stage implementation extends dependencies to include consistent `input_modality` parameter handling across platform gateway and agent service streaming endpoints, plus Web Speech API integration for voice input, and comprehensive security validation for markdown rendering.

**Enhanced** The dependency tree has been comprehensively refreshed by SPEC-042 with modern versions including React 19.x, Vite 8.x, TypeScript 5.9.x, Vitest 4.x, and jsdom 30.x, while maintaining zero behavioral changes and adding comprehensive deprecation regression guards.

```mermaid
graph LR
UI["React UI"] --> Adapter["SSE Contract Adapter"]
Adapter --> GW["Platform Gateway"]
GW --> Contracts["Shared Schemas"]
GW --> Agent["Agent Platform"]
Contracts --> ChatReq["agent-chat-request.schema.json"]
Contracts --> Confirm["chat-confirm.schema.json"]
GW -.-> Modality["input_modality<br/>metadata parameter"]
Agent -.-> Modality
Modality --> Audit["Audit Trail<br/>Conversation Provenance"]
UI -.-> SpeechAPI["Web Speech API<br/>Browser Integration"]
SpeechAPI -.-> VoiceInput["Voice Composition"]
UI -.-> Markdown["XSS-Safe Rendering"]
Markdown -.-> Security["Escape-First Security Model"]
UI -.-> DepHygiene["Deprecation Guards<br/>Managed Refresh"]
DepHygiene -.-> ModernStack["React 19 + Vite 8<br/>TypeScript 5.9 + Vitest 4"]
```

**Diagram sources**
- [transport.ts:31-49](file://products/operator-portal/web-ui/app/src/stream/transport.ts#L31-L49)
- [chat.py:90-143](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L90-L143)
- [routes.py:135-165](file://products/agent-platform/src/agent_service/api/v2/routes.py#L135-L165)
- [useSpeechRecognition.ts:38-46](file://products/operator-portal/web-ui/app/src/voice/useSpeechRecognition.ts#L38-L46)
- [markdown.ts:1-88](file://products/operator-portal/web-ui/app/src/chat/markdown.ts#L1-L88)
- [package.json:15-33](file://products/operator-portal/web-ui/app/package.json#L15-L33)

**Section sources**
- [spec.md:210-218](file://docs/specs/SPEC-023-portal-framework-rebuild/spec.md#L210-L218)
- [plan.md:97-108](file://docs/specs/SPEC-023-portal-framework-rebuild/plan.md#L97-L108)

## Performance Considerations
- **Session Panel Polling**: Refresh at most every 30 seconds plus lifecycle-triggered refresh; cap-50 list does not require virtualization
- **Streaming Performance**: Use `fetch` + `ReadableStream` with abort controllers to avoid memory leaks during session switches
- **Asset Caching**: Content-hashed assets enable immutable caching; `index.html` remains `no-store` to ensure fresh shell load
- **Bundle Optimization**: Route-level code splitting mitigates heavier dependency tree from React + antd/Ant Design X
- **Voice Recognition**: Web Speech API runs entirely client-side with no network overhead; graceful degradation when unsupported

**Updated** The four-stage implementation maintains performance characteristics while adding minimal overhead for `input_modality` parameter processing, audit trail generation, client-side speech recognition, and XSS-safe markdown rendering.

**Enhanced** The dependency hygiene measures from SPEC-042 improve long-term performance through modernized build toolchain (Vite 8.x), optimized bundling, and reduced bundle sizes from updated dependencies while maintaining zero behavioral changes.

[No sources needed since this section provides general guidance]

## Security Hardening
**New Section** Comprehensive security hardening measures have been implemented across the portal framework to address XSS vulnerabilities and enhance session security.

### XSS Vulnerability Fixes in Markdown Rendering Pipeline
- **Escape-First Security Model**: All user-provided content passes through HTML escaping before any markup introduction
- **JavaScript URL Protection**: Explicitly blocks `javascript:`, `data:`, and other dangerous URL schemes
- **Attribute Context Protection**: Proper quote escaping prevents attribute breakout attacks
- **Link Security**: Only `http(s)` URLs are allowed; all links include `rel="noopener noreferrer"` attributes

### Robust Session Handling Improvements
- **Owner Validation**: All session operations validate session ownership with 404 responses for foreign sessions (anti-enumeration pattern)
- **Race Condition Protection**: Named session creation handles Redis last-writer-wins race conditions safely
- **Parked Confirmation Protection**: Sessions with pending confirmations cannot be deleted until resolved
- **TTL Management**: Automatic cleanup of expired sessions with configurable limits

### Enhanced API Contract Validation for v6 Schema Compliance
- **Schema Validation**: All streaming events validated against v6 schema contracts
- **Type Safety**: Strict typing enforcement for all API parameters and responses
- **Error Handling**: Consistent error responses with appropriate HTTP status codes
- **Audit Trail**: Complete audit logging for all session operations and chat interactions

### Comprehensive Testing Coverage for Security Scenarios
- **XSS Attack Prevention**: Tests verify protection against script injection, attribute breakout, and dangerous URL schemes
- **Session Security**: Tests validate owner isolation, foreign session access prevention, and parked confirmation handling
- **Contract Compliance**: Automated validation of API responses against JSON schemas
- **Edge Case Coverage**: Tests for malformed input, concurrent operations, and failure scenarios

### Deprecation Regression Guard
**New** SPEC-042 introduces comprehensive deprecation regression testing to prevent future maintenance debt accumulation.

- **Zero Tolerance Policy**: Any antd deprecation warning in test output immediately fails the suite
- **Comprehensive Monitoring**: Intercepts console.error/console.warn during test execution
- **Automatic Detection**: Identifies deprecated prop usage across all 48 Drawer width and 5 Alert message instances
- **Preventive Measures**: Ensures deprecations are caught at pull request time rather than accumulating silently

```mermaid
flowchart TD
UserInput["User Input"] --> Escape["HTML Escape<br/>(&lt;&gt;&quot;&amp;)"]
Escape --> Markup["Markup Processing"]
Markup --> LinkCheck{"URL Check"}
LinkCheck --> |http(s)| SafeLink["Safe Link<br/>rel='noopener noreferrer'"]
LinkCheck --> |dangerous| PlainText["Plain Text<br/>(blocked)")
SafeLink --> Output["Secure HTML Output"]
PlainText --> Output
Output --> XSSProtection["XSS Protection Verified"]
DeprecationCheck["Deprecation Guard"] --> TestSuite["Vitest Suite"]
TestSuite --> ZeroWarnings["Zero Deprecation Warnings"]
ZeroWarnings --> Maintainability["Long-term Maintainability"]
```

**Diagram sources**
- [markdown.ts:10-55](file://products/operator-portal/web-ui/app/src/chat/markdown.ts#L10-L55)
- [markdown.test.ts:7-57](file://products/operator-portal/web-ui/app/src/chat/__tests__/markdown.test.ts#L7-L57)
- [SPEC-042 plan.md:32-42](file://docs/specs/SPEC-042-portal-dependency-hygiene/plan.md#L32-L42)

**Section sources**
- [markdown.ts:1-88](file://products/operator-portal/web-ui/app/src/chat/markdown.ts#L1-L88)
- [markdown.test.ts:1-63](file://products/operator-portal/web-ui/app/src/chat/__tests__/markdown.test.ts#L1-L63)
- [session_service.py:19-61](file://products/agent-platform/src/agent_service/services/session_service.py#L19-L61)
- [routes.py:72-101](file://products/agent-platform/src/agent_service/api/v2/routes.py#L72-L101)
- [SPEC-042 spec.md:76-87](file://docs/specs/SPEC-042-portal-dependency-hygiene/spec.md#L76-L87)

## Troubleshooting Guide
- **Stream Framing Issues**: Verify adapter mapping against fixture frames for every schema v6 event type; check terminal state handling on stream close/truncation
- **Confirmation Anchoring**: Ensure confirmation cards remain bound to their parking session; confirm that approve/deny resumes the correct session stream
- **Voice Input Degradation**: Detect Web Speech API availability; hide/disable affordance when unsupported; validate language selector defaults and persistence
- **Version Mismatch**: Ensure `PLATFORM_VERSION` injection matches root `VERSION`; run `make validate-version` to assert constant location

**Updated** Security-focused troubleshooting for the completed four-stage rollout with comprehensive security hardening:
- **XSS Attack Detection**: Monitor for script injection attempts, attribute breakout attacks, and dangerous URL schemes in markdown rendering
- **Session Security Issues**: Validate owner isolation, check for foreign session access attempts, and monitor parked confirmation states
- **Modality Validation Errors**: Check that `input_modality` parameter values are restricted to `text` or `voice`; invalid values return 422 status codes
- **Audit Trail Gaps**: Verify that `chat_started` and `chat_completed` events include `input_modality` in their details for complete conversation provenance
- **Streaming Endpoint Parity**: Ensure both POST and streaming endpoints handle `input_modality` consistently across platform gateway and agent service
- **Test Coverage Verification**: Confirm all unit tests pass for transport, decoder, session workspace, voice language resolution, and security scenarios
- **Language Resolution Issues**: Validate browser locale detection, primary subtag mapping, and localStorage persistence for voice language selection
- **Speech Recognition Errors**: Check microphone permissions, browser compatibility, and error message mapping for common recognition failures
- **Contract Validation Failures**: Verify API responses conform to v6 schemas and investigate schema validation errors

**Enhanced** Deprecation-related troubleshooting for SPEC-042 implementation:
- **Deprecation Warning Detection**: Monitor vitest output for `[antd: …] … deprecated` warnings which now fail the suite automatically
- **Drawer Width Issues**: Verify all Drawer components use `size` property instead of deprecated `width` property
- **Alert Message Issues**: Confirm all Alert components use `title` property instead of deprecated `message` property
- **Dependency Version Conflicts**: Check package-lock.json consistency and resolve peer dependency warnings after updates
- **Build Toolchain Issues**: Verify Vite 8.x compatibility with plugin-react 6.x and TypeScript 5.9.x configuration
- **React 19 Migration Issues**: Address any React 19 type tightening or removed legacy APIs with behavior-preserving edits

**Section sources**
- [plan.md:110-123](file://docs/specs/SPEC-023-portal-framework-rebuild/plan.md#L110-L123)
- [spec.md:83-107](file://docs/specs/SPEC-023-portal-framework-rebuild/spec.md#L83-L107)
- [tasks.md:14-19](file://docs/specs/SPEC-023-portal-framework-rebuild/tasks.md#L14-L19)
- [transport.test.ts:75-92](file://products/operator-portal/web-ui/app/src/stream/__tests__/transport.test.ts#L75-L92)
- [decoder.test.ts:203-208](file://products/operator-portal/web-ui/app/src/stream/__tests__/decoder.test.ts#L203-L208)
- [languages.test.ts:22-42](file://products/operator-portal/web-ui/app/src/voice/__tests__/languages.test.ts#L22-L42)
- [markdown.test.ts:37-57](file://products/operator-portal/web-ui/app/src/chat/__tests__/markdown.test.ts#L37-L57)
- [SPEC-042 plan.md:32-42](file://docs/specs/SPEC-042-portal-dependency-hygiene/plan.md#L32-L42)

## Conclusion
SPEC-023 delivers a modern, maintainable operator portal frontend that implements the deferred multi-session workspace UI, preserves all backend contracts and security invariants, and prepares the platform for future enhancements like model dropdowns. The platform-owned SSE adapter isolates wire protocol concerns, enabling framework agility while keeping deployment and runtime characteristics stable.

**Updated** The four-stage progressive rollout is now complete with comprehensive security hardening, delivering a production-ready streaming infrastructure with extensive test coverage. Stage 1 provides the foundation build system, Stage 2 delivers the platform-owned SSE contract adapter with full streaming capabilities, Stage 3 implements the complete multi-session workspace UI with robust session handling, and Stage 4 provides voice input with speech recognition and graceful degradation. The implementation ensures consistent `input_modality` parameter support across all chat endpoints, comprehensive XSS protection in markdown rendering, robust session security with owner validation, and complete audit trails for voice-composed conversations while maintaining the same security and policy guarantees as text-based interactions.

**Enhanced** The portal framework has been further strengthened by SPEC-042 which extends the foundation with comprehensive dependency hygiene measures, antd v6 API migration, React 19 upgrade, and managed component refresh cycles. These enhancements ensure long-term maintainability through automated deprecation detection, modernized build toolchain, and zero behavioral changes while significantly reducing future maintenance debt accumulation.

[No sources needed since this section summarizes without analyzing specific files]

## Appendices

### Current Baseline Reference
The existing vanilla portal demonstrates streaming via `fetch` + `ReadableStream`, Keycloak OIDC flow, and role-scoped views. These patterns inform the rebuild's adapter and auth shell design.

**Section sources**
- [spike.md:21-42](file://docs/workspace/portal-framework-rebuild-spike.md#L21-L42)

### Four-Stage Implementation Status
**Completed** All four stages of the progressive rollout have been successfully implemented with comprehensive security hardening:

- **Stage 1 - Portal Foundation**: Complete build toolchain with Vite, React 18, TypeScript, and Ant Design X theming system
- **Stage 2 - Platform-Owned SSE Contract Adapter**: Full streaming infrastructure with transport, decoder, and comprehensive test coverage including security scenarios
- **Stage 3 - Session Workspace UI**: Complete multi-session management interface with robust session handling, owner validation, and anti-enumeration patterns
- **Stage 4 - Voice Input**: Speech recognition with language selection, graceful degradation, consistent `input_modality` parameter support, and XSS protection

**Enhanced** The foundation has been further strengthened by SPEC-042 with dependency hygiene measures including antd v6 API migration, React 19 upgrade, and comprehensive deprecation regression guards that prevent future maintenance debt accumulation.

**Section sources**
- [tasks.md:5-43](file://docs/specs/SPEC-023-portal-framework-rebuild/tasks.md#L5-L43)

### Voice-Readiness Contract Details
**Completed** R-4 implementation establishes the following contract for voice-readiness parity with comprehensive security measures:

- **Parameter Definition**: `input_modality` accepts only `text` or `voice` values with `text` as default
- **Endpoint Coverage**: Available on both `POST /api/v1/chat` (body) and `GET /api/v1/chat/stream` (query parameter)
- **Service Propagation**: Flows through platform gateway to agent service without semantic transformation
- **Audit Integration**: Included in `chat_started` and `chat_completed` audit events for complete provenance
- **Security Guarantee**: Never influences policy decisions, auto-allow behavior, or HITL outcomes
- **Language Support**: Minimum English (`en-US`) and Mandarin (`zh-CN`) with browser locale detection and localStorage persistence
- **XSS Protection**: Comprehensive markdown rendering with escape-first security model protecting against script injection and dangerous URLs

**Section sources**
- [chat.py:90-143](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L90-L143)
- [routes.py:135-165](file://products/agent-platform/src/agent_service/api/v2/routes.py#L135-L165)
- [transport.ts:31-49](file://products/operator-portal/web-ui/app/src/stream/transport.ts#L31-L49)
- [languages.ts:10-13](file://products/operator-portal/web-ui/app/src/voice/languages.ts#L10-L13)
- [useSpeechRecognition.ts:38-46](file://products/operator-portal/web-ui/app/src/voice/useSpeechRecognition.ts#L38-L46)
- [markdown.ts:47-55](file://products/operator-portal/web-ui/app/src/chat/markdown.ts#L47-L55)

### Security Hardening Implementation Details
**New Section** Comprehensive security measures implemented across the portal framework:

#### XSS Protection in Markdown Rendering
- **Escape-First Approach**: All user input escaped before any markup processing
- **Dangerous URL Blocking**: Explicit rejection of `javascript:`, `data:`, and other malicious URL schemes
- **Attribute Context Protection**: Proper quote escaping prevents HTML attribute breakout
- **Link Security**: Only `http(s)` URLs allowed with `rel="noopener noreferrer"` attributes

#### Session Security Enhancements
- **Owner Validation**: All session operations enforce ownership with 404 responses for foreign sessions
- **Anti-Enumeration**: Foreign session IDs indistinguishable from unknown ones
- **Race Condition Protection**: Named session creation handles concurrent access safely
- **Parked Confirmation Protection**: Sessions with pending confirmations protected from deletion

#### API Contract Validation
- **Schema Compliance**: All responses validated against v6 JSON schemas
- **Type Safety**: Strict typing enforcement throughout the request/response chain
- **Error Handling**: Consistent error responses with appropriate HTTP status codes
- **Audit Logging**: Complete audit trail for all security-relevant operations

#### Deprecation Hygiene and Maintenance
**New** SPEC-042 introduces comprehensive dependency hygiene measures to prevent future maintenance debt:

- **Antd v6 API Migration**: All deprecated props migrated (`Drawer.width` → `Drawer.size`, `Alert.message` → `Alert.title`)
- **Deprecation Regression Guard**: Vitest suite fails on any antd deprecation warning, preventing silent accumulation
- **Managed Component Refresh**: Systematic upgrade of dependencies (React 19, Vite 8, TypeScript 5.9, Vitest 4, jsdom 30)
- **Zero Behavioral Changes**: All upgrades maintain exact same functionality and visual appearance
- **Comprehensive Testing**: Full regression testing suite validates no breaking changes during dependency updates

**Section sources**
- [markdown.ts:1-88](file://products/operator-portal/web-ui/app/src/chat/markdown.ts#L1-L88)
- [markdown.test.ts:1-63](file://products/operator-portal/web-ui/app/src/chat/__tests__/markdown.test.ts#L1-L63)
- [session_service.py:19-61](file://products/agent-platform/src/agent_service/services/session_service.py#L19-L61)
- [routes.py:72-101](file://products/agent-platform/src/agent_service/api/v2/routes.py#L72-L101)
- [SPEC-042 spec.md:56-87](file://docs/specs/SPEC-042-portal-dependency-hygiene/spec.md#L56-L87)
- [SPEC-042 plan.md:15-42](file://docs/specs/SPEC-042-portal-dependency-hygiene/plan.md#L15-L42)

### Dependency Hygiene Specifications
**New Section** SPEC-042 defines comprehensive dependency hygiene requirements for long-term maintainability:

#### Antd API Migration Requirements
- **Drawer Components**: Migrate `width` property to `size` property (230px, 260px, 560px instances)
- **Alert Components**: Migrate `message` property to `title` property across 15 instances in 9 files
- **Visual Parity**: Ensure all migrations maintain exact same visual appearance and behavior
- **Zero Deprecation Warnings**: Vitest suite must emit zero antd deprecation warnings

#### Managed Component Refresh Strategy
- **Adopt Set**: Systematic upgrade of core dependencies (React 19, Vite 8, TypeScript 5.9, Vitest 4, jsdom 30)
- **Version Lockstep**: All packages maintained at compatible versions with proper lockfile management
- **Node Engine Requirements**: Updated to `>=22.22.2` to satisfy jsdom 30 requirements
- **Behavioral Preservation**: All upgrades maintain zero behavioral changes with comprehensive regression testing

#### Deprecation Prevention Infrastructure
- **Console Interception**: Vitest setup intercepts console.error/console.warn during test execution
- **Pattern Matching**: Automatically detects `[antd: …] … deprecated` warning patterns
- **Fail-Fast Policy**: Any deprecation warning causes immediate test suite failure
- **Developer Feedback**: Provides clear error messages pointing to offending deprecation warnings

**Section sources**
- [SPEC-042 spec.md:56-125](file://docs/specs/SPEC-042-portal-dependency-hygiene/spec.md#L56-L125)
- [SPEC-042 plan.md:15-67](file://docs/specs/SPEC-042-portal-dependency-hygiene/plan.md#L15-L67)
- [SPEC-042 tasks.md:5-28](file://docs/specs/SPEC-042-portal-dependency-hygiene/tasks.md#L5-L28)