"""Internal Postgres custody primitives. No routes, provider calls, or access-token store.

All grant operations serialize on a configuration row before touching a binding.
This deliberately favors auditable fencing over throughput. Provider I/O occurs only
between committed begin/complete calls, never while a database lock is held.
"""
from __future__ import annotations

import asyncio
import hashlib
import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from pydantic import SecretStr

from tool_gateway.services.custody_crypto import CustodyError, Keyring, capability_hash
from tool_gateway.services.custody_schema import DDL, SCHEMA_VERSION, UPGRADE_V1_TO_V2, UPGRADE_V2_TO_V3
from tool_gateway.tools.delegated_configuration import ConfigurationError, load_snapshot


@dataclass(frozen=True)
class Owner:
    namespace: str
    subject: str

    def __post_init__(self):
        if any(not isinstance(v, str) or not v.strip() for v in (self.namespace, self.subject)):
            raise CustodyError("invalid_owner")


@dataclass(frozen=True)
class CredentialMetadata:
    generation: str
    epoch: int
    target_account: str
    scopes: str


@dataclass(frozen=True)
class RefreshClaim:
    owner: Owner
    generation: str
    epoch: int
    attempt_id: str
    operation: SecretStr = field(repr=False)
    refresh_secret: SecretStr = field(repr=False)
    # The absolute renewal deadline carried by the credential before this claim.
    # A renewal may shorten it (a shorter provider refresh expiry) but can never
    # extend it, so the acquisition client caps the replacement deadline against
    # this value. ``None`` only for a credential published without a refresh
    # lifetime, which ``begin_refresh`` never claims.
    original_refresh_expires_at: datetime | None = None


def credential_binding(row):
    return {key: row[key] for key in ("set_id", "target", "owner_namespace", "owner_sub",
                                     "config_generation", "epoch", "target_account", "scopes")}


async def migrate_custody(db_url: str, keyring: Keyring):
    """Explicit migration entry point, never called by runtime initialize().

    Creates a fresh version-3 schema, or upgrades an existing version-1/version-2
    schema in place through each explicit step. Both paths are idempotent and
    never rewrite a published active credential row.
    """
    keys = keyring.snapshot()
    try:
        async with await psycopg.AsyncConnection.connect(db_url, connect_timeout=3, row_factory=dict_row) as conn:
            await conn.execute(DDL)
            row = await (await conn.execute(
                "SELECT version FROM gateway_custody.schema_version WHERE singleton")).fetchone()
            # Apply each upgrade in sequence from the originally observed version:
            # a version-1 database needs both steps, a version-2 database only the
            # browser-binding step, and a fresh version-3 database needs neither.
            observed = row["version"] if row else None
            if observed is not None and observed < 2:
                await conn.execute(UPGRADE_V1_TO_V2)
            if observed is not None and observed < 3:
                await conn.execute(UPGRADE_V2_TO_V3)
            await conn.execute("INSERT INTO gateway_custody.key_policy"
                "(singleton,recovery_epoch,active_key_id,fingerprint_key_hash) VALUES(TRUE,%s,%s,%s)"
                " ON CONFLICT DO NOTHING", (keys.recovery_epoch, keys.active_key_id,
                                             hashlib.sha256(keys.fingerprint_key).hexdigest()))
    except psycopg.Error:
        raise CustodyError("migration_failed") from None


