---
kind: external_dependency
name: AgentScope Runtime Kernel
slug: agentscope
category: external_dependency
category_hints:
    - vendor_identity
    - framework_behavior
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/agent-platform/src/agent_service/entrypoints/runtime.py
---

AgentScope is the chosen agent orchestration kernel for the platform, selected via ADR-0002 as the production-ready runtime with native permissions/sandbox, MCP support, and service exposure capabilities. The agent-platform product integrates AgentScope through its runtime kernel layer, with the gateway communicating over HTTP to AgentScope's wire protocol (/agent/, /sessions/, /chat/, SSE). The integration is designed to be swappable via a platform-owned contract (ADR-0003), allowing future framework swaps without platform-wide migrations.