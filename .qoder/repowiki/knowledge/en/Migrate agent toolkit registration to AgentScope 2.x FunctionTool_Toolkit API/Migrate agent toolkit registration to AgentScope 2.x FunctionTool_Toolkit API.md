---
kind: design
name: Migrate agent toolkit registration to AgentScope 2.x FunctionTool/Toolkit API
source: session
category: adr
---

# Migrate agent toolkit registration to AgentScope 2.x FunctionTool/Toolkit API

_Source: coding plans from commit period 0b20258 → d0bd19f — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
After a policy fix enabled the read-only-observer to discover four K8s tools, agent-platform failed to register them with `failed to register tool k8s.list_pods: 'Toolkit' object has no attribute 'add'`. The installed AgentScope 2.0.4.post1 no longer supports `Toolkit().add(fn)`; tools must be passed at construction via `Toolkit(tools=[FunctionTool(...)])`. An empty toolkit caused the LLM to fabricate operational reports and prevented `tool_call`/`tool_result` events from reaching the evidence panel.

## Decision drivers
- compatibility with AgentScope 2.x runtime
- reliable function-calling schema propagation to the LLM
- preserving existing per-request toolkit monkeypatch contract

## Considered options
- **AgentScope 2.x `FunctionTool` + `Toolkit(tools=...)`** — pros: matches installed runtime; exposes correct schemas via `get_tool_schemas()`; enables proper tool calling and evidence-panel events
- **Downgrade AgentScope to pre-2.x API** _(rejected)_ — pros: keeps existing `.add()` loop unchanged; cons: introduces dependency regression risk; not aligned with platform's pinned version

## Decision
Rewrite `gateway_tools.py` to build `list[FunctionTool]` (with names sanitized, descriptions set, `is_read_only` derived from `risk_level`, and `input_schema` threaded from the gateway's `parameters_schema`) and construct the toolkit as `Toolkit(tools=...)`. Update `_build_request_toolkit` in `runtime_kernel.py` to call the new builder instead of looping over `Toolkit().add()`. Keep the `build_toolkit` signature for test monkeypatching.

## Consequences
Tools are now correctly registered and the LLM receives accurate function schemas, eliminating fabricated answers and restoring evidence-panel `tool_call`/`tool_result` cards. Per-request toolkit override remains compatible with existing tests. A fallback path is noted: if e2e shows the agent still sees no tools, pass the request toolkit at agent construction time.