# Skill Format Specification

<cite>
**Referenced Files in This Document**
- [skill-format.md](file://shared/shared-contracts/skill-format.md)
- [skill.schema.json](file://shared/shared-contracts/schemas/skill.schema.json)
- [SPEC-014-skills-and-grounded-guidance/spec.md](file://docs/specs/SPEC-014-skills-and-grounded-guidance/spec.md)
- [SPEC-055-develop-as-you-go-skill-graduation/spec.md](file://docs/specs/SPEC-055-develop-as-you-go-skill-graduation/spec.md)
- [SPEC-057-skill-composition-runbooks/spec.md](file://docs/specs/SPEC-057-skill-composition-runbooks/spec.md)
- [ingestion.py](file://products/skills-hub/src/skills_hub/services/ingestion.py)
- [test_contracts.py](file://products/skills-hub/tests/test_contracts.py)
- [test_ingestion.py](file://products/skills-hub/tests/test_ingestion.py)
- [test_sync.py](file://products/skills-hub/tests/test_sync.py)
- [RecoverAcmeAccount.md](file://samples/acme-admin/composition/skill/RecoverAcmeAccount.md)
- [README.md](file://samples/acme-admin/composition/README.md)
- [skills-guide.md](file://docs/guides/skills-guide.md)
</cite>

## Update Summary
**Changes Made**
- Updated skill format specification from v2 to v3 with comprehensive composition skill type documentation
- Added detailed sub_skills field validation rules and JSON schema updates
- Enhanced composition workflow documentation with two-layer validation (structural + resolution)
- Updated examples to include composition skills alongside executable flows
- Expanded troubleshooting guide for composition-specific validation errors

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
This document specifies the skill format used to author and package operational guidance for the platform. A skill is a Markdown document with YAML frontmatter that describes knowledge, executable browser or infrastructure flows, or compositions of single-target skills. The specification defines:
- Frontmatter metadata and validation rules
- Step definitions and tool references for executable flows
- Parameter specifications and credential handling
- Evidence collection points and expectations
- Composition patterns for multi-step workflows
- Variable substitution and conditional logic as authoring guidance (not runtime control flow)
- Validation, grading criteria, and graduation from draft to production
- Best practices for authoring, testing, and maintenance

The skill format is consumed by the skills-hub service, surfaced through the agent via read-only tools, and can be graduated into replayable executable flows under strict safety gates.

**Updated** The specification has been extended from v2 to v3 with the addition of composition skills, which allow operators to create validated runbooks that reference multiple single-target skills while maintaining security boundaries.

**Section sources**
- [skill-format.md:1-54](file://shared/shared-contracts/skill-format.md#L1-L54)
- [SPEC-014-skills-and-grounded-guidance/spec.md:43-180](file://docs/specs/SPEC-014-skills-and-grounded-guidance/spec.md#L43-L180)

## Project Structure
Skills are authored as Markdown files with YAML frontmatter and ingested by skills-hub from federated sources (Git repositories or local directories). The ingestion pipeline validates documents against the shared schema, stores them, and serves search/list/get endpoints. The agent accesses skills through tool-gateway's read-only tools, inheriting policy, audit, redaction, and evidence-panel behavior. Graduation transforms approved troubleshooting sessions into executable-flow skills that replay under one gate.

```mermaid
graph TB
subgraph "Authoring"
MD["Markdown skill<br/>YAML frontmatter"]
end
subgraph "Ingestion"
Hub["skills-hub"]
Store["Postgres store"]
end
subgraph "Consumption"
GW["tool-gateway"]
Agent["Agent"]
Portal["Operator portal"]
end
MD --> Hub
Hub --> Store
Agent --> GW
GW --> Hub
Portal --> GW
GW --> Store
```

**Diagram sources**
- [SPEC-014-skills-and-grounded-guidance/spec.md:69-180](file://docs/specs/SPEC-014-skills-and-grounded-guidance/spec.md#L69-L180)
- [skills-guide.md:12-35](file://docs/guides/skills-guide.md#L12-L35)

**Section sources**
- [SPEC-014-skills-and-grounded-guidance/spec.md:69-180](file://docs/specs/SPEC-014-skills-and-grounded-guidance/spec.md#L69-L180)
- [skills-guide.md:12-35](file://docs/guides/skills-guide.md#L12-L35)

## Core Components
- Skill envelope: defined by the shared JSON schema; includes identifiers, provenance, title, description, tags, version, optional web_target/risk_class/flow_intent/kind/steps/sub_skills, updated_at, and body where applicable.
- Frontmatter contract: required keys (title, description), optional keys (tags, version, source_url, web_target, risk_class, flow_intent, kind, steps, sub_skills), size caps, identity rules, and validation pre-flight.
- Executable flows: machine-readable step lists for replay, with tool names, arguments, and optional expectations; credentials referenced by set and field, never literals.
- Compositions: ordered lists of single-target sub-skills with notes; no authority of their own; each sub-skill keeps its own gate.
- Retrieval and grounding: deterministic keyword ranking across title/tags/body; citations include provenance; empty-match behavior returns success with no matches.
- Graduation: blast-radius re-validation, deterministic draft generation from an approved authoring trace, human merge, and replay under one gate with per-write signing.

**Updated** Added composition skills as a third skill class that provides validated runbooks of single-target skills without carrying authority of their own.

**Section sources**
- [skill.schema.json:1-146](file://shared/shared-contracts/schemas/skill.schema.json#L1-L146)
- [skill-format.md:31-160](file://shared/shared-contracts/skill-format.md#L31-L160)
- [SPEC-057-skill-composition-runbooks/spec.md:86-152](file://docs/specs/SPEC-057-skill-composition-runbooks/spec.md#L86-L152)
- [SPEC-014-skills-and-grounded-guidance/spec.md:108-180](file://docs/specs/SPEC-014-skills-and-grounded-guidance/spec.md#L108-L180)
- [SPEC-055-develop-as-you-go-skill-graduation/spec.md:157-249](file://docs/specs/SPEC-055-develop-as-you-go-skill-graduation/spec.md#L157-L249)

## Architecture Overview
The skill lifecycle spans authoring, ingestion, retrieval, execution, and graduation.

```mermaid
sequenceDiagram
participant Author as "Author"
participant Hub as "skills-hub"
participant Store as "Postgres"
participant GW as "tool-gateway"
participant Agent as "Agent"
participant Portal as "Portal"
Author->>Hub : Publish Markdown skill
Hub->>Hub : Validate frontmatter + schema
Hub->>Store : Persist validated record
Agent->>GW : skills.search / .get / .list
GW->>Hub : Query with auth
Hub-->>GW : Ranked results / full record
GW-->>Agent : Tool result with citations
Portal->>GW : View skills / evidence
GW-->>Portal : Rendered guidance + provenance
```

**Diagram sources**
- [SPEC-014-skills-and-grounded-guidance/spec.md:108-180](file://docs/specs/SPEC-014-skills-and-grounded-guidance/spec.md#L108-L180)
- [skills-guide.md:12-35](file://docs/guides/skills-guide.md#L12-L35)

## Detailed Component Analysis

### Skill Envelope and Frontmatter
- Required fields: skill_id, source_id, source_path, source_ref, title, description, updated_at.
- Optional fields: tags, version, source_url, web_target, risk_class, flow_intent, kind, steps, sub_skills, body.
- Identity: skill_id = <source_id>/<slug>, slug derived from file path segments normalized to lowercase alphanumeric and hyphens; moving files changes skill_id intentionally.
- Size caps: body ≤ 64 KiB; description ≤ 500 chars; ≤ 10 tags; steps list bounded at ingestion and replay.
- Unknown keys rejected; additionalProperties false on schema.

```mermaid
classDiagram
class Skill {
+string skill_id
+string source_id
+string source_path
+string source_ref
+string title
+string description
+string[] tags
+string version
+string source_url
+string web_target
+string risk_class
+string flow_intent
+string kind
+Step[] steps
+SubSkill[] sub_skills
+string updated_at
+string body
}
class Step {
+string tool
+object args
+string expect
}
class SubSkill {
+string skill_id
+string note
}
Skill "1" --> "0..*" Step : "steps"
Skill "1" --> "0..*" SubSkill : "sub_skills"
```

**Updated** Added SubSkill class representing composition references with skill_id and optional note fields.

**Diagram sources**
- [skill.schema.json:16-146](file://shared/shared-contracts/schemas/skill.schema.json#L16-L146)

**Section sources**
- [skill.schema.json:16-146](file://shared/shared-contracts/schemas/skill.schema.json#L16-L146)
- [skill-format.md:31-175](file://shared/shared-contracts/skill-format.md#L31-L175)

### Executable Flow Skills
- Declared by kind: executable_flow with a non-empty steps list and risk_class: write.
- Steps define canonical tool names, JSON-compatible arguments, and optional expectations.
- Credentials must be references (credential_set + field); literal secrets are rejected.
- Browser flows require web_target; non-browser mutating flows do not.
- Blast-radius re-validation during graduation enforces origin allowlists, declared risk_class, step budget, and credential resolution.

```mermaid
flowchart TD
Start(["Executable flow ingestion"]) --> CheckKind{"kind == executable_flow?"}
CheckKind --> |No| Knowledge["Treat as knowledge skill"]
CheckKind --> |Yes| CheckSteps{"steps present and non-empty?"}
CheckSteps --> |No| Reject["Reject: missing steps"]
CheckSteps --> |Yes| CheckRisk{"risk_class == write?"}
CheckRisk --> |No| RejectRisk["Reject: executable_flow requires write"]
CheckRisk --> |Yes| CheckBrowser{"Any web.* step?"}
CheckBrowser --> |Yes| CheckTarget{"web_target declared?"}
CheckBrowser --> |No| Proceed["Proceed"]
CheckTarget --> |No| RejectTarget["Reject: web.* requires web_target"]
CheckTarget --> |Yes| ValidateArgs["Validate args and credential refs"]
ValidateArgs --> Accept["Accept and store"]
Reject --> End(["Reject"])
RejectRisk --> End
RejectTarget --> End
Knowledge --> End
Proceed --> Accept
Accept --> End
```

**Diagram sources**
- [skill-format.md:55-141](file://shared/shared-contracts/skill-format.md#L55-L141)
- [skill.schema.json:80-111](file://shared/shared-contracts/schemas/skill.schema.json#L80-L111)

**Section sources**
- [skill-format.md:55-141](file://shared/shared-contracts/skill-format.md#L55-L141)
- [SPEC-055-develop-as-you-go-skill-graduation/spec.md:157-249](file://docs/specs/SPEC-055-develop-as-you-go-skill-graduation/spec.md#L157-L249)

### Composition Skills (v3)
A `composition` is an ordered, validated list of single-target sub-skill references. It expresses a multi-target workflow without widening any skill's authorization scope and carries no authority of its own. Each referenced sub-skill keeps its own HITL gate, enforced by the shipped browser flow identity guard and per-action infra gating.

```mermaid
flowchart TD
CStart(["Composition ingestion"]) --> ValidateStructural["Validate structural facts:<br/>- Non-empty sub_skills list<br/>- No web_target/steps/risk_class<br/>- Valid item schema"]
ValidateStructural --> ResolveRefs["Resolve sub_skills.skill_id<br/>against catalog"]
ResolveRefs --> Published{"All published?"}
Published --> |No| CReject["Reject: unresolved or unpublished"]
Published --> SingleTarget{"All single-target?"}
SingleTarget --> |No| CRejectST["Reject: multi-target sub-skill"]
SingleTarget --> NotComposition{"Not another composition?"}
NotComposition --> |No| CRejectNest["Reject: nested composition"]
NotComposition --> Bound{"Within sub-skill cap?"}
Bound --> |No| CRejectCap["Reject: too many sub-skills"]
Bound --> CAccept["Accept and store"]
```

**Updated** Added comprehensive composition validation flow showing both structural and resolution layers.

**Diagram sources**
- [SPEC-057-skill-composition-runbooks/spec.md:86-152](file://docs/specs/SPEC-057-skill-composition-runbooks/spec.md#L86-L152)
- [ingestion.py:491-586](file://products/skills-hub/src/skills_hub/services/ingestion.py#L491-L586)

**Section sources**
- [SPEC-057-skill-composition-runbooks/spec.md:86-152](file://docs/specs/SPEC-057-skill-composition-runbooks/spec.md#L86-L152)
- [ingestion.py:491-586](file://products/skills-hub/src/skills_hub/services/ingestion.py#L491-L586)

### Two-Layer Composition Validation
Composition validation operates in two distinct layers to ensure both immediate feedback and cross-skill consistency:

**Structural Layer (Pure Validation)**
- Validates document structure without catalog access
- Checks sub_skills list shape, item key sets, count caps, duplicate rules
- Enforces "no web_target/steps/risk_class" invariant for compositions
- Available in draft pre-flight and CLI validation

**Resolution Layer (Store-Consulting)**
- Resolves sub_skills.skill_id references against the catalog
- Verifies sub-skills are published and single-target
- Prevents nested compositions (Phase 1 restriction)
- Derives and persists display risk_class based on sub-skills

```mermaid
sequenceDiagram
participant Author as "Author"
participant Draft as "Draft Pre-flight"
participant Sync as "Sync Process"
participant Catalog as "Catalog"
Note over Author,Draft : Immediate validation feedback
Author->>Draft : Submit composition draft
Draft->>Draft : Validate structure only
Draft-->>Author : Pass/Fail with reasons
Note over Sync,Catalog : Cross-skill consistency check
Author->>Sync : Publish composition
Sync->>Catalog : Resolve sub_skill references
Catalog-->>Sync : Published status + targets
Sync->>Sync : Validate single-target + no nesting
Sync-->>Author : Final acceptance/rejection
```

**Diagram sources**
- [ingestion.py:491-586](file://products/skills-hub/src/skills_hub/services/ingestion.py#L491-L586)
- [test_sync.py:306-417](file://products/skills-hub/tests/test_sync.py#L306-L417)

**Section sources**
- [ingestion.py:491-586](file://products/skills-hub/src/skills_hub/services/ingestion.py#L491-L586)
- [test_sync.py:306-417](file://products/skills-hub/tests/test_sync.py#L306-L417)

### Retrieval and Grounded Guidance
- Deterministic keyword matching across title, tags, body with fixed weighting (title > tags > body).
- Ties broken by skill_id ascending; results bounded with excerpts.
- Empty match returns success with no matches; agent reports honestly when no guidance matched.
- Provenance included in results for citations.

```mermaid
sequenceDiagram
participant Agent as "Agent"
participant GW as "tool-gateway"
participant Hub as "skills-hub"
Agent->>GW : skills.search(q, filters)
GW->>Hub : Authenticated query
Hub->>Hub : Rank by title/tags/body
Hub-->>GW : Ranked hits with provenance
GW-->>Agent : Results + data_summary
Note over Agent,GW : Evidence panel shows cited guidance chips
```

**Diagram sources**
- [SPEC-014-skills-and-grounded-guidance/spec.md:108-180](file://docs/specs/SPEC-014-skills-and-grounded-guidance/spec.md#L108-L180)

**Section sources**
- [SPEC-014-skills-and-grounded-guidance/spec.md:108-180](file://docs/specs/SPEC-014-skills-and-grounded-guidance/spec.md#L108-L180)

### Graduation Workflow (Draft to Production)
- Capture: durable authoring-trace store records approved mutations with secret-safe parameterization.
- Re-validation: blast-radius checks (step count, origins, declared risk_class, credential references).
- Draft generation: deterministic build_executable_flow_draft from trace; validated via skills-hub ingestion path.
- Human review: preview rendered + raw; download for merge into team repo.
- Replay: graduated flow replays under one gate with per-write signing and gateway deviation guard.

```mermaid
sequenceDiagram
participant Operator as "Operator"
participant AP as "agent-platform"
participant Hub as "skills-hub"
participant GW as "tool-gateway"
Operator->>AP : POST /sessions/{id}/skill-graduate
AP->>AP : Load authoring trace + target declaration
AP->>AP : revalidate_blast_radius()
AP->>AP : build_executable_flow_draft()
AP->>Hub : Validate markdown via ingestion path
Hub-->>AP : valid/invalid
AP-->>Operator : Preview (rendered + raw)
Operator->>Operator : Review and merge into repo
Note over GW,AP : Replay later under one gate with per-write signing
```

**Diagram sources**
- [SPEC-055-develop-as-you-go-skill-graduation/spec.md:181-249](file://docs/specs/SPEC-055-develop-as-you-go-skill-graduation/spec.md#L181-L249)

**Section sources**
- [SPEC-055-develop-as-you-go-skill-graduation/spec.md:181-249](file://docs/specs/SPEC-055-develop-as-you-go-skill-graduation/spec.md#L181-L249)

### Examples of Well-formed Skills
- Password reset flow (write-class browser skill): demonstrates web_target, risk_class: write, flow_intent, single HITL gate on destructive mutation, credential-set references, and evidence capture.
- Ad-hoc password reset (per-action approval): demonstrates unbound writes parking per-action cards, change-request projections, and reference-only credential entry.
- Account recovery composition (v3): demonstrates composition of multiple single-target skills with ordered execution guidance while maintaining separate authorization boundaries.

Use these samples to model your own skills for incident response, system maintenance, and troubleshooting procedures.

**Updated** Added composition skill example demonstrating multi-target workflow composition.

**Section sources**
- [ResetUserPassword.md:1-190](file://samples/web-checks/password-reset/skill/ResetUserPassword.md#L1-L190)
- [ResetPasswordAdHoc.md:1-220](file://samples/web-checks/adhoc-password-reset/skill/ResetPasswordAdHoc.md#L1-L220)
- [RecoverAcmeAccount.md:1-194](file://samples/acme-admin/composition/skill/RecoverAcmeAccount.md#L1-L194)

## Dependency Analysis
- Schema lockstep: skill.schema.json mirrors skills-hub schemas and ingestion validation; any drift breaks ingestion.
- Retrieval depends on deterministic scoring and provenance fields.
- Graduation depends on authoring-trace capture at approval seams and blast-radius re-validation.
- Compositions depend on published single-target sub-skills; no new enforcement machinery beyond existing flow context guards.

```mermaid
graph LR
Schema["skill.schema.json"] --> Ingestion["skills-hub ingestion"]
Ingestion --> Store["Postgres store"]
Store --> Search["Search/List/Get"]
Trace["Authoring trace"] --> Graduation["Graduation endpoint"]
Graduation --> Draft["Executable-flow draft"]
Draft --> Ingestion
Composition["Composition skill"] --> SubSkills["Single-target sub-skills"]
Composition --> Resolution["Two-layer validation"]
```

**Updated** Added composition validation dependency showing two-layer architecture.

**Diagram sources**
- [skill.schema.json:1-146](file://shared/shared-contracts/schemas/skill.schema.json#L1-L146)
- [SPEC-055-develop-as-you-go-skill-graduation/spec.md:111-249](file://docs/specs/SPEC-055-develop-as-you-go-skill-graduation/spec.md#L111-L249)
- [SPEC-057-skill-composition-runbooks/spec.md:86-152](file://docs/specs/SPEC-057-skill-composition-runbooks/spec.md#L86-L152)

**Section sources**
- [SPEC-055-develop-as-you-go-skill-graduation/spec.md:111-249](file://docs/specs/SPEC-055-develop-as-you-go-skill-graduation/spec.md#L111-L249)

## Performance Considerations
- Step budgets: replay bounded by GATEWAY_BROWSER_FLOW_MAX_STEPS; graduation twin AGENT_SKILL_GRADUATION_MAX_STEPS ensures alignment.
- Size caps: body ≤ 64 KiB; steps list serialized ≤ 64 KiB; description ≤ 500 chars; tags ≤ 10.
- Scoring: deterministic keyword ranking avoids ML overhead; ties broken by skill_id.
- Storage: steps stored as JSONB; backends must agree on NULL vs None mapping.
- Composition limits: SKILLS_COMPOSITION_MAX_SUB_SKILLS (default 8) × GATEWAY_BROWSER_FLOW_MAX_STEPS (default 20) = 160 worst-case unlocked browser writes per run.

**Updated** Added composition performance considerations including sub-skill limits and worst-case scenario analysis.

## Troubleshooting Guide
- New/revised skill not visible: sync interval not yet elapsed or ConfigMap wiring missed; restart deployment or wait for next sync.
- Source reports rejections: inspect status endpoint for per-document reasons; fix frontmatter/schema violations.
- Git source errors: unreachable URL, expired token, or missing subpath; previous slice continues serving until resolved.
- Search returns no matches: verify skills.list/catalog; check status for accepted counts.
- Agent claims no skills exist: ensure skills connector configured (GATEWAY_SKILLS_SERVICE_URL) and query-secret matches.
- Graduation fails: blast-radius refusal enumerates guard failures; correct origins, risk_class, step budget, or credential references.
- Composition validation fails: check structural validation (missing sub_skills, forbidden keys) or resolution validation (unresolved references, nested compositions, multi-target sub-skills).

**Updated** Added composition-specific troubleshooting scenarios covering both structural and resolution layer failures.

**Section sources**
- [skills-guide.md:338-373](file://docs/guides/skills-guide.md#L338-L373)
- [SPEC-055-develop-as-you-go-skill-graduation/spec.md:181-249](file://docs/specs/SPEC-055-develop-as-you-go-skill-graduation/spec.md#L181-L249)

## Conclusion
The skill format standardizes how operational guidance is authored, validated, retrieved, and, when appropriate, graduated into replayable executable flows. It balances flexibility (knowledge, executable flows, compositions) with strong safety (schema validation, credential references, blast-radius re-validation, one-gate replay). Teams should use the provided examples as templates, validate locally before publishing, and follow best practices for clarity, security, and maintainability.

**Updated** The v3 specification adds composition skills, enabling operators to create validated multi-target runbooks while preserving security boundaries through per-sub-skill authorization.

## Appendices

### Authoring Best Practices
- Keep titles concise and descriptions informative; tag with domain-specific keywords.
- For executable flows, declare exactly one write-tier interaction and park the HITL gate on the destructive mutation.
- Use credential-set references; never embed secrets in skills.
- Split long guides; respect size caps.
- Prefer stable file paths to preserve skill_id and citation continuity.
- For compositions, ensure all referenced sub-skills are published and single-target; keep sub_skills within configured limits.

**Updated** Added composition authoring best practices.

**Section sources**
- [skill-format.md:31-175](file://shared/shared-contracts/skill-format.md#L31-L175)
- [RecoverAcmeAccount.md:21-194](file://samples/acme-admin/composition/skill/RecoverAcmeAccount.md#L21-L194)

### Testing Approaches
- Validate locally using the same code path as the service; exit code 0 indicates safe to publish.
- Use e2e smoke tests after content changes; assert deterministic outcomes.
- Rely on unit tests for scoring determinism and storage mapping.
- Test composition validation across both structural and resolution layers.

**Updated** Added composition testing approaches.

**Section sources**
- [skills-guide.md:85-108](file://docs/guides/skills-guide.md#L85-L108)
- [test_contracts.py:106-146](file://products/skills-hub/tests/test_contracts.py#L106-L146)
- [test_ingestion.py:900-1052](file://products/skills-hub/tests/test_ingestion.py#L900-L1052)

### Maintenance Strategies
- Keep source_url and NOTICE files for adapted open-source content.
- Monitor metrics: syncs_total, ingest_rejected_total, store_skills, searches_total.
- Audit trail: skill drafts and graduations recorded; track approvals and outcomes.
- Monitor composition resolution failures and adjust sub-skill references as needed.

**Updated** Added composition maintenance considerations.

**Section sources**
- [skill-format.md:188-203](file://shared/shared-contracts/skill-format.md#L188-L203)
- [skills-guide.md:350-373](file://docs/guides/skills-guide.md#L350-L373)