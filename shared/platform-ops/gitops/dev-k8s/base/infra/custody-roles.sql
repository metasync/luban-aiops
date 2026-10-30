-- SPEC-070 delegated-custody roles and database-level privileges.
--
-- Applied by sync-custody-db.sh (NOT by /docker-entrypoint-initdb.d, and NOT
-- part of the postgres-initdb ConfigMap): the roles must exist before the
-- operator migration runs, and the table-level grants in custody-grants.sql
-- must run AFTER it creates the tables.
--
-- Two SEPARATE roles enforce least privilege (plan line 166):
--   custody_operator -- migration / rotation / recovery administration. Owns the
--                       gateway_custody schema, may run DDL, and may alter
--                       key_policy values. Used by `custody_cli migrate`,
--                       `rotate-key`, `recover`, and `reencrypt`.
--   custody_runtime  -- the gateway send-path role. Connects only; every table
--                       privilege is granted explicitly in custody-grants.sql.
--                       Never DDL, never key_policy value authority, never
--                       cross-application access.
--
-- NO password appears here. sync-custody-db.sh generates role passwords at
-- deploy time and sets them from the environment (never committed, never in
-- argv), and only on first creation so a re-run never rotates a live password
-- out from under the mounted runtime DSN.
--
-- Idempotent: an existing role is left untouched; the database grants are
-- re-assertable. Run against any database in the cluster (roles are
-- cluster-level; the database grants name `custody` explicitly).

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'custody_operator') THEN
    CREATE ROLE custody_operator LOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'custody_runtime') THEN
    CREATE ROLE custody_runtime LOGIN;
  END IF;
END
$$;

-- The operator role creates the gateway_custody schema and its tables via
-- `custody_cli migrate`, so it needs CREATE on the database. The runtime role
-- only connects; it holds no database-level CREATE and no DDL authority.
GRANT CONNECT ON DATABASE custody TO custody_operator;
GRANT CREATE ON DATABASE custody TO custody_operator;
GRANT CONNECT ON DATABASE custody TO custody_runtime;
