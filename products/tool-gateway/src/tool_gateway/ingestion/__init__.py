"""MCP-ingestion subpackage (SPEC-069 R-2).

Holds the **generic, server-agnostic** MCP-ingestion adapter
(:mod:`~tool_gateway.ingestion.mcp_adapter`) plus per-target **bindings** that
supply the admitted-tool allowlist and gateway-owned schemas/tiers as
configuration — the Ansible read-only binding
(:mod:`~tool_gateway.ingestion.ansible_binding`) and its native
``ansible-inventory`` fallback (:mod:`~tool_gateway.ingestion.ansible_native`).

The adapter is the piece SPEC-067 (ServiceNow) and the Layer-2 runbook-tool
fast-follow later reuse by supplying their own binding config, not by rebuilding
the adapter.
"""
