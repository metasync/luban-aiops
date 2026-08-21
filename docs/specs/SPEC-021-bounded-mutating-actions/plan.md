# SPEC-021 Plan: Bounded Mutating Actions — First Approval-Gated Write Tool

## Approach

Introduce the platform's first mutating execution path as a vertically
integrated slice that reuses every control layer SPEC-004/007/018/020 already
built, and adds exactly three new mechanisms: a risk-tier admission gate in
the tool-gateway, a fail-closed auto-allow invariant in the agent-platform,
and a new deny-by-default `tools:mutate` policy action. Everything downstream
of a confirmed decision — delegated-token identity, redaction, evidence,
`tool_invoked`/`confirmation_decided` audit — is existing machinery.

The slice deliberately stays on the tool-gateway execution path: `policy-center`
and `execution-runtime` remain boundary stubs until this pattern is proven.
The operator guide (R-5) is written to make that layering explicit so the
policy-center extraction has a documented target.

Stages: contracts & policy (R-4, R-1 contracts) → tool-gateway gate + tool
(R-1, R-2) → agent-platform invariant + stream frame (R-3) → portal surfaces
(R-3) → operator docs (R-5) → deployment + e2e + gate (R-6).

## Design Per Requirement

### R-1: Risk-tier admission at the tool-gateway

- affected files / modules: `products/tool-gateway/src/tool_gateway/core/settings.py`, `services/policy_engine.py`, `services/gateway_service.py`, `tools/registry.py`, `tools/base.py`, `api/routes` (invoke/discovery), tests
- chosen approach: `ToolRegistry` validates `risk_level` ∈ {read, write, admin} at registration and filters non-read tools out when `GATEWAY_MUTATING_TOOLS_ENABLED` is false (they are simply never registered — discovery and invoke behave as if the tool does not exist). The invoke path resolves the tool's risk tier and selects the required action: `tools:invoke` for read, the new `tools:mutate` for write/admin, evaluated through the existing `enforce_policy` machinery (same bundle, same structured 403).
- alternatives considered: per-tool action names (`tools:k8s.delete_pod`) — rejected for this slice: action-per-tool explodes the bundle vocabulary before the tool taxonomy is proven; the risk-tier split mirrors the existing `risk_level` vocabulary and keeps the bundle at one new action.

### R-2: First bounded mutating tool — `k8s.delete_pod`

- affected files / modules: `products/tool-gateway/src/tool_gateway/tools/k8s_connector.py`, tests
- chosen approach: a `DeletePodTool` following the existing `BaseTool` pattern (lazy client, executor-based sync wrapper), `risk_level="write"`, parameters `name` (required) + `namespace` (optional). Uses `core_v1.delete_namespaced_pod` with default propagation; errors mapped through the connector's structured error conventions (ApiException 404 → not-found code, 403 → permission code). Registered only when both `GATEWAY_K8S_ENABLED` and `GATEWAY_MUTATING_TOOLS_ENABLED` are true.
- alternatives considered: `k8s.restart_deployment` (rollout restart via patch) — rejected as the first tool: a deployment patch touches controller state and has wider blast radius than deleting one pod managed by its controller; delete-pod is the most bounded mutation with a natural undo.

### R-3: HITL confirmation invariant for mutating tools

- affected files / modules: `products/agent-platform/src/agent_service/services/kernel_middleware.py` (allow-list resolution + permission decision), toolkit construction path (per-token toolkit cache), `runtime_kernel.py` (confirmation frame emission), `schemas/v2.py`, `shared/shared-contracts/schemas/agent-stream-event.schema.json`, tests
- chosen approach: toolkit construction already receives tool definitions including `risk_level` from discovery; the permission middleware's auto-allow check gains one condition — the tool must be read-risk — so a non-read tool ASKs even if named in `AGENT_GATEWAY_TOOL_AUTO_ALLOW`. When `AGENT_HITL_CONFIRM_TIMEOUT=0`, toolkit construction drops non-read tools from registration entirely (an ASK that can never park is a lie; the honest posture is "tool not available", surfaced through the existing no-tools notice machinery when it empties the toolkit). The `confirmation_request` pending-call object gains optional `risk_level` (schema v5 → v6, additive).
- alternatives considered: a separate `AGENT_MUTATING_TOOLS_ENABLED` setting in agent-platform — rejected: the gateway gate (R-1) plus discovery-driven filtering already make the agent's surface truthful; a second flag would create a configuration matrix with no safety benefit.

