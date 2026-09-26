"""Parent-acknowledged, bounded barriers usable across spawned processes."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import multiprocessing
import os
import json
import select
import socket
import time

CONTEXT = multiprocessing.get_context("spawn")
NAMES = ("B0", "B1", "B2", "B3", "B4", "B5")


@dataclass
class Barriers:
    armed: frozenset
    released: dict
    events: object
    watchdog: float = 45

    @classmethod
    def create(cls, *armed, watchdog=45):
        if set(armed) - set(NAMES):
            raise ValueError("unknown barrier")
        # A killed Event waiter can strand notify_all's semaphore handshake.
        # Parent-only byte stores and datagrams need no child-owned locks.
        return cls(frozenset(armed), {name: CONTEXT.RawValue("b", 0) for name in armed},
                   socket.socketpair(type=socket.SOCK_DGRAM), watchdog)

    def hit(self, name):
        if name not in NAMES:
            raise ValueError("unknown barrier")
        if name not in self.armed:
            return
        self.events[1].send(json.dumps({"barrier": name, "pid": os.getpid(), "at": time.monotonic()}).encode())
        deadline = time.monotonic() + self.watchdog
        while not self.released[name].value:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"barrier {name} release watchdog expired")
            time.sleep(0.005)

    async def __call__(self, name):
        await asyncio.to_thread(self.hit, name)

    def wait(self, name, *, timeout=15):
        if not select.select([self.events[0]], [], [], timeout)[0]:
            raise AssertionError(f"barrier {name} acknowledgment missing")
        event = json.loads(self.events[0].recv(1024))
        assert event["barrier"] == name, f"expected {name}; received {event['barrier']}"
        return event

    def release(self, name):
        self.released[name].value = 1

    def release_all(self):
        for flag in self.released.values():
            flag.value = 1

    def close(self):
        self.release_all()
        for endpoint in self.events:
            endpoint.close()
        self.released.clear()
