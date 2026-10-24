"""Migration-only SQL. Runtime roles are granted DML, never schema ownership.

The shipped baseline is schema version 2. ``DDL`` creates a fresh version-2
schema directly; ``UPGRADE_V1_TO_V2`` is an explicit, idempotent migration for a
database that still carries the version-1 prototype schema. Runtime never issues
DDL: ``migrate_custody`` applies these statements and ``initialize`` rejects any
schema whose version is not exactly 2.
"""

# Current schema version created for a fresh database and required at runtime.
SCHEMA_VERSION = 2

DDL = """
SELECT pg_advisory_xact_lock(700016);
CREATE SCHEMA IF NOT EXISTS gateway_custody;
REVOKE ALL ON SCHEMA gateway_custody FROM PUBLIC;
CREATE TABLE IF NOT EXISTS gateway_custody.schema_version (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton), version INTEGER NOT NULL
);
INSERT INTO gateway_custody.schema_version VALUES (TRUE, 2) ON CONFLICT DO NOTHING;
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
    callback_hash TEXT UNIQUE
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
