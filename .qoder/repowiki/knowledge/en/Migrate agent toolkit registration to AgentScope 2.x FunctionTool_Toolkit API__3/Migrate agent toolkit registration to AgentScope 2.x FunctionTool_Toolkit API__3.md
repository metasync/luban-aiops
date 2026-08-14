---
kind: design
name: Migrate agent toolkit registration to AgentScope 2.x FunctionTool/Toolkit API
source: session
category: adr
---

# Migrate agent toolkit registration to AgentScope 2.x FunctionTool/Toolkit API

_Source: coding plans from commit period d80c5a1 → 4b8700e — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
After the policy fix enabled `read-only-observer` to discover four K8s tools, agent-platform failed to register them because it used the deprecated `Toolkit().add(fn)` pattern. The installed AgentScope 2.0.4.post1 requires passing tools at construction via `Toolkit(tools=[FunctionTool(...)])`. An empty toolkit caused the LLM to fabricate operational results and prevented `tool_call`/`tool_result` events from reaching the evidence panel.

## Decision drivers
- compatibility with AgentScope 2.x runtime
- correct function-calling schema propagation so the model can invoke real tools
- preserving existing monkeypatch contract for tests

## Considered options
- **AgentScope 2.x `FunctionTool` + `Toolkit(tools=...)`** — pros: matches installed runtime; produces valid schemas via `get_tool_schemas()`; enables tool calls and evidence-panel events
- **Keep legacy `Toolkit().add(fn)` loop** _(rejected)_ — pros: minimal code churn; cons: AttributeError at runtime; toolkit stays empty; model hallucinates answers

## Decision
Replace `build_toolkit_functions` with `build_function_tools` that constructs `FunctionTool` objects (with sanitized names, descriptions, read-only flags, and `input_schema` sourced from the gateway's `parameters_schema`) and build a `Toolkit` by passing the list at construction. `_build_request_toolkit` in `runtime_kernel.py` now returns this new toolkit directly.

## Consequences
Tools are registered correctly and the LLM receives proper function-calling schemas, eliminating fabricated responses and restoring evidence-panel `tool_call`/`tool_result` cards. The change is scoped to `gateway_tools.py` and `runtime_kernel.py`; per-request toolkit override remains assumed to be consumed by the Agent at reply time per SPEC-011.