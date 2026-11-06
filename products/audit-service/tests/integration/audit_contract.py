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
    # SPEC-070 (plan line 156): the durable Postgres round-trip also covers the exact
    # lifecycle/overflow envelope shapes the gateway emits — a target_authorization
    # success carrying its top-level mode and a tool_invoked whose attribution survives
    # a REDACTION_OVERFLOW error outcome — queried by event_type and by
    # (delegation_mode, outcome). A distinct owner keeps the per-mode loop and the
    # four-event pagination above unaffected.
    spec070 = [
        AuditEvent(event_id="evt-authz", occurred_at="2030-01-01T00:00:00Z",
                   event_type="target_authorization", service="tool-gateway", request_id="req-authz",
                   username="carol", subject="issuer:carol", actor="platform-gateway", session_id="ses-1",
                   outcome="success", delegation_mode="user_delegated",
                   details={"operation": "enroll", "authorization_outcome": "authorized",
                            "challenge_id": "11111111-1111-4111-8111-111111111111", "target": "Automation"}),
        AuditEvent(event_id="evt-overflow", occurred_at="2030-01-01T00:00:00Z",
                   event_type="tool_invoked", service="tool-gateway", request_id="req-overflow",
                   username="carol", subject="issuer:carol", actor="platform-gateway",
                   outcome="error", delegation_mode="acting_service",
                   details={"tool_name": "test.leaky_basic", "status": "error",
                            "error_code": "REDACTION_OVERFLOW"}),
    ]
    assert await second.add(spec070) == 2
    assert await second.add(spec070) == 0  # event_id primary key dedupes a re-delivery.
    authz = await second.query(AuditQuery(event_type="target_authorization"), None, 50)
    assert [e.event_id for e in authz.events] == ["evt-authz"]
    assert authz.events[0].delegation_mode == "user_delegated"
    assert authz.events[0].details["authorization_outcome"] == "authorized"
    # Attribution survives an error outcome: the overflow event is queryable by its
    # mode AND its outcome, and never surfaces under a success filter for this owner.
    overflow = await second.query(AuditQuery(delegation_mode="acting_service", outcome="error"), None, 50)
    assert [e.event_id for e in overflow.events] == ["evt-overflow"]
    assert not (await second.query(AuditQuery(delegation_mode="acting_service", outcome="success",
                                              username="carol"), None, 50)).events
    assert (await second.summarize(AuditQuery(event_type="target_authorization"))).total_events == 1
    # SPEC-075 (plan line 156): the durable Postgres round-trip also covers the
    # additive agent_role attribution dimension — stored, filtered by ?agent_role=,
    # and returned verbatim — while a legacy row reads back agent_role is None. A
    # distinct owner ("dave") keeps the delegation_mode loop and the four-event
    # pagination above unaffected.
    spec075 = [
        AuditEvent(event_id=f"evt-role-{role}", occurred_at="2030-01-01T00:00:00Z",
                   event_type="execution_requested", service="agent-platform", request_id=f"req-role-{role}",
                   username="dave", subject="issuer:dave", actor="platform-gateway",
                   outcome="success", agent_role=role, details={"target": "Automation"})
        for role in ("diagnostician", "orchestrator", "executor")
    ]
    assert await second.add(spec075) == 3
    assert await second.add(spec075) == 0  # event_id primary key dedupes a re-delivery.
    for event in spec075:
        filters = AuditQuery(agent_role=event.agent_role, username="dave")
        page = await second.query(filters, None, 1)
        assert page.events == [event] and page.next_cursor is None
        assert page.events[0].agent_role == event.agent_role  # returned verbatim
        summary = await second.summarize(filters)
        assert summary.total_events == 1
        assert summary.window == {"agent_role": event.agent_role, "username": "dave"}
    # A role filter never crosses owners, and the pre-SPEC-075 legacy row still
    # reads back agent_role is None (backward compatibility).
    assert not (await second.query(AuditQuery(agent_role="executor", username="alice"), None, 50)).events
    everything = (await second.query(AuditQuery(), None, 50)).events
    legacy_row = next(e for e in everything if e.event_id == "legacy")
    assert legacy_row.agent_role is None
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
