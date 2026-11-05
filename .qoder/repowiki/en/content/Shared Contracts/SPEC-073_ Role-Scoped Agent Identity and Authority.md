# SPEC-073: Role-Scoped Agent Identity and Authority

<cite>
**Referenced Files in This Document**
- [spec.md](file://docs/specs/SPEC-073-role-scoped-agent-identity/spec.md)
- [plan.md](file://docs/specs/SPEC-073-role-scoped-agent-identity/plan.md)
- [tasks.md](file://docs/specs/SPEC-073-role-scoped-agent-identity/tasks.md)
- [agent_role.py](file://products/agent-platform/src/agent_service/services/agent_role.py)
- [test_agent_role.py](file://products/agent-platform/tests/test_agent_role.py)
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [delegated_identity.py](file://products/agent-platform/src/agent_service/services/delegated_identity.py)
- [policy_engine.py](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py)
- [policy_engine.py](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py)
- [policy-rule.schema.json](file://shared/shared-contracts/schemas/policy-rule.schema.json)
- [authorization-matrix.md](file://docs/agentic-aiops-platform/authorization-matrix.md)
- [identity-and-authorization-design.md](file://docs/agentic-aiops-platform/identity-and-authorization-design.md)
- [policy-scenarios.yaml](file://shared/shared-contracts/policies/policy-scenarios.yaml)
</cite>

## Update Summary
**Changes Made**
- Updated SPEC-073 status from delivered to **delivered with phase 3 completion** - the multi-agent orchestration series is now complete through the policy role axis
- Added comprehensive documentation of SPEC-074 Policy Role Axis implementation that completes the phased program
- Updated architecture diagrams to reflect the complete two-layer narrowing model (toolkit + policy)
- Enhanced component analysis to include the policy engine implementations across both gateways
- Added detailed coverage of the v3 policy schema extension and scenario testing framework
- Updated troubleshooting guide with policy-axis specific checks for the completed substrate

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Dependency Analysis](#dependency-analysis)
7. [Performance Considerations](#performance-considerations)
8. [Implementation Roadmap](#implementation-roadmap)
9. [Troubleshooting Guide](#troubleshooting-guide)
10. [Conclusion](#conclusion)

## Introduction
SPEC-073 defines the role-scoped agent identity and authority substrate required by ADR-0017's phased multi-agent program. **Status: Delivered** (2026-11-04 as v0.54.0, with phase 3 policy role axis completed as v0.55.0). Its phase-2 goal was narrow and defensive: introduce a closed, platform-owned `agent-role` vocabulary (`diagnostician`, `orchestrator`, `executor`) that narrows an agent's toolkit on the existing gateway-forwarded delegated token, without creating a new principal, broker identity, or wire claim. The spec preserves end-to-end human identity ("on whose behalf"), keeps every mutation on the existing HITL-gated signed dispatch path, and ships inert by default so the deployed single-agent turn remains byte-identical.

The specification is now **fully delivered** with all six Open Questions resolved and all six requirements implemented. **Phase 3 completion** adds the policy role axis (SPEC-074), completing the two-layer narrowing model envisioned by ADR-0017 Decision 4: toolkit narrowing (phase 2) plus policy evaluation (phase 3). The policy axis extends the deny-by-default authorization model with an optional `agent_roles_any` dimension in the policy rule schema, implementing conjunctive composition with human roles while maintaining fail-closed semantics.

**Section sources**
- [spec.md:3-30](file://docs/specs/SPEC-073-role-scoped-agent-identity/spec.md#L3-L30)
- [spec.md:65-77](file://docs/specs/SPEC-073-role-scoped-agent-identity/spec.md#L65-L77)
- [spec.md:322-342](file://docs/specs/SPEC-073-role-scoped-agent-identity/spec.md#L322-L342)

## Project Structure
SPEC-073 is now fully implemented as a design and requirements document backed by concrete runtime surfaces in the agent-platform product, with phase 3 extending into the gateway policy layer:

| Area | Repository location | Implementation Status |
|---|---|---|
| Specification | `docs/specs/SPEC-073-role-scoped-agent-identity/spec.md` | Defines roles, requirements, non-goals, impact boundaries, and open questions. |
| Implementation Plan | `docs/specs/SPEC-073-role-scoped-agent-identity/plan.md` | Binding four-stage rollout plan with detailed technical approach. |
| Task Tracking | `docs/specs/SPEC-073-role-scoped-agent-identity/tasks.md` | Granular task checklist tied to requirement IDs - all tasks completed. |
| Role Substrate | `products/agent-platform/src/agent_service/services/agent_role.py` | Closed AgentRole enum, AGENT_ROLE ContextVar, and role scope management. |
| Toolkit narrowing seam | `products/agent-platform/src/agent_service/runtime_kernel.py` | Implements per-token toolkit caching, read-only filtering, and role-aware narrowing. |
| Human identity context | `products/agent-platform/src/agent_service/services/delegated_identity.py` | Provides `VerifiedHuman` and the `REQUESTER_IDENTITY` / `DECIDER_IDENTITY` contextvars referenced by R-3. |
| Policy Engine (Platform) | `products/platform-gateway/src/platform_gateway/services/policy_engine.py` | Implements agent-role axis with `agent_roles_any` matching and conjunctive composition. |
| Policy Engine (Tool) | `products/tool-gateway/src/tool_gateway/services/policy_engine.py` | Mirrors platform-gateway semantics with tool-specific behavior. |
| Policy Schema | `shared/shared-contracts/schemas/policy-rule.schema.json` | v3 schema with additive `agent_roles_any` field in match block. |
| Test Coverage | `products/agent-platform/tests/test_agent_role.py` | Comprehensive 29-test suite covering all requirements and acceptance criteria. |
| Scenario Testing | `shared/shared-contracts/policies/policy-scenarios.yaml` | Agent-role demonstration scenarios validating axis semantics. |

```mermaid
graph TB
Spec["SPEC-073<br/>Role-scoped agent identity & authority"] --> Kernel["Agent Platform Runtime Kernel<br/>Toolkit construction & caching"]
Spec --> Identity["Delegated Identity Service<br/>VerifiedHuman & contextvars"]
Spec --> RoleModule["Agent Role Module<br/>Closed enum & context management"]
Spec --> PolicyAxis["SPEC-074 Policy Role Axis<br/>Gateway policy engines"]
Plan["Implementation Plan<br/>Four-stage rollout"] --> Tasks["Task Checklist<br/>Requirement-tracked tasks"]
Kernel --> Gateway["Tool Gateway (external)<br/>Discovered tools"]
Kernel --> Toolkit["Agentscope Toolkit<br/>Read/write tier filter"]
Identity --> ContextVars["Process-local contextvars<br/>REQUESTER_IDENTITY / DECIDER_IDENTITY"]
RoleModule --> RoleContext["AGENT_ROLE ContextVar<br/>Process-local role binding"]
PolicyAxis --> PlatformGW["Platform Gateway Policy Engine<br/>agent_roles_any matching"]
PolicyAxis --> ToolGW["Tool Gateway Policy Engine<br/>agent_roles_any matching"]
PolicyAxis --> Schema["Policy Rule Schema v3<br/>agent_roles_any field"]
TestSuite["Test Suite<br/>29+ comprehensive tests"] --> AllComponents["All delivered components"]
```

**Diagram sources**
- [spec.md:45-57](file://docs/specs/SPEC-073-role-scoped-agent-identity/spec.md#L45-L57)
- [plan.md:8-18](file://docs/specs/SPEC-073-role-scoped-agent-identity/plan.md#L8-L18)
- [agent_role.py:30-120](file://products/agent-platform/src/agent_service/services/agent_role.py#L30-L120)
- [runtime_kernel.py:501-660](file://products/agent-platform/src/agent_service/runtime_kernel.py#L501-L660)
- [policy_engine.py:428-499](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L428-L499)
- [policy-engine.py:348-419](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L348-L419)

**Section sources**
- [spec.md:232-249](file://docs/specs/SPEC-073-role-scoped-agent-identity/spec.md#L232-L249)
- [plan.md:8-18](file://docs/specs/SPEC-073-role-scoped-agent-identity/plan.md#L8-L18)
- [agent_role.py:1-120](file://products/agent-platform/src/agent_service/services/agent_role.py#L1-L120)
- [runtime_kernel.py:501-660](file://products/agent-platform/src/agent_service/runtime_kernel.py#L501-L660)
- [delegated_identity.py:28-55](file://products/agent-platform/src/agent_service/services/delegated_identity.py#L28-L55)

## Core Components
SPEC-073 centers on six requirements that together form the phase-2 substrate, all now fully implemented and tested, with phase 3 completing the policy role axis:

| Requirement | Purpose | Current Status |
|---|---|---|
| R-1 | Closed, immutable, platform-owned `agent-role` vocabulary with no agentscope type leakage. | **Delivered**: Three-value enum `diagnostician`, `orchestrator`, `executor` in `agent_role.py`. |
| R-2 | Generalize `_ensure_toolkit(bearer_token, read_only)` into per-role toolkit narrowing keyed by `(token, role)`. | **Delivered**: `_narrow_for_role` method with role-aware cache keys. |
| R-3 | Preserve the same delegated token and human requester identity across role-scoped delegation. | **Delivered**: Process-local `AGENT_ROLE` ContextVar beside `DELEGATED_TOKEN`. |
| R-4 | Label executor-staged mutations with staging role provenance while keeping the existing HITL + signed dispatch path unchanged. | **Delivered**: Kernel-internal provenance labeling via `staged_by_role` field. |
| R-5 | Fail-closed posture, four-point-gate parity, and inertness proof with no orchestration caller. | **Delivered**: Guard tests and full suite verification (1710 passed). |
| R-6 | Update identity/design documentation and spec index without changing shared contracts. | **Delivered**: Documentation reconciliation completed. |

Key acceptance constraints are all satisfied:
- No per-role broker mint or second identity edge.
- Toolkit narrowing is subtractive only.
- Unknown or absent role fails closed to the most restrictive posture.
- No additive field on `execution-request.schema.json` in phase 2.
- No v2 stream/schema change in phase 2.
- Full agent-platform suite passes with 1710 tests green.

**Phase 3 Completion**: The policy role axis (SPEC-074) extends this foundation with gateway-level authorization control, adding an optional `agent_roles_any` dimension to the policy rule schema (v2→v3) and implementing conjunctive composition with human roles in both gateway policy engines.

**Section sources**
- [spec.md:98-215](file://docs/specs/SPEC-073-role-scoped-agent-identity/spec.md#L98-L215)
- [spec.md:257-305](file://docs/specs/SPEC-073-role-scoped-agent-identity/spec.md#L257-L305)
- [tasks.md:7-85](file://docs/specs/SPEC-073-role-scoped-agent-identity/tasks.md#L7-L85)

## Architecture Overview
At a high level, SPEC-073 extends the existing agent-platform execution model rather than introducing a new control plane, with phase 3 completing the two-layer narrowing architecture:

```mermaid
sequenceDiagram
participant Caller as "Orchestration caller (phase 5+)"
participant Kernel as "RuntimeKernel"
participant RoleModule as "AgentRole Module"
participant Toolkit as "Agentscope Toolkit"
participant PolicyEngine as "Gateway Policy Engine"
participant Gateway as "Tool Gateway"
participant Worker as "Signed execution worker"
participant Store as "Confirmation / parked record store"
Caller->>RoleModule : "Bind role via agent_role_scope()"
RoleModule->>RoleModule : "Set AGENT_ROLE ContextVar"
Caller->>Kernel : "Invoke with bearer_token + bound role"
Kernel->>Kernel : "Resolve role-scoped cache key (token, role)"
Kernel->>Gateway : "Discover tools for bearer_token"
Gateway-->>Kernel : "Tool definitions"
Kernel->>Toolkit : "Build toolkit filtered by role"
Toolkit-->>Kernel : "Narrowed toolkit"
Note over PolicyEngine : "Phase 3 : Policy evaluation with agent_roles_any"
PolicyEngine->>PolicyEngine : "Evaluate roles × actions × agent_roles_any"
PolicyEngine-->>Caller : "Deny/Allow/RequireApproval decision"
alt "Role is executor and action mutates"
Kernel->>Store : "Stage mutation via existing HITL path"
Store->>Store : "Record staged_by_role provenance"
Store-->>Worker : "Approved mutation dispatched once"
Worker-->>Caller : "Result"
else "Diagnostic or planner role"
Kernel-->>Caller : "Read-only or delegate-only result"
end
```

**Diagram sources**
- [spec.md:111-172](file://docs/specs/SPEC-073-role-scoped-agent-identity/spec.md#L111-L172)
- [agent_role.py:103-120](file://products/agent-platform/src/agent_service/services/agent_role.py#L103-L120)
- [runtime_kernel.py:501-660](file://products/agent-platform/src/agent_service/runtime_kernel.py#L501-L660)
- [policy_engine.py:428-499](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L428-L499)

The diagram maps the intended flow from requirement R-2 (role-scoped toolkit narrowing) through R-4 (executor staging), while preserving the existing HITL and signed-dispatch boundary described in the spec. Phase 3 adds the policy evaluation layer that composes agent-role constraints with human role grants.

## Detailed Component Analysis

### Agent Role Module (R-1)
The `agent_role.py` module implements the closed, platform-owned role vocabulary with fail-closed semantics:

```mermaid
classDiagram
class AgentRole {
<<enumeration>>
DIAGNOSTICIAN = "diagnostician"
ORCHESTRATOR = "orchestrator"
EXECUTOR = "executor"
}
class AgentRoleError {
+__init__()
+message : "agent_role_invalid"
}
class ContextManagement {
+ContextVar AGENT_ROLE
+coerce_agent_role(value) AgentRole
+current_agent_role() AgentRole|None
+current_agent_role_value() str|None
+agent_role_scope(value) Iterator[AgentRole]
}
AgentRole <.. ContextManagement : "validated by"
AgentRoleError <.. ContextManagement : "raised on invalid input"
```

**Diagram sources**
- [agent_role.py:30-120](file://products/agent-platform/src/agent_service/services/agent_role.py#L30-L120)

#### Key Implementation Details
- **Closed Enum**: `AgentRole` inherits from both `str` and `Enum`, providing plain string values while maintaining type safety
- **Fail-Closed Validation**: `coerce_agent_role()` rejects unknown values with `AgentRoleError` instead of coercing them
- **Process-Local Context**: `AGENT_ROLE` is a `ContextVar` with `default=None`, ensuring unscoped turns remain byte-identical
- **Scope Management**: `agent_role_scope()` provides a context manager that sets and restores the role context automatically
- **No Agentscope Imports**: The module contains no agentscope imports, satisfying gate point 4

**Section sources**
- [agent_role.py:30-120](file://products/agent-platform/src/agent_service/services/agent_role.py#L30-L120)

### Per-Role Toolkit Narrowing (R-2)
The `_narrow_for_role` method in `runtime_kernel.py` implements role-based toolkit filtering:

```mermaid
flowchart TD
Start(["_narrow_for_role(definitions, role)"]) --> CheckRole{"Check role type"}
CheckRole --> |DIAGNOSTICIAN| FilterRO["_filter_read_only()"]
CheckRole --> |EXECUTOR| ReturnFull["Return full definitions"]
CheckRole --> |ORCHESTRATOR| ReturnEmpty["Return empty list"]
CheckRole --> |Unknown| LogWarn["Log warning + return empty"]
FilterRO --> Result["Filtered toolkit"]
ReturnFull --> Result
ReturnEmpty --> Result
LogWarn --> Result
```

**Diagram sources**
- [runtime_kernel.py:629-660](file://products/agent-platform/src/agent_service/runtime_kernel.py#L629-L660)

#### Cache Key Strategy
The cache key extension follows a precise pattern:
- Base key: `(bearer_token or "") + ("::read-only" if read_only else "")`
- Role extension: Only appended when `role is not None`
- Result: Unscoped turns keep exact current behavior; role-scoped turns get separate cache entries

**Section sources**
- [runtime_kernel.py:501-580](file://products/agent-platform/src/agent_service/runtime_kernel.py#L501-L580)
- [runtime_kernel.py:629-660](file://products/agent-platform/src/agent_service/runtime_kernel.py#L629-L660)

### Policy Role Axis (SPEC-074, Phase 3)
Phase 3 completes the two-layer narrowing model by implementing the agent-role dimension in the gateway policy engines:

```mermaid
flowchart TD
Rule["Policy Rule with agent_roles_any"] --> MatchRoles{"Match human roles_any"}
MatchRoles --> |No match| Deny["Deny"]
MatchRoles --> |Match| MatchActions{"Match actions_any"}
MatchActions --> |No match| Deny
MatchActions --> |Match| MatchAgentRoles{"Match agent_roles_any"}
MatchAgentRoles --> |Absent| Allow["Allow/Deny/RequireApproval"]
MatchAgentRoles --> |Present & matches| Allow
MatchAgentRoles --> |Present & no match| Deny
```

**Diagram sources**
- [policy_engine.py:428-499](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L428-L499)
- [policy-engine.py:348-419](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L348-L419)

#### Key Implementation Details
- **Additive Schema Extension**: `policy-rule.schema.json` v3 adds optional `agent_roles_any` array in match block
- **Conjunctive Composition**: Rules match only if human roles AND agent roles both satisfy their respective constraints
- **Fail-Closed Semantics**: Rules with `agent_roles_any` never match unscoped calls (`agent_role=None`)
- **Dual Engine Implementation**: Both platform-gateway and tool-gateway implement identical semantics
- **Inert Deployment**: Canonical policy bundle remains byte-unchanged; no deployed caller threads agent-role yet

**Section sources**
- [policy_engine.py:428-499](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L428-L499)
- [policy-engine.py:348-419](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L348-L419)
- [policy-rule.schema.json:44-48](file://shared/shared-contracts/schemas/policy-rule.schema.json#L44-L48)

### Human Identity Context Preservation (R-3)
The role context operates alongside existing identity contextvars without interference:

| Symbol | Meaning | Relevance to SPEC-073 |
|---|---|---|
| `VerifiedHuman` | Frozen dataclass representing a verified human identity with namespace, subject, user_id, actor, and expiry. | Used to assert "on whose behalf" identity preservation across delegation hops. |
| `REQUESTER_IDENTITY` | Process-local contextvar holding the verified requester. | Must remain unchanged when an orchestrator delegates to a member. |
| `DECIDER_IDENTITY` | Process-local contextvar holding the verified decider/approver. | Must remain distinct from the requester for self-approval checks. |
| `AGENT_ROLE` | New process-local contextvar for role binding. | Mirrors the pattern of other contextvars while remaining independent. |

```mermaid
classDiagram
class VerifiedHuman {
+string namespace
+string subject
+string user_id
+string actor
+int expires_at
+require_live()
+matches(namespace, subject) bool
}
class DelegatedIdentityVerifier {
+string issuer
+string audience
+frozenset actors
+verify(token, user_id) VerifiedHuman
}
class ContextVars {
+ContextVar REQUESTER_IDENTITY
+ContextVar DECIDER_IDENTITY
+ContextVar DELEGATED_TOKEN
+ContextVar AGENT_ROLE (new)
}
VerifiedHuman <.. DelegatedIdentityVerifier : "constructed by"
ContextVars --> VerifiedHuman : "holds process-local identity"
```

**Diagram sources**
- [delegated_identity.py:28-55](file://products/agent-platform/src/agent_service/services/delegated_identity.py#L28-L55)
- [delegated_identity.py:58-98](file://products/agent-platform/src/agent_service/services/delegated_identity.py#L58-L98)

**Section sources**
- [delegated_identity.py:28-98](file://products/agent-platform/src/agent_service/services/delegated_identity.py#L28-L98)
- [spec.md:138-156](file://docs/specs/SPEC-073-role-scoped-agent-identity/spec.md#L138-L156)

### Role Vocabulary and Authority Model
The three conceptual roles are now implemented as a closed enum with clear authority boundaries, extended by the policy role axis:

| Role | Authority posture | Implementation behavior |
|---|---|---|
| `diagnostician` | Read-only toolkit. | Reuses `_filter_read_only` over discovered tools; policy rules may grant diagnostician-scoped access. |
| `orchestrator` | Delegation-only; no direct tool authority. | Returns empty list from `_narrow_for_role`; policy rules may restrict orchestrator access further. |
| `executor` | May stage mutations through the existing HITL + signed path. | Returns full definitions; mutations still park on HITL; policy enforces executor→human approver invariant. |

```mermaid
flowchart TD
Role["agent_role"] --> Diagnostician["diagnostician"]
Role --> Orchestrator["orchestrator"]
Role --> Executor["executor"]
Diagnostician --> ToolkitD["Toolkit subset: read-level tools"]
Orchestrator --> ToolkitO["Toolkit subset: empty (no gateway tools)"]
Executor --> ToolkitE["Toolkit subset: may include mutating tools"]
ToolkitE --> Park["Park on existing HITL confirmation"]
Park --> Approve["Distinct human approves"]
Approve --> Dispatch["Signed at-most-one dispatch"]
PolicyLayer["Policy Layer (Phase 3)"] --> AgentRoles["agent_roles_any matching"]
AgentRoles --> Conjunctive["Conjunctive with human roles_any"]
```

**Diagram sources**
- [spec.md:98-125](file://docs/specs/SPEC-073-role-scoped-agent-identity/spec.md#L98-L125)
- [spec.md:158-178](file://docs/specs/SPEC-073-role-scoped-agent-identity/spec.md#L158-L178)
- [authorization-matrix.md:155-186](file://docs/agentic-aiops-platform/authorization-matrix.md#L155-L186)

**Section sources**
- [spec.md:98-125](file://docs/specs/SPEC-073-role-scoped-agent-identity/spec.md#L98-L125)
- [spec.md:257-305](file://docs/specs/SPEC-073-role-scoped-agent-identity/spec.md#L257-L305)

## Dependency Analysis
SPEC-073's phase-2 dependencies are intentionally narrow and all dependencies are satisfied, with phase 3 extending into the gateway policy layer:

```mermaid
graph LR
Spec["SPEC-073 spec.md"] --> Kernel["runtime_kernel.py"]
Spec --> Identity["delegated_identity.py"]
Spec --> RoleModule["agent_role.py"]
Spec --> Plan["plan.md"]
Spec --> Tasks["tasks.md"]
Spec --> PolicyAxis["SPEC-074 Policy Role Axis"]
Kernel --> Agentscope["agentscope.tool.Toolkit"]
Kernel --> Gateway["tool_gateway_url"]
Identity --> JWT["PyJWT / PyJWKClient"]
RoleModule --> ContextVars["contextvars.ContextVar"]
PolicyAxis --> PlatformGW["platform-gateway policy_engine.py"]
PolicyAxis --> ToolGW["tool-gateway policy_engine.py"]
PolicyAxis --> Schema["policy-rule.schema.json v3"]
Tests["test_agent_role.py"] --> AllComponents["All delivered components"]
```

**Diagram sources**
- [spec.md:232-249](file://docs/specs/SPEC-073-role-scoped-agent-identity/spec.md#L232-L249)
- [agent_role.py:22-27](file://products/agent-platform/src/agent_service/services/agent_role.py#L22-L27)
- [runtime_kernel.py:520-557](file://products/agent-platform/src/agent_service/runtime_kernel.py#L520-L557)
- [delegated_identity.py:13-13](file://products/agent-platform/src/agent_service/services/delegated_identity.py#L13-L13)
- [policy_engine.py:428-499](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L428-L499)

### Coupling and Cohesion
- **High cohesion within agent-platform**: The substrate lives in `agent_service`, where toolkit construction and identity context already coexist.
- **Low coupling to external services**: The role concept itself is process-local; the only external dependency is the existing tool discovery call through `tool_gateway_url`.
- **No new principal**: The spec explicitly forbids per-role broker identities, keeping identity coupling to the single delegated token.
- **Phase 3 gateway integration**: Policy engines mirror the closed vocabulary locally since they cannot import agent-platform types across product boundaries.

### Potential Risks
- If role binding leaks into serialized surfaces, it violates R-1 and R-3.
- If toolkit widening occurs due to incorrect cache-key logic, it violates R-2 and R-5.
- If executor staging bypasses the existing HITL path, it violates R-4.
- If policy axis widens authority beyond human roles, it violates the subtractive-only invariant.
- If agent-role literals appear outside policy_engine.py, it violates the reachability guard.

**Section sources**
- [spec.md:111-182](file://docs/specs/SPEC-073-role-scoped-agent-identity/spec.md#L111-L182)
- [agent_role.py:30-120](file://products/agent-platform/src/agent_service/services/agent_role.py#L30-L120)
- [runtime_kernel.py:501-660](file://products/agent-platform/src/agent_service/runtime_kernel.py#L501-L660)
- [delegated_identity.py:28-55](file://products/agent-platform/src/agent_service/services/delegated_identity.py#L28-L55)

## Performance Considerations
SPEC-073's performance expectations are conservative because phase 2 is inert, with phase 3 adding minimal overhead:

- The existing per-token toolkit cache must be extended to split by role only when a role can change the constructed toolkit.
- An unrole-scoped single-agent turn must keep one cache entry and remain byte-identical.
- Empty discovery results must remain uncached, matching current behavior.
- No additional network round-trips to the identity broker or tool gateway are introduced by the role label itself.
- The role context operations are lightweight ContextVar operations with minimal overhead.
- Policy evaluation adds negligible CPU overhead for the optional agent-role matching condition.
- The policy engines maintain identical performance characteristics since the default `agent_role=None` path is byte-identical.

These constraints follow directly from R-2's cache semantics and the existing `_ensure_toolkit` implementation, plus the inert deployment guarantees of SPEC-074.

**Section sources**
- [spec.md:111-130](file://docs/specs/SPEC-073-role-scoped-agent-identity/spec.md#L111-L130)
- [runtime_kernel.py:501-580](file://products/agent-platform/src/agent_service/runtime_kernel.py#L501-L580)

## Implementation Roadmap
SPEC-073 follows a binding four-stage rollout plan established in the approved implementation plan, all stages now completed, with phase 3 completing the multi-agent orchestration series:

### Stage 1: Role Type + Context Variable (R-1) ✅ COMPLETED
- ✅ Added `services/agent_role.py` with closed `AgentRole` enum (`diagnostician`, `orchestrator`, `executor`)
- ✅ Implemented `AGENT_ROLE: ContextVar[AgentRole | None]` with fail-closed `coerce_agent_role`
- ✅ Created `agent_role_scope` context manager for role binding
- ✅ Tested out-of-set construction rejection and immutability guarantees

### Stage 2: Per-Role Toolkit Narrowing (R-2) ✅ COMPLETED
- ✅ Extended `_ensure_toolkit`'s `cache_key` to append `::{role.value}` only when a role is bound
- ✅ Added `_narrow_for_role(definitions, role)` method with role-specific filtering
- ✅ Tested per-role toolkit contents and subtractive-only invariant
- ✅ Verified cache splitting per role while maintaining unscoped behavior

### Stage 3: Same-Token Identity Preservation (R-3) ✅ COMPLETED
- ✅ Set/reset `AGENT_ROLE` around role-scoped turns mirroring `DELEGATED_TOKEN` bracket
- ✅ Tested member presents same delegated token as orchestrator
- ✅ Verified requester `VerifiedHuman` unchanged across delegation hop
- ✅ Confirmed role never appears as JWT claim or wire field

### Stage 4: Provenance Labeling + Guards (R-4, R-5) ✅ COMPLETED
- ✅ Record staging `AgentRole` on kernel-internal parked/confirmation records via `staged_by_role`
- ✅ Implement fail-closed guards for absent/unrecognized roles
- ✅ Add guard tests asserting no role-scoped path reachable from deployed handlers
- ✅ Verify contract schemas remain unchanged

### Stage 5: Inertness Proof (R-5) ✅ COMPLETED
- ✅ Verify single-agent turn is byte-identical with substrate present but unexercised
- ✅ Confirm full agent-platform suite + root `make verify` green (1710 tests passed)
- ✅ Validate no contract or gateway/policy changes
- ✅ Execute comprehensive test suite with 29 new role-specific tests

### Stage 6: Documentation Reconciliation (R-6) ✅ COMPLETED
- ✅ Updated `identity-and-authorization-design.md` with role model and phase boundaries
- ✅ Annotated ADR-0017 consequence note that phase 2 is delivered
- ✅ Updated specs index and roadmap rows to reflect delivery status
- ✅ Maintained no changes to shared contract schemas

### Phase 3 Completion: Policy Role Axis (SPEC-074) ✅ COMPLETED
- ✅ Extended `policy-rule.schema.json` to v3 with additive `agent_roles_any` field
- ✅ Implemented agent-role axis in both platform-gateway and tool-gateway policy engines
- ✅ Added conjunctive composition with human roles and fail-closed semantics
- ✅ Updated authorization matrix and policy specification documentation
- ✅ Created scenario-expectation coverage for agent-role matching semantics
- ✅ Verified inert deployment with no deployed caller threading agent-role
- ✅ Complete multi-agent orchestration series from ADR-0017 now delivered

**Section sources**
- [plan.md:97-105](file://docs/specs/SPEC-073-role-scoped-agent-identity/plan.md#L97-L105)
- [tasks.md:7-85](file://docs/specs/SPEC-073-role-scoped-agent-identity/tasks.md#L7-L85)

## Troubleshooting Guide
When implementing or reviewing SPEC-073, use these checks based on the delivered implementation:

| Symptom | Likely cause | Required check |
|---|---|---|
| Toolkit widens under a restricted role | Cache key or narrowing logic grants tools instead of subtracting them. | Assert role toolkit ⊆ unscoped toolkit for the same token using `_count_gateway_tools`. |
| Diagnostician can stage mutations | Role mapping exposes mutating tools or bypasses `_filter_read_only`. | Verify diagnostician toolkit has no mutating tool via `_narrow_for_role` tests. |
| Orchestrator sees gateway tools | Role is mapped to more than delegation-only. | Verify orchestrator toolkit excludes gateway tools (should be empty). |
| Broker exchange invoked multiple times per user | Code mints or requests a second delegated token for a role. | Add a guard test failing on extra broker calls (see test_agent_role.py patterns). |
| Requester identity changes after delegation | Role context or identity contextvar handling is incorrect. | Assert `VerifiedHuman` equality before and after delegation using existing test patterns. |
| Contract test fails unexpectedly | Phase-2 code added a field to `execution-request.schema.json`. | Confirm phase-2 leaves the schema byte-unchanged (already verified in tests). |
| Single-agent path behaves differently | Substrate is not inert or cache key changed for unrole-scoped turns. | Run full suite and compare deployed chat path behavior (1710 tests should pass). |
| Role context doesn't restore properly | `agent_role_scope` context manager not used correctly. | Verify proper usage of context manager pattern with try/finally semantics. |
| Unknown role causes unexpected behavior | `coerce_agent_role` not rejecting invalid values. | Test that unknown values raise `AgentRoleError` with message "agent_role_invalid". |
| Policy rule with agent_roles_any matches unscoped call | Fail-closed semantics not implemented correctly. | Verify rule never matches when `agent_role=None` (SPEC-074 R-2). |
| Agent-role literal found outside policy_engine.py | Reachability guard violation in phase 3. | Scan product source for agent-role literals or `agent_role=` keyword usage. |
| Policy evaluation differs between gateways | Engine-specific behavior not accounted for. | Verify tool-gateway skips require_approval rules (SPEC-030 R-2). |
| Schema validation fails for agent_roles_any | Out-of-vocabulary values or malformed structure. | Test against closed vocabulary `{diagnostician, orchestrator, executor}`. |

**Section sources**
- [spec.md:111-191](file://docs/specs/SPEC-073-role-scoped-agent-identity/spec.md#L111-L191)
- [test_agent_role.py:68-299](file://products/agent-platform/tests/test_agent_role.py#L68-L299)

## Conclusion
SPEC-073 is a narrowly scoped, defensively designed substrate that has successfully advanced from draft to delivered status, with phase 3 completion marking the successful realization of the multi-agent orchestration series from ADR-0017. Its value is not in adding new runtime surfaces, but in fixing the identity and authority seam that ADR-0017 requires before later phases can safely add audit attribution, bounded autonomous diagnosis, and a v2 multi-agent contract. The existing `_ensure_toolkit` seam and `VerifiedHuman` contextvars provide the right anchors; the delivered work includes defining the closed role vocabulary, generalizing toolkit narrowing, preserving identity, labeling executor staging internally, proving inertness, and completing the policy role axis.

With all six Open Questions resolved and a complete implementation plan executed, SPEC-073 represents a solid foundation for the phased multi-agent program. The three-value closed enum (`diagnostician`, `orchestrator`, `executor`) provides clear authority boundaries while maintaining the single-edge identity model. The process-local `AGENT_ROLE` ContextVar ensures no wire protocol changes, and the comprehensive test coverage (29 new tests plus integration with the existing 1710-test suite) validates all requirements.

**Phase 3 completion** delivers the policy role axis (SPEC-074), completing the two-layer narrowing model: toolkit narrowing (what an agent sees) plus policy evaluation (what the gateway authorizes). The additive v3 policy schema extension, dual gateway engine implementations, and scenario-expectation framework ensure the axis is inert, subtractive-only, and fail-closed. The authorization matrix and identity design documentation have been updated to reflect the complete model, including the `executor`→human-approver invariant encoded as policy.

The multi-agent orchestration series from ADR-0017 is now complete through the policy layer, with future phases (audit attribution, bounded diagnosis, v2 contract) building upon this solid foundation. The delivered substrate provides clear boundaries between what was accomplished (identity, toolkit narrowing, policy axis) and what remains for later phases (wire projection, live binding, orchestration loop).