"""SPEC-055 R-1: the durable authoring-trace store.

Covers both backends (in-memory semantics, Postgres SQL shape via a fake
driver), the factory's backend selection and its two knobs, and the four
R-1 invariants: every schema field exists on **both** backends (the
skills-hub ``web_target``/``risk_class`` lesson — a field on one backend
only is silently dropped in production), the per-session step cap drops
capture beyond the bound, the lifecycle is ``draft → graduated |
discarded`` and terminal, and the idle-GC reclaims idle ``draft`` traces
while never touching a terminal one.

The Postgres append also takes a transaction-scoped per-session advisory
lock before it writes: the step *cap* is atomic on the insert alone, but
the never-reopen guard reads the session's statuses in the same statement
that writes the new row, so without the lock a ``close_trace`` committing
in between would leave a trailing draft row behind the terminal ones.

R-4 adds the trace's two forms of **target**: ``authoring_trace_target``
holds the origin an operator declared when opening a skill-development
session (up front, so it is an authorization scope, not a post-hoc claim),
and ``flow_origin`` on each step holds the origin the gateway reported the
interaction actually landed on. Both are asserted here on **both** backends
— first-declaration-wins and first-observation-wins are the invariants that
make them usable as evidence rather than as decoration — plus
``origin_of_url``, the deliberate twin of the tool-gateway's ``origin_of``
whose agreement graduation depends on, and ``skill_target_scope``, which
reduces a declaration to the origin and path a replay is bound by.

A store *write* failure propagates to the caller by design — same
posture as ``execution_records``, whose best-effort guard lives at the
kernel seam (``_persist_execution_request``). R-2 lands the matching
guard for trace capture; what degrades without raising here is the store
selection (an unreachable Postgres falls back to memory) and
``is_ready()``.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest

from agent_service.services.authoring_trace import (
    DEFAULT_IDLE_DAYS,
    DEFAULT_MAX_STEPS,
    TRACE_DRAFT,
    AuthoringTraceStore,
    InMemoryAuthoringTraceStore,
    PostgresAuthoringTraceStore,
    build_authoring_trace_store,
    make_trace_step,
    origin_of_url,
    skill_target_scope,
)


def _step(
    session_id: str = "ses-1",
    tool_name: str = "k8s.restart_service",
    args: dict | None = None,
    captured_at: str = "2026-09-08T10:00:00Z",
    execution_id: str | None = "exec-call-1",
    confirm_id: str | None = "cf-1",
    flow_origin: str | None = None,
) -> dict:
    return make_trace_step(
        session_id=session_id,
        tool_name=tool_name,
        args={"namespace": "ops"} if args is None else args,
        captured_at=captured_at,
        execution_id=execution_id,
        confirm_id=confirm_id,
        flow_origin=flow_origin,
    )


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("AGENT_STATE_STORE_BACKEND", raising=False)
    monkeypatch.delenv("AGENT_STATE_DB_URL", raising=False)
    monkeypatch.delenv("AGENT_AUTHORING_TRACE_MAX_STEPS", raising=False)
    monkeypatch.delenv("AGENT_AUTHORING_TRACE_IDLE_DAYS", raising=False)


# --- In-memory store semantics ---


class TestInMemoryStore:
    def test_append_assigns_per_session_positions_in_order(self) -> None:
        store = InMemoryAuthoringTraceStore()
        assert store.append_step(_step(tool_name="k8s.scale_deployment")) is True
        assert store.append_step(_step(tool_name="k8s.restart_service")) is True
        rows = store.load_for_session("ses-1")
        # The store owns the ordinal: capture order is the replay order.
        assert [row["position"] for row in rows] == [1, 2]
        assert [row["tool_name"] for row in rows] == [
            "k8s.scale_deployment",
            "k8s.restart_service",
        ]
        assert all(row["status"] == TRACE_DRAFT for row in rows)

    def test_positions_are_per_session(self) -> None:
        store = InMemoryAuthoringTraceStore()
        store.append_step(_step(session_id="ses-1"))
        store.append_step(_step(session_id="ses-2", tool_name="web.click"))
        assert [row["position"] for row in store.load_for_session("ses-1")] == [1]
        assert [row["position"] for row in store.load_for_session("ses-2")] == [1]

    def test_load_is_session_scoped_and_copies_rows(self) -> None:
        store = InMemoryAuthoringTraceStore()
        store.append_step(_step(session_id="ses-1"))
        store.append_step(_step(session_id="ses-2", tool_name="web.click"))
        rows = store.load_for_session("ses-1")
        assert len(rows) == 1
        assert store.load_for_session("ses-3") == []
        # A caller mutating a loaded row cannot corrupt the stored trace.
        rows[0]["args"]["namespace"] = "tampered"
        assert store.load_for_session("ses-1")[0]["args"] == {"namespace": "ops"}

    def test_nested_args_are_not_aliased_in_or_out(self) -> None:
        store = InMemoryAuthoringTraceStore()
        source = {"spec": {"replicas": 3}}
        store.append_step(_step(args=source))
        # The capturing seam still holds the parsed tool call; mutating it
        # afterwards must not retro-edit the trace a graduation replays.
        source["spec"]["replicas"] = 99
        rows = store.load_for_session("ses-1")
        assert rows[0]["args"] == {"spec": {"replicas": 3}}
        # Nor may a reader shaping a draft mutate the stored provenance.
        rows[0]["args"]["spec"]["replicas"] = 1
        assert store.load_for_session("ses-1")[0]["args"] == {
            "spec": {"replicas": 3}
        }

    def test_references_not_receipts_ride_the_step(self) -> None:
        store = InMemoryAuthoringTraceStore()
        store.append_step(_step())
        row = store.load_for_session("ses-1")[0]
        assert row["execution_id"] == "exec-call-1"
        assert row["confirm_id"] == "cf-1"
        assert row["captured_at"] == "2026-09-08T10:00:00Z"
        # The signed receipt and outcome stay in execution_records.
        assert "receipt" not in row
        assert "signature" not in row
        assert "args_digest" not in row

    def test_step_cap_drops_capture_beyond_the_bound(self) -> None:
        store = InMemoryAuthoringTraceStore(max_steps=2)
        assert store.append_step(_step(tool_name="k8s.scale_deployment")) is True
        assert store.append_step(_step(tool_name="k8s.restart_service")) is True
        # Beyond the cap the capture drops best-effort: no raise, no row.
        assert store.append_step(_step(tool_name="k8s.delete_pod")) is False
        rows = store.load_for_session("ses-1")
        assert [row["position"] for row in rows] == [1, 2]
        assert [row["tool_name"] for row in rows] == [
            "k8s.scale_deployment",
            "k8s.restart_service",
        ]

    def test_cap_is_counted_per_session(self) -> None:
        store = InMemoryAuthoringTraceStore(max_steps=1)
        assert store.append_step(_step(session_id="ses-1")) is True
        assert store.append_step(_step(session_id="ses-1")) is False
        # One session at its cap never blocks another session's trace.
        assert store.append_step(_step(session_id="ses-2")) is True

    def test_append_to_a_closed_trace_is_refused(self) -> None:
        store = InMemoryAuthoringTraceStore()
        store.append_step(_step())
        assert store.close_trace("ses-1", "graduated") is True
        # A graduated trace is the provenance of a published draft: a later
        # approval never reopens it or adds a step the skill does not have.
        assert store.append_step(_step(tool_name="k8s.delete_pod")) is False
        assert len(store.load_for_session("ses-1")) == 1

    def test_close_trace_graduates_and_first_close_wins(self) -> None:
        store = InMemoryAuthoringTraceStore()
        store.append_step(_step())
        store.append_step(_step(tool_name="k8s.delete_pod"))
        assert store.trace_status("ses-1") == TRACE_DRAFT
        assert store.close_trace("ses-1", "graduated") is True
        assert store.trace_status("ses-1") == "graduated"
        assert all(
            row["status"] == "graduated" for row in store.load_for_session("ses-1")
        )
        # Terminal is terminal: neither a re-graduate nor a discard lands.
        assert store.close_trace("ses-1", "graduated") is False
        assert store.close_trace("ses-1", "discarded") is False
        assert store.trace_status("ses-1") == "graduated"

    def test_close_trace_discards(self) -> None:
        store = InMemoryAuthoringTraceStore()
        store.append_step(_step())
        assert store.close_trace("ses-1", "discarded") is True
        assert store.trace_status("ses-1") == "discarded"
        assert store.close_trace("ses-1", "graduated") is False
        assert store.trace_status("ses-1") == "discarded"

    def test_close_trace_rejects_a_non_terminal_status(self) -> None:
        store = InMemoryAuthoringTraceStore()
        store.append_step(_step())
        with pytest.raises(ValueError, match="Unknown authoring-trace status"):
            store.close_trace("ses-1", TRACE_DRAFT)
        with pytest.raises(ValueError, match="Unknown authoring-trace status"):
            store.close_trace("ses-1", "published")
        assert store.trace_status("ses-1") == TRACE_DRAFT

    def test_close_trace_on_an_unknown_session_is_a_noop(self) -> None:
        store = InMemoryAuthoringTraceStore()
        assert store.close_trace("nope", "graduated") is False
        assert store.trace_status("nope") is None

    def test_idle_gc_reclaims_a_draft_trace_and_never_a_terminal_one(self) -> None:
        store = InMemoryAuthoringTraceStore(idle_days=180)
        now = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)
        stale = (now - timedelta(days=181)).strftime("%Y-%m-%dT%H:%M:%SZ")
        store.append_step(_step(session_id="ses-draft", captured_at=stale))
        store.append_step(_step(session_id="ses-graduated", captured_at=stale))
        store.append_step(_step(session_id="ses-discarded", captured_at=stale))
        store.append_step(
            _step(session_id="ses-fresh", captured_at="2026-09-08T11:00:00Z")
        )
        store.close_trace("ses-graduated", "graduated")
        store.close_trace("ses-discarded", "discarded")

        assert store.sweep_idle(now=now) == 1
        # Only the idle draft is gone; both terminal traces survive the
        # sweep even though their steps are just as old.
        assert store.load_for_session("ses-draft") == []
        assert store.trace_status("ses-draft") is None
        assert len(store.load_for_session("ses-graduated")) == 1
        assert len(store.load_for_session("ses-discarded")) == 1
        assert len(store.load_for_session("ses-fresh")) == 1

    def test_idle_gc_measures_idleness_from_the_newest_step(self) -> None:
        store = InMemoryAuthoringTraceStore(idle_days=180)
        now = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)
        stale = (now - timedelta(days=400)).strftime("%Y-%m-%dT%H:%M:%SZ")
        fresh = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        store.append_step(_step(session_id="ses-1", captured_at=stale))
        store.append_step(_step(session_id="ses-1", captured_at=fresh))
        # Idleness belongs to the trace, not to one old step: a session
        # appended to yesterday is not reclaimable, and sweeping the old
        # row alone would hole the trace the graduation reads.
        assert store.sweep_idle(now=now) == 0
        assert [row["position"] for row in store.load_for_session("ses-1")] == [1, 2]

    def test_idle_gc_disabled_at_zero_days(self) -> None:
        store = InMemoryAuthoringTraceStore(idle_days=0)
        store.append_step(_step(captured_at="2020-01-01T00:00:00Z"))
        assert store.sweep_idle(now=datetime(2026, 9, 8, tzinfo=timezone.utc)) == 0
        assert len(store.load_for_session("ses-1")) == 1

    def test_idle_gc_skips_a_trace_it_cannot_date(self) -> None:
        store = InMemoryAuthoringTraceStore(idle_days=180)
        now = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)
        store.append_step(_step(session_id="ses-undatable", captured_at="nonsense"))
        # The sweep must neither raise on the malformed stamp nor reclaim a
        # trace it cannot prove is idle.
        assert store.sweep_idle(now=now) == 0
        assert len(store.load_for_session("ses-undatable")) == 1

    def test_delete_session(self) -> None:
        store = InMemoryAuthoringTraceStore()
        store.append_step(_step())
        assert store.delete_session("ses-1") is True
        assert store.delete_session("ses-1") is False
        assert store.load_for_session("ses-1") == []

    def test_is_ready(self) -> None:
        assert InMemoryAuthoringTraceStore().is_ready() is True


# --- Postgres backend (fake driver) ---


class _FakeCursor:
    def __init__(self, calls: list[dict], rows=None, rowcount: int = 1) -> None:
        self._calls = calls
        self._rows = rows or []
        self.rowcount = rowcount

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


def _fake_connect(
    calls: list[dict], rows=None, rowcount: int = 1, fail: bool = False
):
    @contextmanager
    def connect():
        if fail:
            raise RuntimeError("connection refused")

        class FakeConn:
            def cursor(self):
                return _FakeCursor(calls, rows, rowcount)

            def commit(self):
                calls.append({"commit": True})

        yield FakeConn()

    return connect


def _pg_store(calls: list[dict], rows=None, rowcount: int = 1, **kwargs):
    return PostgresAuthoringTraceStore(
        db_url="postgresql://fake",
        connect=_fake_connect(calls, rows=rows, rowcount=rowcount),
        **kwargs,
    )


# Column order of _LOAD_FOR_SESSION / _TRACE_STATUS.
_PG_ROW = (
    "ses-1",
    2,
    "k8s.restart_service",
    {"namespace": "ops"},
    "exec-call-1",
    "cf-1",
    "draft",
    datetime(2026, 9, 8, 10, 0, 0, tzinfo=timezone.utc),
    "https://admin.internal",
)


class TestPostgresStore:
    def test_initialize_runs_ddl_and_idle_sweep(self) -> None:
        calls: list[dict] = []
        _pg_store(calls, idle_days=90).initialize()
        sqls = [call["sql"] for call in calls if "sql" in call]
        assert any("CREATE TABLE IF NOT EXISTS authoring_trace" in s for s in sqls)
        sweeps = [sql for sql in sqls if "DELETE FROM authoring_trace" in sql]
        assert len(sweeps) == 2
        sweep = next(
            call
            for call in calls
            if "sql" in call and "DELETE FROM authoring_trace" in call["sql"]
        )
        assert sweep["params"]["idle_days"] == 90
        # The idle-GC is scoped to draft traces in the SQL predicate itself.
        assert "status = 'draft'" in sweep["sql"]
        # The orphaned-declaration sweep runs after the step sweep, in the
        # same transaction: a session emptied by this run loses its
        # declaration in this run rather than a window later.
        assert "authoring_trace_target" in sweeps[1]

    def test_initialize_migrates_a_cluster_that_predates_flow_origin(self) -> None:
        calls: list[dict] = []
        _pg_store(calls).initialize()
        alter = next(
            call
            for call in calls
            if "sql" in call and "ALTER TABLE authoring_trace" in call["sql"]
        )
        # IF NOT EXISTS is what makes startup idempotent, and nullable is what
        # makes a pre-R-4 row readable: NULL means "no origin recorded", which
        # graduation treats as unverified rather than as a drift.
        assert "ADD COLUMN IF NOT EXISTS flow_origin TEXT" in alter["sql"]

    def test_initialize_skips_the_sweep_when_idle_gc_disabled(self) -> None:
        calls: list[dict] = []
        _pg_store(calls, idle_days=0).initialize()
        assert not any(
            "sql" in call and "DELETE FROM authoring_trace" in call["sql"]
            for call in calls
        )
        # The DDL and its migration still run: disabling the GC is not
        # disabling the store.
        assert any(
            "sql" in call and "ALTER TABLE authoring_trace" in call["sql"]
            for call in calls
        )

    def test_ddl_declares_every_field_and_the_ordered_key(self) -> None:
        calls: list[dict] = []
        _pg_store(calls).initialize()
        ddl = next(
            call["sql"]
            for call in calls
            if "sql" in call and "CREATE TABLE IF NOT EXISTS" in call["sql"]
        )
        for column in (
            "session_id",
            "position",
            "tool_name",
            "args",
            "execution_id",
            "confirm_id",
            "status",
            "captured_at",
            "flow_origin",
        ):
            assert column in ddl
        assert "args         JSONB NOT NULL" in ddl
        # Ordered by (session_id, position) — the replay order is the key.
        assert "PRIMARY KEY (session_id, position)" in ddl
        # The declaration is one row per session and is never anonymous.
        assert "CREATE TABLE IF NOT EXISTS authoring_trace_target" in ddl
        assert "target      TEXT NOT NULL" in ddl

    def test_append_step_enforces_both_bounds_in_one_statement(self) -> None:
        calls: list[dict] = []
        store = _pg_store(calls, max_steps=25)
        assert store.append_step(_step()) is True
        insert = next(
            call
            for call in calls
            if "sql" in call and "INSERT INTO authoring_trace" in call["sql"]
        )
        sql = insert["sql"]
        # The per-session ordinal is computed, not caller-supplied.
        assert "COALESCE(MAX(position), 0) + 1" in sql
        # The step cap drops capture beyond the bound.
        assert "HAVING COUNT(*) < %(max_steps)s" in sql
        assert insert["params"]["max_steps"] == 25
        # A closed trace is never reopened.
        assert "COUNT(*) FILTER (WHERE status <> 'draft') = 0" in sql
        # A racing append is a no-op rather than an error in the seam.
        assert "ON CONFLICT (session_id, position) DO NOTHING" in sql

    def test_append_step_wraps_args_as_jsonb(self) -> None:
        from psycopg.types.json import Jsonb

        calls: list[dict] = []
        _pg_store(calls).append_step(_step(args={"credential_set": "admin-portal"}))
        insert = next(
            call
            for call in calls
            if "sql" in call and "INSERT INTO authoring_trace" in call["sql"]
        )
        assert isinstance(insert["params"]["args"], Jsonb)
        assert insert["params"]["args"].obj == {"credential_set": "admin-portal"}
        assert insert["params"]["execution_id"] == "exec-call-1"
        assert insert["params"]["confirm_id"] == "cf-1"

    def test_append_step_reports_a_dropped_capture(self) -> None:
        calls: list[dict] = []
        store = _pg_store(calls, rowcount=0)
        # rowcount 0 means the HAVING guard or the conflict clause dropped
        # the step; the seam reads that as "no graduation candidate".
        assert store.append_step(_step()) is False

    def test_append_step_sweeps_opportunistically(self) -> None:
        calls: list[dict] = []
        _pg_store(calls, idle_days=180).append_step(_step())
        executed = [call["sql"] for call in calls if "sql" in call]
        insert_at = next(
            index
            for index, sql in enumerate(executed)
            if "INSERT INTO authoring_trace" in sql
        )
        assert any(
            "DELETE FROM authoring_trace" in sql
            for sql in executed[insert_at + 1 :]
        )

    def test_load_for_session_maps_every_field_in_position_order(self) -> None:
        calls: list[dict] = []
        store = _pg_store(calls, rows=[_PG_ROW])
        row = store.load_for_session("ses-1")[0]
        assert row == {
            "session_id": "ses-1",
            "position": 2,
            "tool_name": "k8s.restart_service",
            "args": {"namespace": "ops"},
            "execution_id": "exec-call-1",
            "confirm_id": "cf-1",
            "status": "draft",
            "captured_at": "2026-09-08T10:00:00Z",
            "flow_origin": "https://admin.internal",
        }
        load = next(call for call in calls if "sql" in call)
        assert "ORDER BY position ASC" in load["sql"]

    def test_a_pre_r4_row_loads_with_no_origin(self) -> None:
        calls: list[dict] = []
        legacy = list(_PG_ROW)
        legacy[8] = None
        store = _pg_store(calls, rows=[tuple(legacy)])
        # A cluster migrated in place carries NULL for every step written
        # before R-4; the row-map must hand back None, not "" or a KeyError,
        # so graduation reads it as "unverified" rather than as a drift.
        assert store.load_for_session("ses-1")[0]["flow_origin"] is None

    def test_trace_status_reads_the_first_step(self) -> None:
        calls: list[dict] = []
        store = _pg_store(calls, rows=[("graduated",)])
        assert store.trace_status("ses-1") == "graduated"
        assert "LIMIT 1" in next(call for call in calls if "sql" in call)["sql"]
        empty = _pg_store(calls, rows=[])
        assert empty.trace_status("ses-none") is None

    def test_close_trace_only_touches_draft_rows(self) -> None:
        calls: list[dict] = []
        store = _pg_store(calls)
        assert store.close_trace("ses-1", "graduated") is True
        update = next(
            call
            for call in calls
            if "sql" in call and "UPDATE authoring_trace" in call["sql"]
        )
        assert "AND status = 'draft'" in update["sql"]
        assert update["params"] == {"session_id": "ses-1", "status": "graduated"}

    def test_append_step_locks_the_session_inside_its_transaction(self) -> None:
        calls: list[dict] = []
        _pg_store(calls).append_step(_step())
        executed = [call for call in calls if "sql" in call]
        # The cap is atomic on the insert alone (primary key + ON CONFLICT),
        # but the never-reopen guard reads statuses in the same statement it
        # writes, so a close committing between the read and the insert would
        # leave a trailing draft row. The lock is what closes that window.
        assert "pg_advisory_xact_lock" in executed[0]["sql"]
        insert_at = next(
            index
            for index, call in enumerate(executed)
            if "INSERT INTO authoring_trace" in call["sql"]
        )
        assert insert_at > 0
        # Transaction-scoped: taken before the write, released by the commit
        # that follows it — never a session-level lock left behind.
        commit_at = next(
            index for index, call in enumerate(calls) if call.get("commit")
        )
        assert commit_at > insert_at
        lock = executed[0]["params"]
        # Two-argument form: namespaced so the trace cannot share a lock with
        # an unrelated single-key advisory user.
        assert lock["lock_class"] == 5501
        assert 0 <= lock["lock_key"] <= 0x7FFFFFFF

    def test_the_lock_is_stable_per_session_and_distinct_across_sessions(
        self,
    ) -> None:
        first: list[dict] = []
        _pg_store(first).append_step(_step(session_id="ses-1"))
        again: list[dict] = []
        _pg_store(again).append_step(_step(session_id="ses-1"))
        other: list[dict] = []
        _pg_store(other).append_step(_step(session_id="ses-2"))
        # Stable, or the same session's operations would not exclude each
        # other; distinct, or every session would serialize behind one lock.
        assert again[0]["params"] == first[0]["params"]
        assert other[0]["params"]["lock_key"] != first[0]["params"]["lock_key"]

    def test_close_trace_takes_the_lock_an_append_takes(self) -> None:
        closed: list[dict] = []
        _pg_store(closed).close_trace("ses-1", "graduated")
        executed = [call for call in closed if "sql" in call]
        assert "pg_advisory_xact_lock" in executed[0]["sql"]
        update_at = next(
            index
            for index, call in enumerate(executed)
            if "UPDATE authoring_trace" in call["sql"]
        )
        assert update_at > 0
        appended: list[dict] = []
        _pg_store(appended).append_step(_step(session_id="ses-1"))
        # The *same* key: one lock both operations contend on, which is the
        # entire point — a close cannot land mid-append.
        assert executed[0]["params"] == appended[0]["params"]

    def test_close_trace_reports_an_already_closed_trace(self) -> None:
        calls: list[dict] = []
        assert _pg_store(calls, rowcount=0).close_trace("ses-1", "discarded") is False

    def test_close_trace_rejects_a_non_terminal_status(self) -> None:
        calls: list[dict] = []
        with pytest.raises(ValueError, match="Unknown authoring-trace status"):
            _pg_store(calls).close_trace("ses-1", TRACE_DRAFT)
        # Nothing reached the database.
        assert not any("sql" in call for call in calls)

    def test_sweep_idle_only_touches_draft_rows(self) -> None:
        calls: list[dict] = []
        store = _pg_store(calls, idle_days=180, rowcount=3)
        assert store.sweep_idle() == 3
        sweep = next(call for call in calls if "sql" in call)
        sql = sweep["sql"]
        # Both the outer delete and the grouping subquery are draft-scoped,
        # so a terminal trace is unreachable by the sweep.
        assert sql.count("status = 'draft'") == 2
        assert "GROUP BY session_id" in sql
        assert (
            "HAVING MAX(captured_at) <= now() - make_interval(days => %(idle_days)s)"
            in sql
        )
        assert sweep["params"] == {"idle_days": 180, "sweep_limit": 50}

    def test_sweep_idle_also_reclaims_orphaned_declarations(self) -> None:
        calls: list[dict] = []
        store = _pg_store(calls, idle_days=180, rowcount=3)
        # The return value stays a *step* count so both backends report the
        # same unit, even though two deletes ran.
        assert store.sweep_idle() == 3
        target_sweep = next(
            call
            for call in calls
            if "sql" in call and "DELETE FROM authoring_trace_target" in call["sql"]
        )
        sql = target_sweep["sql"]
        # A declaration whose session still has steps is governed by the
        # trace's own lifecycle, never by the declaration's age.
        assert "session_id NOT IN (SELECT session_id FROM authoring_trace)" in sql
        assert target_sweep["params"] == {"idle_days": 180}

    def test_sweep_idle_disabled_at_zero_days(self) -> None:
        calls: list[dict] = []
        assert _pg_store(calls, idle_days=0).sweep_idle() == 0
        assert not any("sql" in call for call in calls)

    def test_delete_session_reports_rows_removed(self) -> None:
        calls: list[dict] = []
        assert _pg_store(calls, rows=[("ses-1",)]).delete_session("ses-1") is True
        empty = _pg_store(calls, rows=[])
        assert empty.delete_session("ses-1") is False

    def test_delete_session_clears_the_declaration_alone(self) -> None:
        calls: list[dict] = []
        # A skill-development session that declared a target and never
        # mutated still has a row to clear, and reporting it as "nothing
        # deleted" would leave the declaration behind for the idle sweep.
        store = _pg_store(calls, rows=[])
        assert store.delete_session("ses-1") is False
        assert any(
            "sql" in call and "DELETE FROM authoring_trace_target" in call["sql"]
            for call in calls
        )

    def test_is_ready_survives_a_driver_failure(self) -> None:
        calls: list[dict] = []
        store = PostgresAuthoringTraceStore(
            db_url="postgresql://fake",
            connect=_fake_connect(calls, fail=True),
        )
        # Degrades to "not ready" instead of raising into the caller.
        assert store.is_ready() is False


# --- R-4: the declared target and the observed step origin ---


class TestDeclaredTarget:
    """The origin an operator names when opening a skill-development session.

    Declared *before* the first mutation, so it is an authorization scope
    rather than a post-hoc claim about the past — and the first declaration
    wins on both backends, because a later one must not retroactively move
    the scope a session's captured steps were authorized under.
    """

    def test_memory_declares_and_reads_back(self) -> None:
        store = InMemoryAuthoringTraceStore()
        assert store.trace_target("ses-1") is None
        assert store.declare_target("ses-1", "https://admin.internal") == (
            "https://admin.internal"
        )
        assert store.trace_target("ses-1") == "https://admin.internal"

    def test_memory_first_declaration_wins(self) -> None:
        store = InMemoryAuthoringTraceStore()
        store.declare_target("ses-1", "https://admin.internal")
        # Returns the target actually in force, not the one just asked for,
        # so a caller cannot believe it moved the scope.
        assert store.declare_target("ses-1", "https://evil.example") == (
            "https://admin.internal"
        )
        assert store.trace_target("ses-1") == "https://admin.internal"

    def test_memory_declarations_are_session_scoped(self) -> None:
        store = InMemoryAuthoringTraceStore()
        store.declare_target("ses-1", "https://admin.internal")
        assert store.trace_target("ses-2") is None

    def test_postgres_declares_with_a_conflict_noop(self) -> None:
        calls: list[dict] = []
        store = _pg_store(calls, rows=[("https://admin.internal",)])
        assert store.declare_target("ses-1", "https://admin.internal") == (
            "https://admin.internal"
        )
        insert = next(
            call
            for call in calls
            if "sql" in call and "INSERT INTO authoring_trace_target" in call["sql"]
        )
        # First-declaration-wins is enforced in the statement, not in Python,
        # so two replicas opening the same session cannot both take effect.
        assert "ON CONFLICT (session_id) DO NOTHING" in insert["sql"]
        assert insert["params"] == {
            "session_id": "ses-1",
            "target": "https://admin.internal",
        }

    def test_postgres_reads_the_target_back_in_the_same_transaction(self) -> None:
        calls: list[dict] = []
        store = _pg_store(calls, rows=[("https://admin.internal",)])
        store.declare_target("ses-1", "https://elsewhere.example")
        sqls = [call["sql"] for call in calls if "sql" in call]
        # The read-back is what makes the return value the *effective*
        # target; committing only after it keeps the two consistent.
        assert any("SELECT target" in sql for sql in sqls)
        assert any(call.get("commit") for call in calls)
        # The caller is told the truth, not its own request.
        assert store.trace_target("ses-1") == "https://admin.internal"

    def test_postgres_reports_the_request_when_nothing_is_stored(self) -> None:
        calls: list[dict] = []
        store = _pg_store(calls, rows=[])
        # A session deleted between the insert and the read-back: report the
        # requested target rather than None, and let graduation refuse the
        # draft on the missing declaration it will actually see.
        assert store.declare_target("ses-1", "https://admin.internal") == (
            "https://admin.internal"
        )
        assert store.trace_target("ses-1") is None

    def test_memory_sweep_keeps_a_declaration_for_a_session_with_steps(self) -> None:
        store = InMemoryAuthoringTraceStore(idle_days=1)
        store.declare_target("ses-1", "https://admin.internal")
        store.append_step(_step(session_id="ses-1"))
        # Far past the window: the declaration is governed by the trace's
        # lifecycle, and a terminal trace is never swept.
        store.close_trace("ses-1", "graduated")
        store.sweep_idle(now=datetime(2030, 1, 1, tzinfo=timezone.utc))
        assert store.trace_target("ses-1") == "https://admin.internal"

    def test_memory_sweep_reclaims_an_orphaned_declaration(self) -> None:
        store = InMemoryAuthoringTraceStore(idle_days=1)
        store.declare_target("ses-never-mutated", "https://admin.internal")
        store.sweep_idle(now=datetime(2030, 1, 1, tzinfo=timezone.utc))
        assert store.trace_target("ses-never-mutated") is None

    def test_memory_sweep_keeps_a_fresh_declaration_with_no_steps(self) -> None:
        store = InMemoryAuthoringTraceStore(idle_days=1)
        store.declare_target("ses-1", "https://admin.internal")
        # This is the case the whole store exists for: a target declared
        # minutes ago for a session that has not mutated yet must survive a
        # sweep run now.
        store.sweep_idle()
        assert store.trace_target("ses-1") == "https://admin.internal"

    def test_memory_delete_session_clears_a_declaration_with_no_steps(self) -> None:
        store = InMemoryAuthoringTraceStore()
        store.declare_target("ses-1", "https://admin.internal")
        assert store.delete_session("ses-1") is True
        assert store.trace_target("ses-1") is None
        assert store.delete_session("ses-1") is False


class TestStepOrigin:
    """The origin the gateway reported a captured step actually landed on.

    Recorded from the receipt seam, after execution, because the signing
    seam that appends the step runs before the call exists. First
    observation wins on both backends: a later frame for the same execution
    must never rewrite what the step was seen to do.
    """

    def test_a_captured_step_starts_with_no_origin(self) -> None:
        store = InMemoryAuthoringTraceStore()
        store.append_step(_step())
        # The key is always present so both backends expose the same field
        # set, and its value is None until the receipt seam observes one.
        assert store.load_for_session("ses-1")[0]["flow_origin"] is None

    def test_memory_records_the_observed_origin(self) -> None:
        store = InMemoryAuthoringTraceStore()
        store.append_step(_step(execution_id="exec-1"))
        assert (
            store.record_step_origin("ses-1", "exec-1", "https://admin.internal")
            is True
        )
        assert store.load_for_session("ses-1")[0]["flow_origin"] == (
            "https://admin.internal"
        )

    def test_memory_first_observation_wins(self) -> None:
        store = InMemoryAuthoringTraceStore()
        store.append_step(_step(execution_id="exec-1"))
        store.record_step_origin("ses-1", "exec-1", "https://admin.internal")
        assert (
            store.record_step_origin("ses-1", "exec-1", "https://evil.example")
            is False
        )
        assert store.load_for_session("ses-1")[0]["flow_origin"] == (
            "https://admin.internal"
        )

    def test_memory_records_only_the_matching_execution(self) -> None:
        store = InMemoryAuthoringTraceStore()
        store.append_step(_step(execution_id="exec-1"))
        store.append_step(_step(execution_id="exec-2", tool_name="web.click"))
        assert store.record_step_origin("ses-1", "exec-2", "https://a.internal") is True
        rows = store.load_for_session("ses-1")
        assert rows[0]["flow_origin"] is None
        assert rows[1]["flow_origin"] == "https://a.internal"
        # An unknown execution is a no-op, not an error: the receipt seam is
        # best-effort and must not raise into the kernel.
        assert store.record_step_origin("ses-1", "exec-none", "https://a.internal") is False
        assert store.record_step_origin("ses-none", "exec-1", "https://a.internal") is False

    def test_postgres_records_the_origin_with_a_null_guard(self) -> None:
        calls: list[dict] = []
        store = _pg_store(calls)
        assert (
            store.record_step_origin("ses-1", "exec-1", "https://admin.internal")
            is True
        )
        update = next(
            call
            for call in calls
            if "sql" in call and "UPDATE authoring_trace" in call["sql"]
        )
        # The IS NULL guard is the SQL form of first-observation-wins.
        assert "flow_origin IS NULL" in update["sql"]
        assert update["params"] == {
            "session_id": "ses-1",
            "execution_id": "exec-1",
            "origin": "https://admin.internal",
        }

    def test_postgres_reports_an_unobserved_step(self) -> None:
        calls: list[dict] = []
        # rowcount 0 covers both "no such step" and "already observed".
        assert (
            _pg_store(calls, rowcount=0).record_step_origin(
                "ses-1", "exec-1", "https://admin.internal"
            )
            is False
        )

    def test_an_explicit_origin_rides_the_append(self) -> None:
        store = InMemoryAuthoringTraceStore()
        # A caller that already knows the origin may set it at capture; the
        # receipt seam then finds it non-NULL and leaves it alone.
        store.append_step(_step(flow_origin="https://admin.internal"))
        assert store.load_for_session("ses-1")[0]["flow_origin"] == (
            "https://admin.internal"
        )
        assert (
            store.record_step_origin("ses-1", "exec-call-1", "https://other.example")
            is False
        )


class TestOriginOfUrl:
    """``origin_of_url`` is the deliberate twin of the gateway's ``origin_of``.

    Graduation compares a target normalized here against origins the gateway
    normalized there, so a divergence would make a coherent trace look like a
    drift. These cases pin the shapes both sides rely on.
    """

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://admin.internal/login", "https://admin.internal"),
            ("https://Admin.Internal/Login", "https://admin.internal"),
            ("http://admin.internal:8080/x", "http://admin.internal:8080"),
            ("https://admin.internal", "https://admin.internal"),
            ("https://admin.internal/?q=1#f", "https://admin.internal"),
        ],
    )
    def test_absolute_http_urls_normalize(self, url: str, expected: str) -> None:
        assert origin_of_url(url) == expected

    @pytest.mark.parametrize(
        "url",
        [
            # Not absolute, not http(s), or no host: no origin to compare,
            # which callers read as "not recorded" rather than as an error.
            "admin.internal/login",
            "/login",
            "",
            None,
            "file:///etc/passwd",
            "ftp://admin.internal/x",
            "javascript:alert(1)",
            "about:blank",
        ],
    )
    def test_anything_else_has_no_origin(self, url) -> None:
        assert origin_of_url(url) is None

    def test_a_non_string_does_not_raise(self) -> None:
        # Capture is best-effort and reads a gateway frame of unknown shape.
        assert origin_of_url({"url": "https://admin.internal"}) is None
        assert origin_of_url(1234) is None


class TestSkillTargetScope:
    """``skill_target_scope`` reduces a declared target to what a replay binds.

    ``bind_flow`` compares origin equality and ``_path_under`` and never reads
    the query, so origin and path *are* the scope and everything else is not.
    These pin both halves of that: the path must survive, because dropping it
    would silently widen the graduated skill to every path on the host, and the
    query, fragment and ``user:password@`` userinfo must not, because they are
    inert at replay and are where an address-bar paste carries a credential into
    a table that outlives every receipt (ADR-0009), into the ``target_origin``
    log field, and into the ``skill_graduated`` audit payload.
    """

    @pytest.mark.parametrize(
        ("declared", "scoped"),
        [
            # Nothing to strip is returned unchanged, so a clean declaration
            # is byte-identical to what the operator typed.
            ("https://admin.internal/login", "https://admin.internal/login"),
            ("https://admin.internal", "https://admin.internal"),
            (
                "https://admin.internal/console/users",
                "https://admin.internal/console/users",
            ),
            # The path narrowing survives the strip...
            (
                "https://admin.internal/console/users?page=2",
                "https://admin.internal/console/users",
            ),
            # ...and a query or fragment never does.
            (
                "https://admin.internal/login?token=hunter2",
                "https://admin.internal/login",
            ),
            ("https://admin.internal/login#results", "https://admin.internal/login"),
            (
                "https://admin.internal/login?next=/admin#results",
                "https://admin.internal/login",
            ),
            ("https://admin.internal/?q=1", "https://admin.internal/"),
            # Embedded credentials go too — the other place a paste carries a
            # secret, and ``origin_of_url`` keeps the netloc verbatim so a
            # userinfo origin could never corroborate against a browser's.
            (
                "https://alice:hunter2@admin.internal/login?x=1",
                "https://admin.internal/login",
            ),
            ("https://alice@admin.internal/login", "https://admin.internal/login"),
            # An ``@`` in the *path* is not a userinfo separator and survives.
            ("https://admin.internal/p@th/x", "https://admin.internal/p@th/x"),
            # Host case is left alone: scoping is not the corroboration step,
            # and ``origin_of_url`` is what normalizes case when graduation
            # compares. Preserving it keeps the draft's ``web_target`` the URL
            # the operator declared.
            (
                "https://Admin.Internal:8443/Login?a=1",
                "https://Admin.Internal:8443/Login",
            ),
        ],
    )
    def test_origin_and_path_survive_a_query_does_not(
        self, declared: str, scoped: str
    ) -> None:
        assert skill_target_scope(declared) == scoped

    def test_scoping_never_changes_the_origin_graduation_compares(self) -> None:
        """The invariant that makes the strip safe: a scoped target corroborates
        exactly the origins the declared one would, so dropping the query
        narrows what is *stored* without narrowing what is *proven*. Userinfo is
        the one deliberate exception, asserted below."""
        for declared in (
            "https://admin.internal/login?token=hunter2",
            "https://admin.internal/console/users?page=2#rows",
            "https://admin.internal",
        ):
            assert origin_of_url(skill_target_scope(declared)) == origin_of_url(
                declared
            )

    def test_stripping_userinfo_changes_the_origin_and_that_is_the_point(
        self,
    ) -> None:
        """``origin_of_url`` keeps the netloc verbatim, so a declared
        ``https://u:p@host`` normalizes to an origin no browser will ever
        report — the live URL the gateway observed has already dropped the
        credentials. Changing the origin here is therefore not a divergence
        from what the operator declared, it is what makes the declaration
        corroborable at all, and it keeps the secret out of the store, the
        ``target_origin`` log field and the ``skill_graduated`` payload."""
        declared = "https://alice:hunter2@admin.internal/login"

        assert origin_of_url(declared) == "https://alice:hunter2@admin.internal"
        assert skill_target_scope(declared) == "https://admin.internal/login"
        assert origin_of_url(skill_target_scope(declared)) == (
            "https://admin.internal"
        )


# --- Dual-backend field parity (the skills-hub silent-drop lesson) ---


class TestBackendFieldParity:
    def test_both_backends_expose_the_same_step_fields(self) -> None:
        shaped = set(
            make_trace_step(
                session_id="ses-1",
                tool_name="k8s.restart_service",
                args={"namespace": "ops"},
                captured_at="2026-09-08T10:00:00Z",
                execution_id="exec-call-1",
                confirm_id="cf-1",
            )
        )

        memory = InMemoryAuthoringTraceStore()
        memory.append_step(_step())
        memory_fields = set(memory.load_for_session("ses-1")[0])

        calls: list[dict] = []
        postgres = _pg_store(calls, rows=[_PG_ROW])
        postgres_fields = set(postgres.load_for_session("ses-1")[0])

        assert memory_fields == shaped
        assert postgres_fields == shaped

    def test_both_backends_round_trip_the_same_values(self) -> None:
        memory = InMemoryAuthoringTraceStore()
        memory.append_step(_step(args={"namespace": "ops", "grace_period": 30}))
        memory_row = memory.load_for_session("ses-1")[0]

        calls: list[dict] = []
        pg_row_tuple = (
            "ses-1",
            1,
            "k8s.restart_service",
            {"namespace": "ops", "grace_period": 30},
            "exec-call-1",
            "cf-1",
            "draft",
            "2026-09-08T10:00:00Z",
            None,
        )
        postgres_row = _pg_store(calls, rows=[pg_row_tuple]).load_for_session("ses-1")[0]

        assert postgres_row == memory_row

    def test_both_backends_canonicalize_captured_at_identically(self) -> None:
        # Postgres renders a TIMESTAMPTZ at second precision on the way out,
        # so the in-memory backend canonicalizes on the way in: a caller must
        # not see sub-second precision on one backend and none on the other.
        memory = InMemoryAuthoringTraceStore()
        memory.append_step(_step(captured_at="2026-09-08T10:00:00.123456+00:00"))

        calls: list[dict] = []
        pg_row = list(_PG_ROW)
        pg_row[7] = datetime(2026, 9, 8, 10, 0, 0, 123456, tzinfo=timezone.utc)
        postgres = _pg_store(calls, rows=[tuple(pg_row)])

        memory_stamp = memory.load_for_session("ses-1")[0]["captured_at"]
        postgres_stamp = postgres.load_for_session("ses-1")[0]["captured_at"]
        assert memory_stamp == postgres_stamp == "2026-09-08T10:00:00Z"

    def test_an_unparsable_captured_at_is_kept_not_raised(self) -> None:
        store = InMemoryAuthoringTraceStore()
        # Canonicalization is best-effort: a malformed stamp from a caller
        # must degrade to the stored string, never raise into the seam.
        assert store.append_step(_step(captured_at="not-a-timestamp")) is True
        assert (
            store.load_for_session("ses-1")[0]["captured_at"] == "not-a-timestamp"
        )

    def test_both_backends_implement_the_r4_target_members(self) -> None:
        # The R-4 target/origin pair exists on *both* backends — the lesson
        # this class exists for. A method on the in-memory store only would
        # make graduation work in CI and fail in a deployed cluster.
        for store in (
            InMemoryAuthoringTraceStore(),
            _pg_store([]),
        ):
            assert isinstance(store, AuthoringTraceStore)
            for member in (
                "declare_target",
                "trace_target",
                "record_step_origin",
            ):
                assert callable(getattr(store, member)), member

    def test_both_backends_guard_first_wins_the_same_way(self) -> None:
        # The two "first wins" invariants are implemented in Python on one
        # backend and in SQL on the other; pin both so a rewrite of either
        # cannot silently drop one.
        memory = InMemoryAuthoringTraceStore()
        memory.declare_target("ses-1", "https://first.internal")
        assert memory.declare_target("ses-1", "https://second.internal") == (
            "https://first.internal"
        )
        memory.append_step(_step(execution_id="exec-1"))
        memory.record_step_origin("ses-1", "exec-1", "https://first.internal")
        assert (
            memory.record_step_origin("ses-1", "exec-1", "https://second.internal")
            is False
        )

        calls: list[dict] = []
        postgres = _pg_store(calls, rows=[("https://first.internal",)])
        assert postgres.declare_target("ses-1", "https://second.internal") == (
            "https://first.internal"
        )
        postgres.record_step_origin("ses-1", "exec-1", "https://first.internal")
        sqls = " ".join(call["sql"] for call in calls if "sql" in call)
        # Declaration: the conflict clause is the SQL form of first-wins.
        assert "ON CONFLICT (session_id) DO NOTHING" in sqls
        # Observation: the NULL guard is the SQL form of first-wins.
        assert "flow_origin IS NULL" in sqls


# --- Factory backend selection and knobs ---


class TestFactory:
    def test_defaults_to_memory_with_the_documented_bounds(self, monkeypatch) -> None:
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "memory")
        store = build_authoring_trace_store()
        assert store.backend_name == "memory"
        assert store._max_steps == DEFAULT_MAX_STEPS == 100
        assert store._idle_days == DEFAULT_IDLE_DAYS == 180

    def test_knobs_reach_the_store(self, monkeypatch) -> None:
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "memory")
        monkeypatch.setenv("AGENT_AUTHORING_TRACE_MAX_STEPS", "5")
        monkeypatch.setenv("AGENT_AUTHORING_TRACE_IDLE_DAYS", "30")
        store = build_authoring_trace_store()
        assert store._max_steps == 5
        assert store._idle_days == 30
        for _ in range(5):
            assert store.append_step(_step()) is True
        assert store.append_step(_step()) is False

    def test_idle_gc_can_be_disabled_by_knob(self, monkeypatch) -> None:
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "memory")
        monkeypatch.setenv("AGENT_AUTHORING_TRACE_IDLE_DAYS", "0")
        store = build_authoring_trace_store()
        assert store._idle_days == 0
        store.append_step(_step(captured_at="2020-01-01T00:00:00Z"))
        assert store.sweep_idle() == 0

    def test_a_malformed_knob_degrades_to_the_default(self, monkeypatch) -> None:
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "memory")
        monkeypatch.setenv("AGENT_AUTHORING_TRACE_MAX_STEPS", "many")
        monkeypatch.setenv("AGENT_AUTHORING_TRACE_IDLE_DAYS", "")
        # A deploy typo logs and falls back rather than taking the service
        # down at import time.
        store = build_authoring_trace_store()
        assert store._max_steps == DEFAULT_MAX_STEPS
        assert store._idle_days == DEFAULT_IDLE_DAYS

    def test_a_knob_below_its_floor_degrades_to_the_default(self, monkeypatch) -> None:
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "memory")
        monkeypatch.setenv("AGENT_AUTHORING_TRACE_MAX_STEPS", "0")
        monkeypatch.setenv("AGENT_AUTHORING_TRACE_IDLE_DAYS", "-5")
        store = build_authoring_trace_store()
        assert store._max_steps == DEFAULT_MAX_STEPS
        assert store._idle_days == DEFAULT_IDLE_DAYS

    def test_postgres_backend_reads_the_same_knobs(self, monkeypatch) -> None:
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "postgres")
        monkeypatch.setenv("AGENT_STATE_DB_URL", "postgresql://fake")
        monkeypatch.setenv("AGENT_AUTHORING_TRACE_MAX_STEPS", "7")
        monkeypatch.setenv("AGENT_AUTHORING_TRACE_IDLE_DAYS", "14")
        calls: list[dict] = []
        monkeypatch.setattr(
            PostgresAuthoringTraceStore,
            "_default_connect",
            lambda self: _fake_connect(calls)(),
        )
        store = build_authoring_trace_store()
        assert store.backend_name == "postgres"
        assert store._max_steps == 7
        assert store._idle_days == 14
        # initialize() created the table and ran the startup idle-GC.
        assert any(
            "sql" in call and "CREATE TABLE IF NOT EXISTS authoring_trace" in call["sql"]
            for call in calls
        )
        sweep = next(
            call
            for call in calls
            if "sql" in call and "DELETE FROM authoring_trace" in call["sql"]
        )
        assert sweep["params"]["idle_days"] == 14

    def test_postgres_without_url_raises(self, monkeypatch) -> None:
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "postgres")
        with pytest.raises(ValueError, match="AGENT_STATE_DB_URL"):
            build_authoring_trace_store()

    def test_postgres_unreachable_falls_back_to_memory(self, monkeypatch) -> None:
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "postgres")
        monkeypatch.setenv("AGENT_STATE_DB_URL", "postgresql://fake")

        def fail_connect():
            raise RuntimeError("connection refused")

        monkeypatch.setattr(
            PostgresAuthoringTraceStore,
            "_default_connect",
            lambda self: fail_connect(),
        )
        # The store failure degrades without raising: the service stays
        # usable and an in-flight trace simply is not durable.
        store = build_authoring_trace_store()
        assert store.backend_name == "memory"
        assert store.append_step(_step()) is True

    def test_unknown_backend_raises(self, monkeypatch) -> None:
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "redis")
        with pytest.raises(ValueError, match="Unknown AGENT_STATE_STORE_BACKEND"):
            build_authoring_trace_store()

    def test_the_module_singleton_is_usable(self) -> None:
        from agent_service.services.authoring_trace import AUTHORING_TRACE_STORE

        assert AUTHORING_TRACE_STORE.is_ready() is True
        assert AUTHORING_TRACE_STORE.load_for_session("ses-unknown") == []
