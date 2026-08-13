---
kind: design
name: Tool execution flows through a dedicated tool-gateway with policy enforcement
source: session
category: adr
---

# Tool execution flows through a dedicated tool-gateway with policy enforcement

_Source: coding plans from commit period 23c7930 → 04b0ac9 — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
The AgentScope LLM kernel needs to invoke Kubernetes read-only tools, but direct K8s access from the agent service would bypass authorization and audit. A separate tool-gateway layer is needed to enforce policies, collect evidence, and provide a stable contract between the agent platform and infrastructure.

## Decision drivers
- policy enforcement at invocation time
- structured evidence for audit
- separation of concerns between agent orchestration and infra access
- namespace-scoped read-only access

## Considered options
- **Direct K8s client in agent service** _(rejected)_ — pros: Simpler call path, no extra service; cons: Bypasses policy engine, no centralized audit/evidence, requires embedding credentials in agent pods
- **Tool-gateway with registry pattern** — pros: Centralized policy check, structured evidence envelope, pluggable tool implementations, namespace-scoped ServiceAccount; cons: Adds network hop, requires maintaining tool registry

## Decision
Implement a tool-gateway service that exposes POST /api/v2/tools/invoke; the agent platform calls this endpoint via httpx. Tools are registered through a ToolRegistry with BaseTool ABC, and each invocation goes through the existing policy engine before hitting the K8s connector.

## Consequences
Agent platform must configure TOOL_GATEWAY_URL and register gateway tools into Toolkit(). Policy bundle gains a `tools:invoke` action scoped to operator/admin roles. K8s connector uses in-cluster config with a read-only ServiceAccount restricted to namespace-level get/list operations on pods, events, and logs.