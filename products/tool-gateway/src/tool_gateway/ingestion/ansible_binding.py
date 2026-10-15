"""Ansible read-only MCP binding (SPEC-069 R-2, Stage-0 items 1/2).

This is the **configuration** the generic adapter consumes for the Ansible
target — the admitted read-only tool allowlist, each tool's canonical name, its
gateway-owned JSON-Schema argument shape, and its tier. None of this comes from
the server: the chosen ``SurgeX-Labs/awx-mcp-server`` exposes a 16-tool
read-*write* surface, and the adapter admits only the six read-only capabilities
named here.

Stage-0 (2026-10-13) pinned this set. The server's **three mutating tools**
(``job_launch``, ``job_cancel``, ``project_update``) are **never** admitted at any
tier — they are simply absent from :data:`ANSIBLE_ADMITTED_TOOLS`, so the
allowlist denies them (R-2/R-3). No playbook-run/runbook-execution name and no
``--check``/dry-run operation is admitted (OQ-2/OQ-3). Four server *read* tools
(``get_job_template``, ``list_jobs``, ``job_events``, ``list_projects``) are
deliberately not admitted — no use case yet; admit later only on a named need.

One honest Stage-0 gap: the server exposes **no host ``gather_facts``/facts
tool**, so live fact gathering is deferred (a native fallback or a later server
tool) rather than faked (OQ-5 "defer, don't fake").

The exact server argument *names* are confirmed against the deployed server's
``inputSchema`` at the R-6 gated live-check (CI makes no live external call);
where a canonical parameter must be renamed, ``argument_map`` carries it as
config — never an adapter-code change.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tool_gateway.ingestion.mcp_adapter import (
    AdmittedTool,
    McpIngestionConnector,
    McpTransport,
)

if TYPE_CHECKING:
    from tool_gateway.core.config import GatewaySettings

CATEGORY = "ansible"
SOURCE_SYSTEM = "ansible"

# Server tools that MUTATE — never admitted at any tier (absent from the
# allowlist below). Tests assert no canonical tool maps to one of these.
DENIED_SERVER_TOOLS = frozenset({"job_launch", "job_cancel", "project_update"})
# Server read tools deliberately not admitted (no use case yet).
NOT_ADMITTED_SERVER_TOOLS = frozenset(
    {"get_job_template", "list_jobs", "job_events", "list_projects"}
)

_NAME_FILTER_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "name_filter": {
            "type": "string",
            "description": "Optional substring to filter results by name.",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 500,
            "description": "Maximum number of results to return (1-500).",
        },
    },
}

# The admitted read-only discovery set (Stage-0 item 2), one typed tool per
# named capability. Every entry is ``risk_level="read"`` — the gateway owns the
# tier; a server-advertised hint can never change it.
ANSIBLE_ADMITTED_TOOLS: tuple[AdmittedTool, ...] = (
    AdmittedTool(
        server_name="list_inventories",
        name="ansible.list_inventories",
        description="List Ansible inventories with optional name filtering.",
        risk_level="read",
        category=CATEGORY,
        parameters_schema=_NAME_FILTER_SCHEMA,
    ),
    AdmittedTool(
        server_name="get_inventory",
        name="ansible.get_inventory",
        description="Get one inventory's details, including its hosts and groups.",
        risk_level="read",
        category=CATEGORY,
        parameters_schema={
            "type": "object",
            "required": ["inventory"],
            "properties": {
                "inventory": {
                    "type": "string",
                    "description": "Inventory name or ID.",
                },
            },
        },
    ),
    AdmittedTool(
        server_name="list_job_templates",
        name="ansible.list_job_templates",
        description="List Ansible job templates with optional name filtering.",
        risk_level="read",
        category=CATEGORY,
        parameters_schema=_NAME_FILTER_SCHEMA,
    ),
    AdmittedTool(
        server_name="get_job",
        name="ansible.get_job",
        description="Get one job's details and current status by ID.",
        risk_level="read",
        category=CATEGORY,
        parameters_schema={
            "type": "object",
            "required": ["job_id"],
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "Job ID.",
                },
            },
        },
    ),
    AdmittedTool(
        server_name="job_stdout",
        name="ansible.get_job_stdout",
        description="Retrieve a job's stdout/log output, optionally tail-bounded.",
        risk_level="read",
        category=CATEGORY,
        parameters_schema={
            "type": "object",
            "required": ["job_id"],
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "Job ID.",
                },
                "tail": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5000,
                    "description": "Return only the last N lines (1-5000).",
                },
            },
        },
    ),
    AdmittedTool(
        server_name="env_get_active",
        name="ansible.get_environment_health",
        description=(
            "Report the active Ansible environment's health/readiness. A pure "
            "read of environment state; it launches nothing."
        ),
        risk_level="read",
        category=CATEGORY,
        parameters_schema={"type": "object", "properties": {}},
    ),
)


def build_ansible_mcp_connector(settings: "GatewaySettings") -> McpIngestionConnector:
    """Construct the generic adapter bound to the Ansible read-only config.

    The endpoint, transport, timeout, and optional credential set are operator
    configuration (never model-selected); the admitted-tool allowlist and tiers
    are the gateway-owned config above. This is the same adapter class a future
    ServiceNow binding (SPEC-067) or an AAP read-only-mode config reuses.
    """
    transport = McpTransport(
        kind=settings.ansible_mcp_transport,
        url=settings.ansible_mcp_url,
        command=settings.ansible_mcp_command,
        args=tuple(settings.ansible_mcp_args),
        timeout_ms=settings.ansible_mcp_timeout_ms,
    )
    # ``target_identity_mode`` stays at its default (``acting_service``): the
    # self-hosted dev server is addressed with the acting service's own credential
    # or a loopback session, never the requesting user's delegated identity. The
    # production ``user_delegated`` mode is SPEC-070's seam and is deliberately not
    # wired here (R-4); the audit record still names the mode so it never implies
    # target-side per-user RBAC the dev topology does not provide.
    return McpIngestionConnector(
        transport=transport,
        admitted=ANSIBLE_ADMITTED_TOOLS,
        source_system=SOURCE_SYSTEM,
        credential_set=settings.ansible_mcp_credential_set,
        credential_sets_path=settings.ansible_mcp_credential_sets_path,
    )
