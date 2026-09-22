# Chat Interface

<cite>
**Referenced Files in This Document**
- [ChatView.tsx](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx)
- [useChatStream.ts](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts)
- [transport.ts](file://products/operator-portal/web-ui/app/src/stream/transport.ts)
- [decoder.ts](file://products/operator-portal/web-ui/app/src/stream/decoder.ts)
- [models.ts](file://products/operator-portal/web-ui/app/src/stream/models.ts)
- [ComposerSelectionBar.tsx](file://products/operator-portal/web-ui/app/src/chat/ComposerSelectionBar.tsx)
- [SkillContentViewer.tsx](file://products/operator-portal/web-ui/app/src/chat/SkillContentViewer.tsx)
- [SkillsView.tsx](file://products/operator-portal/web-ui/app/src/views/control/SkillsView.tsx)
- [transcript.ts](file://products/operator-portal/web-ui/app/src/chat/transcript.ts)
- [client.ts](file://products/operator-portal/web-ui/app/src/api/client.ts)
- [secrets_connector.py](file://products/tool-gateway/src/tool_gateway/tools/secrets_connector.py)
- [secret_delivery.py](file://products/tool-gateway/src/tool_gateway/tools/secret_delivery.py)
- [tools.py](file://products/platform-gateway/src/platform_gateway/api/routes/tools.py)
- [SPEC-062 spec.md](file://docs/specs/SPEC-062-secure-password-generation-and-delivery/spec.md)
- [TurnGroup.test.tsx](file://products/operator-portal/web-ui/app/src/chat/__tests__/TurnGroup.test.tsx)
- [useChatStream.test.ts](file://products/operator-portal/web-ui/app/src/stream/__tests__/useChatStream.test.ts)
- [transport.test.ts](file://products/operator-portal/web-ui/app/src/stream/__tests__/transport.test.ts)
- [decoder.test.ts](file://products/operator-portal/web-ui/app/src/stream/__tests__/decoder.test.ts)
- [SkillContentViewer.test.tsx](file://products/operator-portal/web-ui/app/src/chat/__tests__/SkillContentViewer.test.tsx)
</cite>

## Update Summary
**Changes Made**
- Added documentation for the one-time password copy interface with temporary delivery controls and expiration timers
- Updated SecretDeliveryFrame handling in streaming architecture
- Enhanced ChatView component documentation to include CopyPasswordControl integration
- Added new section on secret delivery workflow and security guarantees
- Updated error recovery mechanisms to cover expired and unavailable secret deliveries

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [One-Time Password Delivery System](#one-time-password-delivery-system)
7. [Composition Runbooks Feature](#composition-runbooks-feature)
8. [Dependency Analysis](#dependency-analysis)
9. [Performance Considerations](#performance-considerations)
10. [Troubleshooting Guide](#troubleshooting-guide)
11. [Conclusion](#conclusion)

## Introduction
This document explains the streaming chat interface that enables real-time agent interactions in the operator portal. It covers the ChatView component architecture, message rendering, and conversation history management; the Server-Sent Events (SSE) implementation via the useChatStream hook for real-time streaming, transport layer abstraction, and event decoding; composer functionality for user input, model selection, and tool invocation display; the one-time password delivery system with secure handoff and expiration controls; composition runbooks with structured sub-skill lists and risk classification badges; as well as streaming performance optimizations, error recovery mechanisms, and accessibility features for screen readers and keyboard navigation.

## Project Structure
The chat interface is implemented in the operator portal web UI under the chat and stream modules:
- ChatView orchestrates session management, transcript rendering, evidence panels, confirmation cards, composer integration, and one-time password delivery controls.
- useChatStream owns per-turn state, SSE lifecycle, HITL confirmations, session switching, turn caching, and secret delivery frame handling.
- transport provides fetch-based SSE opening, chunk consumption, and request ID propagation.
- decoder implements an incremental SSE line decoder and frame mapping to typed models, including secret delivery frames.
- ComposerSelectionBar hosts per-turn model selection when a catalog is available.
- SkillContentViewer renders skill details including composition runbooks with structured sub-skill lists.
- SkillsView displays skills inventory with risk classification badges.
- transcript converts persisted transcripts into turns for replay.
- client.ts provides secure API functions for secret redemption with clipboard integration.

```mermaid
graph TB
subgraph "UI"
CV["ChatView"]
CSB["ComposerSelectionBar"]
SCV["SkillContentViewer"]
SV["SkillsView"]
CPC["CopyPasswordControl"]
end
subgraph "Streaming"
UCS["useChatStream"]
TR["transport"]
DEC["decoder"]
MOD["models"]
end
subgraph "Secret Delivery"
API["Platform Gateway"]
TC["Tool Gateway"]
BUF["Secret Delivery Buffer"]
CLI["Client API"]
end
subgraph "History"
TRN["transcript"]
end
CV --> UCS
CV --> CSB
CV --> SCV
CV --> CPC
SV --> SCV
CV --> TRN
UCS --> TR
TR --> DEC
DEC --> MOD
CPC --> CLI
CLI --> API
API --> TC
TC --> BUF
```

**Diagram sources**
- [ChatView.tsx:622-664](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L622-L664)
- [useChatStream.ts:1-80](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L1-L80)
- [transport.ts:1-60](file://products/operator-portal/web-ui/app/src/stream/transport.ts#L1-L60)
- [decoder.ts:100-114](file://products/operator-portal/web-ui/app/src/stream/decoder.ts#L100-L114)
- [models.ts:56-61](file://products/operator-portal/web-ui/app/src/stream/models.ts#L56-L61)
- [client.ts:125-153](file://products/operator-portal/web-ui/app/src/api/client.ts#L125-L153)
- [tools.py:39-58](file://products/platform-gateway/src/platform_gateway/api/routes/tools.py#L39-L58)
- [secrets_connector.py:120-153](file://products/tool-gateway/src/tool_gateway/tools/secrets_connector.py#L120-L153)

**Section sources**
- [ChatView.tsx:622-664](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L622-L664)
- [useChatStream.ts:1-80](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L1-L80)
- [transport.ts:1-60](file://products/operator-portal/web-ui/app/src/stream/transport.ts#L1-L60)
- [decoder.ts:100-114](file://products/operator-portal/web-ui/app/src/stream/decoder.ts#L100-L114)
- [models.ts:56-61](file://products/operator-portal/web-ui/app/src/stream/models.ts#L56-L61)
- [client.ts:125-153](file://products/operator-portal/web-ui/app/src/api/client.ts#L125-L153)
- [tools.py:39-58](file://products/platform-gateway/src/platform_gateway/api/routes/tools.py#L39-L58)
- [secrets_connector.py:120-153](file://products/tool-gateway/src/tool_gateway/tools/secrets_connector.py#L120-L153)

## Core Components
- ChatView: Renders sessions, messages, tool evidence, confirmation cards, composer, and controls for skill drafting/graduation. Manages arrival highlighting, sticky request banners, and one-time password delivery controls.
- useChatStream: Maintains per-turn state, accumulates deltas, handles tool frames, terminal events, confirmation requests/results, errors, session switching with abort, retry on stale session 404, and secret delivery frame processing.
- transport: Opens SSE streams with auth headers and request IDs, reads chunks, and consumes them through the decoder. Encapsulates open failures and structured 409 detail parsing.
- decoder: Incrementally parses SSE blocks separated by double newlines, maps wire payloads to typed StreamFrame types, and safely ignores unknown or malformed frames. Includes secret delivery frame validation.
- ComposerSelectionBar: Displays a model selector when a model catalog is available; collapses otherwise.
- SkillContentViewer: Renders skill details including composition runbooks with structured sub-skill lists showing title, target, and notes, plus risk classification badges.
- SkillsView: Displays skills inventory with derived risk classification badges for compositions.
- transcript: Converts stored transcripts into ChatTurn arrays, attaching evidence and confirmations for replay parity with live streams.
- CopyPasswordControl: Handles one-time password redemption with expiration timers, clipboard integration, and security state management.

**Section sources**
- [ChatView.tsx:595-749](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L595-L749)
- [ChatView.tsx:622-664](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L622-L664)
- [useChatStream.ts:135-501](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L135-L501)
- [transport.ts:108-165](file://products/operator-portal/web-ui/app/src/stream/transport.ts#L108-L165)
- [decoder.ts:95-251](file://products/operator-portal/web-ui/app/src/stream/decoder.ts#L95-L251)
- [decoder.ts:100-114](file://products/operator-portal/web-ui/app/src/stream/decoder.ts#L100-L114)
- [ComposerSelectionBar.tsx:1-48](file://products/operator-portal/web-ui/app/src/chat/ComposerSelectionBar.tsx#L1-L48)
- [SkillContentViewer.tsx:45-193](file://products/operator-portal/web-ui/app/src/chat/SkillContentViewer.tsx#L45-L193)
- [SkillsView.tsx:93-139](file://products/operator-portal/web-ui/app/src/views/control/SkillsView.tsx#L93-L139)
- [transcript.ts:266-302](file://products/operator-portal/web-ui/app/src/chat/transcript.ts#L266-L302)

## Architecture Overview
The chat interface composes a React view with a streaming adapter. The view renders messages and interactive elements while the adapter manages SSE lifecycles, decodes events, and updates turn state. Transport abstracts network concerns and ensures consistent error handling and request correlation. The one-time password delivery system provides secure credential handoff without exposing values in the stream or render tree. Composition runbooks extend the skill viewing experience with structured guidance for multi-step workflows.

```mermaid
sequenceDiagram
participant User as "Operator"
participant View as "ChatView"
participant Hook as "useChatStream"
participant Trans as "transport"
participant Dec as "decoder"
participant API as "Gateway /api/v1/chat/*"
participant SecAPI as "Secret Delivery API"
User->>View : Type message + optional model
View->>Hook : send(message, options)
Hook->>Trans : openStream(chatStreamPath(...))
Trans-->>Hook : {requestId, chunks}
Hook->>Dec : consumeStream(chunks, onEvent)
Dec-->>Hook : decoded events (delta/tool_call/tool_result/terminal/error/confirmation_*/secret_delivery)
Hook-->>View : update turns (replyText, tool frames, confirmations, secret deliveries)
Note over View : Render CopyPasswordControl for secret_delivery frames
View->>SecAPI : GET /api/v1/secrets/delivery/{id}
SecAPI-->>View : value (clipboard only)
View-->>User : Render streamed reply, evidence, cards, copy button
```

**Diagram sources**
- [useChatStream.ts:240-328](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L240-L328)
- [transport.ts:111-165](file://products/operator-portal/web-ui/app/src/stream/transport.ts#L111-L165)
- [decoder.ts:227-251](file://products/operator-portal/web-ui/app/src/stream/decoder.ts#L227-L251)
- [ChatView.tsx:1672-1694](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L1672-L1694)
- [tools.py:39-58](file://products/platform-gateway/src/platform_gateway/api/routes/tools.py#L39-L58)

## Detailed Component Analysis

### ChatView: Message Rendering, Evidence, History, and Secret Delivery
- TurnGroup renders user bubbles, assistant markdown content, loading indicators, post-approval "Agent is working…" indicator, tool evidence panel, confirmation cards, and one-time password delivery controls.
- Arrival window and typewriter reveal animate newly landed text within a bounded time, respecting reduced-motion preferences.
- Sticky request banner keeps the user's prompt visible when the assistant reply scrolls out of view.
- EvidencePanel aggregates tool calls and results, shows status tags, parameters, execution metadata, truncation notices, and special rendering for screenshots.
- ConfirmationCardView displays pending approvals, flow summaries, change-request projections, technical details, and execution receipts, with role-based decision gating.
- CopyPasswordControl renders one-time password redemption with expiration timers, clipboard integration, and security state management.
- Session actions include Draft as skill, Graduate as skill, Declare target, and Copy session id, each with appropriate role checks and error messaging.
- Transcript seeding uses transcriptToTurns to convert stored history into ChatTurn objects, preserving evidence, confirmations, and secret deliveries for replay parity.

```mermaid
flowchart TD
Start(["Render Turn"]) --> Reply["Render assistant reply<br/>with markdown"]
Reply --> Loading{"Streaming?"}
Loading --> |Yes| Spinner["Show loading indicator"]
Loading --> |No| Evidence{"Has tool frames?"}
Evidence --> |Yes| Evid["EvidencePanel"]
Evidence --> |No| Confirm{"Has confirmations?"}
Evid --> Confirm
Confirm --> |Yes| Card["ConfirmationCardView"]
Confirm --> |No| Secret{"Has secret delivery?"}
Secret --> |Yes| CopyCtrl["CopyPasswordControl"]
Secret --> |No| End(["Done"])
CopyCtrl --> End
Card --> End
```

**Diagram sources**
- [ChatView.tsx:605-749](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L605-L749)
- [ChatView.tsx:622-664](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L622-L664)
- [ChatView.tsx:1672-1694](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L1672-L1694)
- [transcript.ts:266-302](file://products/operator-portal/web-ui/app/src/chat/transcript.ts#L266-L302)

**Section sources**
- [ChatView.tsx:98-314](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L98-L314)
- [ChatView.tsx:316-593](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L316-L593)
- [ChatView.tsx:595-749](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L595-L749)
- [ChatView.tsx:622-664](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L622-L664)
- [ChatView.tsx:1672-1694](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L1672-L1694)
- [transcript.ts:266-302](file://products/operator-portal/web-ui/app/src/chat/transcript.ts#L266-L302)

### useChatStream: Streaming Lifecycle, Event Handling, Recovery, and Secret Delivery
- send creates a new turn, opens an SSE stream, and consumes events until completion or error.
- handleEvent accumulates delta text, records tool calls/results, marks terminal, manages confirmation cards and errors, and processes secret delivery frames.
- decide posts a confirmation decision and resumes the SSE stream bound to the parked turn, locking card states and completing the turn appropriately.
- Session switching aborts in-flight streams, stashes current turns, restores cached turns, and supports reseedTurns for authoritative timeline refresh.
- Error recovery includes:
  - Stale session 404: drops sessionId and retries once to auto-create.
  - Authentication failure 401: surfaces sign-in guidance.
  - Confirmation race 409: flips card to winner's outcome with attribution if present.
  - Expired confirmation 410: marks expired and completes the turn.
  - AbortError on switch: settles partial turns without leaving spinners.
  - Secret delivery expiration: handles expired delivery handles gracefully.

```mermaid
sequenceDiagram
participant Hook as "useChatStream"
participant API as "Gateway"
participant Cache as "turnsCacheRef"
Hook->>API : GET /api/v1/chat/stream?message&user_id[&session_id]
API-->>Hook : SSE events (delta/tool/terminal/error/confirmation/secret_delivery)
Hook->>Hook : accumulate reply & frames
alt 404 stale session
Hook->>API : GET /api/v1/chat/stream (no session_id)
API-->>Hook : resumed stream
else 409 race
Hook->>Hook : flip card to winner outcome
else 410 expired
Hook->>Hook : mark expired & complete turn
end
Note over Hook,Cache : setSession aborts current stream and swaps cache
```

**Diagram sources**
- [useChatStream.ts:240-454](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L240-L454)
- [useChatStream.ts:456-488](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L456-L488)

**Section sources**
- [useChatStream.ts:167-328](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L167-L328)
- [useChatStream.ts:330-454](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L330-L454)
- [useChatStream.ts:456-488](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L456-L488)

### Transport Layer: Open, Consume, and Decode
- openStream builds authenticated requests with x-request-id, handles non-OK responses by throwing StreamOpenError with parsed detail when possible, and returns requestId plus a chunk source.
- readableToChunks adapts ReadableStream or AsyncIterable inputs to a uniform async generator.
- consumeStream drives the SseLineDecoder over UTF-8 decoded chunks, emitting only fully delimited events.
- chatStreamPath constructs query strings including message, user_id, optional session_id, input_modality, and model.

```mermaid
flowchart TD
A["openStream(path, options)"] --> B{"response.ok?"}
B --> |No| C["Parse JSON detail if possible"]
C --> D["Throw StreamOpenError(status, detail)"]
B --> |Yes| E["Return {requestId, chunks}"]
E --> F["consumeStream(chunks, onEvent)"]
F --> G["SseLineDecoder.push(text)"]
G --> H["onEvent(decoded)"]
```

**Diagram sources**
- [transport.ts:111-165](file://products/operator-portal/web-ui/app/src/stream/transport.ts#L111-L165)
- [decoder.ts:227-251](file://products/operator-portal/web-ui/app/src/stream/decoder.ts#L227-L251)

**Section sources**
- [transport.ts:1-60](file://products/operator-portal/web-ui/app/src/stream/transport.ts#L1-L60)
- [transport.ts:88-165](file://products/operator-portal/web-ui/app/src/stream/transport.ts#L88-L165)

### Decoder: Frame Mapping and Robustness
- SseLineDecoder buffers raw text, splits on double newline, and yields decoded events only when complete.
- decodeEventBlock extracts session_id and maps payload to StreamFrame; unknown or malformed blocks are ignored to avoid breaking the stream.
- toFrame recognizes delta, terminal, tool_call, tool_result, confirmation_request, confirmation_result, error, and secret_delivery frames, normalizing fields and dropping unsupported actions gracefully.
- toSecretDeliveryFrame validates UUID format, channel type, and expiration timestamp for secret delivery frames.

```mermaid
classDiagram
class SseLineDecoder {
-string buffer
+push(chunk) DecodedEvent[]
+reset() void
}
class Models {
<<types>>
DeltaFrame
TerminalFrame
ToolCallFrame
ToolResultFrame
SecretDeliveryFrame
}
SseLineDecoder --> Models : "produces typed frames"
```

**Diagram sources**
- [decoder.ts:95-251](file://products/operator-portal/web-ui/app/src/stream/decoder.ts#L95-L251)
- [decoder.ts:100-114](file://products/operator-portal/web-ui/app/src/stream/decoder.ts#L100-L114)
- [models.ts:1-54](file://products/operator-portal/web-ui/app/src/stream/models.ts#L1-L54)
- [models.ts:56-61](file://products/operator-portal/web-ui/app/src/stream/models.ts#L56-L61)

**Section sources**
- [decoder.ts:95-251](file://products/operator-portal/web-ui/app/src/stream/decoder.ts#L95-L251)
- [decoder.ts:100-114](file://products/operator-portal/web-ui/app/src/stream/decoder.ts#L100-L114)
- [models.ts:1-54](file://products/operator-portal/web-ui/app/src/stream/models.ts#L1-L54)
- [models.ts:56-61](file://products/operator-portal/web-ui/app/src/stream/models.ts#L56-L61)

### Composer: Input, Model Selection, and Tool Invocation Display
- ComposerSelectionBar mounts under the message input and shows a model selector when a catalog is available; it collapses when no models are configured, letting server-side defaults apply.
- ChatView integrates the composer with voice input support and error alerts, and passes selected model to useChatStream.send via SendOptions.model.
- Tool invocations appear in the EvidencePanel with call/result pairing, status tags, parameter expansion, execution metadata, truncation notices, and specialized screenshot rendering.

**Section sources**
- [ComposerSelectionBar.tsx:1-48](file://products/operator-portal/web-ui/app/src/chat/ComposerSelectionBar.tsx#L1-L48)
- [ChatView.tsx:1697-1704](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L1697-L1704)
- [ChatView.tsx:98-314](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L98-L314)

## One-Time Password Delivery System

### Overview
The one-time password delivery system provides secure credential handoff from agents to operators without exposing sensitive values in the stream, render tree, logs, or audit stores. When an agent generates a password using `secrets.generate_password` with `handoff='portal_copy'`, the system creates a temporary, single-use delivery handle that allows operators to securely copy the password to their clipboard through an authenticated gateway endpoint.

### Security Architecture
The system enforces several security guarantees:
- **No Projection**: The generated password never appears in conversation transcripts, evidence, titles, cards, or any human-readable projection
- **Single Use**: Each delivery handle can be redeemed exactly once, then immediately invalidated
- **Owner Scoping**: Redemption requires authentication matching the original session owner
- **TTL Expiration**: Delivery handles expire after a configurable time period (default 300 seconds)
- **Clipboard-Only Access**: Values are written directly to the clipboard without being displayed in the UI
- **Server-Side Storage**: Secrets are stored in ephemeral buffers (in-memory or Redis) with automatic cleanup

### Implementation Components

#### Frontend Integration
The `CopyPasswordControl` component renders a secure copy button with the following behavior:
- **State Management**: Tracks ready, copying, copied, and unavailable states
- **Expiration Handling**: Monitors delivery handle expiration and disables the button when expired
- **Security Validation**: Prevents multiple attempts and validates clipboard access
- **User Feedback**: Provides clear status messages about copy success, expiration, and unavailability

#### Backend Processing
The backend consists of three main layers:

1. **Tool Gateway**: Implements `secrets.generate_password` and `secrets.deliver` tools with proper validation and policy enforcement
2. **Platform Gateway**: Provides the `/api/v1/secrets/delivery/{delivery_id}` endpoint for secure redemption
3. **Secret Delivery Buffer**: Stores secrets with TTL and owner scoping, supporting both in-memory and Redis backends

```mermaid
sequenceDiagram
participant Agent as "Agent"
participant TG as "Tool Gateway"
participant PB as "Secret Buffer"
participant PG as "Platform Gateway"
participant UI as "Operator UI"
Agent->>TG : secrets.generate_password(handoff='portal_copy')
TG->>PB : stash(value, owner, session, ttl)
PB-->>TG : delivery_id
TG-->>Agent : delivery_id + expires_at
Agent-->>UI : secret_delivery frame
UI->>PG : GET /api/v1/secrets/delivery/{id}
PG->>PB : redeem(delivery_id, owner)
PB-->>PG : value (single use)
PG-->>UI : value (clipboard only)
UI->>UI : navigator.clipboard.writeText()
PB-->>PB : invalidate handle
```

**Diagram sources**
- [secrets_connector.py:393-521](file://products/tool-gateway/src/tool_gateway/tools/secrets_connector.py#L393-L521)
- [secret_delivery.py:89-158](file://products/tool-gateway/src/tool_gateway/tools/secret_delivery.py#L89-L158)
- [tools.py:39-58](file://products/platform-gateway/src/platform_gateway/api/routes/tools.py#L39-L58)
- [client.ts:125-153](file://products/operator-portal/web-ui/app/src/api/client.ts#L125-L153)

### Data Flow and Validation
The secret delivery system follows a strict data flow with comprehensive validation:

- **Generation Phase**: Agent calls `secrets.generate_password` with policy constraints and handoff preference
- **Storage Phase**: Value is stashed in the delivery buffer with owner context and TTL
- **Rendering Phase**: Frontend receives `secret_delivery` frame with delivery metadata (never the value)
- **Redemption Phase**: Operator clicks copy button, triggering authenticated redemption
- **Cleanup Phase**: Handle is immediately invalidated after successful redemption

### Testing and Validation
The system includes comprehensive test coverage:
- **Single Use Enforcement**: Verifies handles cannot be reused after redemption
- **Expiration Handling**: Tests TTL-based expiration and graceful degradation
- **Owner Scoping**: Ensures only the original session owner can redeem
- **Clipboard Integration**: Validates clipboard write operations and error handling
- **Security State**: Confirms no plaintext values persist in storage or UI

**Section sources**
- [secrets_connector.py:393-521](file://products/tool-gateway/src/tool_gateway/tools/secrets_connector.py#L393-L521)
- [secrets_connector.py:524-653](file://products/tool-gateway/src/tool_gateway/tools/secrets_connector.py#L524-L653)
- [secret_delivery.py:89-158](file://products/tool-gateway/src/tool_gateway/tools/secret_delivery.py#L89-L158)
- [secret_delivery.py:167-229](file://products/tool-gateway/src/tool_gateway/tools/secret_delivery.py#L167-L229)
- [tools.py:39-58](file://products/platform-gateway/src/platform_gateway/api/routes/tools.py#L39-L58)
- [client.ts:125-153](file://products/operator-portal/web-ui/app/src/api/client.ts#L125-L153)
- [ChatView.tsx:622-664](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L622-L664)
- [decoder.ts:100-114](file://products/operator-portal/web-ui/app/src/stream/decoder.ts#L100-L114)
- [models.ts:56-61](file://products/operator-portal/web-ui/app/src/stream/models.ts#L56-L61)
- [SPEC-062 spec.md:171-186](file://docs/specs/SPEC-062-secure-password-generation-and-delivery/spec.md#L171-L186)
- [TurnGroup.test.tsx:70-117](file://products/operator-portal/web-ui/app/src/chat/__tests__/TurnGroup.test.tsx#L70-L117)

## Composition Runbooks Feature

### Overview
The composition runbooks feature enhances the operator portal chat interface to display structured guidance for multi-step workflows. When viewing a composition skill, operators see a structured list showing each sub-skill's title, target, and associated notes, along with derived risk classification badges that indicate the overall risk level of the composition.

### Sub-Skill Display Structure
The SkillContentViewer component renders composition runbooks with the following structure:

- **Ordered List**: Each sub-skill appears in the declared sequence, maintaining the intended workflow order
- **Resolved Title**: Shows the human-readable title from the sub-skill's metadata, falling back to skill_id if unresolved
- **Target Information**: Displays the web target when available, omitting it for infrastructure skills without web targets
- **Associated Notes**: Shows any plain-language notes provided by the composition author
- **Visual Hierarchy**: Uses typography and spacing to clearly distinguish between different information levels

### Risk Classification Badges
Compositions derive their risk classification automatically based on their sub-skills:

- **Write Risk**: If any sub-skill performs write operations, the composition derives a "write" risk class
- **Read Risk**: If all sub-skills are read-only, the composition derives a "read" risk class
- **Badge Display**: Risk badges use color coding (default for read, warning for write) consistent with confirmation cards
- **List Integration**: Risk badges appear in the skills inventory table alongside other skill metadata

### Implementation Details
The composition runbooks feature is implemented across several components:

```mermaid
flowchart TD
A["SkillDetail with kind=composition"] --> B["Extract sub_skills array"]
B --> C["For each sub_skill"]
C --> D["Display resolved_title or skill_id"]
C --> E["Display resolved_web_target if present"]
C --> F["Display note if present"]
D --> G["Add to ordered list"]
E --> G
F --> G
G --> H["Render structured runbook list"]
A --> I["Display derived risk_class badge"]
```

**Diagram sources**
- [SkillContentViewer.tsx:131-167](file://products/operator-portal/web-ui/app/src/chat/SkillContentViewer.tsx#L131-L167)
- [SkillsView.tsx:100-113](file://products/operator-portal/web-ui/app/src/views/control/SkillsView.tsx#L100-L113)

### Data Flow and Enrichment
The composition data flows through the system with read-path enrichment:

- **Authored Data**: Contains skill_id and optional note for each sub-skill
- **Enriched Data**: Skills-hub's read path adds resolved_title and resolved_web_target
- **Fallback Behavior**: Missing sub-skills degrade gracefully to show authored skill_id
- **Display Only**: The structured list is for review purposes only and doesn't enforce workflow execution

### Testing and Validation
The feature includes comprehensive test coverage:

- **Structured List Rendering**: Verifies ordered list with correct title, target, and note display
- **Fallback Behavior**: Tests graceful degradation when sub-skill titles are unresolved
- **Raw View Compatibility**: Ensures Raw view shows authored body verbatim without structured list
- **Non-Composition Skills**: Confirms no sub-skill list appears for regular skills

**Section sources**
- [SkillContentViewer.tsx:131-167](file://products/operator-portal/web-ui/app/src/chat/SkillContentViewer.tsx#L131-L167)
- [SkillsView.tsx:100-113](file://products/operator-portal/web-ui/app/src/views/control/SkillsView.tsx#L100-L113)
- [SkillContentViewer.test.tsx:113-172](file://products/operator-portal/web-ui/app/src/chat/__tests__/SkillContentViewer.test.tsx#L113-L172)

## Dependency Analysis
- ChatView depends on useChatStream for streaming state and decisions, on transcript for history seeding, on ComposerSelectionBar for model selection, and on CopyPasswordControl for secret delivery handling.
- useChatStream depends on transport for SSE I/O and on decoder/models for event processing, including secret delivery frame handling.
- SkillContentViewer depends on renderMarkdown for safe HTML generation and displays composition runbooks when available.
- SkillsView depends on derived risk_class from skills-hub summary for badge display.
- transport depends on client utilities for auth headers and gateway URL resolution.
- decoder depends on models for type definitions, including SecretDeliveryFrame.
- Client API provides secure secret redemption with clipboard integration and security state management.

```mermaid
graph LR
ChatView --> useChatStream
ChatView --> transcript
ChatView --> ComposerSelectionBar
ChatView --> CopyPasswordControl
useChatStream --> transport
useChatStream --> decoder
useChatStream --> models
SkillContentViewer --> renderMarkdown
SkillsView --> SkillContentViewer
transport --> decoder
decoder --> models
CopyPasswordControl --> client
client --> platformGateway
platformGateway --> toolGateway
toolGateway --> secretBuffer
```

**Diagram sources**
- [ChatView.tsx:1-100](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L1-L100)
- [useChatStream.ts:1-80](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L1-L80)
- [transport.ts:1-60](file://products/operator-portal/web-ui/app/src/stream/transport.ts#L1-L60)
- [decoder.ts:1-40](file://products/operator-portal/web-ui/app/src/stream/decoder.ts#L1-L40)
- [models.ts:1-54](file://products/operator-portal/web-ui/app/src/stream/models.ts#L1-L54)
- [models.ts:56-61](file://products/operator-portal/web-ui/app/src/stream/models.ts#L56-L61)
- [SkillContentViewer.tsx:1-193](file://products/operator-portal/web-ui/app/src/chat/SkillContentViewer.tsx#L1-L193)
- [SkillsView.tsx:93-139](file://products/operator-portal/web-ui/app/src/views/control/SkillsView.tsx#L93-L139)
- [client.ts:125-153](file://products/operator-portal/web-ui/app/src/api/client.ts#L125-L153)

**Section sources**
- [ChatView.tsx:1-100](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L1-L100)
- [useChatStream.ts:1-80](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L1-L80)
- [transport.ts:1-60](file://products/operator-portal/web-ui/app/src/stream/transport.ts#L1-L60)
- [decoder.ts:1-40](file://products/operator-portal/web-ui/app/src/stream/decoder.ts#L1-L40)
- [models.ts:1-54](file://products/operator-portal/web-ui/app/src/stream/models.ts#L1-L54)
- [models.ts:56-61](file://products/operator-portal/web-ui/app/src/stream/models.ts#L56-L61)
- [SkillContentViewer.tsx:1-193](file://products/operator-portal/web-ui/app/src/chat/SkillContentViewer.tsx#L1-L193)
- [SkillsView.tsx:93-139](file://products/operator-portal/web-ui/app/src/views/control/SkillsView.tsx#L93-L139)
- [client.ts:125-153](file://products/operator-portal/web-ui/app/src/api/client.ts#L125-L153)

## Performance Considerations
- Typewriter reveal with arrival window: New reply text is revealed incrementally within a fixed time window, improving perceived responsiveness without blocking rendering. Reduced motion preference disables animation for accessibility.
- Segment breaks: Tool frames trigger paragraph breaks so subsequent text segments render cleanly, avoiding merged headings or sentences.
- Efficient decoding: SseLineDecoder emits events only on complete blocks, minimizing allocations and preventing partial frames from disrupting the stream.
- Abort on session switch: In-flight streams are aborted promptly to avoid unnecessary work and stale UI states.
- Collapsible selection bar: Model selector collapses when unavailable, keeping the composer compact and reducing layout shifts.
- Composition runbook rendering: Structured sub-skill lists are rendered efficiently with minimal DOM manipulation and fallback handling for missing data.
- Secret delivery optimization: One-time passwords are handled asynchronously with immediate UI feedback and background redemption processing.
- Memory management: Secret delivery handles are automatically cleaned up after expiration or redemption to prevent memory leaks.

## Troubleshooting Guide
Common issues and their handling:
- Stale session 404: The hook detects a 404 on open, clears the session pointer, retries once without session_id, and updates the session id from the response. Verified by tests asserting URL changes and recovered reply text.
- Authentication 401: The hook surfaces a clear sign-in message to guide users back to authentication.
- Confirmation race 409: If another approver decided first, the card flips to the winner's outcome with attribution and completes the turn to prevent hung UI.
- Expired confirmation 410: The card is marked expired and the turn completes, avoiding a perpetual spinner.
- Malformed or unknown SSE frames: The decoder ignores non-data lines and malformed JSON, ensuring corrupt frames do not break the stream.
- Empty catalog: ComposerSelectionBar collapses when no models are configured, falling back to server-side defaults.
- Missing sub-skill titles: Composition runbooks gracefully fall back to displaying skill_id when resolved titles are unavailable.
- Unresolved web targets: Infrastructure skills without web targets simply omit the target line from the runbook display.
- Secret delivery expiration: CopyPasswordControl displays "Password expired" message and disables the copy button when delivery handles expire.
- Secret delivery unavailability: Handles invalid redemption attempts gracefully and suggests generating a new password.
- Clipboard access denied: Falls back to "Password unavailable" state when clipboard operations fail.
- Authentication required: Prevents secret redemption without proper authentication headers.

**Section sources**
- [useChatStream.ts:283-328](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L283-L328)
- [useChatStream.ts:392-454](file://products/operator-portal/web-ui/app/src/stream/useChatStream.ts#L392-L454)
- [decoder.ts:204-251](file://products/operator-portal/web-ui/app/src/stream/decoder.ts#L204-L251)
- [decoder.ts:100-114](file://products/operator-portal/web-ui/app/src/stream/decoder.ts#L100-L114)
- [ComposerSelectionBar.tsx:22-27](file://products/operator-portal/web-ui/app/src/chat/ComposerSelectionBar.tsx#L22-L27)
- [useChatStream.test.ts:645-672](file://products/operator-portal/web-ui/app/src/stream/__tests__/useChatStream.test.ts#L645-L672)
- [transport.test.ts:22-48](file://products/operator-portal/web-ui/app/src/stream/__tests__/transport.test.ts#L22-L48)
- [decoder.test.ts:385-438](file://products/operator-portal/web-ui/app/src/stream/__tests__/decoder.test.ts#L385-L438)
- [SkillContentViewer.test.tsx:141-152](file://products/operator-portal/web-ui/app/src/chat/__tests__/SkillContentViewer.test.tsx#L141-L152)
- [TurnGroup.test.tsx:92-117](file://products/operator-portal/web-ui/app/src/chat/__tests__/TurnGroup.test.tsx#L92-L117)

## Conclusion
The streaming chat interface combines a robust React view with a resilient SSE adapter. ChatView renders rich conversations with evidence and approval workflows, while useChatStream manages streaming lifecycles, event accumulation, and recovery paths. The transport and decoder layers provide reliable, incremental parsing and error-tolerant decoding. Composer functionality supports model selection and integrates seamlessly with streaming. The one-time password delivery system provides secure credential handoff with expiration controls and clipboard integration, ensuring sensitive values never enter the stream or render tree. The composition runbooks feature enhances the operator experience by providing structured guidance for multi-step workflows with clear visual hierarchy and risk classification. Performance optimizations like arrival windows and segment breaks enhance responsiveness, and accessibility features ensure inclusive interaction. Together, these components deliver a responsive, auditable, and operator-friendly chat experience with enhanced compositional guidance capabilities and secure secret delivery mechanisms.