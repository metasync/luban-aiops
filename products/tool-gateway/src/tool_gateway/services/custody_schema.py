"""Migration-only SQL. Runtime roles are granted DML, never schema ownership.

The shipped baseline is schema version 3. ``DDL`` creates a fresh version-3
schema directly; ``UPGRADE_V1_TO_V2`` and ``UPGRADE_V2_TO_V3`` are explicit,
idempotent migrations for a database that still carries an older schema. Runtime
never issues DDL: ``migrate_custody`` applies these statements and ``initialize``
rejects any schema whose version is not exactly 3.

Version 3 (SPEC-070 browser handoff) adds the per-challenge browser-binding
fields to ``transaction_secrets`` and extends the authenticated verifier binding
to cover them, so a version-2 verifier ciphertext can no longer decrypt. The
v2->v3 upgrade therefore fences every pending prototype transaction (it carries
no browser binding and its verifier was bound under the v2 AAD) instead of
decrypting under a guessed binding; published grants are never touched.
"""

# Current schema version created for a fresh database and required at runtime.
SCHEMA_VERSION = 3

DDL = """
SELECT pg_advisory_xact_lock(700016);
CREATE SCHEMA IF NOT EXISTS gateway_custody;
REVOKE ALL ON SCHEMA gateway_custody FROM PUBLIC;
CREATE TABLE IF NOT EXISTS gateway_custody.schema_version (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton), version INTEGER NOT NULL
);
INSERT INTO gateway_custody.schema_version VALUES (TRUE, 3) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS gateway_custody.key_policy (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    recovery_epoch TEXT NOT NULL, active_key_id TEXT NOT NULL,
    retired_key_ids TEXT[] NOT NULL DEFAULT '{}', fingerprint_key_hash TEXT NOT NULL,
    retired_recovery_epochs TEXT[] NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS gateway_custody.configurations (
    set_id TEXT PRIMARY KEY, target TEXT NOT NULL, revision BIGINT NOT NULL CHECK (revision > 0),
    fingerprint TEXT NOT NULL, generation TEXT NOT NULL, active BOOLEAN NOT NULL
);
CREATE TABLE IF NOT EXISTS gateway_custody.credentials (
    set_id TEXT NOT NULL REFERENCES gateway_custody.configurations(set_id), target TEXT NOT NULL,
    owner_namespace TEXT NOT NULL, owner_sub TEXT NOT NULL, config_generation TEXT NOT NULL,
    epoch BIGINT NOT NULL CHECK (epoch >= 0),
    status TEXT NOT NULL CHECK (status IN ('absent','active','in_flight','staged','revoked')),
    target_account TEXT NOT NULL DEFAULT '', scopes TEXT NOT NULL DEFAULT '',
    recovery_epoch TEXT NOT NULL, refresh_cipher BYTEA, key_id TEXT, refresh_expires_at TIMESTAMPTZ,
    operation_hash TEXT, operation_deadline TIMESTAMPTZ, attempt_id TEXT,
    PRIMARY KEY (set_id, target, owner_namespace, owner_sub),
    CHECK (status IN ('active','staged') OR refresh_cipher IS NULL),
    CHECK (status NOT IN ('in_flight','staged') OR (operation_hash IS NOT NULL AND operation_deadline IS NOT NULL)),
    CHECK (status <> 'active' OR (operation_hash IS NULL AND operation_deadline IS NULL)),
    CONSTRAINT credentials_attempt_fenced
        CHECK (status NOT IN ('in_flight','staged') OR attempt_id IS NOT NULL),
    CONSTRAINT credentials_attempt_cleared
        CHECK (status IN ('in_flight','staged') OR attempt_id IS NULL)
);
CREATE TABLE IF NOT EXISTS gateway_custody.transactions (
    challenge_id TEXT PRIMARY KEY, set_id TEXT NOT NULL, target TEXT NOT NULL,
    owner_namespace TEXT NOT NULL, owner_sub TEXT NOT NULL,
    config_generation TEXT NOT NULL, credential_epoch BIGINT NOT NULL,
    session_id TEXT NOT NULL, call_id TEXT NOT NULL, return_url TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending','authorized','canceled','expired','failed')),
    consumed BOOLEAN NOT NULL DEFAULT FALSE, created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL, expires_at TIMESTAMPTZ NOT NULL,
    CHECK (expires_at > created_at),
    FOREIGN KEY (set_id, target, owner_namespace, owner_sub)
        REFERENCES gateway_custody.credentials(set_id, target, owner_namespace, owner_sub)
);
CREATE INDEX IF NOT EXISTS custody_transaction_expiry ON gateway_custody.transactions(expires_at);
CREATE TABLE IF NOT EXISTS gateway_custody.transaction_secrets (
    challenge_id TEXT PRIMARY KEY REFERENCES gateway_custody.transactions(challenge_id) ON DELETE CASCADE,
    start_hash TEXT UNIQUE, start_expires_at TIMESTAMPTZ, start_consumed BOOLEAN NOT NULL DEFAULT FALSE,
    state_hash TEXT UNIQUE, verifier_cipher BYTEA, key_id TEXT,
    callback_hash TEXT UNIQUE,
    browser_secret_hash TEXT, browser_expires_at TIMESTAMPTZ,
    start_attempt INTEGER NOT NULL DEFAULT 0
);
REVOKE ALL ON ALL TABLES IN SCHEMA gateway_custody FROM PUBLIC;
"""

