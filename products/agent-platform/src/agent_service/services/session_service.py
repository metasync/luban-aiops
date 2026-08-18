from __future__ import annotations

from fastapi import HTTPException

from agent_service.core.metrics import record_session_created
from agent_service.schemas.api import SessionRecord
from agent_service.services.agent_state_store import AGENT_STATE_STORE
from agent_service.services.session_store import SESSION_STORE


def _assert_session_owner(session: SessionRecord, user_id: str | None) -> None:
    # 404 instead of 403 so foreign session IDs are indistinguishable from
    # unknown ones.
    if session.user_id and user_id and session.user_id != user_id:
        raise HTTPException(status_code=404, detail="session not found")


def create_session(user_id: str | None) -> SessionRecord:
    record_session_created()
    return SESSION_STORE.create_session(user_id)


def create_named_session(session_id: str, user_id: str | None) -> SessionRecord:
    """Get-or-create a caller-supplied dedicated session (SPEC-015 R-3).

    Idempotent for the owning user so re-triage of an incident reuses the
    same session; a foreign owner is indistinguishable from an unknown id.
    The post-create re-read resolves the check-then-create race (Redis
    last-writer-wins) by surfacing a lost race as 404 instead of letting
    two owners share one session.
    """
    existing = SESSION_STORE.get_session(session_id)
    if existing is not None:
        _assert_session_owner(existing, user_id)
        return existing
    record_session_created()
    record = SESSION_STORE.create_session(user_id, session_id=session_id)
    stored = SESSION_STORE.get_session(session_id)
    if stored is None:
        return record
    _assert_session_owner(stored, user_id)
    return stored


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


def delete_session(session_id: str, user_id: str | None = None) -> bool:
    """Delete a session and its persisted agent state (SPEC-017 R-3).

    State cleanup follows session deletion so a deleted session never
    leaves a durable conversation snapshot behind; a state-store failure
    does not fail the session delete (fail-open).
    """
    session = SESSION_STORE.get_session(session_id)
    if session is None:
        return False
    _assert_session_owner(session, user_id)
    deleted = SESSION_STORE.delete_session(session_id)
    if deleted:
        try:
            AGENT_STATE_STORE.delete_state(session_id)
        except Exception:
            # Durability cleanup is best-effort; the session is gone.
            pass
    return deleted
