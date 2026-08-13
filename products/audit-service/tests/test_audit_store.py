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


class PostgresStoreAdapterTests(unittest.TestCase):
    """Parameter adaptation against a fake psycopg driver (live-test regression).

    A raw dict cannot be adapted for a JSONB column (``psycopg.ProgrammingError:
    cannot adapt type 'dict'``); ``add`` must hand the driver a ``Jsonb`` adapter.
    """

    def _fake_connect(self, calls: list[dict]):
        from contextlib import asynccontextmanager

        class FakeCursor:
            rowcount = 1

            async def execute(self, sql, params=None):
                calls.append({"sql": sql, "params": params})

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
