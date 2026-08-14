---
kind: design
name: Inject deterministic NO_TOOLS_NOTICE when gateway provides zero functional tools
source: session
category: adr
---

# Inject deterministic NO_TOOLS_NOTICE when gateway provides zero functional tools

_Source: coding plans from commit period 0b20258 → d0bd19f — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
Even with an anti-fabrication system prompt deployed, the model still hallucinated operational data when the toolkit was empty — a system prompt is only a probabilistic hint and cannot reliably suppress helpfulness bias without real tool data. The root cause was the broken toolkit registration, but a structural guard is needed for cases where the gateway is down, missing a token, or discovery fails.

## Decision drivers
- prevent hallucinated infrastructure data
- make failure mode observable to users
- defense-in-depth beyond prompt engineering

## Considered options
- **Code-injected `NO_TOOLS_NOTICE` turn content** — pros: fires exactly when `await request_toolkit.get_tool_schemas()` yields zero functions; does not rely on the model obeying a standing instruction; user-visible explanation of unavailability
- **Rely solely on the anti-fabrication system prompt** _(rejected)_ — pros: no code change; cons: proven insufficient — the model still fabricated when no tools were available

## Decision
In `stream_prompt`, after building the request toolkit, count real tools via `await request_toolkit.get_tool_schemas()` filtered to `type == "function"`. If a gateway is configured but zero tools are available, prepend a constant `NO_TOOLS_NOTICE` to the turn content instructing the agent that tooling is unavailable and it MUST NOT report live infrastructure data.

## Consequences
When the tool gateway is unreachable or misconfigured, the agent explicitly states tooling is unavailable rather than inventing metrics. This is a one-time guardrail that becomes dormant once the toolkit registration fix restores normal tool availability.