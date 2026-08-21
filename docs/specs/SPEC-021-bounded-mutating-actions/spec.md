# SPEC-021: Bounded Mutating Actions — First Approval-Gated Write Tool

## Status

- status: `delivered`
- owner: chi
- created: 2026-08-21
- release slice: R4 approval-gated bounded actions — second slice (0.7.0 train)
- related ADRs: none new; builds on SPEC-020 (HITL confirmation bridging — the mandated precondition), SPEC-018 Future Scope (write/mutating tools may only land after the HITL bridge), SPEC-007 (read-only tool execution framework), SPEC-004 (deny-by-default policy), SPEC-012/SPEC-015 guide discipline

## Summary

Deliver the platform's first bounded mutating capability — one approval-gated Kubernetes action (`k8s.delete_pod`) — end to end through the existing SPEC-020 HITL path, with risk-tier enforcement at the tool-gateway, a new deny-by-default `tools:mutate` policy action, fail-closed allow-list invariants, and a new operator guide covering the full approval model: how tools are admitted, how to manage the auto-allow list, how approval requirements are defined via the policy bundle today, and how that maps to the future policy-center.

## Motivation

- SPEC-020 delivered the read-to-write bridge precisely so this slice could exist: the SPEC-018 utilization memo declares HITL bridging "MUST precede any write/mutating tool", and that precondition is now satisfied. Every release so far (tools, evidence, skills, incidents, HITL) has been scaffolding toward agent-assisted remediation; R4's theme is "safe operational action through approval".
- The tool contract already anticipates this: `ToolDefinition.risk_level` has carried the `"read" | "write" | "admin"` vocabulary since SPEC-007, every tool registers `risk_level="read"` today, and both the policy bundle and the Tool and Connector Guide carry explicit "re-scope before any mutating tool" reservations.
- The policy bundle's `tools:invoke` grant to `read-only-observer` is only safe while every registered tool is read-only; admitting the first write tool without re-scoping admission would break the authorization matrix invariant.
- Operators currently have no documentation describing how approval works on this platform: how the allow-list (`AGENT_GATEWAY_TOOL_AUTO_ALLOW`) interacts with HITL confirmation (`AGENT_HITL_CONFIRM_TIMEOUT`, `chat:confirm`), how policy rules admit actions, and where policy-center fits in the future. Introducing mutating capability without that guide violates the platform's operator-enablement discipline (SPEC-012).

## Requirements

Each requirement is stable once the spec is `approved` and carries testable acceptance criteria.

### R-1: Risk-tier admission at the tool-gateway

The tool-gateway enforces a risk-tier gate on invocation so that mutating tools are deny-by-default at the execution boundary, independently of any agent-side control.

Acceptance criteria:

- `ToolDefinition.risk_level` is constrained to the existing vocabulary (`read` | `write` | `admin`); invalid values fail startup registration.
- Invoking a tool with `risk_level != "read"` requires the new `tools:mutate` action evaluated by the tool-gateway policy engine (same bundle, same deny-by-default semantics as `tools:invoke`); read tools keep requiring only `tools:invoke`. A caller with `tools:invoke` but without `tools:mutate` receives the standard structured 403, counted in metrics.
- New setting `GATEWAY_MUTATING_TOOLS_ENABLED` (default `false`): when false, tools with `risk_level != "read"` are not registered at startup (absent from `tools:list` discovery and from invoke, which returns `TOOL_NOT_FOUND`), so an unset deployment's tool surface is byte-identical to today's.
- Tool discovery (`GET /api/v2/tools`) already returns `risk_level` per tool; no contract change, but the gateway tests pin that a registered mutating tool reports `risk_level: "write"`.

### R-2: First bounded mutating tool — `k8s.delete_pod`

The Kubernetes connector gains exactly one bounded mutating tool, feature-gated behind R-1.

Acceptance criteria:

