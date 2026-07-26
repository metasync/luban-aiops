from __future__ import annotations

from uuid import uuid4


def resolve_request_id(request_id: str | None) -> str:
    return request_id or f"req-{uuid4()}"
