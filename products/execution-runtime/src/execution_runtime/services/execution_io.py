"""Bound database wire waits and retain ownership across coroutine cancellation."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
import time

import psycopg

_DEADLINE: ContextVar[float | None] = ContextVar("execution_database_deadline", default=None)


@contextmanager
def database_budget(seconds):
    deadline = time.monotonic() + seconds
    outer = _DEADLINE.get()
    token = _DEADLINE.set(min(deadline, outer) if outer is not None else deadline)
    try:
        yield
    finally:
        _DEADLINE.reset(token)


def remaining():
    deadline = _DEADLINE.get()
    return float("inf") if deadline is None else deadline - time.monotonic()


class BoundedConnection(psycopg.Connection):
    """Server statement timeouts alone cannot bound a lost wire response."""

    def wait(self, gen, interval=0.02):
        deadline = min(time.monotonic() + 2, _DEADLINE.get() or float("inf"))

        def bounded():
            try:
                if time.monotonic() >= deadline:
                    raise psycopg.OperationalError("execution database wait expired")
                state = next(gen)
                while True:
                    ready = yield state
                    if time.monotonic() >= deadline:
                        raise psycopg.OperationalError("execution database wait expired")
                    state = gen.send(ready)
            except StopIteration as done:
                return done.value
            finally:
                gen.close()

        try:
            return super().wait(bounded(), interval=min(interval, 0.02))
        except psycopg.OperationalError:
            # The transaction may have committed. Discard the connection, not
            # the durable claim; do not attempt an unbounded rollback/cancel.
            self.close()
            raise


async def owned_thread(function, *args, dispose=None, **kwargs):
    """Do not abandon a thread that may return or still use an owned connection.

    The callable must use bounded database operations. Cancellation waits for
    that operation to exit before the caller's finally block can close its
    connection. A returned resource is disposed if delivery was canceled.
    """
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except BaseException:
                break
        if not task.cancelled() and task.exception() is None and dispose is not None:
            dispose(task.result())
        raise
