"""Incident store tests (SPEC-015 R-2).

Exercises the in-memory store (create/get/list filters + pagination,
fingerprint dedupe view, reports and dispatch records) and the Postgres
adapter against a fake driver double (skills-hub pattern).
"""

from __future__ import annotations

import asyncio
import json
import unittest
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from incident_service.core.config import IncidentSettings
from incident_service.schemas.incident import (
    ConnectorDispatch,
    Incident,
    TriageReport,
)
from incident_service.services.incident_store import (
    InMemoryIncidentStore,
    PostgresIncidentStore,
    StoreError,
    build_incident_store,
)

NOW = datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc)


def _run(coro):
    return asyncio.run(coro)


def _incident(
    incident_id: str = "inc-aaa111",
    fingerprint: str = "fp-1",
    status: str = "new",
    severity: str = "warning",
    source: str = "alertmanager",
    minutes: int = 0,
) -> Incident:
    when = NOW + timedelta(minutes=minutes)
    return Incident(
        incident_id=incident_id,
        fingerprint=fingerprint,
        source=source,
        severity=severity,
        status=status,
        title=f"title {incident_id}",
        summary="summary",
        labels={"alertname": "X"},
        created_at=when,
        updated_at=when,
    )


def _report(incident_id: str = "inc-aaa111") -> TriageReport:
    return TriageReport(
        incident_id=incident_id,
        summary="assessment",
        severity_assessment="critical",
        evidence=[{"source": "k8s.list_pods", "description": "pods restarting"}],
        hypotheses=["crash loop"],
        next_steps=[
            {"title": "check logs", "rationale": "evidence", "priority": "high"}
        ],
        skills_cited=["sre-alerting/kubepodcrashlooping"],
        session_id=f"incident-{incident_id}",
        generated_at=NOW,
        generated_by="alice",
    )


class InMemoryStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryIncidentStore()

    def test_create_and_get_round_trip(self) -> None:
        _run(self.store.create(_incident()))
        fetched = _run(self.store.get("inc-aaa111"))
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.title, "title inc-aaa111")

    def test_get_unknown_returns_none(self) -> None:
        self.assertIsNone(_run(self.store.get("inc-nope")))

    def test_get_open_by_fingerprint_skips_resolved(self) -> None:
        _run(self.store.create(_incident("inc-a", status="resolved", minutes=1)))
        _run(self.store.create(_incident("inc-b", minutes=2)))
        found = _run(self.store.get_open_by_fingerprint("fp-1"))
        self.assertEqual(found.incident_id, "inc-b")

    def test_get_open_by_fingerprint_returns_newest(self) -> None:
        _run(self.store.create(_incident("inc-a", minutes=1)))
        _run(self.store.create(_incident("inc-b", minutes=5)))
        found = _run(self.store.get_open_by_fingerprint("fp-1"))
        self.assertEqual(found.incident_id, "inc-b")

    def test_list_orders_newest_first_and_paginates(self) -> None:
        for index, minutes in enumerate([1, 5, 3]):
            _run(self.store.create(_incident(f"inc-{index}", minutes=minutes)))
        page, total = _run(self.store.list(0, 2))
        self.assertEqual(total, 3)
        self.assertEqual(
            [i.incident_id for i in page], ["inc-1", "inc-2"]
        )
        page, _ = _run(self.store.list(2, 2))
        self.assertEqual([i.incident_id for i in page], ["inc-0"])

    def test_list_filters_by_status_severity_source(self) -> None:
        _run(self.store.create(_incident("inc-a", status="resolved")))
        _run(
            self.store.create(
                _incident("inc-b", severity="critical", source="manual")
            )
        )
        _, total = _run(self.store.list(0, 10, status="resolved"))
        self.assertEqual(total, 1)
        _, total = _run(self.store.list(0, 10, severity="critical"))
        self.assertEqual(total, 1)
        _, total = _run(self.store.list(0, 10, source="manual"))
        self.assertEqual(total, 1)
        _, total = _run(self.store.list(0, 10, source="alertmanager", status="new"))
        self.assertEqual(total, 0)

    def test_report_round_trip_latest_wins(self) -> None:
        _run(self.store.create(_incident()))
        _run(self.store.set_report("inc-aaa111", _report()))
        updated = _report().model_copy(update={"summary": "second pass"})
        _run(self.store.set_report("inc-aaa111", updated))
        fetched = _run(self.store.get_report("inc-aaa111"))
        self.assertEqual(fetched.summary, "second pass")

    def test_report_absent_returns_none(self) -> None:
        self.assertIsNone(_run(self.store.get_report("inc-nope")))

    def test_dispatches_append_in_order(self) -> None:
        _run(self.store.create(_incident()))
        for status in ("delivered", "failed"):
            _run(
                self.store.add_dispatch(
                    "inc-aaa111",
                    ConnectorDispatch(
                        connector="audit", status=status, created_at=NOW
                    ),
                )
            )
        dispatches = _run(self.store.get_dispatches("inc-aaa111"))
        self.assertEqual([d.status for d in dispatches], ["delivered", "failed"])

    def test_count_open_only_excludes_resolved(self) -> None:
        _run(self.store.create(_incident("inc-a", status="resolved")))
        _run(self.store.create(_incident("inc-b")))
        self.assertEqual(_run(self.store.count()), 2)
        self.assertEqual(_run(self.store.count(open_only=True)), 1)

    def test_ready_and_close_are_noops(self) -> None:
        self.assertTrue(_run(self.store.ready()))
        self.assertIsNone(_run(self.store.close()))


