"""SPEC-031 R-1/R-2/R-3/R-4: durable confirmation records, cards, inbox.

Covers the confirmation record store (in-memory semantics, Postgres SQL
shape via a fake driver, factory backend selection), the kernel-facing
surfaces (session-detail cards, pending-confirmation fallback), the
approver inbox endpoint, and the race-resilient already_resolved
semantics on the confirm route.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from agent_service.api.v2.routes import chat_confirm
from agent_service.app import create_app
from agent_service.schemas.v2 import AgentChatConfirmRequest
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
    turn_index: int | None = None,
    flow_summary: dict | None = None,
) -> dict:
    record = make_record(
        confirm_id,
        session_id,
        owner,
        [{"call_id": "call-1", "tool_name": "k8s.restart_service"}],
        "tools:mutate",
        turn_index=turn_index,
        flow_summary=flow_summary,
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

    def test_save_and_load_round_trips_turn_index(self) -> None:
        """SPEC-033 R-1: the parking turn ordinal survives the store."""
        store = InMemoryConfirmationRecordStore()
        store.save_parked(_record("cf-1", turn_index=4))
        store.save_parked(_record("cf-2"))
        rows = store.load_for_session("ses-1")
        assert rows[0]["turn_index"] == 4
        assert rows[1]["turn_index"] is None
        assert store.load_pending_for_session("ses-1")["turn_index"] is None

    def test_save_and_load_round_trips_flow_summary(self) -> None:
        """SPEC-051 R-6: the card-level browser-flow headline survives the
        store so the inbox and session detail replay the same workflow
        framing; a non-browser (or pre-spec) card round-trips None."""
        store = InMemoryConfirmationRecordStore()
        summary = {
            "skill_id": "samples/password-reset",
            "origin": "http://admin.local",
            "title": "Reset User Password",
            "description": "Reset a user's password in the admin portal",
            "flow_intent": "Submit the password reset for the user.",
            "risk_class": "write",
        }
        store.save_parked(_record("cf-1", flow_summary=summary))
        store.save_parked(_record("cf-2"))
        rows = store.load_for_session("ses-1")
        assert rows[0]["flow_summary"] == summary
        assert rows[1]["flow_summary"] is None
        assert store.load_pending_for_session("ses-1")["flow_summary"] is None
        assert store.load_record("ses-1", "cf-1")["flow_summary"] == summary

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

    def test_mark_resolved_second_write_is_noop(self) -> None:
        """SPEC-031 R-4: the first outcome wins — the claim-time write
        owns the resolution, the resume's safety-net write is a no-op."""
        store = InMemoryConfirmationRecordStore()
        store.save_parked(_record("cf-1"))
        store.mark_resolved("ses-1", "cf-1", "approved", "bob", "approve")
        first = store.load_record("ses-1", "cf-1")
        store.mark_resolved("ses-1", "cf-1", "denied", "carol", "deny")
        record = store.load_record("ses-1", "cf-1")
        assert record["status"] == "approved"
        assert record["decider_user_id"] == "bob"
        assert record["decision"] == "approve"
        assert record["decided_at"] == first["decided_at"]

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

    def test_inbox_split_keeps_pending_and_recent_history_only(self) -> None:
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
        # SPEC-036 R-2: pending and resolved history are separate
        # queries; the pending queue holds parked work only.
        pending_ids = [row["confirm_id"] for row in store.load_pending_inbox()]
        assert pending_ids == ["cf-pending"]
        history, total = store.load_inbox_history(50, 0)
        history_ids = [row["confirm_id"] for row in history]
        # Retention is decided_at-based: cf-stale was decided just now, so
        # it stays despite its old park; cf-aged fell out of the window.
        assert history_ids == ["cf-recent", "cf-stale"]
        assert total == 2

    def test_pending_inbox_caps_at_limit_most_recent_first(self) -> None:
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
        rows = store.load_pending_inbox()
        assert len(rows) == INBOX_LIMIT
        assert rows[0]["confirm_id"] == f"cf-{INBOX_LIMIT + 9:03d}"

    def test_inbox_history_paginates_with_total(self) -> None:
        """SPEC-036 R-2: offset paging with the windowed total."""
        store = InMemoryConfirmationRecordStore()
        now = datetime.now(timezone.utc)
        for index in range(15):
            session_id = f"ses-{index:02d}"
            store.save_parked(
                _record(
                    f"cf-{index:02d}",
                    session_id=session_id,
                    parked_at=now + timedelta(seconds=index),
                )
            )
            store.mark_resolved(
                session_id, f"cf-{index:02d}", "approved", "bob", "approve"
            )
        page_one, total = store.load_inbox_history(10, 0)
        assert total == 15
        assert len(page_one) == 10
        # Newest park first.
        assert page_one[0]["confirm_id"] == "cf-14"
        page_two, total_two = store.load_inbox_history(10, 10)
        assert total_two == 15
        assert len(page_two) == 5
        seen = {row["confirm_id"] for row in page_one} | {
            row["confirm_id"] for row in page_two
        }
        assert len(seen) == 15

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
        store.initialize(stale_after_seconds=600)
        sqls = [call["sql"] for call in calls if "sql" in call]
        assert any("CREATE TABLE IF NOT EXISTS confirmation_records" in s for s in sqls)
        # SPEC-033 R-1: pre-spec tables migrate in place at startup.
        assert any(
            "ADD COLUMN IF NOT EXISTS turn_index" in s for s in sqls
        )
        # SPEC-051 R-6: the browser-flow headline column migrates in place too.
        assert any(
            "ADD COLUMN IF NOT EXISTS flow_summary" in s for s in sqls
        )
        sweep = next(
            call
            for call in calls
            if "sql" in call and "status = 'expired'" in call["sql"]
        )
        # SPEC-031 review fix: the sweep is scoped to rows older than the
        # HITL TTL so a sibling replica's live park is never expired.
        assert "status = 'pending'" in sweep["sql"]
        assert "parked_at <= now() - make_interval" in sweep["sql"]
        assert sweep["params"] == {"stale_after_seconds": 600}

    def test_mark_resolved_only_touches_pending_rows(self) -> None:
        """Idempotent resolution at the SQL level: the UPDATE carries the
        ``status = 'pending'`` guard so a second writer finds no row."""
        calls: list[dict] = []
        store = PostgresConfirmationRecordStore(
            db_url="postgresql://fake", connect=_fake_connect(calls)
        )
        store.mark_resolved("ses-1", "cf-1", "approved", "bob", "approve")
        update = next(call for call in calls if "sql" in call)
        assert "UPDATE confirmation_records" in update["sql"]
        assert "AND status = 'pending'" in update["sql"]

    def test_save_parked_wraps_pending_calls_in_jsonb_and_bounds(self) -> None:
        from psycopg.types.json import Jsonb

        calls: list[dict] = []
        store = PostgresConfirmationRecordStore(
            db_url="postgresql://fake", connect=_fake_connect(calls)
        )
        store.save_parked(_record("cf-1", turn_index=2))
        executed = [call for call in calls if "sql" in call]
        insert = executed[0]
        assert "ON CONFLICT (confirm_id) DO NOTHING" in insert["sql"]
        assert isinstance(insert["params"]["pending_calls"], Jsonb)
        # SPEC-033 R-1: the parking turn ordinal rides the insert.
        assert insert["params"]["turn_index"] == 2
        # SPEC-051 R-6: an absent flow headline inserts as SQL NULL — never a
        # bare dict, which psycopg3 cannot adapt to a JSONB column.
        assert insert["params"]["flow_summary"] is None
        assert any("OFFSET" in call["sql"] for call in executed[1:])
        assert any("status <> 'pending'" in call["sql"] for call in executed[1:])

    def test_save_parked_wraps_flow_summary_in_jsonb(self) -> None:
        """SPEC-051 R-6: a browser-flow headline is wrapped in ``Jsonb`` so
        psycopg3 adapts it to the JSONB column (a bare dict raises
        ``cannot adapt type 'dict'``)."""
        from psycopg.types.json import Jsonb

        calls: list[dict] = []
        store = PostgresConfirmationRecordStore(
            db_url="postgresql://fake", connect=_fake_connect(calls)
        )
        summary = {
            "skill_id": "samples/password-reset",
            "origin": "http://admin.local",
            "title": "Reset User Password",
            "description": "Reset a user's password in the admin portal",
            "flow_intent": "Submit the password reset for the user.",
            "risk_class": "write",
        }
        store.save_parked(_record("cf-1", flow_summary=summary))
        insert = next(call for call in calls if "sql" in call)
        wrapped = insert["params"]["flow_summary"]
        assert isinstance(wrapped, Jsonb)
        assert wrapped.obj == summary

    def test_load_record_maps_row_to_record(self) -> None:
        calls: list[dict] = []
        summary = {
            "skill_id": "samples/password-reset",
            "origin": "http://admin.local",
            "title": "Reset User Password",
            "description": "Reset a user's password in the admin portal",
            "flow_intent": "Submit the password reset for the user.",
            "risk_class": "write",
        }
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
            3,
            summary,
        )
        store = PostgresConfirmationRecordStore(
            db_url="postgresql://fake", connect=_fake_connect(calls, rows=[row])
        )
        record = store.load_record("ses-1", "cf-1")
        assert record["confirm_id"] == "cf-1"
        assert record["parked_at"] == "2026-08-25T10:00:00Z"
        assert record["decided_at"] == "2026-08-25T10:05:00Z"
        assert record["status"] == "approved"
        assert record["turn_index"] == 3
        # SPEC-051 R-6: the browser-flow headline maps from the new column.
        assert record["flow_summary"] == summary

    def test_load_record_maps_legacy_row_without_turn_index(self) -> None:
        """SPEC-033 R-1 / SPEC-051 R-6: rows parked before the columns existed
        load with ``turn_index=None`` and ``flow_summary=None`` and keep the
        legacy newest-turn anchoring."""
        calls: list[dict] = []
        row = (
            "cf-1",
            "ses-1",
            "alice",
            [{"tool_name": "k8s.restart_service"}],
            "tools:mutate",
            "pending",
            datetime(2026, 8, 25, 10, 0, 0, tzinfo=timezone.utc),
            None,
            None,
            None,
            None,
            None,
        )
        store = PostgresConfirmationRecordStore(
            db_url="postgresql://fake", connect=_fake_connect(calls, rows=[row])
        )
        record = store.load_record("ses-1", "cf-1")
        assert record["turn_index"] is None
        assert record["flow_summary"] is None

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

    def test_load_inbox_split_queries_carry_pagination_params(self) -> None:
        """SPEC-036 R-2: the pending queue and the history page are
        separate statements; the page carries limit/offset and the
        retention window, and the total counts the same window."""
        calls: list[dict] = []
        store = PostgresConfirmationRecordStore(
            db_url="postgresql://fake", connect=_fake_connect(calls)
        )
        assert store.load_pending_inbox() == []
        history, total = store.load_inbox_history(10, 20)
        assert history == []
        assert total == 0
        sqls = [call for call in calls if "sql" in call]
        pending_call = sqls[0]
        assert "status = 'pending'" in pending_call["sql"]
        assert pending_call["params"] == {"limit": INBOX_LIMIT}
        history_call = next(
            call
            for call in sqls
            if "LIMIT %(limit)s OFFSET %(offset)s" in call["sql"]
        )
        assert history_call["params"] == {
            "history_days": HISTORY_WINDOW_DAYS,
            "limit": 10,
            "offset": 20,
        }
        count_call = next(call for call in sqls if "COUNT(*)" in call["sql"])
        assert count_call["params"] == {"history_days": HISTORY_WINDOW_DAYS}

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

    def test_postgres_initialize_scopes_sweep_to_hitl_timeout(
        self, monkeypatch
    ) -> None:
        """The startup sweep TTL mirrors AGENT_HITL_CONFIRM_TIMEOUT."""
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "postgres")
        monkeypatch.setenv("AGENT_STATE_DB_URL", "postgresql://fake")
        monkeypatch.setenv("AGENT_HITL_CONFIRM_TIMEOUT", "900")
        captured: dict = {}

        def fake_initialize(self, stale_after_seconds: float = 0.0) -> None:
            captured["stale_after_seconds"] = stale_after_seconds

        monkeypatch.setattr(
            PostgresConfirmationRecordStore, "initialize", fake_initialize
        )
        store = build_confirmation_record_store()
        assert store.backend_name == "postgres"
        assert captured["stale_after_seconds"] == 900

    def test_postgres_initialize_falls_back_on_bad_timeout(
        self, monkeypatch
    ) -> None:
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "postgres")
        monkeypatch.setenv("AGENT_STATE_DB_URL", "postgresql://fake")
        monkeypatch.setenv("AGENT_HITL_CONFIRM_TIMEOUT", "not-a-number")
        captured: dict = {}

        def fake_initialize(self, stale_after_seconds: float = 0.0) -> None:
            captured["stale_after_seconds"] = stale_after_seconds

        monkeypatch.setattr(
            PostgresConfirmationRecordStore, "initialize", fake_initialize
        )
        build_confirmation_record_store()
        assert captured["stale_after_seconds"] == 600


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


