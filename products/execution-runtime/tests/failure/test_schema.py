"""Disposable catalog, migration, and independent signing parity proofs."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from importlib.resources import files
from uuid import uuid4

import httpx
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest

from execution_runtime.services.execution_migration import TABLES, connect, fingerprint, migrate, verify_schema
from execution_runtime.services.execution_protocol import ProtocolError, timestamp, validate_request
from execution_runtime.services.execution_records import _EXECUTION_RECORDS_DDL, make_execution_record
from execution_runtime.services.execution_signing import build_receipt, canonical_digest, sign_envelope, verify_envelope
from support.barriers import CONTEXT
from support.infrastructure import ROOT
from support.ledger import claim_count, register, signed_request
from test_admission import ledger, outcome
from test_agent_storage import agent


def initialize(db):
    migrate(db.dsn, db.epoch)
    with db.connect() as conn:
        conn.execute("UPDATE execution_protocol_state SET admission_enabled=true")


@pytest.mark.parametrize("case", ("missing_table", "missing_state", "unique", "trigger", "column", "function"))
@pytest.mark.scenario("F-06", "schema")
@pytest.mark.scenario("F-06", "constraint")
def test_catalog_damage_closes_both_products(empty_database, services, case, evidence):
    db = empty_database
    initialize(db)
    envelope = signed_request(services.token, db.epoch)
    register(db, envelope)
    changes = {
        "missing_table": "DROP TABLE execution_observations",
        "missing_state": "DELETE FROM execution_protocol_state",
        "unique": "ALTER TABLE execution_dispatch_claims DROP CONSTRAINT execution_dispatch_claims_confirm_id_call_id_key",
        "trigger": "ALTER TABLE execution_dispatch_claims DISABLE TRIGGER execution_claims_immutable",
        "column": "ALTER TABLE execution_observation_state ALTER COLUMN overflow DROP NOT NULL",
        "function": "CREATE OR REPLACE FUNCTION execution_json_strings(value jsonb) RETURNS boolean LANGUAGE sql IMMUTABLE STRICT AS $$ SELECT true $$",
    }
    with db.connect() as conn:
        conn.execute(changes[case])
    target = services.http()
    gateway = services.http(upstream=target.url)
    worker = services.worker(gateway=gateway, database=db)
    with httpx.Client(trust_env=False, timeout=5) as client:
        assert client.get(worker.url + "/health/live").status_code == 200
        ready = client.get(worker.url + "/health/ready")
        assert ready.status_code == 503 and not ready.json()["protocol_ready"]
    reply = outcome(worker, services.token, envelope)
    assert reply.status_code == 503 and reply.json()["kind"] == "unavailable"
    reader = agent(db, services.token, "lookup", execution_id=envelope["execution_id"])
    assert reader["recovery"]["availability"] == "unavailable"
    assert reader["recovery"]["state"] is None and not reader["recovery"]["observations"]
    assert not agent(db, services.token, "register", envelope=envelope)["ok"]
    assert claim_count(db, envelope["execution_id"]) == 0
    facts = services.facts(gateway, target)
    assert facts == {"gateway_attempts": 0, "target_accepted": 0, "target_effects": 0}
    evidence(**facts, claim_count=0, mode=case, observer_pid=reader["pid"])


@pytest.mark.scenario("F-06", "before_claim")
def test_database_outage_at_b0_cannot_dispatch(empty_database, postgres, services, evidence):
    db = empty_database
    initialize(db)
    envelope = signed_request(services.token, db.epoch)
    register(db, envelope)
    gate = services.barrier("B0")
    target = services.http()
    gateway = services.http(upstream=target.url)
    worker = services.worker(gateway=gateway, database=db, hooks=gate)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(outcome, worker, services.token, envelope)
        gate.wait("B0")
        try:
            with postgres.connect() as admin:
                admin.autocommit = True
                admin.execute(sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS false").format(sql.Identifier(db.name)))
            gate.release("B0")
            reply = pending.result(timeout=10)
            assert reply.status_code == 503 and reply.json()["kind"] == "unavailable"
            assert agent(db, services.token, "lookup", execution_id=envelope["execution_id"])["recovery"]["availability"] == "unavailable"
        finally:
            with postgres.connect() as admin:
                admin.autocommit = True
                admin.execute(sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS true").format(sql.Identifier(db.name)))
    assert claim_count(db, envelope["execution_id"]) == 0
    facts = services.facts(gateway, target)
    assert facts == {"gateway_attempts": 0, "target_accepted": 0, "target_effects": 0}
    evidence(**facts, claim_count=0, barriers=["B0"], asserted="actual database refuses connections before claim")


@pytest.mark.scenario("F-06", "backend")
def test_durability_setting_is_checked(ledger_database, evidence):
    with connect(ledger_database.dsn) as conn:
        conn.execute("SET synchronous_commit=off")
        assert conn.execute("SHOW synchronous_commit").fetchone()[0] == "off"
        with pytest.raises(ProtocolError, match="store_unavailable"):
            verify_schema(conn)
    evidence(asserted="real Postgres nondurable session refused by catalog gate")


@pytest.mark.parametrize("kind", ("action", "flow"))
@pytest.mark.parametrize("lifetime", (1, 900))
@pytest.mark.scenario("F-02", "provenance")
def test_action_flow_signing_and_catalog_parity(ledger_database, services, kind, lifetime, evidence):
    db, key = ledger_database, services.token
    parameters = {"nested": {"z": [None, True, 1.25], "a": "é雪"}}
    signed = agent(db, key, "sign", kind=kind, run_id=str(uuid4()), confirm_id=str(uuid4()),
                   lifetime=lifetime, parameters=parameters)
    assert signed["ok"]
    envelope = signed["envelope"]
    validate_request(envelope, key)
    assert envelope["approval_kind"] == kind
    assert timestamp(envelope["expires_at"]) - timestamp(envelope["requested_at"]) == timedelta(seconds=lifetime)
    assert envelope["args_digest"] == canonical_digest(parameters)
    assert signed["digest"] == canonical_digest(envelope)
    assert verify_envelope(envelope, envelope["signature"], key)
    for field, changed in (("run_id", str(uuid4())), ("admission_epoch", str(uuid4())),
                           ("expires_at", envelope["requested_at"]), ("approval_kind", "flow" if kind == "action" else "action")):
        with pytest.raises(ProtocolError):
            validate_request({**envelope, field: changed}, key)
    reversed_bytes = dict(reversed(list(envelope.items())))
    reversed_bytes["signature"] = sign_envelope(reversed_bytes, key)
    verified = agent(db, key, "validate", envelope=reversed_bytes)
    assert verified["ok"] and verified["signature"] == envelope["signature"]
    assert verified["digest"] == signed["digest"]
    catalog = agent(db, key, "catalog")
    with connect(db.dsn) as conn:
        assert catalog["fingerprint"] == fingerprint(conn)
        assert catalog["state"] == verify_schema(conn)
    canonical = ROOT / "shared/shared-contracts/schemas"
    for name in ("execution-request", "execution-receipt", "execution-observation", "execution-recovery", "execution-handoff-response", "tool-result"):
        expected = (canonical / f"{name}.schema.json").read_bytes()
        for product, package in (("agent-platform", "agent_service"), ("execution-runtime", "execution_runtime")):
            assert (ROOT / f"products/{product}/src/{package}/contracts/{name}.schema.json").read_bytes() == expected
    assert files("execution_runtime").joinpath("contracts/execution-ledger-v1.sql").read_bytes() == (ROOT / "shared/shared-contracts/sql/execution-ledger-v1.sql").read_bytes()
    evidence(observer_pid=signed["pid"], mode=f"{kind}-{lifetime}", asserted="independent product signers, validators, packaged contracts, and catalogs agree")


@pytest.mark.parametrize("status,case", [
    pytest.param(status, case, marks=pytest.mark.scenario("F-31", case))
    for status, case in (("succeeded", "success"), ("timeout", "timeout"), ("requested", "open"))
])
def test_legacy_migration_preserves_bytes_without_inventing_claims(empty_database, services, status, case, evidence):
    db = empty_database
    legacy = signed_request(services.token, db.epoch)
    for field in ("protocol_version", "run_id", "admission_epoch", "expires_at", "approval_kind"):
        legacy.pop(field)
    legacy["signature"] = sign_envelope(legacy, services.token)
    record = make_execution_record(legacy)
    receipt = None if status == "requested" else build_receipt(legacy, status, {"historical": True}, "legacy-original", services.token)
    with db.connect() as conn:
        conn.execute(_EXECUTION_RECORDS_DDL)
        conn.execute("INSERT INTO execution_records (confirm_id,call_id,session_id,execution_id,tool_name,requested_at,status,receipt) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                     tuple(record[name] for name in ("confirm_id", "call_id", "session_id", "execution_id", "tool_name", "requested_at")) + (status, Jsonb(receipt)))
        before = conn.execute("SELECT row_to_json(r)::text FROM execution_records r").fetchall()
    migrate(db.dsn, db.epoch)
    migrate(db.dsn, db.epoch)
    with connect(db.dsn) as conn:
        assert not verify_schema(conn)["admission_enabled"]
        assert conn.execute("SELECT row_to_json(r)::text FROM execution_records r").fetchall() == before
        for table in TABLES[1:]:
            assert conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))).fetchone()[0] == 0
    with pytest.raises(ProtocolError, match="protocol_unsupported"):
        validate_request(legacy, services.token)
    if receipt:
        assert verify_envelope(receipt, receipt["signature"], services.token)
    evidence(claim_count=0, mode=case, asserted="additive idempotent disabled migration preserves original legacy bytes")


@pytest.mark.parametrize("table", ("execution_intents", "execution_dispatch_claims", "execution_observations"))
@pytest.mark.parametrize("operation", ("update", "delete", "early_retention"))
@pytest.mark.scenario("F-30", "retention_boundary")
def test_sql_immutable_evidence_cannot_be_reused(ledger_database, services, table, operation, evidence):
    db, key = ledger_database, services.token
    envelope = signed_request(key, db.epoch)
    register(db, envelope)
    assert ledger(db, key).claim(envelope, "harness-original").permit
    with db.connect() as conn:
        with pytest.raises(psycopg.Error):
            with conn.transaction():
                if operation == "early_retention":
                    conn.execute("SET LOCAL luban.execution_retention='on'")
                query = ("UPDATE {} SET execution_id=execution_id WHERE execution_id=%s"
                         if operation == "update" else "DELETE FROM {} WHERE execution_id=%s")
                conn.execute(sql.SQL(query).format(sql.Identifier(table)), (envelope["execution_id"],))
    assert claim_count(db, envelope["execution_id"]) == 1
    assert ledger(db, key).claim(envelope, "replay").reason == "metadata_replay"
    evidence(claim_count=1, mode=f"{table}-{operation}", asserted="SQL protection forbids updates, deletes, and early retention")


@pytest.mark.parametrize("field,value", (("protocol_version", 4), ("tool_name", "t" * 129),
                                         ("owner_user_id", "o" * 257), ("args_digest", "invalid"),
                                         ("unexpected", "not allowed")))
@pytest.mark.scenario("F-06", "constraint")
def test_sql_request_shape_constraints_reject_invalid_metadata(ledger_database, services, field, value, evidence):
    envelope = signed_request(services.token, ledger_database.epoch, **{field: value})
    with pytest.raises(psycopg.Error):
        register(ledger_database, envelope)
    with ledger_database.connect() as conn:
        assert conn.execute("SELECT count(*) FROM execution_intents WHERE execution_id=%s", (envelope["execution_id"],)).fetchone()[0] == 0
    evidence(claim_count=0, mode=field, asserted="direct SQL cannot bypass closed and bounded request metadata")


def interrupted_migration(dsn, epoch, gate):
    class BeforeCommit:
        def __init__(self, connection):
            self.connection = connection

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def commit(self):
            gate.hit("B0")
            self.connection.commit()

    migrate(dsn, epoch, connection_factory=lambda value: BeforeCommit(connect(value)))


@pytest.mark.scenario("F-31", "interrupted")
def test_killed_migration_rolls_back_entire_catalog(empty_database, services, evidence):
    db = empty_database
    gate = services.barrier("B0")
    child = CONTEXT.Process(target=interrupted_migration, args=(db.dsn, db.epoch, gate))
    child.start()
    try:
        ack = gate.wait("B0")
        assert ack["pid"] == child.pid
        child.kill()
        child.join(timeout=5)
        assert not child.is_alive() and child.exitcode != 0
        with db.connect() as conn:
            assert conn.execute("SELECT to_regclass('public.execution_protocol_state')").fetchone()[0] is None
            assert conn.execute("SELECT count(*) FROM pg_proc WHERE proname='execution_immutable'").fetchone()[0] == 0
        migrate(db.dsn, db.epoch)
        with connect(db.dsn) as conn:
            assert not verify_schema(conn)["admission_enabled"]
        evidence(worker_pids=[ack["pid"]], claim_count=0, asserted="killed migrator leaves no partial schema; rerun remains disabled")
    finally:
        if child.is_alive():
            child.kill()
            child.join(timeout=5)
        child.close()
