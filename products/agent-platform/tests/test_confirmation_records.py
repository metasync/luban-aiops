"""SPEC-031 R-1/R-2/R-3/R-4: durable confirmation records, cards, inbox.

Covers the confirmation record store (in-memory semantics, Postgres SQL
shape via a fake driver, factory backend selection), the kernel-facing
surfaces (session-detail cards, pending-confirmation fallback), the
approver inbox endpoint, and the race-resilient already_resolved
semantics on the confirm route.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from agent_service.app import create_app
from agent_service.services.confirmation_records import (
    CONFIRMATION_RECORD_STORE,
    HISTORY_WINDOW_DAYS,
    INBOX_LIMIT,
    PER_SESSION_CAP,
    InMemoryConfirmationRecordStore,
    PostgresConfirmationRecordStore,
    build_confirmation_record_store,
    make_record,
)
from agent_service.services.hitl_confirmations import CONFIRMATION_REGISTRY


def _iso(stamp: datetime) -> str:
    return stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record(
    confirm_id: str,
    session_id: str = "ses-1",
    owner: str = "alice",
    parked_at: datetime | None = None,
) -> dict:
    record = make_record(
        confirm_id,
        session_id,
        owner,
        [{"call_id": "call-1", "tool_name": "k8s.restart_service"}],
        "tools:mutate",
    )
    if parked_at is not None:
        record["parked_at"] = _iso(parked_at)
    return record


@pytest.fixture(autouse=True)
def _clean_state():
    CONFIRMATION_REGISTRY._by_session.clear()
    records = getattr(CONFIRMATION_RECORD_STORE, "_by_confirm_id", None)
    if records is not None:
        records.clear()
    yield
    CONFIRMATION_REGISTRY._by_session.clear()
    if records is not None:
        records.clear()


# --- In-memory store semantics ---


class TestInMemoryStore:
    def test_save_and_load_for_session_ordered_by_parked_at(self) -> None:
        store = InMemoryConfirmationRecordStore()
        base = datetime.now(timezone.utc)
        store.save_parked(_record("cf-2", parked_at=base))
        store.save_parked(_record("cf-1", parked_at=base - timedelta(minutes=5)))
        rows = store.load_for_session("ses-1")
        assert [row["confirm_id"] for row in rows] == ["cf-1", "cf-2"]

    def test_mark_resolved_attributes_decider_and_outcome(self) -> None:
        store = InMemoryConfirmationRecordStore()
        store.save_parked(_record("cf-1"))
        store.mark_resolved("ses-1", "cf-1", "approved", "bob", "approve")
        record = store.load_record("ses-1", "cf-1")
        assert record["status"] == "approved"
        assert record["decider_user_id"] == "bob"
        assert record["decision"] == "approve"
        assert record["decided_at"] is not None

    def test_mark_resolved_ignores_unknown_and_foreign_ids(self) -> None:
        store = InMemoryConfirmationRecordStore()
        store.save_parked(_record("cf-1"))
        store.mark_resolved("ses-1", "nope", "approved", "bob", "approve")
        store.mark_resolved("ses-other", "cf-1", "approved", "bob", "approve")
        assert store.load_record("ses-1", "cf-1")["status"] == "pending"

    def test_load_pending_for_session_returns_most_recent_pending(self) -> None:
        store = InMemoryConfirmationRecordStore()
        base = datetime.now(timezone.utc)
        store.save_parked(_record("cf-old", parked_at=base - timedelta(hours=1)))
        store.save_parked(_record("cf-new", parked_at=base))
        store.mark_resolved("ses-1", "cf-new", "denied", "bob", "deny")
        pending = store.load_pending_for_session("ses-1")
        assert pending["confirm_id"] == "cf-old"
        store.mark_resolved("ses-1", "cf-old", "approved", "bob", "approve")
        assert store.load_pending_for_session("ses-1") is None

    def test_per_session_cap_evicts_oldest_first(self) -> None:
        store = InMemoryConfirmationRecordStore()
        base = datetime.now(timezone.utc)
        for index in range(PER_SESSION_CAP + 5):
            store.save_parked(
                _record(f"cf-{index:03d}", parked_at=base + timedelta(seconds=index))
            )
        rows = store.load_for_session("ses-1")
        assert len(rows) == PER_SESSION_CAP
        assert rows[0]["confirm_id"] == "cf-005"
        assert rows[-1]["confirm_id"] == f"cf-{PER_SESSION_CAP + 4:03d}"

    def test_delete_session_removes_only_that_session(self) -> None:
        store = InMemoryConfirmationRecordStore()
        store.save_parked(_record("cf-1", session_id="ses-1"))
        store.save_parked(_record("cf-2", session_id="ses-2"))
        assert store.delete_session("ses-1") is True
        assert store.delete_session("ses-1") is False
        assert store.load_for_session("ses-1") == []
        assert len(store.load_for_session("ses-2")) == 1

    def test_inbox_keeps_pending_and_recent_history_only(self) -> None:
        store = InMemoryConfirmationRecordStore()
        now = datetime.now(timezone.utc)
        store.save_parked(_record("cf-pending", parked_at=now))
        store.save_parked(
            _record("cf-recent", parked_at=now - timedelta(days=5))
        )
        store.mark_resolved("ses-1", "cf-recent", "approved", "bob", "approve")
        store.save_parked(
            _record("cf-stale", parked_at=now - timedelta(days=60))
        )
        store.mark_resolved("ses-1", "cf-stale", "denied", "bob", "deny")
        # A resolved record whose decision aged past the window drops out.
        aged = _record(
            "cf-aged", session_id="ses-aged", parked_at=now - timedelta(days=40)
        )
        store.save_parked(aged)
        store.mark_resolved("ses-aged", "cf-aged", "approved", "bob", "approve")
        store._by_confirm_id["cf-aged"]["decided_at"] = _iso(
            now - timedelta(days=HISTORY_WINDOW_DAYS + 1)
        )
        ids = [row["confirm_id"] for row in store.load_inbox()]
        # Retention is decided_at-based: cf-stale was decided just now, so
        # it stays despite its old park; cf-aged fell out of the window.
        assert ids == ["cf-pending", "cf-recent", "cf-stale"]

    def test_inbox_caps_at_limit_most_recent_first(self) -> None:
        store = InMemoryConfirmationRecordStore()
        now = datetime.now(timezone.utc)
        for index in range(INBOX_LIMIT + 10):
            # One record per session keeps the per-session cap out of play.
            store.save_parked(
                _record(
                    f"cf-{index:03d}",
                    session_id=f"ses-{index:03d}",
                    parked_at=now + timedelta(seconds=index),
                )
            )
        rows = store.load_inbox()
        assert len(rows) == INBOX_LIMIT
        assert rows[0]["confirm_id"] == f"cf-{INBOX_LIMIT + 9:03d}"

    def test_is_ready(self) -> None:
        assert InMemoryConfirmationRecordStore().is_ready() is True


# --- Postgres backend (fake driver) ---


class _FakeCursor:
    def __init__(self, calls: list[dict], rows=None) -> None:
        self._calls = calls
        self._rows = rows or []

    def execute(self, sql, params=None):
        self._calls.append({"sql": sql, "params": params})

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_connect(calls: list[dict], rows=None, fail: bool = False):
    @contextmanager
    def connect():
        if fail:
            raise RuntimeError("connection refused")

        class FakeConn:
            def cursor(self):
                return _FakeCursor(calls, rows)

            def commit(self):
                calls.append({"commit": True})

        yield FakeConn()

    return connect


class TestPostgresStore:
    def test_initialize_runs_ddl_and_closes_stale_pending(self) -> None:
        calls: list[dict] = []
        store = PostgresConfirmationRecordStore(
            db_url="postgresql://fake", connect=_fake_connect(calls)
        )
        store.initialize()
        sqls = [call["sql"] for call in calls if "sql" in call]
        assert any("CREATE TABLE IF NOT EXISTS confirmation_records" in s for s in sqls)
        assert any("status = 'expired'" in s and "status = 'pending'" in s for s in sqls)

    def test_save_parked_wraps_pending_calls_in_jsonb_and_bounds(self) -> None:
        from psycopg.types.json import Jsonb

        calls: list[dict] = []
        store = PostgresConfirmationRecordStore(
            db_url="postgresql://fake", connect=_fake_connect(calls)
        )
        store.save_parked(_record("cf-1"))
        executed = [call for call in calls if "sql" in call]
        insert = executed[0]
        assert "ON CONFLICT (confirm_id) DO NOTHING" in insert["sql"]
        assert isinstance(insert["params"]["pending_calls"], Jsonb)
        assert any("OFFSET" in call["sql"] for call in executed[1:])
        assert any("status <> 'pending'" in call["sql"] for call in executed[1:])

    def test_load_record_maps_row_to_record(self) -> None:
        calls: list[dict] = []
        row = (
            "cf-1",
            "ses-1",
            "alice",
            [{"tool_name": "k8s.restart_service"}],
            "tools:mutate",
            "approved",
            datetime(2026, 8, 25, 10, 0, 0, tzinfo=timezone.utc),
            "bob",
            "approve",
            datetime(2026, 8, 25, 10, 5, 0, tzinfo=timezone.utc),
        )
        store = PostgresConfirmationRecordStore(
            db_url="postgresql://fake", connect=_fake_connect(calls, rows=[row])
        )
        record = store.load_record("ses-1", "cf-1")
        assert record["confirm_id"] == "cf-1"
        assert record["parked_at"] == "2026-08-25T10:00:00Z"
        assert record["decided_at"] == "2026-08-25T10:05:00Z"
        assert record["status"] == "approved"

    def test_load_record_returns_none_without_row(self) -> None:
        calls: list[dict] = []
        store = PostgresConfirmationRecordStore(
            db_url="postgresql://fake", connect=_fake_connect(calls)
        )
        assert store.load_record("ses-1", "cf-1") is None

    def test_delete_session_reports_rows_removed(self) -> None:
        calls: list[dict] = []
        store = PostgresConfirmationRecordStore(
            db_url="postgresql://fake", connect=_fake_connect(calls, rows=[("cf-1",)])
        )
        assert store.delete_session("ses-1") is True
        empty = PostgresConfirmationRecordStore(
            db_url="postgresql://fake", connect=_fake_connect(calls)
        )
        assert empty.delete_session("ses-1") is False

    def test_is_ready_false_on_connection_failure(self) -> None:
        store = PostgresConfirmationRecordStore(
            db_url="postgresql://fake", connect=_fake_connect([], fail=True)
        )
        assert store.is_ready() is False


# --- Factory ---


class TestFactory:
    def test_memory_backend_is_default(self, monkeypatch) -> None:
        monkeypatch.delenv("AGENT_STATE_STORE_BACKEND", raising=False)
        store = build_confirmation_record_store()
        assert store.backend_name == "memory"

    def test_postgres_without_db_url_raises(self, monkeypatch) -> None:
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "postgres")
        monkeypatch.delenv("AGENT_STATE_DB_URL", raising=False)
        with pytest.raises(ValueError):
            build_confirmation_record_store()

    def test_unknown_backend_raises(self, monkeypatch) -> None:
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "redis")
        with pytest.raises(ValueError):
            build_confirmation_record_store()


# --- Routes: persistent cards and inbox (R-2/R-3) ---


def _client() -> TestClient:
    return TestClient(create_app())


def _seed_resolved(
    confirm_id: str,
    session_id: str,
    status: str,
    decider: str | None,
    decision: str | None,
) -> None:
    CONFIRMATION_RECORD_STORE.save_parked(
        make_record(
            confirm_id,
            session_id,
            "alice",
            [{"call_id": "call-1", "tool_name": "k8s.restart_service"}],
            "tools:mutate",
        )
    )
    CONFIRMATION_RECORD_STORE.mark_resolved(
        session_id, confirm_id, status, decider, decision
    )


def test_confirm_already_resolved_returns_structured_409() -> None:
    """SPEC-031 R-4: the racing approver sees the outcome, not a 404."""
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    _seed_resolved("cf-done", session_id, "approved", "bob-approver", "approve")
    response = client.post(
        "/api/v2/chat/confirm",
        json={
            "session_id": session_id,
            "confirm_id": "cf-done",
            "decision": "approve",
        },
        headers={"X-User-ID": "carol-approver"},
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["reason"] == "already_resolved"
    assert detail["status"] == "approved"
    assert detail["decider_user_id"] == "bob-approver"
    assert detail["decision"] == "approve"
    assert detail["decided_at"] is not None


def test_confirm_pending_record_without_registry_stays_404() -> None:
    """A durable pending record on a replica that lost its park keeps the
    404 posture — it cannot be resumed here and must not masquerade."""
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    CONFIRMATION_RECORD_STORE.save_parked(
        make_record(
            "cf-parked-elsewhere",
            session_id,
            "alice",
            [{"call_id": "call-1", "tool_name": "k8s.restart_service"}],
            "tools:mutate",
        )
    )
    response = client.post(
        "/api/v2/chat/confirm",
        json={
            "session_id": session_id,
            "confirm_id": "cf-parked-elsewhere",
            "decision": "approve",
        },
        headers={"X-User-ID": "alice"},
    )
    assert response.status_code == 404


def test_pending_confirmation_falls_back_to_durable_store() -> None:
    """SPEC-031 R-1: a replica without the registry park answers the tier
    bridge from the durable record."""
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    CONFIRMATION_RECORD_STORE.save_parked(
        make_record(
            "cf-replica",
            session_id,
            "alice",
            [{"call_id": "call-1", "tool_name": "k8s.restart_service"}],
            "tools:mutate",
        )
    )
    response = client.get(
        "/api/v2/chat/pending-confirmation",
        params={"session_id": session_id},
        headers={"X-User-ID": "bob-approver"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["confirm_id"] == "cf-replica"
    assert body["owner_user_id"] == "alice"
    assert body["action"] == "tools:mutate"
    assert body["pending_calls"][0]["tool_name"] == "k8s.restart_service"


def test_session_detail_carries_confirmation_cards() -> None:
    """SPEC-031 R-2: cards survive re-login on the owner transcript."""
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    CONFIRMATION_RECORD_STORE.save_parked(
        make_record(
            "cf-first",
            session_id,
            "alice",
            [{"call_id": "call-1", "tool_name": "k8s.restart_service"}],
            "tools:mutate",
        )
    )
    CONFIRMATION_RECORD_STORE.mark_resolved(
        session_id, "cf-first", "approved", "bob-approver", "approve"
    )
    CONFIRMATION_RECORD_STORE.save_parked(
        make_record(
            "cf-second",
            session_id,
            "alice",
            [{"call_id": "call-2", "tool_name": "k8s.restart_service"}],
            "tools:mutate",
        )
    )
    detail = client.get(
        f"/api/v2/sessions/{session_id}", headers={"X-User-ID": "alice"}
    )
    assert detail.status_code == 200
    cards = detail.json()["confirmations"]
    assert [card["confirm_id"] for card in cards] == ["cf-first", "cf-second"]
    assert cards[0]["status"] == "approved"
    assert cards[0]["decider_user_id"] == "bob-approver"
    assert cards[1]["status"] == "pending"


def test_session_detail_confirmations_empty_for_clean_session() -> None:
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    detail = client.get(
        f"/api/v2/sessions/{session_id}", headers={"X-User-ID": "alice"}
    )
    assert detail.json()["confirmations"] == []


def test_inbox_lists_pending_and_history_with_session_titles() -> None:
    """SPEC-031 R-3: cross-session discovery, metadata only."""
    client = _client()
    first = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    second = client.post("/api/v2/sessions", headers={"X-User-ID": "carol"})
    first_id = first.json()["session_id"]
    second_id = second.json()["session_id"]
    _seed_resolved("cf-old", first_id, "approved", "bob-approver", "approve")
    CONFIRMATION_RECORD_STORE.save_parked(
        make_record(
            "cf-live",
            second_id,
            "carol",
            [{"call_id": "call-9", "tool_name": "k8s.restart_service"}],
            "tools:mutate",
        )
    )
    response = client.get(
        "/api/v2/confirmations", headers={"X-User-ID": "bob-approver"}
    )
    assert response.status_code == 200
    items = response.json()["confirmations"]
    by_id = {item["confirm_id"]: item for item in items}
    assert set(by_id) == {"cf-old", "cf-live"}
    # No transcript text leaks — metadata fields only.
    assert "transcript" not in items[0]
    live = by_id["cf-live"]
    assert live["owner_user_id"] == "carol"
    assert live["status"] == "pending"
    assert "session_title" in live


def test_delete_session_cascades_confirmation_records() -> None:
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    _seed_resolved("cf-gone", session_id, "denied", "bob-approver", "deny")
    deleted = client.delete(
        f"/api/v2/sessions/{session_id}", headers={"X-User-ID": "alice"}
    )
    assert deleted.status_code in (200, 204)
    assert CONFIRMATION_RECORD_STORE.load_for_session(session_id) == []
    inbox = client.get("/api/v2/confirmations", headers={"X-User-ID": "bob"})
    assert all(
        item["confirm_id"] != "cf-gone" for item in inbox.json()["confirmations"]
    )
