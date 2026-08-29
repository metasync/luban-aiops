---
kind: design
name: Capture triage output as validated fenced JSON rather than via write tools
source: session
category: adr
---

# Capture triage output as validated fenced JSON rather than via write tools

_Source: coding plans from commit period 7c01b8c → 7f98c1e — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
R3 must preserve SPEC-007: tool-gateway stays strictly read-only. The agent still needs to produce actionable triage reports that the system can persist and display.

## Decision drivers
- enforce read-only invariant on tool-gateway
- structured, machine-parseable output
- no kernel changes to agent-runtime

## Considered options
- **Fenced JSON `triage-report` block parsed by Pydantic** — pros: keeps tool-gateway read-only, yields strongly-typed report fields, parse failure falls back to `triage_failed` with raw text preserved
- **Write tool on tool-gateway to emit reports** _(rejected)_ — pros: simpler ingestion path; cons: violates SPEC-007 read-only invariant, opens write surface to agents

## Decision
Instruct the agent via a prompt template to emit a fenced `triage-report` JSON block; the incident-service validates it with Pydantic and stores it, marking the incident `triage_failed` when parsing fails while preserving raw text.

## Consequences
Agents gain a stable contract for producing triage data without any new write capabilities. Prompt discipline becomes part of the spec; malformed outputs are recoverable but degrade UX until the model stabilizes.