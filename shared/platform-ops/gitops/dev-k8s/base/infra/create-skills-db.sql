-- Skills database for skills-hub (SPEC-014 R-6).
-- Runs only on fresh clusters via /docker-entrypoint-initdb.d; existing
-- clusters are covered by sync-skills-secrets.sh, which creates the
-- database idempotently through kubectl exec.
CREATE DATABASE skills;
