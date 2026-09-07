---
kind: design
name: Require requirement-to-test and shipped-sample traceability before marking specs delivered
source: session
category: adr
---

# Require requirement-to-test and shipped-sample traceability before marking specs delivered

_Source: coding plans from commit period 123c4b6 → e252f12 — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
SPEC-049 R-4 shipped as `delivered` despite being unimplemented — review-discipline alone did not catch it. There was no enforcement that acceptance criteria map to automated tests or that shipped samples are exercised in CI.

## Decision drivers
- prevent unimplemented requirements from reaching `delivered`
- tie 'declared delivered' to 'demonstrably delivered'
- avoid arbitrary numeric coverage bars (per CONTRIBUTING policy)

## Considered options
- **Review-discipline only** _(rejected)_ — pros: no process friction; cons: exactly how R-4 slipped through
- **Numeric test-coverage bar** _(rejected)_ — pros: measurable; cons: CONTRIBUTING deliberately has none; invites gaming
- **Mandatory mapping: each R-x → ≥1 automated test + shipped samples exercised in `make verify`** — pros: enforces traceability at delivery time; catches regressions like R-4; cons: adds authoring overhead; requires gating scripts

## Decision
Adopt a delivery gate: a spec may flip to `delivered` only when (a) every R-x acceptance criterion maps to at least one automated test asserting it, and (b) any `samples/` demo the spec ships is exercised by its own demo script under `make verify` (or a documented, gated reason it cannot be). Realized as a `CONTRIBUTING.md` addition plus a line in the spec `README.md` Enforcement section.

## Consequences
Future specs must ship with executable verification; the SPEC-051 release demonstrates the pattern (R-1/R-2/R-3 covered by dedicated unit tests, password-reset demo asserts exactly one card). Adds upfront authoring cost but blocks the class of defect that allowed R-4 to ship untested.