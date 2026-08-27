"""Single-flight idempotency keyed by execution_id (SPEC-038 R-5).

The gateway call for one signed execution request happens exactly once
per ``execution_id``: the first handoff creates the flight and runs the
executor, concurrent duplicates await the same future, and completed
flights serve repeats from their cached outcome until eviction. There
is no retry and no automatic re-execution — a replayed handoff always
receives the original outcome.

The registry is in-process and authoritative because the deployment
pins ``replicas: 1``; scaling beyond one replica requires a durable
flight registry first (recorded in the product README boundary).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

# Completed flights are bounded both by age and by count so a replay
# storm can never grow the registry without limit.
MAX_COMPLETED_FLIGHTS = 4096


@dataclass
class _Flight:
    future: asyncio.Future
    completed_at: float | None = None
    outcome: Any = None


@dataclass
class SingleFlightRegistry:
    """Asyncio registry joining concurrent duplicates on one future."""

    retention_seconds: int = 900
    _flights: dict[str, _Flight] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def run(
        self,
        key: str,
        factory: Callable[[], Awaitable[Any]],
    ) -> tuple[Any, bool]:
        """Run ``factory`` once per key; duplicates await its outcome.

        Returns ``(outcome, owner)`` — ``owner`` is True for the flight
        that performed the work, False for joins and replays (used to
        keep audit emission single-flight as well).
        """
        loop = asyncio.get_running_loop()
        async with self._lock:
            self._evict(now=time.monotonic())
            flight = self._flights.get(key)
            owner = flight is None
            if owner:
                flight = _Flight(future=loop.create_future())
                self._flights[key] = flight

        if owner:
            try:
                outcome = await factory()
            except BaseException as exc:
                # Drop the failed flight so the registry never pins a
                # key on a poison outcome; the handoff route maps
                # executor failures into results, so this stays a
                # defensive path. Cancel the future so concurrent
                # joiners are released instead of awaiting forever.
                async with self._lock:
                    self._flights.pop(key, None)
                flight.future.cancel()
                raise exc
            flight.outcome = outcome
            flight.completed_at = time.monotonic()
            flight.future.set_result(outcome)
            async with self._lock:
                # Evict post-completion too, so the registry never sits
                # above the cap between calls.
                self._evict(now=time.monotonic())
            return outcome, True

        return await flight.future, False

    def _evict(self, now: float) -> None:
        """Drop completed flights past retention; cap the remainder."""
        expired = [
            key
            for key, flight in self._flights.items()
            if flight.completed_at is not None
            and now - flight.completed_at > self.retention_seconds
        ]
        for key in expired:
            del self._flights[key]
        completed = [
            (key, flight)
            for key, flight in self._flights.items()
            if flight.completed_at is not None
        ]
        if len(completed) > MAX_COMPLETED_FLIGHTS:
            completed.sort(key=lambda pair: pair[1].completed_at or 0.0)
            for key, _flight in completed[
                : len(completed) - MAX_COMPLETED_FLIGHTS
            ]:
                del self._flights[key]
