from fastapi import HTTPException
from fastapi.testclient import TestClient

from agent_service.app import create_app
from agent_service.services import session_service
from agent_service.services.session_store import InMemorySessionStore


def test_create_and_get_session_round_trip(monkeypatch):
    monkeypatch.setattr(session_service, "SESSION_STORE", InMemorySessionStore())

    created = session_service.create_session("alice")
    fetched = session_service.get_session(created.session_id)

    assert fetched.session_id == created.session_id
    assert fetched.user_id == "alice"


def test_get_session_raises_for_missing_session(monkeypatch):
    monkeypatch.setattr(session_service, "SESSION_STORE", InMemorySessionStore())

    try:
        session_service.get_session("missing-session")
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail == "session not found"
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Missing session should raise HTTPException")


def test_ensure_session_rejects_unknown_client_supplied_id(monkeypatch):
    monkeypatch.setattr(session_service, "SESSION_STORE", InMemorySessionStore())

    try:
        session_service.ensure_session("ses-attacker-chosen", "alice")
    except HTTPException as exc:
        assert exc.status_code == 404
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Unknown session_id must not be silently adopted")


def test_session_is_not_readable_by_another_user(monkeypatch):
    monkeypatch.setattr(session_service, "SESSION_STORE", InMemorySessionStore())

    created = session_service.create_session("alice")

    try:
        session_service.get_session(created.session_id, "bob")
    except HTTPException as exc:
        assert exc.status_code == 404
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Foreign sessions must not be readable")

    try:
        session_service.ensure_session(created.session_id, "bob")
    except HTTPException as exc:
        assert exc.status_code == 404
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Foreign sessions must not be continuable")

    fetched = session_service.get_session(created.session_id, "alice")
    assert fetched.session_id == created.session_id


def test_session_store_evicts_expired_sessions(monkeypatch):
    from agent_service.services import session_store as store_module

    clock = {"now": 100.0}
    monkeypatch.setattr(store_module.time, "monotonic", lambda: clock["now"])

    store = InMemorySessionStore(ttl_seconds=10.0)
    record = store.create_session("alice")

    clock["now"] = 105.0
    assert store.get_session(record.session_id) is not None

    clock["now"] = 120.0
    assert store.get_session(record.session_id) is None
    assert len(store) == 0


def test_session_store_enforces_max_entries():
    store = InMemorySessionStore(max_entries=2)

    first = store.create_session("alice")
    second = store.create_session("alice")
    third = store.create_session("alice")

    assert len(store) == 2
    assert store.get_session(first.session_id) is None
    assert store.get_session(second.session_id) is not None
    assert store.get_session(third.session_id) is not None


def test_session_store_reads_env_configuration(monkeypatch):
    monkeypatch.setenv("SESSION_TTL_SECONDS", "120")
    monkeypatch.setenv("SESSION_MAX_ENTRIES", "5")

    from agent_service.services.session_store import build_session_store

    monkeypatch.setenv("SESSION_STORE_BACKEND", "memory")
    store = build_session_store()

    assert isinstance(store, InMemorySessionStore)
    assert store.ttl_seconds == 120.0
    assert store.max_entries == 5


def test_session_routes_enforce_integrity():
    client = TestClient(create_app())

    unknown_chat = client.post(
        "/api/v2/chat",
        json={"message": "hello", "session_id": "ses-unknown"},
        headers={"X-User-ID": "alice"},
    )
    assert unknown_chat.status_code == 404

    created = client.post(
        "/api/v2/sessions",
        headers={"X-User-ID": "alice"},
    )
    assert created.status_code == 201
    session_id = created.json()["session_id"]

    foreign = client.get(
        f"/api/v2/sessions/{session_id}",
        headers={"X-User-ID": "bob"},
    )
    assert foreign.status_code == 404

    owner = client.get(
        f"/api/v2/sessions/{session_id}",
        headers={"X-User-ID": "alice"},
    )
    assert owner.status_code == 200
    assert owner.json()["user_id"] == "alice"
