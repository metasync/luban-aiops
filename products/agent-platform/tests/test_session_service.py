from fastapi import HTTPException

from agent_service.services import session_service
from agent_service.services.session_store import SessionStore


def test_create_and_get_session_round_trip(monkeypatch):
    monkeypatch.setattr(session_service, "SESSION_STORE", SessionStore())

    created = session_service.create_session("alice")
    fetched = session_service.get_session(created.session_id)

    assert fetched.session_id == created.session_id
    assert fetched.user_id == "alice"


def test_get_session_raises_for_missing_session(monkeypatch):
    monkeypatch.setattr(session_service, "SESSION_STORE", SessionStore())

    try:
        session_service.get_session("missing-session")
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail == "session not found"
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Missing session should raise HTTPException")