### R-4: Policy bundle — `tools:mutate` action

- affected files / modules: `shared/shared-contracts/policies/policy-default.yaml`, platform-gateway + tool-gateway packaged copies (via `make sync-policy`), dev-k8s ConfigMap, `docs/agentic-aiops-platform/authorization-matrix.md`
- chosen approach: one new rule `allow-operators-tools-mutate` granting `tools:mutate` to `platform-admin` and `operator`; all other roles denied by default. Follows the bundle's existing naming/priority/comment conventions; the SPEC-019 live permission matrix picks the action up automatically.
- alternatives considered: reusing `tools:invoke` with a role-conditioned deny rule for mutating — rejected: the gateway cannot express "this invocation targets a write tool" inside an action string without a new action, and deny-by-default with an explicit new action is the bundle's own convention for capability growth (see the `chat:confirm` precedent).

### R-5: Operator documentation — Approval and HITL Governance Guide

- affected files / modules: new `docs/guides/approval-and-hitl.md`; updates to `docs/guides/tool-configuration.md`, `configuration-reference.md`, `troubleshooting.md`, `README.md`
- chosen approach: a dedicated guide (rather than appending to configuration-reference) because the approval model spans four services and needs a narrative layering explanation; the reference guides keep their env-var/checklist roles and cross-link. Written against the as-delivered behavior, including the v1 self-confirmation caveat and the policy-center/execution-runtime future mapping (from `docs/workspace/product-boundaries.md` and the Tier-1 policy specification).
- alternatives considered: documenting inside tool-configuration.md only — rejected: auto-allow management, policy workflow, and HITL knobs are cross-cutting governance topics, not connector activation.

### R-6: Deployment, demo, and verification

- affected files / modules: `shared/platform-ops/gitops/dev-k8s/` (tool-gateway runtime-config.env, new opt-in RBAC manifest + README), new `shared/platform-ops/e2e/mutating-demo.sh`, root Makefile only if the demo needs wiring (follows the skills-demo/incident-demo precedent)
- chosen approach: mutating capability ships disabled in the overlay (`GATEWAY_MUTATING_TOOLS_ENABLED=false`); activation is a documented opt-in that applies the pod-delete RBAC manifest and flips the flag. The e2e demo creates a throwaway pod, drives the scripted chat → confirmation → approve/deny paths, and asserts the audit chain.
- alternatives considered: enabling by default in dev-k8s — rejected: the overlay should demonstrate the safe default; the demo flips the gate explicitly.

## Sequencing And Dependencies

1. Policy bundle + action vocabulary (R-4) — depends on nothing; unblocks gateway work
2. tool-gateway risk gate + `k8s.delete_pod` (R-1, R-2) — depends on 1
3. agent-platform invariant + stream frame bump (R-3 backend) — depends on 2 (needs risk_level in discovery)
4. portal surfaces (R-3 frontend) — depends on 3
5. Operator guide + guide updates (R-5) — depends on 2–4 (documents as-delivered semantics)
6. dev-k8s overlay, e2e demo, `make verify`, delivery close (R-6) — depends on all above

## Test Strategy

- unit tests: tool-gateway risk-gate matrix (read→invoke, write→mutate, disabled→absent, invalid risk_level→startup failure), `k8s.delete_pod` error mapping against the fake k8s client; agent-platform allow-list invariant (write tool named in allow-list still ASKs; bridging-disabled drops write tools; read behavior byte-stable)
- contract tests: `agent-stream-event.schema.json` v6 frame validation incl. optional `risk_level`; policy bundle validation via `make validate-policy`
- integration / overlay validation: `kustomize build` for all overlays, e2e `mutating-demo.sh` against dev-k8s (discovery gating, observer 403, park/approve/deny, audit chain), `make verify` green

## Rollout And Migration

- deployment/configuration changes: new `GATEWAY_MUTATING_TOOLS_ENABLED` (default false) in tool-gateway settings and overlay; new `tools:mutate` rule synced to all four bundle copies + ConfigMap; opt-in pod-delete RBAC manifest (never merged into the default ClusterRole)
- backward compatibility: unset deployments are behaviorally identical — no mutating tool registers, no new action is exercised, stream frames unchanged (the v6 bump is additive-optional)
- rollback approach: set `GATEWAY_MUTATING_TOOLS_ENABLED=false` (or unset) and remove the opt-in RBAC manifest; no state to migrate back