class PostgresStoreAdapterTests(unittest.TestCase):
    """SQL shape against a fake psycopg driver (skills-hub pattern)."""

    def _fake_connect(self, calls: list[dict], rows=None):
        class FakeCursor:
            async def execute(self, sql, params=None):
                calls.append({"sql": sql, "params": params})

            async def fetchall(self):
                return rows or []

            async def fetchone(self):
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

    def test_initialize_runs_ddl(self) -> None:
        calls: list[dict] = []
        store = PostgresIncidentStore(
            "postgresql://fake", connect=self._fake_connect(calls)
        )
        _run(store.initialize())
        self.assertIn("CREATE TABLE IF NOT EXISTS incidents", calls[0]["sql"])
        self.assertIn("CREATE TABLE IF NOT EXISTS triage_reports", calls[0]["sql"])
        self.assertIn(
            "CREATE TABLE IF NOT EXISTS connector_dispatches", calls[0]["sql"]
        )

    def test_save_serializes_labels_as_json_string(self) -> None:
        """psycopg3 needs a JSON string for JSONB columns, not a raw dict."""
        calls: list[dict] = []
        store = PostgresIncidentStore(
            "postgresql://fake", connect=self._fake_connect(calls)
        )
        _run(store.save(_incident()))
        self.assertIn("ON CONFLICT (incident_id)", calls[0]["sql"])
        params = calls[0]["params"]
        self.assertEqual(params["incident_id"], "inc-aaa111")
        self.assertIsInstance(params["labels"], str)
        self.assertEqual(json.loads(params["labels"]), {"alertname": "X"})

    def test_get_row_maps_back_to_incident(self) -> None:
        calls: list[dict] = []
        row = (
            "inc-aaa111", "fp-1", "alertmanager", "warning", "new",
            "title inc-aaa111", "summary", {"alertname": "X"},
            None, None, None, NOW, NOW, None,
        )
        store = PostgresIncidentStore(
            "postgresql://fake", connect=self._fake_connect(calls, rows=[row])
        )
        fetched = _run(store.get("inc-aaa111"))
        self.assertEqual(fetched.incident_id, "inc-aaa111")
        self.assertEqual(fetched.labels, {"alertname": "X"})
        self.assertIsNone(fetched.resolved_at)

    def test_get_open_by_fingerprint_excludes_resolved(self) -> None:
        calls: list[dict] = []
        store = PostgresIncidentStore(
            "postgresql://fake", connect=self._fake_connect(calls, rows=[])
        )
        self.assertIsNone(_run(store.get_open_by_fingerprint("fp-1")))
        self.assertIn("status <> 'resolved'", calls[0]["sql"])
        self.assertEqual(calls[0]["params"], {"fingerprint": "fp-1"})

    def test_list_applies_filters_and_pagination(self) -> None:
        calls: list[dict] = []
        # No page rows: the count query consumes the fake result, so the
        # recorded SQL still shows the WHERE clause shape.
        store = PostgresIncidentStore(
            "postgresql://fake",
            connect=self._fake_connect(calls, rows=[]),
        )
        page, total = _run(
            store.list(0, 10, status="triaged", severity="critical")
        )
        self.assertEqual(total, 0)
        self.assertEqual(page, [])
        filtered = [c for c in calls if "status = %(status)s" in c["sql"]]
        self.assertTrue(filtered)
        self.assertIn("severity = %(severity)s", filtered[0]["sql"])
        page_call = [c for c in calls if "LIMIT %(limit)s" in c["sql"]]
        self.assertEqual(
            page_call[0]["params"]["limit"], 10
        )

    def test_set_report_upserts_with_json_string(self) -> None:
        calls: list[dict] = []
        store = PostgresIncidentStore(
            "postgresql://fake", connect=self._fake_connect(calls)
        )
        _run(store.set_report("inc-aaa111", _report()))
        sql = calls[0]["sql"]
        self.assertIn("INSERT INTO triage_reports", sql)
        self.assertIn("ON CONFLICT (incident_id)", sql)
        self.assertIsInstance(calls[0]["params"]["report"], str)
        self.assertEqual(
            json.loads(calls[0]["params"]["report"])["incident_id"],
            "inc-aaa111",
        )

    def test_get_report_validates_stored_json(self) -> None:
        calls: list[dict] = []
        stored = json.loads(json.dumps(_report().model_dump(mode="json")))
        store = PostgresIncidentStore(
            "postgresql://fake", connect=self._fake_connect(calls, rows=[(stored,)])
        )
        fetched = _run(store.get_report("inc-aaa111"))
        self.assertEqual(fetched.incident_id, "inc-aaa111")

    def test_add_dispatch_inserts_record(self) -> None:
        calls: list[dict] = []
        store = PostgresIncidentStore(
            "postgresql://fake", connect=self._fake_connect(calls)
        )
        _run(
            store.add_dispatch(
                "inc-aaa111",
                ConnectorDispatch(
                    connector="audit",
                    status="delivered",
                    reference="evt-1",
                    created_at=NOW,
                ),
            )
        )
        self.assertIn("INSERT INTO connector_dispatches", calls[0]["sql"])
        self.assertEqual(calls[0]["params"]["connector"], "audit")
        self.assertEqual(calls[0]["params"]["reference"], "evt-1")

    def test_get_dispatches_maps_rows(self) -> None:
        calls: list[dict] = []
        row = ("audit", "failed", None, "audit-service unreachable", NOW)
        store = PostgresIncidentStore(
            "postgresql://fake", connect=self._fake_connect(calls, rows=[row])
        )
        dispatches = _run(store.get_dispatches("inc-aaa111"))
        self.assertEqual(dispatches[0].status, "failed")
        self.assertEqual(dispatches[0].error, "audit-service unreachable")

    def test_ready_returns_false_when_select_fails(self) -> None:
        class BrokenConn:
            def cursor(self):
                raise RuntimeError("down")

            async def commit(self):
                return None

            async def close(self):
                return None

        @asynccontextmanager
        async def connect():
            yield BrokenConn()

        store = PostgresIncidentStore("postgresql://fake", connect=connect)
        self.assertFalse(_run(store.ready()))


class BuildIncidentStoreTests(unittest.TestCase):
    def test_defaults_to_memory_backend(self) -> None:
        store = build_incident_store(IncidentSettings())
        self.assertIsInstance(store, InMemoryIncidentStore)

    def test_postgres_backend_requires_db_url(self) -> None:
        with self.assertRaises(StoreError):
            build_incident_store(
                IncidentSettings(store_backend="postgres", db_url="")
            )

    def test_postgres_backend_selected_with_url(self) -> None:
        store = build_incident_store(
            IncidentSettings(store_backend="postgres", db_url="postgresql://x")
        )
        self.assertIsInstance(store, PostgresIncidentStore)


if __name__ == "__main__":
    unittest.main()
