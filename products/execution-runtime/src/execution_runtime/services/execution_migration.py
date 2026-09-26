"""Explicit disabled migration and fail-closed catalog verification (SPEC-063)."""
from __future__ import annotations

import argparse
from importlib.resources import files
import os
from uuid import UUID

import psycopg

from execution_runtime.services.execution_io import BoundedConnection, remaining
from execution_runtime.services.execution_protocol import ProtocolError
from execution_runtime.services.execution_signing import canonical_digest

TABLES = ("execution_protocol_state", "execution_runs", "execution_intents",
          "execution_dispatch_claims", "execution_observations", "execution_observation_state")
FUNCTIONS = ("execution_json_strings", "execution_immutable", "execution_run_monotonic",
             "execution_observation_monotonic")


def connect(dsn):
    if not dsn or remaining() < 2:
        raise ProtocolError("store_unavailable")
    return BoundedConnection.connect(dsn, connect_timeout=2,
                           options="-c statement_timeout=2000 -c lock_timeout=2000 "
                                   "-c synchronous_commit=on -c search_path=public "
                                   "-c idle_in_transaction_session_timeout=5000")


def fingerprint(connection):
    rows = []
    queries = (
        "SELECT c.relname,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,a.attidentity,"
        "pg_get_expr(d.adbin,d.adrelid) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "JOIN pg_attribute a ON a.attrelid=c.oid LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum "
        "WHERE n.nspname='public' AND c.relname=ANY(%s) AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attnum",
        "SELECT c.relname,x.conname,x.convalidated,pg_get_constraintdef(x.oid) FROM pg_constraint x "
        "JOIN pg_class c ON c.oid=x.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND c.relname=ANY(%s) ORDER BY c.relname,x.conname",
        "SELECT c.relname,t.tgname,t.tgenabled,pg_get_triggerdef(t.oid) FROM pg_trigger t "
        "JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND c.relname=ANY(%s) AND NOT t.tgisinternal ORDER BY c.relname,t.tgname",
        "SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' "
        "AND tablename=ANY(%s) ORDER BY tablename,indexname",
    )
    for query in queries:
        rows.append(connection.execute(query, (list(TABLES),)).fetchall())
    rows.append(connection.execute(
        "SELECT p.proname,p.prosrc,p.provolatile,p.proisstrict FROM pg_proc p "
        "JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' "
        "AND p.proname=ANY(%s) ORDER BY p.proname", (list(FUNCTIONS),)).fetchall())
    if len({row[0] for row in rows[0]}) != len(TABLES) or len(rows[-1]) != len(FUNCTIONS):
        raise ProtocolError("schema_invalid")
    return canonical_digest(rows)


def verify_schema(connection):
    row = connection.execute(
        "SELECT schema_version,admission_epoch,admission_enabled,schema_fingerprint "
        "FROM execution_protocol_state WHERE singleton=true").fetchone()
    if not row or row[0] != 1 or fingerprint(connection) != row[3]:
        raise ProtocolError("schema_invalid")
    for setting in ("fsync", "full_page_writes", "synchronous_commit"):
        if connection.execute(f"SHOW {setting}").fetchone()[0] != "on":
            raise ProtocolError("store_unavailable")
    return {"schema_version": row[0], "admission_epoch": str(row[1]), "admission_enabled": row[2]}


def migrate(dsn, epoch, *, connection_factory=connect):
    epoch = str(UUID(epoch))
    connection = connection_factory(dsn)
    try:
        connection.execute("SELECT pg_advisory_xact_lock(-630001)")
        exists = connection.execute("SELECT to_regclass('public.execution_protocol_state')").fetchone()[0]
        if exists:
            state = verify_schema(connection)
            if state["admission_enabled"] or state["admission_epoch"] != epoch:
                raise ProtocolError("admission_disabled")
        else:
            connection.execute(files("execution_runtime").joinpath(
                "contracts", "execution-ledger-v1.sql").read_text())
            digest = fingerprint(connection)
            connection.execute("INSERT INTO execution_protocol_state "
                               "(schema_version,admission_epoch,admission_enabled,schema_fingerprint) "
                               "VALUES (1,%s,false,%s)", (epoch, digest))
        connection.commit()
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description="Add execution ledger with admission disabled; never auto-enable")
    parser.add_argument("--epoch", required=True)
    args = parser.parse_args()
    try:
        migrate(os.environ.get("EXECUTION_STATE_DB_URL", ""), args.epoch)
    except (ValueError, psycopg.Error, ProtocolError):
        raise SystemExit("execution migration refused or unavailable; admission remains disabled") from None
    print("Execution ledger verified; admission remains disabled")


if __name__ == "__main__":
    main()
