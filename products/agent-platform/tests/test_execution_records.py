"""SPEC-037 R-4: durable execution records beside confirmation records.

Covers the execution record store (in-memory semantics, Postgres SQL
shape via a fake driver, factory backend selection): request rows land
at resume, receipts close open rows exactly once, invocation-boundary
rejections mark rows without a receipt, and session-scoped loads keep
the session-detail surface owner-shaped.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from agent_service.services.execution_records import (
    RETENTION_WINDOW_DAYS,
    InMemoryExecutionRecordStore,
    PostgresExecutionRecordStore,
    build_execution_record_store,
    make_execution_record,
)


def _request(
    confirm_id: str = "cf-1",
    call_id: str = "call-1",
    session_id: str = "ses-1",
    execution_id: str | None = None,
) -> dict:
    return {
        "execution_id": execution_id or f"exec-{call_id}",
        "confirm_id": confirm_id,
        "call_id": call_id,
        "session_id": session_id,
        "owner_user_id": "alice",
        "decider_user_id": "bob",
        "tool_name": "k8s.restart_service",
        "args_digest": "a" * 64,
        "requested_at": "2026-08-27T10:00:00Z",
        "signature": "b" * 64,
    }


def _receipt(status: str = "succeeded") -> dict:
    return {
        "execution_id": "exec-call-1",
        "status": status,
        "outcome_digest": "c" * 64,
        "request_id": "req-9",
        "completed_at": "2026-08-27T10:00:05Z",
        "signature": "d" * 64,
    }


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("AGENT_STATE_STORE_BACKEND", raising=False)
    monkeypatch.delenv("AGENT_STATE_DB_URL", raising=False)


# --- In-memory store semantics ---


class TestInMemoryStore:
    def test_save_request_and_load_for_session(self) -> None:
        store = InMemoryExecutionRecordStore()
        store.save_request(make_execution_record(_request(call_id="call-2")))
        store.save_request(make_execution_record(_request(call_id="call-1")))
        rows = store.load_for_session("ses-1")
        # Same requested_at: the call id keeps the batch order stable.
        assert [row["call_id"] for row in rows] == ["call-1", "call-2"]
        assert rows[0]["status"] == "requested"
        assert rows[0]["receipt"] is None
        assert rows[0]["digest_match"] is None

    def test_save_request_is_idempotent(self) -> None:
        store = InMemoryExecutionRecordStore()
        store.save_request(make_execution_record(_request()))
        store.save_receipt("cf-1", "call-1", _receipt(), True)
        # A replayed request write never resurrects or clobbers a closed row.
        store.save_request(make_execution_record(_request()))
        row = store.load_for_session("ses-1")[0]
        assert row["status"] == "succeeded"

    def test_save_receipt_closes_open_row(self) -> None:
        store = InMemoryExecutionRecordStore()
        store.save_request(make_execution_record(_request()))
        store.save_receipt("cf-1", "call-1", _receipt("failed"), True)
        row = store.load_for_session("ses-1")[0]
        assert row["status"] == "failed"
        assert row["digest_match"] is True
        assert row["receipt"]["request_id"] == "req-9"
        assert row["completed_at"] == "2026-08-27T10:00:05Z"

    def test_save_receipt_first_close_wins(self) -> None:
        store = InMemoryExecutionRecordStore()
        store.save_request(make_execution_record(_request()))
        store.save_receipt("cf-1", "call-1", _receipt("succeeded"), True)
        store.save_receipt("cf-1", "call-1", _receipt("failed"), True)
        assert store.load_for_session("ses-1")[0]["status"] == "succeeded"

    def test_save_receipt_ignores_unknown_keys(self) -> None:
        store = InMemoryExecutionRecordStore()
        store.save_receipt("nope", "call-1", _receipt(), True)
        assert store.load_for_session("ses-1") == []

    def test_mark_rejected_closes_without_receipt(self) -> None:
        store = InMemoryExecutionRecordStore()
        store.save_request(make_execution_record(_request()))
        store.mark_rejected("cf-1", "call-1", "args_digest_mismatch", False)
        row = store.load_for_session("ses-1")[0]
        assert row["status"] == "rejected"
        assert row["reject_reason"] == "args_digest_mismatch"
        assert row["digest_match"] is False
        assert row["receipt"] is None
        # A late receipt cannot reopen a rejected row.
        store.save_receipt("cf-1", "call-1", _receipt(), True)
        assert store.load_for_session("ses-1")[0]["status"] == "rejected"

    def test_load_is_session_scoped(self) -> None:
        store = InMemoryExecutionRecordStore()
        store.save_request(make_execution_record(_request(session_id="ses-1")))
        store.save_request(
            make_execution_record(_request(session_id="ses-2", call_id="call-9"))
        )
        assert len(store.load_for_session("ses-1")) == 1
        assert len(store.load_for_session("ses-2")) == 1

    def test_delete_session(self) -> None:
        store = InMemoryExecutionRecordStore()
        store.save_request(make_execution_record(_request()))
        assert store.delete_session("ses-1") is True
        assert store.delete_session("ses-1") is False
        assert store.load_for_session("ses-1") == []

    def test_is_ready(self) -> None:
        assert InMemoryExecutionRecordStore().is_ready() is True


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
    def test_initialize_runs_ddl_and_retention_sweep(self) -> None:
        calls: list[dict] = []
        store = PostgresExecutionRecordStore(
            db_url="postgresql://fake", connect=_fake_connect(calls)
        )
        store.initialize()
        sqls = [call["sql"] for call in calls if "sql" in call]
        assert any(
            "CREATE TABLE IF NOT EXISTS execution_records" in s for s in sqls
        )
        sweep = next(
            call
            for call in calls
            if "sql" in call and "DELETE FROM execution_records" in call["sql"]
        )
        assert (
            sweep["params"]["retention_days"] == RETENTION_WINDOW_DAYS
        )

    def test_save_request_inserts_once_and_sweeps(self) -> None:
        calls: list[dict] = []
        store = PostgresExecutionRecordStore(
            db_url="postgresql://fake", connect=_fake_connect(calls)
        )
        store.save_request(make_execution_record(_request()))
        executed = [call for call in calls if "sql" in call]
        insert = executed[0]
        assert "INSERT INTO execution_records" in insert["sql"]
        assert "ON CONFLICT (confirm_id, call_id) DO NOTHING" in insert["sql"]
        assert insert["params"]["execution_id"] == "exec-call-1"
        assert any(
            "DELETE FROM execution_records" in call["sql"]
            for call in executed[1:]
        )

    def test_save_receipt_only_touches_requested_rows(self) -> None:
        from psycopg.types.json import Jsonb

        calls: list[dict] = []
        store = PostgresExecutionRecordStore(
            db_url="postgresql://fake", connect=_fake_connect(calls)
        )
        store.save_receipt("cf-1", "call-1", _receipt("timeout"), True)
        update = next(call for call in calls if "sql" in call)
        assert "UPDATE execution_records" in update["sql"]
        assert "AND status = 'requested'" in update["sql"]
        assert isinstance(update["params"]["receipt"], Jsonb)
        assert update["params"]["status"] == "timeout"
        assert update["params"]["digest_match"] is True

    def test_mark_rejected_only_touches_requested_rows(self) -> None:
        calls: list[dict] = []
        store = PostgresExecutionRecordStore(
            db_url="postgresql://fake", connect=_fake_connect(calls)
        )
        store.mark_rejected("cf-1", "call-1", "request_missing", None)
        update = next(call for call in calls if "sql" in call)
        assert "UPDATE execution_records" in update["sql"]
        assert "AND status = 'requested'" in update["sql"]
        assert update["params"]["reject_reason"] == "request_missing"
        assert update["params"]["digest_match"] is None

    def test_load_for_session_maps_rows(self) -> None:
        calls: list[dict] = []
        row = (
            "cf-1",
            "call-1",
            "ses-1",
            "exec-call-1",
            "k8s.restart_service",
            datetime(2026, 8, 27, 10, 0, 0, tzinfo=timezone.utc),
            "succeeded",
            True,
            None,
            {"status": "succeeded"},
            datetime(2026, 8, 27, 10, 0, 5, tzinfo=timezone.utc),
        )
        store = PostgresExecutionRecordStore(
            db_url="postgresql://fake", connect=_fake_connect(calls, rows=[row])
        )
        record = store.load_for_session("ses-1")[0]
        assert record["requested_at"] == "2026-08-27T10:00:00Z"
        assert record["completed_at"] == "2026-08-27T10:00:05Z"
        assert record["status"] == "succeeded"
        assert record["digest_match"] is True
        assert record["receipt"] == {"status": "succeeded"}

    def test_delete_session_reports_rows_removed(self) -> None:
        calls: list[dict] = []
        store = PostgresExecutionRecordStore(
            db_url="postgresql://fake",
            connect=_fake_connect(calls, rows=[("cf-1",)]),
        )
        assert store.delete_session("ses-1") is True
        empty = PostgresExecutionRecordStore(
            db_url="postgresql://fake", connect=_fake_connect(calls)
        )
        assert empty.delete_session("ses-1") is False


# --- Factory backend selection ---


class TestFactory:
    def test_defaults_to_memory(self, monkeypatch) -> None:
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "memory")
        store = build_execution_record_store()
        assert store.backend_name == "memory"

    def test_postgres_without_url_raises(self, monkeypatch) -> None:
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "postgres")
        with pytest.raises(ValueError, match="AGENT_STATE_DB_URL"):
            build_execution_record_store()

    def test_postgres_unreachable_falls_back_to_memory(self, monkeypatch) -> None:
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "postgres")
        monkeypatch.setenv("AGENT_STATE_DB_URL", "postgresql://fake")

        def fail_connect():
            raise RuntimeError("connection refused")

        monkeypatch.setattr(
            PostgresExecutionRecordStore,
            "_default_connect",
            lambda self: fail_connect(),
        )
        store = build_execution_record_store()
        assert store.backend_name == "memory"

    def test_unknown_backend_raises(self, monkeypatch) -> None:
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "redis")
        with pytest.raises(ValueError, match="Unknown AGENT_STATE_STORE_BACKEND"):
            build_execution_record_store()


# --- Session detail: executions attach to confirmation cards (R-4) ---


class TestSessionDetail:
    @pytest.fixture(autouse=True)
    def _clean_stores(self):
        from agent_service.services.confirmation_records import (
            CONFIRMATION_RECORD_STORE,
        )
        from agent_service.services.execution_records import (
            EXECUTION_RECORD_STORE,
        )

        confirmations = getattr(CONFIRMATION_RECORD_STORE, "_by_confirm_id", None)
        executions = getattr(EXECUTION_RECORD_STORE, "_by_key", None)
        if confirmations is not None:
            confirmations.clear()
        if executions is not None:
            executions.clear()
        yield
        if confirmations is not None:
            confirmations.clear()
        if executions is not None:
            executions.clear()

    def test_session_detail_attaches_executions_per_confirmation(self) -> None:
        from fastapi.testclient import TestClient

        from agent_service.app import create_app
        from agent_service.services.confirmation_records import (
            CONFIRMATION_RECORD_STORE,
            make_record,
        )
        from agent_service.services.execution_records import (
            EXECUTION_RECORD_STORE,
        )

        client = TestClient(create_app())
        session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
        session_id = session.json()["session_id"]
        CONFIRMATION_RECORD_STORE.save_parked(
            make_record(
                "cf-exec",
                session_id,
                "alice",
                [
                    {"call_id": "call-1", "tool_name": "k8s.restart_service"},
                    {"call_id": "call-2", "tool_name": "k8s.scale_deployment"},
                ],
                "tools:mutate",
            )
        )
        CONFIRMATION_RECORD_STORE.mark_resolved(
            session_id, "cf-exec", "approved", "alice", "approve"
        )
        EXECUTION_RECORD_STORE.save_request(
            make_execution_record(_request(confirm_id="cf-exec", session_id=session_id))
        )
        second = _request(confirm_id="cf-exec", session_id=session_id, call_id="call-2")
        EXECUTION_RECORD_STORE.save_request(make_execution_record(second))
        EXECUTION_RECORD_STORE.save_receipt(
            "cf-exec", "call-2", _receipt("succeeded"), True
        )

        detail = client.get(
            f"/api/v2/sessions/{session_id}", headers={"X-User-ID": "alice"}
        )
        assert detail.status_code == 200
        cards = detail.json()["confirmations"]
        assert len(cards) == 1
        executions = cards[0]["executions"]
        assert [row["call_id"] for row in executions] == ["call-1", "call-2"]
        assert executions[0]["status"] == "requested"
        assert executions[1]["status"] == "succeeded"
        assert executions[1]["digest_match"] is True
        assert executions[1]["receipt"]["request_id"] == "req-9"

    def test_session_detail_cards_without_executions_keep_empty_list(self) -> None:
        from fastapi.testclient import TestClient

        from agent_service.app import create_app
        from agent_service.services.confirmation_records import (
            CONFIRMATION_RECORD_STORE,
            make_record,
        )

        client = TestClient(create_app())
        session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
        session_id = session.json()["session_id"]
        CONFIRMATION_RECORD_STORE.save_parked(
            make_record(
                "cf-legacy",
                session_id,
                "alice",
                [{"call_id": "call-1", "tool_name": "k8s.restart_service"}],
                "tools:mutate",
            )
        )
        CONFIRMATION_RECORD_STORE.mark_resolved(
            session_id, "cf-legacy", "approved", "alice", "approve"
        )
        detail = client.get(
            f"/api/v2/sessions/{session_id}", headers={"X-User-ID": "alice"}
        )
        assert detail.status_code == 200
        # Legacy decided cards (no execution rows) surface unchanged.
        assert detail.json()["confirmations"][0]["executions"] == []

