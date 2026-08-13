---
kind: design
name: Introduce a Tool Gateway with registry-based read-only tool execution
source: session
category: adr
---

# Introduce a Tool Gateway with registry-based read-only tool execution

_Source: coding plans from commit period 84f91db → d541fdd — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
The AgentScope LLM kernel could chat but had no way to act on infrastructure. Direct K8s calls from the agent service would bypass policy enforcement, lack structured evidence, and couple the agent platform to Kubernetes internals.

## Decision drivers
- policy enforcement at execution time
- structured audit evidence
- tool abstraction for future write operations
- separation of concerns between agent runtime and infrastructure access

## Considered options
- **Direct K8s client in agent service** _(rejected)_ — pros: simplest path, no new service; cons: bypasses existing policy engine, no standardized evidence format, couples agent to K8s SDK, no tool catalog discovery
- **Tool gateway with registry pattern** — pros: centralized policy checks, uniform evidence envelope, discoverable tool catalog via /api/v2/tools, easy to add new tools without touching agent code; cons: adds another service boundary and HTTP hop

## Decision
Implement a dedicated tool-gateway service under src/api_gateway/tools/ with a ToolRegistry, BaseTool ABC, and kubernetes-client connector exposing GET /api/v2/tools and POST /api/v2/tools/invoke. The agent-platform registers these as Toolkit functions that forward calls over HTTP when TOOL_GATEWAY_URL is configured.

## Consequences
Adds a new service boundary (tool-gateway) and an HTTP round-trip per tool invocation. Gains centralized policy enforcement via `tools:invoke` action, standardized `tool-invocation.schema.json` / `tool-result.schema.json` contracts, and a clean extension point for future write tools. Read-only tools are auto-allowed for operator/admin roles; namespace-scoped RBAC limits blast radius.