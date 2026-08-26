# v0.16.0 — Approval & Owner Chat UX Polish (SPEC-034)

Date: 2026-08-26
Release type: minor (portal-only usability enhancements; no backend,
contract, or policy changes)

## Summary

v0.16.0 ships five portal enhancements gathered from the v0.15.0 live
approval test. Post-decision content in the owner window is now visibly
signposted, the session panel learns decisions instantly, and the
Approvals view is reorganized into Pending/History tabs with separated,
readable entry cards and a banner that states the expiry rule.

## What Changed

### Owner window (R-1, R-2)

- **Arrival highlight.** When the SPEC-032 decision-sync poll reseeds the
  transcript and the timeline gained content (a resumed reply grew, or a
  new turn appeared), every turn group from the first changed position
  onward flashes a 3-second accent tint. Pure card flips (deny/expiry
  with no resumed content) do not flash. Detection is a pure helper
  (`detectArrivalSpan`) with dedicated unit tests, and the flash honors
  `prefers-reduced-motion`.
- **Instant session-list refresh.** The poll's apply path and the
  approvals inbox (successful decide and 409 race patches) now trigger a
  session-workspace refresh immediately, so the "awaiting approval" tag
  and last-active ordering update with the decision instead of at the
  next 30-second poll tick. The 30-second cadence remains the background
  floor.

### Approvals view (R-3, R-4, R-5)

- **Tabs.** Pending (default) and History, each labelled with its record
  count. The decider's eye stays on actionable work; decided records
  live one click away.
- **Separated entries with structured headers.** Each inbox entry is a
  bordered card. The run-on metadata line (`session: …owner: …parked …`)
  becomes a two-line header: session title (falling back to the session
  id) first, then owner and relative parked time — plus the decision
  outcome, relative decided time, and decider attribution for history
  entries, and a status tag beside the title.
- **Expiry in the banner.** The info banner now also says unanswered
  requests expire after the confirmation timeout —
  `AGENT_HITL_CONFIRM_TIMEOUT`, 10 minutes by default. The portal states
  the default; it does not read the server setting.

## Validation

- Portal suite: 142 tests across 16 files, including new
  `detectArrivalSpan` unit tests and an `ApprovalsView` component suite
  (tabs, headers, banner); the pre-existing SPEC-031 inbox suite was
  updated to the tab layout. A vitest jsdom setup file stubs
  `ResizeObserver` for antd layout components.
- `make verify` green: full multi-product test suite, kustomize overlay
  builds, policy validation, version lockstep.

## Compatibility

- Portal-only: no wire-contract, schema, policy, or storage changes;
  no migration or restart coordination required.
