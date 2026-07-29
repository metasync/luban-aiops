# Part 1b: Framework Revalidation (2026-07)

## Objective

Re-run the `Part 1` framework decision against the current framework landscape
and our `Release 0` implementation evidence, before committing the native
runtime behind a platform-owned contract seam.

This is a delta review, not a from-scratch re-score. It answers two questions:

1. Is `AgentScope 2.0` still the right runtime kernel for the current roadmap?
2. Does the decision remain robust if the platform's center of gravity shifts?

This document is the evidence base for `ADR-0002` (runtime kernel re-affirmation)
and `ADR-0003` (platform-owned agent-service contract).

## What Changed Since Part 1

### External landscape

- `AgentScope 2.0`
  - now positions itself as production-ready with a dedicated `AgentScope Runtime`
  - the runtime adds full-stack serving plus secure sandboxed execution, with Docker and Kubernetes deployment support
  - this strengthens the two criteria it already led on: security/permissions and service exposure
- `LangGraph`
  - widely cited in 2026 as the production leader for durable execution, checkpointing, and human-in-the-loop pause/resume
  - its `MCP` and interoperability story has matured since the original review
  - a documented nuance: framework checkpointing is not the same as full durable execution, which matters for long-running operational workflows
- `Microsoft Agent Framework`
  - reached `1.0 GA` in April 2026, converging `AutoGen` and `Semantic Kernel` into one supported platform
  - a material change from its preview state during `Part 1`, though its center of gravity remains the Azure / `.NET` / Entra ecosystem

### Implementation evidence from Release 0

- `AgentScope` coupling is narrow and confined to `products/agent-platform`:
  - `runtime_kernel.py` (agent, message, toolkit, streaming)
  - `entrypoints/runtime.py` and `entrypoints/native.py` (serving, session state, storage/bus/workspace)
  - `providers/*` (each builds an AgentScope model instance)
- every product outside `agent-platform` reaches the kernel over HTTP; none import AgentScope
- the native entrypoint already adopts Redis-backed storage and message bus plus a local workspace manager, which de-risks the multi-replica and durable-state concerns earlier than expected

## New Candidates Added

Two additional candidates were nominated for this revalidation.

### Pi (pi.dev)

Pi is a minimal coding-agent harness (tiny core: four tools — Read, Write, Edit,
Bash — plus an extension system with persistent state and session trees). It is
well-built software, but it is a different category from an enterprise
orchestration kernel:

- no permission or sandbox model (scores low on the heaviest criterion)
- no MCP support by philosophical design (the agent writes its own tools)
- no multi-session serving, workflow engine, or HITL approval primitives
- no service-exposure story; it is a single-user coding agent, not a platform runtime

Verdict: excluded from scoring. Pi solves a different problem (personal coding
agent / agent harness) and is not a candidate for the platform's orchestration
kernel. Recorded here so the evaluation trail is complete.

### VoltAgent (voltagent.dev)

VoltAgent is an end-to-end AI agent engineering platform: an open-source
TypeScript framework (agents, workflows, supervisors, MCP, memory, RAG,
guardrails, resumable streaming) plus a commercial VoltOps console
(observability, deployment, evals). It explicitly targets enterprise agents.

## Updated Scoring (delta from Part 1)

Weights are unchanged from `Part 1`. Only changed scores are annotated.

### AgentScope 2.0

- `Security / permissions` — `5` (runtime sandbox reinforces this)
- `Stateful orchestration / reliability` — `5` (was `4`; native runtime adds Redis storage/bus and workspace management)
- `Human-in-the-loop / approvals` — `5`
- `MCP / A2A / interoperability` — `5`
- `API gateway / service exposure readiness` — `5`
- `Kubernetes / distributed fit` — `5` (was `4`; runtime ships Docker/K8s deployment)
- `Streaming UI / event model` — `5`
- `Knowledge / RAG / skills integration` — `4`
- `Hybrid / on-prem fit` — `4`
- `Developer ergonomics / extensibility` — `4`
- weighted: `92.6 / 100` (was `91.2`)

### LangGraph

- `Security / permissions` — `3`
- `Stateful orchestration / reliability` — `5`
- `Human-in-the-loop / approvals` — `5`
- `MCP / A2A / interoperability` — `4` (was `3`; ecosystem matured)
- `API gateway / service exposure readiness` — `4`
- `Kubernetes / distributed fit` — `5`
- `Streaming UI / event model` — `4`
- `Knowledge / RAG / skills integration` — `3`
- `Hybrid / on-prem fit` — `5`
- `Developer ergonomics / extensibility` — `4`
- weighted: `82.2 / 100` (was `80.8`)

### Microsoft Agent Framework

