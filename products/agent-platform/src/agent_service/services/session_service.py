from __future__ import annotations

import logging

from fastapi import HTTPException

from agent_service.core.metrics import record_session_created
from agent_service.schemas.api import SessionRecord
from agent_service.services.agent_state_store import AGENT_STATE_STORE
from agent_service.services.evidence_store import EVIDENCE_STORE
from agent_service.services.session_store import SESSION_STORE

LOGGER = logging.getLogger(__name__)

# SPEC-022 R-1: workspace list cap and title minting bounds.
SESSION_LIST_CAP = 50
SESSION_TITLE_MAX_LENGTH = 80


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


def list_sessions(user_id: str) -> list[SessionRecord]:
    """The caller's sessions, most-recently-active first (SPEC-022 R-1).

    Backends that cannot order server-side (memory, Redis) are sorted here;
    the Postgres backend already returns the capped, ordered window.
    """
    records = SESSION_STORE.list_sessions_by_user(user_id)
    records.sort(
        key=lambda record: record.last_active_at or record.created_at,
        reverse=True,
    )
    return records[:SESSION_LIST_CAP]


def mark_session_turn(session_id: str, message: str) -> None:
    """Workspace bookkeeping at chat-turn start (SPEC-022 R-1).

    Mints the title from the first user turn (80-char cap, never rewritten)
    and refreshes ``last_active_at``. Both are fail-open: bookkeeping never
    fails a turn.
    """
    title = " ".join(message.split())[:SESSION_TITLE_MAX_LENGTH]
    try:
        if title:
            SESSION_STORE.set_session_title(session_id, title)
        SESSION_STORE.touch_session(session_id)
    except Exception as exc:
        LOGGER.warning(
            "session workspace bookkeeping failed for %s: %s", session_id, exc
        )


def pin_session_model(session_id: str, model: str | None) -> None:
    """Pin the model that resolved for a turn (SPEC-024 R-3, Q-4).

    The newest resolved selection wins (unlike the set-once title). Like
    all workspace bookkeeping this is fail-open: a store failure degrades
    affinity, never the turn.
    """
    if not model:
        return
    try:
        SESSION_STORE.set_session_model(session_id, model)
    except Exception as exc:
        LOGGER.warning(
            "session model pinning failed for %s: %s", session_id, exc
        )


def delete_session(session_id: str, user_id: str | None = None) -> bool:
    """Delete a session and its persisted agent state (SPEC-017 R-3).

    State cleanup follows session deletion so a deleted session never
    leaves a durable conversation snapshot behind; a state-store failure
    does not fail the session delete (fail-open). Stored tool evidence
    cascades with the session for the same reason (SPEC-025 R-2).
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
        try:
            EVIDENCE_STORE.delete_session(session_id)
        except Exception:
            # Evidence cleanup is best-effort; the session is gone.
            pass
    return deleted
