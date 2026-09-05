---
kind: design
name: Require requirement-to-test traceability and exercised demos before marking specs delivered
source: session
category: adr
---

# Require requirement-to-test traceability and exercised demos before marking specs delivered

_Source: coding plans from commit period c66ad9a → 7eee39a — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
SPEC-049 R-4 shipped as 'delivered' despite being unimplemented because there was no enforcement that acceptance criteria map to automated tests or that shipped samples are exercised by their demo scripts. The plan explicitly identifies this as the process gap that allowed R-4 to slip through review.

## Decision drivers
- prevent specs from flipping to 'delivered' without demonstrable proof
- tie spec status to verifiable test coverage and demo execution
- avoid numeric coverage bars in favor of criterion-level mapping

## Considered options
- **Review-discipline only (rely on human reviewers to catch gaps)** _(rejected)_ — pros: no process overhead; cons: exactly how R-4 slipped; unreliable at scale
- **Numeric code-coverage bar enforced in CI** _(rejected)_ — pros: automatable metric; cons: CONTRIBUTING deliberately has none; coverage ≠ correctness
- **Mandatory mapping: every R-x → ≥1 automated test asserting it, plus shipped samples exercised under `make verify`** — pros: enforces 'declared delivered = demonstrably delivered'; catches missing implementation like R-4 before flip; cons: adds authoring overhead; requires updating CONTRIBUTING.md and spec README Enforcement section

## Decision
Adopt ADR-0008: a spec flips to `delivered` only when (a) every R-x acceptance criterion maps to at least one automated test asserting it, and (b) any `samples/` demo the spec ships is exercised by its own demo script under `make verify` (or a documented, gated reason it cannot be). Realize this as a `CONTRIBUTING.md` delivery-gate addition plus a line in the spec `README.md` Enforcement section.

## Consequences
Future specs must include tests covering every acceptance criterion and runnable demo scripts; the design-review checklist gains a traceability question. This process change is orthogonal to the code but prevents the same class of defect (unimplemented requirements marked delivered) from recurring.