---
kind: design
name: Use a pluggable Connector protocol with audit-service as the built-in sink
source: session
category: adr
---

# Use a pluggable Connector protocol with audit-service as the built-in sink

_Source: coding plans from commit period 7c01b8c → 7f98c1e — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
Post-triage events need to be forwarded to downstream systems (audit log, future Slack/Jira). Hard-coding one target would make later adapters invasive.

## Decision drivers
- extensibility for multiple downstream sinks
- single source of truth for dispatch config
- contract-first design before implementing all adapters

## Considered options
- **Config-driven `Connector` registry with `dispatch(incident, report)` protocol** — pros: new adapters implement one method; built-in `audit` connector emits structured events to audit-service; Slack/Jira deferred to future work
- **Direct calls from incident-service to each downstream** _(rejected)_ — pros: simpler initially; cons: tight coupling, harder to add/remove sinks, no shared dispatch semantics

## Decision
Define a `Connector` protocol and a config-driven registry; ship only the `audit` connector that posts structured triage events to audit-service, documenting the contract so Slack/Jira adapters can be added later without changing incident-service internals.

## Consequences
Dispatch failures are isolated per connector and recorded in `connector_dispatch`. Adding a new sink is a one-method implementation plus config entry, at the cost of an extra indirection layer around every triage event.