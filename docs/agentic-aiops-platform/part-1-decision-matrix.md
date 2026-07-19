# Part 1: Framework Decision Matrix

## Objective

Select the best foundation for an enterprise-grade agentic AIOps platform for IT operations with the following characteristics:

- enterprise-first security and governance
- large-public or frontier LLMs used mainly for planning
- smaller and more trusted models used for execution and tool calling
- on-prem or private access to enterprise systems and infrastructure
- integration with observability and operations tools such as Elastic or ITRS
- support for MCP and likely A2A
- Kubernetes-native deployment
- web chat UI with streaming and human approval for risky actions
- Git-managed Markdown skills maintained by operations teams

## Candidate Frameworks

- `AgentScope 2.0`
- `LangGraph`
- `Microsoft Agent Framework`

## Evaluation Notes

This is not a general-purpose framework ranking. The scoring is specific to the target platform above.

The key design assumption behind this comparison is:

- use a stronger planning model for decomposition, reasoning, summarization, and coordination
- use smaller or local models in the trusted environment for execution, tool use, and access to enterprise resources

## Revised Scoring Model

The comparison uses a `1-5` score for each dimension, where a higher score means better fit for the intended platform.

### Weighted Criteria

- `Security / permission model` — `18`
- `Stateful orchestration / reliability` — `14`
- `Human-in-the-loop / approvals` — `10`
- `MCP / A2A / interoperability` — `11`
- `API gateway / service exposure readiness` — `10`
- `Kubernetes / distributed deployment fit` — `9`
- `Streaming UI / event model` — `7`
- `Knowledge / RAG / skills integration` — `7`
- `Hybrid / on-prem model topology fit` — `7`
- `Developer ergonomics / extensibility` — `7`

### API Gateway Criterion

`API gateway / service exposure readiness` was added as an explicit criterion because the selected runtime or orchestration layer should be consumable by other applications and services without requiring a separate custom adapter layer.

This criterion measures:

- native HTTP or service exposure
- standard protocol support
- how easily the runtime can sit behind an enterprise API gateway
- how much custom wrapper code would be needed before applying gateway controls

This criterion does not mean the framework replaces a real API gateway. A real gateway is still recommended for:

- authentication and authorization
- rate limiting and quotas
- request validation
- API versioning
- traffic policy and audit controls

## Raw Scores

### AgentScope 2.0

- `Security / permissions` — `5`
- `Stateful orchestration / reliability` — `4`
- `Human-in-the-loop / approvals` — `5`
- `MCP / A2A / interoperability` — `5`
- `API gateway / service exposure readiness` — `5`
- `Kubernetes / distributed fit` — `4`
- `Streaming UI / event model` — `5`
- `Knowledge / RAG / skills integration` — `4`
- `Hybrid / on-prem fit` — `4`
- `Developer ergonomics / extensibility` — `4`

### LangGraph

- `Security / permissions` — `3`
- `Stateful orchestration / reliability` — `5`
- `Human-in-the-loop / approvals` — `5`
- `MCP / A2A / interoperability` — `3`
- `API gateway / service exposure readiness` — `4`
- `Kubernetes / distributed fit` — `5`
- `Streaming UI / event model` — `4`
- `Knowledge / RAG / skills integration` — `3`
- `Hybrid / on-prem fit` — `5`
- `Developer ergonomics / extensibility` — `4`

### Microsoft Agent Framework

- `Security / permissions` — `4`
- `Stateful orchestration / reliability` — `4`
- `Human-in-the-loop / approvals` — `4`
- `MCP / A2A / interoperability` — `4`
- `API gateway / service exposure readiness` — `5`
- `Kubernetes / distributed fit` — `3`
- `Streaming UI / event model` — `4`
- `Knowledge / RAG / skills integration` — `3`
- `Hybrid / on-prem fit` — `3`
- `Developer ergonomics / extensibility` — `3`

## Weighted Results

- `1. AgentScope 2.0` — `91.2 / 100`
- `2. LangGraph` — `80.8 / 100`
- `3. Microsoft Agent Framework` — `76.0 / 100`

## Decision Summary

### Winner

- `AgentScope 2.0`

### Runner-Up

- `LangGraph`

### Third Place

- `Microsoft Agent Framework`

## Why AgentScope 2.0 Wins

AgentScope 2.0 is the best overall fit for the target platform because it provides the most balanced alignment across runtime orchestration, permissions, streaming UX support, protocol openness, and service exposure.

Main reasons:

- strong native alignment with `bounded autonomy`
- explicit focus on permissions and user confirmation
- good fit for a streaming `web chat + approval` experience
- better overlap with `MCP` and `A2A` oriented connectivity goals
- suitable starting point for controlled agentic execution in enterprise settings
- good service exposure story for putting the runtime directly behind an enterprise API gateway

## Why LangGraph Comes Second

LangGraph remains the strongest alternative if the platform later prioritizes deterministic orchestration and graph-level control above framework-native runtime features.

Main strengths:

- best-in-class stateful orchestration model
- strong checkpointing, persistence, and resume behavior
- excellent human pause and resume patterns
- very good Kubernetes and long-running workflow fit

Main weakness for this use case:

- more platform work would likely be required around permissions, sandboxing, and runtime governance

## Why Microsoft Agent Framework Comes Third

Microsoft Agent Framework has real strengths, especially in workflow patterns, service exposure, observability, and enterprise hosting.

Main strengths:

- good workflow orchestration patterns
- strong hosting and endpoint exposure options
- strong Microsoft ecosystem alignment
- good support for approvals and OpenAI-compatible endpoints

Main weakness for this use case:

- less natural fit for a provider-flexible, Kubernetes-first, on-prem-friendly control plane unless the organization is already strongly aligned to Azure, .NET, Entra, and Foundry

## Architectural Implications

The result of Part 1 does not mean the selected framework should be treated as the full platform.

The expected platform shape still includes:

- `agent orchestration/runtime layer`
- `policy and approval layer`
- `tool gateway`
- `isolated execution workers`
- `knowledge and skills layer`
- `API gateway`
- `web chat UI`

The runtime should expose stable endpoints, but enterprise gateway capabilities should still be handled by a proper API gateway in front of it.

## Final Recommendation

Use `AgentScope 2.0` as the primary orchestration and runtime kernel for the proposed agentic AIOps platform.

Also carry forward the following design rules:

- keep planner and executor responsibilities separated
- avoid giving high-privilege execution rights directly to the planning model
- enforce human approval for risky actions
- put a real API gateway in front of the runtime
- maintain explicit control boundaries between orchestration, policy, and execution

## Next Step

Part 2 will define the reference architecture based on `AgentScope 2.0`.
