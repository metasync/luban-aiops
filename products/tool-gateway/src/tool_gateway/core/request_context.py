from __future__ import annotations

import re
from uuid import uuid4

from tool_gateway.core.telemetry import current_trace_id


def resolve_request_id(request_id: str | None) -> str:
    """Resolve the x-request-id correlation key (SPEC-005 R-4).

    Inbound value wins (portal contract); otherwise bridge to the active
    OTel trace_id when tracing is on, else fall back to a generated UUID.
    """
    if isinstance(request_id, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", request_id):
        return request_id
    trace_id = current_trace_id()
    if trace_id:
        return trace_id
    return f"req-{uuid4()}"


def execution_correlation(value: str | None) -> dict[str, str]:
    """Bounded audit metadata only; never injected into connector identity."""
    if isinstance(value, str) and re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", value
    ):
        return {"execution_id": value}
    return {}


def resolve_user_id(
    default_user_id: str,
    explicit_user_id: str | None = None,
    header_user_id: str | None = None,
    authenticated_user_id: str | None = None,
) -> str:
    if authenticated_user_id:
        return authenticated_user_id
    if explicit_user_id:
        return explicit_user_id
    if header_user_id:
        return header_user_id
    return default_user_id