def test_confirm_persists_outcome_at_claim_time_before_stream_drains() -> None:
    """SPEC-031 review fix (M1): the durable outcome lands the moment the
    claim succeeds — racing approvers see the structured 409 while the
    winner's resumed turn still streams, never an opaque 404."""
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    pending = CONFIRMATION_REGISTRY.register(
        session_id, "alice", "reply-1", [], timeout=600.0
    )
    CONFIRMATION_RECORD_STORE.save_parked(
        make_record(
            pending.confirm_id,
            session_id,
            "alice",
            [{"call_id": "call-1", "tool_name": "k8s.restart_service"}],
            "tools:mutate",
        )
    )

    # First approver claims; the StreamingResponse is returned but its
    # body never drained, so the resumed turn has not finished yet.
    asyncio.run(
        chat_confirm(
            AgentChatConfirmRequest(
                session_id=session_id,
                confirm_id=pending.confirm_id,
                decision="approve",
            ),
            x_user_id="bob-approver",
        )
    )
    record = CONFIRMATION_RECORD_STORE.load_record(session_id, pending.confirm_id)
    assert record["status"] == "approved"
    assert record["decider_user_id"] == "bob-approver"
    assert record["decision"] == "approve"

    # Second approver, still mid-stream of the winner: structured 409
    # carrying the winner's outcome instead of a bare 404.
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(
            chat_confirm(
                AgentChatConfirmRequest(
                    session_id=session_id,
                    confirm_id=pending.confirm_id,
                    decision="deny",
                ),
                x_user_id="carol-approver",
            )
        )
    assert excinfo.value.status_code == 409
    detail = excinfo.value.detail
    assert detail["reason"] == "already_resolved"
    assert detail["status"] == "approved"
    assert detail["decider_user_id"] == "bob-approver"
    assert detail["decision"] == "approve"
    # The loser's decision never overwrites the winner's outcome.
    record = CONFIRMATION_RECORD_STORE.load_record(session_id, pending.confirm_id)
    assert record["status"] == "approved"
    assert record["decider_user_id"] == "bob-approver"


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
            turn_index=2,
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
    # SPEC-033 R-2: the parking turn ordinal rides the session detail;
    # pre-spec records stay null.
    assert cards[1]["turn_index"] == 2
    assert cards[0]["turn_index"] is None


