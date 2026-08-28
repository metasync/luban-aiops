# SPEC-039: Operations Document Repository Specification

<cite>
**Referenced Files in This Document**
- [spec.md](file://docs/specs/SPEC-039-operations-document-repository/spec.md)
- [plan.md](file://docs/specs/SPEC-039-operations-document-repository/plan.md)
- [tasks.md](file://docs/specs/SPEC-039-operations-document-repository/tasks.md)
- [operation_documents.py](file://products/agent-platform/src/agent_service/services/operation_documents.py)
- [shift_summary.py](file://products/agent-platform/src/agent_service/services/shift_summary.py)
- [document_prose.py](file://products/agent-platform/src/agent_service/services/document_prose.py)
- [routes.py](file://products/agent-platform/src/agent_service/api/v2/routes.py)
- [documents.py](file://products/platform-gateway/src/platform_gateway/api/routes/documents.py)
- [policy-default.yaml](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml)
- [operation-document.schema.json](file://shared/shared-contracts/schemas/operation-document.schema.json)
- [v2.py](file://products/agent-platform/src/agent_service/schemas/v2.py)
- [DocumentsView.tsx](file://products/operator-portal/web-ui/app/src/views/workspace/DocumentsView.tsx)
- [SPEC-041 spec.md](file://docs/specs/SPEC-041-documents-readability-and-digest-reference/spec.md)
- [SPEC-041 plan.md](file://docs/specs/SPEC-041-documents-readability-and-digest-reference/plan.md)
</cite>

## Update Summary
**Changes Made**
- Updated implementation status to reflect fully delivered Phase 1 with all eight requirements completed
- Enhanced architecture diagrams to include platform gateway policy enforcement and operator portal integration
- Added detailed component analysis for the complete typed document store, shift summary assembler, prose generator, and API routes
- Updated dependency analysis to show full cross-product integration between agent-platform, platform-gateway, and operator-portal
- Added comprehensive troubleshooting guide covering all error scenarios and degradation paths
- Updated conclusion to reflect delivery status and future extensibility
- Integrated SPEC-040 context showing handover section support and prose generation defaults changes
- **Added SPEC-041 enhancement planning**: Documentation now includes forward-looking information about upcoming readability improvements and digest reference capabilities that will extend the delivered SPEC-039 functionality

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Dependency Analysis](#dependency-analysis)
7. [Performance Considerations](#performance-considerations)
8. [Troubleshooting Guide](#troubleshooting-guide)
9. [Future Enhancements (SPEC-041)](#future-enhancements-spec-041)
10. [Conclusion](#conclusion)

## Introduction
This document specifies the Operations Document Repository (SPEC-039), a platform-owned, typed-document substrate that lets operators produce durable operational recaps from existing platform records and share them by role rather than per-document grants. Phase 1 ships the substrate with a draft→published lifecycle, role-based access matrix, provenance anchoring, audit events, and a portal Documents view. The first document type is the shift summary: a deterministic digest of sessions, confirmation decisions, execution receipts, and evidence counts, with an optional clearly-labeled prose layer generated solely from the digest.

Key goals:
- Immutable snapshots anchored to record ids, not live references.
- Role-based visibility: drafts owner-only; published visible to all documents:read holders.
- Safe LLM-generated prose that can only paraphrase verified facts.
- Audit trails for creation, publishing, and cross-owner reads.

**Section sources**
- [spec.md:12-55](file://docs/specs/SPEC-039-operations-document-repository/spec.md#L12-L55)

## Project Structure
The implementation spans three products plus shared contracts:
- Agent Platform: document store, shift-summary assembler, prose generator, routes, and session add-ons.
- Platform Gateway: pass-through routes enforcing new policy actions and foreign coverage capability.
- Operator Portal: Documents view and session rename/id-copy UX.
- Shared Contracts: JSON schema for operation documents and default policy bundle updates.

```mermaid
graph TB
subgraph "Agent Platform"
A["operation_documents.py"]
B["shift_summary.py"]
C["document_prose.py"]
D["routes.py"]
end
subgraph "Platform Gateway"
E["documents.py"]
F["policy-default.yaml"]
end
subgraph "Operator Portal"
G["DocumentsView.tsx"]
H["Documents View UI"]
end
subgraph "Shared Contracts"
I["operation-document.schema.json"]
J["v2.py"]
end
D --> A
D --> B
D --> C
E --> D
F --> E
G --> E
I --> D
I --> G
J --> D
```

**Diagram sources**
- [operation_documents.py:1-531](file://products/agent-platform/src/agent_service/services/operation_documents.py#L1-L531)
- [shift_summary.py:1-323](file://products/agent-platform/src/agent_service/services/shift_summary.py#L1-L323)
- [document_prose.py:1-100](file://products/agent-platform/src/agent_service/services/document_prose.py#L1-L100)
- [routes.py:738-957](file://products/agent-platform/src/agent_service/api/v2/routes.py#L738-L957)
- [documents.py:1-171](file://products/platform-gateway/src/platform_gateway/api/routes/documents.py#L1-L171)
- [policy-default.yaml:251-267](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L251-L267)
- [DocumentsView.tsx:195-249](file://products/operator-portal/web-ui/app/src/views/workspace/DocumentsView.tsx#L195-L249)
- [operation-document.schema.json:1-101](file://shared/shared-contracts/schemas/operation-document.schema.json#L1-L101)
- [v2.py:335-367](file://products/agent-platform/src/agent_service/schemas/v2.py#L335-L367)

**Section sources**
- [plan.md:3-16](file://docs/specs/SPEC-039-operations-document-repository/plan.md#L3-L16)
- [tasks.md:5-52](file://docs/specs/SPEC-039-operations-document-repository/tasks.md#L5-L52)

## Core Components
- Typed document store: immutable rows with draft→published lifecycle, per-owner cap (20), 30-day TTL sweep, memory and Postgres backends behind one interface.
- Shift-summary assembler: builds deterministic digests from durable stores with two-tier coverage (owner full, foreign metadata-only).
- Optional prose generator: digest-only prompt contract, hard timeout, fail-soft degradation to digest-only documents.
- API routes: create, list (mine/published), get, publish, delete; session rename route; structured denials via gateway policy.
- Policy actions: documents:create, documents:read, session:update granted to operator/approver/platform-admin by default.
- Schema: strict JSON schema for operation documents including envelope fields, provenance, digest, and prose status.

**Section sources**
- [operation_documents.py:38-105](file://products/agent-platform/src/agent_service/services/operation_documents.py#L38-L105)
- [shift_summary.py:40-74](file://products/agent-platform/src/agent_service/services/shift_summary.py#L40-L74)
- [document_prose.py:24-56](file://products/agent-platform/src/agent_service/services/document_prose.py#L24-L56)
- [routes.py:763-957](file://products/agent-platform/src/agent_service/api/v2/routes.py#L763-L957)
- [policy-default.yaml:251-267](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L251-L267)
- [operation-document.schema.json:8-99](file://shared/shared-contracts/schemas/operation-document.schema.json#L8-L99)

## Architecture Overview
The repository composes a typed store, a type-agnostic assembler, and an optional prose generator, exposed through versioned routes and guarded by gateway-enforced policies.

```mermaid
sequenceDiagram
participant Client as "Client"
participant Gateway as "Platform Gateway"
participant Routes as "Agent v2 Routes"
participant Store as "OperationDocumentStore"
participant Asm as "Shift Summary Assembler"
participant Prose as "Prose Generator"
participant Audit as "Audit Emitter"
Client->>Gateway : POST /api/v1/documents
Gateway->>Routes : enforce_policy("documents : create")
Routes->>Asm : build_digest(requester, session_ids, can_view_foreign)
Asm-->>Routes : digest + provenance
Routes->>Store : create(document)
Store-->>Routes : ok
Routes->>Prose : generate_prose(kernel, type, digest)
Prose-->>Routes : prose or failed
Routes->>Audit : emit document_created
Routes-->>Client : {document_id, state=draft}
```

**Diagram sources**
- [documents.py:29-69](file://products/platform-gateway/src/platform_gateway/api/routes/documents.py#L29-L69)
- [routes.py:763-856](file://products/agent-platform/src/agent_service/api/v2/routes.py#L763-L856)
- [shift_summary.py:266-323](file://products/agent-platform/src/agent_service/services/shift_summary.py#L266-L323)
- [operation_documents.py:488-531](file://products/agent-platform/src/agent_service/services/operation_documents.py#L488-L531)
- [document_prose.py:59-100](file://products/agent-platform/src/agent_service/services/document_prose.py#L59-L100)
- [policy-default.yaml:251-267](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L251-L267)

## Detailed Component Analysis

### Operation Document Store (R-1)
- Interface: OperationDocumentStore with create, publish, load, list_for_owner, list_published, delete, is_ready.
- Backends: InMemoryOperationDocumentStore and PostgresOperationDocumentStore sharing the same behavior.
- Lifecycle: One-way publish (draft→published), owner-only publish/delete, immutable after publish.
- Retention and caps: Per-owner cap of 20 with oldest eviction; 30-day TTL sweep on writes and startup.
- Visibility: list_for_owner returns owner's drafts; list_published returns team-visible published docs.

```mermaid
classDiagram
class OperationDocumentStore {
+backend_name : string
+create(document) void
+publish(owner_user_id, document_id) bool
+load(document_id) dict|None
+list_for_owner(owner_user_id) list[dict]
+list_published() list[dict]
+delete(owner_user_id, document_id) bool
+is_ready() bool
}
class InMemoryOperationDocumentStore {
+backend_name = "memory"
}
class PostgresOperationDocumentStore {
+backend_name = "postgres"
+initialize() void
}
OperationDocumentStore <|.. InMemoryOperationDocumentStore
OperationDocumentStore <|.. PostgresOperationDocumentStore
```

**Diagram sources**
- [operation_documents.py:80-105](file://products/agent-platform/src/agent_service/services/operation_documents.py#L80-L105)
- [operation_documents.py:112-195](file://products/agent-platform/src/agent_service/services/operation_documents.py#L112-L195)
- [operation_documents.py:342-481](file://products/agent-platform/src/agent_service/services/operation_documents.py#L342-L481)

**Section sources**
- [operation_documents.py:38-105](file://products/agent-platform/src/agent_service/services/operation_documents.py#L38-L105)
- [operation_documents.py:112-195](file://products/agent-platform/src/agent_service/services/operation_documents.py#L112-L195)
- [operation_documents.py:202-297](file://products/agent-platform/src/agent_service/services/operation_documents.py#L202-L297)
- [operation_documents.py:342-481](file://products/agent-platform/src/agent_service/services/operation_documents.py#L342-L481)
- [operation_documents.py:488-531](file://products/agent-platform/src/agent_service/services/operation_documents.py#L488-L531)

### Shift Summary Assembler (R-3)
- Inputs: requester user id, bounded session ids (≤20), and a flag indicating whether foreign sessions may be viewed.
- Ownership tiers:
  - Owner sessions: full digest (title, transcript counts, evidence counts, confirmations, executions, open items).
  - Foreign sessions: metadata-only (decisions, receipts, record counts) gated by approvals:list.
- Degradation: unreadable secondary stores mark sections unavailable; never raise 500.
- Validation: rejects unknown session ids structurally without revealing ownership.

```mermaid
flowchart TD
Start(["build_digest"]) --> Validate["Validate session ids<br/>bounded input"]
Validate --> Exists{"All session ids exist?"}
Exists -- No --> RaiseUnknown["Raise UnknownSessionError"]
Exists -- Yes --> Classify["Classify owner vs foreign"]
Classify --> ForeignCheck{"Any foreign sessions?"}
ForeignCheck -- Yes & no approvals:list --> RaiseDenied["Raise ForeignSessionDenied"]
ForeignCheck -- Yes & has approvals:list --> BuildForeign["Build metadata-only entries"]
ForeignCheck -- No --> BuildOwner["Build full-digest entries"]
BuildForeign --> Merge["Merge entries + provenance"]
BuildOwner --> Merge
Merge --> Return(["Return (digest, provenance)"])
```

**Diagram sources**
- [shift_summary.py:77-90](file://products/agent-platform/src/agent_service/services/shift_summary.py#L77-L90)
- [shift_summary.py:182-263](file://products/agent-platform/src/agent_service/services/shift_summary.py#L182-L263)
- [shift_summary.py:266-323](file://products/agent-platform/src/agent_service/services/shift_summary.py#L266-L323)

**Section sources**
- [shift_summary.py:1-22](file://products/agent-platform/src/agent_service/services/shift_summary.py#L1-L22)
- [shift_summary.py:77-90](file://products/agent-platform/src/agent_service/services/shift_summary.py#L77-L90)
- [shift_summary.py:182-263](file://products/agent-platform/src/agent_service/services/shift_summary.py#L182-L263)
- [shift_summary.py:266-323](file://products/agent-platform/src/agent_service/services/shift_summary.py#L266-L323)

### Optional Prose Layer (R-4)
- Prompt contract: digest-only input; model cannot see transcripts or evidence payloads.
- Execution: uses runtime's default model client with a hard timeout; drains streaming responses if needed.
- Failure mode: any error yields prose_status=failed; document still created with digest only.

```mermaid
sequenceDiagram
participant Route as "v2 Routes"
participant Prose as "generate_prose"
participant Kernel as "Runtime Kernel"
Route->>Prose : generate_prose(kernel, document_type, digest)
Prose->>Kernel : build_model(None)
Prose->>Kernel : call model([Msg(text=prompt)])
Kernel-->>Prose : response or stream
Prose-->>Route : (prose, "included") or (None, "failed")
```

**Diagram sources**
- [document_prose.py:24-56](file://products/agent-platform/src/agent_service/services/document_prose.py#L24-L56)
- [document_prose.py:59-100](file://products/agent-platform/src/agent_service/services/document_prose.py#L59-L100)

**Section sources**
- [document_prose.py:1-13](file://products/agent-platform/src/agent_service/services/document_prose.py#L1-L13)
- [document_prose.py:24-56](file://products/agent-platform/src/agent_service/services/document_prose.py#L24-L56)
- [document_prose.py:59-100](file://products/agent-platform/src/agent_service/services/document_prose.py#L59-L100)

### API Routes and Policy Enforcement (R-2, R-5, R-7)
- Create/list/get/publish/delete endpoints for documents with structured rejections.
- Session rename endpoint PATCH /sessions/{id}/title owner-only, bounds-checked, 404 for unknown/foreign.
- Gateway enforces documents:create, documents:read, session:update via policy-default.yaml.
- Audit emission: document_created, document_published, document_read (cross-owner only).

```mermaid
sequenceDiagram
participant Client as "Client"
participant Gateway as "Platform Gateway"
participant Routes as "Agent v2 Routes"
participant Store as "OperationDocumentStore"
participant Audit as "Audit Emitter"
Client->>Gateway : GET /api/v1/documents?scope=mine
Gateway->>Routes : enforce_policy("documents : read")
Routes->>Store : list_for_owner(user_id)
Store-->>Routes : [documents...]
Routes->>Audit : emit document_read (if cross-owner read of published)
Routes-->>Client : [documents...]
```

**Diagram sources**
- [documents.py:72-95](file://products/platform-gateway/src/platform_gateway/api/routes/documents.py#L72-L95)
- [routes.py:858-874](file://products/agent-platform/src/agent_service/api/v2/routes.py#L858-L874)
- [policy-default.yaml:251-267](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L251-L267)

**Section sources**
- [routes.py:763-957](file://products/agent-platform/src/agent_service/api/v2/routes.py#L763-L957)
- [documents.py:29-171](file://products/platform-gateway/src/platform_gateway/api/routes/documents.py#L29-L171)
- [policy-default.yaml:251-267](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L251-L267)
- [spec.md:87-106](file://docs/specs/SPEC-039-operations-document-repository/spec.md#L87-L106)
- [spec.md:156-170](file://docs/specs/SPEC-039-operations-document-repository/spec.md#L156-L170)
- [spec.md:189-219](file://docs/specs/SPEC-039-operations-document-repository/spec.md#L189-L219)

### Data Model (Operation Document)
- Envelope fields: document_id, document_type, state, owner_user_id, label, created_at, published_at, provenance, digest, prose, prose_status.
- Provenance: sessions array with session_id, coverage (owner/foreign), cited_record_ids.
- Digest: type-specific deterministic data copied verbatim from durable stores.
- Prose: optional narrative produced from digest only; prose_status indicates included/failed/not_requested.

```mermaid
erDiagram
OPERATION_DOCUMENT {
string document_id PK
string document_type
string state
string owner_user_id
string label
datetime created_at
datetime published_at
jsonb provenance
jsonb digest
text prose
string prose_status
}
```

**Diagram sources**
- [operation-document.schema.json:8-99](file://shared/shared-contracts/schemas/operation-document.schema.json#L8-L99)

**Section sources**
- [operation-document.schema.json:1-101](file://shared/shared-contracts/schemas/operation-document.schema.json#L1-L101)

## Dependency Analysis
- Routes depend on:
  - OperationDocumentStore (create/list/get/publish/delete)
  - ShiftSummaryAssembler (build_digest)
  - ProseGenerator (generate_prose)
  - AuditEmitter (emit events)
  - Session services (rename title)
- Policy actions gate routes at the gateway:
  - documents:create → create/publish/delete own documents
  - documents:read → list/get documents
  - session:update → rename session title
- Store depends on environment knobs AGENT_STATE_STORE_BACKEND and AGENT_STATE_DB_URL; falls back to in-memory when Postgres is unreachable.

```mermaid
graph LR
Routes["v2 Routes"] --> Store["OperationDocumentStore"]
Routes --> Asm["Shift Summary Assembler"]
Routes --> Prose["Prose Generator"]
Routes --> Audit["Audit Emitter"]
Routes --> SessionSvc["Session Services"]
Policy["policy-default.yaml"] --> Routes
Gateway["Platform Gateway"] --> Routes
Portal["Operator Portal"] --> Gateway
```

**Diagram sources**
- [routes.py:763-957](file://products/agent-platform/src/agent_service/api/v2/routes.py#L763-L957)
- [operation_documents.py:488-531](file://products/agent-platform/src/agent_service/services/operation_documents.py#L488-L531)
- [documents.py:29-171](file://products/platform-gateway/src/platform_gateway/api/routes/documents.py#L29-L171)
- [policy-default.yaml:251-267](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L251-L267)

**Section sources**
- [plan.md:119-132](file://docs/specs/SPEC-039-operations-document-repository/plan.md#L119-L132)
- [policy-default.yaml:251-267](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L251-L267)

## Performance Considerations
- Store operations are bounded: per-owner cap of 20 with oldest eviction; 30-day TTL sweep piggybacks on writes and initialization.
- Secondary store reads degrade gracefully; failures do not block request paths.
- Prose generation has a hard timeout to prevent route blocking; failures degrade to digest-only documents.
- Postgres queries use indexes on owner and state columns for efficient listing.

## Troubleshooting Guide
- Unknown session ids during digest assembly: raises a specific error carrying offending ids; routes respond 400 without revealing ownership.
- Missing permissions: gateway returns structured denial for missing documents:create/documents:read/session:update.
- Postgres unavailability: store factory falls back to in-memory backend; service remains usable.
- Prose generation failure: prose_status set to failed; document still created with digest only.
- Foreign session access: requires approvals:list capability; denied without proper authorization.
- Session rename validation: titles must be 1-80 characters after trimming; foreign or unknown sessions return 404.

**Section sources**
- [shift_summary.py:46-70](file://products/agent-platform/src/agent_service/services/shift_summary.py#L46-L70)
- [policy-default.yaml:251-267](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L251-L267)
- [operation_documents.py:488-531](file://products/agent-platform/src/agent_service/services/operation_documents.py#L488-L531)
- [document_prose.py:59-100](file://products/agent-platform/src/agent_service/services/document_prose.py#L59-L100)
- [routes.py:705-736](file://products/agent-platform/src/agent_service/api/v2/routes.py#L705-L736)

## Future Enhancements (SPEC-041)

### Planned Readability Improvements
The operations document repository is planned to receive significant usability enhancements through SPEC-041, which addresses operator feedback from the v0.22.0 live test. These enhancements focus on improving the digest's readability and providing better context for operators encountering the document system for the first time.

### Key Planned Features

#### R-1: Operator Digest and Documents Reference
- Dedicated operator-facing reference documentation explaining digest vocabulary (digest, frame, coverage tiers, handover)
- Integration with portal user guide and Documents view
- Maintains envelope-only listing posture while providing educational content

#### R-2: Tabbed, Structured Digest Rendering  
- Restructure the current recursive JSON tree into tabbed interface with dedicated tabs for:
  - Handover (default) - shift-level counts, open items, quiet state
  - Sessions - per-session coverage details
  - Confirmations - decision tracking
  - Executions - tool execution outcomes
  - Evidence & Transcript Counts - quantitative metrics
  - Open Items - pending actions breakdown
  - Raw JSON - preserves artifact inspection capability

#### R-3: Bounded Scrollable Digest and Prose Panes
- Maximum height constraints with internal scrolling for long content
- Expand/collapse affordances for full content access
- Prevents drawer overflow while maintaining content accessibility

#### R-4: Deterministic Counts-Only Document Summary
- Creation-time summary computed from handover skeleton (no model involvement)
- Shows covered session counts, decision/execution counts, open item counts
- Quiet phrasing for shifts with no recorded activity
- Envelope-only field that maintains security posture

### Implementation Timeline
SPEC-041 is currently in draft status targeting version 0.23.0 as part of the R5 hardening cycle. The enhancements are designed to be additive, preserving all existing functionality while significantly improving operator experience and onboarding.

**Section sources**
- [SPEC-041 spec.md:11-45](file://docs/specs/SPEC-041-documents-readability-and-digest-reference/spec.md#L11-L45)
- [SPEC-041 plan.md:13-87](file://docs/specs/SPEC-041-documents-readability-and-digest-reference/plan.md#L13-L87)

## Conclusion
SPEC-039 introduces a robust, typed operations document repository with a clear separation between immutable digests and optional prose, enforced by role-based access and strong provenance. Phase 1 delivers the substrate, shift summaries, and portal support, while leaving room for future document types and integrations. All eight requirements have been successfully implemented and delivered in v0.21.0, providing operators with a complete solution for creating, managing, and sharing operational documentation across their teams.

The system is now positioned to integrate with SPEC-040 capabilities, which will enhance the shift summaries with deterministic handover sections and improved prose generation defaults, further strengthening the operational handover workflow for relief operators. Additionally, SPEC-041 planning ensures continued evolution toward better operator experience through enhanced readability features and digest reference capabilities.

The combination of SPEC-039's solid foundation, SPEC-040's handover narrative enhancements, and the planned SPEC-041 readability improvements creates a comprehensive operational documentation system that scales from basic digest capture to sophisticated operator workflows.