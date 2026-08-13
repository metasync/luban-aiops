---
kind: design
name: Migrate agent toolkit registration to AgentScope 2.x FunctionTool/Toolkit API
source: session
category: adr
---

# Migrate agent toolkit registration to AgentScope 2.x FunctionTool/Toolkit API

_Source: coding plans from commit period 4b8700e → 663274c — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
After a policy change enabled the read-only-observer to discover K8s tools, agent-platform failed at runtime with `'Toolkit' object has no attribute 'add'`. The installed AgentScope 2.0.4.post1 requires tools to be passed at construction via `Toolkit(tools=[FunctionTool(...)])` instead of calling `.add()` on an empty Toolkit. An empty toolkit caused the LLM to fabricate operational reports and prevented `tool_call`/`tool_result` events from reaching the evidence panel.

## Decision drivers
- compatibility with AgentScope 2.x API
- correct function-calling schema generation for tool parameters
- reliability of tool invocation in production

## Considered options
- **AgentScope 2.x FunctionTool + Toolkit(tools=...) constructor** — pros: matches installed AgentScope version; produces correct schemas via `get_tool_schemas()`; preserves existing `_make_tool_fn` behavior for token binding and tracing
- **Keep legacy `Toolkit().add(fn)` loop** _(rejected)_ — pros: minimal code churn; cons: incompatible with AgentScope 2.x; results in empty toolkit and model hallucination

## Decision
Replace `build_toolkit_functions` with `build_function_tools` that constructs `FunctionTool` instances per tool definition (sanitizing names, setting `input_schema` from the gateway's `parameters_schema`, marking read-only by risk level) and return them via `Toolkit(tools=...)`. Update `_build_request_toolkit` to call the new builder and preserve the async `build_toolkit` signature used by tests.

## Consequences
Tools now register correctly and expose proper JSON schemas to the LLM, enabling real `tool_call`/`tool_result` events in the evidence panel. Tests must assert against `get_tool_schemas()` rather than internal closures. A separate deterministic `NO_TOOLS_NOTICE` guardrail was added as defense-in-depth for cases where the gateway is unreachable or discovery fails.