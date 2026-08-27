# SPEC-040: Shift-Summary Handover Narrative and Export

<cite>
**Referenced Files in This Document**
- [spec.md](file://docs/specs/SPEC-040-shift-summary-handover-narrative/spec.md)
- [plan.md](file://docs/specs/SPEC-040-shift-summary-handover-narrative/plan.md)
- [tasks.md](file://docs/specs/SPEC-040-shift-summary-handover-narrative/tasks.md)
- [shift_summary.py](file://products/agent-platform/src/agent_service/services/shift_summary.py)
- [document_prose.py](file://products/agent-platform/src/agent_service/services/document_prose.py)
- [DocumentsView.tsx](file://products/operator-portal/web-ui/app/src/views/workspace/DocumentsView.tsx)
- [App.tsx](file://products/operator-portal/web-ui/app/src/App.tsx)
- [2026-08-28-release-notes.md](file://docs/agentic-aiops-platform/release-notes/2026-08-28-shift-summary-handover-narrative-export.md)
</cite>

## Update Summary
**Changes Made**
- Updated status from draft to delivered (v0.22.0)
- Added comprehensive implementation details for all four workstreams (W-1 through W-4)
- Enhanced architecture diagrams with actual file mappings
- Added detailed component analysis based on delivered code
- Updated troubleshooting guide with specific error scenarios
- Added verification and testing information from release notes

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Dependency Analysis](#dependency-analysis)
7. [Performance Considerations](#performance-considerations)
8. [Verification and Testing](#verification-and-testing)
9. [Troubleshooting Guide](#troubleshooting-guide)
10. [Conclusion](#conclusion)

## Introduction
SPEC-040 enhances the shift-summary artifact so that relieving operators inherit a clear, deterministic handover story plus an optional digest-anchored narrative, and can export the document offline as Markdown. The specification has been **delivered in v0.22.0** with all four workstreams fully implemented: deterministic handover section, prose generation default flip, portal navigation reorganization, and client-side Markdown export functionality.

The implementation spans three layers:
- Agent platform (digest assembly and prose generation)
- Operator portal (navigation placement, UI defaults, and client-side export)
- Spec artifacts (requirements, plan, tasks)

## Project Structure
The delivered implementation follows the planned architecture with all components integrated:

```mermaid
graph TB
subgraph "Agent Platform"
A["shift_summary.py<br/>_handover() function"]
B["document_prose.py<br/>anchored prompt contract"]
C["build_digest()<br/>includes handover"]
end
subgraph "Operator Portal"
D["App.tsx<br/>Workspace navigation"]
E["DocumentsView.tsx<br/>create dialog + export"]
F["Drawer Export Button<br/>client-side markdown"]
end
subgraph "Spec Artifacts"
S1["spec.md<br/>status: delivered"]
S2["plan.md<br/>all workstreams complete"]
S3["tasks.md<br/>all tasks checked"]
end
S1 --> A
S1 --> B
S1 --> D
S1 --> E
S2 --> A
S2 --> B
S2 --> D
S2 --> E
S3 --> A
S3 --> B
S3 --> D
S3 --> E
```

**Diagram sources**
- [shift_summary.py:182-280](file://products/agent-platform/src/agent_service/services/shift_summary.py#L182-L280)
- [document_prose.py:32-50](file://products/agent-platform/src/agent_service/services/document_prose.py#L32-50)
- [DocumentsView.tsx:254-305](file://products/operator-portal/web-ui/app/src/views/workspace/DocumentsView.tsx#L254-L305)
- [App.tsx:113-203](file://products/operator-portal/web-ui/app/src/App.tsx#L113-L203)

**Section sources**
- [spec.md:5-11](file://docs/specs/SPEC-040-shift-summary-handover-narrative/spec.md#L5-L11)
- [plan.md:11-88](file://docs/specs/SPEC-040-shift-summary-handover-narrative/plan.md#L11-L88)

## Core Components
All four requirements have been successfully delivered:

### R-1: Deterministic Handover Section
- `_handover(entries)` function aggregates decisions, executions, open items, and quiet state across covered sessions
- Two-tier coverage preserved: owner sessions contribute full details; foreign sessions contribute counts only
- Unavailable sources degrade gracefully; assembly remains side-effect-free and deterministic

### R-2: Prose as Default, Digest-Anchored Narrative  
- `include_prose` defaults to `true` in create requests
- Prompt contract enforces anchoring rules: every statement traces to digest sections
- Generation uses runtime model with timeout; failures return `prose_status=failed`
- Portal create dialog defaults prose switch on with explicit opt-out preserved

### R-3: Documents Navigation Move
- Documents entry relocated from Control to Workspace group
- Role gating (`documents:read`) moved with it into workspace visibility block
- Control rendering remains correct for roles seeing only other surfaces

### R-4: Client-Side Markdown Export
- Renders metadata, provenance, digest (including handover), and prose when included
- Filename derived from slugified label and short document id
- Download performed via Blob without network calls
- Drawer includes Export button next to header meta

**Section sources**
- [shift_summary.py:182-280](file://products/agent-platform/src/agent_service/services/shift_summary.py#L182-L280)
- [document_prose.py:32-50](file://products/agent-platform/src/agent_service/services/document_prose.py#L32-50)
- [DocumentsView.tsx:254-305](file://products/operator-portal/web-ui/app/src/views/workspace/DocumentsView.tsx#L254-L305)
- [App.tsx:113-203](file://products/operator-portal/web-ui/app/src/App.tsx#L113-L203)

## Architecture Overview
End-to-end flow for creating and exporting a shift summary under SPEC-040:

```mermaid
sequenceDiagram
participant User as "Operator"
participant Portal as "DocumentsView.tsx"
participant Gateway as "Platform Gateway"
participant Agent as "shift_summary.py"
participant Prose as "document_prose.py"
participant Store as "Durable Stores"
User->>Portal : Create shift summary (include_prose default true)
Portal->>Gateway : POST createDocument({document_type, session_ids, label, include_prose})
Gateway->>Agent : build_digest(requester_user_id, session_ids, can_view_foreign)
Agent->>Store : Load confirmations, executions, evidence, transcripts
Store-->>Agent : Records (per-session entries)
Agent->>Agent : _handover(entries) -> deterministic handover
Agent-->>Gateway : {digest (with handover), provenance}
alt include_prose == true
Gateway->>Prose : generate_prose(kernel, "shift_summary", digest)
Prose-->>Gateway : {prose, status : included|failed}
else include_prose == false
Gateway-->>Portal : document without prose
end
Portal-->>User : Draft created (digest + optional prose)
User->>Portal : Open document drawer
Portal->>Portal : buildDocumentMarkdown(document)
Portal-->>User : Download <label-slug>-doc-<id>.md
```

**Diagram sources**
- [DocumentsView.tsx:254-305](file://products/operator-portal/web-ui/app/src/views/workspace/DocumentsView.tsx#L254-L305)
- [shift_summary.py:367-426](file://products/agent-platform/src/agent_service/services/shift_summary.py#L367-L426)
- [document_prose.py:68-109](file://products/agent-platform/src/agent_service/services/document_prose.py#L68-L109)
- [DocumentsView.tsx:393-461](file://products/operator-portal/web-ui/app/src/views/workspace/DocumentsView.tsx#L393-L461)

## Detailed Component Analysis

### Deterministic Handover Section (R-1) - DELIVERED
The `_handover()` function provides a deterministic skeleton of the shift story:

```mermaid
flowchart TD
Start(["_handover(entries)"]) --> Split["Split entries into own vs foreign"]
Split --> OwnLoop{"For each own session"}
OwnLoop --> Decisions["Accumulate decided confirmations<br/>and open pending"]
OwnLoop --> Execs["Accumulate executions<br/>and requested ones"]
OwnLoop --> OpenSessions["Mark sessions with any open item"]
Decisions --> SortDecisions["Sort decisions by time/id"]
Execs --> SortExecs["Sort executions by time/id"]
SortDecisions --> ForeignLoop{"For each foreign session"}
SortExecs --> ForeignLoop
ForeignLoop --> Counts["Add foreign counts only"]
Counts --> Quiet{"No decisions AND no executions?"}
Quiet --> |Yes| QuietFlag["quiet = true"]
Quiet --> |No| KeepQuiet["quiet = false"]
QuietFlag --> Return(["Return handover object"])
KeepQuiet --> Return
```

**Key Features:**
- Aggregation logic computes counts, own-coverage decision/execution details, open items, open sessions, and quiet flag deterministically
- Two-tier posture preserved: owner sessions contribute full details; foreign sessions contribute counts only
- Unavailable sources degrade gracefully; assembly remains side-effect-free and deterministic

**Section sources**
- [shift_summary.py:182-280](file://products/agent-platform/src/agent_service/services/shift_summary.py#L182-L280)
- [shift_summary.py:367-426](file://products/agent-platform/src/agent_service/services/shift_summary.py#L367-L426)

### Digest-Anchored Prose Default (R-2) - DELIVERED
The prose layer now serves as the default narrative with strict anchoring rules:

```mermaid
classDiagram
class DocumentProse {
+build_prose_prompt(document_type, digest) string
+generate_prose(kernel, document_type, digest) tuple<string?, string>
}
class ShiftSummaryDigest {
+build_digest(...) tuple<dict, dict>
}
DocumentProse --> ShiftSummaryDigest : "receives digest"
```

**Implementation Details:**
- Prompt template enforces anchoring: every statement must trace to a digest section; no record ids, causes, or recommendations absent from input
- Generation uses runtime model with 30-second timeout; failures return `prose_status=failed`, leaving digest intact
- Portal create dialog defaults prose switch on; explicit opt-out preserved
- Panel relabeled to "AI-generated narrative — from this document's digest facts"

**Section sources**
- [document_prose.py:32-50](file://products/agent-platform/src/agent_service/services/document_prose.py#L32-50)
- [document_prose.py:68-109](file://products/agent-platform/src/agent_service/services/document_prose.py#L68-L109)
- [DocumentsView.tsx:254-305](file://products/operator-portal/web-ui/app/src/views/workspace/DocumentsView.tsx#L254-L305)

### Documents Navigation Move (R-3) - DELIVERED
The Documents view has been successfully relocated to improve ergonomics:

```mermaid
graph LR
App["App.tsx SidebarContent"] --> Workspace["Workspace group"]
Workspace --> Docs["Documents entry"]
Docs --> View["DocumentsView.tsx"]
```

**Navigation Changes:**
- Documents moved from Control to Workspace in the sidebar menu
- Visibility mirror (`documents:read`) moved with it into workspace visibility block
- Control rendering remains correct for roles seeing only other surfaces
- First entry in Workspace group after role validation

**Section sources**
- [App.tsx:113-203](file://products/operator-portal/web-ui/app/src/App.tsx#L113-L203)
- [DocumentsView.tsx:1-7](file://products/operator-portal/web-ui/app/src/views/workspace/DocumentsView.tsx#L1-L7)

### Client-Side Markdown Export (R-4) - DELIVERED
Export functionality provides offline access to shift summaries:

```mermaid
sequenceDiagram
participant User as "Operator"
participant Drawer as "DocumentsView.tsx Drawer"
participant Renderer as "buildDocumentMarkdown()"
participant Browser as "Browser Download"
User->>Drawer : Click "Export .md"
Drawer->>Renderer : render(document)
Renderer-->>Drawer : Markdown string
Drawer->>Browser : downloadBlob(filename, markdown)
Browser-->>User : File saved locally
```

**Export Features:**
- Renders metadata table, provenance table, digest (including handover), labeled prose when included, and failure note when prose failed
- Filename derived from slugified label and short document id (e.g., `night-shift-2026-08-28-doc-3f2a91.md`)
- Download performed via Blob without network calls
- Drawer includes Export button next to header meta with tooltip description

**Section sources**
- [DocumentsView.tsx:393-461](file://products/operator-portal/web-ui/app/src/views/workspace/DocumentsView.tsx#L393-L461)
- [DocumentsView.tsx:683-701](file://products/operator-portal/web-ui/app/src/views/workspace/DocumentsView.tsx#L683-L701)

## Dependency Analysis
The implementation maintains clean separation of concerns while preserving existing invariants:

```mermaid
graph TB
SS["shift_summary.py"] --> CS["confirmation records store"]
SS --> ES["execution records store"]
SS --> ESTORE["evidence store"]
SS --> T["session transcript"]
DP["document_prose.py"] --> K["runtime kernel / model"]
PV["DocumentsView.tsx"] --> API["API clients (list/get/create)"]
PV -.->|no network| MD["client-side Markdown renderer"]
```

**Dependencies:**
- Agent platform depends on durable stores (confirmations, executions, evidence, transcripts) through safe reads; degradation yields unavailable sections rather than errors
- Prose generation depends on the runtime kernel's model path with a hard timeout; failures are captured and surfaced as `prose_status=failed`
- Portal depends on existing API clients for list/get/create/publish/delete; export is purely client-side and does not call the gateway

**Section sources**
- [shift_summary.py:93-113](file://products/agent-platform/src/agent_service/services/shift_summary.py#L93-L113)
- [document_prose.py:79-109](file://products/agent-platform/src/agent_service/services/document_prose.py#L79-L109)
- [DocumentsView.tsx:393-461](file://products/operator-portal/web-ui/app/src/views/workspace/DocumentsView.tsx#L393-L461)

## Performance Considerations
- Handover assembly is O(N) over covered sessions and their confirmation/execution rows; sorting is bounded by per-session lists
- Prose generation has a fixed 30-second timeout to prevent blocking the create route; empty replies are treated as failures
- Export is client-side and CPU-bound only on the current tab; large digests may increase render time but do not impact servers
- No new server endpoints or audit events introduced; export leverages already-fetched documents

## Verification and Testing
The implementation has been thoroughly verified through multiple testing approaches:

### Unit Tests
- `TestHandoverSection` pins determinism, two-tier foreign counts-only posture, quiet-shift empty state, open items, and degraded-source assembly
- Route-created document assertion requires the `handover` skeleton
- Prompt-contract test asserts the R-2 anchoring rules
- Portal suite covers narrative default, drawer export affordance, and Markdown serializer

### Integration Testing
- Agent-platform + platform-gateway suites green
- Portal `tsc` build and unit tests green
- `make verify` green at 0.22.0

### Live Verification
- Extended `documents-demo.sh` validates created document carries `handover` (quiet shape on demo session)
- Browser walkthrough covers nav placement, default prose switch, handover rendering, and export download
- Dev cluster deployment validated end-to-end workflow

**Section sources**
- [2026-08-28-release-notes.md:65-80](file://docs/agentic-aiops-platform/release-notes/2026-08-28-shift-summary-handover-narrative-export.md#L65-L80)

## Troubleshooting Guide
Common issues and their resolutions:

### Missing Handover in Older Documents
- Pre-SPEC-040 documents retain original shape; consumers should treat absent `handover` as legacy
- New documents always include the `handover` section

### Prose Not Included
- Check `prose_status`; if `not_requested`, ensure create request omits `include_prose` (defaults to true) or explicitly sets it
- If `failed`, investigate model timeouts or empty replies
- Verify the 30-second timeout hasn't been exceeded

### Export File Missing Prose
- Exported Markdown notes failure when `prose_status=failed`; digest remains complete
- Check that the document was created with prose enabled (default behavior)

### Navigation Confusion
- Documents now appears under Workspace; verify role grants for `documents:read`
- Ensure users have appropriate workspace permissions

### Handover Data Issues
- Check that underlying stores (confirmations, executions, evidence) are accessible
- Verify session IDs are valid and accessible to the requester
- Review foreign session permissions for cross-owner coverage

**Section sources**
- [document_prose.py:68-109](file://products/agent-platform/src/agent_service/services/document_prose.py#L68-L109)
- [DocumentsView.tsx:198-236](file://products/operator-portal/web-ui/app/src/views/workspace/DocumentsView.tsx#L198-L236)
- [DocumentsView.tsx:393-461](file://products/operator-portal/web-ui/app/src/views/workspace/DocumentsView.tsx#L393-L461)
- [App.tsx:113-203](file://products/operator-portal/web-ui/app/src/App.tsx#L113-L203)

## Conclusion
SPEC-040 has been successfully delivered in v0.22.0, providing a comprehensive solution for shift handover workflows. The implementation delivers:

- **Deterministic handover skeleton**: Provides reliable facts about decisions, executions, and open items
- **Digest-anchored narrative**: Default prose generation with strict anchoring rules prevents hallucination
- **Improved workspace ergonomics**: Documents relocated to logical Workspace location
- **Offline capability**: Client-side Markdown export enables handover sharing outside the portal

The changes preserve all prior invariants (no model output outside labeled prose, fail-soft generation, two-tier coverage) while closing the operator feedback gap about inheriting actionable context between shifts. All four workstreams (W-1 through W-4) have been completed and verified through comprehensive testing and live deployment.