- New tool `k8s.delete_pod` (risk `write`, category `kubernetes`): deletes a single pod by `name` (required) and `namespace` (optional, defaults to the connector namespace). No label-selector, wildcard, count-based, or multi-pod variants — bounded means one named object per invocation. Deleting a controller-managed pod is the platform's bounded "restart" primitive; the tool description states this and notes the controller recreates the pod.
- The tool is registered only when `GATEWAY_K8S_ENABLED` and `GATEWAY_MUTATING_TOOLS_ENABLED` are both true.
- Execution follows the connector conventions: delegated-token bearer identity, structured error mapping (404 pod → `RESOURCE_NOT_FOUND`-style code, RBAC/forbidden → structured error), redaction choke point unchanged, evidence envelope carries `risk_level: "write"`, and every invocation emits the standard `tool_invoked` audit event (the confirmer's identity rides the delegated token per SPEC-020).
- No other mutating tool is added in this spec; `k8s.scale_*`, `k8s.rollout_*`, and all Elastic/skills/incidents writes are explicitly out of scope.

### R-3: HITL confirmation invariant for mutating tools

agent-platform guarantees that a mutating tool can never execute without a human confirmation, regardless of operator configuration.

Acceptance criteria:

- The allow-list loader treats the auto-allow surface as read-only-by-construction: tools discovered with `risk_level != "read"` are excluded from auto-approval even if their name appears in `AGENT_GATEWAY_TOOL_AUTO_ALLOW`; the exclusion is logged once at toolkit construction. Admission and policy at the tool-gateway remain the enforcement backstop (R-1).
- A mutating tool proposal always resolves to an explicit ASK and parks as a SPEC-020 confirmation card; there is no configuration path that auto-runs a mutating tool.
- When HITL bridging is disabled (`AGENT_HITL_CONFIRM_TIMEOUT=0`), non-read tools are excluded from the agent's toolkit entirely and the no-tools/mutating-unavailable posture is surfaced honestly in the system context — a mutating action can never silently park and never silently run.
- `agent-stream-event.schema.json` bumps v5 → v6 additively: each pending call in a `confirmation_request` frame may carry an optional `risk_level`; all existing frames remain byte-stable. The portal confirmation card renders a visible `mutating` badge when any pending call is non-read, and the Tools inventory view (SPEC-019) shows the tool's risk level and whether confirmation is required. Cache-busting strings are bumped.

### R-4: Policy bundle — `tools:mutate` action

The canonical policy bundle gains the `tools:mutate` action with deny-by-default grants and the observer re-scoping the bundle's own comments require.

Acceptance criteria:

- `policy-default.yaml` adds an `allow-operators-tools-mutate` rule granting `tools:mutate` to `platform-admin` and `operator` only; `developer`, `approver`, `auditor`, and `read-only-observer` are denied by default. The rule's comment records the rationale (execution roles per the authorization matrix's `restart-service` example; `approver` stays approve-only; extension is a documented bundle edit).
- The existing `allow-operators-tools` (`tools:invoke`) rule comment is updated to reflect that the gateway now mechanically scopes read vs write invocation by risk tier (R-1), retiring the "re-scope before any mutating tool" reservation.
- `make sync-policy` refreshes all consumer copies and the dev-k8s ConfigMap; `make validate-policy` passes.
- `docs/agentic-aiops-platform/authorization-matrix.md` documents `tools:mutate` and its grants, and the portal live permission matrix (SPEC-019 `policy:read` surface) reflects the new action without code change.

### R-5: Operator documentation — Approval and HITL Governance Guide

A new operator guide makes the approval model a documented, operable surface — this is a first-class deliverable of the spec, not a delivery footnote.

Acceptance criteria:

- New `docs/guides/approval-and-hitl.md` covering, with concrete examples:
  1. The four-layer approval model: (a) deny-by-default policy bundle actions, (b) tool risk tiers and the `tools:mutate` admission gate, (c) the agent auto-allow list, (d) HITL confirmation. Each layer names its enforcement point, its configuration surface, and what it does *not* protect against.
  2. Managing the auto-allow list: `AGENT_GATEWAY_TOOL_AUTO_ALLOW` semantics (comma-separated, empty string approves nothing, unset uses the vetted read-only default, dot/underscore normalization), how to admit a read tool to auto-approval per environment, and the invariant that mutating tools are never auto-approved regardless of this setting.
  3. Defining approval requirements today: the policy-bundle workflow (edit canonical `policy-default.yaml` → `make sync-policy` → `make validate-policy` → deploy the ConfigMap), how to grant or revoke `tools:mutate` and `chat:confirm` per role, and the HITL knobs (`AGENT_HITL_CONFIRM_TIMEOUT` incl. the 0 = disabled semantics, `chat:confirm` role grants).
  4. The road ahead: how today's layers map to the Tier-1 policy specification's `require_approval` / `allow_with_conditions` outcomes, and that `policy-center` (evaluation + approval routing) and `execution-runtime` (signed bounded execution) are the later-R4 extraction targets — kernel ASK confirmation and policy-level approval are different layers and the guide must say so explicitly.
  5. Role guidance and caveats: who should hold `tools:mutate` vs `chat:confirm`, and the explicit v1 caveat that the confirmer is the session owner (self-confirmation), pending the policy-center approval workflow with separation of duties.
