# v0.27.1 — Post-Release Review Remediation

Date: 2026-08-30
Release type: patch (same-day follow-up to the v0.27.0 code & doc
review; one bundle-purity fix in the incident skill-draft assembler —
no routes, policy actions, audit events, or response shapes change)

## Summary

The post-release code & doc review of v0.27.0 (SPEC-045 incident-
anchored skill drafts and draft preview) returned one High finding:
the incident bundle assembler stripped `triage_raw` from the incident
envelope but not the triage `session_id`. This patch closes the gap
and hardens the test that should have pinned it.

## The finding

`build_incident_skill_draft_bundle` strips `triage_raw` from the
envelope comprehension and `session_id` from the validated triage
report — but not `session_id` from the envelope itself. incident-
service always populates the envelope's `session_id` during triage,
and on success it is the session actually used — which can be the
operator-suffixed `incident-{id}--{operator-slug}` form that names
the triage operator. Since drafting only succeeds on incidents with a
validated report (i.e., triaged incidents), every successful incident
draft carried that session id into the generation prompt, where it
could surface in the downloaded `.md`.

That contradicts the feature's central invariant — "never anyone's
session" — which the code implemented for the report and the
provenance block but missed on the envelope. The gap was masked by
the purity test: its fixture envelope omitted `session_id`, so the
existing assertions passed vacuously.

Blast radius is bounded — the leaked value is an agent session
identifier inside a draft handed to roles that already hold
`incident:read` — but the invariant is load-bearing in the spec, the
authorization matrix, and the release notes, so the code is corrected
to match the contract rather than the other way around.

## The fix

- `skill_draft.py`: the envelope comprehension now excludes
  `session_id` alongside `triage_raw`; the module and function
  docstrings name both strips.
- `test_skill_draft.py`: the incident-service fixture envelope now
  carries `session_id`, and `test_bundle_purity` asserts
  `"session_id" not in envelope` beside the existing report
  assertion — the fixture can no longer mask the strip.

## Documentation corrections

- The v0.27.0 release note's assembler sentence now names both
  envelope strips.
- SPEC-045's spec trio records the same: spec.md (generation input,
  Q-3, the digest-only invariant, and a changelog entry for this
  patch), plan.md, and tasks.md.

## What does not change

- No route, policy action, audit event type, or response shape moves.
- The session-scoped drafting surface (SPEC-044) is untouched — zero
  backend movement, as specified.
- Version lockstep only: every product and the portal report 0.27.1.

## Verification

- agent-platform: full suite green (735 tests), including the
  hardened purity test with the session-id fixture.
- House train: `make verify` green before and after `make build`,
  `make deploy`, and a live spot-check confirming a generated
  incident draft carries no session identifier.
