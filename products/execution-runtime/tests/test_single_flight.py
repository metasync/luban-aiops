"""Single-flight registry: join, replay, eviction (SPEC-038 R-5)."""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from execution_runtime.services import single_flight
from execution_runtime.services.single_flight import SingleFlightRegistry


def _run(coro):
    return asyncio.run(coro)


class SingleFlightTests(unittest.TestCase):
    def test_owner_runs_factory_once(self) -> None:
        registry = SingleFlightRegistry(retention_seconds=900)
        calls = 0

        async def factory():
            nonlocal calls
            calls += 1
            return {"receipt": "r", "result": "x"}

        async def scenario():
            outcome, owner = await registry.run("exec-1", factory)
            return outcome, owner

        outcome, owner = _run(scenario())
        self.assertTrue(owner)
        self.assertEqual(outcome["receipt"], "r")
        self.assertEqual(calls, 1)

    def test_concurrent_duplicates_join_one_execution(self) -> None:
        registry = SingleFlightRegistry(retention_seconds=900)
        calls = 0

        async def scenario():
            nonlocal calls
            started = asyncio.Event()

            async def factory():
                nonlocal calls
                calls += 1
                started.set()
                await asyncio.sleep(0.05)
                return {"n": calls}

            owner_task = asyncio.create_task(registry.run("exec-1", factory))
            await started.wait()
            # The flight is in progress: both duplicates must join it.
            join_a = asyncio.create_task(registry.run("exec-1", factory))
            join_b = asyncio.create_task(registry.run("exec-1", factory))
            return await asyncio.gather(owner_task, join_a, join_b)

        results = _run(scenario())
        self.assertEqual(calls, 1)
        outcomes = [outcome for outcome, _owner in results]
        self.assertEqual(outcomes, [{"n": 1}, {"n": 1}, {"n": 1}])
        owners = [owner for _outcome, owner in results]
        self.assertEqual(sum(owners), 1)

    def test_replay_after_completion_never_reexecutes(self) -> None:
        registry = SingleFlightRegistry(retention_seconds=900)
        calls = 0

        async def factory():
            nonlocal calls
            calls += 1
            return {"n": calls}

        async def scenario():
            first = await registry.run("exec-1", factory)
            second = await registry.run("exec-1", factory)
            return first, second

        first, second = _run(scenario())
        self.assertEqual(first, ({"n": 1}, True))
        self.assertEqual(second, ({"n": 1}, False))
        self.assertEqual(calls, 1)

    def test_distinct_keys_run_independently(self) -> None:
        registry = SingleFlightRegistry(retention_seconds=900)

        async def scenario():
            a = await registry.run("exec-1", self._const({"k": "a"}))
            b = await registry.run("exec-2", self._const({"k": "b"}))
            return a, b

        a, b = _run(scenario())
        self.assertEqual(a[0]["k"], "a")
        self.assertEqual(b[0]["k"], "b")

    @staticmethod
    def _const(value):
        async def factory():
            return value

        return factory

    def test_expired_flights_evicted_and_rerun(self) -> None:
        registry = SingleFlightRegistry(retention_seconds=10)
        clock = {"now": 1000.0}
        calls = 0

        async def factory():
            nonlocal calls
            calls += 1
            return {"n": calls}

        async def scenario():
            await registry.run("exec-1", factory)
            clock["now"] += registry.retention_seconds + 1
            return await registry.run("exec-1", factory)

        with mock.patch.object(
            single_flight.time, "monotonic", lambda: clock["now"]
        ):
            _outcome, owner = _run(scenario())
        # Eviction freed the key: the new flight owns and re-runs.
        self.assertTrue(owner)
        self.assertEqual(calls, 2)

    def test_completed_flight_cap_evicts_oldest(self) -> None:
        registry = SingleFlightRegistry(retention_seconds=900)
        calls = 0

        async def factory():
            nonlocal calls
            calls += 1
            return {"n": calls}

        async def scenario():
            for index in range(single_flight.MAX_COMPLETED_FLIGHTS + 1):
                await registry.run(f"exec-{index}", factory)
            return len(registry._flights)

        size = _run(scenario())
        self.assertLessEqual(size, single_flight.MAX_COMPLETED_FLIGHTS)

    def test_failed_flight_is_dropped_not_pinned(self) -> None:
        registry = SingleFlightRegistry(retention_seconds=900)
        attempts = 0

        async def factory():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("boom")
            return {"ok": True}

        async def scenario():
            try:
                await registry.run("exec-1", factory)
            except RuntimeError:
                pass
            return await registry.run("exec-1", factory)

        outcome, owner = _run(scenario())
        self.assertTrue(owner)
        self.assertEqual(outcome, {"ok": True})

    def test_failed_flight_releases_concurrent_joiners(self) -> None:
        registry = SingleFlightRegistry(retention_seconds=900)
        attempts = 0

        async def scenario():
            nonlocal attempts
            started = asyncio.Event()

            async def failing_factory():
                nonlocal attempts
                attempts += 1
                started.set()
                await asyncio.sleep(0.05)
                raise RuntimeError("boom")

            owner_task = asyncio.create_task(
                registry.run("exec-1", failing_factory)
            )
            await started.wait()
            joiner = asyncio.create_task(registry.run("exec-1", failing_factory))
            with self.assertRaises(RuntimeError):
                await owner_task
            # The joiner must be released by the cancelled future; the
            # bounded wait fails the test instead of hanging on a
            # regression.
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(joiner, timeout=2.0)

        _run(scenario())
        self.assertEqual(attempts, 1)


if __name__ == "__main__":
    unittest.main()