async def recover_custody(db_url: str, keyring: Keyring, *, expected_epoch: str):
    """Explicit offline recovery fence; never called by application startup."""
    keys = keyring.snapshot()
    if keys.recovery_epoch == expected_epoch:
        raise CustodyError("new_recovery_epoch_required")
    try:
        async with await psycopg.AsyncConnection.connect(db_url, connect_timeout=3, row_factory=dict_row) as conn:
            row = await (await conn.execute("SELECT * FROM gateway_custody.key_policy WHERE singleton FOR UPDATE")).fetchone()
            if (not row or row["recovery_epoch"] != expected_epoch
                    or keys.recovery_epoch in row["retired_recovery_epochs"]
                    or keys.active_key_id in row["retired_key_ids"]):
                raise CustodyError("recovery_epoch_conflict")
            await conn.execute("UPDATE gateway_custody.configurations SET active=FALSE")
            await conn.execute("UPDATE gateway_custody.credentials SET status='revoked',epoch=epoch+1,refresh_cipher=NULL,"
                               "operation_hash=NULL,operation_deadline=NULL,attempt_id=NULL,recovery_epoch=%s", (keys.recovery_epoch,))
            await conn.execute("UPDATE gateway_custody.transactions SET status='failed',updated_at=clock_timestamp()"
                               " WHERE status='pending'")
            await conn.execute("DELETE FROM gateway_custody.transaction_secrets")
            await conn.execute("UPDATE gateway_custody.key_policy SET recovery_epoch=%s,active_key_id=%s,"
                               "fingerprint_key_hash=%s,retired_recovery_epochs=array_append(retired_recovery_epochs,%s)"
                               " WHERE singleton", (keys.recovery_epoch, keys.active_key_id,
                               hashlib.sha256(keys.fingerprint_key).hexdigest(), expected_epoch))
    except psycopg.Error:
        raise CustodyError("recovery_failed") from None


