# SPEC-012: Operator Guide and Deployment Documentation

## Status

- status: `approved`
- owner: workspace maintainers
- created: 2026-08-05
- release slice: `R1` (read-only operations copilot)
- related ADRs: ADR-0002 (AgentScope runtime kernel), ADR-0003 (platform-owned agent service contract), ADR-0005 (platform gateway extraction)

## Summary

Create operator-facing documentation that enables engineers to deploy, configure, verify, and troubleshoot the platform end-to-end — closing the gap between developer specs (SPEC-001..011) and the operational knowledge required to run the platform in a local or staging Kubernetes cluster.

## Motivation

SPEC-007 through SPEC-011 delivered a fully wired read-only operations copilot: Kubernetes tools, token delegation, deterministic redaction, Elastic observability connector, and an evidence panel. However, the documentation landscape is entirely developer-facing:

1. **Scattered knowledge**: configuration details are spread across 5 product READMEs, 11 spec documents, the dev-k8s overlay README, and the CHANGELOG. No single document tells an operator "here is what you need to deploy and run this platform."
2. **Hidden prerequisites**: the token delegation chain (SPEC-008) requires two optional K8s secrets with matching shared credentials. Missing secrets cause silent failures (agent reports "access not granted") with no obvious diagnostic path. This exact issue was encountered during SPEC-011 verification.
3. **No troubleshooting surface**: when something breaks, the operator has no symptom → cause → resolution guide. Each issue requires reading source code to understand the failure mode.
4. **Feature activation is undocumented**: enabling a connector (K8s, Elastic) involves cross-service configuration (env vars, RBAC, secrets) that is only described in the spec that introduced it.

The existing dev-k8s README (`shared/platform-ops/gitops/dev-k8s/README.md`, 325+ lines) is implementation-oriented and assumes familiarity with the platform's architecture. It is a deployer's reference, not an operator's guide.

## Requirements

### R-1: Getting Started Guide

A task-oriented walkthrough that takes an engineer from "I have a Kubernetes cluster" to "the agent can invoke tools and I can see evidence in the portal."

**Acceptance criteria:**
- Prerequisites section: Kubernetes (kind/minikube/real cluster), kubectl, make, Docker or Podman
- Step-by-step build → deploy → verify flow with concrete commands
- Secrets provisioning: LLM provider API key, token delegation secrets, OIDC client secret (when required)
- End-to-end verification checklist: portal login → session creation → agent reply → tool invocation → evidence panel
- Document lives at `docs/guides/getting-started.md`

### R-2: Configuration Reference

A definitive cross-service environment variable dependency map that shows which variables interact across service boundaries and what each feature requires.

**Acceptance criteria:**
- Feature activation matrix: table mapping capabilities (tools, K8s connector, Elastic connector, redaction, OTel) to required env vars and secrets
- Cross-service dependency chains: token delegation, tool relay, identity flow
- Per-service env var table with purpose, default, and source file
- Document lives at `docs/guides/configuration-reference.md`

### R-3: Troubleshooting Guide

A symptom-based diagnostic guide covering the most common deployment and runtime issues.

**Acceptance criteria:**
- At minimum, cover: "agent says access not granted," "agent has no tools," "portal login fails," "stream never completes," "tool returns denied by policy"
- Each symptom includes: likely cause, diagnostic commands (kubectl logs, curl endpoints), and resolution steps
- Document lives at `docs/guides/troubleshooting.md`

### R-4: Tool and Connector Guide

An inventory of available tools and a per-connector activation checklist.

**Acceptance criteria:**
- Tool inventory table: tool name, description, parameters, required RBAC
- K8s connector checklist: `GATEWAY_K8S_ENABLED`, `GATEWAY_K8S_NAMESPACE`, RBAC Role/RoleBinding, service account
- Elastic connector checklist: all 7 `GATEWAY_ELASTIC_*` env vars, network reachability, auth options
- How to add a new connector (brief, pointing to the connector pattern in SPEC-007/SPEC-011)
- Document lives at `docs/guides/tool-configuration.md`

### R-5: Architecture Overview

A high-level service topology and request flow diagram for operators who need to understand how the pieces connect.

**Acceptance criteria:**
- Service topology: all 6 services (web-ui, platform-gateway, tool-gateway, agent-service, identity-service, redis) with their roles
- Request flow: portal → platform-gateway → agent-service → tool-gateway → connector → external system
- Trust chain: OIDC login → platform JWT → delegated token → tool invocation
- RBAC model: what roles exist, what actions each role grants
- Document lives at `docs/guides/architecture-overview.md`

## Non-Goals

- Production deployment hardening (network policies, ingress, autoscaling, HA Redis) — deferred to a future spec
- Cloud-specific deployment guides (EKS, GKE, AKS)
- API reference documentation (the schemas in `shared/shared-contracts` are the API contract)
- Developer contribution guide (the existing SDD workflow in `docs/specs/README.md` covers this)

## Impact

### Tier 3 Living State Documents (new)

- `docs/guides/README.md` — guide index and navigation
- `docs/guides/getting-started.md` — R-1
- `docs/guides/configuration-reference.md` — R-2
- `docs/guides/troubleshooting.md` — R-3
- `docs/guides/tool-configuration.md` — R-4
- `docs/guides/architecture-overview.md` — R-5

### Existing Documents (minor updates)

- `docs/specs/README.md` — spec index updated with SPEC-012
- `CHANGELOG.md` — Unreleased entry referencing SPEC-012

### SDD Workflow

- Each future spec's delivery gate should include a task to update affected sections of the operator guide (e.g., a new connector spec updates `tool-configuration.md`)

## Open Questions

- **Q-1**: Should the guides include Mermaid diagrams for the architecture overview, or stay text-only for maximum portability? Proposed: Mermaid (GitHub renders it natively; the SDD workflow already uses markdown).
- **Q-2**: Should the `sync-delegation-secrets.sh` script (added during SPEC-011 delivery) be considered part of this spec's R-1 deliverable, or is it a standalone fix? Proposed: standalone fix (already shipped), R-1 documents its usage.
