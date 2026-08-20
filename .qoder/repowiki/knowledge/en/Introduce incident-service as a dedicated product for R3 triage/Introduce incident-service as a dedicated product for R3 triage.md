---
kind: design
name: Introduce incident-service as a dedicated product for R3 triage
source: session
category: adr
---

# Introduce incident-service as a dedicated product for R3 triage

_Source: coding plans from commit period 7c01b8c → 7f98c1e — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
The platform needed to evolve from a query assistant into an incident-support tool (SPEC-015, Flow 3). A new service was required to own incident intake, triage orchestration, and collaboration without entangling the existing agent-platform or skills-hub.

## Decision drivers
- separation of concerns per product boundary
- reusability of the existing audit-service/skills-hub chassis pattern
- clear ownership of incident lifecycle state

## Considered options
- **New standalone `incident-service` product** — pros: isolates incident domain, reuses proven FastAPI/uv/Dockerfile skeleton, fits gitops overlays cleanly
- **Extend agent-platform with incident features** _(rejected)_ — pros: fewer services; cons: blurs product boundaries, mixes chat runtime with incident workflow state

## Decision
Ship a new `products/incident-service/` product mirroring the audit-service/skills-hub chassis (frozen-dataclass settings with `INCIDENT_*` prefix, structured JSON logging, FastAPI exception middleware, uv lockfile, shared base-uv Dockerfile) owning canonical `incident`, `triage_report`, and `connector_dispatch` models backed by a dual in-memory + Postgres store on a dedicated `incidents` database.

## Consequences
Adds one more deployable surface and a new DB to provision via `sync-incident-secrets.sh` / `docker-entrypoint-initdb.d`, but keeps each product self-contained and testable. Future integrations (Slack/Jira) plug in via the documented `Connector` protocol without touching core code.