---
kind: design
name: Use a pluggable `Connector` protocol for post-triage collaboration sinks
source: session
category: adr
---

# Use a pluggable `Connector` protocol for post-triage collaboration sinks

_Source: coding plans from commit period 7f98c1e → 5140fe4 — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
After triage, findings need to be dispatched to external systems (audit log, future Slack/Jira). The design should support multiple backends without hard-coding each one.

## Decision drivers
- extensibility for third-party collaboration tools
- single dispatch point after triage
- contract-first so adapters can be added later

## Considered options
- **`Connector` protocol with config-driven registry and built-in `audit` connector** — pros: reusable contract; audit-service integration is immediate; Slack/Jira adapters are pure plugins
- **Hard-code per-integration handlers inside `incident-service`** _(rejected)_ — pros: simpler initially; cons: tight coupling; every new sink requires service changes and redeploy

## Decision
Define a `Connector` protocol (`dispatch(incident, report)`) with a configuration-backed registry; ship a built-in `audit` connector emitting structured events to `audit-service`, and document the contract for future Slack/Jira adapters.

## Consequences
Adding a new collaboration target becomes a small plugin plus config change. R3 ships only the audit connector; Slack/Jira remain future work.