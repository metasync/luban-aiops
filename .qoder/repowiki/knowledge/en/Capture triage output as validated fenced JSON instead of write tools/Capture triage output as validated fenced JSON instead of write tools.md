---
kind: design
name: Capture triage output as validated fenced JSON instead of write tools
source: session
category: adr
---

# Capture triage output as validated fenced JSON instead of write tools

_Source: coding plans from commit period 7f98c1e → 5140fe4 — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
Triage must not let the agent execute changes during R3; the SPEC-007 invariant requires tool-gateway to stay strictly read-only. The agent still needs to produce structured findings (summary, severity assessment, evidence refs, hypotheses, ranked next steps).

## Decision drivers
- preserve read-only tool-gateway invariant
- structured, machine-parseable triage output
- resilience when LLM output is malformed

## Considered options
- **Fenced `triage-report` JSON block parsed by Pydantic** — pros: enforces schema, preserves raw text on failure as `triage_failed`, no write surface exposed
- **Allow a write tool to persist triage results directly** _(rejected)_ — pros: simpler for the agent; cons: violates SPEC-007 read-only invariant; introduces write risk in R3

## Decision
Instruct the agent to emit a fenced `triage-report` JSON block; `incident-service` validates it with Pydantic and records parse failures as `triage_failed` while preserving the raw text.

## Consequences
Triage remains advisory — execution stays out of scope until R4. Malformed LLM output degrades gracefully rather than crashing the pipeline.