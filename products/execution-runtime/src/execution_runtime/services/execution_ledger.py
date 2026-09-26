"""Durable single-use dispatch authority. No leases, takeover, or memory fallback."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
import os
import hashlib
import time
import threading
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from execution_runtime.services.execution_migration import connect, verify_schema
from execution_runtime.services.execution_protocol import (
    OBSERVE_SECONDS, ProtocolError, iso, observation, timestamp, validate_observation, validate_request,
)
from execution_runtime.services.execution_signing import canonical_digest

_AUTHORITY = object()
_RESERVED = {"claim_committed": "claim", "worker_result": "result", "wait_expired": "timeout",
             "run_stopped": "stop", "response_accepted": "acceptance"}
_UNCERTAIN = {"wait_expired", "transport_uncertain", "result_persistence_unconfirmed"}

# One bounded aggregate for the operational gauges (SPEC-063 R-7c). "Unresolved"
# is a minted claim on a live run with no recorded worker_result; the oldest age
# is measured with the DATABASE clock so a scrape never depends on host time and
# never resets a deadline. Read-only: it mints no permit and releases no claim.
_UNRESOLVED_SQL = (
    "SELECT count(*) AS unresolved_count, "
    "coalesce(extract(epoch FROM (clock_timestamp() - min(c.claimed_at))), 0) AS oldest_age_seconds "
    "FROM execution_dispatch_claims c "
    "JOIN execution_intents i ON i.execution_id = c.execution_id "
    "JOIN execution_runs r ON r.run_id = i.run_id "
    "WHERE r.stopped_at IS NULL AND NOT EXISTS ("
    "SELECT 1 FROM execution_observations o "
    "WHERE o.execution_id = c.execution_id AND o.kind = 'worker_result')"
)


class DispatchPermit:
    __slots__ = ("execution_id", "run_id", "request_digest", "owner_id", "_pid", "_used", "_lock")

    def __init__(self, authority, envelope, owner_id):
        if authority is not _AUTHORITY:
            raise TypeError("dispatch permits require acknowledged durable admission")
        self.execution_id, self.run_id = envelope["execution_id"], envelope["run_id"]
        self.request_digest, self.owner_id = canonical_digest(envelope), owner_id
        self._pid, self._used, self._lock = os.getpid(), False, threading.Lock()

    def consume(self, envelope):
        with self._lock:
            if self._used or self._pid != os.getpid() or self.request_digest != canonical_digest(envelope):
                raise ProtocolError("identity_conflict")
            self._used = True

    def __reduce__(self):
        raise TypeError("dispatch permits cannot be serialized or copied")

    def __copy__(self):
        raise TypeError("dispatch permits cannot be copied")

    def __deepcopy__(self, memo):
        raise TypeError("dispatch permits cannot be copied")


@dataclass(frozen=True)
class ClaimDecision:
    permit: DispatchPermit | None = None
    reason: str = "none"
    observation: dict | None = None


class ExecutionLedger:
    def __init__(self, dsn, key, epoch, *, admission_enabled=False, connection_factory=connect):
        self._dsn, self._key, self._epoch = dsn, key, epoch
        self._enabled, self._connect = admission_enabled, connection_factory

    @contextmanager
    def connection(self):
        connection = self._connect(self._dsn)
        try:
            yield connection
        finally:
            connection.close()

    def health(self):
        try:
            with self.connection() as conn:
                state = verify_schema(conn)
            reason = ("admission_disabled" if not self._enabled or not state["admission_enabled"] else
                      "epoch_mismatch" if state["admission_epoch"] != self._epoch else "none")
            return {"actual_backend": "postgres", "schema_ready": True,
                    "admission_enabled": reason == "none", "reason_code": reason}
        except (psycopg.Error, ProtocolError) as exc:
            return {"actual_backend": "unavailable", "schema_ready": False, "admission_enabled": False,
                    "reason_code": exc.reason if isinstance(exc, ProtocolError) else "store_unavailable"}

    def metrics_snapshot(self):
        """Bounded read-only projection for the operational gauges (R-7c).

        Publishes actual admission availability plus the unresolved-claim count
        and the oldest unresolved age measured with the database clock. Fails
        open: an unreachable or damaged store yields ``store_unavailable`` with
        zeroed gauges rather than raising, so a scrape can never break the
        metrics surface. This performs no execution work.
        """
        try:
            with self.connection() as conn:
                conn.execute("SET TRANSACTION READ ONLY")
                state = verify_schema(conn)
                available = bool(self._enabled and state["admission_enabled"]
                                 and state["admission_epoch"] == self._epoch)
                reason = ("none" if available else
                          "epoch_mismatch" if state["admission_epoch"] != self._epoch
                          else "admission_disabled")
                row = self._one(conn, _UNRESOLVED_SQL)
                return {"admission_available": available, "reason_code": reason,
                        "unresolved_count": int(row["unresolved_count"] or 0),
                        "oldest_unresolved_age_seconds": float(row["oldest_age_seconds"] or 0.0)}
        except (psycopg.Error, ProtocolError):
            return {"admission_available": False, "reason_code": "store_unavailable",
                    "unresolved_count": 0, "oldest_unresolved_age_seconds": 0.0}

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

    def _intent(self, conn, execution_id):
        return self._one(conn, "SELECT * FROM execution_intents WHERE execution_id=%s", (execution_id,))

    def _run(self, conn, run_id):
        return self._one(conn, "SELECT * FROM execution_runs WHERE run_id=%s FOR UPDATE", (run_id,))

    def _predecessor(self, conn, intent):
        return conn.execute(
            "SELECT EXISTS (SELECT 1 FROM execution_intents i "
            "LEFT JOIN execution_observation_state s USING (execution_id) "
            "WHERE i.run_id=%s AND i.registration_seq<%s AND "
            "(coalesce(s.integrity_conflict,false) OR NOT EXISTS ("
            "SELECT 1 FROM execution_observations a JOIN execution_observations r ON "
            "r.execution_id=a.execution_id AND r.kind='worker_result' "
            "AND r.payload->>'receipt_digest'=a.payload->>'receipt_digest' "
            "WHERE a.execution_id=i.execution_id AND a.kind='response_accepted')))",
            (intent["run_id"], intent["registration_seq"])).fetchone()[0]

    def claim(self, envelope, current_request_id):
        validate_request(envelope, self._key)
        committing = False
        try:
            with self.connection() as conn:
                state = verify_schema(conn)
                run = self._run(conn, envelope["run_id"])
                intent = self._intent(conn, envelope["execution_id"])
                if not intent:
                    collision = conn.execute("SELECT 1 FROM execution_intents WHERE confirm_id=%s AND call_id=%s",
                                             (envelope["confirm_id"], envelope["call_id"])).fetchone()
                    return ClaimDecision(reason="identity_conflict" if collision else "request_missing")
                if (intent["request_digest"] != canonical_digest(envelope) or not run
                        or run["owner_user_id"] != envelope["owner_user_id"]
                        or run["session_id"] != envelope["session_id"]):
                    return ClaimDecision(reason="identity_conflict")
                existing = conn.execute("SELECT 1 FROM execution_dispatch_claims WHERE execution_id=%s",
                                        (envelope["execution_id"],)).fetchone()
                if existing:
                    # Keep the new HTTP id without replacing the registered attempt.
                    # Ordinary-slot overflow remains bounded and never mints a permit.
                    fact = observation(envelope, source="worker", kind="duplicate_seen",
                                       attempt_request_id=intent["attempt_request_id"],
                                       current_request_id=current_request_id, key=self._key,
                                       reason="metadata_replay")
                    retained = self._append(conn, intent, fact) == "inserted"
                    conn.commit()
                    return ClaimDecision(reason="metadata_replay", observation=fact if retained else None)
                if not self._enabled or not state["admission_enabled"]:
                    return ClaimDecision(reason="admission_disabled")
                if self._epoch != envelope["admission_epoch"] or state["admission_epoch"] != self._epoch:
                    return ClaimDecision(reason="epoch_mismatch")
                if run["stopped_at"]:
                    return ClaimDecision(reason="run_stopped")
                if self._predecessor(conn, intent):
                    return ClaimDecision(reason="predecessor_unresolved")
                now = conn.execute("SELECT clock_timestamp()").fetchone()[0]
                if timestamp(envelope["requested_at"]) > now:
                    return ClaimDecision(reason="request_not_yet_valid")
                if timestamp(envelope["expires_at"]) <= now:
                    return ClaimDecision(reason="request_expired")
                owner = str(uuid4())
                inserted = conn.execute(
                    "INSERT INTO execution_dispatch_claims "
                    "(execution_id,confirm_id,call_id,request_digest,claim_owner_id,claimed_at,observe_by,retain_until) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING execution_id",
                    (envelope["execution_id"], envelope["confirm_id"], envelope["call_id"],
                     intent["request_digest"], owner, now, now + timedelta(seconds=OBSERVE_SECONDS),
                     timestamp(envelope["expires_at"]) + timedelta(days=30))).fetchone()
                if not inserted:
                    return ClaimDecision(reason="identity_conflict")
                fact = observation(envelope, source="worker", kind="claim_committed",
                                   attempt_request_id=intent["attempt_request_id"], current_request_id=current_request_id,
                                   key=self._key, observed_at=now, claim_owner_id=owner)
                if self._append(conn, intent, fact) != "inserted":
                    raise ProtocolError("integrity_conflict")
                committing = True
                conn.commit()
                # This is the only minting site. No post-error read can reach it.
                return ClaimDecision(DispatchPermit(_AUTHORITY, envelope, owner), observation=fact)
        except (psycopg.Error, ProtocolError) as exc:
            reason = exc.reason if isinstance(exc, ProtocolError) else "store_unavailable"
            return ClaimDecision(reason="claim_commit_unconfirmed" if committing else reason)

    @staticmethod
    def lock_key(run_id):
        return int.from_bytes(hashlib.sha256(str(run_id).encode()).digest()[:8], "big", signed=True)

    def _mutex(self, conn, run_id):
        # Session lock, not a long-lived transaction over the gateway exchange.
        conn.autocommit = True
        deadline = time.monotonic() + 2
        while True:
            if conn.execute("SELECT pg_try_advisory_lock(%s)", (self.lock_key(run_id),)).fetchone()[0]:
                return
            if time.monotonic() >= deadline:
                raise ProtocolError("send_lock_unavailable")
            time.sleep(0.01)

    def open_send(self, permit, envelope):
        """Burn the local permit and acquire the final send/stop linearization gate."""
        permit.consume(envelope)
        conn = self._connect(self._dsn)
        try:
            self._mutex(conn, envelope["run_id"])
            with conn.transaction():
                state = verify_schema(conn)
                run = self._run(conn, envelope["run_id"])
                intent = self._intent(conn, envelope["execution_id"])
                claim = self._one(conn, "SELECT * FROM execution_dispatch_claims WHERE execution_id=%s",
                                  (envelope["execution_id"],))
                if (not intent or intent["request_digest"] != permit.request_digest or not claim
                        or str(claim["claim_owner_id"]) != permit.owner_id):
                    raise ProtocolError("identity_conflict")
                if not self._enabled or not state["admission_enabled"]:
                    raise ProtocolError("admission_disabled")
                if state["admission_epoch"] != self._epoch or envelope["admission_epoch"] != self._epoch:
                    raise ProtocolError("epoch_mismatch")
                if not run or run["stopped_at"]:
                    raise ProtocolError("run_stopped")
                integrity = conn.execute("SELECT integrity_conflict FROM execution_observation_state WHERE execution_id=%s",
                                         (envelope["execution_id"],)).fetchone()
                if not integrity or integrity[0]:
                    raise ProtocolError("integrity_conflict")
                if self._predecessor(conn, intent):
                    raise ProtocolError("predecessor_unresolved")
            return conn
        except BaseException:
            conn.close()
            raise

    def finish(self, conn, envelope, fact, *, stop_reason=None):
        """Commit metadata before releasing the caller-owned session mutex."""
        with conn.transaction():
            verify_schema(conn)
            run = self._run(conn, envelope["run_id"])
            intent = self._intent(conn, envelope["execution_id"])
            if not run or not intent or intent["request_digest"] != canonical_digest(envelope):
                raise ProtocolError("identity_conflict")
            result = self._append(conn, intent, fact)
            if stop_reason:
                conn.execute("UPDATE execution_runs SET stopped_at=clock_timestamp(),stop_reason=%s "
                             "WHERE run_id=%s AND stopped_at IS NULL", (stop_reason, envelope["run_id"]))
        return result

    def stop(self, envelope, fact, *, reason):
        """A stop and its attributed fact are atomic and can never reset a run."""
        with self.connection() as conn:
            self._mutex(conn, envelope["run_id"])
            with conn.transaction():
                self._run(conn, envelope["run_id"])
                if fact["kind"] == "pre_dispatch_refused" and conn.execute(
                    "SELECT 1 FROM execution_dispatch_claims WHERE execution_id=%s",
                    (envelope["execution_id"],)).fetchone():
                    raise ProtocolError("claim_commit_unconfirmed")
                return self.finish(conn, envelope, fact, stop_reason=reason)

    def _conflict(self, conn, execution_id, digest):
        conn.execute("UPDATE execution_observation_state SET integrity_conflict=true, "
                     "first_conflicting_digest=coalesce(first_conflicting_digest,%s) WHERE execution_id=%s",
                     (digest, execution_id))

    def _append(self, conn, intent, fact):
        envelope = intent["request_envelope"]
        validate_observation(fact, envelope, self._key)
        if fact["attempt_request_id"] != intent["attempt_request_id"]:
            raise ProtocolError("identity_conflict")
        execution_id, digest = envelope["execution_id"], canonical_digest(fact)
        state = self._one(conn, "SELECT * FROM execution_observation_state WHERE execution_id=%s FOR UPDATE",
                          (execution_id,))
        if state is None:
            raise ProtocolError("schema_invalid")
        existing = self._one(conn, "SELECT content_digest FROM execution_observations WHERE observation_id=%s",
                             (fact["observation_id"],))
        if existing:
            if existing["content_digest"] == digest:
                conn.execute("UPDATE execution_observation_state SET duplicate_count=least(2147483647::bigint, "
                             "duplicate_count::bigint+1) WHERE execution_id=%s", (execution_id,))
                return "identical"
            self._conflict(conn, execution_id, digest)
            return "conflict"
        if fact["kind"] in {"worker_result", "claim_committed"}:
            claim = self._one(conn, "SELECT claim_owner_id FROM execution_dispatch_claims WHERE execution_id=%s",
                              (execution_id,))
            if not claim or str(claim["claim_owner_id"]) != fact["claim_owner_id"]:
                raise ProtocolError("identity_conflict")
        slot = _RESERVED.get(fact["kind"])
        if fact["kind"] == "worker_result":
            first = self._one(conn, "SELECT payload FROM execution_observations WHERE execution_id=%s AND kind='worker_result' "
                             "ORDER BY insertion_seq LIMIT 1", (execution_id,))
            if first and first["payload"]["receipt_digest"] != fact["receipt_digest"]:
                self._conflict(conn, execution_id, digest)
                slot = "conflict"
        if fact["kind"] == "response_accepted":
            run = self._run(conn, envelope["run_id"])
            result = conn.execute("SELECT 1 FROM execution_observations WHERE execution_id=%s "
                                  "AND kind='worker_result' AND payload->>'receipt_digest'=%s",
                                  (execution_id, fact["receipt_digest"])).fetchone()
            if not result or run["stopped_at"] or state["integrity_conflict"]:
                raise ProtocolError("run_stopped")
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
                     "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                     (fact["observation_id"], execution_id, fact["source"], fact["kind"], slot, Jsonb(fact), digest))
        if slot is None:
            conn.execute("UPDATE execution_observation_state SET ordinary_count=ordinary_count+1 WHERE execution_id=%s",
                         (execution_id,))
        return "inserted"

    def append(self, execution_id, fact, *, source="worker"):
        if fact.get("source") != source:
            raise ProtocolError("bad_request")
        with self.connection() as conn:
            verify_schema(conn)
            intent = self._intent(conn, execution_id)
            if intent is None:
                raise ProtocolError("request_missing")
            self._run(conn, intent["run_id"])
            result = self._append(conn, intent, fact)
            conn.commit()
            # Conflict is a committed result, never an exception inside the transaction.
            return result

    def retention_sweep(self, *, batch=500):
        """Bounded, independent ledger retention sweep (SPEC-063 R-7a).

        Only rows whose signed request expired at least 30 days ago are
        eligible. The ``execution_immutable`` trigger re-checks every deleted
        row against the database clock, so a wrong cutoff cannot reclaim
        protected evidence; this method never widens that horizon. Deletes run
        in foreign-key order (observations, observation state, claims, then
        intents) and never touch ``execution_runs``, which outlive their
        dependent claims/intents. This is deliberately separate from the
        presentation store's ``requested_at`` sweep and reclaims durable rows
        only; it confers no dispatch, continuation, or secret-release authority
        and cannot resurrect a stopped run. Bounded per call: repeat to drain a
        backlog. Returns per-table delete counts.
        """
        if type(batch) is not int or not 1 <= batch <= 5000:
            raise ProtocolError("bad_request")
        with self.connection() as conn:
            # Autocommit before the explicit block so ``conn.transaction()`` is
            # a top-level transaction (matching ``stop``), not a savepoint that
            # would roll the deletes back when the connection context closes.
            conn.autocommit = True
            verify_schema(conn)
            with conn.transaction():
                # Enabled only for this transaction; the trigger still refuses
                # any row inside its 30-day post-expiry protection window.
                conn.execute("SET LOCAL luban.execution_retention='on'")
                eligible = [row[0] for row in conn.execute(
                    "SELECT execution_id FROM execution_intents "
                    "WHERE expires_at + interval '30 days' <= clock_timestamp() "
                    "ORDER BY registration_seq LIMIT %s", (batch,)).fetchall()]
                if not eligible:
                    return {"eligible": 0, "observations": 0, "claims": 0, "intents": 0}
                counts = {"eligible": len(eligible)}
                counts["observations"] = conn.execute(
                    "DELETE FROM execution_observations WHERE execution_id = ANY(%s)",
                    (eligible,)).rowcount
                conn.execute("DELETE FROM execution_observation_state WHERE execution_id = ANY(%s)",
                             (eligible,))
                counts["claims"] = conn.execute(
                    "DELETE FROM execution_dispatch_claims WHERE execution_id = ANY(%s)",
                    (eligible,)).rowcount
                counts["intents"] = conn.execute(
                    "DELETE FROM execution_intents WHERE execution_id = ANY(%s)",
                    (eligible,)).rowcount
                return counts

    def lookup(self, execution_id, *, replay=True):
        try:
            with self.connection() as conn:
                conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                verify_schema(conn)
                now = conn.execute("SELECT clock_timestamp()").fetchone()[0]
                intent = self._intent(conn, execution_id)
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
                rows = self._all(conn, "SELECT payload,content_digest FROM execution_observations "
                                 "WHERE execution_id=%s ORDER BY insertion_seq LIMIT 71", (execution_id,))
                facts = []
                conflict = state["integrity_conflict"]
                for row in rows:
                    fact = row["payload"]
                    try:
                        validate_observation(fact, envelope, self._key)
                        if (canonical_digest(fact) != row["content_digest"]
                                or fact["attempt_request_id"] != intent["attempt_request_id"]
                                or (fact["kind"] in {"worker_result", "claim_committed"} and
                                    (not claim or fact["claim_owner_id"] != str(claim["claim_owner_id"])))):
                            raise ProtocolError("integrity_conflict")
                        facts.append(fact)
                    except ProtocolError:
                        conflict = True
                receipts = {fact["receipt_digest"]: fact["receipt"] for fact in facts if fact["kind"] == "worker_result"}
                conflict = conflict or len(receipts) > 1
                deadline = claim["observe_by"] if claim else intent["registered_at"] + timedelta(seconds=OBSERVE_SECONDS)
                kinds = {fact["kind"] for fact in facts}
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
                projection = self.empty("available", execution_id, as_of=iso(now), replay=replay)
                projection.update({name: envelope[name] for name in (
                    "confirm_id", "call_id", "session_id", "run_id", "admission_epoch", "tool_name", "requested_at", "expires_at")})
                projection.update(state=dispatch_state, request_digest=intent["request_digest"],
                                  attempt_request_id=intent["attempt_request_id"], claimed_at=iso(claim["claimed_at"]) if claim else None,
                                  observe_by=iso(deadline), run_stopped=bool(run["stopped_at"]), integrity_conflict=conflict,
                                  target_verification_required=bool(claim) or dispatch_state == "outcome_unknown",
                                  receipt=receipt, observations=facts[:20],
                                  observations_truncated=state["overflow"] or len(facts) > 20)
                if dispatch_state is None:
                    projection["preparation_state"] = "registered"
                return projection
        except (psycopg.Error, ProtocolError):
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
