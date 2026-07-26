from __future__ import annotations

from fastapi import HTTPException

from agent_service.schemas.api import SessionRecord
from agent_service.services.session_store import SESSION_STORE


def create_session(user_id: str | None) -> SessionRecord:
    return SESSION_STORE.ensure_session(None, user_id)


def ensure_session(session_id: str | None, user_id: str | None) -> SessionRecord:
    return SESSION_STORE.ensure_session(session_id, user_id)


def get_session(session_id: str) -> SessionRecord:
    session = SESSION_STORE.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session
