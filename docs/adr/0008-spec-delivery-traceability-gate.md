# ADR-0008: Spec Delivery Requires Requirement-To-Test Traceability And Exercised Samples

## Status

`accepted`

- date: 2026-09-04
- deciders: workspace maintainers
- related specs: SPEC-051 (first spec delivered under this gate), SPEC-049
  (whose R-4 shipped unimplemented — the motivating gap)

## Context

The SDD workflow (`docs/specs/README.md`) flips a spec to `delivered` when
"all acceptance criteria [are] met and validated," and enforcement is "by
review discipline: reviewers check acceptance criteria before marking a
spec `delivered`."

SPEC-049 was marked `delivered` (v0.31.0) with R-4's flow-unlock acceptance
criterion — "A `write`-class flow parks exactly one confirmation card;
after approval, the declared steps execute without further cards" — never
implemented in the kernel and never asserted by a test. The gap surfaced
only during a live operator test on v0.32.0 (see ADR-0007).

The same class of gap applies to shipped samples: `samples/` demos are
documentation-by-execution, but nothing required a delivered spec's demo to
be run by its own script under the verification gate, so a sample could
drift from its skill/pages/design without failing anything — exactly what
happened to the password-reset sample.

Review discipline alone caught neither gap, because acceptance criteria were
read as prose rather than mapped to executable assertions.

## Decision

A spec may advance to `delivered` only when both hold:

1. Every `R-x` acceptance criterion maps to at least one automated test
   that asserts it, and the spec's `tasks.md` records that mapping
   (criterion → test). "Declared delivered" must equal "demonstrably
   delivered."
2. Any `samples/` demo the spec ships is exercised by its own demo script
   as part of the verification path (`make verify` or a documented,
   reviewer-approved live-check step recorded in the spec).

This is a delivery gate, not a coverage bar: it requires traceability from
each acceptance criterion to a test, not a numeric coverage threshold
(`CONTRIBUTING.md` deliberately sets none).

## Alternatives Considered

- rely on review discipline alone (status quo) — rejected: this is exactly
  how SPEC-049 R-4 shipped unimplemented; prose criteria without mapped
  tests are not verifiable at delivery time.
- impose a numeric coverage bar — rejected: `CONTRIBUTING.md` explicitly has
  none, and a coverage percentage does not ensure the *right* branches (each
  acceptance criterion) are asserted.
- enforce only in CI, not in the workflow doc — rejected: the gate must be
  visible to authors at spec time, not discovered at merge time; it belongs
  in `CONTRIBUTING.md` and the spec `README.md` enforcement section.

## Consequences

- acceptance criteria become executable at delivery; a requirement that is
  written but not built fails the gate instead of shipping silently; shipped
  samples stay honest because their demo scripts run in the verification
  path.
- realized as a `CONTRIBUTING.md` delivery-gate addition (Testing + Design
  Review Checklist) and a line in the `docs/specs/README.md` Enforcement
  section. SPEC-051 is the first spec to carry the criterion → test mapping
  in its `tasks.md`.
- trade-off: slightly more upfront work per spec (mapping criteria to tests,
  wiring sample demos into the verification path); accepted as the cost of
  not repeating the R-4 gap.
- does not retroactively re-open delivered specs; it governs deliveries from
  SPEC-051 forward. A follow-up sweep of the recently delivered browser
  specs (SPEC-049/050) against this gate is advisable but out of scope here.
