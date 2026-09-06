---
kind: design
name: Require spec acceptance criteria to map to automated tests before delivery
source: session
category: adr
---

# Require spec acceptance criteria to map to automated tests before delivery

_Source: coding plans from commit period 545a4fc → 33e6a7f — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
SPEC-049 R-4 shipped as delivered despite never being implemented in the kernel, because there was no enforcement that acceptance criteria were covered by tests or that shipped samples were exercised under make verify.

## Decision drivers
- prevent unimplemented specs from shipping
- tie declared delivered to demonstrable delivery
- low-cost process guard over review-only discipline

## Considered options
- **Review-discipline only** _(rejected)_ — pros: no process overhead; cons: exactly how R-4 slipped through; relies on human vigilance
- **Numeric coverage bar** _(rejected)_ — pros: measurable; cons: CONTRIBUTING deliberately avoids hard coverage thresholds; brittle against refactors
- **Delivery gate: each R-x maps to at least one automated test and shipped samples run in verify** — pros: enforces traceability at merge time; catches gaps like R-4 before release; cons: requires updating CONTRIBUTING and design-review checklist

## Decision
Add a delivery-gate rule to CONTRIBUTING.md: a spec flips to delivered only when every R-x acceptance criterion maps to at least one automated test asserting it, and any samples/ demo shipped with the spec is exercised by its own demo script under make verify (or has a documented, gated reason it cannot be). Add the same question to the Design Review Checklist.

## Consequences
Future specs must include executable verification of their acceptance criteria before they can be marked delivered. This raises upfront test authoring effort but prevents regression-style slips where specs ship without implementation.