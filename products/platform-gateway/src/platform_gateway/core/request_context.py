from __future__ import annotations

from uuid import uuid4

from platform_gateway.core.telemetry import current_trace_id


def resolve_request_id(request_id: str | None) -> str:
    """Resolve the x-request-id correlation key (SPEC-005 R-4).

    Inbound value wins (portal contract); otherwise bridge to the active
    OTel trace_id when tracing is on, else fall back to a generated UUID.
    """
    if request_id:
        return request_id
    trace_id = current_trace_id()
    if trace_id:
        return trace_id
    return f"req-{uuid4()}"


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
