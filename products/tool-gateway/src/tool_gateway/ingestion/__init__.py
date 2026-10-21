"""MCP-ingestion subpackage (SPEC-069 R-2).

Holds the **generic, server-agnostic** MCP-ingestion adapter
(:mod:`~tool_gateway.ingestion.mcp_adapter`) plus per-target **bindings** that
supply the admitted-tool allowlist and gateway-owned schemas/tiers as
configuration — the Ansible read-only binding
(:mod:`~tool_gateway.ingestion.ansible_binding`) and its native
``ansible-inventory`` fallback (:mod:`~tool_gateway.ingestion.ansible_native`).

The adapter is the piece the Layer-2 runbook-tool fast-follow later reuses by
supplying its own binding config, not by rebuilding the adapter. SPEC-067
(ServiceNow) takes the **native REST** path instead — the OQ-3 fallback chosen
at Stage-0 2026-10-19, because its PDI exposes no ServiceNow MCP server — via
:mod:`~tool_gateway.ingestion.servicenow_native` (a Table-API connector on the
same SPEC-007 ``BaseTool`` seam) and its gateway-owned read-tool allowlist
:mod:`~tool_gateway.ingestion.servicenow_binding`.
"""
