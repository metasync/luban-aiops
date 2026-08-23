from fastapi import HTTPException
from fastapi.testclient import TestClient

from agent_service.app import create_app
from agent_service.services import session_service
from agent_service.services.agent_state_store import InMemoryAgentStateStore
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


def test_create_named_session_is_idempotent_for_owner(monkeypatch):
    monkeypatch.setattr(session_service, "SESSION_STORE", InMemorySessionStore())

    created = session_service.create_named_session("incident-inc-aaa111", "alice")
    assert created.session_id == "incident-inc-aaa111"
    assert created.user_id == "alice"

    again = session_service.create_named_session("incident-inc-aaa111", "alice")
    assert again.session_id == "incident-inc-aaa111"


def test_create_named_session_hides_foreign_owner(monkeypatch):
    monkeypatch.setattr(session_service, "SESSION_STORE", InMemorySessionStore())

    session_service.create_named_session("incident-inc-aaa111", "alice")

    try:
        session_service.create_named_session("incident-inc-aaa111", "bob")
    except HTTPException as exc:
        assert exc.status_code == 404
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Foreign named sessions must not be adoptable")


def test_create_named_session_lost_race_surfaces_as_404(monkeypatch):
    # Simulates two operators creating the same named session concurrently
    # on a last-writer-wins backend: the loser must get 404 instead of
    # chatting under a session now owned by someone else.
    store = InMemorySessionStore()
    real_create = store.create_session

    def racing_create(user_id, session_id=None):
        record = real_create(user_id, session_id=session_id)
        if session_id == "incident-inc-race01":
            real_create("other-user", session_id=session_id)
        return record

    monkeypatch.setattr(store, "create_session", racing_create)
    monkeypatch.setattr(session_service, "SESSION_STORE", store)

    try:
        session_service.create_named_session("incident-inc-race01", "alice")
    except HTTPException as exc:
        assert exc.status_code == 404
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("A lost create race must not return a session")


def test_named_session_route_accepts_caller_supplied_id():
    client = TestClient(create_app())

    created = client.post(
        "/api/v2/sessions",
        json={"session_id": "incident-inc-route01"},
        headers={"X-User-ID": "alice"},
    )
    assert created.status_code == 201
    assert created.json()["session_id"] == "incident-inc-route01"

    # Idempotent for the owning user (re-triage reuses the session).
    again = client.post(
        "/api/v2/sessions",
        json={"session_id": "incident-inc-route01"},
        headers={"X-User-ID": "alice"},
    )
    assert again.status_code == 201
    assert again.json()["session_id"] == "incident-inc-route01"

    # Foreign owner is indistinguishable from an unknown id.
    foreign = client.post(
        "/api/v2/sessions",
        json={"session_id": "incident-inc-route01"},
        headers={"X-User-ID": "bob"},
    )
    assert foreign.status_code == 404

    # The named session is usable where an unknown id would 404.
    readable = client.get(
        "/api/v2/sessions/incident-inc-route01",
        headers={"X-User-ID": "alice"},
    )
    assert readable.status_code == 200


def test_delete_session_removes_session_and_agent_state(monkeypatch):
    monkeypatch.setattr(session_service, "SESSION_STORE", InMemorySessionStore())
    state_store = InMemoryAgentStateStore()
    monkeypatch.setattr(session_service, "AGENT_STATE_STORE", state_store)

    created = session_service.create_session("alice")
    state_store.save_state(created.session_id, '{"turn": 1}')

    assert session_service.delete_session(created.session_id, "alice") is True
    assert state_store.load_state(created.session_id) is None

    # Session is gone: repeat delete reports absence.
    assert session_service.delete_session(created.session_id, "alice") is False


def test_delete_session_missing_returns_false(monkeypatch):
    monkeypatch.setattr(session_service, "SESSION_STORE", InMemorySessionStore())
    assert session_service.delete_session("ses-nope", "alice") is False


def test_delete_session_hides_foreign_owner(monkeypatch):
    monkeypatch.setattr(session_service, "SESSION_STORE", InMemorySessionStore())
    state_store = InMemoryAgentStateStore()
    monkeypatch.setattr(session_service, "AGENT_STATE_STORE", state_store)

    created = session_service.create_session("alice")
    state_store.save_state(created.session_id, '{"turn": 1}')

    try:
        session_service.delete_session(created.session_id, "bob")
    except HTTPException as exc:
        assert exc.status_code == 404
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Foreign sessions must not be deletable")

    # The owner's session and its state survive the foreign attempt.
    assert session_service.get_session(created.session_id, "alice") is not None
    assert state_store.load_state(created.session_id) is not None


def test_delete_session_survives_state_store_failure(monkeypatch):
    monkeypatch.setattr(session_service, "SESSION_STORE", InMemorySessionStore())

    class BrokenStateStore:
        def delete_state(self, session_id):
            raise RuntimeError("state store down")

    monkeypatch.setattr(session_service, "AGENT_STATE_STORE", BrokenStateStore())

    created = session_service.create_session("alice")
    # Fail-open: the session delete succeeds even if state cleanup fails.
    assert session_service.delete_session(created.session_id, "alice") is True


def test_delete_session_cascades_stored_evidence(monkeypatch):
    from agent_service.services.evidence_store import InMemoryEvidenceStore

    monkeypatch.setattr(session_service, "SESSION_STORE", InMemorySessionStore())
    monkeypatch.setattr(
        session_service, "AGENT_STATE_STORE", InMemoryAgentStateStore()
    )
    evidence_store = InMemoryEvidenceStore()
    monkeypatch.setattr(session_service, "EVIDENCE_STORE", evidence_store)

    created = session_service.create_session("alice")
    evidence_store.save_turn(
        created.session_id,
        "req-1",
        0,
        [{"type": "tool_call", "call_id": "call-1", "tool_name": "k8s.list_pods"}],
        1 << 30,
    )
    assert evidence_store.load_turns(created.session_id) != []

    # SPEC-025 R-2: stored evidence follows the session into deletion.
    assert session_service.delete_session(created.session_id, "alice") is True
    assert evidence_store.load_turns(created.session_id) == []


def test_delete_session_survives_evidence_store_failure(monkeypatch):
    monkeypatch.setattr(session_service, "SESSION_STORE", InMemorySessionStore())

    class BrokenEvidenceStore:
        def delete_session(self, session_id):
            raise RuntimeError("evidence store down")

    monkeypatch.setattr(session_service, "EVIDENCE_STORE", BrokenEvidenceStore())

    created = session_service.create_session("alice")
    # Fail-open: evidence cleanup never fails the session delete.
    assert session_service.delete_session(created.session_id, "alice") is True
