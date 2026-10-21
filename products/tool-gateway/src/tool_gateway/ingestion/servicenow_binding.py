"""ServiceNow read-only Table-API binding (SPEC-067 R-2, OQ-4).

This is the **configuration** the native REST connector consumes for the
ServiceNow target — the admitted read-only tool allowlist, each tool's canonical
name, its fixed table, its allowlisted field projection, its gateway-owned
JSON-Schema argument shape, and its tier. None of it comes from the target: the
gateway owns admission, projection, and tier, and nothing a ServiceNow instance
advertises can widen them.

**The six admitted read tools (OQ-4, resolved 2026-10-20).** ``change_request``
is first-class (kept **in scope** by operator amendment, both ``.list`` and
``.get``); only **attachments** (``/attachment/{sys_id}/file`` — a
binary/exfiltration surface) and **``problem``** are deferred to a fast-follow
and are therefore absent here, so the allowlist denies them by absence. Every
entry is ``risk_level="read"`` — the gateway owns the tier.

**Field projection is a safety allowlist, not a convenience.** Each tool names
the exact columns it may return; the connector projects every record down to
that set *after* the response arrives (and asks for it via ``sysparm_fields``),
so a column we did not enumerate can never reach a result. The ``sys_user``
allowlist deliberately omits ``password``/``user_password`` and every other
secret-bearing column — a user read returns identity/contact/profile fields
only.

**Bounds (OQ-4's "bounded argument schema").** The table is fixed per tool
(never a model argument); a ``get`` requires a validated 32-char hex ``sys_id``;
a ``list`` accepts only an optional ``limit`` clamped into
``[1, MAX_LIMIT]``. No free-form ``sysparm_query`` is admitted — an unbounded
filter string is an injection surface with no approved use case yet; admit one
later only on a named need, as bounded config.

The concrete field allowlists and argument names are confirmed against the real
Table API at the documented gated live-PDI operator check (OQ-5); CI validates
against a **local mock Table-API responder** and makes no live external call.
Where a column must be renamed or added, it is edited here as config — never an
adapter-code change.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tool_gateway.ingestion.servicenow_native import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    ServiceNowNativeConnector,
    ServiceNowReadTool,
)

if TYPE_CHECKING:
    from tool_gateway.core.config import GatewaySettings

CATEGORY = "servicenow"
SOURCE_SYSTEM = "servicenow"

# Field-projection allowlists (gateway-owned). Secret-bearing columns are
# excluded by omission — most critically every ``sys_user`` credential column.
_INCIDENT_FIELDS = (
    "sys_id", "number", "short_description", "state", "priority", "severity",
    "impact", "urgency", "category", "assignment_group", "assigned_to",
    "opened_at", "updated_at", "closed_at", "cmdb_ci",
)
_CHANGE_REQUEST_FIELDS = (
    "sys_id", "number", "short_description", "state", "type", "priority",
    "risk", "impact", "start_date", "end_date", "requested_by",
    "assignment_group", "cmdb_ci",
)
# NEVER includes ``password`` / ``user_password`` or any credential column.
_USER_FIELDS = (
    "sys_id", "user_name", "name", "email", "title", "department", "active",
    "manager",
)
_CMDB_CI_FIELDS = (
    "sys_id", "name", "sys_class_name", "ci_class_id", "operational_status",
    "install_status", "ip_address", "mac_address", "support_group",
    "assigned_to",
)

_LIST_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_LIMIT,
            "default": DEFAULT_LIMIT,
            "description": (
                f"Maximum number of records to return (1-{MAX_LIMIT}; "
                f"default {DEFAULT_LIMIT})."
            ),
        },
    },
}

_GET_SCHEMA: dict = {
    "type": "object",
    "required": ["sys_id"],
    "properties": {
        "sys_id": {
            "type": "string",
            # Formal mirror of the connector's _SYS_ID_RE (servicenow_native.py)
            # so a model constructing args sees the same bound the gateway
            # enforces pre-transport; enforcement never relies on this hint.
            "pattern": "^[0-9a-fA-F]{32}$",
            "description": "The 32-character hex sys_id of the record to fetch.",
        },
    },
}

# The admitted read-only set (OQ-4), one typed tool per named capability.
SERVICENOW_ADMITTED_TOOLS: tuple[ServiceNowReadTool, ...] = (
    ServiceNowReadTool(
        name="servicenow.incident.list",
        table="incident",
        op="list",
        description=(
            "List ServiceNow incidents (newest first, bounded by 'limit'), "
            "projected to triage fields only."
        ),
        fields=_INCIDENT_FIELDS,
        parameters_schema=_LIST_SCHEMA,
    ),
    ServiceNowReadTool(
        name="servicenow.incident.get",
        table="incident",
        op="get",
        description="Get one ServiceNow incident by sys_id, projected to triage fields only.",
        fields=_INCIDENT_FIELDS,
        parameters_schema=_GET_SCHEMA,
    ),
    ServiceNowReadTool(
        name="servicenow.change_request.list",
        table="change_request",
        op="list",
        description=(
            "List ServiceNow change requests (bounded by 'limit'), projected to "
            "change-review fields only."
        ),
        fields=_CHANGE_REQUEST_FIELDS,
        parameters_schema=_LIST_SCHEMA,
    ),
    ServiceNowReadTool(
        name="servicenow.change_request.get",
        table="change_request",
        op="get",
        description=(
            "Get one ServiceNow change request by sys_id, projected to "
            "change-review fields only."
        ),
        fields=_CHANGE_REQUEST_FIELDS,
        parameters_schema=_GET_SCHEMA,
    ),
    ServiceNowReadTool(
        name="servicenow.user.get",
        table="sys_user",
        op="get",
        description=(
            "Get one ServiceNow user by sys_id, projected to identity/contact "
            "profile fields only (never a credential column)."
        ),
        fields=_USER_FIELDS,
        parameters_schema=_GET_SCHEMA,
    ),
    ServiceNowReadTool(
        name="servicenow.cmdb_ci.get",
        table="cmdb_ci",
        op="get",
        description=(
            "Get one ServiceNow CMDB configuration item by sys_id, projected to "
            "asset/operational fields only."
        ),
        fields=_CMDB_CI_FIELDS,
        parameters_schema=_GET_SCHEMA,
    ),
)


def build_servicenow_connector(
    settings: "GatewaySettings",
    transport: object | None = None,
) -> ServiceNowNativeConnector:
    """Construct the native REST connector bound to the ServiceNow read config.

    The base URL, credential set, and timeout are operator configuration (never
    model-selected); the admitted-tool allowlist, tables, field projections, and
    tiers are the gateway-owned config above. ``transport`` is the test seam (an
    ``httpx.MockTransport``); production passes nothing and uses httpx's default.
    """
    return ServiceNowNativeConnector(
        base_url=settings.servicenow_base_url,
        admitted=SERVICENOW_ADMITTED_TOOLS,
        credential_set=settings.servicenow_credential_set,
        credential_sets_path=settings.servicenow_credential_sets_path,
        timeout_ms=settings.servicenow_timeout_ms,
        transport=transport,  # type: ignore[arg-type]
    )
