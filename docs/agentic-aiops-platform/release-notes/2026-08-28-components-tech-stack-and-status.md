# v0.23.4 — Components Table Tech-Stack Versions and Status Vocabulary

Date: 2026-08-28
Release type: patch (follow-up polish on the v0.23.3 Settings component
table — informational backend fields and presentational portal changes;
no new actions, event types, or approval-path change)

## Summary

Operator feedback on the v0.23.3 **Key platform components** table:

1. All components follow the platform version, so listing each
   component's own version is redundant — the interesting question is
   what tech stack sits underneath each component, and how new those
   stacks are.
2. The status column mixed words (*ok* / *loaded* / *ready*), and it
   was worth asking whether the column earns its place at all.

## What Changed

### Table shape: Component / Technology / Version (operator-portal web-ui)

- The table now names the tech stack underneath each component:
  operator portal → React · Ant Design, platform gateway → FastAPI ·
  Python, agent service → AgentScope · FastAPI, agent runtime → the LLM
  provider API with the active model, session / agent-state stores →
  their backend (PostgreSQL / Redis / In-memory) with the live server
  version, and policy bundle → JSON policy rules with the rule count.
- The platform version stays where it always was — the Descriptions
  block above the table — and the table caption says so explicitly.
- React and Ant Design versions are locked from the portal's
  `package-lock.json` at build time (with a package.json fallback), so
  the row reflects what actually shipped in the bundle.

### Backend version plumbing (agent-platform + platform-gateway)

- Agent-service `/api/v2/health` gains five optional fields:
  `python_version`, `fastapi_version`, `agentscope_version`,
  `session_store_version`, `agent_state_version`. Store backends gain
  an informational `server_version()` (`current_setting('server_version')`
  for PostgreSQL, `INFO server` for Redis, `None` for in-memory).
- The gateway's `/health/ready` gains `python_version` /
  `fastapi_version` in all three branches (ok and both degraded paths).
- Every lookup is best-effort: a failure yields `null` for that entry
  and never disturbs the readiness contract.

### Status: kept, unified (operator-portal web-ui)

- One vocabulary across every row: **ready** (green), **degraded**
  (orange), **not ready** (red), plus *unavailable* when a probe fails
  and *checking…* while probes are in flight. The prior *ok* / *loaded*
  mix is gone.
- The column is deliberately kept: the portal is a static bundle, so
  this page loads even when the gateway is down, a store is unhealthy,
  or the LLM provider is misconfigured — exactly the states the table
  should surface before they show up as failed chat turns or lost
  sessions.

### Tests

- SettingsView: the component-table test asserts the new columns —
  AgentScope · FastAPI versions, FastAPI · Python per service, provider
  and model, PostgreSQL backends with their server version, policy rule
  count, and the unified ready tags; the degradation test asserts
  *unavailable* rows when probes fail.
- Targeted backend suites for the health route and store backends, and
  the gateway readiness branches, are green.

## Posture

Informational and presentational. No new policy actions, audit event
types, or approval semantics; health endpoints keep their
unauthenticated, readiness-first contract and the new fields can only
be `null`, never a failure mode.
