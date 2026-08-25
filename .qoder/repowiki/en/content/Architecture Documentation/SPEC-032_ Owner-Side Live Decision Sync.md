# SPEC-032: Owner-Side Live Decision Sync

<cite>
**Referenced Files in This Document**
- [spec.md](file://docs/specs/SPEC-032-owner-side-live-decision-sync/spec.md)
- [plan.md](file://docs/specs/SPEC-032-owner-side-live-decision-sync/plan.md)
- [tasks.md](file://docs/specs/SPEC-032-owner-side-live-decision-sync/tasks.md)
- [usePendingDecisionPoll.ts](file://products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts)
- [ChatView.tsx](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx)
- [sessions.ts](file://products/operator-portal/web-ui/app/src/api/sessions.ts)
- [transcript.ts](file://products/operator-portal/web-ui/app/src/chat/transcript.ts)
- [usePendingDecisionPoll.test.ts](file://products/operator-portal/web-ui/app/src/chat/__tests__/usePendingDecisionPoll.test.ts)
</cite>

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
SPEC-032 delivers owner-side live decision sync for the operator portal. When an approval-gated action is pending, the owner’s chat view polls the existing session detail endpoint on a short interval and re-renders as soon as the card resolves. The change is gated so identical responses do not rebuild the timeline or disturb scroll position, composer drafts, or in-flight streams. No new backend surface is introduced; decisions continue to be durable records consumed by both the approver inbox and the owner’s transcript.

Key outcomes:
- Pending cards flip to approved, denied, or expired with decider attribution.
- The resumed turn’s content appears without requiring a manual refresh.
- Polling is bounded: it runs only while a pending card exists and never while a stream is active.

**Section sources**
- [spec.md:11-38](file://docs/specs/SPEC-032-owner-side-live-decision-sync/spec.md#L11-L38)
- [spec.md:40-100](file://docs/specs/SPEC-032-owner-side-live-decision-sync/spec.md#L40-L100)

## Project Structure
This feature is portal-only and touches the operator portal web UI under products/operator-portal/web-ui/app. It introduces a new React hook that wires into the existing ChatView and reuses the session-detail API client and transcript seeding path.

```mermaid
graph TB
subgraph "Operator Portal Web UI"
CV["ChatView.tsx"]
Hook["usePendingDecisionPoll.ts"]
API["api/sessions.ts"]
Trans["chat/transcript.ts"]
end
CV --> Hook
Hook --> API
CV --> Trans
Hook -.->|applies via| CV
```

**Diagram sources**
- [ChatView.tsx:718-739](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L718-L739)
- [usePendingDecisionPoll.ts:1-145](file://products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts#L1-L145)
- [sessions.ts:107-115](file://products/operator-portal/web-ui/app/src/api/sessions.ts#L107-L115)
- [transcript.ts:162-198](file://products/operator-portal/web-ui/app/src/chat/transcript.ts#L162-L198)

**Section sources**
- [plan.md:3-13](file://docs/specs/SPEC-032-owner-side-live-decision-sync/plan.md#L3-L13)
- [ChatView.tsx:718-739](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L718-L739)

## Core Components
- usePendingDecisionPoll hook: Implements bounded, change-gated polling of the session detail endpoint while a confirmation card is pending and no stream is active. Uses a fingerprint over confirmations and transcript length/content to avoid unnecessary re-renders. Includes a settle window after the last pending card resolves to capture trailing resumed content.
- ChatView integration: Wires the hook into the chat workspace and applies the authoritative session detail through the same transcript-to-turns path used on initial load.
- Session detail API client: Provides getSession for reading the authoritative session state (transcript, evidence turns, confirmations).
- Transcript mapping: Converts session detail into chat turns and merges durable confirmation records into the turn timeline, including attribution notes for decided cards.

Acceptance criteria alignment:
- R-1: Poll-while-pending on the active session using GET /api/v1/sessions/{id}.
- R-2: Bounded polling with no activity when idle or streaming; auto-stop after resolution plus settle ticks.
- R-3: Outcome parity across approvals, denials, expirations, and same-window tier_1 decisions.

**Section sources**
- [usePendingDecisionPoll.ts:16-49](file://products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts#L16-L49)
- [usePendingDecisionPoll.ts:51-145](file://products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts#L51-L145)
- [ChatView.tsx:718-739](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L718-L739)
- [sessions.ts:44-94](file://products/operator-portal/web-ui/app/src/api/sessions.ts#L44-L94)
- [transcript.ts:84-135](file://products/operator-portal/web-ui/app/src/chat/transcript.ts#L84-L135)
- [transcript.ts:137-198](file://products/operator-portal/web-ui/app/src/chat/transcript.ts#L137-L198)

## Architecture Overview
The owner’s chat view observes its local turns for pending confirmation cards. If present and no stream is active, the hook periodically fetches the authoritative session detail. On a changed fingerprint, ChatView re-seeds the turn timeline through transcriptToTurns, which merges transcript, evidence turns, and durable confirmations. The result is a consistent UI update that mirrors a manual refresh but without disturbing user interactions.

```mermaid
sequenceDiagram
participant User as "Owner Browser"
participant CV as "ChatView.tsx"
participant Hook as "usePendingDecisionPoll.ts"
participant API as "sessions.ts"
participant Trans as "transcript.ts"
User->>CV : Open session with pending card
CV->>Hook : Provide sessionId, turns, streaming, applyDetail
Hook->>API : GET /api/v1/sessions/{id} every 5s (bounded)
API-->>Hook : SessionDetail (transcript, confirmations)
alt Fingerprint changed
Hook->>CV : applyDetail(detail)
CV->>Trans : transcriptToTurns(transcript, evidence_turns, confirmations)
Trans-->>CV : ChatTurn[] with decided cards
CV-->>User : Re-rendered timeline with attribution + resumed content
else No change
Hook-->>Hook : Skip re-render (change gate)
end
```

**Diagram sources**
- [usePendingDecisionPoll.ts:72-143](file://products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts#L72-L143)
- [ChatView.tsx:718-739](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L718-L739)
- [sessions.ts:107-115](file://products/operator-portal/web-ui/app/src/api/sessions.ts#L107-L115)
- [transcript.ts:162-198](file://products/operator-portal/web-ui/app/src/chat/transcript.ts#L162-L198)

## Detailed Component Analysis

### usePendingDecisionPoll Hook
Responsibilities:
- Determine whether to poll based on presence of a pending confirmation card and absence of streaming.
- Maintain latest-value refs to avoid stale closures during async operations.
- Compute a cheap fingerprint from confirmation statuses and transcript size to detect changes.
- Apply a settle window after the last pending card resolves to ensure resumed content surfaces.
- Safely drop in-flight responses if streaming starts or the session switches.

Key behaviors:
- Interval-driven polling at PENDING_SYNC_INTERVAL_MS (5 seconds).
- Baseline capture on first tick to avoid applying unchanged data.
- Change gating prevents timeline rebuilds on identical responses.
- Error handling preserves last-good view and retries on next tick.

```mermaid
flowchart TD
Start(["Effect start"]) --> CheckState{"sessionId set<br/>and not streaming?"}
CheckState --> |No| Idle["Do nothing"]
CheckState --> |Yes| HasPending{"Any pending card<br/>or settling?"}
HasPending --> |No| Idle
HasPending --> |Yes| Tick["Fetch session detail"]
Tick --> Changed{"Fingerprint changed?"}
Changed --> |No| Settle{"Settling?<br/>count down"}
Settle --> |Yes| Wait["Wait next tick"]
Settle --> |No| Stop["Stop interval"]
Changed --> |Yes| Apply["applyDetail(detail)"]
Apply --> StillPending{"Still pending?"}
StillPending --> |Yes| Wait
StillPending --> |No| OpenSettle["Open settle window"]
OpenSettle --> Wait
Wait --> Tick
```

**Diagram sources**
- [usePendingDecisionPoll.ts:23-40](file://products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts#L23-L40)
- [usePendingDecisionPoll.ts:51-145](file://products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts#L51-L145)

**Section sources**
- [usePendingDecisionPoll.ts:16-49](file://products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts#L16-L49)
- [usePendingDecisionPoll.ts:51-145](file://products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts#L51-L145)

### ChatView Integration
Integration points:
- Wires usePendingDecisionPoll with current sessionId, turns, streaming flag, and an applyDetail callback.
- applyDetail calls transcriptToTurns with the authoritative detail, ensuring consistent rendering of decided cards and resumed content.
- Existing session switch logic seeds the initial timeline via the same transcriptToTurns path, keeping behavior uniform between initial load and live sync.

```mermaid
sequenceDiagram
participant CV as "ChatView.tsx"
participant Hook as "usePendingDecisionPoll.ts"
participant Trans as "transcript.ts"
CV->>Hook : usePendingDecisionPoll({ sessionId, turns, streaming, applyDetail })
Hook-->>CV : applyDetail(detail)
CV->>Trans : transcriptToTurns(detail.transcript, detail.evidence_turns, detail.confirmations)
Trans-->>CV : ChatTurn[]
CV-->>CV : setSession(sessionId, turns)
```

**Diagram sources**
- [ChatView.tsx:718-739](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L718-L739)
- [transcript.ts:162-198](file://products/operator-portal/web-ui/app/src/chat/transcript.ts#L162-L198)

**Section sources**
- [ChatView.tsx:718-739](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L718-L739)

### Session Detail API Client
Provides:
- getSession(sessionId, signal?) to read authoritative session state.
- Types for SessionDetail, ConfirmationRecord, EvidenceTurn, and related shapes used by both the hook and transcript mapper.

Usage in this spec:
- Called by the hook on each tick to obtain the latest confirmations and transcript growth.

**Section sources**
- [sessions.ts:44-94](file://products/operator-portal/web-ui/app/src/api/sessions.ts#L44-L94)
- [sessions.ts:107-115](file://products/operator-portal/web-ui/app/src/api/sessions.ts#L107-L115)

### Transcript Mapping and Attribution
Responsibilities:
- Convert server transcript and evidence turns into chat turns.
- Merge durable confirmation records into turns, marking pending cards and attaching attribution notes for decided cards.
- Ensure parity with live stream rendering so the owner sees the same outcome regardless of how the decision arrived.

Attribution note generation:
- For non-pending records, includes status, decider user id, and decision timestamp where available.

**Section sources**
- [transcript.ts:84-135](file://products/operator-portal/web-ui/app/src/chat/transcript.ts#L84-L135)
- [transcript.ts:137-198](file://products/operator-portal/web-ui/app/src/chat/transcript.ts#L137-L198)

### Tests
Coverage highlights:
- External approval flips the pending card and surfaces resumed content without refresh.
- No polling when idle or streaming.
- In-flight response dropped when a stream starts.
- Denial and expiration parity through the same poll path.
- Transport errors preserve last-good view and retry.
- Stale responses dropped after session switch.

**Section sources**
- [usePendingDecisionPoll.test.ts:111-296](file://products/operator-portal/web-ui/app/src/chat/__tests__/usePendingDecisionPoll.test.ts#L111-L296)

## Dependency Analysis
Component coupling:
- ChatView depends on usePendingDecisionPoll and transcriptToTurns for consistent timeline updates.
- usePendingDecisionPoll depends on sessions.getSession and relies on ChatTurn shape from the stream module.
- transcript.ts depends on API types from sessions.ts and stream models for tool frames.

External contracts:
- Reads GET /api/v1/sessions/{id} — no write paths, no contract changes.
- Consumes durable confirmation records produced by earlier specs (SPEC-031).

Potential risks:
- Race between poll and stream: guarded by streaming flag and session identity checks.
- Stale responses after session switch: guarded by captured session id and ref-based latest values.

```mermaid
graph LR
ChatView["ChatView.tsx"] --> Hook["usePendingDecisionPoll.ts"]
Hook --> API["sessions.ts"]
ChatView --> Trans["transcript.ts"]
Trans --> API
```

**Diagram sources**
- [ChatView.tsx:718-739](file://products/operator-portal/web-ui/app/src/chat/ChatView.tsx#L718-L739)
- [usePendingDecisionPoll.ts:12-14](file://products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts#L12-L14)
- [sessions.ts:107-115](file://products/operator-portal/web-ui/app/src/api/sessions.ts#L107-L115)
- [transcript.ts:9-20](file://products/operator-portal/web-ui/app/src/chat/transcript.ts#L9-L20)

**Section sources**
- [plan.md:53-59](file://docs/specs/SPEC-032-owner-side-live-decision-sync/plan.md#L53-L59)

## Performance Considerations
- Poll interval: 5 seconds balances near-instant visibility with low server load.
- Change gating: Fingerprint avoids unnecessary timeline rebuilds, preserving scroll and focus.
- Bounded execution: No polling when idle or streaming; automatic teardown on state changes.
- Settle window: Limits extra requests after resolution to capture trailing resumed content.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and mitigations:
- No visible update after approval:
  - Verify a pending card exists in the active session turns.
  - Confirm the session is not streaming; polling is disabled during streams.
  - Check network errors; transient failures are retried on the next tick.
- Unexpected re-renders:
  - Ensure fingerprint logic remains intact; identical responses should not rebuild the timeline.
- Stale decision applied to wrong session:
  - Validate session identity checks in the hook; responses for previous sessions are dropped.

Operational tips:
- Use browser dev tools to inspect periodic GET /api/v1/sessions/{id} calls.
- Temporarily reduce PENDING_SYNC_INTERVAL_MS in tests to validate behavior quickly.
- Confirm transcriptToTurns is invoked with the correct detail fields.

**Section sources**
- [usePendingDecisionPoll.ts:87-130](file://products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts#L87-L130)
- [usePendingDecisionPoll.test.ts:247-296](file://products/operator-portal/web-ui/app/src/chat/__tests__/usePendingDecisionPoll.test.ts#L247-L296)

## Conclusion
SPEC-032 completes the R4 owner experience by making external decisions visible in real time within the owner’s chat view. The implementation is portal-only, leverages existing session detail and durable confirmation records, and uses a bounded, change-gated poll to keep latency acceptable while avoiding interference with live streams. All acceptance criteria are covered by unit tests and documented in the spec plan and tasks.

[No sources needed since this section summarizes without analyzing specific files]