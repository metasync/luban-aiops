"""Postgres session store tests (SPEC-016).

Exercises PostgresSessionStore against a fake sync psycopg driver
(audit-service / incident-service pattern) and the build_session_store
factory's postgres branch.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from prometheus_client import REGISTRY

from agent_service.services.session_store import (
    InMemorySessionStore,
    PostgresSessionStore,
    build_session_store,
)

NOW = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)


def _error_count(operation: str) -> float:
    return (
        REGISTRY.get_sample_value(
            "session_store_errors_total", {"operation": operation}
        )
        or 0.0
    )


def _fallback_count() -> float:
    return REGISTRY.get_sample_value("session_store_fallbacks_total") or 0.0


def _fake_connect(calls: list[dict], rows=None, fail: bool = False):
    """Build a fake sync connect factory mirroring the audit-service pattern."""

    class FakeCursor:
        def execute(self, sql, params=None):
            if fail:
                raise RuntimeError("connection refused")
            calls.append({"sql": sql, "params": params})

        def fetchone(self):
            return rows[0] if rows else None

        def fetchall(self):
            return rows or []

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def commit(self):
            return None

        def close(self):
            return None

    @contextmanager
    def connect():
        yield FakeConn()

    return connect


# ---------------------------------------------------------------------------
# PostgresSessionStore SQL shape
# ---------------------------------------------------------------------------


class TestPostgresSessionStore:
    def test_backend_name(self):
        store = PostgresSessionStore("postgresql://fake")
        assert store.backend_name == "postgres"

    def test_initialize_runs_ddl(self):
        calls: list[dict] = []
        store = PostgresSessionStore(
            "postgresql://fake", connect=_fake_connect(calls)
        )
        store.initialize()
        assert "CREATE TABLE IF NOT EXISTS sessions" in calls[0]["sql"]
        assert "idx_sessions_user" in calls[0]["sql"]
        assert "idx_sessions_accessed" in calls[0]["sql"]

    def test_create_session_inserts_and_sweeps(self):
        calls: list[dict] = []
        store = PostgresSessionStore(
            "postgresql://fake", ttl_seconds=600, connect=_fake_connect(calls)
        )
        record = store.create_session("alice", session_id="ses-fixed")
        assert record.session_id == "ses-fixed"
        assert record.user_id == "alice"

        insert = calls[0]
        assert "INSERT INTO sessions" in insert["sql"]
        assert insert["params"]["session_id"] == "ses-fixed"
        assert insert["params"]["user_id"] == "alice"
        # Conflict-safe insert: expired-but-unswept rows are reclaimed and
        # live conflicts no-op (create_named_session re-read resolves them),
        # never raising UniqueViolation as a 500.
        assert "ON CONFLICT (session_id) DO UPDATE" in insert["sql"]
        assert insert["params"]["ttl_seconds"] == 600

        sweep = calls[1]
        assert "DELETE FROM sessions" in sweep["sql"]
        assert sweep["params"]["ttl_seconds"] == 600
        assert sweep["params"]["sweep_limit"] == 100

    def test_create_session_generates_id(self):
        calls: list[dict] = []
        store = PostgresSessionStore(
            "postgresql://fake", connect=_fake_connect(calls)
        )
        record = store.create_session("alice")
        assert record.session_id.startswith("ses-")

    def test_get_session_refreshes_ttl_and_maps_row(self):
        calls: list[dict] = []
        row = ("ses-1", "alice", NOW)
        store = PostgresSessionStore(
            "postgresql://fake", ttl_seconds=600,
            connect=_fake_connect(calls, rows=[row]),
        )
        fetched = store.get_session("ses-1")
        assert fetched is not None
        assert fetched.session_id == "ses-1"
        assert fetched.user_id == "alice"
        assert fetched.created_at == NOW

        sql = calls[0]["sql"]
        assert "UPDATE sessions" in sql
        assert "RETURNING session_id, user_id, created_at" in sql
        # Idle-TTL predicate folded into the read.
        assert "last_accessed_at > now() - make_interval" in sql
        assert calls[0]["params"]["ttl_seconds"] == 600

    def test_get_session_missing_returns_none(self):
        calls: list[dict] = []
        store = PostgresSessionStore(
            "postgresql://fake", connect=_fake_connect(calls)
        )
        assert store.get_session("ses-nope") is None

    def test_list_sessions_by_user(self):
        calls: list[dict] = []
        rows = [("ses-1", "alice", NOW), ("ses-2", "alice", NOW)]
        store = PostgresSessionStore(
            "postgresql://fake", connect=_fake_connect(calls, rows=rows)
        )
        sessions = store.list_sessions_by_user("alice")
        assert [s.session_id for s in sessions] == ["ses-1", "ses-2"]
        sql = calls[0]["sql"]
        assert "user_id = %(user_id)s" in sql
        assert "ORDER BY created_at" in sql

    def test_delete_session_true_when_row_returned(self):
        calls: list[dict] = []
        store = PostgresSessionStore(
            "postgresql://fake", connect=_fake_connect(calls, rows=[("ses-1",)])
        )
        assert store.delete_session("ses-1") is True
        assert "RETURNING session_id" in calls[0]["sql"]

    def test_delete_session_false_when_missing(self):
        calls: list[dict] = []
        store = PostgresSessionStore(
            "postgresql://fake", connect=_fake_connect(calls)
        )
        assert store.delete_session("ses-nope") is False

    def test_len_counts_non_expired(self):
        calls: list[dict] = []
        store = PostgresSessionStore(
            "postgresql://fake", ttl_seconds=600,
            connect=_fake_connect(calls, rows=[(7,)]),
        )
        assert len(store) == 7
        assert "COUNT(*)" in calls[0]["sql"]
        assert calls[0]["params"]["ttl_seconds"] == 600

    def test_is_ready_true_when_select_succeeds(self):
        calls: list[dict] = []
        store = PostgresSessionStore(
            "postgresql://fake", connect=_fake_connect(calls, rows=[(1,)])
        )
        assert store.is_ready() is True

    def test_is_ready_false_when_connect_fails(self):
        calls: list[dict] = []
        store = PostgresSessionStore(
            "postgresql://fake", connect=_fake_connect(calls, fail=True)
        )
        assert store.is_ready() is False

    def test_operation_failure_records_error_and_raises(self):
        calls: list[dict] = []
        store = PostgresSessionStore(
            "postgresql://fake", connect=_fake_connect(calls, fail=True)
        )
        before = _error_count("create")
        with pytest.raises(RuntimeError):
            store.create_session("alice")
        assert _error_count("create") == before + 1

        before = _error_count("get")
        with pytest.raises(RuntimeError):
            store.get_session("ses-1")
        assert _error_count("get") == before + 1

    def test_len_returns_zero_on_failure(self):
        calls: list[dict] = []
        store = PostgresSessionStore(
            "postgresql://fake", connect=_fake_connect(calls, fail=True)
        )
        assert len(store) == 0


# ---------------------------------------------------------------------------
# Factory: postgres branch
# ---------------------------------------------------------------------------


class TestBuildSessionStorePostgres:
    def test_postgres_backend_selected(self, monkeypatch):
        calls: list[dict] = []
        monkeypatch.setenv("SESSION_STORE_BACKEND", "postgres")
        monkeypatch.setenv("SESSION_DB_URL", "postgresql://fake/sessions")
        monkeypatch.setattr(
            PostgresSessionStore,
            "_default_connect",
            lambda self: _fake_connect(calls, rows=[(1,)])(),
        )
        store = build_session_store()
        assert isinstance(store, PostgresSessionStore)
        assert store.backend_name == "postgres"
        # initialize() applied the DDL.
        assert "CREATE TABLE IF NOT EXISTS sessions" in calls[0]["sql"]

    def test_postgres_without_dsn_fails_startup(self, monkeypatch):
        monkeypatch.setenv("SESSION_STORE_BACKEND", "postgres")
        monkeypatch.delenv("SESSION_DB_URL", raising=False)
        with pytest.raises(ValueError, match="SESSION_DB_URL"):
            build_session_store()

    def test_postgres_unreachable_falls_back_to_memory(self, monkeypatch):
        monkeypatch.setenv("SESSION_STORE_BACKEND", "postgres")
        monkeypatch.setenv("SESSION_DB_URL", "postgresql://fake/sessions")
        monkeypatch.setattr(
            PostgresSessionStore,
            "_default_connect",
            lambda self: _fake_connect([], fail=True)(),
        )
        before = _fallback_count()
        store = build_session_store()
        assert isinstance(store, InMemorySessionStore)
        assert _fallback_count() == before + 1

    def test_ttl_propagated_to_postgres(self, monkeypatch):
        calls: list[dict] = []
        monkeypatch.setenv("SESSION_STORE_BACKEND", "postgres")
        monkeypatch.setenv("SESSION_DB_URL", "postgresql://fake/sessions")
        monkeypatch.setenv("SESSION_TTL_SECONDS", "300")
        monkeypatch.setattr(
            PostgresSessionStore,
            "_default_connect",
            lambda self: _fake_connect(calls)(),
        )
        store = build_session_store()
        assert store.ttl_seconds == 300.0

    def test_unknown_backend_fails_startup(self, monkeypatch):
        monkeypatch.setenv("SESSION_STORE_BACKEND", "sqlite")
        with pytest.raises(ValueError, match="Unknown SESSION_STORE_BACKEND"):
            build_session_store()
