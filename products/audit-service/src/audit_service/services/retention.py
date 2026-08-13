"""Retention eviction task (SPEC-013 R-6).

Runs on a bounded periodic schedule inside the app lifespan: evicts events
older than ``AUDIT_RETENTION_DAYS``, then enforces the hard ``AUDIT_MAX_EVENTS``
cap. Deletes are batched and self-contained so ingest is never blocked beyond
normal contention.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from audit_service.core.config import AuditSettings
from audit_service.core.metrics import (
    record_evicted,
    record_store_error,
    set_store_size,
)
from audit_service.core.observability import log_event
from audit_service.services.audit_store import AuditStore

LOGGER = logging.getLogger(__name__)


class RetentionTask:
    def __init__(self, store: AuditStore, settings: AuditSettings) -> None:
        self._store = store
        self._settings = settings
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._settings.eviction_interval_seconds)
            try:
                await self.evict_once()
            except Exception:  # noqa: BLE001 - retention must not crash the loop
                record_store_error("evict")
                LOGGER.exception("retention eviction failed")

    async def evict_once(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(
            days=self._settings.retention_days
        )
        evicted = await self._store.evict(
            cutoff=cutoff,
            max_events=self._settings.max_events,
            batch_size=self._settings.eviction_batch_size,
        )
        record_evicted(evicted)
        # Reconcile the exact store size each sweep (also corrects the
        # incremental ingest gauge against any drift).
        set_store_size(await self._store.count())
        if evicted:
            log_event(
                LOGGER,
                "audit_events_evicted",
                evicted=evicted,
                retention_days=self._settings.retention_days,
                max_events=self._settings.max_events,
            )
        return evicted
