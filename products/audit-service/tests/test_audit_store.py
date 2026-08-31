"""Audit store tests (SPEC-013 R-2/R-6).

Exercises the cursor codec, the in-memory store (add/query/count/evict with
filtering, newest-first ordering, and keyset pagination) and the backend
factory. Envelopes must round-trip verbatim — no field rewriting.
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone

from audit_service.core.config import AuditSettings
from audit_service.schemas.audit import AuditEvent, AuditQuery
from audit_service.services.audit_store import (
    InMemoryAuditStore,
    StoreError,
    build_audit_store,
    decode_cursor,
    encode_cursor,
)

BASE = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)


def _run(coro):
    return asyncio.run(coro)


def _event(event_id: str, minutes: int = 0, **overrides) -> AuditEvent:
    fields = {
        "event_id": event_id,
        "occurred_at": BASE + timedelta(minutes=minutes),
        "event_type": "tool_invoked",
        "service": "tool-gateway",
        "request_id": f"req-{event_id}",
        "outcome": "success",
        "details": {"tool_name": "k8s.list_pods"},
    }
    fields.update(overrides)
    return AuditEvent(**fields)


class CursorCodecTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        cursor = encode_cursor(BASE, "evt-1")
        occurred_at, event_id = decode_cursor(cursor)
        self.assertEqual(occurred_at, BASE)
        self.assertEqual(event_id, "evt-1")

    def test_invalid_cursor_raises_store_error(self) -> None:
        with self.assertRaises(StoreError):
            decode_cursor("not-base64-cursor")

    def test_cursor_missing_event_id_raises(self) -> None:
        import base64

        raw = base64.urlsafe_b64encode(
            BASE.isoformat().encode() + b"|"
        ).decode()
        with self.assertRaises(StoreError):
            decode_cursor(raw)

    def test_naive_cursor_timestamp_rejected(self) -> None:
        import base64

        raw = base64.urlsafe_b64encode(b"2026-08-01T12:00:00|evt-1").decode()
        with self.assertRaises(StoreError):
            decode_cursor(raw)


class InMemoryStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryAuditStore()

    def test_add_inserts_and_dedupes(self) -> None:
        inserted = _run(self.store.add([_event("a"), _event("a"), _event("b")]))
        self.assertEqual(inserted, 2)
        self.assertEqual(_run(self.store.count()), 2)

    def test_query_returns_newest_first(self) -> None:
        _run(
            self.store.add(
                [_event("old", minutes=0), _event("new", minutes=10)]
            )
        )
        page = _run(self.store.query(AuditQuery(), None, 50))
        self.assertEqual([e.event_id for e in page.events], ["new", "old"])
        self.assertIsNone(page.next_cursor)

    def test_query_verbatim_round_trip(self) -> None:
        event = _event(
            "a",
            subject="user-1",
            username="alice",
            actor="platform-gateway",
            roles=["operator"],
            session_id="ses-1",
            details={"tool_name": "elastic.search", "status": "ok"},
        )
        _run(self.store.add([event]))
        page = _run(self.store.query(AuditQuery(), None, 50))
        self.assertEqual(page.events[0], event)
        self.assertEqual(page.events[0].details["tool_name"], "elastic.search")

    def test_filters_by_username_service_and_type(self) -> None:
        _run(
            self.store.add(
                [
                    _event("a", username="alice", service="tool-gateway"),
                    _event("b", username="bob", service="tool-gateway"),
                    _event(
                        "c",
                        username="alice",
                        service="platform-gateway",
                        event_type="policy_decision",
                    ),
                ]
            )
        )
        page = _run(
            self.store.query(AuditQuery(username="alice"), None, 50)
        )
        self.assertEqual({e.event_id for e in page.events}, {"a", "c"})

        page = _run(self.store.query(AuditQuery(service="platform-gateway"), None, 50))
        self.assertEqual([e.event_id for e in page.events], ["c"])

        page = _run(
            self.store.query(AuditQuery(event_type="policy_decision"), None, 50)
        )
        self.assertEqual([e.event_id for e in page.events], ["c"])

    def test_filters_by_session_and_request_id(self) -> None:
        _run(
            self.store.add(
                [
                    _event("a", session_id="ses-1"),
                    _event("b", session_id="ses-2"),
                ]
            )
        )
        page = _run(self.store.query(AuditQuery(session_id="ses-1"), None, 50))
        self.assertEqual([e.event_id for e in page.events], ["a"])

        page = _run(self.store.query(AuditQuery(request_id="req-b"), None, 50))
        self.assertEqual([e.event_id for e in page.events], ["b"])

    def test_filters_by_since_until(self) -> None:
        _run(
            self.store.add(
                [
                    _event("t0", minutes=0),
                    _event("t10", minutes=10),
                    _event("t20", minutes=20),
                ]
            )
        )
        since = BASE + timedelta(minutes=5)
        until = BASE + timedelta(minutes=15)
        page = _run(
            self.store.query(AuditQuery(since=since, until=until), None, 50)
        )
        self.assertEqual([e.event_id for e in page.events], ["t10"])

    def test_pagination_with_cursor(self) -> None:
        _run(self.store.add([_event(f"e{i}", minutes=i) for i in range(5)]))

        first = _run(self.store.query(AuditQuery(), None, 2))
        self.assertEqual([e.event_id for e in first.events], ["e4", "e3"])
        self.assertIsNotNone(first.next_cursor)

        second = _run(self.store.query(AuditQuery(), first.next_cursor, 2))
        self.assertEqual([e.event_id for e in second.events], ["e2", "e1"])
        self.assertIsNotNone(second.next_cursor)

        third = _run(self.store.query(AuditQuery(), second.next_cursor, 2))
        self.assertEqual([e.event_id for e in third.events], ["e0"])
        self.assertIsNone(third.next_cursor)

    def test_evict_drops_events_older_than_cutoff(self) -> None:
        _run(
            self.store.add(
                [_event("old", minutes=0), _event("new", minutes=100)]
            )
        )
        cutoff = BASE + timedelta(minutes=50)
        evicted = _run(self.store.evict(cutoff, max_events=100, batch_size=10))
        self.assertEqual(evicted, 1)
        page = _run(self.store.query(AuditQuery(), None, 50))
        self.assertEqual([e.event_id for e in page.events], ["new"])

    def test_evict_enforces_max_events_cap(self) -> None:
        _run(self.store.add([_event(f"e{i}", minutes=i) for i in range(5)]))
        # No retention cutoff hit, but cap the store to the 2 newest.
        evicted = _run(
            self.store.evict(BASE - timedelta(days=1), max_events=2, batch_size=10)
        )
        self.assertEqual(evicted, 3)
        page = _run(self.store.query(AuditQuery(), None, 50))
        self.assertEqual([e.event_id for e in page.events], ["e4", "e3"])

    def test_ready_and_close_are_noops(self) -> None:
        self.assertTrue(_run(self.store.ready()))
        self.assertIsNone(_run(self.store.close()))

    # --- Summarize (SPEC-046 R-1) ------------------------------------------

    def _seed_summary_fixture(self) -> None:
        # 3 tool_invoked (2 success by alice, 1 deny by bob), 1
        # policy_decision (allow, carol), 1 confirmation_decided +
        # execution chain pair (alice). Username carrie is null-username
        # coverage via event "no-user".
        _run(
            self.store.add(
                [
                    _event("t1", username="alice", outcome="success"),
                    _event("t2", username="alice", outcome="success"),
                    _event("t3", username="bob", outcome="deny"),
                    _event(
                        "p1",
                        username="carol",
                        event_type="policy_decision",
                        service="platform-gateway",
                        outcome="allow",
                    ),
                    _event(
                        "c1",
                        username="alice",
                        event_type="confirmation_decided",
                        service="platform-gateway",
                    ),
                    _event(
                        "x1",
                        username="alice",
                        event_type="execution_requested",
                        service="execution-runtime",
                    ),
                    _event(
                        "x2",
                        event_type="execution_completed",
                        service="execution-runtime",
                    ),
                ]
            )
        )

    def test_summarize_aggregates_envelope_columns(self) -> None:
        self._seed_summary_fixture()
        summary = _run(self.store.summarize(AuditQuery()))
        self.assertEqual(summary.total_events, 7)
        self.assertEqual(
            [(b.name, b.count) for b in summary.by_event_type],
            [
                ("tool_invoked", 3),
                ("confirmation_decided", 1),
                ("execution_completed", 1),
                ("execution_requested", 1),
                ("policy_decision", 1),
            ],
        )
        self.assertEqual(
            [(b.name, b.count) for b in summary.by_outcome],
            [("success", 5), ("allow", 1), ("deny", 1)],
        )
        self.assertEqual(
            [(b.name, b.count) for b in summary.by_service],
            [
                ("tool-gateway", 3),
                ("execution-runtime", 2),
                ("platform-gateway", 2),
            ],
        )

    def test_summarize_top_actors_excludes_null_usernames(self) -> None:
        self._seed_summary_fixture()
        summary = _run(self.store.summarize(AuditQuery()))
        # execution_completed had no username and must not appear.
        self.assertEqual(
            [(b.name, b.count) for b in summary.top_actors],
            [("alice", 4), ("bob", 1), ("carol", 1)],
        )

    def test_summarize_top_actors_capped_at_ten(self) -> None:
        _run(
            self.store.add(
                [
                    _event(f"e{i}", username=f"user-{i:02d}", minutes=i)
                    for i in range(12)
                ]
                + [_event("extra", username="user-00", minutes=99)]
            )
        )
        summary = _run(self.store.summarize(AuditQuery()))
        self.assertEqual(len(summary.top_actors), 10)
        # Busiest first; ties broken by name ascending.
        self.assertEqual(summary.top_actors[0].name, "user-00")
        self.assertEqual(summary.top_actors[0].count, 2)
        self.assertEqual(
            [b.name for b in summary.top_actors[1:]],
            [f"user-{i:02d}" for i in range(1, 10)],
        )

    def test_summarize_decision_chain_projects_spec037_events(self) -> None:
        self._seed_summary_fixture()
        summary = _run(self.store.summarize(AuditQuery()))
        chain = summary.decision_chain
        self.assertEqual(chain.confirmation_decided, 1)
        self.assertEqual(chain.execution_requested, 1)
        self.assertEqual(chain.execution_completed, 1)
        self.assertEqual(chain.execution_rejected, 0)  # zero when absent

    def test_summarize_respects_filters_and_echoes_window(self) -> None:
        self._seed_summary_fixture()
        filters = AuditQuery(
            username="alice", since=BASE - timedelta(hours=1)
        )
        summary = _run(self.store.summarize(filters))
        self.assertEqual(summary.total_events, 4)
        self.assertEqual(
            summary.window,
            {
                "username": "alice",
                "since": (BASE - timedelta(hours=1)).isoformat(),
            },
        )
        self.assertEqual(
            [(b.name, b.count) for b in summary.top_actors], [("alice", 4)]
        )

    def test_summarize_empty_window_answers_zeros(self) -> None:
        self._seed_summary_fixture()
        summary = _run(
            self.store.summarize(AuditQuery(username="nobody"))
        )
        self.assertEqual(summary.total_events, 0)
        self.assertEqual(summary.by_event_type, ())
        self.assertEqual(summary.by_outcome, ())
        self.assertEqual(summary.by_service, ())
        self.assertEqual(summary.top_actors, ())
        self.assertEqual(
            summary.decision_chain.confirmation_decided, 0
        )


def _pg_row(event: AuditEvent) -> tuple:
    """Build a driver row tuple in ``_row_names()`` column order."""
    return (
        event.event_id,
        event.occurred_at,
        event.event_type,
        event.service,
        event.request_id,
        event.subject,
        event.username,
        event.actor,
        event.roles,
        event.session_id,
        event.outcome,
        event.details,
    )


class PostgresStoreAdapterTests(unittest.TestCase):
    """SQL/parameter adaptation against a fake psycopg driver.

    A raw dict cannot be adapted for a JSONB column (``psycopg.ProgrammingError:
    cannot adapt type 'dict'``); ``add`` must hand the driver a ``Jsonb`` adapter.
    The fake driver supports scripted ``rowcount`` sequences (evict loops) and
    canned result rows (query/count/ready).
    """

    def _fake_connect(
        self,
        calls: list[dict],
        rows: list[tuple] | None = None,
        rowcounts: list[int] | None = None,
    ):
        from contextlib import asynccontextmanager

        pending_rows = list(rows or [])
        pending_counts = list(rowcounts) if rowcounts is not None else None

        class FakeCursor:
            rowcount = 1

            async def execute(self, sql, params=None):
                calls.append({"sql": sql, "params": params})
                if pending_counts is not None:
                    self.rowcount = (
                        pending_counts.pop(0) if pending_counts else 0
                    )

            async def fetchall(self):
                return list(pending_rows)

            async def fetchone(self):
                return pending_rows[0] if pending_rows else None

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

        class FakeConn:
            def cursor(self):
                return FakeCursor()

            async def commit(self):
                return None

            async def close(self):
                return None

        @asynccontextmanager
        async def connect():
            yield FakeConn()

        return connect

    def _store(self, calls, **kwargs):
        from audit_service.services.audit_store import PostgresAuditStore

        return PostgresAuditStore(
            "postgresql://fake", connect=self._fake_connect(calls, **kwargs)
        )

    def test_add_wraps_details_in_jsonb_adapter(self) -> None:
        from psycopg.types.json import Jsonb

        from audit_service.services.audit_store import PostgresAuditStore

        calls: list[dict] = []
        store = PostgresAuditStore("postgresql://fake", connect=self._fake_connect(calls))
        inserted = _run(store.add([_event("a")]))
        self.assertEqual(inserted, 1)
        params = calls[0]["params"]
        self.assertIsInstance(params["details"], Jsonb)
        self.assertEqual(params["details"].obj, {"tool_name": "k8s.list_pods"})
        self.assertEqual(params["roles"], None)

    def test_initialize_runs_schema_ddl(self) -> None:
        calls: list[dict] = []
        _run(self._store(calls).initialize())
        self.assertEqual(len(calls), 1)
        self.assertIn("CREATE TABLE IF NOT EXISTS audit_events", calls[0]["sql"])

    def test_query_builds_filter_clauses_and_keyset_cursor(self) -> None:
        calls: list[dict] = []
        filters = AuditQuery(
            username="alice",
            session_id="ses-1",
            request_id="req-a",
            event_type="tool_invoked",
            service="tool-gateway",
            since=BASE,
            until=BASE + timedelta(hours=1),
        )
        cursor = encode_cursor(BASE + timedelta(minutes=30), "evt-9")
        _run(self._store(calls).query(filters, cursor, 2))
        sql = calls[0]["sql"]
        for fragment in (
            "username = %(username)s",
            "session_id = %(session_id)s",
            "request_id = %(request_id)s",
            "event_type = %(event_type)s",
            "service = %(service)s",
            "occurred_at >= %(since)s",
            "occurred_at <= %(until)s",
            "(occurred_at, event_id) < (%(cursor_ts)s, %(cursor_id)s)",
            "ORDER BY occurred_at DESC, event_id DESC",
        ):
            self.assertIn(fragment, sql)
        params = calls[0]["params"]
        self.assertEqual(params["limit"], 3)  # limit + 1 overflow probe
        self.assertEqual(params["cursor_id"], "evt-9")

    def test_query_maps_rows_and_paginates(self) -> None:
        calls: list[dict] = []
        newer, older = _event("new", minutes=10), _event("old")
        store = self._store(calls, rows=[_pg_row(newer), _pg_row(older)])
        page = _run(store.query(AuditQuery(), None, 1))
        self.assertEqual(page.events, [newer])
        self.assertIsNotNone(page.next_cursor)
        occurred_at, event_id = decode_cursor(page.next_cursor)
        self.assertEqual((occurred_at, event_id), (newer.occurred_at, "new"))

    def test_count_returns_scalar(self) -> None:
        calls: list[dict] = []
        store = self._store(calls, rows=[(5,)])
        self.assertEqual(_run(store.count()), 5)
        self.assertIn("count(*)", calls[0]["sql"])

    def test_evict_batches_until_short_delete(self) -> None:
        # Cutoff loop: full batch (2) then short batch (1) then the cap loop
        # sees 0 and stops -> 3 DELETEs total, 3 rows evicted.
        calls: list[dict] = []
        store = self._store(calls, rowcounts=[2, 1, 0])
        evicted = _run(store.evict(BASE, max_events=10, batch_size=2))
        self.assertEqual(evicted, 3)
        self.assertEqual(len(calls), 3)
        self.assertIn("occurred_at < %(cutoff)s", calls[0]["sql"])
        self.assertIn("occurred_at < %(cutoff)s", calls[1]["sql"])
        self.assertIn("OFFSET %(keep)s", calls[2]["sql"])

    def test_ready_true_when_probe_succeeds(self) -> None:
        calls: list[dict] = []
        store = self._store(calls, rows=[(1,)])
        self.assertTrue(_run(store.ready()))
        self.assertEqual(calls[0]["sql"], "SELECT 1")

    def test_ready_false_when_connect_fails(self) -> None:
        from contextlib import asynccontextmanager

        from audit_service.services.audit_store import PostgresAuditStore

        @asynccontextmanager
        async def broken_connect():
            raise RuntimeError("connection refused")
            yield  # pragma: no cover

        store = PostgresAuditStore("postgresql://fake", connect=broken_connect)
        self.assertFalse(_run(store.ready()))

    def test_close_is_noop(self) -> None:
        calls: list[dict] = []
        self.assertIsNone(_run(self._store(calls).close()))


class PostgresSummarizeTests(unittest.TestCase):
    """Grouped-SQL adaptation against a fake driver (SPEC-046 R-1).

    The driver hands back one canned result set per executed statement
    (total, three grouped sections, top actors, decision chain); the
    expectations are computed with the shared ``summarize_events`` helper
    so the Postgres mapping layer is pinned to the in-memory semantics.
    """

    def _fake_connect(self, calls: list[dict], result_sets: list[list[tuple]]):
        from contextlib import asynccontextmanager

        queue = [list(rows) for rows in result_sets]

        class FakeCursor:
            async def execute(self, sql, params=None):
                calls.append({"sql": sql, "params": params})

            async def fetchall(self):
                return queue.pop(0) if queue else []

            async def fetchone(self):
                rows = queue.pop(0) if queue else []
                return rows[0] if rows else None

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

        class FakeConn:
            def cursor(self):
                return FakeCursor()

            async def commit(self):
                return None

            async def close(self):
                return None

        @asynccontextmanager
        async def connect():
            yield FakeConn()

        return connect

    def test_summarize_matches_in_memory_semantics(self) -> None:
        from audit_service.services.audit_store import (
            PostgresAuditStore,
            summarize_events,
        )

        fixture = [
            _event("t1", username="alice"),
            _event("t2", username="alice"),
            _event("t3", username="bob", outcome="deny"),
            _event("c1", username="alice", event_type="confirmation_decided"),
            _event(
                "x1",
                event_type="execution_requested",
                service="execution-runtime",
            ),
        ]
        filters = AuditQuery(service="tool-gateway")
        expected = summarize_events(
            [e for e in fixture if e.service == "tool-gateway"], filters
        )

        calls: list[dict] = []
        result_sets = [
            [(4,)],  # total
            [("tool_invoked", 3), ("confirmation_decided", 1)],
            [("success", 3), ("deny", 1)],
            [("tool-gateway", 4)],
            [("alice", 3), ("bob", 1)],
            [("confirmation_decided", 1)],
        ]
        store = PostgresAuditStore(
            "postgresql://fake", connect=self._fake_connect(calls, result_sets)
        )
        summary = _run(store.summarize(filters))
        self.assertEqual(summary.total_events, expected.total_events)
        self.assertEqual(summary.by_event_type, expected.by_event_type)
        self.assertEqual(summary.by_outcome, expected.by_outcome)
        self.assertEqual(summary.by_service, expected.by_service)
        self.assertEqual(summary.top_actors, expected.top_actors)
        self.assertEqual(
            summary.decision_chain.confirmation_decided,
            expected.decision_chain.confirmation_decided,
        )
        self.assertEqual(summary.window, expected.window)

        # Shared WHERE-builder: the filter rides every statement; the
        # envelope-only rule holds (no ``details`` anywhere).
        for call in calls:
            self.assertIn("service = %(service)s", call["sql"])
            self.assertNotIn("details", call["sql"])
        self.assertIn("GROUP BY event_type", calls[1]["sql"])
        self.assertIn("GROUP BY outcome", calls[2]["sql"])
        self.assertIn("GROUP BY service", calls[3]["sql"])
        self.assertIn("username IS NOT NULL", calls[4]["sql"])
        self.assertIn("LIMIT %(top_actors_limit)s", calls[4]["sql"])
        self.assertIn("event_type = ANY(%(chain_types)s)", calls[5]["sql"])
        # psycopg adapts a Python list to a Postgres array for ``= ANY``;
        # a tuple would adapt to a composite type and ``IN`` rejects arrays
        # outright — pin the exact shape that works (live Postgres regression).
        self.assertIsInstance(calls[5]["params"]["chain_types"], list)

    def test_summarize_empty_window_answers_zeros(self) -> None:
        from audit_service.services.audit_store import PostgresAuditStore

        calls: list[dict] = []
        result_sets = [(0,), [], [], [], [], []]
        store = PostgresAuditStore(
            "postgresql://fake", connect=self._fake_connect(calls, result_sets)
        )
        summary = _run(store.summarize(AuditQuery()))
        self.assertEqual(summary.total_events, 0)
        self.assertEqual(summary.by_event_type, ())
        self.assertEqual(summary.top_actors, ())
        self.assertEqual(summary.decision_chain.execution_rejected, 0)


class BuildAuditStoreTests(unittest.TestCase):
    def test_defaults_to_memory_backend(self) -> None:
        store = build_audit_store(AuditSettings())
        self.assertIsInstance(store, InMemoryAuditStore)

    def test_postgres_backend_requires_db_url(self) -> None:
        with self.assertRaises(StoreError):
            build_audit_store(AuditSettings(store_backend="postgres", db_url=""))

    def test_postgres_backend_selected_with_url(self) -> None:
        from audit_service.services.audit_store import PostgresAuditStore

        store = build_audit_store(
            AuditSettings(store_backend="postgres", db_url="postgresql://x")
        )
        self.assertIsInstance(store, PostgresAuditStore)


if __name__ == "__main__":
    unittest.main()