# Explicit, idempotent upgrade for a database still on the version-1 prototype
# schema. It never rewrites published active rows; it only fences legacy
# unpublished credential operations that lack attempt identity and then raises
# the recorded version. Safe to run repeatedly.
UPGRADE_V1_TO_V2 = """
SELECT pg_advisory_xact_lock(700016);
ALTER TABLE gateway_custody.credentials ADD COLUMN IF NOT EXISTS attempt_id TEXT;
-- Fence legacy in-flight/staged operations: they carry no attempt identity and
-- can no longer be safely published or cleaned, so they are revoked. Published
-- active rows are left untouched.
UPDATE gateway_custody.credentials
   SET status='revoked', epoch=epoch+1, refresh_cipher=NULL,
       operation_hash=NULL, operation_deadline=NULL, attempt_id=NULL
 WHERE status IN ('in_flight','staged');
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='credentials_attempt_fenced'
                   AND conrelid='gateway_custody.credentials'::regclass) THEN
        ALTER TABLE gateway_custody.credentials ADD CONSTRAINT credentials_attempt_fenced
            CHECK (status NOT IN ('in_flight','staged') OR attempt_id IS NOT NULL);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='credentials_attempt_cleared'
                   AND conrelid='gateway_custody.credentials'::regclass) THEN
        ALTER TABLE gateway_custody.credentials ADD CONSTRAINT credentials_attempt_cleared
            CHECK (status IN ('in_flight','staged') OR attempt_id IS NULL);
    END IF;
END $$;
UPDATE gateway_custody.schema_version SET version=2 WHERE singleton AND version < 2;
"""

# Explicit, idempotent upgrade from version 2 to version 3 (SPEC-070 browser
# handoff). It adds the per-challenge browser-binding fields and then fences every
# pending prototype transaction: a version-2 transaction carries no browser
# binding and its encrypted verifier was authenticated under the version-2
# binding, so it can neither satisfy the version-3 browser proof nor decrypt under
# the extended binding. Fencing (fail + burn the secret state) is the safe choice;
# decrypting under a guessed binding is forbidden. Published grants and terminal
# transactions are never touched, and the statement is safe to run repeatedly.
UPGRADE_V2_TO_V3 = """
SELECT pg_advisory_xact_lock(700016);
ALTER TABLE gateway_custody.transaction_secrets ADD COLUMN IF NOT EXISTS browser_secret_hash TEXT;
ALTER TABLE gateway_custody.transaction_secrets ADD COLUMN IF NOT EXISTS browser_expires_at TIMESTAMPTZ;
ALTER TABLE gateway_custody.transaction_secrets ADD COLUMN IF NOT EXISTS start_attempt INTEGER NOT NULL DEFAULT 0;
WITH fenced AS (
    UPDATE gateway_custody.transactions SET status='failed', updated_at=clock_timestamp()
     WHERE status='pending' RETURNING challenge_id
)
DELETE FROM gateway_custody.transaction_secrets
 WHERE challenge_id IN (SELECT challenge_id FROM fenced);
UPDATE gateway_custody.schema_version SET version=3 WHERE singleton AND version < 3;
"""
