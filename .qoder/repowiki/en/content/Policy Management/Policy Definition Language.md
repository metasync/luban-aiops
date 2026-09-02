# Policy Definition Language

<cite>
**Referenced Files in This Document**
- [policy-specification.md](file://docs/agentic-aiops-platform/policy-specification.md)
- [SPEC-004-policy-enforcement/spec.md](file://docs/specs/SPEC-004-policy-enforcement/spec.md)
- [SPEC-048-policy-testing-rollout-controls/spec.md](file://docs/specs/SPEC-048-policy-testing-rollout-controls/spec.md)
- [policy-default.yaml](file://products/tool-gateway/src/api_gateway/policies/policy-default.yaml)
- [policy-default.yaml](file://shared/shared-contracts/policies/policy-default.yaml)
- [policy-engine.py](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py)
- [policy-engine.py](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py)
- [test_policy_engine.py](file://products/platform-gateway/tests/test_policy_engine.py)
- [test_policy_engine.py](file://products/tool-gateway/tests/test_policy_engine.py)
- [test_policy_enforcement.py](file://products/platform-gateway/tests/test_policy_enforcement.py)
- [policy-rule.schema.json](file://shared/shared-contracts/schemas/policy-rule.schema.json)
- [policy-decision.schema.json](file://shared/shared-contracts/schemas/policy-decision.schema.json)
- [policy_matrix.py](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py)
- [gateway_service.py](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py)
</cite>

## Update Summary
**Changes Made**
- Updated policy bundle lifecycle section to reflect enhanced 5-step process with provenance tracking
- Added SHA-256 fingerprinting integration for deployment verification
- Documented no-hot-reload posture where ConfigMaps take effect only on pod restart
- Enhanced rollout controls and verification procedures
- Updated testing and validation sections to include scenario-expectation harness

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Enhanced Policy Bundle Lifecycle](#enhanced-policy-bundle-lifecycle)
6. [Detailed Component Analysis](#detailed-component-analysis)
7. [Dependency Analysis](#dependency-analysis)
8. [Performance Considerations](#performance-considerations)
9. [Troubleshooting Guide](#troubleshooting-guide)
10. [Conclusion](#conclusion)
11. [Appendices](#appendices)

## Introduction
This document describes the policy definition language used by the Luban AIOps platform to enforce access control, rate limiting, data validation, and resource constraints at runtime. Policies are authored as YAML documents that define rules with conditions and actions. The engine evaluates these policies against request context and returns a decision (allow/deny) along with metadata for observability.

The language supports:
- Rule structure with identifiers, scopes, and priorities
- Condition expressions using boolean operators, comparisons, pattern matching, and data extraction from request context
- Actions such as allow, deny, log, throttle, and transform
- Built-in variables representing identity, request attributes, and environment context
- Composition and inheritance patterns via modularization and references

**Updated** Enhanced with provenance tracking, SHA-256 fingerprinting, and improved rollout controls for better deployment verification and auditability.

## Project Structure
Policy-related artifacts are distributed across specification documents, schema definitions, default policy files, and the runtime engine implementation:

- Specification and design:
  - Platform-level policy specification
  - Enforcement spec detailing evaluation semantics and lifecycle
  - Testing and rollout controls specification
- Schema contracts:
  - Policy rule schema defining valid structures
  - Policy decision schema describing outcomes
- Default policies:
  - Example policy YAML for gateway and shared contracts
- Runtime engine:
  - Policy engine service implementing evaluation logic
  - Tests validating behavior and edge cases

```mermaid
graph TB
subgraph "Specs"
PS["Policy Specification"]
SE["Enforcement Spec"]
TRC["Testing & Rollout Controls"]
end
subgraph "Contracts"
PRS["Policy Rule Schema"]
PDS["Policy Decision Schema"]
end
subgraph "Policies"
PDG["Gateway Default Policy"]
PSC["Shared Contracts Default Policy"]
end
subgraph "Runtime"
PE["Policy Engine Service"]
TPE["Policy Engine Tests"]
TPF["Policy Enforcement Tests"]
PM["Policy Matrix Builder"]
GS["Gateway Service"]
end
PS --> PRS
SE --> PRS
TRC --> PRS
PRS --> PE
PDS --> PE
PDG --> PE
PSC --> PE
PE --> TPE
PE --> TPF
PM --> PE
GS --> PE
```

**Diagram sources**
- [policy-specification.md](file://docs/agentic-aiops-platform/policy-specification.md)
- [SPEC-004-policy-enforcement/spec.md](file://docs/specs/SPEC-004-policy-enforcement/spec.md)
- [SPEC-048-policy-testing-rollout-controls/spec.md](file://docs/specs/SPEC-048-policy-testing-rollout-controls/spec.md)
- [policy-rule.schema.json](file://shared/shared-contracts/schemas/policy-rule.schema.json)
- [policy-decision.schema.json](file://shared/shared-contracts/schemas/policy-decision.schema.json)
- [policy-default.yaml](file://products/tool-gateway/src/api_gateway/policies/policy-default.yaml)
- [policy-default.yaml](file://shared/shared-contracts/policies/policy-default.yaml)
- [policy-engine.py](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py)
- [policy-engine.py](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py)
- [test_policy_engine.py](file://products/platform-gateway/tests/test_policy_engine.py)
- [test_policy_engine.py](file://products/tool-gateway/tests/test_policy_engine.py)
- [test_policy_enforcement.py](file://products/platform-gateway/tests/test_policy_enforcement.py)
- [policy_matrix.py](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py)
- [gateway_service.py](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py)

**Section sources**
- [policy-specification.md](file://docs/agentic-aiops-platform/policy-specification.md)
- [SPEC-004-policy-enforcement/spec.md](file://docs/specs/SPEC-004-policy-enforcement/spec.md)
- [SPEC-048-policy-testing-rollout-controls/spec.md](file://docs/specs/SPEC-048-policy-testing-rollout-controls/spec.md)
- [policy-rule.schema.json](file://shared/shared-contracts/schemas/policy-rule.schema.json)
- [policy-decision.schema.json](file://shared/shared-contracts/schemas/policy-decision.schema.json)
- [policy-default.yaml](file://products/tool-gateway/src/api_gateway/policies/policy-default.yaml)
- [policy-default.yaml](file://shared/shared-contracts/policies/policy-default.yaml)
- [policy-engine.py](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py)
- [policy-engine.py](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py)
- [test_policy_engine.py](file://products/platform-gateway/tests/test_policy_engine.py)
- [test_policy_engine.py](file://products/tool-gateway/tests/test_policy_engine.py)
- [test_policy_enforcement.py](file://products/platform-gateway/tests/test_policy_enforcement.py)
- [policy_matrix.py](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py)
- [gateway_service.py](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py)

## Core Components
- Policy Rule Schema: Defines the canonical structure for policy rules including identifiers, versioning, scope, priority, conditions, and actions.
- Policy Decision Schema: Describes the outcome of policy evaluation, including decision, reason, and metadata.
- Default Policies: YAML examples demonstrating common patterns like rate limiting, access control, and validation.
- Policy Engine: Evaluates policies against request context, resolves variables, executes condition expressions, and produces decisions.
- **Enhanced**: Provenance tracking with SHA-256 fingerprinting for deployment verification and audit trails.

Key responsibilities:
- Parsing and validating policy YAML against schemas
- Resolving built-in variables and extracting values from request context
- Evaluating boolean expressions and pattern matching
- Applying actions and aggregating results
- Returning structured decisions with traceable reasons
- **Enhanced**: Computing and exposing content fingerprints for deployment verification

**Section sources**
- [policy-rule.schema.json](file://shared/shared-contracts/schemas/policy-rule.schema.json)
- [policy-decision.schema.json](file://shared/shared-contracts/schemas/policy-decision.schema.json)
- [policy-default.yaml](file://products/tool-gateway/src/api_gateway/policies/policy-default.yaml)
- [policy-default.yaml](file://shared/shared-contracts/policies/policy-default.yaml)
- [policy-engine.py](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py)
- [policy-engine.py](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py)

## Architecture Overview
The policy enforcement flow integrates into the API gateway's request lifecycle. Requests carry identity and contextual attributes; the policy engine evaluates configured policies and returns a decision that gates further processing.

```mermaid
sequenceDiagram
participant Client as "Client"
participant Gateway as "API Gateway"
participant Engine as "Policy Engine"
participant Rules as "Policy Rules (YAML)"
participant Context as "Request Context"
participant Provenance as "Provenance Tracker"
Client->>Gateway : "HTTP Request"
Gateway->>Context : "Build context (identity, headers, body)"
Gateway->>Engine : "Evaluate policies(context)"
Engine->>Rules : "Load and parse policies"
Engine->>Context : "Resolve built-in variables"
Engine->>Provenance : "Compute SHA-256 fingerprint"
Engine->>Engine : "Evaluate conditions and actions"
Engine-->>Gateway : "Decision {allow|deny}, reason, metadata"
Gateway-->>Client : "Response based on decision"
```

**Diagram sources**
- [policy-engine.py](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py)
- [policy-engine.py](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py)
- [policy-default.yaml](file://products/tool-gateway/src/api_gateway/policies/policy-default.yaml)
- [policy-rule.schema.json](file://shared/shared-contracts/schemas/policy-rule.schema.json)
- [policy-decision.schema.json](file://shared/shared-contracts/schemas/policy-decision.schema.json)

## Enhanced Policy Bundle Lifecycle

**New Section** The policy bundle lifecycle has been enhanced with a comprehensive 5-step process that includes provenance tracking, deployment verification, and improved rollback capabilities.

### Five-Step Lifecycle Process

1. **Bundle Authoring**: Policies are authored as YAML documents with semantic versioning and descriptive comments
2. **Validation & Testing**: Bundles undergo schema validation and scenario-expectation testing before deployment
3. **Deployment**: ConfigMaps are updated via `make sync-policy` and deployed to target environments
4. **Verification**: SHA-256 fingerprints are exposed on readiness and matrix surfaces for live verification
5. **Rollback**: Reverting bundles restores previous operator-self-confirm behavior instantly

### Provenance Tracking

Both policy engines now compute and expose SHA-256 content hashes of the exact loaded bundle text:

- **Platform Gateway**: `bundle_metadata()` function returns version, source, and sha256 fields
- **Tool Gateway**: `bundle_sha256()` function provides content fingerprint after bundle load
- **Readiness Surfaces**: Both gateways expose `policy_bundle_sha256` on health/readiness endpoints
- **Matrix Surface**: Policy matrix endpoint carries provenance block under existing `policy:read` gate

### No-Hot-Reload Posture

ConfigMaps take effect only on pod restart, maintaining fail-fast semantics:

- Bundles are cached keyed on configured path for performance
- Changed ConfigMaps are never re-read during runtime
- PolicyLoadError ensures immediate failure on invalid bundles
- Hot reload is deliberately absent to maintain consistency guarantees

### Deployment Verification

Operators can verify enforced bundles through multiple surfaces:

```mermaid
flowchart TD
Start(["Deploy Policy Bundle"]) --> Sync["Run make sync-policy"]
Sync --> Verify["Run make verify"]
Verify --> Test["Scenario Tests Pass?"]
Test --> |No| Fail["Fail Build"]
Test --> |Yes| Deploy["Deploy to Environment"]
Deploy --> Check["Check Readiness Endpoint"]
Check --> VerifyHash["Verify SHA-256 Hash"]
VerifyHash --> |Match| Success["Deployment Verified"]
VerifyHash --> |Mismatch| Alert["Alert Mismatch"]
```

**Diagram sources**
- [SPEC-048-policy-testing-rollout-controls/spec.md](file://docs/specs/SPEC-048-policy-testing-rollout-controls/spec.md)
- [gateway_service.py](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py)
- [policy_matrix.py](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py)

**Section sources**
- [SPEC-048-policy-testing-rollout-controls/spec.md](file://docs/specs/SPEC-048-policy-testing-rollout-controls/spec.md)
- [policy-engine.py](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py)
- [policy-engine.py](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py)
- [gateway_service.py](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py)
- [policy_matrix.py](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py)

## Detailed Component Analysis

### Policy Rule Schema
The policy rule schema defines the structure for each rule, including:
- Identifier and version fields for tracking and evolution
- Scope specifying applicable targets (e.g., endpoints, methods, tenants)
- Priority determining evaluation order among multiple rules
- Conditions expressing boolean logic over context variables
- Actions specifying outcomes (allow, deny, log, throttle, transform)

Complexity considerations:
- Rule parsing is O(n) over rule count per evaluation
- Condition evaluation uses short-circuit boolean operations
- Pattern matching leverages compiled regex where supported

Best practices:
- Use stable identifiers and semantic versioning
- Keep scopes narrow to minimize evaluation overhead
- Prefer explicit priorities to avoid ambiguity

**Section sources**
- [policy-rule.schema.json](file://shared/shared-contracts/schemas/policy-rule.schema.json)

### Policy Decision Schema
The decision schema captures:
- Decision value (allow/deny)
- Reason string explaining the outcome
- Metadata including matched rule IDs, timestamps, and counters

Usage:
- Downstream components use the decision to proceed or reject requests
- Observability systems consume metadata for metrics and tracing

**Section sources**
- [policy-decision.schema.json](file://shared/shared-contracts/schemas/policy-decision.schema.json)

### Default Policies
Default policy YAML files demonstrate practical patterns:
- Rate limiting rules based on client identity and endpoint frequency
- Access control rules enforcing role-based permissions
- Data validation rules ensuring payload shape and constraints
- Resource constraint rules bounding compute or storage usage

Modularization techniques:
- Splitting policies by domain (auth, rate-limit, validate)
- Referencing shared fragments via includes or anchors
- Versioned policy bundles for environments

**Section sources**
- [policy-default.yaml](file://products/tool-gateway/src/api_gateway/policies/policy-default.yaml)
- [policy-default.yaml](file://shared/shared-contracts/policies/policy-default.yaml)

### Policy Engine
The policy engine implements evaluation semantics:
- Loads and validates policies against schemas
- Builds a context object with built-in variables (identity, request attributes, environment)
- Iterates rules by priority and evaluates conditions
- Applies actions and aggregates results
- Produces a structured decision with reasons and metadata
- **Enhanced**: Computes SHA-256 fingerprints of loaded bundles for provenance tracking

Evaluation algorithm overview:

```mermaid
flowchart TD
Start(["Start Evaluation"]) --> Load["Load and Parse Policies"]
Load --> Validate{"Valid?"}
Validate --> |No| Error["Return Validation Error"]
Validate --> |Yes| BuildCtx["Build Request Context"]
BuildCtx --> ComputeHash["Compute SHA-256 Fingerprint"]
ComputeHash --> SortRules["Sort Rules by Priority"]
SortRules --> Iterate["Iterate Rules"]
Iterate --> EvalCond["Evaluate Conditions"]
EvalCond --> CondResult{"Condition True?"}
CondResult --> |No| NextRule["Next Rule"]
CondResult --> |Yes| ApplyAct["Apply Actions"]
ApplyAct --> Decide["Compute Decision"]
Decide --> Return["Return Decision + Metadata"]
NextRule --> Iterate
Error --> End(["End"])
Return --> End
```

**Diagram sources**
- [policy-engine.py](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py)
- [policy-engine.py](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py)

**Section sources**
- [policy-engine.py](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py)
- [policy-engine.py](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py)

### Testing and Validation
Tests cover:
- Policy engine evaluation paths (allow/deny scenarios)
- Edge cases (missing context fields, malformed policies)
- Integration points with gateway request lifecycle
- **Enhanced**: Scenario-expectation harness for preventing unintended grant changes
- **Enhanced**: SHA-256 hash stability and sensitivity tests
- **Enhanced**: Readiness surface verification with provenance tracking

Recommendations:
- Maintain test coverage for new operators and functions
- Add negative tests for invalid inputs and unexpected contexts
- Simulate high-throughput scenarios to validate performance
- Use scenario tables to guard against unintended policy changes

**Section sources**
- [test_policy_engine.py](file://products/platform-gateway/tests/test_policy_engine.py)
- [test_policy_engine.py](file://products/tool-gateway/tests/test_policy_engine.py)
- [test_policy_enforcement.py](file://products/platform-gateway/tests/test_policy_enforcement.py)

## Dependency Analysis
Policy components depend on schemas for validation and on YAML files for configuration. The engine orchestrates evaluation and interacts with request context.

```mermaid
graph LR
PRS["Policy Rule Schema"] --> PE["Policy Engine"]
PDS["Policy Decision Schema"] --> PE
PDG["Gateway Default Policy"] --> PE
PSC["Shared Contracts Default Policy"] --> PE
PE --> TPE["Policy Engine Tests"]
PE --> TPF["Policy Enforcement Tests"]
PM["Policy Matrix Builder"] --> PE
GS["Gateway Service"] --> PE
PROVENANCE["Provenance Tracking"] --> PE
```

**Diagram sources**
- [policy-rule.schema.json](file://shared/shared-contracts/schemas/policy-rule.schema.json)
- [policy-decision.schema.json](file://shared/shared-contracts/schemas/policy-decision.schema.json)
- [policy-default.yaml](file://products/tool-gateway/src/api_gateway/policies/policy-default.yaml)
- [policy-default.yaml](file://shared/shared-contracts/policies/policy-default.yaml)
- [policy-engine.py](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py)
- [policy-engine.py](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py)
- [test_policy_engine.py](file://products/platform-gateway/tests/test_policy_engine.py)
- [test_policy_engine.py](file://products/tool-gateway/tests/test_policy_engine.py)
- [test_policy_enforcement.py](file://products/platform-gateway/tests/test_policy_enforcement.py)
- [policy_matrix.py](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py)
- [gateway_service.py](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py)

**Section sources**
- [policy-rule.schema.json](file://shared/shared-contracts/schemas/policy-rule.schema.json)
- [policy-decision.schema.json](file://shared/shared-contracts/schemas/policy-decision.schema.json)
- [policy-default.yaml](file://products/tool-gateway/src/api_gateway/policies/policy-default.yaml)
- [policy-default.yaml](file://shared/shared-contracts/policies/policy-default.yaml)
- [policy-engine.py](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py)
- [policy-engine.py](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py)
- [test_policy_engine.py](file://products/platform-gateway/tests/test_policy_engine.py)
- [test_policy_engine.py](file://products/tool-gateway/tests/test_policy_engine.py)
- [test_policy_enforcement.py](file://products/platform-gateway/tests/test_policy_enforcement.py)
- [policy_matrix.py](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py)
- [gateway_service.py](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py)

## Performance Considerations
- Minimize rule count and complexity to reduce evaluation time
- Use precise scopes to limit context resolution overhead
- Cache compiled patterns for repeated pattern matching
- Avoid heavy computations inside conditions; precompute when possible
- Monitor decision latency and adjust priorities accordingly
- **Enhanced**: SHA-256 computation occurs once at bundle load time, not per-request

## Troubleshooting Guide
Common issues and resolutions:
- Invalid policy YAML: Validate against schema and fix structural errors
- Missing context variables: Ensure request context includes required fields
- Unexpected denials: Inspect decision reason and matched rule IDs
- Performance regressions: Profile evaluation paths and optimize rules
- **Enhanced**: Deployment mismatches: Compare expected vs actual SHA-256 hashes on readiness surfaces
- **Enhanced**: Bundle loading failures: Check ConfigMap mounting and file permissions

Diagnostic steps:
- Enable detailed logging for policy evaluations
- Export decision metadata for analysis
- Reproduce failures with minimal policy sets
- **Enhanced**: Use `make policy-diff` to review impact of bundle changes
- **Enhanced**: Verify bundle provenance on both matrix and readiness endpoints

**Section sources**
- [policy-engine.py](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py)
- [policy-engine.py](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py)
- [test_policy_engine.py](file://products/platform-gateway/tests/test_policy_engine.py)
- [test_policy_engine.py](file://products/tool-gateway/tests/test_policy_engine.py)
- [test_policy_enforcement.py](file://products/platform-gateway/tests/test_policy_enforcement.py)

## Conclusion
The policy definition language enables flexible, maintainable governance of requests through declarative YAML policies. By adhering to schema-defined structures, leveraging built-in variables and operators, and following best practices for composition and versioning, teams can implement robust access control, rate limiting, validation, and resource constraints. The enhanced policy engine ensures consistent evaluation, actionable decisions with rich metadata for observability and debugging, and comprehensive provenance tracking for deployment verification and audit trails.

**Updated** The addition of SHA-256 fingerprinting, scenario-expectation testing, and improved rollout controls provides operators with confidence in policy deployments while maintaining the fail-fast, no-hot-reload posture that ensures consistency.

## Appendices

### YAML Syntax Reference
- Rule fields: identifier, version, scope, priority, conditions, actions
- Condition expressions: boolean operators (and, or, not), comparisons (equals, greater-than, less-than), pattern matching (regex), data extraction (context keys)
- Actions: allow, deny, log, throttle, transform
- Built-in variables: identity attributes, request headers, method, path, tenant, timestamp

### Common Policy Patterns
- Rate limiting: Limit requests per client per minute
- Access control: Enforce role-based permissions on endpoints
- Data validation: Validate payload shape and constraints
- Resource constraints: Bound compute or storage usage per tenant

### Inheritance and Composition
- Modularize policies by domain and reference shared fragments
- Use versioned bundles for environment-specific overrides
- Compose complex rules from simpler primitives

### Versioning and Naming Conventions
- Semantic versioning for policy bundles
- Stable identifiers for rules and scopes
- Prefix naming for domains (e.g., auth.*, rate.*)

### Enhanced Rollout Procedures
- Edit bundle → Run `make sync-policy` → Execute `make verify` → Review with `make policy-diff` → Commit → Deploy → Verify SHA-256 hash on readiness/matrix surfaces
- No hot reload: Changes take effect only on pod restart
- Rollback: Revert bundle and restart pods to restore previous state

[No sources needed since this section provides general guidance]