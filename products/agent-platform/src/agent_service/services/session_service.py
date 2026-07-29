from __future__ import annotations

from fastapi import HTTPException

from agent_service.core.metrics import record_session_created
from agent_service.schemas.api import SessionRecord
from agent_service.services.session_store import SESSION_STORE


def _assert_session_owner(session: SessionRecord, user_id: str | None) -> None:
    # 404 instead of 403 so foreign session IDs are indistinguishable from
    # unknown ones.
    if session.user_id and user_id and session.user_id != user_id:
        raise HTTPException(status_code=404, detail="session not found")


def create_session(user_id: str | None) -> SessionRecord:
    record_session_created()
    return SESSION_STORE.create_session(user_id)


def ensure_session(session_id: str | None, user_id: str | None) -> SessionRecord:
    if session_id is None:
        record_session_created()
        return SESSION_STORE.create_session(user_id)
    session = SESSION_STORE.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    _assert_session_owner(session, user_id)
    return session


def get_session(session_id: str, user_id: str | None = None) -> SessionRecord:
    session = SESSION_STORE.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    _assert_session_owner(session, user_id)
    return session
