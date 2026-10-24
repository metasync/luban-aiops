"""Concrete OQ-7 routing stores. Construction does not register authorization routes."""
from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from pydantic import SecretStr

from tool_gateway.services.authorization_transactions import AuthorizationLifetimes, AuthorizationTransaction
from tool_gateway.services.custody_crypto import CustodyError, capability_hash
from tool_gateway.services.delegated_custody import Owner, PostgresCustodyStore


@dataclass(frozen=True)
class CallbackClaim:
    transaction: AuthorizationTransaction
    operation: SecretStr = field(repr=False)
    verifier: SecretStr = field(repr=False)


def transaction_binding(row):
    return {**{key: row[key] for key in ("challenge_id", "set_id", "target", "owner_namespace", "owner_sub",
        "config_generation", "credential_epoch", "session_id", "call_id", "return_url")},
        "expires_at": row["expires_at"].isoformat()}


def projection(row):
    return AuthorizationTransaction(challenge_id=row["challenge_id"], owner_namespace=row["owner_namespace"],
        owner_sub=row["owner_sub"], target=row["target"], credential_set_id=row["set_id"],
        config_generation=row["config_generation"], session_id=row["session_id"], call_id=row["call_id"],
        return_url=row["return_url"], status=row["status"], consumed=row["consumed"],
        created_at=row["created_at"], updated_at=row["updated_at"], expires_at=row["expires_at"])


class MemoryAuthorizationTransactionStore:
    backend_name = "memory"
    shared = False

    def __init__(self, *, clock=time.monotonic, lifetimes=None):
        self._clock = clock
        self._lifetimes = lifetimes or AuthorizationLifetimes()
        self._records = {}
        self._deadlines = {}
        self._secrets = {}

    async def initialize(self):
        return None

    async def create(self, transaction):
        if (transaction.challenge_id in self._records or len(self._records) >= 10000
                or transaction.status != "pending" or transaction.consumed):
            raise CustodyError("transaction_conflict")
        seconds = min((transaction.expires_at - datetime.now(timezone.utc)).total_seconds(),
                      self._lifetimes.transaction_ttl_seconds)
        if seconds <= 0:
            raise CustodyError("transaction_expired")
        self._records[transaction.challenge_id] = transaction
        self._deadlines[transaction.challenge_id] = self._clock() + seconds

    def _owned(self, challenge_id, namespace, subject, now):
        row = self._records.get(challenge_id)
        if not row or row.owner_namespace != namespace or row.owner_sub != subject:
            return None
        if row.status == "pending" and (self._clock() >= self._deadlines[challenge_id] or now >= row.expires_at):
            row = row.model_copy(update={"status": "expired", "updated_at": now})
            self._records[challenge_id] = row
            self._secrets.pop(challenge_id, None)
        return row

    async def get(self, challenge_id, owner_namespace, owner_sub, *, now):
        return self._owned(challenge_id, owner_namespace, owner_sub, now)

    async def claim_callback(self, challenge_id, owner_namespace, owner_sub, config_generation, *, now):
        row = self._owned(challenge_id, owner_namespace, owner_sub, now)
        if not row or row.status != "pending" or row.consumed or row.config_generation != config_generation:
            return None
        self._records[challenge_id] = row.model_copy(update={"consumed": True, "updated_at": now})
        return self._records[challenge_id]

    async def finish(self, challenge_id, owner_namespace, owner_sub, config_generation, status, *, now):
        row = self._owned(challenge_id, owner_namespace, owner_sub, now)
        # Memory routing state cannot prove a committed durable credential installation.
        if (status not in {"failed", "canceled", "expired"} or not row or not row.consumed
                or row.status != "pending" or row.config_generation != config_generation):
            return False
        self._records[challenge_id] = row.model_copy(update={"status": status, "updated_at": now})
        self._secrets.pop(challenge_id, None)
        return True

    async def cancel(self, challenge_id, owner_namespace, owner_sub, *, now):
        row = self._owned(challenge_id, owner_namespace, owner_sub, now)
        if row and row.status == "pending":
            self._records[challenge_id] = row.model_copy(update={"status": "canceled", "updated_at": now})
            self._secrets.pop(challenge_id, None)

    async def issue_start(self, challenge_id, owner_namespace, owner_sub, *, now):
        row = self._owned(challenge_id, owner_namespace, owner_sub, now)
        if not row or row.status != "pending" or row.consumed:
            return None
        previous = self._secrets.get(challenge_id)
        if previous and previous.get("start_consumed"):
            return None
        token = SecretStr(str(uuid4()))
        self._secrets[challenge_id] = dict(start_hash=capability_hash(token), start_consumed=False,
            expires_at=min(row.expires_at, now + timedelta(seconds=self._lifetimes.start_ttl_seconds)),
            deadline=min(self._deadlines[challenge_id], self._clock() + self._lifetimes.start_ttl_seconds))
        return token

    async def consume_start(self, token, *, now):
        digest = capability_hash(token)
        for challenge_id, data in self._secrets.items():
            if data["start_hash"] == digest:
                row = self._records[challenge_id]
                row = self._owned(challenge_id, row.owner_namespace, row.owner_sub, now)
                if (row.status != "pending" or row.consumed or data["start_consumed"]
                        or self._clock() >= data["deadline"] or now >= data["expires_at"]):
                    return None
                data["start_consumed"] = True
                return row
        return None

    async def prepare_state(self, challenge_id, owner_namespace, owner_sub, *, now):
        row = self._owned(challenge_id, owner_namespace, owner_sub, now)
        data = self._secrets.get(challenge_id)
        if (not row or row.status != "pending" or row.consumed or not data
                or not data["start_consumed"] or "state_hash" in data):
            return None
        state, verifier = SecretStr(secrets.token_urlsafe(32)), SecretStr(secrets.token_urlsafe(48))
        data.update(state_hash=capability_hash(state), verifier=verifier)
        return state, verifier

    async def claim_state(self, state, *, now):
        digest = capability_hash(state)
        for challenge_id, data in list(self._secrets.items()):
            if data.get("state_hash") != digest:
                continue
            row = self._records[challenge_id]
            claimed = await self.claim_callback(challenge_id, row.owner_namespace, row.owner_sub,
                                                row.config_generation, now=now)
            if claimed is None:
                return None
            verifier = data.pop("verifier")
            data.pop("state_hash")
            return CallbackClaim(claimed, SecretStr(secrets.token_urlsafe(32)), verifier)
        return None

    async def expire(self, *, now, limit):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise CustodyError("invalid_batch")
        expired = 0
        for handle, row in list(self._records.items()):
            if expired >= limit:
                break
            current = self._owned(handle, row.owner_namespace, row.owner_sub, now)
            if current.status != "pending" and self._clock() >= self._deadlines[handle] + 300:
                self._records.pop(handle)
                self._deadlines.pop(handle)
                self._secrets.pop(handle, None)
                expired += 1
        return expired

    async def ready(self):
        return True

    async def close(self):
        self._records.clear()
        self._deadlines.clear()
        self._secrets.clear()


