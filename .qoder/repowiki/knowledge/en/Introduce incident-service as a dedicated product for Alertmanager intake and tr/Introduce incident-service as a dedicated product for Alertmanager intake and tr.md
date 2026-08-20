---
kind: design
name: Introduce incident-service as a dedicated product for Alertmanager intake and triage
source: session
category: adr
---

# Introduce incident-service as a dedicated product for Alertmanager intake and triage

_Source: coding plans from commit period 7f98c1e → 5140fe4 — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
The platform needed to evolve from a query assistant into an incident-support tool (R3). Incoming alerts from Alertmanager and manual reports had to be normalized into a single canonical model, persisted durably, and surfaced through the portal and chat tools.

## Decision drivers
- single canonical incident model across sources
- durable persistence with Postgres
- read-only guardrail for tool-gateway
- pluggable collaboration sinks

## Considered options
- **New `incident-service` product mirroring audit-service/skills-hub chassis** — pros: consistent settings (`INCIDENT_*`), logging, Dockerfile, Makefile; isolates incident domain; reuses existing patterns
- **Extend existing services (e.g. agent-platform or skills-hub) with incident logic** _(rejected)_ — pros: less new code; cons: blurs service boundaries; harder to scope R3 read-only invariant; duplicates auth/policy wiring already in place via platform-gateway

## Decision
Ship a standalone `products/incident-service/` FastAPI product that normalizes Alertmanager webhooks and manual portal submissions into a canonical `incident` model, persists them on a dedicated `incidents` Postgres database, and exposes query endpoints plus a triage orchestration flow.

## Consequences
Adds a new deployable service, secrets, and GitOps overlay but keeps the rest of the platform unchanged. Future integrations (Slack/Jira) plug in via the documented `Connector` protocol without touching core flows.