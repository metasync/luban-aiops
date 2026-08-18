"""Agent state store tests (SPEC-017 R-3).

Exercises InMemoryAgentStateStore, PostgresAgentStateStore against a fake
sync psycopg driver (SPEC-016 pattern), and the build_agent_state_store
factory's backend branches.
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import pytest
from prometheus_client import REGISTRY

from agent_service.services.agent_state_store import (
    DEFAULT_STATE_TTL_SECONDS,
    InMemoryAgentStateStore,
    PostgresAgentStateStore,
    build_agent_state_store,
)


def _error_count(operation: str) -> float:
    return (
        REGISTRY.get_sample_value(
            "agent_state_errors_total", {"operation": operation}
        )
        or 0.0
    )


def _fallback_count() -> float:
    return REGISTRY.get_sample_value("agent_state_fallbacks_total") or 0.0


def _fake_connect(calls: list[dict], rows=None, fail: bool = False):
    """Build a fake sync connect factory mirroring the SPEC-016 pattern."""

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
# InMemoryAgentStateStore
# ---------------------------------------------------------------------------


class TestInMemoryAgentStateStore:
    def test_backend_name_and_ready(self):
        store = InMemoryAgentStateStore()
        assert store.backend_name == "memory"
        assert store.is_ready() is True

    def test_save_load_round_trip(self):
        store = InMemoryAgentStateStore()
        store.save_state("ses-1", '{"session_id": "ses-1"}')
        assert store.load_state("ses-1") == '{"session_id": "ses-1"}'

    def test_load_missing_returns_none(self):
        store = InMemoryAgentStateStore()
        assert store.load_state("ses-nope") is None

    def test_save_overwrites_previous_snapshot(self):
        store = InMemoryAgentStateStore()
        store.save_state("ses-1", '{"turn": 1}')
        store.save_state("ses-1", '{"turn": 2}')
        assert store.load_state("ses-1") == '{"turn": 2}'
        assert len(store) == 1

    def test_delete_state_reports_presence(self):
        store = InMemoryAgentStateStore()
        store.save_state("ses-1", "{}")
        assert store.delete_state("ses-1") is True
        assert store.delete_state("ses-1") is False
        assert store.load_state("ses-1") is None


# ---------------------------------------------------------------------------
# PostgresAgentStateStore SQL shape
# ---------------------------------------------------------------------------


class TestPostgresAgentStateStore:
    def test_backend_name(self):
        store = PostgresAgentStateStore("postgresql://fake")
        assert store.backend_name == "postgres"

    def test_initialize_runs_ddl(self):
        calls: list[dict] = []
        store = PostgresAgentStateStore(
            "postgresql://fake", connect=_fake_connect(calls)
        )
        store.initialize()
        assert "CREATE TABLE IF NOT EXISTS agent_states" in calls[0]["sql"]
        assert "idx_agent_states_updated" in calls[0]["sql"]

    def test_save_state_upserts_and_sweeps(self):
        calls: list[dict] = []
        store = PostgresAgentStateStore(
            "postgresql://fake", ttl_seconds=600, connect=_fake_connect(calls)
        )
        store.save_state("ses-1", '{"turn": 1}')

        upsert = calls[0]
        assert "INSERT INTO agent_states" in upsert["sql"]
        assert "ON CONFLICT (session_id)" in upsert["sql"]
        assert upsert["params"]["session_id"] == "ses-1"
        # JSONB is written as a JSON string, never a raw dict.
        assert upsert["params"]["state"] == '{"turn": 1}'

        sweep = calls[1]
        assert "DELETE FROM agent_states" in sweep["sql"]
        assert sweep["params"]["ttl_seconds"] == 600
        assert sweep["params"]["sweep_limit"] == 100

    def test_load_state_reserializes_jsonb_dict(self):
        calls: list[dict] = []
        store = PostgresAgentStateStore(
            "postgresql://fake",
            connect=_fake_connect(calls, rows=[({"turn": 1},)]),
        )
        loaded = store.load_state("ses-1")
        assert json.loads(loaded) == {"turn": 1}
        # The read folds in a TTL refresh so a live session's snapshot is
        # never swept while it is still being restored.
        sql = calls[0]["sql"]
        assert "UPDATE agent_states" in sql
        assert "SET updated_at = now()" in sql
        assert "RETURNING state" in sql

    def test_load_state_passthrough_string(self):
        calls: list[dict] = []
        store = PostgresAgentStateStore(
            "postgresql://fake",
            connect=_fake_connect(calls, rows=[('{"turn": 1}',)]),
        )
        assert store.load_state("ses-1") == '{"turn": 1}'

    def test_load_state_missing_returns_none(self):
        calls: list[dict] = []
        store = PostgresAgentStateStore(
            "postgresql://fake", connect=_fake_connect(calls)
        )
        assert store.load_state("ses-nope") is None

    def test_delete_state_true_when_row_returned(self):
        calls: list[dict] = []
        store = PostgresAgentStateStore(
            "postgresql://fake", connect=_fake_connect(calls, rows=[("ses-1",)])
        )
        assert store.delete_state("ses-1") is True
        assert "RETURNING session_id" in calls[0]["sql"]

    def test_delete_state_false_when_missing(self):
        calls: list[dict] = []
        store = PostgresAgentStateStore(
            "postgresql://fake", connect=_fake_connect(calls)
        )
        assert store.delete_state("ses-nope") is False

    def test_is_ready_true_when_select_succeeds(self):
        calls: list[dict] = []
        store = PostgresAgentStateStore(
            "postgresql://fake", connect=_fake_connect(calls, rows=[(1,)])
        )
        assert store.is_ready() is True

    def test_is_ready_false_when_connect_fails(self):
        calls: list[dict] = []
        store = PostgresAgentStateStore(
            "postgresql://fake", connect=_fake_connect(calls, fail=True)
        )
        assert store.is_ready() is False

    def test_operation_failure_records_error_and_raises(self):
        calls: list[dict] = []
        store = PostgresAgentStateStore(
            "postgresql://fake", connect=_fake_connect(calls, fail=True)
        )
        before = _error_count("save")
        with pytest.raises(RuntimeError):
            store.save_state("ses-1", "{}")
        assert _error_count("save") == before + 1

        before = _error_count("load")
        with pytest.raises(RuntimeError):
            store.load_state("ses-1")
        assert _error_count("load") == before + 1

        before = _error_count("delete")
        with pytest.raises(RuntimeError):
            store.delete_state("ses-1")
        assert _error_count("delete") == before + 1


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestBuildAgentStateStore:
    def test_memory_backend_is_default(self, monkeypatch):
        monkeypatch.delenv("AGENT_STATE_STORE_BACKEND", raising=False)
        store = build_agent_state_store()
        assert isinstance(store, InMemoryAgentStateStore)

    def test_postgres_backend_selected(self, monkeypatch):
        calls: list[dict] = []
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "postgres")
        monkeypatch.setenv("AGENT_STATE_DB_URL", "postgresql://fake/sessions")
        monkeypatch.setattr(
            PostgresAgentStateStore,
            "_default_connect",
            lambda self: _fake_connect(calls, rows=[(1,)])(),
        )
        store = build_agent_state_store()
        assert isinstance(store, PostgresAgentStateStore)
        assert store.backend_name == "postgres"
        # initialize() applied the DDL.
        assert "CREATE TABLE IF NOT EXISTS agent_states" in calls[0]["sql"]

    def test_postgres_without_dsn_fails_startup(self, monkeypatch):
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "postgres")
        monkeypatch.delenv("AGENT_STATE_DB_URL", raising=False)
        with pytest.raises(ValueError, match="AGENT_STATE_DB_URL"):
            build_agent_state_store()

    def test_postgres_unreachable_falls_back_to_memory(self, monkeypatch):
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "postgres")
        monkeypatch.setenv("AGENT_STATE_DB_URL", "postgresql://fake/sessions")
        monkeypatch.setattr(
            PostgresAgentStateStore,
            "_default_connect",
            lambda self: _fake_connect([], fail=True)(),
        )
        before = _fallback_count()
        store = build_agent_state_store()
        assert isinstance(store, InMemoryAgentStateStore)
        assert _fallback_count() == before + 1

    def test_ttl_propagated_to_postgres(self, monkeypatch):
        calls: list[dict] = []
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "postgres")
        monkeypatch.setenv("AGENT_STATE_DB_URL", "postgresql://fake/sessions")
        monkeypatch.setenv("AGENT_STATE_TTL_SECONDS", "300")
        monkeypatch.setattr(
            PostgresAgentStateStore,
            "_default_connect",
            lambda self: _fake_connect(calls)(),
        )
        store = build_agent_state_store()
        assert store.ttl_seconds == 300.0

    def test_default_ttl(self, monkeypatch):
        monkeypatch.delenv("AGENT_STATE_TTL_SECONDS", raising=False)
        calls: list[dict] = []
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "postgres")
        monkeypatch.setenv("AGENT_STATE_DB_URL", "postgresql://fake/sessions")
        monkeypatch.setattr(
            PostgresAgentStateStore,
            "_default_connect",
            lambda self: _fake_connect(calls)(),
        )
        store = build_agent_state_store()
        assert store.ttl_seconds == DEFAULT_STATE_TTL_SECONDS

    def test_unknown_backend_fails_startup(self, monkeypatch):
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "redis")
        with pytest.raises(ValueError, match="Unknown AGENT_STATE_STORE_BACKEND"):
            build_agent_state_store()
