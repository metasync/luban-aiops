---
kind: design
name: Adopt a spec-delivery traceability gate requiring test/sample coverage before flipping specs delivered
source: session
category: adr
---

# Adopt a spec-delivery traceability gate requiring test/sample coverage before flipping specs delivered

_Source: coding plans from commit period e252f12 → 6359eeb — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
R-4 shipped without implementation because there was no enforcement that acceptance criteria mapped to automated tests or that shipped samples were exercised under `make verify`. Review discipline alone allowed the gap to pass.

## Decision drivers
- prevent unimplemented specs from shipping
- tie 'delivered' status to demonstrable delivery
- avoid arbitrary numeric coverage thresholds

## Considered options
- **Review-discipline only** _(rejected)_ — pros: no process overhead; cons: exactly how R-4 slipped through
- **Numeric test-coverage bar** _(rejected)_ — pros: measurable; cons: CONTRIBUTING deliberately has none; brittle threshold
- **Criterion-to-test + shipped-sample-exercise gate** — pros: each R-x maps to ≥1 automated test; any shipped `samples/` demo runs under `make verify`; 'declared delivered' equals 'demonstrably delivered'; cons: adds documentation and checklist burden; requires gating reason if a sample cannot be exercised

## Decision
Add an ADR-0008 delivery-gate rule to CONTRIBUTING.md and the spec README Enforcement section: a spec flips to `delivered` only when every R-x acceptance criterion maps to at least one automated test asserting it, and any shipped sample is exercised by its own demo script under `make verify` (or has a documented, gated reason it cannot be).

## Consequences
Future specs must include tests and runnable demos before being marked delivered. Realized as a CONTRIBUTING.md addition plus a line in the spec README Enforcement section. This is a process decision rather than a code-level architectural change.