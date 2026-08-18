-- Sessions database for the agent-platform session store (SPEC-016).
-- Runs only on fresh clusters via /docker-entrypoint-initdb.d; existing
-- clusters are covered by sync-sessions-db.sh, which creates the database
-- idempotently through kubectl exec.
CREATE DATABASE sessions;
