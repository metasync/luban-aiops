# Post-Review Remediation: Audit View Hook Order and Doc Alignment (v0.29.2)

Date: 2026-09-01

Remediation batch from the post-v0.29.1 code & doc review of the
SPEC-047 delivery (v0.29.0) and its hardening patch (v0.29.1). One
component touched — `AuditView.tsx` — plus one regression test and
three doc annotations; no API, contract, route, or policy changes.

## What the review found

- **Code (Critical)**: the SPEC-047 drill-down `useCallback` landed
  after the `!allowed` early return in `AuditView`, so the two render
  branches no longer ran an identical hook sequence. The app shell is
  not session-gated and `logout()` clears the session synchronously
  before the redirect round-trip (and scheduled token refresh can
  swap roles), so signing out — or a role-changing refresh — while
  viewing the Audit trail re-rendered the view with `allowed = false`;
  React threw "Rendered fewer hooks than during the previous render"
  and, with no error boundary in the portal, unmounted the whole UI.
- **Code (Nit)**: the panel exports a `DrilldownPatch` contract, but
  the view typed the callback as `Partial<Filters>`, leaving the
  exported contract dead.
- **Doc (Minor)**: the v0.29.1 share-bar retirement was not annotated
  in the SPEC-047 index line, the spec changelog, or the delivery
  roadmap.

## What changed

- The callback moved above the early return beside the other hooks;
  it already guarded `!allowed` internally, so behavior is unchanged.
- The callback is typed `(patch: DrilldownPatch) => void`, making the
  one-dimension-at-a-time drill-down invariant compile-time.
- A regression test renders the view as an auditor, flips the role
  gate while mounted, and asserts no throw plus the denial posture;
  it fails on the pre-fix code (260 portal tests green).
- The three doc surfaces now annotate the bar retirement, following
  the SPEC-036 R-1 revert annotation posture from 0.18.1.

## Untouched

Drill-down semantics, the outcome filter dimension end-to-end, the
Summary tab rendering, and every backend/gateway path (review
verified the filtering, gating, and store parity clean). Version
lockstep 0.29.2 validated across all products and the portal;
`make verify` green before and after `make build`.
