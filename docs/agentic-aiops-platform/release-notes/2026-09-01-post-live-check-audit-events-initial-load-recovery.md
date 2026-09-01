# Post-Live-Check Remediation: Audit Events Initial-Load Recovery (v0.29.3)

Date: 2026-09-01

Remediation batch from the post-v0.29.2 live-check observation: the
Audit Events tab intermittently rendered its initial empty posture
while the Summary tab counted the full trail, and a manual Refresh
restored the rows. One component touched — `AuditView.tsx` — plus one
regression test; no API, contract, route, or policy changes.

## What the investigation proved

- The server path is innocent: direct unfiltered queries to
  audit-service return rows, and timestamp-correlated gateway ↔
  audit-service logs show every 200 during the repro window served a
  full 50-row page. The audit service never returned an empty page.
- The observed posture is the client's initial render state
  (`loaded=false`), so the first auto-load's result was never applied
  to the mounted view.
- The gateway log exposed the trigger environment: before the fresh
  sign-in, the browser booted under a stale expired stored session
  (`/sessions` and `/approvals/inbox` answered 401, the silent
  `/auth/refresh` failed and cleared the session). The shell still
  renders signed-in during that window because
  `refreshAuthenticatedIdentity` deliberately falls back to the
  cached identity, so an audit auto-load fired in the window fails
  401.

## What changed

- The Audit view's initial-load effect latched on that failure: the
  `!error` guard plus `[allowed]`-only deps meant the effect never
  re-ran after the fresh sign-in (the role gate stayed continuously
  true), leaving the view in its failure posture until a manual
  Refresh, which bypasses the guard. The effect is now keyed on the
  session object as well: when the identity lifecycle moves (stale
  session cleared, fresh sign-in, silent refresh) it clears any
  latched error and retries once if not yet loaded.
- A regression test simulates the stale-session 401 → fresh sign-in
  sequence and asserts auto-recovery without a manual Refresh; it
  fails on the pre-fix code (261 portal tests green).

## Untouched

Drill-down, the outcome filter dimension, the Summary tab, and every
backend/gateway path. Known benign cosmetic: the Summary total can
differ from the section sums by the events ingested between the
`count(*)` and `GROUP BY` statements in `summarize` (no transaction)
— recorded, not worth a release on its own. Version lockstep 0.29.3
validated across all products and the portal; `make verify` green
before and after `make build`.
