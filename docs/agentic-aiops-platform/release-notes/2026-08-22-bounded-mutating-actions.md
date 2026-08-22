# Release Notes: 2026-08-22 — Bounded Mutating Actions (SPEC-021, v0.7.0)

## Summary

SPEC-021 delivers the platform's first write capability — `k8s.delete_pod`
— behind three independent, each fail-closed gates. Tool-gateway gains
risk-tier admission: every tool now carries a `risk_level`
(`read`/`write`/`admin`) validated at registration, and while
`GATEWAY_MUTATING_TOOLS_ENABLED` stays `false` (the committed default)
non-read tools are never registered — absent from discovery and answered
with `TOOL_NOT_FOUND` on invoke. When the gate is opted in, mutating
invokes additionally require the new deny-by-default `tools:mutate`
policy action, granted to `platform-admin` and `operator` only. On the
agent side, auto-allow is read-only by construction: mutating tools carry
`is_read_only=False`, so naming one in `AGENT_GATEWAY_TOOL_AUTO_ALLOW`
can never grant auto-execution — it is logged as misconfiguration and
still parks for confirmation. Every mutating call therefore reaches
execution only through the SPEC-020 HITL bridge: the confirmation card
gains a `mutating` badge and per-call `risk_level` markers (stream schema
v6), and approval remains an explicit operator action.

Live testing on the dev cluster validated the whole chain, including the
fail-closed behavior: with the opt-in RBAC not yet applied, an approved
deletion reached the Kubernetes API and was refused there (403 mapped to
a structured tool error), proving every platform gate had opened while
cluster-level blast radius stayed zero.

## Change Set 1: Risk-tier admission and `tools:mutate` (R-1, R-4)

### Highlights

- `ToolDefinition.risk_level` vocabulary (`read`/`write`/`admin`)
  validated at registration; invalid tiers refuse the tool.
- Registry admission: non-read tools are skipped (with a startup log)
  while `GATEWAY_MUTATING_TOOLS_ENABLED` is false — discovery and invoke
  both fail closed.
- Invoke path: read tools keep `tools:invoke`; write/admin tools
  additionally require `tools:mutate`, with structured 403, warning log,
  and `policy_decision` audit event on deny. Denied envelopes carry the
  tool's true `risk_level`.
- Policy bundle: new `allow-operators-tools-mutate` rule (12 rules now
  validate); `tools:mutate` added to both gateways' protected-action
  vocabularies; all four bundle copies byte-identical via
  `make sync-policy`.
- New bounded tool `k8s.delete_pod` (namespace-scoped, single pod) with
  structured 404/403 error mapping.

### Why It Matters

Every layer denies independently: a misconfigured flag, a missing policy
rule, or a missing RBAC verb each stops the mutation on its own. The
authorization matrix now pins approver/developer/observer denial of
`tools:mutate` in tests.

## Change Set 2: Read-only-by-construction auto-allow and HITL surfacing (R-3)

### Highlights

- `gateway_risk_level` on FunctionTools flows into parked confirmation
  frames; `confirmation_request`/`confirmation_result` carry optional
  `risk_level` per pending call (agent-stream-event schema v6).
- Auto-allow exclusion invariant tested: mutating tools can never bypass
  the confirmation bridge regardless of allow-list contents.
- HITL-disabled posture (`AGENT_HITL_CONFIRM_TIMEOUT=0`) drops non-read
  tools from the toolkit entirely and injects a deterministic system
  notice — write capability can never silently become unconfirmable.
- Portal: amber `mutating` badge on confirmation cards, per-call risk
  badges, and a confirmation column in the Tools inventory.

### Why It Matters

The agent layer cannot be tricked into auto-executing a write tool even
by operator misconfiguration; the invariant is structural, not prompt-
based.

## Change Set 3: Operator enablement and deployment posture (R-5, R-6)

### Highlights

- New Approval and HITL Governance Guide (`docs/guides/approval-and-hitl.md`)
  covering the four-layer approval model, auto-allow management, policy
  bundle workflow, and every HITL knob; tool-configuration,
  configuration-reference, and troubleshooting guides updated.
- dev-k8s commits `GATEWAY_MUTATING_TOOLS_ENABLED=false` with a
  documented four-step opt-in; the pod-delete Role/RoleBinding ships as
  an out-of-kustomization manifest so default deploys never gain delete
  verbs.
- New deterministic `shared/platform-ops/e2e/mutating-demo.sh`: asserts
  the deny-by-default posture on default deploys, the full opt-in chain
  after enablement, and an opt-in HITL chat leg with audit assertions.

### Why It Matters

Activation is an explicit, auditable operator action with a matching
deactivation path; the e2e script is rerunnable in either posture.

## Validation

- `make verify` green after final review fixes: 1003 tests across seven
  products (agent-platform 281, tool-gateway 196, platform-gateway 148,
  incident-service 130, skills-hub 118, audit-service 70,
  identity-broker 60), all four kustomize overlays render, 12 policy
  rules validate, version lockstep 0.7.0.
- Pre-tag code & doc review: no blocking issues; two findings fixed
  (denied-envelope `risk_level` fidelity, schema-version docstring).
- Live cluster test: portal approval of `k8s.delete_pod` recycled the
  target pod end to end; prior run without opt-in RBAC demonstrated the
  Kubernetes-side fail-closed layer with a structured error envelope.
- L3 deep security review on the committed change set: no findings.
- Shipped as commits `53ea460` + `40b3551`, tag `v0.7.0`.

## Known Limitations

- Mutating capability is single-tool and Kubernetes-only
  (`k8s.delete_pod`); further write tools require their own risk-tier
  registration, RBAC manifests, and guide updates.
- Policy-center `require_approval` semantics are not yet enforced —
  approval requirements come from the HITL bridge and policy actions,
  not per-rule declarations (next R4 slice).
- `mutating-demo.sh`'s HITL chat leg is LLM-dependent and opt-in
  (`RUN_HITL_LEG=true`), mirroring the other e2e demos' chat legs.

## Related Documents

- `docs/specs/SPEC-021-bounded-mutating-actions/` (spec, plan, tasks)
- `docs/guides/approval-and-hitl.md`
- `docs/guides/tool-configuration.md` (activation checklist)
- `shared/platform-ops/gitops/dev-k8s/README.md` (opt-in runbook)
- `CHANGELOG.md` (0.7.0)
