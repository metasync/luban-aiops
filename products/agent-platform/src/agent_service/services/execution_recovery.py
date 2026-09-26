"""Agent-owned preparation and recovery, never worker dispatch authority.

Only acknowledged writes return success. Runtime startup never migrates tables;
no status read or registration can reconstruct a consumed dispatch right.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
import base64
import hashlib
import hmac
import json
import time
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from agent_service.services.execution_catalog import connect, verify_schema
from agent_service.services.execution_protocol import (
    OBSERVE_SECONDS, ProtocolError, SAFE_REQUEST_ID, iso, observation,
    timestamp, validate_observation, validate_request,
)
from agent_service.services.execution_signing import canonical_digest

_RESERVED = {"wait_expired": "timeout", "run_stopped": "stop", "response_accepted": "acceptance"}
_UNCERTAIN = {"wait_expired", "transport_uncertain", "result_persistence_unconfirmed"}
_STOP_REASONS = {"wait_expired", "transport_error", "response_invalid", "receipt_unconfirmed",
                 "run_stopped", "predecessor_unresolved", "send_lock_unavailable", "shutdown",
                 "integrity_conflict", "metadata_replay", "store_unavailable", "claim_commit_unconfirmed",
                 "request_expired", "request_not_yet_valid", "admission_disabled", "epoch_mismatch",
                 "gateway_not_configured", "credential_missing", "request_missing", "schema_invalid"}


RECOVERY_AVAILABILITY = ("available", "unavailable", "not_found")
RECOVERY_STATES = (None, "not_dispatched", "dispatch_claimed", "outcome_unknown", "result_recorded")
TOOL_REPORT_STATUSES = ("succeeded", "failed", "timeout")


def summarize_execution_recovery(projection: dict) -> dict:
    """Closed facts for derived documents; never original-response authority.

    Outcome/receipt selection belongs to the full-ledger reducer. This function
    only projects its result; an observation page can never change the verdict.
    """
    availability = projection.get("availability")
    if availability not in RECOVERY_AVAILABILITY:
        availability = "unavailable"
    readable = availability == "available"
    conflict = readable and projection.get("integrity_conflict") is True
    state = projection.get("state") if readable else None
    if conflict:
        state = "outcome_unknown"
    if state not in RECOVERY_STATES:
        state = "outcome_unknown"
    receipt = projection.get("receipt") or {}
    tool_status = receipt.get("status") if state == "result_recorded" and isinstance(receipt, dict) else None
    if tool_status not in TOOL_REPORT_STATUSES:
        tool_status = None
        if state == "result_recorded":
            state = "outcome_unknown"
    late = False
    if tool_status and projection.get("observe_by") and receipt.get("completed_at"):
        try:
            late = timestamp(receipt["completed_at"]) > timestamp(projection["observe_by"])
        except (ProtocolError, ValueError, TypeError):
            pass
    return {
        "availability": availability,
        "state": state,
        "preparation_state": "registered" if readable and state is None else None,
        "tool_report_status": tool_status,
        "late_report": late,
        "integrity_conflict": conflict,
        "run_stopped": readable and projection.get("run_stopped") is True,
        "target_verification_required": True,
    }


def read_owner_recovery_page(session_id: str, owner_user_id: str) -> dict | None:
    """Bounded snapshot for an already owner-checked evidence consumer.

    No ledger access when admission is disabled. Failure is explicit and never
    replaced by an empty successful history or a legacy presentation receipt.
    """
    try:
        from agent_service.services.runtime_dependencies import get_runtime_kernel

        recovery = get_runtime_kernel()._execution_recovery()
        if recovery is None:
            return None
        return recovery.owner_session_recovery(session_id, owner_user_id, page_size=100)
    except Exception:
        return {"availability": "unavailable", "executions": [], "executions_truncated": False}


EXECUTION_EVIDENCE_GUIDANCE = (
    "Execution recovery is evidence, not proof of business success. Preserve "
    "unknown outcomes, late tool reports, integrity conflicts, unavailable or "
    "missing evidence, and incomplete coverage. Historical receipt statuses do "
    "not override current recovery. A succeeded tool report still requires "
    "independent target verification; failure or timeout does not prove no "
    "effect. Account for work that may still be running. Recovery cannot "
    "authorize a retry, continuation, secret release, or an authoring origin."
)


def execution_evidence_label(facts: dict) -> str:
    """Deterministic text for a compact summary, never raw tool output."""
    availability = facts.get("availability")
    if availability != "available":
        return "Recovery not found — inconclusive" if availability == "not_found" else "Recovery unavailable"
    if facts.get("integrity_conflict") is True:
        return "Outcome unknown — conflicting reports"
    labels = {
        None: "Registered — dispatch not established",
        "not_dispatched": "Not dispatched — this submission only",
        "dispatch_claimed": "Dispatch claimed — outcome pending",
        "outcome_unknown": "Outcome unknown",
        "result_recorded": "Tool report recorded",
    }
    state = facts.get("state")
    if state not in RECOVERY_STATES:
        return "Outcome unknown"
    status = facts.get("tool_report_status")
    if state == "result_recorded" and status not in TOOL_REPORT_STATUSES:
        return "Outcome unknown"
    label = labels[state]
    if state == "result_recorded":
        label += f" — tool reported {status}"
        if facts.get("late_report") is True:
            label += " — late report"
    return label


@dataclass(frozen=True)
class Registration:
    execution_id: str
    request_digest: str
    attempt_request_id: str
    # Preparation only: deliberately no dispatch or continuation permit.


class ExecutionRecovery:
    def __init__(self, dsn, key, epoch, *, admission_enabled=False, connection_factory=connect):
        self._dsn, self._key, self._epoch = dsn, key, epoch
        self._enabled, self._connect = admission_enabled, connection_factory

    @contextmanager
    def connection(self):
        conn = None
        try:
            conn = self._connect(self._dsn)
            yield conn
        except psycopg.Error:
            raise ProtocolError("store_unavailable") from None
        finally:
            if conn is not None:
                conn.close()

    @staticmethod
    def _one(conn, query, args=()):
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, args)
            return cursor.fetchone()

    @staticmethod
    def _all(conn, query, args=()):
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, args)
            return cursor.fetchall()

    @staticmethod
    def lock_key(run_id):
        return int.from_bytes(hashlib.sha256(str(run_id).encode()).digest()[:8], "big", signed=True)

    def _mutex(self, conn, run_id):
        conn.autocommit = True
        deadline = time.monotonic() + 2
        while not conn.execute("SELECT pg_try_advisory_lock(%s)", (self.lock_key(run_id),)).fetchone()[0]:
            if time.monotonic() >= deadline:
                raise ProtocolError("send_lock_unavailable")
            time.sleep(0.01)

    def _enabled_state(self, state):
        if not self._enabled or not state["admission_enabled"]:
            raise ProtocolError("admission_disabled")
        if not self._epoch or self._epoch != state["admission_epoch"]:
            raise ProtocolError("epoch_mismatch")

    def _run(self, conn, run_id, session_id, owner_user_id):
        row = self._one(conn, "SELECT * FROM execution_runs WHERE run_id=%s FOR UPDATE", (run_id,))
        if not row:
            raise ProtocolError("request_missing")
        if row["session_id"] != session_id or row["owner_user_id"] != owner_user_id:
            raise ProtocolError("identity_conflict")
        return row

    def _intent(self, conn, envelope):
        row = self._one(conn, "SELECT * FROM execution_intents WHERE execution_id=%s", (envelope["execution_id"],))
        if not row:
            raise ProtocolError("request_missing")
        if row["request_digest"] != canonical_digest(envelope) or row["request_envelope"] != envelope:
            raise ProtocolError("identity_conflict")
        return row

    def create_run(self, session_id, owner_user_id):
        """Only a new human root uses this; restore must retain its existing UUID."""
        if any(not isinstance(value, str) or not 0 < len(value) <= 256 for value in (session_id, owner_user_id)):
            raise ProtocolError("bad_request")
        run_id = str(uuid4())
        with self.connection() as conn:
            verify_schema(conn)
            conn.execute("INSERT INTO execution_runs (run_id,session_id,owner_user_id) VALUES (%s,%s,%s)",
                         (run_id, session_id, owner_user_id))
            conn.commit()
        return run_id

    def _unresolved(self, conn, run_id, execution_id=None):
        return conn.execute(
            "SELECT EXISTS (SELECT 1 FROM execution_intents i "
            "LEFT JOIN execution_observation_state s USING (execution_id) "
            "WHERE i.run_id=%s AND i.execution_id IS DISTINCT FROM %s::uuid AND "
            "(coalesce(s.integrity_conflict,false) OR NOT EXISTS ("
            "SELECT 1 FROM execution_observations a JOIN execution_observations r ON "
            "r.execution_id=a.execution_id AND r.kind='worker_result' "
            "AND r.payload->>'receipt_digest'=a.payload->>'receipt_digest' "
            "WHERE a.execution_id=i.execution_id AND a.kind='response_accepted')))",
            (run_id, execution_id)).fetchone()[0]

    def check_run(self, run_id, session_id, owner_user_id, *, envelope=None):
        with self.connection() as conn:
            self._enabled_state(verify_schema(conn))
            run = self._run(conn, run_id, session_id, owner_user_id)
            if run["stopped_at"]:
                raise ProtocolError("run_stopped")
            execution_id = None
            if envelope is not None:
                validate_request(envelope, self._key)
                if envelope["run_id"] != run_id:
                    raise ProtocolError("identity_conflict")
                self._intent(conn, envelope)
                execution_id = envelope["execution_id"]
                state = conn.execute("SELECT integrity_conflict FROM execution_observation_state WHERE execution_id=%s",
                                     (execution_id,)).fetchone()
                if not state or state[0]:
                    raise ProtocolError("integrity_conflict")
            if self._unresolved(conn, run_id, execution_id):
                raise ProtocolError("predecessor_unresolved")

    def register(self, envelope, attempt_request_id):
        validate_request(envelope, self._key)
        if not isinstance(attempt_request_id, str) or not SAFE_REQUEST_ID.fullmatch(attempt_request_id):
            raise ProtocolError("bad_request")
        digest = canonical_digest(envelope)
        with self.connection() as conn:
            state = verify_schema(conn)
            run = self._run(conn, envelope["run_id"], envelope["session_id"], envelope["owner_user_id"])
            existing = self._one(conn, "SELECT * FROM execution_intents WHERE execution_id=%s OR "
                                 "(confirm_id=%s AND call_id=%s)",
                                 (envelope["execution_id"], envelope["confirm_id"], envelope["call_id"]))
            if existing:
                if (str(existing["execution_id"]) != envelope["execution_id"]
                        or existing["request_digest"] != digest or existing["request_envelope"] != envelope):
                    raise ProtocolError("identity_conflict")
                conn.commit()
                return Registration(envelope["execution_id"], digest, existing["attempt_request_id"])
            self._enabled_state(state)
            if envelope["admission_epoch"] != self._epoch:
                raise ProtocolError("epoch_mismatch")
            if run["stopped_at"]:
                raise ProtocolError("run_stopped")
            if self._unresolved(conn, envelope["run_id"]):
                raise ProtocolError("predecessor_unresolved")
            now = conn.execute("SELECT clock_timestamp()").fetchone()[0]
            if timestamp(envelope["requested_at"]) > now:
                raise ProtocolError("request_not_yet_valid")
            if timestamp(envelope["expires_at"]) <= now:
                raise ProtocolError("request_expired")
            inserted = conn.execute(
                "INSERT INTO execution_intents (execution_id,confirm_id,call_id,run_id,request_digest,"
                "request_envelope,attempt_request_id,requested_at,expires_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING execution_id",
                (envelope["execution_id"], envelope["confirm_id"], envelope["call_id"], envelope["run_id"],
                 digest, Jsonb(envelope), attempt_request_id, timestamp(envelope["requested_at"]),
                 timestamp(envelope["expires_at"]))).fetchone()
            if not inserted:
                raise ProtocolError("identity_conflict")
            conn.execute("INSERT INTO execution_observation_state (execution_id) VALUES (%s)",
                         (envelope["execution_id"],))
            conn.commit()
        return Registration(envelope["execution_id"], digest, attempt_request_id)

    def _append(self, conn, intent, fact):
        validate_observation(fact, intent["request_envelope"], self._key)
        if fact["source"] != "agent" or fact["attempt_request_id"] != intent["attempt_request_id"]:
            raise ProtocolError("identity_conflict")
        execution_id, digest = str(intent["execution_id"]), canonical_digest(fact)
        state = self._one(conn, "SELECT * FROM execution_observation_state WHERE execution_id=%s FOR UPDATE",
                          (execution_id,))
        if not state:
            raise ProtocolError("schema_invalid")
        old = conn.execute("SELECT content_digest FROM execution_observations WHERE observation_id=%s",
                           (fact["observation_id"],)).fetchone()
        if old:
            if old[0] == digest:
                conn.execute("UPDATE execution_observation_state SET duplicate_count=least(2147483647::bigint,"
                             "duplicate_count::bigint+1) WHERE execution_id=%s", (execution_id,))
                return "identical"
            conn.execute("UPDATE execution_observation_state SET integrity_conflict=true, "
                         "first_conflicting_digest=coalesce(first_conflicting_digest,%s) WHERE execution_id=%s",
                         (digest, execution_id))
            return "conflict"
        slot = _RESERVED.get(fact["kind"])
        if slot and conn.execute("SELECT 1 FROM execution_observations WHERE execution_id=%s AND reserved_slot=%s",
                                 (execution_id, slot)).fetchone():
            slot = None
        if slot is None and state["ordinary_count"] >= 64:
            conn.execute("UPDATE execution_observation_state SET overflow=true, "
                         "overflow_count=least(2147483647::bigint,overflow_count::bigint+1) WHERE execution_id=%s",
                         (execution_id,))
            return "overflow"
        conn.execute("INSERT INTO execution_observations "
                     "(observation_id,execution_id,source,kind,reserved_slot,payload,content_digest) "
                     "VALUES (%s,%s,'agent',%s,%s,%s,%s)",
                     (fact["observation_id"], execution_id, fact["kind"], slot, Jsonb(fact), digest))
        if slot is None:
            conn.execute("UPDATE execution_observation_state SET ordinary_count=ordinary_count+1 WHERE execution_id=%s",
                         (execution_id,))
        return "inserted"

    def stop_run(self, run_id, session_id, owner_user_id, *, reason, envelope=None, fact=None):
        """Stop before returning control; a failed write must leave the local latch set."""
        if (envelope is None) != (fact is None):
            raise ProtocolError("bad_request")
        if envelope is not None:
            validate_request(envelope, self._key)
            if envelope["run_id"] != run_id or fact.get("kind") not in {
                "wait_expired", "transport_uncertain", "pre_dispatch_refused", "run_stopped"
            }:
                raise ProtocolError("bad_request")
        with self.connection() as conn:
            self._mutex(conn, run_id)
            with conn.transaction():
                verify_schema(conn)
                self._run(conn, run_id, session_id, owner_user_id)
                result = "stopped"
                if envelope is not None:
                    intent = self._intent(conn, envelope)
                    if fact["kind"] == "pre_dispatch_refused" and conn.execute(
                        "SELECT 1 FROM execution_dispatch_claims WHERE execution_id=%s", (envelope["execution_id"],)
                    ).fetchone():
                        raise ProtocolError("claim_commit_unconfirmed")
                    result = self._append(conn, intent, fact)
                conn.execute("UPDATE execution_runs SET stopped_at=clock_timestamp(),stop_reason=%s "
                             "WHERE run_id=%s AND stopped_at IS NULL",
                             (reason if reason in _STOP_REASONS else "response_invalid", run_id))
            return result

    def accept(self, envelope, original, current_request_id):
        """Only a validated original response, never a recovery page, can be accepted."""
        from agent_service.services.execution_protocol import VerifiedOriginal
        if not isinstance(original, VerifiedOriginal):
            raise ProtocolError("response_invalid")
        original.revalidate(envelope, self._key)
        worker_fact = original.observation
        fact = observation(envelope, source="agent", kind="response_accepted", key=self._key,
                           attempt_request_id=worker_fact["attempt_request_id"], current_request_id=current_request_id,
                           receipt_digest=worker_fact["receipt_digest"])
        with self.connection() as conn:
            verify_schema(conn)
            run = self._run(conn, envelope["run_id"], envelope["session_id"], envelope["owner_user_id"])
            intent = self._intent(conn, envelope)
            state = conn.execute("SELECT integrity_conflict FROM execution_observation_state WHERE execution_id=%s",
                                 (envelope["execution_id"],)).fetchone()
            row = self._one(conn, "SELECT payload,content_digest FROM execution_observations "
                            "WHERE execution_id=%s AND observation_id=%s AND kind='worker_result'",
                            (envelope["execution_id"], worker_fact["observation_id"]))
            claim = conn.execute("SELECT claim_owner_id FROM execution_dispatch_claims WHERE execution_id=%s",
                                 (envelope["execution_id"],)).fetchone()
            if run["stopped_at"] or not state or state[0]:
                raise ProtocolError("run_stopped")
            if (not row or row["payload"] != worker_fact or row["content_digest"] != canonical_digest(worker_fact)
                    or not claim or str(claim[0]) != worker_fact["claim_owner_id"]):
                raise ProtocolError("response_invalid")
            result = self._append(conn, intent, fact)
            conn.commit()
        if result not in {"inserted", "identical"}:
            raise ProtocolError("integrity_conflict")
        return fact

    def _project(self, conn, execution_id, *, now, replay, page_after=None, cursor_scope=None):
        """Build the recovery projection for one execution over an open read.

        Shared by the internal :meth:`lookup` (legacy first-20 truncation, no
        cursor) and the owner-scoped :meth:`owner_recovery` (cursor paging).
        ``state``/``receipt``/``integrity_conflict`` are always derived from the
        full validated observation set; only the returned ``observations``
        window is bounded, so paging never changes the reported outcome.
        """
        intent = self._one(conn, "SELECT * FROM execution_intents WHERE execution_id=%s", (execution_id,))
        if not intent:
            return self.empty("not_found", execution_id, as_of=iso(now), replay=replay)
        envelope = intent["request_envelope"]
        validate_request(envelope, self._key)
        if canonical_digest(envelope) != intent["request_digest"]:
            raise ProtocolError("integrity_conflict")
        run = self._one(conn, "SELECT * FROM execution_runs WHERE run_id=%s", (intent["run_id"],))
        claim = self._one(conn, "SELECT * FROM execution_dispatch_claims WHERE execution_id=%s", (execution_id,))
        state = self._one(conn, "SELECT * FROM execution_observation_state WHERE execution_id=%s", (execution_id,))
        if not run or not state:
            raise ProtocolError("schema_invalid")
        if (run["session_id"] != envelope["session_id"] or
                run["owner_user_id"] != envelope["owner_user_id"]):
            raise ProtocolError("integrity_conflict")
        rows = self._all(conn, "SELECT payload,content_digest,insertion_seq FROM execution_observations "
                         "WHERE execution_id=%s ORDER BY insertion_seq LIMIT 71", (execution_id,))
        facts, conflict = [], state["integrity_conflict"]
        for row in rows:
            fact = row["payload"]
            try:
                validate_observation(fact, envelope, self._key)
                if (canonical_digest(fact) != row["content_digest"]
                        or fact["attempt_request_id"] != intent["attempt_request_id"]
                        or (fact["kind"] in {"worker_result", "claim_committed"} and
                            (not claim or fact["claim_owner_id"] != str(claim["claim_owner_id"])))):
                    raise ProtocolError("integrity_conflict")
                facts.append((row["insertion_seq"], fact))
            except ProtocolError:
                conflict = True
        receipts = {fact["receipt_digest"]: fact["receipt"] for _seq, fact in facts if fact["kind"] == "worker_result"}
        conflict = conflict or len(receipts) > 1
        deadline = claim["observe_by"] if claim else intent["registered_at"] + timedelta(seconds=OBSERVE_SECONDS)
        kinds = {fact["kind"] for _seq, fact in facts}
        receipt = next(iter(receipts.values())) if len(receipts) == 1 and not conflict else None
        if conflict:
            dispatch_state = "outcome_unknown"
        elif receipt:
            dispatch_state = "result_recorded"
        elif kinds & _UNCERTAIN or now >= deadline:
            dispatch_state = "outcome_unknown"
        elif claim:
            dispatch_state = "dispatch_claimed"
        elif "pre_dispatch_refused" in kinds and run["stopped_at"]:
            dispatch_state = "not_dispatched"
        else:
            dispatch_state = None
        if cursor_scope is not None:
            window = [pair for pair in facts if page_after is None or pair[0] > page_after]
            page = window[:20]
            next_cursor = self._encode_cursor(cursor_scope, page[-1][0]) if len(window) > 20 else None
            observations = [fact for _seq, fact in page]
            truncated = next_cursor is not None or state["overflow"]
        else:
            observations = [fact for _seq, fact in facts[:20]]
            next_cursor = None
            truncated = state["overflow"] or len(facts) > 20
        projection = self.empty("available", execution_id, as_of=iso(now), replay=replay)
        projection.update({name: envelope[name] for name in (
            "confirm_id", "call_id", "session_id", "run_id", "admission_epoch", "tool_name", "requested_at", "expires_at")})
        projection.update(state=dispatch_state, request_digest=intent["request_digest"],
                          attempt_request_id=intent["attempt_request_id"], claimed_at=iso(claim["claimed_at"]) if claim else None,
                          observe_by=iso(deadline), run_stopped=bool(run["stopped_at"]), integrity_conflict=conflict,
                          target_verification_required=bool(claim) or dispatch_state == "outcome_unknown",
                          receipt=receipt, observations=observations,
                          observations_truncated=truncated, next_observation_cursor=next_cursor)
        if dispatch_state is None:
            projection["preparation_state"] = "registered"
        return projection

    def lookup(self, execution_id, *, replay=True):
        known_id = None
        try:
            UUID(execution_id)
            known_id = execution_id
            with self.connection() as conn:
                conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                verify_schema(conn)
                now = conn.execute("SELECT clock_timestamp()").fetchone()[0]
                return self._project(conn, execution_id, now=now, replay=replay)
        except (ProtocolError, ValueError, TypeError, AttributeError):
            return self.empty("unavailable", known_id, replay=replay)

    @staticmethod
    def _owner_scope(session_id, owner_user_id):
        if any(not isinstance(value, str) or not 0 < len(value) <= 256
               for value in (session_id, owner_user_id)):
            raise ProtocolError("bad_request")

    @staticmethod
    def _execution_id(value):
        try:
            if not isinstance(value, str) or str(UUID(value)) != value:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise ProtocolError("bad_request") from None

    def _encode_cursor(self, scope, position):
        # No identities or signed envelopes in the token. A domain-separated
        # MAC binds the opaque keyset position to this owner/session/read kind.
        raw = position.to_bytes(8, "big")
        message = json.dumps(["execution-recovery-cursor-v1", *scope],
                             ensure_ascii=True, separators=(",", ":")).encode() + raw
        mac = hmac.digest(self._key.encode(), message, "sha256")
        return base64.urlsafe_b64encode(raw + mac).decode().rstrip("=")

    def _decode_cursor(self, scope, cursor):
        if cursor is None:
            return None
        try:
            if not isinstance(cursor, str) or len(cursor) != 54:
                raise ValueError
            raw = base64.b64decode(cursor + "==", altchars=b"-_", validate=True)
            position = int.from_bytes(raw[:8], "big")
            if (not 0 < position < 2**63 or
                    not hmac.compare_digest(cursor, self._encode_cursor(scope, position))):
                raise ValueError
            return position
        except (ValueError, TypeError, UnicodeError):
            raise ProtocolError("bad_request") from None

    def owner_session_recovery(self, session_id, owner_user_id, *, execution=None,
                               cursor=None, page_size=50):
        """Read a bounded ledger-first page, with no presentation-store dependency.

        Without an execution filter the cursor pages registration order; with
        a filter it pages that execution's observations. The HTTP owner check
        precedes this method, and SQL independently enforces the same scope.
        Read failures are unavailable, never a successful empty history.
        """
        self._owner_scope(session_id, owner_user_id)
        if type(page_size) is not int or not 1 <= page_size <= 100:
            raise ProtocolError("bad_request")
        if execution is not None:
            self._execution_id(execution)
        scope = ("executions", session_id, owner_user_id) if execution is None else (
            "observations", session_id, owner_user_id, execution)
        position = self._decode_cursor(scope, cursor)
        unavailable = {"availability": "unavailable", "executions": [],
                       "executions_truncated": False, "next_execution_cursor": None}
        try:
            with self.connection() as conn:
                conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                verify_schema(conn)
                now = conn.execute("SELECT clock_timestamp()").fetchone()[0]
                query = ("SELECT i.execution_id,i.registration_seq FROM execution_intents i "
                         "JOIN execution_runs r USING (run_id) "
                         "WHERE r.session_id=%s AND r.owner_user_id=%s")
                args = [session_id, owner_user_id]
                if execution is not None:
                    query += " AND i.execution_id=%s"
                    args.append(execution)
                elif position is not None:
                    query += " AND i.registration_seq>%s"
                    args.append(position)
                rows = self._all(conn, query + " ORDER BY i.registration_seq LIMIT %s", (*args, page_size + 1))
                projections = [self._project(
                    conn, str(row["execution_id"]), now=now, replay=False,
                    page_after=position if execution else None,
                    cursor_scope=("observations", session_id, owner_user_id, str(row["execution_id"])),
                ) for row in rows[:page_size]]
                more = len(rows) > page_size
                return {"availability": "available", "executions": projections,
                        "executions_truncated": more,
                        "next_execution_cursor": self._encode_cursor(scope, rows[page_size - 1]["registration_seq"])
                        if more else None}
        except (ProtocolError, ValueError, TypeError, AttributeError):
            return unavailable

    def owner_recovery(self, execution_id, session_id, owner_user_id, *, cursor=None, replay=False):
        """Bounded owner-session recovery read (SPEC-063 R-5a).

        Returns the current projection plus a cursor-paged observation window
        for one execution, scoped to the run owner. Possession of an execution
        id never authorizes access: a caller who is not the run owner, or who
        names a foreign or forged id, gets ``not_found`` with no distinguishing
        detail (anti-enumeration). Reads the SPEC-063 ledger independently of
        the legacy confirmation/presentation rows, so a lost card or history
        write never hides an outcome; a ledger outage yields ``unavailable``.
        A recovery read is never an original response and confers no dispatch,
        continuation, or secret-release permit.
        """
        self._execution_id(execution_id)
        self._owner_scope(session_id, owner_user_id)
        scope = ("observations", session_id, owner_user_id, execution_id)
        page_after = self._decode_cursor(scope, cursor)
        try:
            with self.connection() as conn:
                conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                verify_schema(conn)
                now = conn.execute("SELECT clock_timestamp()").fetchone()[0]
                owned = conn.execute(
                    "SELECT 1 FROM execution_intents i JOIN execution_runs r USING (run_id) "
                    "WHERE i.execution_id=%s AND r.session_id=%s AND r.owner_user_id=%s",
                    (execution_id, session_id, owner_user_id)).fetchone()
                if not owned:
                    return self.empty("not_found", execution_id, as_of=iso(now), replay=replay)
                return self._project(conn, execution_id, now=now, replay=replay,
                                     page_after=page_after, cursor_scope=scope)
        except (ProtocolError, ValueError, TypeError, AttributeError):
            return self.empty("unavailable", execution_id, replay=replay)

    @staticmethod
    def empty(availability, execution_id=None, *, as_of=None, replay=True):
        return {"recovery_version": 1, "availability": availability, "state": None,
                "execution_id": execution_id, "confirm_id": None, "call_id": None, "session_id": None,
                "run_id": None, "admission_epoch": None, "tool_name": None, "attempt_request_id": None,
                "request_digest": None, "requested_at": None, "expires_at": None,
                "claimed_at": None, "observe_by": None, "as_of": as_of, "replay": replay,
                "run_stopped": False, "integrity_conflict": False, "target_verification_required": True,
                "receipt": None, "observations": [], "observations_truncated": False, "next_observation_cursor": None}
