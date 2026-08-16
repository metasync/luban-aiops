# SPEC-014: Skills and Grounded Guidance Specification

<cite>
**Referenced Files in This Document**
- [spec.md](file://docs/specs/SPEC-014-skills-and-grounded-guidance/spec.md)
- [plan.md](file://docs/specs/SPEC-014-skills-and-grounded-guidance/plan.md)
- [tasks.md](file://docs/specs/SPEC-014-skills-and-grounded-guidance/tasks.md)
- [skill-format.md](file://shared/shared-contracts/skill-format.md)
- [skill.schema.json](file://shared/shared-contracts/schemas/skill.schema.json)
- [app.py](file://products/skills-hub/src/skills_hub/app.py)
- [main.py](file://products/skills-hub/src/skills_hub/main.py)
- [skills.py](file://products/skills-hub/src/skills_hub/api/routes/skills.py)
- [config.py](file://products/skills-hub/src/skills_hub/core/config.py)
- [ingestion.py](file://products/skills-hub/src/skills_hub/services/ingestion.py)
- [skill_store.py](file://products/skills-hub/src/skills_hub/services/skill_store.py)
- [scoring.py](file://products/skills-hub/src/skills_hub/services/scoring.py)
- [skills_connector.py](file://products/tool-gateway/src/tool_gateway/tools/skills_connector.py)
- [runtime_settings.py](file://products/agent-platform/src/agent_service/runtime_settings.py)
</cite>

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
SPEC-014 delivers Release 2 of the platform’s skills and grounded guidance capability. It introduces a new skills-hub service that ingests team-owned Markdown runbooks from federated sources, validates them against a shared contract, indexes them, and exposes deterministic search and retrieval APIs. The agent-platform extends its system prompt to consult skills when answering procedure or remediation questions, and tool-gateway registers read-only skills tools so all skill access flows through policy, audit, redaction, and evidence panels without expanding the trust surface.

Key outcomes:
- A stable skill document contract with JSON schema validation and frontmatter rules.
- Federated ingestion from local directories and Git repositories with per-source atomic swaps.
- Deterministic keyword-based search with explainable ranking and provenance.
- Read-only skills tools exposed via tool-gateway, inheriting existing security and observability controls.
- Operator-facing citations visible in the portal evidence panel and chat transcripts.

**Section sources**
- [spec.md:13-41](file://docs/specs/SPEC-014-skills-and-grounded-guidance/spec.md#L13-L41)
- [plan.md:3-22](file://docs/specs/SPEC-014-skills-and-grounded-guidance/plan.md#L3-L22)

## Project Structure
The implementation spans three products plus shared contracts:
- skills-hub: FastAPI service for ingestion, storage, and retrieval.
- tool-gateway: Registers skills tools and proxies calls to skills-hub.
- agent-platform: Extends system prompt and auto-allowed tools.
- shared contracts: Skill schema and format convention consumed by skills-hub and tests.

```mermaid
graph TB
subgraph "Agent Platform"
AP["Agent Runtime Settings"]
end
subgraph "Tool Gateway"
TG["Skills Connector"]
end
subgraph "Skills Hub"
SH_API["Retrieval API"]
SH_ING["Ingestion"]
SH_STORE["Skill Store"]
SH_SCORE["Scorer"]
SH_CFG["Config & Auth"]
end
subgraph "Shared Contracts"
SCHEMA["Skill Schema"]
FORMAT["Skill Format"]
end
AP --> TG
TG --> SH_API
SH_API --> SH_STORE
SH_STORE --> SH_SCORE
SH_ING --> SH_STORE
SH_API --> SH_CFG
SH_ING --> SCHEMA
SH_ING --> FORMAT
```

**Diagram sources**
- [app.py:20-56](file://products/skills-hub/src/skills_hub/app.py#L20-L56)
- [skills.py:17-119](file://products/skills-hub/src/skills_hub/api/routes/skills.py#L17-L119)
- [ingestion.py:151-229](file://products/skills-hub/src/skills_hub/services/ingestion.py#L151-L229)
- [skill_store.py:30-67](file://products/skills-hub/src/skills_hub/services/skill_store.py#L30-L67)
- [scoring.py:28-97](file://products/skills-hub/src/skills_hub/services/scoring.py#L28-L97)
- [config.py:147-189](file://products/skills-hub/src/skills_hub/core/config.py#L147-L189)
- [skills_connector.py:71-88](file://products/tool-gateway/src/tool_gateway/tools/skills_connector.py#L71-L88)
- [runtime_settings.py:8-22](file://products/agent-platform/src/agent_service/runtime_settings.py#L8-L22)
- [skill.schema.json:1-76](file://shared/shared-contracts/schemas/skill.schema.json#L1-L76)
- [skill-format.md:1-85](file://shared/shared-contracts/skill-format.md#L1-L85)

**Section sources**
- [spec.md:43-213](file://docs/specs/SPEC-014-skills-and-grounded-guidance/spec.md#L43-L213)
- [plan.md:24-235](file://docs/specs/SPEC-014-skills-and-grounded-guidance/plan.md#L24-L235)

## Core Components
- Skill contract: Envelope and frontmatter rules define how skills are authored and validated.
- Ingestion pipeline: Walks source directories, parses YAML frontmatter, enforces size caps and allowed keys, derives slugs, and rejects invalid documents with structured reasons.
- Storage backends: In-memory store for dev/tests; PostgreSQL store for production with per-source atomic replace and GIN full-text index pre-filtering.
- Search and scoring: Deterministic keyword scorer with fixed weights (title > tags > body), capped body occurrences, and stable tie-breaking by skill id.
- Retrieval API: List, get-by-id, and search endpoints with auth, parameter validation, pagination, and bounded results.
- Tool connector: Registers read-only skills tools in tool-gateway, authenticates to skills-hub with gateway-held credentials, maps upstream errors, and emits standard evidence envelopes.
- Agent integration: System prompt instructs the agent to consult skills for procedure/interpretation/remediation and cite used skills; tools are auto-allowed.

**Section sources**
- [skill.schema.json:1-76](file://shared/shared-contracts/schemas/skill.schema.json#L1-L76)
- [skill-format.md:9-68](file://shared/shared-contracts/skill-format.md#L9-L68)
- [ingestion.py:85-149](file://products/skills-hub/src/skills_hub/services/ingestion.py#L85-L149)
- [skill_store.py:72-154](file://products/skills-hub/src/skills_hub/services/skill_store.py#L72-L154)
- [skill_store.py:247-432](file://products/skills-hub/src/skills_hub/services/skill_store.py#L247-L432)
- [scoring.py:28-97](file://products/skills-hub/src/skills_hub/services/scoring.py#L28-L97)
- [skills.py:34-119](file://products/skills-hub/src/skills_hub/api/routes/skills.py#L34-L119)
- [skills_connector.py:143-401](file://products/tool-gateway/src/tool_gateway/tools/skills_connector.py#L143-L401)
- [runtime_settings.py:8-22](file://products/agent-platform/src/agent_service/runtime_settings.py#L8-L22)

## Architecture Overview
End-to-end flow from agent request to cited skill result:

```mermaid
sequenceDiagram
participant Client as "Client"
participant Gateway as "Platform Gateway"
participant Agent as "Agent Platform"
participant Tools as "Tool Gateway"
participant Skills as "Skills Hub"
participant Store as "Skill Store"
participant Score as "Scorer"
Client->>Gateway : Chat request
Gateway->>Agent : Forward to runtime kernel
Agent->>Tools : Invoke skills.search (auto-allowed)
Tools->>Skills : GET /api/v1/skills/search?q=...&limit=...
Skills->>Store : search(query, limit, filters)
Store->>Score : rank(query, candidates, limit)
Score-->>Store : Ordered hits with excerpts
Store-->>Skills : Hits + provenance
Skills-->>Tools : Matches + total
Tools-->>Agent : ToolResult with data_summary
Agent-->>Gateway : Final answer citing skills
Gateway-->>Client : Response with evidence frames
```

**Diagram sources**
- [skills_connector.py:187-232](file://products/tool-gateway/src/tool_gateway/tools/skills_connector.py#L187-L232)
- [skills.py:65-101](file://products/skills-hub/src/skills_hub/api/routes/skills.py#L65-L101)
- [skill_store.py:366-392](file://products/skills-hub/src/skills_hub/services/skill_store.py#L366-L392)
- [scoring.py:85-97](file://products/skills-hub/src/skills_hub/services/scoring.py#L85-L97)
- [runtime_settings.py:8-22](file://products/agent-platform/src/agent_service/runtime_settings.py#L8-L22)

## Detailed Component Analysis

### Skill Contract and Validation
- Envelope fields include globally unique skill_id namespaced by source_id, provenance fields (source_path, source_ref, updated_at), human-readable title/description, optional tags/version/source_url, and body where applicable.
- Frontmatter must be a YAML mapping with required keys and strict size caps; unknown keys are rejected.
- Slug derivation is path-based and sanitized, ensuring moves within a repo change skill_id intentionally.
- Ingestion walks directories, skips README/NOTICE files, handles Kubernetes projected volumes, and reports per-document rejections.

```mermaid
flowchart TD
Start(["Start Ingestion"]) --> Walk["Walk *.md files"]
Walk --> Parse["Parse frontmatter YAML"]
Parse --> ValidFM{"Valid mapping?"}
ValidFM --> |No| RejectFM["Reject: invalid frontmatter"]
ValidFM --> |Yes| CheckKeys["Check allowed keys"]
CheckKeys --> SizeCaps["Enforce size caps"]
SizeCaps --> Slug["Derive slug from path"]
Slug --> Duplicate{"Duplicate slug in source?"}
Duplicate --> |Yes| RejectDup["Reject: duplicate slug"]
Duplicate --> |No| BuildRecord["Build Skill record"]
BuildRecord --> Next["Next file"]
RejectFM --> Next
RejectDup --> Next
Next --> End(["Snapshot complete"])
```

**Diagram sources**
- [ingestion.py:151-229](file://products/skills-hub/src/skills_hub/services/ingestion.py#L151-L229)
- [skill.schema.json:1-76](file://shared/shared-contracts/schemas/skill.schema.json#L1-L76)
- [skill-format.md:26-68](file://shared/shared-contracts/skill-format.md#L26-L68)

**Section sources**
- [skill.schema.json:1-76](file://shared/shared-contracts/schemas/skill.schema.json#L1-L76)
- [skill-format.md:9-68](file://shared/shared-contracts/skill-format.md#L9-L68)
- [ingestion.py:85-149](file://products/skills-hub/src/skills_hub/services/ingestion.py#L85-L149)
- [ingestion.py:151-229](file://products/skills-hub/src/skills_hub/services/ingestion.py#L151-L229)

### Federated Ingestion and Sync
- Sources are configured via SKILLS_SOURCES entries supporting local directories and Git repositories.
- Each source syncs on an interval, builds a fully validated snapshot, and atomically replaces the source slice in the store.
- Rejections are reported per document with structured reasons; zero valid docs still swap to an empty slice.
- Status endpoint exposes last sync time, ref, accepted count, and rejection list.

```mermaid
classDiagram
class SourceSpec {
+string source_id
+string type
+string path
+string url
+string ref
}
class SkillsSettings {
+tuple sources
+dict git_tokens
+int sync_interval_seconds
+string data_path
+string store_backend
+string db_url
+tuple query_clients
+string workload_issuer_url
+string workload_audience
+tuple workload_clients
+from_env() SkillsSettings
}
SourceSpec --> SkillsSettings : "parsed into"
```

**Diagram sources**
- [config.py:22-31](file://products/skills-hub/src/skills_hub/core/config.py#L22-L31)
- [config.py:147-189](file://products/skills-hub/src/skills_hub/core/config.py#L147-L189)

**Section sources**
- [config.py:49-117](file://products/skills-hub/src/skills_hub/core/config.py#L49-L117)
- [config.py:147-189](file://products/skills-hub/src/skills_hub/core/config.py#L147-L189)
- [app.py:20-56](file://products/skills-hub/src/skills_hub/app.py#L20-L56)

### Storage Backends
- InMemorySkillStore: Per-source snapshot map with atomic reference swap; suitable for dev/tests.
- PostgresSkillStore: Durable table with GIN index on title/body tsvector; per-source delete+insert transaction; tag filtering uses safe constructs; search pre-filters via full-text then re-ranks with shared scorer for byte-identical ordering.

```mermaid
classDiagram
class SkillStore {
<<interface>>
+initialize() void
+replace_source(source_id, records) int
+prune_sources(source_ids) int
+get(skill_id) Skill?
+list(offset, limit, source?, tag?) tuple
+search(query, limit, source?, tag?) list
+count() int
+ready() bool
+close() void
}
class InMemorySkillStore {
-dict _by_source
+initialize() void
+replace_source(source_id, records) int
+prune_sources(source_ids) int
+get(skill_id) Skill?
+list(offset, limit, source?, tag?) tuple
+search(query, limit, source?, tag?) list
+count() int
+ready() bool
+close() void
}
class PostgresSkillStore {
-string _db_url
+initialize() void
+replace_source(source_id, records) int
+prune_sources(source_ids) int
+get(skill_id) Skill?
+list(offset, limit, source?, tag?) tuple
+search(query, limit, source?, tag?) list
+count() int
+ready() bool
+close() void
}
SkillStore <|.. InMemorySkillStore
SkillStore <|.. PostgresSkillStore
```

**Diagram sources**
- [skill_store.py:30-67](file://products/skills-hub/src/skills_hub/services/skill_store.py#L30-L67)
- [skill_store.py:72-154](file://products/skills-hub/src/skills_hub/services/skill_store.py#L72-L154)
- [skill_store.py:247-432](file://products/skills-hub/src/skills_hub/services/skill_store.py#L247-L432)

**Section sources**
- [skill_store.py:72-154](file://products/skills-hub/src/skills_hub/services/skill_store.py#L72-L154)
- [skill_store.py:247-432](file://products/skills-hub/src/skills_hub/services/skill_store.py#L247-L432)

### Deterministic Scoring and Ranking
- Tokenization uses lowercase alphanumeric tokens.
- Weights: title ×3, tags ×2, body ×1 (capped occurrences).
- Zero-score records excluded; ties broken by skill_id ascending.
- Excerpts bounded to ≤400 chars around first matched region; fallback to description head if match only in title/tags.

```mermaid
flowchart TD
Q["Query tokens"] --> S["For each skill"]
S --> T["Title matches ×3"]
S --> G["Tag matches ×2"]
S --> B["Body occurrences ×1 (capped)"]
T --> Sum["Sum scores"]
G --> Sum
B --> Sum
Sum --> Filter{"Score > 0?"}
Filter --> |No| Drop["Exclude"]
Filter --> |Yes| Hit["Create SearchHit"]
Hit --> Sort["Sort by (-score, skill_id)"]
Sort --> Cap["Cap at limit"]
```

**Diagram sources**
- [scoring.py:28-97](file://products/skills-hub/src/skills_hub/services/scoring.py#L28-L97)

**Section sources**
- [scoring.py:28-97](file://products/skills-hub/src/skills_hub/services/scoring.py#L28-L97)

### Retrieval API
- Endpoints:
  - GET /api/v1/skills: list with offset/limit, optional source/tag filters; returns summaries without bodies.
  - GET /api/v1/skills/{skill_id:path}: full record including body; 404 for unknown ids.
  - GET /api/v1/skills/search: ranked matches with excerpt and provenance; q required; limit capped.
- Authentication: Basic clients or projected workload tokens; unauthenticated requests receive 401.
- Parameter validation: Returns structured 400 errors for malformed inputs.

```mermaid
sequenceDiagram
participant C as "Caller"
participant R as "FastAPI Router"
participant A as "QueryAuth"
participant ST as "SkillStore"
participant S as "Scorer"
C->>R : GET /api/v1/skills/search?q=...
R->>A : authenticate_caller()
A-->>R : OK
R->>ST : search(q, limit, source?, tag?)
ST->>S : rank(q, candidates, limit)
S-->>ST : ordered hits
ST-->>R : hits
R-->>C : {matches, total}
```

**Diagram sources**
- [skills.py:34-119](file://products/skills-hub/src/skills_hub/api/routes/skills.py#L34-L119)
- [skill_store.py:366-392](file://products/skills-hub/src/skills_hub/services/skill_store.py#L366-L392)
- [scoring.py:85-97](file://products/skills-hub/src/skills_hub/services/scoring.py#L85-L97)

**Section sources**
- [skills.py:34-119](file://products/skills-hub/src/skills_hub/api/routes/skills.py#L34-L119)

### Tool-Gateway Skills Connector
- Registers read-only tools: skills.search, skills.get, skills.list.
- Parameters validated locally; skill_id validated against namespaced pattern before URL interpolation.
- HTTP transport uses httpx with timeout and Basic auth from gateway-held credentials.
- Error mapping: 404 → SKILL_NOT_FOUND; unreachable → TOOL_EXECUTION_ERROR; other 4xx pass through with code/message.
- Evidence envelope built for every outcome; tool invocations inherit policy, audit emission, and redaction.

```mermaid
sequenceDiagram
participant AG as "Agent"
participant TG as "Tool Gateway"
participant SC as "SkillsConnector"
participant SH as "Skills Hub"
AG->>TG : Call skills.search(query, source?, tag?, limit?)
TG->>SC : execute(parameters, identity)
SC->>SH : GET /api/v1/skills/search?q=...
alt Success
SH-->>SC : {matches, total}
SC-->>TG : ToolResult(status="success", data={matches,total})
else Upstream error
SH-->>SC : 4xx payload
SC-->>TG : ToolResult(error mapped)
else Transport error
SC-->>TG : ToolResult(TOOL_EXECUTION_ERROR)
end
TG-->>AG : Result with evidence envelope
```

**Diagram sources**
- [skills_connector.py:143-232](file://products/tool-gateway/src/tool_gateway/tools/skills_connector.py#L143-L232)
- [skills_connector.py:235-294](file://products/tool-gateway/src/tool_gateway/tools/skills_connector.py#L235-L294)
- [skills_connector.py:297-401](file://products/tool-gateway/src/tool_gateway/tools/skills_connector.py#L297-L401)

**Section sources**
- [skills_connector.py:71-88](file://products/tool-gateway/src/tool_gateway/tools/skills_connector.py#L71-L88)
- [skills_connector.py:143-232](file://products/tool-gateway/src/tool_gateway/tools/skills_connector.py#L143-L232)
- [skills_connector.py:235-294](file://products/tool-gateway/src/tool_gateway/tools/skills_connector.py#L235-L294)
- [skills_connector.py:297-401](file://products/tool-gateway/src/tool_gateway/tools/skills_connector.py#L297-L401)

### Agent Integration and Citations
- DEFAULT_SYSTEM_PROMPT extended to instruct the agent to consult skills for procedure/interpretation/remediation, cite used skills by title or skill_id, separate skill guidance from live cluster data, and report no-match honestly.
- Auto-allowed tools include skills.search and skills.get, enabling frictionless retrieval when needed.
- Empty-match behavior: skills.search returns success with empty matches; agent reports no team guidance matched.

**Section sources**
- [runtime_settings.py:8-22](file://products/agent-platform/src/agent_service/runtime_settings.py#L8-L22)
- [plan.md:147-167](file://docs/specs/SPEC-014-skills-and-grounded-guidance/plan.md#L147-L167)

## Dependency Analysis
- skills-hub depends on shared contracts for schema and format; uses FastAPI router, metrics, observability, and request context modules.
- Retrieval routes depend on query authentication and skill store; store implementations depend on scorer for consistent ranking.
- tool-gateway depends on base tool framework and registry; skills connector depends on httpx and error mapping utilities.
- agent-platform depends on runtime settings for prompt and allow-list.

```mermaid
graph LR
SCHEMA["skill.schema.json"] --> INGEST["ingestion.py"]
FORMAT["skill-format.md"] --> INGEST
INGEST --> STORE["skill_store.py"]
STORE --> SCORE["scoring.py"]
ROUTE["api/routes/skills.py"] --> STORE
ROUTE --> AUTH["query_auth (via config)"]
CONNECTOR["tools/skills_connector.py"] --> ROUTE
AGENT["runtime_settings.py"] --> CONNECTOR
```

**Diagram sources**
- [skill.schema.json:1-76](file://shared/shared-contracts/schemas/skill.schema.json#L1-L76)
- [skill-format.md:1-85](file://shared/shared-contracts/skill-format.md#L1-L85)
- [ingestion.py:151-229](file://products/skills-hub/src/skills_hub/services/ingestion.py#L151-L229)
- [skill_store.py:30-67](file://products/skills-hub/src/skills_hub/services/skill_store.py#L30-L67)
- [scoring.py:28-97](file://products/skills-hub/src/skills_hub/services/scoring.py#L28-L97)
- [skills.py:17-119](file://products/skills-hub/src/skills_hub/api/routes/skills.py#L17-L119)
- [skills_connector.py:71-88](file://products/tool-gateway/src/tool_gateway/tools/skills_connector.py#L71-L88)
- [runtime_settings.py:8-22](file://products/agent-platform/src/agent_service/runtime_settings.py#L8-L22)

**Section sources**
- [plan.md:24-235](file://docs/specs/SPEC-014-skills-and-grounded-guidance/plan.md#L24-L235)
- [spec.md:250-266](file://docs/specs/SPEC-014-skills-and-grounded-guidance/spec.md#L250-L266)

## Performance Considerations
- Scoring is O(n·t) per query where n is candidate count and t is token count; body occurrence cap prevents long bodies from dominating scores.
- PostgreSQL search uses GIN full-text index to reduce candidate set; Python re-ranking ensures deterministic ordering parity with in-memory store.
- Pagination limits protect payloads: list limit capped at 100, search limit capped at 20; excerpts bounded to ≤400 chars.
- Atomic per-source replace avoids partial reads during sync; failed sync preserves previous snapshot.
- Timeouts and structured errors prevent cascading failures in tool execution.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and diagnostics:
- Invalid frontmatter or unknown keys: ingestion rejects with structured reason; check skill-format constraints and size caps.
- Duplicate slug within a source: ingestion rejects; ensure unique paths per source.
- Unreachable skills-hub: tool-gateway returns TOOL_EXECUTION_ERROR; verify GATEWAY_SKILLS_SERVICE_URL and credentials.
- Unknown skill id: 404 SKILL_NOT_FOUND; confirm namespaced id format and existence.
- Unauthorized access: 401 UNAUTHORIZED; configure SKILLS_QUERY_CLIENTS or workload tokens correctly.
- Empty matches: skills.search returns success with empty matches; agent should report no team guidance matched.

Operational checks:
- Use GET /api/v1/skills/status to inspect last sync outcomes per source, accepted counts, and rejections.
- Validate sources locally with the standalone validator CLI to catch issues before deployment.

**Section sources**
- [ingestion.py:85-149](file://products/skills-hub/src/skills_hub/services/ingestion.py#L85-L149)
- [skills.py:34-119](file://products/skills-hub/src/skills_hub/api/routes/skills.py#L34-L119)
- [skills_connector.py:117-137](file://products/tool-gateway/src/tool_gateway/tools/skills_connector.py#L117-L137)
- [plan.md:86-93](file://docs/specs/SPEC-014-skills-and-grounded-guidance/plan.md#L86-L93)

## Conclusion
SPEC-014 integrates team-owned operational knowledge into the platform in a secure, auditable, and operator-visible way. By enforcing a strict skill contract, providing deterministic retrieval, and routing access through existing tool-execution guardrails, it enhances agent answers with cited guidance while preserving the trust model. The design supports future enhancements such as semantic retrieval or per-team scoping without disrupting current behavior.

[No sources needed since this section summarizes without analyzing specific files]

## Appendices
- Deployment and configuration details are covered in the plan and tasks, including overlay wiring, secrets sync, and sample skill sources.
- Living-state documentation updates include product READMEs, configuration references, tool configuration guides, and architecture overview diagrams.

**Section sources**
- [plan.md:168-235](file://docs/specs/SPEC-014-skills-and-grounded-guidance/plan.md#L168-L235)
- [tasks.md:49-67](file://docs/specs/SPEC-014-skills-and-grounded-guidance/tasks.md#L49-L67)