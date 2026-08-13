---
kind: design
name: Tool contracts defined as JSON schemas shared between agent-platform and tool-gateway
source: session
category: adr
---

# Tool contracts defined as JSON schemas shared between agent-platform and tool-gateway

_Source: coding plans from commit period 23c7930 → 04b0ac9 — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
The agent platform and tool-gateway need a stable interface for tool invocations and results so that new tools can be added without coordinating schema changes across services.

## Decision drivers
- schema evolution safety
- cross-service contract validation
- tool parameter discovery by LLM

## Considered options
- **JSON Schema files under shared-contracts** — pros: Machine-readable, validates at runtime, documents parameter structure for LLM tool descriptions; cons: Requires code generation or manual parsing
- **Python dataclasses shared via package** _(rejected)_ — pros: Type safety within Python ecosystem; cons: Tight coupling, harder to validate cross-language boundaries

## Decision
Define `tool-invocation.schema.json` and `tool-result.schema.json` under `shared/shared-contracts/schemas/`. The tool-gateway validates incoming requests against the invocation schema, and both sides serialize/deserialize using these schemas.

## Consequences
New tools must conform to the shared schemas. The result schema includes an `evidence` envelope (executed_at, duration_ms, risk_level, source_system) that every tool must populate, enabling consistent audit trails.