# ADR-0002: Re-affirm AgentScope 2.0 as the Runtime Kernel

## Status

`accepted`

- date: 2026-07-28
- deciders: workspace maintainers
- related specs: `part-1b-framework-revalidation.md`, `ADR-0003`

## Context

`Part 1` selected `AgentScope 2.0` over `LangGraph` and `Microsoft Agent Framework`, weighted heavily toward security/permissions. Before committing the native runtime behind a platform-owned contract seam, the decision was revalidated against the current landscape and our `Release 0` implementation evidence (`part-1b-framework-revalidation.md`):

- AgentScope now ships a production-ready runtime with sandboxed execution and Docker/K8s deployment, strengthening the criteria it already led on
- LangGraph is the 2026 production leader for durable execution and checkpointing, but framework checkpointing is not full durable execution, and its center of gravity is orchestration rather than framework-native permissions
- Microsoft Agent Framework reached 1.0 GA but remains Azure/.NET-leaning
- our own coupling to AgentScope is narrow and confined to `products/agent-platform`; nothing outside it imports the framework

Two additional candidates were evaluated: `VoltAgent` (TypeScript agent platform; scored 74.5 — strong DX and RAG but lacks framework-native permissions and K8s-first deployment) and `Pi` (minimal coding-agent harness; excluded as a different category — no permission model, no MCP, no multi-session serving).

The re-score left the ranking unchanged with a wider lead (AgentScope 92.6, LangGraph 82.2, MAF 78.3, VoltAgent 74.5).

## Decision

Re-affirm `AgentScope 2.0` as the platform's runtime kernel, and record `LangGraph` as the watched alternative with explicit re-decision triggers.

## Alternatives Considered

- adopt `LangGraph` now — rejected: it still requires the platform to build the permission/sandbox/governance layer that AgentScope provides natively, which the roadmap's `R1`-`R4` phases depend on; its durability lead matters more at `R3`/`R5`
- adopt `Microsoft Agent Framework` — rejected: strong service exposure and GA maturity, but a poor fit for a provider-flexible, Kubernetes-first, on-prem control plane absent an Azure/.NET standardization
- adopt `VoltAgent` — rejected: excellent developer ergonomics and built-in RAG/workflows, but no framework-native permission model (the heaviest criterion), a TypeScript/Node.js stack misaligned with the Python-first K8s control plane, and a younger distributed-deployment story
- adopt `Pi` — rejected: different category entirely (minimal coding-agent harness); no permissions, no MCP, no multi-session serving or service-exposure primitives
- keep the decision open indefinitely — rejected: the contract seam (`ADR-0003`) already makes the kernel swappable, so re-affirming now carries low lock-in risk while unblocking native adoption

## Consequences

- the native AgentScope runtime becomes the kernel for `agent-platform`, front-loading the roadmap's permission, tool/MCP, and HITL needs
- the decision is weight-driven and contingent: it holds while the workload stays permission-and-tool-heavy
- re-decision triggers are recorded in `part-1b-framework-revalidation.md`: a shift to long-running durable workflows, near-term multi-replica/durable-execution requirements the native runtime cannot meet, an AgentScope permissions/MCP stall, or an Azure/.NET standardization
- follow-up: `ADR-0003` defines the platform-owned contract that keeps this choice swappable