def test_session_detail_confirmations_empty_for_clean_session() -> None:
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    detail = client.get(
        f"/api/v2/sessions/{session_id}", headers={"X-User-ID": "alice"}
    )
    assert detail.json()["confirmations"] == []


def test_inbox_lists_pending_and_history_with_session_titles() -> None:
    """SPEC-031 R-3 / SPEC-036 R-3: cross-session discovery, metadata
    only, split into a complete pending queue and a paged history."""
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
    body = response.json()
    pending = body["confirmations"]
    history = body["history"]
    assert {item["confirm_id"] for item in pending} == {"cf-live"}
    assert {item["confirm_id"] for item in history} == {"cf-old"}
    assert body["history_total"] == 1
    # No transcript text leaks — metadata fields only.
    assert "transcript" not in pending[0]
    live = pending[0]
    assert live["owner_user_id"] == "carol"
    assert live["status"] == "pending"
    assert "session_title" in live
    assert "session_title" in history[0]


def test_inbox_history_pagination_params_page_the_results() -> None:
    """SPEC-036 R-3: history_limit/history_offset shift the page while
    the total counts the whole retention window."""
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    for index in range(5):
        _seed_resolved(
            f"cf-{index}", session_id, "approved", "bob-approver", "approve"
        )
    headers = {"X-User-ID": "bob-approver"}
    first = client.get(
        "/api/v2/confirmations?history_limit=2&history_offset=0",
        headers=headers,
    )
    second = client.get(
        "/api/v2/confirmations?history_limit=2&history_offset=2",
        headers=headers,
    )
    assert first.status_code == 200
    assert second.status_code == 200
    first_page = first.json()
    second_page = second.json()
    assert len(first_page["history"]) == 2
    assert len(second_page["history"]) == 2
    assert first_page["history_total"] == 5
    assert second_page["history_total"] == 5
    first_ids = {item["confirm_id"] for item in first_page["history"]}
    second_ids = {item["confirm_id"] for item in second_page["history"]}
    assert first_ids.isdisjoint(second_ids)
    assert first_page["confirmations"] == []


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
    body = inbox.json()
    assert all(
        item["confirm_id"] != "cf-gone"
        for item in body["confirmations"] + body["history"]
    )
