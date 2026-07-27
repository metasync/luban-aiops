from __future__ import annotations

from uuid import uuid4


def resolve_request_id(request_id: str | None) -> str:
    return request_id or f"req-{uuid4()}"


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