- `Security / permissions` — `4`
- `Stateful orchestration / reliability` — `4`
- `Human-in-the-loop / approvals` — `4`
- `MCP / A2A / interoperability` — `4`
- `API gateway / service exposure readiness` — `5`
- `Kubernetes / distributed fit` — `4` (was `3`; GA improved hosting/deployment story)
- `Streaming UI / event model` — `4`
- `Knowledge / RAG / skills integration` — `3`
- `Hybrid / on-prem fit` — `3`
- `Developer ergonomics / extensibility` — `4` (was `3`; unified runtime removed the AutoGen-vs-SK split)
- weighted: `78.3 / 100` (was `76.0`)

### VoltAgent

- `Security / permissions` — `3` (guardrails and content policies, but no framework-native RBAC or permission model comparable to AgentScope's bounded autonomy)
- `Stateful orchestration / reliability` — `4` (workflow engine with suspend/resume and durable memory adapters; younger than LangGraph's checkpointing)
- `Human-in-the-loop / approvals` — `4` (explicit workflow suspend/resume with typed resume schemas)
- `MCP / A2A / interoperability` — `4` (native MCP client support, multi-provider LLM compatibility)
- `API gateway / service exposure readiness` — `4` (HTTP server via Hono, resumable streaming; less gateway-proven than AgentScope or MAF)
- `Kubernetes / distributed fit` — `3` (Node.js/Hono; containerizable but not K8s-first; no native distributed-deployment story documented)
- `Streaming UI / event model` — `4` (resumable streaming with client reconnect)
- `Knowledge / RAG / skills integration` — `4` (managed knowledge base, retriever agents, RAG built in)
- `Hybrid / on-prem fit` — `3` (TypeScript/Node.js; VoltOps console has cloud coupling; self-hosted option exists but less on-prem-proven)
- `Developer ergonomics / extensibility` — `5` (Zod-typed tools, CLI scaffolding, strong DX, MIT license)
- weighted: `74.5 / 100`

## Result

- `1. AgentScope 2.0` — `92.6 / 100`
- `2. LangGraph` — `82.2 / 100`
- `3. Microsoft Agent Framework` — `78.3 / 100`
- `4. VoltAgent` — `74.5 / 100`
- `—. Pi` — excluded (different category; see above)

The ranking of the original three is unchanged and the lead widened. The
movement came from AgentScope closing its own gaps (stateful orchestration,
distributed fit), not from competitors regressing.

VoltAgent enters below the original three. Its strengths (developer ergonomics,
RAG, HITL workflows) are real, but it loses ground on the platform's
highest-weighted criteria: it lacks a framework-native permission model
(`Security / permissions` weight 18), and its TypeScript/Node.js stack is not
Kubernetes-first or on-prem-proven. It would become more relevant if the
platform adopted a Node.js runtime layer or if its distributed-deployment story
matured.

## Sensitivity Analysis

The decision is weight-driven, and that is the honest risk to record:

- `Security / permissions` carries the heaviest weight (`18`), and AgentScope leads LangGraph by `2` points there. That single criterion contributes most of the margin.
- if the platform re-weights toward durable orchestration and large-scale stateful reliability (LangGraph's strength) and away from framework-native permissions, the margin narrows materially.
- the roadmap today front-loads AgentScope's strengths (`R1` tools/MCP, `R4` permissions/approvals/HITL). LangGraph's advantages matter more at `R3`/`R5` scale and resumability.

Conclusion: AgentScope remains the best fit for the roadmap as written, but the
decision is contingent on the weighting staying permission-and-tool-heavy.

## Decision

- re-affirm `AgentScope 2.0` as the runtime kernel (`ADR-0002`)
- adopt a platform-owned agent-service contract so the kernel sits behind an adapter inside `agent-platform` and remains swappable (`ADR-0003`)
- because the seam is kernel-agnostic, the contract decision is safe to adopt now and does not pre-empt this revalidation

## Re-decision Triggers

Re-open the matrix if any of these become true:

- the platform's dominant workload shifts to long-running, resumable, deterministic operational workflows where checkpoint-based durability is the primary requirement
- multi-replica scale or durable-execution guarantees become a near-term (`R3`-class) requirement that the native runtime cannot satisfy
- AgentScope's permissions / sandbox / MCP trajectory stalls relative to alternatives
- the organization standardizes on the Azure / `.NET` stack, changing the Microsoft Agent Framework fit calculation

## Sources

- AgentScope repository and runtime site (production-ready framing, runtime sandbox, Docker/K8s deployment)
- 2026 production-framework comparisons citing LangGraph durable execution and HITL leadership, and the checkpointing-vs-durable-execution nuance
- Microsoft Agent Framework `1.0 GA` (April 2026) announcement and documentation
