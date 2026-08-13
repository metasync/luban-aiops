---
kind: design
name: Inject deterministic NO_TOOLS_NOTICE when no operational tools are available
source: session
category: adr
---

# Inject deterministic NO_TOOLS_NOTICE when no operational tools are available

_Source: coding plans from commit period d80c5a1 → 4b8700e — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
Even with an anti-fabrication system prompt active, the model still produced fabricated operational data when the toolkit was empty — a system prompt alone is probabilistic and cannot guarantee behavior under help bias. A structural guardrail is needed for cases where the tool gateway is down, missing a token, or discovery fails.

## Decision drivers
- deterministic safety against hallucinated infrastructure reports
- defense-in-depth beyond system prompts
- only activate when risk exists (gateway configured but zero tools)

## Considered options
- **Code-injected `NO_TOOLS_NOTICE` turn content in `stream_prompt`** — pros: fires exactly when `await request_toolkit.get_tool_schemas()` yields zero functions; forces the model to state tooling is unavailable instead of inventing metrics
- **Rely solely on the anti-fabrication system prompt** _(rejected)_ — pros: no extra code; cons: proven unreliable — model still hallucinated when toolkit was empty

## Decision
In `stream_prompt`, after building the request toolkit, count real tools via `get_tool_schemas()` filtered to `type == 'function'`. If a gateway is configured but zero tools are available, prepend the `NO_TOOLS_NOTICE` constant to the turn content instructing the agent that tooling is unavailable and it must not report live infrastructure data.

## Consequences
Provides a deterministic fallback that prevents hallucinated operational reports during gateway outages, missing tokens, or discovery failures. Once the toolkit fix lands, normal requests have tools and the notice path is bypassed.