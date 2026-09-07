---
kind: design
name: Adopt a spec-delivery traceability gate requiring test coverage and exercised demos
source: session
category: adr
---

# Adopt a spec-delivery traceability gate requiring test coverage and exercised demos

_Source: coding plans from commit period 33e6a7f → 123c4b6 — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
SPEC-049 R-4 shipped without automated tests asserting the acceptance criterion, slipping through review-discipline alone. There was no numeric coverage bar in CONTRIBUTING.md.

## Decision drivers
- prevent unimplemented requirements from being marked delivered
- tie 'delivered' to demonstrable behavior in `make verify`
- avoid introducing a numeric coverage threshold

## Considered options
- **Review-discipline only** _(rejected)_ — pros: no process change; cons: exactly how R-4 slipped; insufficient
- **Numeric coverage bar** _(rejected)_ — pros: measurable; cons: CONTRIBUTING deliberately has none; easy to game
- **Requirement→test mapping + shipped-sample exercise rule** — pros: each R-x maps to ≥1 automated test; any shipped sample is exercised under `make verify`; enforceable at merge time; cons: adds authoring overhead; some specs may need documented gated reasons if they cannot be exercised

## Decision
Add a delivery-gate rule to CONTRIBUTING.md and the spec README Enforcement section: a spec flips to `delivered` only when every acceptance criterion maps to at least one automated test and any shipped sample is exercised by its own demo script under `make verify` (or a documented, gated reason is provided). Realize it via a Design Review Checklist item and updated Testing section.

## Consequences
Future specs must ship with tests covering their acceptance criteria and runnable demos, closing the gap that allowed R-4 to ship untested. Adds upfront authoring cost but reduces post-release regressions.