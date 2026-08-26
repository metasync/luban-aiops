# SPEC-035: Decision Sync Robustness and Arrival Polish

## Status

- status: `draft`
- owner: luban-platform-team
- created: 2026-08-26
- release slice: R4 — Approval-Gated Bounded Actions
- related ADRs: none

## Summary

Seven fixes from the v0.16.0 live approval test: the resumed reply after
an approval now reaches the owner window reliably (longer, time-based
settle window with a visibility kick), transcript segments keep their
paragraph boundaries so headings like `## Pod Restart Summary` render as
markdown (both in the durable transcript reconstruction and the live
stream), newly arrived content is revealed progressively instead of
appearing in one silent jump, the session panel's "awaiting approval" tag
appears when a request parks and can no longer be resurrected by a stale
list response, the Approvals banner moves to its own line, and the inbox
History tab paginates.

## Motivation

The v0.16.0 live test (pod restart, approver decided from the admin
window) exposed four functional gaps and two layout gaps:

- **The resumed reply can need a manual refresh.** After approval the
  owner window flipped the card to Approved, but the agent's resumed
  content (tool execution plus summary) only landed after the tester
  refreshed the browser. Root cause: SPEC-032's settle window is 12
  ticks of 5 seconds — 60 seconds — counted only while the tab's timers
  run. A resumed turn that runs tools and then summarizes can outlast
  that budget, and background tabs throttle timers further, so the poll
  gives up before the transcript grows.
- **Resumed headings render as raw markdown.** The kernel persists an
  assistant message as a list of text blocks (one per reasoning segment
  between tool calls); `session_transcript._extract_text` flattens them
  with `"".join(...)`, so a segment that starts with `## Pod Restart
  Summary` lands mid-line (`...controller.## Pod Restart Summary`) and
  the heading regex never fires. The live stream has the same boundary
  problem: deltas from segments separated by tool frames accumulate with
  no paragraph break.
- **The arrival highlight went unnoticed.** SPEC-034's 3-second background
  tint was too subtle, and in the approve case nothing arrived until
  refresh (no detection ran at all). The tester suggested revealing the
  reply progressively so the eye catches the movement.
- **The "awaiting approval" tag has the wrong timing.** It never appears
  when a request parks (the session list only refreshes on its 30-second
  cadence), and an in-flight stale list response can land *after* the
  decision refresh and resurrect the tag on an already-decided session.
- **Approvals layout.** The info banner crowds the title row, and the
  History tab grows unbounded (50 records per session over 30 days).

## Requirements

Each requirement is stable once the spec is `approved` and carries
testable acceptance signals.

### R-1: Paragraph boundaries between transcript text blocks

`agent_service.services.session_transcript` joins the text blocks of a
message with a blank line (`\n\n`) instead of an empty string, so block
markdown at a segment start (headings, lists, rules) survives the
durable transcript reconstruction. Tool/thinking blocks remain skipped.

Acceptance signals:

- A state snapshot whose assistant message carries two text blocks
  separated by tool frames reconstructs to content joined by `\n\n`.
- Single-block messages are unchanged.

### R-2: Paragraph break between tool-separated live stream segments

The chat stream hook inserts a paragraph break into the accumulating
reply before the first delta that follows a tool frame, so a live
approve (where the resumed segments ride the answering stream) renders
the same boundaries as the reseeded transcript.

Acceptance signals:

- Stream-hook test: deltas, then a tool_call/tool_result pair, then more
  deltas accumulate with a `\n\n` separator at the segment boundary and
  nowhere else.

### R-3: Time-based settle window with visibility kick

The pending-decision poll's post-decision settle window is time-based
(5 minutes) instead of a tick budget, resets whenever a change applies,
and the poll ticks immediately when the tab becomes visible or focused.
Polling still stops on its own once the window lapses without change and
never runs while a stream is active.

Acceptance signals:

- Hook tests with fake timers: a change that lands after the old 60-second
  tick budget still applies; the window lapses after 5 quiet minutes;
  a visibility/focus event triggers an immediate fetch.

### R-4: Progressive arrival presentation

When a reseed delivers new content (per the SPEC-034 detection), the
newly arrived reply text reveals progressively (typewriter-style,
bounded total duration) instead of appearing in one jump, the turn
groups from the first changed position carry a more prominent arrival
flash (background tint plus accent edge), and the first arrived group
scrolls into view. Pure card flips still trigger nothing. All motion
degrades to an instant render with a static tint under
`prefers-reduced-motion`.

Acceptance signals:

- The arrival detection helper reports the previous reply length for the
  first changed turn so the reveal starts where the old text ended;
  unit tests pin the shape.
- ChatView passes reveal parameters only to arrived turn groups and
  clears them after the presentation window.
- Reduced-motion users get the full text immediately.

### R-5: Session tag appears at park and never resurrects

The session workspace refreshes whenever the active transcript's pending
card count changes (covering the parking moment of the owner's own
stream, in addition to the decision moment already wired by SPEC-034),
and `useSessionWorkspace` discards list responses from superseded
refresh requests so a slow stale response cannot overwrite fresher
state.

Acceptance signals:

- ChatView triggers a workspace refresh on pending-card-count
  transitions while authenticated.
- useSessionWorkspace guards responses with a monotonic request
  sequence; a stale response from an earlier request never applies.

### R-6: Approvals banner on its own line

The Approvals info banner renders on its own line below the title row
(keep title + Refresh button on the first row).

Acceptance signals:

- Component test: the banner text still renders; it is no longer a
  sibling of the title row's flex container.

### R-7: History tab pagination

The History tab paginates client-side at 10 entries per page with an
antd `Pagination` control (hidden while one page suffices). The Pending
tab stays unpaginated — it is the actionable queue and stays short by
construction (50-record server cap, decisions drain it).

Acceptance signals:

- Component test: with more than 10 history records the first page shows
  10 entries and the second page shows the remainder; with 10 or fewer
  no pagination control renders.

## Non-Goals

- No server-side pagination for the inbox API (the 30-day/50-per-session
  caps keep the payload bounded; client-side pagination suffices).
- No per-entry countdown timers on pending records.
- No cross-owner session visibility, session inheritance, or shift
  handoff artifacts — those are separate future specs (see Open
  Questions).
- No change to the HITL timeout value.

## Open Questions

- **Shift handoff / reviewing other users' sessions.** Raised by the
  tester as an operational need (incident review and 7x24 roster
  handover). Tracked as future work: a read-only cross-owner session
  review surface (role-gated, audit-logged) and an agent-generated
  shift-summary artifact are the candidate directions; session
  inheritance is discouraged (never-expiring sessions, ambiguous HITL
  ownership). Not in scope here.

## Change Log

- 2026-08-26: drafted from live-test feedback on v0.16.0 approval flow.
