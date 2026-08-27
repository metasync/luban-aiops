"""Execution record closing: first-write-wins, late arrival (SPEC-038 R-3)."""

from __future__ import annotations

import unittest
from collections.abc import Iterator
from contextlib import contextmanager

from execution_runtime.core.config import ExecutionSettings
from execution_runtime.services.execution_records import (
    InMemoryExecutionRecordStore,
    PostgresExecutionRecordStore,
    build_execution_record_store,
    make_execution_record,
)


def _request(**overrides) -> dict:
    record = {
        "confirm_id": "confirm-1",
        "call_id": "call-1",
        "session_id": "session-1",
        "execution_id": "exec-1",
        "tool_name": "k8s.scale_deployment",
        "requested_at": "2026-08-27T10:00:00Z",
    }
    record.update(overrides)
    return record


def _receipt(status: str = "succeeded") -> dict:
    return {
        "execution_id": "exec-1",
        "status": status,
        "outcome_digest": "digest",
        "request_id": "req-1",
        "completed_at": "2026-08-27T10:00:05Z",
        "signature": "sig",
    }


class InMemoryStoreTests(unittest.TestCase):
    def test_close_on_missing_row_opens_and_closes(self) -> None:
        store = InMemoryExecutionRecordStore()
        existing = store.close_execution(
            make_execution_record(_request()), _receipt(), True
        )
        self.assertIsNone(existing)
        row = store._by_key[("confirm-1", "call-1")]
        self.assertEqual(row["status"], "succeeded")
        self.assertEqual(row["receipt"]["request_id"], "req-1")

    def test_first_close_wins_on_open_row(self) -> None:
        store = InMemoryExecutionRecordStore()
        store._by_key[("confirm-1", "call-1")] = make_execution_record(_request())
        existing = store.close_execution(
            make_execution_record(_request()), _receipt("succeeded"), True
        )
        self.assertIsNone(existing)
        self.assertEqual(
            store._by_key[("confirm-1", "call-1")]["status"], "succeeded"
        )

    def test_late_arrival_returns_existing_receipt(self) -> None:
        store = InMemoryExecutionRecordStore()
        # The resumed stream's timeout close lands first.
        timeout_receipt = _receipt("timeout")
        store.close_execution(make_execution_record(_request()), timeout_receipt, True)
        # The worker's late completion must not overwrite it.
        existing = store.close_execution(
            make_execution_record(_request()), _receipt("succeeded"), True
        )
        self.assertEqual(existing, timeout_receipt)
        self.assertEqual(
            store._by_key[("confirm-1", "call-1")]["status"], "timeout"
        )

    def test_is_ready(self) -> None:
        self.assertTrue(InMemoryExecutionRecordStore().is_ready())


# ---------------------------------------------------------------------------
# Postgres backend against a fake driver
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, db: dict) -> None:
        self._db = db
        self.rowcount = 0
        self._rows: list = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql: str, params: dict | None = None) -> None:
        statement = sql.strip()
        self.rowcount = 0
        self._rows = []
        if statement.startswith(("CREATE TABLE", "CREATE INDEX", "DELETE FROM")):
            return
        if statement.startswith("SELECT 1"):
            self._rows = [(1,)]
            return
        params = params or {}
        key = (params.get("confirm_id"), params.get("call_id"))
        if statement.startswith("INSERT INTO execution_records"):
            if key not in self._db:
                self._db[key] = {
                    "status": "requested",
                    "receipt": None,
                }
            return
        if statement.startswith("UPDATE execution_records"):
            row = self._db.get(key)
            if row is not None and row["status"] == "requested":
                receipt = params["receipt"]
                # psycopg wraps JSONB params in Jsonb; unwrap for the fake.
                row["status"] = params["status"]
                row["receipt"] = getattr(receipt, "obj", receipt)
                self.rowcount = 1
            return
        if statement.startswith("SELECT receipt"):
            row = self._db.get(key)
            if row is not None:
                self._rows = [(row["receipt"],)]
            return

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _FakeConnection:
    def __init__(self, db: dict) -> None:
        self._db = db

    @contextmanager
    def cursor(self) -> Iterator[_FakeCursor]:
        yield _FakeCursor(self._db)

    def commit(self) -> None:
        pass

    def close(self) -> None:
        pass


def _fake_store() -> tuple[PostgresExecutionRecordStore, dict]:
    db: dict = {}

    @contextmanager
    def connect() -> Iterator[_FakeConnection]:
        yield _FakeConnection(db)

    return PostgresExecutionRecordStore("postgresql://fake", connect), db


class PostgresStoreTests(unittest.TestCase):
    def test_initialize_runs_ddl_and_sweep(self) -> None:
        store, _db = _fake_store()
        store.initialize()  # must not raise against the fake driver

    def test_close_on_missing_row_inserts_then_closes(self) -> None:
        store, db = _fake_store()
        existing = store.close_execution(
            make_execution_record(_request()), _receipt(), True
        )
        self.assertIsNone(existing)
        self.assertEqual(db[("confirm-1", "call-1")]["status"], "succeeded")

    def test_close_on_open_row_closes_once(self) -> None:
        store, db = _fake_store()
        db[("confirm-1", "call-1")] = {"status": "requested", "receipt": None}
        existing = store.close_execution(
            make_execution_record(_request()), _receipt(), True
        )
        self.assertIsNone(existing)
        self.assertEqual(db[("confirm-1", "call-1")]["status"], "succeeded")

    def test_late_arrival_returns_surviving_receipt(self) -> None:
        store, db = _fake_store()
        timeout_receipt = _receipt("timeout")
        db[("confirm-1", "call-1")] = {
            "status": "timeout",
            "receipt": timeout_receipt,
        }
        existing = store.close_execution(
            make_execution_record(_request()), _receipt("succeeded"), True
        )
        self.assertEqual(existing, timeout_receipt)
        self.assertEqual(db[("confirm-1", "call-1")]["status"], "timeout")

    def test_is_ready(self) -> None:
        store, _db = _fake_store()
        self.assertTrue(store.is_ready())


class FactoryTests(unittest.TestCase):
    def test_memory_backend(self) -> None:
        store = build_execution_record_store(ExecutionSettings())
        self.assertEqual(store.backend_name, "memory")

    def test_postgres_unavailable_falls_back_to_memory(self) -> None:
        from unittest import mock

        class _ExplodingStore:
            def __init__(self, db_url: str) -> None:
                raise RuntimeError("no postgres here")

        with mock.patch(
            "execution_runtime.services.execution_records."
            "PostgresExecutionRecordStore",
            _ExplodingStore,
        ):
            store = build_execution_record_store(
                ExecutionSettings(
                    state_store_backend="postgres",
                    state_db_url="postgresql://nowhere",
                )
            )
        self.assertEqual(store.backend_name, "memory")


if __name__ == "__main__":
    unittest.main()
