"""Disposable Postgres OQ-7 migration/round-trip proof (no external DB input).

Run via root make audit-contract-test. Uses only a newly created loopback-bound
Docker container with ephemeral storage; no cluster or operator database.
"""

import asyncio
import os
import secrets
import subprocess
import time

import psycopg

from audit_service.schemas.audit import AuditEvent, AuditQuery
from audit_service.services.audit_store import PostgresAuditStore

# The pre-SPEC-070 schema, intentionally independent of the current store DDL.
LEGACY_DDL = """
CREATE TABLE audit_events (
    event_id TEXT PRIMARY KEY, occurred_at TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL, service TEXT NOT NULL, request_id TEXT NOT NULL,
    subject TEXT, username TEXT, actor TEXT, roles TEXT[], session_id TEXT,
    outcome TEXT NOT NULL, details JSONB NOT NULL DEFAULT '{}'::jsonb
);
INSERT INTO audit_events(event_id, occurred_at, event_type, service, request_id, outcome)
VALUES ('legacy', '2030-01-01T00:00:00Z', 'tool_invoked', 'tool-gateway', 'req-legacy', 'success');
"""


def docker(*args, **kwargs):
    return subprocess.run(["docker", *args], check=True, capture_output=True,
                          text=True, timeout=90, **kwargs).stdout.strip()


async def prove(db_url):
    # Readiness is bounded; inability to obtain real Postgres is a failure,
    # never a skip or fallback to a fake-driver test.
    for attempt in range(60):
        try:
            conn = await psycopg.AsyncConnection.connect(db_url, connect_timeout=2)
            break
        except psycopg.OperationalError:
            if attempt == 59:
                raise RuntimeError("disposable audit Postgres did not become ready") from None
            await asyncio.sleep(0.5)
    async with conn:
        await conn.execute(LEGACY_DDL)
    first = PostgresAuditStore(db_url)
    await first.initialize()
    await first.initialize()  # Idempotent upgrade, not just fresh-table creation.
    old = (await first.query(AuditQuery(), None, 50)).events
    assert len(old) == 1 and old[0].delegation_mode is None
    assert not (await first.query(AuditQuery(delegation_mode="none"), None, 50)).events
    events = [AuditEvent(event_id=f"evt-{mode}", occurred_at="2030-01-01T00:00:00Z",
                         event_type="tool_invoked", service="tool-gateway", request_id=f"req-{mode}",
                         username="alice", subject="issuer:alice", actor="platform-gateway",
                         outcome="success", delegation_mode=mode, details={"target": "Automation"})
              for mode in ("user_delegated", "acting_service", "none")]
    assert await first.add(events) == 3
    assert await first.add(events) == 0
    await first.close()
    # A fresh store/connection must read the committed values, not a cache.
    second = PostgresAuditStore(db_url)
    await second.initialize()
    for event in events:
        filters = AuditQuery(delegation_mode=event.delegation_mode, username="alice")
        page = await second.query(filters, None, 1)
        assert page.events == [event] and page.next_cursor is None
        summary = await second.summarize(filters)
        assert summary.total_events == 1
        assert summary.window == {"delegation_mode": event.delegation_mode, "username": "alice"}
        assert not (await second.query(AuditQuery(delegation_mode=event.delegation_mode,
                                                  username="bob"), None, 50)).events
    first_page = await second.query(AuditQuery(), None, 2)
    next_page = await second.query(AuditQuery(), first_page.next_cursor, 2)
    assert len(first_page.events) + len(next_page.events) == 4
    assert len({e.event_id for e in first_page.events + next_page.events}) == 4
    assert next_page.next_cursor is None
    await second.close()


def main():
    if not __debug__:
        raise RuntimeError("audit contract proof requires Python assertions enabled")
    password = secrets.token_hex(24)
    name = f"luban-audit-contract-{secrets.token_hex(6)}"
    started = time.monotonic()
    try:
        docker("run", "--rm", "-d", "--name", name, "-p", "127.0.0.1::5432",
               "--tmpfs", "/var/lib/postgresql/data", "-e", "POSTGRES_PASSWORD",
               "postgres:16-alpine", env={**os.environ, "POSTGRES_PASSWORD": password})
        port = int(docker("port", name, "5432/tcp").rsplit(":", 1)[1])
        asyncio.run(prove(f"postgresql://postgres:{password}@127.0.0.1:{port}/postgres"))
    finally:
        # --rm owns disposal; stop only the unique container created above.
        cleanup = subprocess.run(["docker", "stop", "--time", "1", name],
                                 capture_output=True, timeout=30)
    if cleanup.returncode != 0:
        raise RuntimeError(f"could not stop disposable audit container {name}")
    print(f"audit contract Postgres proof passed ({time.monotonic() - started:.1f}s)")


if __name__ == "__main__":
    main()
