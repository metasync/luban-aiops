"""SPEC-056 R-1/R-2/R-4: the ``session_type`` birth discriminator in the store.

These tests pin the load-bearing invariants the plan names for stage 2:

- ``session_type`` round-trips on **all three** backends and defaults to
  ``operation`` (R-1); the ephemeral backends carry the default with no
  migration, Postgres with a nullable column plus the OQ-2 inference.
- it is written **exactly once** on the create path and no store or service
  method mutates it afterwards — the Protocol exposes no setter, and the
  SPEC-055 declare-target path writes the authoring-trace row and leaves the
  type untouched (R-1 immutability).
- the Postgres DDL is additive + idempotent, and its ``to_regclass`` guard
  actually defers the ``authoring_trace_target`` reference (a DO block with
  dynamic EXECUTE) instead of merely naming it in a WHERE clause; the reclaim
  branch re-types an expired row while a live conflict no-ops, and a ``NULL``
  read degrades to ``operation`` (R-1 / plan §5-6).
- ``list_sessions_by_user`` takes an optional ``session_type`` scope that
  excludes the other type, returns all when omitted, and leaves ownership
  scoping and the 50-cap unchanged (R-2 / R-4).

The behavioral backfill (a legacy NULL row with/without an authoring-trace
target → development/operation, no NULL left, second run a no-op) is exercised
against a real Postgres 16 at the Delivery Gate via ``.sqlcheck-spec056-oq2.sql``
(the SPEC-055 precedent); here the fake driver asserts the SQL shape that makes
it correct and idempotent. That real-server check is not redundant with these
tests: it is what caught the guard below being decorative, because a fake
driver never parses the SQL and a text assertion cannot tell a guard that runs
from one that only appears in the string.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

import fakeredis
import pytest

from agent_service.schemas.api import SessionRecord
from agent_service.services import session_service
from agent_service.services.authoring_trace import InMemoryAuthoringTraceStore
from agent_service.services.session_service import SESSION_LIST_CAP
from agent_service.services.session_store import (
    InMemorySessionStore,
    PostgresSessionStore,
    RedisSessionStore,
    SessionStore,
)

NOW = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)


def _fake_connect(calls: list[dict], rows=None, fail: bool = False):
    """Fake sync psycopg driver mirroring test_postgres_session_store.py."""

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


def _redis_store() -> RedisSessionStore:
    return RedisSessionStore(
        client=fakeredis.FakeRedis(decode_responses=False), ttl_seconds=60
    )


# ---------------------------------------------------------------------------
# R-1: round-trip on all three backends + default ``operation``
# ---------------------------------------------------------------------------


class TestSessionTypeRoundTrip:
    def test_memory_backend_round_trips_and_defaults(self):
        store = InMemorySessionStore()
        # Default: an omitted session_type is ``operation``.
        default = store.create_session("alice")
        assert default.session_type == "operation"
        assert store.get_session(default.session_id).session_type == "operation"
        # Explicit development round-trips through the read.
        dev = store.create_session("alice", session_type="development")
        assert dev.session_type == "development"
        assert store.get_session(dev.session_id).session_type == "development"

    def test_redis_backend_round_trips_and_defaults(self):
        store = _redis_store()
        default = store.create_session("alice")
        assert default.session_type == "operation"
        # The blob is JSON-serialized, so the type must survive the round trip.
        assert store.get_session(default.session_id).session_type == "operation"
        dev = store.create_session("alice", session_type="development")
        assert store.get_session(dev.session_id).session_type == "development"

    def test_postgres_backend_writes_type_on_insert_and_reads_it_back(self):
        # Write: the INSERT params carry the birth type.
        calls: list[dict] = []
        store = PostgresSessionStore(
            "postgresql://fake", connect=_fake_connect(calls)
        )
        record = store.create_session("alice", session_type="development")
        assert record.session_type == "development"
        insert = calls[0]
        assert "INSERT INTO sessions" in insert["sql"]
        assert insert["params"]["session_type"] == "development"
        assert "session_type" in insert["sql"]

        # Read: row[6] maps to session_type.
        read_calls: list[dict] = []
        row = ("ses-1", "alice", NOW, None, None, None, "development")
        reader = PostgresSessionStore(
            "postgresql://fake", connect=_fake_connect(read_calls, rows=[row])
        )
        assert reader.get_session("ses-1").session_type == "development"

    def test_postgres_defaults_to_operation_when_param_omitted(self):
        calls: list[dict] = []
        store = PostgresSessionStore(
            "postgresql://fake", connect=_fake_connect(calls)
        )
        record = store.create_session("alice")
        assert record.session_type == "operation"
        assert calls[0]["params"]["session_type"] == "operation"


# ---------------------------------------------------------------------------
# R-1 immutability: write-once, no setter, declare-target leaves it untouched
# ---------------------------------------------------------------------------


class TestSessionTypeImmutability:
    def test_protocol_exposes_no_session_type_setter(self):
        # Immutability has no API surface: neither the Protocol nor any backend
        # offers a way to re-type a live session.
        assert not hasattr(SessionStore, "set_session_type")
        assert not hasattr(SessionStore, "update_session_type")
        for factory in (
            InMemorySessionStore,
            _redis_store,
            lambda: PostgresSessionStore("postgresql://fake"),
        ):
            store = factory()
            assert not hasattr(store, "set_session_type")
            assert not hasattr(store, "update_session_type")

    def test_declare_target_leaves_session_type_untouched(self, monkeypatch):
        # The SPEC-055 declare-target path is the one place an operator
        # re-scopes a live session; it must write the authoring-trace target
        # and never the session's birth type.
        store = InMemorySessionStore()
        monkeypatch.setattr(session_service, "SESSION_STORE", store)
        traces = InMemoryAuthoringTraceStore()

        session = session_service.create_session("alice")  # operation by birth
        assert session.session_type == "operation"

        traces.declare_target(session.session_id, "https://admin.internal/login")
        # The target is recorded on the trace store...
        assert traces.load_for_session(session.session_id) is not None
        # ...and the session's type is unchanged.
        assert store.get_session(session.session_id).session_type == "operation"

    def test_touch_and_title_and_model_never_change_type(self, monkeypatch):
        # Every post-create bookkeeping writer leaves the birth type alone.
        store = InMemorySessionStore()
        monkeypatch.setattr(session_service, "SESSION_STORE", store)
        dev = session_service.create_session("alice", session_type="development")

        session_service.mark_session_turn(dev.session_id, "do a thing")
        session_service.pin_session_model(dev.session_id, "deepseek")
        session_service.rename_session_title(dev.session_id, "renamed", "alice")

        assert store.get_session(dev.session_id).session_type == "development"

    def test_service_create_threads_type_once(self, monkeypatch):
        store = InMemorySessionStore()
        monkeypatch.setattr(session_service, "SESSION_STORE", store)
        dev = session_service.create_session("alice", session_type="development")
        op = session_service.create_session("alice")
        assert dev.session_type == "development"
        assert op.session_type == "operation"
        # ensure_session's create branch (session_id=None) threads it too.
        ensured = session_service.ensure_session(None, "alice", "development")
        assert ensured.session_type == "development"


# ---------------------------------------------------------------------------
# R-1 / plan §5-6: Postgres DDL, backfill, reclaim, mapper default
# ---------------------------------------------------------------------------


class TestPostgresDDLAndBackfill:
    def _ddl(self) -> str:
        calls: list[dict] = []
        store = PostgresSessionStore(
            "postgresql://fake", connect=_fake_connect(calls)
        )
        store.initialize()
        return calls[0]["sql"]

    def test_create_table_declares_session_type_column(self):
        ddl = self._ddl()
        assert "session_type     TEXT" in ddl or "session_type TEXT" in ddl

    def test_additive_alter_is_idempotent_and_nullable(self):
        ddl = self._ddl()
        # Nullable + IF NOT EXISTS: the house additive-column convention, and
        # what leaves legacy rows NULL for the inference to key on.
        assert (
            "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS session_type TEXT"
            in ddl
        )

    def test_oq2_backfill_infers_from_authoring_trace_target(self):
        ddl = self._ddl()
        # development for a session already holding a declared target...
        assert "SET session_type = 'development'" in ddl
        assert "authoring_trace_target" in ddl
        assert "session_id IN (SELECT session_id FROM authoring_trace_target)" in ddl
        # ...operation otherwise, and never leaving a row NULL.
        assert "SET session_type = 'operation' WHERE session_type IS NULL" in ddl

    def test_backfill_is_null_keyed_for_idempotency(self):
        # Both UPDATEs key on IS NULL, so a re-run finds no row to touch.
        ddl = self._ddl()
        dev_update = ddl.split("SET session_type = 'development'")[1]
        assert "session_type IS NULL" in dev_update.split(";")[0]

    def test_backfill_guard_defers_the_relation_reference(self):
        # The ``to_regclass`` guard protects the inference only if the
        # ``authoring_trace_target`` reference is resolved *after* the guard has
        # been evaluated. In a plain UPDATE PostgreSQL resolves the relation
        # inside the ``IN (SELECT ...)`` subquery at parse-analysis time, before
        # any predicate runs, so the guard is decorative: a cluster whose
        # SPEC-055 authoring-trace DDL had not run would abort the whole schema
        # bootstrap with "relation does not exist" — a hard startup failure in
        # exactly the situation the guard exists for. The DO block + dynamic
        # EXECUTE is what moves that resolution inside the IF. Verified against
        # a real Postgres 16 by ``.sqlcheck-spec056-oq2.sql`` step 5.
        ddl = self._ddl()
        assert "to_regclass('authoring_trace_target') IS NOT NULL" in ddl
        # What the server parses is the DDL minus its ``--`` commentary — the
        # guard's own explanation names the relation, so strip comments before
        # asking where the reference is actually resolved.
        sql = "\n".join(
            line
            for line in ddl.splitlines()
            if not line.lstrip().startswith("--")
        )
        guard = sql.split("DO $$", 1)[1].split("$$;", 1)[0]
        # The conditional relation is referenced only inside the deferred text.
        assert "EXECUTE" in guard
        assert "FROM authoring_trace_target" in guard
        static = sql.split("DO $$", 1)[0] + sql.split("$$;", 1)[1]
        assert "authoring_trace_target" not in static
        # The operation fallback stays a plain statement: it references no
        # conditional relation, so it needs no guard and must still leave no row
        # NULL when the inference was skipped.
        assert (
            "SET session_type = 'operation' WHERE session_type IS NULL" in static
        )

    def test_insert_reclaim_sets_type_live_conflict_noops(self):
        calls: list[dict] = []
        store = PostgresSessionStore(
            "postgresql://fake", connect=_fake_connect(calls)
        )
        store.create_session("alice", session_type="development")
        sql = calls[0]["sql"]
        # Reclaiming an expired row is a fresh creation, so it takes the new
        # caller's type...
        assert "session_type = EXCLUDED.session_type" in sql
        # ...but the WHERE idle-TTL guard makes a live conflict a no-op, which
        # is the immutability boundary (a live named session keeps its type).
        assert "WHERE sessions.last_accessed_at <= now() - make_interval" in sql

    def test_null_type_read_degrades_to_operation(self):
        # A NULL row (impossible post-migration) still maps to ``operation``
        # rather than erroring, on both the single-row and list mappers.
        calls: list[dict] = []
        null_row = ("ses-1", "alice", NOW, None, None, None, None)
        store = PostgresSessionStore(
            "postgresql://fake", connect=_fake_connect(calls, rows=[null_row])
        )
        assert store.get_session("ses-1").session_type == "operation"

        list_calls: list[dict] = []
        lister = PostgresSessionStore(
            "postgresql://fake",
            connect=_fake_connect(list_calls, rows=[null_row]),
        )
        assert lister.list_sessions_by_user("alice")[0].session_type == "operation"


# ---------------------------------------------------------------------------
# R-2 / R-4: the optional list filter, ownership and cap unchanged
# ---------------------------------------------------------------------------


class TestSessionTypeListFilter:
    def _seed(self, store):
        store.create_session("alice", session_id="op-1", session_type="operation")
        store.create_session(
            "alice", session_id="dev-1", session_type="development"
        )
        store.create_session("bob", session_id="op-bob", session_type="operation")
        return store

    @pytest.mark.parametrize(
        "factory",
        [
            pytest.param(InMemorySessionStore, id="memory"),
            pytest.param(_redis_store, id="redis"),
        ],
    )
    def test_filter_scopes_by_type_and_omitted_returns_all(self, factory):
        store = self._seed(factory())
        ops = store.list_sessions_by_user("alice", session_type="operation")
        assert {s.session_id for s in ops} == {"op-1"}
        devs = store.list_sessions_by_user("alice", session_type="development")
        assert {s.session_id for s in devs} == {"dev-1"}
        everything = store.list_sessions_by_user("alice")
        assert {s.session_id for s in everything} == {"op-1", "dev-1"}

    @pytest.mark.parametrize(
        "factory",
        [
            pytest.param(InMemorySessionStore, id="memory"),
            pytest.param(_redis_store, id="redis"),
        ],
    )
    def test_ownership_scoping_is_unchanged(self, factory):
        store = self._seed(factory())
        # A filter never widens ownership: bob's operation session is not
        # alice's to list, filtered or not (anti-enumeration preserved).
        alice_ops = store.list_sessions_by_user("alice", session_type="operation")
        assert all(s.user_id == "alice" for s in alice_ops)
        assert "op-bob" not in {s.session_id for s in alice_ops}

    def test_postgres_filter_passes_param_and_scopes_in_sql(self):
        calls: list[dict] = []
        store = PostgresSessionStore(
            "postgresql://fake", connect=_fake_connect(calls, rows=[])
        )
        store.list_sessions_by_user("alice", session_type="development")
        sql = calls[0]["sql"]
        assert calls[0]["params"]["session_type"] == "development"
        # NULL-tolerant predicate: an omitted filter is byte-for-byte legacy.
        assert "%(session_type)s::text IS NULL" in sql
        assert "COALESCE(session_type, 'operation') = %(session_type)s::text" in sql

    def test_service_list_scopes_and_caps(self, monkeypatch):
        store = InMemorySessionStore()
        monkeypatch.setattr(session_service, "SESSION_STORE", store)
        store.create_session("alice", session_type="development")
        for i in range(SESSION_LIST_CAP + 5):
            store.create_session("alice", session_type="operation")

        ops = session_service.list_sessions("alice", session_type="operation")
        assert all(s.session_type == "operation" for s in ops)
        # The 50-cap is unchanged by the filter.
        assert len(ops) == SESSION_LIST_CAP
        devs = session_service.list_sessions("alice", session_type="development")
        assert len(devs) == 1
        # Omitted filter returns everything (still capped).
        assert len(session_service.list_sessions("alice")) == SESSION_LIST_CAP


def test_session_record_model_default_is_operation():
    # The Pydantic default is what keeps ephemeral backends and pre-SPEC-056
    # rows correct with no migration.
    record = SessionRecord(
        session_id="ses-1", user_id="alice", created_at=NOW
    )
    assert record.session_type == "operation"
