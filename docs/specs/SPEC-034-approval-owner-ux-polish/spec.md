# SPEC-034: Approval & Owner Chat UX Polish

## Status

- status: `delivered`
- owner: luban-platform-team
- created: 2026-08-26
- release slice: R4 — Approval-Gated Bounded Actions
- related ADRs: none

## Summary

Five portal-only usability enhancements gathered from the v0.15.0 live
approval test: a visible arrival indicator when the owner window receives
new content after a decision, an instant session-list refresh so the
"awaiting approval" tag clears with the decision instead of up to 30
seconds later, Pending/History tabs in the Approvals view, clearly
separated inbox entries with a structured provenance header, and an inbox
banner that also tells approvers unanswered requests expire.

## Motivation

- **Approval outcomes land silently (owner window).** SPEC-032's poll
  reseeds the transcript the moment a decision is applied, but the resumed
  agent messages appear with no visual cue. The live tester nearly missed
  that anything changed after granting approval — the new turn needs an
  arrival highlight.
- **The "awaiting approval" tag lags the decision.** The session panel
  refreshes on a 30-second interval, so after a decision lands (and the
  poll has already reseeded the chat) the session entry keeps showing the
  stale tag for up to half a minute. The poll and the inbox both already
  know the exact moment a decision is applied — the session list should
  refresh right then.
- **The Approvals view mixes queues.** Pending requests and 30-day history
  render in one scrolling list. Tabs with a Pending default keep the
  decider's eye on actionable work.
- **Inbox entries are hard to scan.** Provenance renders as a run-on
  metadata line (`session: …owner: …parked 7 minutes ago`) directly
  against the next entry. Entries need visual separation and a readable
  two-line header (session title, then owner and timing).
- **The banner omits the expiry rule.** The inbox already says pending
  confirmations park until decided and history keeps 30 days, but it does
  not mention that unanswered requests expire after the platform's
  confirmation timeout (`AGENT_HITL_CONFIRM_TIMEOUT`, 600 s default) — the
  rule approvers most need to know.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable
acceptance signals.

### R-1: Owner-window arrival highlight for post-decision content

When the SPEC-032 pending-decision poll re-seeds the active transcript and
the reseeded timeline gained content compared with the turns on screen
(new turn groups, or a longer reply on an existing turn), the portal marks
every turn group from the first changed position onward with a transient
arrival highlight (accent-tinted background flash, roughly 3 seconds).
Pure card-status flips (deny/expiry with no resumed content) do not
trigger the highlight. The arrival detection comparison is a pure,
unit-tested helper.

Acceptance signals:

- Unit tests: `detectArrivalSpan(previous, next)` returns `null` when the
  timelines are content-identical, the first changed index when a reply
  grew, and the previous length when turns were appended.
- ChatView passes a `justArrived` flag to every `TurnGroup` at or after the
  detected span and clears it after the flash duration.
- `.turn-group.turn-arrived` renders a fading accent background via CSS
  keyframes using the shared theme tokens.

### R-2: Instant session-list refresh on applied decisions

When the pending-decision poll applies a reseed (owner window) or the
approvals inbox applies a decision (admin window), the portal triggers a
session-workspace refresh so `pending_confirmation` tags and last-active
ordering update immediately rather than at the next 30-second interval
tick.

Acceptance signals:

- ChatView's `applyDetail` callback invokes the workspace refresh after
  reseeding.
- `useApprovalsInbox` accepts an optional `onDecisionApplied` callback and
  invokes it after a successful decide and after a 409 race patch; App
  wires it to the workspace refresh.
- No new polling interval is introduced; the 30-second cadence stays as
  the background floor.

### R-3: Pending / History tabs in the Approvals view

The Approvals view splits its content into two antd `Tabs`: **Pending**
(default) and **History**, each labelled with its record count. The
Refresh button and info banner stay above the tabs. Both tabs share the
single inbox poll state; deciding the last pending record keeps the
decider on the Pending tab (which then shows its empty state).

Acceptance signals:

- Component test: the Pending tab renders by default and shows only
  pending records; switching to History shows only decided records with
  count labels in both tabs.

### R-4: Separated inbox entries with structured provenance headers

Each inbox entry renders as a visually separated card (border, surface
background, radius, inter-entry spacing). The run-on metadata line becomes
a two-line header: the session title as a prominent first line (falling
back to the session id), and a secondary line with the owner and relative
parked time — plus the decision outcome and relative decided time for
history entries. The confirmation card renders below the header unchanged.

Acceptance signals:

- Component test: an entry renders the session title, owner, parked
  relative time, and — for decided records — the decision outcome and
  decided relative time.
- `.approvals-entry` / `.approvals-entry-header` styles use shared CSS
  custom properties (`--surface`, `--border`, `--radius`).

### R-5: Banner states the pending-request expiry rule

The Approvals banner text additionally tells approvers that unanswered
requests expire after the platform's confirmation timeout (10 minutes by
default, configurable via `AGENT_HITL_CONFIRM_TIMEOUT`). The portal states
the default only — it does not read the server setting.

Acceptance signals:

- Component test: the banner text mentions the expiry and the default
  duration.

## Non-Goals

- No backend or wire-contract changes; everything is portal-only.
- No per-turn "new" badge or unread counter in the session panel — the
  arrival highlight plus instant tag refresh is the scope.
- No countdown timer on pending inbox entries (the banner states the rule;
  per-entry countdowns are a future enhancement).
- No change to the HITL timeout value or its configuration surface.

## Open Questions

None — all five behaviors were requested explicitly in the v0.15.0
live-test feedback; layout discretion for R-4 was granted to the
implementer.

## Change Log

- 2026-08-26: drafted from live-test feedback on v0.15.0 approval flow.
- 2026-08-26: delivered in the 0.16.0 train — all five requirements
  implemented portal-only; 142 portal tests green and `make verify`
  green.
