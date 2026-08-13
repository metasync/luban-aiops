---
kind: design
name: Inject deterministic NO_TOOLS_NOTICE when no operational tools are available
source: session
category: adr
---

# Inject deterministic NO_TOOLS_NOTICE when no operational tools are available

_Source: coding plans from commit period 4b8700e → 663274c — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
Even with the anti-fabrication system prompt deployed, the model still fabricated infrastructure data when the toolkit was empty — a system prompt is only a probabilistic hint and cannot override the model's helpfulness bias without real grounding data. Relying solely on prompts proved insufficient to prevent hallucinated operational reports.

## Decision drivers
- deterministic safety guarantee against hallucination
- defense-in-depth for transient gateway failures
- no reliance on model obedience

## Considered options
- **Code-injected NO_TOOLS_NOTICE prepended to turn content** — pros: fires exactly when zero function tools are detected via `get_tool_schemas()`; forces the model to state tooling is unavailable instead of inventing data; works regardless of gateway-down / no-token / discovery-failure states
- **Rely on system prompt alone** _(rejected)_ — pros: no code changes needed; cons: proven unreliable; model can ignore instructions when no real tools exist

## Decision
In `stream_prompt`, after building the request toolkit, count real function tools via `await request_toolkit.get_tool_schemas()`. If a gateway is configured but zero tools are available, prepend a deterministic `NO_TOOLS_NOTICE` constant to the turn content instructing the agent that tooling is unavailable and it MUST NOT report live infrastructure data.

## Consequences
Provides a hard fail-safe against hallucinated operational reports during outages. Once the toolkit fix lands, the normal path has tools so this notice only fires in failure modes. Adds a small constant and one extra schema check in the prompt-building path.