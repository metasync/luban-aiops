-- SPEC-070 delegated-custody table-level least privilege for custody_runtime.
--
-- Applied by sync-custody-db.sh INSIDE the `custody` database AFTER
-- `custody_cli migrate` has created the gateway_custody schema and its tables
-- (a GRANT on a table that does not yet exist fails). Run as custody_operator
-- (the schema owner) or the cluster admin.
--
-- These statements are the committed mirror of the boundary the disposable
-- Postgres integration proof already enforces and tests
-- (products/tool-gateway/tests/integration/delegated_custody.py, run via
-- `make delegated-custody-test`): the runtime role gets exactly the DML the
-- send path needs and is PROVEN denied everything else.

-- Reach the schema, but own none of it.
GRANT USAGE ON SCHEMA gateway_custody TO custody_runtime;

-- Read-only on the version/policy singletons: the runtime must observe the
-- schema version and the active key policy, but never rewrite them.
GRANT SELECT ON gateway_custody.schema_version TO custody_runtime;
GRANT SELECT ON gateway_custody.key_policy TO custody_runtime;

-- Row-lock permission on the key_policy singleton WITHOUT authority to alter
-- any key-policy value: the runtime serializes on the row during rotation but
-- cannot itself change the active key (that is the operator role's action).
GRANT UPDATE (singleton) ON gateway_custody.key_policy TO custody_runtime;

-- Full DML on the four gateway-owned data tables the send path reads and writes.
GRANT SELECT, INSERT, UPDATE, DELETE
  ON gateway_custody.configurations,
     gateway_custody.credentials,
     gateway_custody.transactions,
     gateway_custody.transaction_secrets
  TO custody_runtime;

-- DENIED to custody_runtime (each raises InsufficientPrivilege; the integration
-- proof asserts the refusal). Kept here as the authoritative negative contract:
--   CREATE TABLE gateway_custody.forbidden(...)          -- no DDL in the schema
--   SELECT * FROM public.unrelated_private               -- no cross-app access
--   UPDATE gateway_custody.key_policy SET active_key_id  -- no key-policy values
--   DELETE FROM gateway_custody.key_policy               -- no key-policy delete
--   UPDATE gateway_custody.schema_version SET version    -- no version rewrite
-- No GRANT below this line: anything not explicitly granted is denied.
