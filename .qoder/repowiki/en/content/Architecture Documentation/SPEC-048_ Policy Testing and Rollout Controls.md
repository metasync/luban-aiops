# SPEC-048: Policy Testing and Rollout Controls

<cite>
**Referenced Files in This Document**
- [spec.md](file://docs/specs/SPEC-048-policy-testing-rollout-controls/spec.md)
- [plan.md](file://docs/specs/SPEC-048-policy-testing-rollout-controls/plan.md)
- [tasks.md](file://docs/specs/SPEC-048-policy-testing-rollout-controls/tasks.md)
- [policy_engine.py (platform-gateway)](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py)
- [policy_engine.py (tool-gateway)](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py)
- [policy_matrix.py](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py)
- [policy.py (routes)](file://products/platform-gateway/src/platform_gateway/api/routes/policy.py)
- [policy-scenarios.yaml](file://shared/shared-contracts/policies/policy-scenarios.yaml)
- [validate_policy_scenarios.py](file://shared/shared-contracts/scripts/validate_policy_scenarios.py)
- [Makefile](file://Makefile)
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

## Introduction
SPEC-048 introduces policy testing and rollout controls for the platform’s policy engines without changing evaluation semantics or bundle schema. It adds a content-hash provenance field to live surfaces, a scenario-expectation harness integrated into verification, a review-time impact report comparing bundles, and a documented rollout runbook. The goal is to prevent silent grant flips, make enforcement transparent, and give operators confidence that the running bundle matches the intended commit.

Key outcomes:
- Bundle provenance hash on matrix and readiness surfaces.
- Scenario expectations enforced by CI via `make verify`.
- Review-time diff of role×action outcome transitions.
- Explicit restart-based rollout posture with no hot reload.

**Section sources**
- [spec.md:19-42](file://docs/specs/SPEC-048-policy-testing-rollout-controls/spec.md#L19-L42)
- [plan.md:3-15](file://docs/specs/SPEC-048-policy-testing-rollout-controls/plan.md#L3-L15)

## Project Structure
SPEC-048 touches two policy engines, their transparency surface, shared scenario definitions, and root Make targets that orchestrate verification and reporting.

```mermaid
graph TB
subgraph "Policy Engines"
PG["platform-gateway<br/>policy_engine.py"]
TG["tool-gateway<br/>policy_engine.py"]
end
subgraph "Transparency Surface"
PM["policy_matrix.py"]
PR["api/routes/policy.py"]
end
subgraph "Shared Contracts"
SCEN["policy-scenarios.yaml"]
VSCN["validate_policy_scenarios.py"]
end
subgraph "Build & Verify"
MK["Makefile"]
end
MK --> VSCN
MK --> PR
VSCN --> PG
VSCN --> TG
PR --> PM
PM --> PG
```

**Diagram sources**
- [policy_engine.py (platform-gateway):323-376](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L323-L376)
- [policy_engine.py (tool-gateway):254-296](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L254-L296)
- [policy_matrix.py:31-87](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py#L31-L87)
- [policy.py (routes):30-54](file://products/platform-gateway/src/platform_gateway/api/routes/policy.py#L30-L54)
- [policy-scenarios.yaml:1-20](file://shared/shared-contracts/policies/policy-scenarios.yaml#L1-L20)
- [validate_policy_scenarios.py:37-47](file://shared/shared-contracts/scripts/validate_policy_scenarios.py#L37-L47)
- [Makefile:122-167](file://Makefile#L122-L167)

**Section sources**
- [Makefile:122-167](file://Makefile#L122-L167)
- [policy_matrix.py:31-87](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py#L31-L87)
- [policy.py (routes):30-54](file://products/platform-gateway/src/platform_gateway/api/routes/policy.py#L30-L54)

## Core Components
- Platform-gateway policy engine: loads bundle, computes SHA-256 of loaded text, exposes metadata including version, source, and sha256.
- Tool-gateway policy engine: same provenance capture; provides a helper to read the hash for health/readiness surfaces.
- Policy matrix builder: includes the provenance block in the matrix payload under the existing `policy:read` gate.
- Scenario harness: evaluates canonical scenarios against both engines using the real evaluation path; enforces coverage of every granted pair.
- Make targets: validate-policy, validate-policy-scenarios, policy-diff, and verify orchestration.

**Section sources**
- [policy_engine.py (platform-gateway):323-376](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L323-L376)
- [policy_engine.py (tool-gateway):254-296](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L254-L296)
- [policy_matrix.py:31-87](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py#L31-L87)
- [validate_policy_scenarios.py:95-155](file://shared/shared-contracts/scripts/validate_policy_scenarios.py#L95-L155)
- [Makefile:136-167](file://Makefile#L136-L167)

## Architecture Overview
The control flow spans bundle load, provenance computation, scenario validation, and matrix exposure.

```mermaid
sequenceDiagram
participant Dev as "Developer"
participant Make as "Makefile"
participant V as "validate_policy_scenarios.py"
participant PGE as "Platform Gateway Engine"
participant TGE as "Tool Gateway Engine"
participant API as "policy routes"
participant Matrix as "policy_matrix.py"
Dev->>Make : make verify / make policy-diff
Make->>V : --engine api|tools
V->>PGE : load_bundle(settings)
V->>TGE : load_bundle(settings)
V->>PGE : evaluate(role, action)
V->>TGE : evaluate(role, action)
Note over V,PGE : Scenario expectations validated<br/>Coverage invariant checked
Dev->>API : GET /api/v1/policy/matrix
API->>Matrix : build_policy_matrix()
Matrix->>PGE : bundle_metadata()
API-->>Dev : {version, source, sha256, ...}
```

**Diagram sources**
- [Makefile:136-167](file://Makefile#L136-L167)
- [validate_policy_scenarios.py:95-155](file://shared/shared-contracts/scripts/validate_policy_scenarios.py#L95-L155)
- [policy_engine.py (platform-gateway):323-376](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L323-L376)
- [policy_engine.py (tool-gateway):254-296](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L254-L296)
- [policy.py (routes):30-54](file://products/platform-gateway/src/platform_gateway/api/routes/policy.py#L30-L54)
- [policy_matrix.py:31-87](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py#L31-L87)

## Detailed Component Analysis

### Platform-Gateway Policy Engine Provenance
- Loads bundle from configured path or packaged default.
- Computes SHA-256 of exact loaded text at load time.
- Exposes `bundle_metadata()` returning version, source, and sha256.
- Matrix route uses this metadata to include sha256 in response.

```mermaid
flowchart TD
Start(["load_bundle(settings)"]) --> CheckCache{"Bundle cached<br/>for path?"}
CheckCache --> |Yes| ReturnRules["Return cached rules"]
CheckCache --> |No| ReadText["Read bundle text"]
ReadText --> Parse["_parse_rules(text)"]
Parse --> SetState["Set _bundle,<br/>_bundle_version,<br/>_configured_path,<br/>_bundle_hash"]
SetState --> Log["Log bundle loaded<br/>with sha256"]
Log --> ReturnRules
```

**Diagram sources**
- [policy_engine.py (platform-gateway):323-360](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L323-L360)

**Section sources**
- [policy_engine.py (platform-gateway):323-376](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L323-L376)
- [policy_matrix.py:31-87](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py#L31-L87)

### Tool-Gateway Policy Engine Provenance
- Same provenance capture strategy as platform-gateway.
- Provides `bundle_sha256()` for readiness/health surfaces.
- Skips require_approval rules at load per gateway constraints.

```mermaid
classDiagram
class ToolGatewayPolicyEngine {
+load_bundle(settings) list
+evaluate(settings, roles, action) PolicyDecision
+bundle_sha256() str
-_bundle_hash str
}
```

**Diagram sources**
- [policy_engine.py (tool-gateway):254-296](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L254-L296)

**Section sources**
- [policy_engine.py (tool-gateway):254-296](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L254-L296)

### Scenario Expectation Harness
- Reads `policy-scenarios.yaml`, expands role/action pairs, imports the owning engine, and evaluates each expectation.
- Enforces coverage: every granted pair must have an expectation.
- Fails non-zero on mismatch or missing coverage.

```mermaid
flowchart TD
S(["main()"]) --> LoadScenarios["Load scenarios YAML"]
LoadScenarios --> Expand["Expand role/action x expect"]
Expand --> LoadEngine["Import engine (--engine api|tools)"]
LoadEngine --> LoadBundle["load_bundle(bundle)"]
LoadBundle --> EvaluateLoop["For each (role, action)<br/>evaluate()"]
EvaluateLoop --> Compare{"Matches expect?"}
Compare --> |No| Fail["Collect failure"]
Compare --> |Yes| Next["Next pair"]
EvaluateLoop --> Coverage["Compute granted pairs"]
Coverage --> Uncovered{"Any uncovered grants?"}
Uncovered --> |Yes| Fail
Uncovered --> |No| Pass["OK: all passed"]
Fail --> Exit1["Exit 1"]
Pass --> Exit0["Exit 0"]
```

**Diagram sources**
- [validate_policy_scenarios.py:95-155](file://shared/shared-contracts/scripts/validate_policy_scenarios.py#L95-L155)
- [policy-scenarios.yaml:21-191](file://shared/shared-contracts/policies/policy-scenarios.yaml#L21-L191)

**Section sources**
- [validate_policy_scenarios.py:95-155](file://shared/shared-contracts/scripts/validate_policy_scenarios.py#L95-L155)
- [policy-scenarios.yaml:1-20](file://shared/shared-contracts/policies/policy-scenarios.yaml#L1-L20)

### Policy Matrix Exposure
- Builds caller-scoped matrix using the actual engine evaluation path.
- Includes provenance block (version, source, sha256) in response under existing `policy:read` gate.

```mermaid
sequenceDiagram
participant Client as "Client"
participant Route as "GET /api/v1/policy/matrix"
participant Matrix as "build_policy_matrix()"
participant Engine as "policy_engine.bundle_metadata()"
Client->>Route : request
Route->>Matrix : build_policy_matrix(settings, identity)
Matrix->>Engine : bundle_metadata()
Engine-->>Matrix : {version, source, sha256}
Matrix-->>Route : {matrix, approval_requirements, ...}
Route-->>Client : JSON payload
```

**Diagram sources**
- [policy.py (routes):30-54](file://products/platform-gateway/src/platform_gateway/api/routes/policy.py#L30-L54)
- [policy_matrix.py:31-87](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py#L31-L87)

**Section sources**
- [policy.py (routes):30-54](file://products/platform-gateway/src/platform_gateway/api/routes/policy.py#L30-L54)
- [policy_matrix.py:31-87](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py#L31-L87)

### Make Targets and Verification Gate
- `sync-policy`: copies canonical bundle to consumer locations.
- `validate-policy`: validates bundle schema.
- `validate-policy-scenarios`: runs scenario harness for both engines.
- `policy-diff`: compares candidate vs canonical (requires CANDIDATE).
- `verify`: aggregates tests, overlays, policy checks, scenarios, and version lockstep.

```mermaid
flowchart TD
V["make verify"] --> T["test"]
V --> O["overlays"]
V --> VP["validate-policy"]
V --> VPS["validate-policy-scenarios"]
V --> VV["validate-version"]
PD["make policy-diff"] --> |CANDIDATE required| Diff["Run diff for api/tools"]
```

**Diagram sources**
- [Makefile:122-167](file://Makefile#L122-L167)

**Section sources**
- [Makefile:122-167](file://Makefile#L122-L167)

## Dependency Analysis
- Shared scripts depend on product engines to ensure evaluation parity; they run inside product uv environments.
- Platform-gateway matrix depends on engine metadata and evaluation path.
- Tool-gateway readiness surfaces depend on engine-provided hash accessor.

```mermaid
graph LR
VSCN["validate_policy_scenarios.py"] --> PGE["platform-gateway policy_engine"]
VSCN --> TGE["tool-gateway policy_engine"]
PR["policy routes"] --> PM["policy_matrix.py"]
PM --> PGE
```

**Diagram sources**
- [validate_policy_scenarios.py:37-47](file://shared/shared-contracts/scripts/validate_policy_scenarios.py#L37-L47)
- [policy_matrix.py:31-87](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py#L31-L87)

**Section sources**
- [validate_policy_scenarios.py:37-47](file://shared/shared-contracts/scripts/validate_policy_scenarios.py#L37-L47)
- [policy_matrix.py:31-87](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py#L31-L87)

## Performance Considerations
- Bundle caching keyed by configured path avoids re-parsing on repeated calls.
- Hash computation occurs once per load; negligible overhead relative to I/O.
- Scenario harness evaluates only declared expectations plus coverage check; complexity proportional to number of scenarios and actions.
- Matrix building iterates visible roles × actions; scope filtering reduces work for non-admin identities.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and resolutions:
- Scenario failures: indicates a rule edit changed an operator-visible outcome or introduced an ungranted gap. Update expectations in the same commit to make intent explicit.
- Missing candidate for `policy-diff`: target requires `CANDIDATE=<path>`; provide a valid file path.
- Bundle load errors: malformed YAML or invalid rule structure will raise `PolicyLoadError`; fix bundle before proceeding.
- Provenance mismatch after deploy: confirm the deployed bundle’s SHA-256 matches the matrix/readiness output; ensure pod restart occurred after ConfigMap change.

**Section sources**
- [validate_policy_scenarios.py:102-122](file://shared/shared-contracts/scripts/validate_policy_scenarios.py#L102-L122)
- [Makefile:145-151](file://Makefile#L145-L151)
- [policy_engine.py (platform-gateway):323-360](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L323-L360)
- [policy_engine.py (tool-gateway):254-287](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L254-L287)

## Conclusion
SPEC-048 hardens policy governance through transparent provenance, scenario-driven guards, and review-time impact analysis while preserving existing evaluation semantics and rollout posture. Operators gain verifiable assurance that the enforced bundle matches the intended commit, and authors are guided to explicitly record intent changes alongside rule edits.

[No sources needed since this section summarizes without analyzing specific files]