- `docs/guides/tool-configuration.md` gains the mutating tool inventory row (`k8s.delete_pod`), the `GATEWAY_MUTATING_TOOLS_ENABLED` activation checklist incl. the opt-in RBAC, and replaces its "all tools read-only" reservation with a pointer to the new guide.
- `docs/guides/configuration-reference.md` documents `GATEWAY_MUTATING_TOOLS_ENABLED` and the cross-service dependency chain (tool-gateway gate → agent-platform invariant → HITL confirmation → `tools:mutate` grant).
- `docs/guides/troubleshooting.md` gains symptoms: mutating tool absent from discovery, 403 on mutating invoke, agent proposes an action but no confirmation card appears (bridging disabled), and approving a mutating card that then fails with RBAC forbidden.
- `docs/guides/README.md` indexes the new guide.

### R-6: Deployment, demo, and verification

The dev-k8s overlay and an e2e demo make the capability verifiable, and the verification gate stays green.

Acceptance criteria:

- dev-k8s: `tool-gateway` runtime config carries `GATEWAY_MUTATING_TOOLS_ENABLED=false` with a documented opt-in; a separate, commented RBAC manifest grants the tool-gateway service account `delete` on pods only (never part of the default read-only ClusterRole), applied only when the opt-in is set. The README documents the full activation path including the guide cross-reference.
- New deterministic e2e demo `shared/platform-ops/e2e/mutating-demo.sh`: asserts discovery hides the mutating tool when disabled; observer invocation is denied 403 even when enabled; an operator chat turn parks a `confirmation_request` with `risk_level: "write"`; deny leaves the pod untouched; approve deletes the target pod and the audit trail contains `confirmation_decided` plus a `tool_invoked` event carrying the confirmer identity and `risk_level: "write"`.
- `make verify` is green: all product suites (new tool-gateway risk-gate tests, agent-platform invariant tests, portal rendering behavior), all overlays render, policy and version gates pass.

## Non-Goals

- The `policy-center` and `execution-runtime` services — both remain boundary stubs; this slice executes through the existing tool-gateway path. Their extraction is a later R4 slice informed by the guide's layering (R-5).
- Policy-level approval outcomes (`require_approval`, `allow_with_conditions`), the approval queue, approval cards distinct from HITL confirmation cards, two-person rules, change windows, and self-approval prevention — all Tier-1 policy specification territory for later slices. The v1 caveat (owner self-confirms) is documented, not solved, here.
- Any mutating tool beyond `k8s.delete_pod` — scaling, rollouts, and non-Kubernetes writes are subsequent slices once this pattern is proven.
- Confirmation flow on the blocking chat path or incident-service triage — both keep the headless posture (no mutating capability there).
- Auto-approval of mutating tools under any configuration — explicitly forbidden by R-3; there is no "production fast path" requirement.

## Impact

- products touched: `products/tool-gateway` (settings, registry risk gate, policy engine action, k8s connector, tests), `products/agent-platform` (kernel middleware allow-list invariant, toolkit construction, settings, tests), `products/platform-gateway` (policy action constants, matrix passthrough, tests), `products/operator-portal/web-ui` (confirmation card risk badge, tools inventory risk column, cache-busting)
- contracts touched: `shared/shared-contracts/policies/policy-default.yaml` (new `tools:mutate` rule, comment updates), `shared/shared-contracts/schemas/agent-stream-event.schema.json` (v5 → v6, additive optional `risk_level` on confirmation pending calls)
- identity / policy / audit / execution safety impact: one new deny-by-default action (`tools:mutate`, granted to platform-admin and operator); the platform's first mutating execution surface, triple-gated (gateway risk tier → agent auto-allow invariant → HITL confirmation); confirmer identity rides the delegated token into the invocation; no new audit event types (`tool_invoked` + `confirmation_decided` already carry the chain)
- living state docs to update on delivery: `CHANGELOG.md`, `docs/specs/README.md` index, `docs/agentic-aiops-platform/authorization-matrix.md`, `docs/guides/` (new guide + four updates per R-5), `products/tool-gateway/README.md`, `products/agent-platform/README.md`, `shared/platform-ops/gitops/dev-k8s/README.md`, delivery-roadmap R4 slice note

## Open Questions

- none — owner sign-off captured 2026-08-21: (1) `tools:mutate` granted to `platform-admin` + `operator`, matching the authorization matrix's `restart-service` example (developer/approver denied by default); (2) `k8s.delete_pod` is the first tool — the most bounded cluster mutation with a natural undo (controller recreates the pod); (3) the v1 self-confirmation caveat is documented rather than solved, with separation of duties deferred to the policy-center slice.

## Changelog

- 2026-08-21: created as `draft`
- 2026-08-21: approved by owner; `plan.md` written, implementation starting
- 2026-08-21: delivered in 0.7.0 — all R-1…R-6 acceptance criteria verified; `make build` + `make verify` green
