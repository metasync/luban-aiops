from __future__ import annotations

from uuid import uuid4

from agent_service.core.telemetry import current_trace_id


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