class PostgresAuthorizationTransactionStore:
    backend_name = "postgres"
    shared = True

    def __init__(self, custody: PostgresCustodyStore, *, lifetimes=None):
        self.custody = custody
        self.lifetimes = lifetimes or AuthorizationLifetimes()

    async def initialize(self):
        await self.custody.initialize()

    async def create(self, transaction):
        if transaction.status != "pending" or transaction.consumed:
            raise CustodyError("invalid_transaction")
        async with self.custody.guarded() as (conn, config, linkage, keys, generation):
            if (transaction.credential_set_id != self.custody.set_id or transaction.config_generation != generation
                    or transaction.target != config.value("target")):
                raise CustodyError("configuration_changed")
            owner = Owner(transaction.owner_namespace, transaction.owner_sub)
            credential = await self.custody.binding_row(conn, config, keys, generation, owner)
            now = (await (await conn.execute("SELECT clock_timestamp() AS now")).fetchone())["now"]
            expiry = min(transaction.expires_at, now + timedelta(seconds=self.lifetimes.transaction_ttl_seconds))
            if expiry <= now:
                raise CustodyError("transaction_expired")
            await conn.execute("INSERT INTO gateway_custody.transactions"
                "(challenge_id,set_id,target,owner_namespace,owner_sub,config_generation,credential_epoch,session_id,call_id,"
                "return_url,status,consumed,created_at,updated_at,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',FALSE,%s,%s,%s)",
                (transaction.challenge_id, self.custody.set_id, transaction.target, owner.namespace, owner.subject,
                 generation, credential["epoch"], transaction.session_id, transaction.call_id, transaction.return_url, now, now, expiry))
            await conn.execute("INSERT INTO gateway_custody.transaction_secrets(challenge_id) VALUES(%s)", (transaction.challenge_id,))

    async def _owned(self, conn, challenge_id, owner_namespace, owner_sub):
        row = await (await conn.execute("SELECT *,clock_timestamp() AS db_now FROM gateway_custody.transactions WHERE challenge_id=%s"
            " AND set_id=%s AND owner_namespace=%s AND owner_sub=%s FOR UPDATE",
            (challenge_id, self.custody.set_id, owner_namespace, owner_sub))).fetchone()
        if row and row["status"] == "pending" and row["expires_at"] <= row["db_now"]:
            await conn.execute("UPDATE gateway_custody.transactions SET status='expired',updated_at=clock_timestamp() WHERE challenge_id=%s",
                               (challenge_id,))
            await conn.execute("DELETE FROM gateway_custody.transaction_secrets WHERE challenge_id=%s", (challenge_id,))
            row.update(status="expired", updated_at=row["db_now"])
        return row

    async def get(self, challenge_id, owner_namespace, owner_sub, *, now):
        async with self.custody.connection() as conn:
            await conn.execute("SELECT set_id FROM gateway_custody.configurations WHERE set_id=%s FOR UPDATE", (self.custody.set_id,))
            row = await self._owned(conn, challenge_id, owner_namespace, owner_sub)
            return projection(row) if row else None

    async def _credential_current(self, conn, row):
        current = await (await conn.execute("SELECT epoch,config_generation FROM gateway_custody.credentials"
            " WHERE set_id=%s AND target=%s AND owner_namespace=%s AND owner_sub=%s",
            (self.custody.set_id, row["target"], row["owner_namespace"], row["owner_sub"]))).fetchone()
        return (current is not None and current["epoch"] == row["credential_epoch"]
                and current["config_generation"] == row["config_generation"])

    async def issue_start(self, challenge_id, owner_namespace, owner_sub, *, now):
        async with self.custody.guarded() as (conn, config, linkage, keys, generation):
            row = await self._owned(conn, challenge_id, owner_namespace, owner_sub)
            if (not row or row["status"] != "pending" or row["consumed"] or row["config_generation"] != generation
                    or not await self._credential_current(conn, row)):
                return None
            token = SecretStr(str(uuid4()))
            result = await conn.execute("UPDATE gateway_custody.transaction_secrets SET start_hash=%s,"
                "start_expires_at=LEAST(%s,clock_timestamp()+%s * interval '1 second')"
                " WHERE challenge_id=%s AND NOT start_consumed",
                (capability_hash(token), row["expires_at"], self.lifetimes.start_ttl_seconds, challenge_id))
            return token if result.rowcount else None

    async def consume_start(self, token, *, now):
        async with self.custody.guarded() as (conn, config, linkage, keys, generation):
            row = await (await conn.execute("SELECT t.* FROM gateway_custody.transactions t JOIN gateway_custody.transaction_secrets s"
                " USING(challenge_id) WHERE t.set_id=%s AND s.start_hash=%s AND NOT s.start_consumed"
                " AND s.start_expires_at>clock_timestamp() AND t.expires_at>clock_timestamp()"
                " AND t.status='pending' AND NOT t.consumed AND t.config_generation=%s FOR UPDATE OF t,s",
                (self.custody.set_id, capability_hash(token), generation))).fetchone()
            if not row or not await self._credential_current(conn, row):
                return None
            await conn.execute("UPDATE gateway_custody.transaction_secrets SET start_consumed=TRUE,start_hash=NULL WHERE challenge_id=%s",
                               (row["challenge_id"],))
            return projection(row)

    async def prepare_state(self, challenge_id, owner_namespace, owner_sub, *, now):
        async with self.custody.guarded() as (conn, config, linkage, keys, generation):
            row = await self._owned(conn, challenge_id, owner_namespace, owner_sub)
            if (not row or row["status"] != "pending" or row["consumed"] or row["config_generation"] != generation
                    or not await self._credential_current(conn, row)):
                return None
            state, verifier = SecretStr(secrets.token_urlsafe(32)), SecretStr(secrets.token_urlsafe(48))
            cipher = keys.encrypt(verifier, "verifier", transaction_binding(row))
            result = await conn.execute("UPDATE gateway_custody.transaction_secrets SET state_hash=%s,verifier_cipher=%s,key_id=%s"
                " WHERE challenge_id=%s AND start_consumed AND state_hash IS NULL",
                (capability_hash(state), cipher, keys.active_key_id, challenge_id))
            return (state, verifier) if result.rowcount else None

    async def claim_callback(self, challenge_id, owner_namespace, owner_sub, config_generation, *, now):
        # Routing-only claim: without a state proof it cannot install credentials.
        async with self.custody.guarded() as (conn, config, linkage, keys, generation):
            row = await self._owned(conn, challenge_id, owner_namespace, owner_sub)
            if (not row or row["status"] != "pending" or row["consumed"]
                    or row["config_generation"] != generation or config_generation != generation
                    or not await self._credential_current(conn, row)):
                return None
            await conn.execute("UPDATE gateway_custody.transactions SET consumed=TRUE,updated_at=clock_timestamp() WHERE challenge_id=%s",
                               (challenge_id,))
            await conn.execute("DELETE FROM gateway_custody.transaction_secrets WHERE challenge_id=%s", (challenge_id,))
            return projection({**row, "consumed": True})

    async def claim_state(self, state: SecretStr, *, now):
        claim = None
        try:
            async with self.custody.guarded() as (conn, config, linkage, keys, generation):
                row = await (await conn.execute("SELECT t.*,s.verifier_cipher FROM gateway_custody.transactions t"
                    " JOIN gateway_custody.transaction_secrets s USING(challenge_id) WHERE t.set_id=%s AND s.state_hash=%s"
                    " AND t.status='pending' AND NOT t.consumed AND t.expires_at>clock_timestamp()"
                    " AND t.config_generation=%s FOR UPDATE OF t,s", (self.custody.set_id, capability_hash(state), generation))).fetchone()
                if not row or row["verifier_cipher"] is None or not await self._credential_current(conn, row):
                    return None
                verifier = keys.decrypt(bytes(row["verifier_cipher"]), "verifier", transaction_binding(row))
                operation = SecretStr(secrets.token_urlsafe(32))
                await conn.execute("UPDATE gateway_custody.transactions SET consumed=TRUE,updated_at=clock_timestamp() WHERE challenge_id=%s",
                                   (row["challenge_id"],))
                await conn.execute("UPDATE gateway_custody.transaction_secrets SET state_hash=NULL,verifier_cipher=NULL,callback_hash=%s"
                                   " WHERE challenge_id=%s", (capability_hash(operation), row["challenge_id"]))
                claim = CallbackClaim(projection({**row, "consumed": True}), operation, verifier)
                await self.custody.commit(conn, "callback_claim")
            return claim
        except BaseException:
            if claim:
                await asyncio.shield(self._cancel_uncertain_claim(claim, now=now))
            raise

    async def _cancel_uncertain_claim(self, claim: "CallbackClaim", *, now):
        """Compare-and-set cleanup for an unacknowledged callback claim.

        Cancels the challenge only while the stored callback operation still
        belongs to this claim, so a late cleanup of an old claim can never cancel
        a successor claim of the same challenge.
        """
        record = claim.transaction
        try:
            async with self.custody.connection() as conn:
                await conn.execute("SELECT set_id FROM gateway_custody.configurations WHERE set_id=%s FOR UPDATE",
                                   (self.custody.set_id,))
                result = await conn.execute("UPDATE gateway_custody.transactions t SET status='canceled',"
                    "updated_at=clock_timestamp() FROM gateway_custody.transaction_secrets s"
                    " WHERE t.challenge_id=s.challenge_id AND t.challenge_id=%s AND t.set_id=%s"
                    " AND t.owner_namespace=%s AND t.owner_sub=%s AND t.status='pending' AND s.callback_hash=%s",
                    (record.challenge_id, self.custody.set_id, record.owner_namespace, record.owner_sub,
                     capability_hash(claim.operation)))
                if result.rowcount:
                    await conn.execute("DELETE FROM gateway_custody.transaction_secrets WHERE challenge_id=%s",
                                       (record.challenge_id,))
        except CustodyError:
            # The committed claim stays consumed/unusable if the store is down.
            pass

    async def complete_authorization(self, claim: CallbackClaim, *, target_account: str, scopes: str,
                                     refresh_secret: SecretStr | None, refresh_expires_at: datetime | None, now):
        record = claim.transaction
        owner = Owner(record.owner_namespace, record.owner_sub)
        epoch = None
        # A fresh completion-attempt identity, generated before staging can
        # suspend and associated with this exact challenge. It fences cleanup so
        # a rolled-back completion cannot revoke a successor that reused the epoch.
        attempt_id = str(uuid4())
        try:
            async with self.custody.guarded() as (conn, config, linkage, keys, generation):
                credential = await self.custody.binding_row(conn, config, keys, generation, owner)
                row = await self._owned(conn, record.challenge_id, owner.namespace, owner.subject)
                secret_row = await (await conn.execute("SELECT callback_hash FROM gateway_custody.transaction_secrets WHERE challenge_id=%s",
                                                       (record.challenge_id,))).fetchone()
                if (not row or row["status"] != "pending" or not row["consumed"] or row["config_generation"] != generation
                        or credential["epoch"] != row["credential_epoch"] or not secret_row
                        or secret_row["callback_hash"] != capability_hash(claim.operation)):
                    return None
                epoch = credential["epoch"] + 1
                await conn.execute("UPDATE gateway_custody.credentials SET epoch=%s WHERE set_id=%s AND target=%s"
                    " AND owner_namespace=%s AND owner_sub=%s", (epoch, self.custody.set_id, row["target"], owner.namespace, owner.subject))
                publication = SecretStr(secrets.token_urlsafe(32))
                await self.custody.stage(conn, config, linkage, keys, {**credential, "epoch": epoch}, target_account,
                                        scopes, refresh_secret, refresh_expires_at, publication, row["expires_at"], attempt_id)
                await conn.execute("DELETE FROM gateway_custody.transaction_secrets WHERE challenge_id=%s", (record.challenge_id,))
                await self.custody.commit(conn, "authorization_stage")
            metadata = await self.custody._publish(owner, record.config_generation, epoch, publication,
                                                  challenge_id=record.challenge_id)
            self.custody._blocked.discard((owner, attempt_id))
            return metadata
        except BaseException:
            if epoch is not None:
                await asyncio.shield(self.custody._uncertain(owner, record.config_generation, epoch, attempt_id,
                                                             challenge_id=record.challenge_id))
            raise

    async def finish(self, challenge_id, owner_namespace, owner_sub, config_generation, status, *, now):
        if status not in {"failed", "expired", "canceled"}:
            return False
        async with self.custody.guarded() as (conn, config, linkage, keys, generation):
            row = await self._owned(conn, challenge_id, owner_namespace, owner_sub)
            if (not row or row["status"] != "pending" or not row["consumed"]
                    or row["config_generation"] != generation or config_generation != generation):
                return False
            await conn.execute("UPDATE gateway_custody.transactions SET status=%s,updated_at=clock_timestamp() WHERE challenge_id=%s",
                               (status, challenge_id))
            await conn.execute("DELETE FROM gateway_custody.transaction_secrets WHERE challenge_id=%s", (challenge_id,))
            return True

    async def cancel(self, challenge_id, owner_namespace, owner_sub, *, now):
        async with self.custody.connection() as conn:
            await conn.execute("SELECT set_id FROM gateway_custody.configurations WHERE set_id=%s FOR UPDATE", (self.custody.set_id,))
            row = await self._owned(conn, challenge_id, owner_namespace, owner_sub)
            if row and row["status"] == "pending":
                await conn.execute("UPDATE gateway_custody.transactions SET status='canceled',updated_at=clock_timestamp() WHERE challenge_id=%s",
                                   (challenge_id,))
                await conn.execute("DELETE FROM gateway_custody.transaction_secrets WHERE challenge_id=%s", (challenge_id,))

    async def expire(self, *, now, limit):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise CustodyError("invalid_batch")
        async with self.custody.connection() as conn:
            await conn.execute("SELECT set_id FROM gateway_custody.configurations WHERE set_id=%s FOR UPDATE", (self.custody.set_id,))
            rows = await (await conn.execute("SELECT challenge_id FROM gateway_custody.transactions WHERE set_id=%s"
                " AND expires_at<=clock_timestamp() AND status='pending' LIMIT %s FOR UPDATE SKIP LOCKED",
                (self.custody.set_id, limit))).fetchall()
            for row in rows:
                await conn.execute("UPDATE gateway_custody.transactions SET status='expired',updated_at=clock_timestamp() WHERE challenge_id=%s",
                                   (row["challenge_id"],))
                await conn.execute("DELETE FROM gateway_custody.transaction_secrets WHERE challenge_id=%s", (row["challenge_id"],))
            await conn.execute("DELETE FROM gateway_custody.transactions WHERE challenge_id IN"
                "(SELECT challenge_id FROM gateway_custody.transactions WHERE set_id=%s AND status<>'pending'"
                " AND expires_at<clock_timestamp()-interval '300 seconds' LIMIT %s)", (self.custody.set_id, limit))
            return len(rows)

    async def ready(self):
        return await self.custody.ready()

    async def close(self):
        await self.custody.close()


def build_transaction_store(*, backend="memory", replicas=1, custody=None, lifetimes=None, clock=time.monotonic):
    if type(replicas) is not int or replicas < 1:
        raise CustodyError("invalid_replica_count")
    if backend == "memory" and replicas == 1:
        return MemoryAuthorizationTransactionStore(clock=clock, lifetimes=lifetimes)
    if backend == "postgres" and isinstance(custody, PostgresCustodyStore):
        return PostgresAuthorizationTransactionStore(custody, lifetimes=lifetimes)
    raise CustodyError("shared_custody_required")
