"""Test-only preparation of immutable intents, independent of worker authority."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from psycopg.types.json import Jsonb

from execution_runtime.services.execution_protocol import iso
from execution_runtime.services.execution_signing import canonical_digest, sign_envelope


def signed_request(key, epoch, **overrides):
    now = datetime.now(timezone.utc)
    value = {"protocol_version": 3, "execution_id": str(uuid4()), "confirm_id": str(uuid4()),
             "call_id": str(uuid4()), "run_id": str(uuid4()), "admission_epoch": epoch,
             "session_id": str(uuid4()), "owner_user_id": "test-owner", "decider_user_id": "test-decider",
             "approval_kind": "action", "tool_name": "test.increment", "args_digest": canonical_digest({}),
             # requested_at is stamped from the host clock but admission compares it
             # against the disposable Postgres clock (requested_at <= database_now).
             # The container clock trails the host by ~0.75s at rest and drifts
             # further under a long loaded run, so a thin margin lets a late-running
             # fixture read as request_not_yet_valid. Backdate by 30s for skew
             # headroom; lifetime stays 630s, well under the 900s protocol max.
             "requested_at": iso(now - timedelta(seconds=30)), "expires_at": iso(now + timedelta(seconds=600)),
             **overrides}
    value["signature"] = sign_envelope(value, key)
    return value


def register(database, envelope, request_id="harness-original"):
    # This helper does not claim or execute. Agent registration is tested at the
    # product seam separately; this is explicit setup for worker/storage proofs.
    with database.connect() as conn:
        conn.execute("INSERT INTO execution_runs (run_id,session_id,owner_user_id) VALUES (%s,%s,%s) "
                     "ON CONFLICT DO NOTHING", (envelope["run_id"], envelope["session_id"], envelope["owner_user_id"]))
        conn.execute("INSERT INTO execution_intents (execution_id,confirm_id,call_id,run_id,request_digest,"
                     "request_envelope,attempt_request_id,requested_at,expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                     (envelope["execution_id"], envelope["confirm_id"], envelope["call_id"], envelope["run_id"],
                      canonical_digest(envelope), Jsonb(envelope), request_id, envelope["requested_at"], envelope["expires_at"]))
        conn.execute("INSERT INTO execution_observation_state(execution_id) VALUES (%s)", (envelope["execution_id"],))


def body(envelope, token):
    return {"request": envelope, "arguments": {}, "delegated_token": token}


def claim_count(database, execution_id):
    with database.connect() as conn:
        return conn.execute("SELECT count(*) FROM execution_dispatch_claims WHERE execution_id=%s",
                            (execution_id,)).fetchone()[0]
