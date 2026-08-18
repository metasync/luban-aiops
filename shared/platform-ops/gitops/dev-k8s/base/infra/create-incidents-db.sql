-- Incidents database for incident-service (SPEC-015).
-- Runs only on fresh clusters via /docker-entrypoint-initdb.d; existing
-- clusters are covered by sync-incident-secrets.sh, which creates the
-- database idempotently through kubectl exec.
CREATE DATABASE incidents;