class PostgresCustodyStore:
    def __init__(self, db_url: str, keyring: Keyring, config_path: str,
                 set_id: str, trusted_callback: str, *, commit_hook=None):
        self._db_url = db_url
        self.keyring = keyring
        self.config_path = config_path
        self.set_id = set_id
        self.trusted_callback = trusted_callback
        self._observed = None
        # Attempt-scoped process-local uncertainty blocks: (owner, attempt_id).
        # Cleaning or completing one attempt never clears another attempt's block.
        self._blocked: set[tuple[Owner, str]] = set()
        # Test-only fault boundary; no provider result or SQL is passed to the hook.
        self._commit_hook = commit_hook

    def _is_blocked(self, owner: Owner) -> bool:
        return any(blocked_owner == owner for blocked_owner, _attempt in self._blocked)

    @asynccontextmanager
    async def connection(self):
        try:
            conn = await psycopg.AsyncConnection.connect(self._db_url, connect_timeout=3, row_factory=dict_row)
            async with conn:
                await conn.execute("SET LOCAL statement_timeout = '5s'")
                await conn.execute("SET LOCAL lock_timeout = '3s'")
                yield conn
        except psycopg.Error:
            raise CustodyError("store_unavailable") from None

    async def initialize(self):
        async with self.connection() as conn:
            row = await (await conn.execute("SELECT version FROM gateway_custody.schema_version WHERE singleton")).fetchone()
            if not row or row["version"] != SCHEMA_VERSION:
                raise CustodyError("schema_not_ready")
        await self.sync_configuration()

    async def _policy(self, conn, keys, *, writing=True):
        row = await (await conn.execute("SELECT * FROM gateway_custody.key_policy WHERE singleton FOR SHARE")).fetchone()
        if (not row or row["recovery_epoch"] != keys.recovery_epoch
                or row["fingerprint_key_hash"] != hashlib.sha256(keys.fingerprint_key).hexdigest()
                or row["active_key_id"] not in keys.keys
                or (writing and row["active_key_id"] != keys.active_key_id)):
            raise CustodyError("key_policy_mismatch")

    async def _invalidate(self, conn, generation):
        await conn.execute("UPDATE gateway_custody.configurations SET active=FALSE WHERE set_id=%s AND generation=%s",
                           (self.set_id, generation))
        await conn.execute("UPDATE gateway_custody.credentials SET status='revoked',epoch=epoch+1,refresh_cipher=NULL,"
                           "operation_hash=NULL,operation_deadline=NULL,attempt_id=NULL WHERE set_id=%s AND config_generation=%s",
                           (self.set_id, generation))
        await conn.execute("UPDATE gateway_custody.transactions SET status='failed',updated_at=clock_timestamp()"
                           " WHERE set_id=%s AND config_generation=%s AND status='pending'", (self.set_id, generation))
        await conn.execute("DELETE FROM gateway_custody.transaction_secrets WHERE challenge_id IN"
                           "(SELECT challenge_id FROM gateway_custody.transactions WHERE set_id=%s AND config_generation=%s)",
                           (self.set_id, generation))

    async def invalidate_observed(self):
        # Snapshot the observed generation before the first await: a stale
        # invalidation of G1 must never invalidate a G2 that another coroutine
        # activated on this same store while we were acquiring a connection.
        observed = self._observed
        if observed is None:
            return
        async with self.connection() as conn:
            row = await (await conn.execute("SELECT * FROM gateway_custody.configurations WHERE set_id=%s FOR UPDATE",
                                           (self.set_id,))).fetchone()
            if row and row["generation"] == observed and row["active"]:
                await self._invalidate(conn, observed)

    async def sync_configuration(self):
        try:
            config, linkage = load_snapshot(self.config_path, self.set_id, self.trusted_callback)
        except ConfigurationError:
            await self.invalidate_observed()
            raise CustodyError("configuration_unavailable") from None
        keys = self.keyring.snapshot()
        fingerprint = config.fingerprint(keys.fingerprint_key, linkage)
        failure = None
        async with self.connection() as conn:
            await self._policy(conn, keys)
            # Covers initial insert and target replacement under the same named set.
            await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,700016))", (self.set_id,))
            row = await (await conn.execute("SELECT * FROM gateway_custody.configurations WHERE set_id=%s FOR UPDATE",
                                           (self.set_id,))).fetchone()
            if row and config.revision < row["revision"]:
                failure = "stale_configuration"
            elif row and config.revision == row["revision"]:
                if row["fingerprint"] != fingerprint:
                    if row["active"]:
                        await self._invalidate(conn, row["generation"])
                    failure = "configuration_revision_reused"
                elif not row["active"]:
                    failure = "configuration_invalidated"
            else:
                if row:
                    await self._invalidate(conn, row["generation"])
                generation = str(uuid4())
                row = await (await conn.execute("INSERT INTO gateway_custody.configurations"
                    "(set_id,target,revision,fingerprint,generation,active) VALUES(%s,%s,%s,%s,%s,TRUE)"
                    " ON CONFLICT(set_id) DO UPDATE SET target=EXCLUDED.target,revision=EXCLUDED.revision,"
                    "fingerprint=EXCLUDED.fingerprint,generation=EXCLUDED.generation,active=TRUE RETURNING *",
                    (self.set_id, config.value("target"), config.revision, fingerprint, generation))).fetchone()
            if not failure:
                self._observed = row["generation"]
        if failure:
            raise CustodyError(failure)
        return config, linkage, keys, row["generation"], fingerprint

    @asynccontextmanager
    async def guarded(self):
        config, linkage, keys, generation, fingerprint = await self.sync_configuration()
        async with self.connection() as conn:
            await self._policy(conn, keys)
            row = await (await conn.execute("SELECT * FROM gateway_custody.configurations WHERE set_id=%s FOR UPDATE",
                                           (self.set_id,))).fetchone()
            if not row or not row["active"] or row["generation"] != generation or row["fingerprint"] != fingerprint:
                raise CustodyError("configuration_changed")
            yield conn, config, linkage, keys, generation

    async def binding_row(self, conn, config, keys, generation, owner: Owner):
        if not isinstance(owner, Owner):
            raise CustodyError("invalid_owner")
        params = self.set_id, config.value("target"), owner.namespace, owner.subject
        await conn.execute("INSERT INTO gateway_custody.credentials"
            "(set_id,target,owner_namespace,owner_sub,config_generation,epoch,status,recovery_epoch)"
            " VALUES(%s,%s,%s,%s,%s,0,'absent',%s) ON CONFLICT DO NOTHING", (*params, generation, keys.recovery_epoch))
        row = await (await conn.execute("SELECT * FROM gateway_custody.credentials WHERE set_id=%s AND target=%s"
            " AND owner_namespace=%s AND owner_sub=%s FOR UPDATE", params)).fetchone()
        if row["config_generation"] != generation:
            row = await (await conn.execute("UPDATE gateway_custody.credentials SET config_generation=%s,epoch=epoch+1,"
                "status='absent',refresh_cipher=NULL,operation_hash=NULL,operation_deadline=NULL,attempt_id=NULL,recovery_epoch=%s"
                " WHERE set_id=%s AND target=%s AND owner_namespace=%s AND owner_sub=%s RETURNING *",
                (generation, keys.recovery_epoch, *params))).fetchone()
        return row

    async def metadata(self, owner: Owner) -> CredentialMetadata | None:
        if self._is_blocked(owner):
            raise CustodyError("reauthorization_required")
        async with self.guarded() as (conn, config, linkage, keys, generation):
            row = await self.binding_row(conn, config, keys, generation, owner)
            if row["status"] != "active" or linkage.get((owner.namespace, owner.subject)) != row["target_account"]:
                return None
            if row["recovery_epoch"] != keys.recovery_epoch:
                raise CustodyError("recovery_epoch_mismatch")
            if row["refresh_cipher"] is not None:
                keys.decrypt(bytes(row["refresh_cipher"]), "refresh", credential_binding(row))
            return CredentialMetadata(generation, row["epoch"], row["target_account"], row["scopes"])

    async def cache_valid(self, owner: Owner, expected: CredentialMetadata) -> bool:
        # No access-token value is accepted or retained by this primitive.
        return await self.metadata(owner) == expected

    async def revoke(self, owner: Owner):
        """Local revocation is independent of keys, config readability, and remote endpoints."""
        self._blocked.add((owner, "revoke"))
        async with self.connection() as conn:
            cfg = await (await conn.execute("SELECT * FROM gateway_custody.configurations WHERE set_id=%s FOR UPDATE",
                                           (self.set_id,))).fetchone()
            if not cfg:
                self._blocked.discard((owner, "revoke"))
                return "local_revoked_remote_unconfirmed"
            await conn.execute("UPDATE gateway_custody.credentials SET status='revoked',epoch=epoch+1,refresh_cipher=NULL,"
                "operation_hash=NULL,operation_deadline=NULL,attempt_id=NULL WHERE set_id=%s AND owner_namespace=%s AND owner_sub=%s",
                (self.set_id, owner.namespace, owner.subject))
            await conn.execute("UPDATE gateway_custody.transactions SET status='failed',updated_at=clock_timestamp()"
                " WHERE set_id=%s AND owner_namespace=%s AND owner_sub=%s AND status='pending'",
                (self.set_id, owner.namespace, owner.subject))
            await conn.execute("DELETE FROM gateway_custody.transaction_secrets WHERE challenge_id IN"
                "(SELECT challenge_id FROM gateway_custody.transactions WHERE set_id=%s AND owner_namespace=%s AND owner_sub=%s)",
                (self.set_id, owner.namespace, owner.subject))
        self._blocked.discard((owner, "revoke"))
        return "local_revoked_remote_unconfirmed"

    async def _uncertain(self, owner, generation, epoch, attempt_id, *, challenge_id=None):
        """Attempt-scoped cleanup of an uncertain unpublished operation.

        The compare-and-set matches the full credential binding, generation,
        epoch, the immutable attempt identity, and unpublished status, so it can
        never revoke an active publication or a successor attempt that reused the
        epoch after a rollback. Refresh cleanup touches no transaction; only an
        authorization completion fails its exact associated challenge.
        """
        self._blocked.add((owner, attempt_id))
        try:
            async with self.connection() as conn:
                await conn.execute("SELECT set_id FROM gateway_custody.configurations WHERE set_id=%s FOR UPDATE", (self.set_id,))
                await conn.execute("UPDATE gateway_custody.credentials SET status='revoked',epoch=epoch+1,refresh_cipher=NULL,"
                    "operation_hash=NULL,operation_deadline=NULL,attempt_id=NULL WHERE set_id=%s AND owner_namespace=%s AND owner_sub=%s"
                    " AND config_generation=%s AND epoch=%s AND attempt_id=%s AND status IN ('in_flight','staged')",
                    (self.set_id, owner.namespace, owner.subject, generation, epoch, attempt_id))
                if challenge_id is not None:
                    await conn.execute("UPDATE gateway_custody.transactions SET status='failed',updated_at=clock_timestamp()"
                        " WHERE challenge_id=%s AND set_id=%s AND owner_namespace=%s AND owner_sub=%s"
                        " AND config_generation=%s AND status='pending'",
                        (challenge_id, self.set_id, owner.namespace, owner.subject, generation))
                    await conn.execute("DELETE FROM gateway_custody.transaction_secrets WHERE challenge_id=%s", (challenge_id,))
            self._blocked.discard((owner, attempt_id))
        except CustodyError:
            # The original committed in-flight fence stays unusable if the store is down.
            pass

    async def commit(self, conn, phase: str):
        if self._commit_hook:
            await self._commit_hook(phase, "before")
        await conn.commit()
        if self._commit_hook:
            await self._commit_hook(phase, "after")

    async def begin_refresh(self, owner: Owner) -> RefreshClaim | None:
        epoch = None
        generation = None
        original_deadline = None
        attempt_id = str(uuid4())
        try:
            async with self.guarded() as (conn, config, linkage, keys, generation):
                if config.renewal == "unsupported":
                    raise CustodyError("renewal_unsupported")
                if self._is_blocked(owner):
                    raise CustodyError("reauthorization_required")
                row = await self.binding_row(conn, config, keys, generation, owner)
                now = (await (await conn.execute("SELECT clock_timestamp() AS now")).fetchone())["now"]
                if (row["status"] != "active" or row["refresh_cipher"] is None
                        or row["refresh_expires_at"] is None or row["refresh_expires_at"] <= now):
                    return None
                secret = keys.decrypt(bytes(row["refresh_cipher"]), "refresh", credential_binding(row))
                operation = SecretStr(secrets.token_urlsafe(32))
                epoch = row["epoch"] + 1
                original_deadline = row["refresh_expires_at"]
                # attempt_id is generated before this operation can suspend and is
                # immutable through claim, staging, publication, and cleanup.
                await conn.execute("UPDATE gateway_custody.credentials SET status='in_flight',epoch=%s,refresh_cipher=NULL,"
                    "operation_hash=%s,operation_deadline=clock_timestamp()+interval '60 seconds',attempt_id=%s"
                    " WHERE set_id=%s AND target=%s AND owner_namespace=%s AND owner_sub=%s",
                    (epoch, capability_hash(operation), attempt_id, self.set_id, row["target"], owner.namespace, owner.subject))
                await self.commit(conn, "refresh_claim")
            return RefreshClaim(owner, generation, epoch, attempt_id, operation, secret, original_deadline)
        except BaseException:
            if epoch is not None:
                await asyncio.shield(self._uncertain(owner, generation, epoch, attempt_id))
            raise

    async def stage(self, conn, config, linkage, keys, row, account, scopes, refresh_secret,
                    refresh_expires_at, publication, deadline, attempt_id):
        owner_key = row["owner_namespace"], row["owner_sub"]
        if config.identity_evidence != "configured" or linkage.get(owner_key) != account or not account:
            raise CustodyError("identity_evidence_unavailable")
        if not isinstance(scopes, str) or not scopes or not set(scopes.split(" ")) <= set(config.value("scope").split(" ")):
            raise CustodyError("invalid_granted_scope")
        if refresh_secret is not None:
            now = (await (await conn.execute("SELECT clock_timestamp() AS now")).fetchone())["now"]
            if (not isinstance(refresh_secret, SecretStr) or not isinstance(refresh_expires_at, datetime)
                    or refresh_expires_at.tzinfo is None or refresh_expires_at <= now):
                raise CustodyError("invalid_refresh_lifetime")
        updated = {**row, "target_account": account, "scopes": scopes}
        cipher = keys.encrypt(refresh_secret, "refresh", credential_binding(updated)) if refresh_secret is not None else None
        await conn.execute("UPDATE gateway_custody.credentials SET status='staged',target_account=%s,scopes=%s,"
            "refresh_cipher=%s,key_id=%s,refresh_expires_at=%s,operation_hash=%s,operation_deadline=%s,attempt_id=%s"
            " WHERE set_id=%s AND target=%s AND owner_namespace=%s AND owner_sub=%s",
            (account, scopes, cipher, keys.active_key_id, refresh_expires_at, capability_hash(publication), deadline,
             attempt_id, self.set_id, row["target"], *owner_key))

    async def _publish(self, owner, generation, epoch, publication, *, challenge_id=None):
        """Only the live acknowledged stager holds this nonpersisted publication capability.

        No recovery or retry path publishes a staged row. A committed publication,
        unlike staging, survives a lost final response; uncertainty cleanup must not undo it.
        """
        async with self.guarded() as (conn, config, linkage, keys, current_generation):
            row = await self.binding_row(conn, config, keys, current_generation, owner)
            now = (await (await conn.execute("SELECT clock_timestamp() AS now")).fetchone())["now"]
            if (generation != current_generation or row["epoch"] != epoch or row["status"] != "staged"
                    or row["operation_hash"] != capability_hash(publication) or row["operation_deadline"] <= now
                    or row["recovery_epoch"] != keys.recovery_epoch
                    or linkage.get((owner.namespace, owner.subject)) != row["target_account"]):
                raise CustodyError("publication_fenced")
            if row["refresh_cipher"] is not None:
                if row["refresh_expires_at"] is None or row["refresh_expires_at"] <= now:
                    raise CustodyError("publication_expired")
                binding = credential_binding(row)
                secret = keys.decrypt(bytes(row["refresh_cipher"]), "refresh", binding)
                # A key-policy rotation between stage and publication must not write an old version.
                await conn.execute("UPDATE gateway_custody.credentials SET refresh_cipher=%s,key_id=%s"
                    " WHERE set_id=%s AND target=%s AND owner_namespace=%s AND owner_sub=%s",
                    (keys.encrypt(secret, "refresh", binding), keys.active_key_id, self.set_id,
                     row["target"], owner.namespace, owner.subject))
            if challenge_id is not None:
                transaction = await (await conn.execute("SELECT * FROM gateway_custody.transactions"
                    " WHERE challenge_id=%s AND set_id=%s AND target=%s AND owner_namespace=%s AND owner_sub=%s FOR UPDATE",
                    (challenge_id, self.set_id, row["target"], owner.namespace, owner.subject))).fetchone()
                if (not transaction or transaction["status"] != "pending" or not transaction["consumed"]
                        or transaction["config_generation"] != generation or transaction["credential_epoch"] != epoch - 1
                        or transaction["expires_at"] <= now):
                    raise CustodyError("publication_fenced")
                await conn.execute("UPDATE gateway_custody.transactions SET status='authorized',updated_at=clock_timestamp()"
                                   " WHERE challenge_id=%s", (challenge_id,))
                await conn.execute("DELETE FROM gateway_custody.transaction_secrets WHERE challenge_id=%s", (challenge_id,))
            await conn.execute("UPDATE gateway_custody.credentials SET status='active',operation_hash=NULL,operation_deadline=NULL,attempt_id=NULL"
                " WHERE set_id=%s AND target=%s AND owner_namespace=%s AND owner_sub=%s",
                (self.set_id, row["target"], owner.namespace, owner.subject))
            phase = "authorization_complete" if challenge_id is not None else "refresh_complete"
            await self.commit(conn, phase)
        return CredentialMetadata(generation, epoch, row["target_account"], row["scopes"])

    async def complete_refresh(self, claim: RefreshClaim, refresh_secret: SecretStr, *, refresh_expires_at: datetime):
        try:
            async with self.guarded() as (conn, config, linkage, keys, generation):
                row = await self.binding_row(conn, config, keys, generation, claim.owner)
                now = (await (await conn.execute("SELECT clock_timestamp() AS now")).fetchone())["now"]
                if (self._is_blocked(claim.owner) or generation != claim.generation or row["epoch"] != claim.epoch
                        or row["status"] != "in_flight" or row["attempt_id"] != claim.attempt_id
                        or row["operation_hash"] != capability_hash(claim.operation)
                        or row["operation_deadline"] <= now):
                    return None
                publication = SecretStr(secrets.token_urlsafe(32))
                await self.stage(conn, config, linkage, keys, row, row["target_account"], row["scopes"],
                                 refresh_secret, refresh_expires_at, publication, row["operation_deadline"], claim.attempt_id)
                await self.commit(conn, "refresh_stage")
            return await self._publish(claim.owner, claim.generation, claim.epoch, publication)
        except BaseException:
            await asyncio.shield(self._uncertain(claim.owner, claim.generation, claim.epoch, claim.attempt_id))
            raise

    async def abandon_refresh(self, claim: RefreshClaim):
        await self._uncertain(claim.owner, claim.generation, claim.epoch, claim.attempt_id)

    async def rotate_key(self, expected_key_id: str):
        """Explicit operator operation; changed mounts alone cannot change write policy."""
        keys = self.keyring.snapshot()
        async with self.connection() as conn:
            row = await (await conn.execute("SELECT * FROM gateway_custody.key_policy WHERE singleton FOR UPDATE")).fetchone()
            if (not row or row["active_key_id"] != expected_key_id or row["recovery_epoch"] != keys.recovery_epoch
                    or keys.active_key_id in row["retired_key_ids"] or expected_key_id not in keys.keys
                    or row["fingerprint_key_hash"] != hashlib.sha256(keys.fingerprint_key).hexdigest()):
                raise CustodyError("key_rotation_rejected")
            if keys.active_key_id != expected_key_id:
                await conn.execute("UPDATE gateway_custody.key_policy SET active_key_id=%s,retired_key_ids=array_append(retired_key_ids,%s)"
                                   " WHERE singleton", (keys.active_key_id, expected_key_id))

    async def reencrypt(self, *, limit=100):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise CustodyError("invalid_batch")
        count = 0
        async with self.guarded() as (conn, config, linkage, keys, generation):
            rows = await (await conn.execute("SELECT * FROM gateway_custody.credentials WHERE set_id=%s AND status='active'"
                " AND config_generation=%s AND refresh_cipher IS NOT NULL AND key_id<>%s LIMIT %s FOR UPDATE SKIP LOCKED",
                (self.set_id, generation, keys.active_key_id, limit))).fetchall()
            for row in rows:
                binding = credential_binding(row)
                cipher = keys.encrypt(keys.decrypt(bytes(row["refresh_cipher"]), "refresh", binding), "refresh", binding)
                await conn.execute("UPDATE gateway_custody.credentials SET refresh_cipher=%s,key_id=%s WHERE set_id=%s"
                    " AND target=%s AND owner_namespace=%s AND owner_sub=%s",
                    (cipher, keys.active_key_id, self.set_id, row["target"], row["owner_namespace"], row["owner_sub"]))
                count += 1
            from tool_gateway.services.authorization_transaction_store import transaction_binding
            transactions = await (await conn.execute("SELECT t.*,s.verifier_cipher,s.browser_secret_hash,s.start_attempt"
                " FROM gateway_custody.transactions t"
                " JOIN gateway_custody.transaction_secrets s USING(challenge_id) WHERE t.set_id=%s"
                " AND t.config_generation=%s AND t.status='pending' AND NOT t.consumed AND t.expires_at>clock_timestamp()"
                " AND s.verifier_cipher IS NOT NULL AND s.key_id<>%s LIMIT %s FOR UPDATE OF t,s SKIP LOCKED",
                (self.set_id, generation, keys.active_key_id, limit - count))).fetchall()
            for row in transactions:
                binding = transaction_binding(row)
                cipher = keys.encrypt(keys.decrypt(bytes(row["verifier_cipher"]), "verifier", binding), "verifier", binding)
                await conn.execute("UPDATE gateway_custody.transaction_secrets SET verifier_cipher=%s,key_id=%s WHERE challenge_id=%s",
                                   (cipher, keys.active_key_id, row["challenge_id"]))
                count += 1
        return count

    async def ready(self):
        try:
            await self.initialize()
            return True
        except (CustodyError, ConfigurationError):
            return False

    async def close(self):
        return None
