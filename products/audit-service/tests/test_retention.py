"""Retention eviction task tests (SPEC-013 R-6).

Validates that ``RetentionTask.evict_once`` prunes events older than the
retention window and enforces the hard ``max_events`` cap via the store.
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone

from audit_service.core.config import AuditSettings
from audit_service.schemas.audit import AuditEvent
from audit_service.services.audit_store import InMemoryAuditStore
from audit_service.services.retention import RetentionTask

BASE = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)


def _event(event_id: str, occurred_at: datetime) -> AuditEvent:
    return AuditEvent(
        event_id=event_id,
        occurred_at=occurred_at,
        event_type="tool_invoked",
        service="tool-gateway",
        request_id=f"req-{event_id}",
        outcome="success",
    )


class RetentionTaskTests(unittest.TestCase):
    def test_evict_once_drops_events_older_than_retention(self) -> None:
        store = InMemoryAuditStore()
        now = datetime.now(timezone.utc)
        asyncio.run(
            store.add(
                [
                    _event("old", now - timedelta(days=45)),
                    _event("new", now - timedelta(hours=1)),
                ]
            )
        )
        settings = AuditSettings(retention_days=30, max_events=100)
        task = RetentionTask(store, settings)

        evicted = asyncio.run(task.evict_once())
        self.assertEqual(evicted, 1)
        self.assertEqual(asyncio.run(store.count()), 1)

    def test_evict_once_enforces_max_events(self) -> None:
        store = InMemoryAuditStore()
        now = datetime.now(timezone.utc)
        asyncio.run(
            store.add(
                [
                    _event(f"e{i}", now - timedelta(minutes=100 - i))
                    for i in range(5)
                ]
            )
        )
        settings = AuditSettings(retention_days=30, max_events=2)
        task = RetentionTask(store, settings)

        evicted = asyncio.run(task.evict_once())
        self.assertEqual(evicted, 3)
        self.assertEqual(asyncio.run(store.count()), 2)

    def test_evict_once_noop_when_within_limits(self) -> None:
        store = InMemoryAuditStore()
        asyncio.run(
            store.add([_event("new", datetime.now(timezone.utc))])
        )
        settings = AuditSettings(retention_days=30, max_events=100)
        task = RetentionTask(store, settings)
        self.assertEqual(asyncio.run(task.evict_once()), 0)

    def test_start_stop_lifecycle(self) -> None:
        async def lifecycle() -> None:
            store = InMemoryAuditStore()
            # Long interval so the loop never fires during the test.
            settings = AuditSettings(eviction_interval_seconds=3600)
            task = RetentionTask(store, settings)
            await task.start()
            self.assertIsNotNone(task._task)
            await task.stop()
            self.assertIsNone(task._task)

        asyncio.run(lifecycle())


if __name__ == "__main__":
    unittest.main()
