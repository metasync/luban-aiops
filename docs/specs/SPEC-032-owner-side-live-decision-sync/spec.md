# SPEC-032: Owner-Side Live Decision Sync

## Status

- status: `draft`
- owner: luban-platform-team
- created: 2026-08-25
- release slice: R4 — Approval-Gated Bounded Actions
- related ADRs: none

## Summary

The owner's open chat session learns about decisions made elsewhere: while a
confirmation card is pending, the chat view polls the session detail on a
short interval and re-renders the moment the card resolves, surfacing the
decided card with attribution and the resumed turn's content — without any
new backend surface.

## Motivation

- **v0.13.1 live validation (2026-08-25) exposed the gap.** An operator
  parked a tier_2 confirmation and watched their chat window while the
  designated approver approved from the Approvals view. Nothing happened in
  the owner's window: the card stayed pending and no resumed turn appeared.
  Only a manual page refresh revealed the decided card. The bounded action
  itself executed server-side at approval time (the resume runs under the
  confirmer's delegated token and appends to the owner's transcript), so the
  gap is purely presentation — but an owner who cannot see their approved
  action progress cannot trust the workflow.
- **The resolution frame only rides the answering stream by design.**
  `confirmation_result` flows down the `chat/confirm` stream of whoever
  answered; SPEC-031 deliberately made the durable record store the source
  of truth for everyone else. The approver inbox already consumes that
  posture with a 30s/focus poll; the owner's chat view simply has no
  equivalent yet.
- This completes the R4 theme's UI layer: an approval-gated action should be
  visibly progressing for the requester from the moment the decision lands,
  whoever made it.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable acceptance criteria.

### R-1: Poll-while-pending on the active session

While the active chat session renders at least one `pending` confirmation
card, the chat view polls the session detail (`GET /api/v1/sessions/{id}`,
the same surface that seeds durable cards per SPEC-031 R-2) on a short
interval and re-renders from the authoritative response when the state
moves.

Acceptance criteria:

- With a pending card open, an approval made from the approver's inbox (or a
  second browser session) appears in the owner's open window within the poll
  interval: the card flips to `approved` with decider attribution, and the
  resumed turn's content (tool result and the agent's follow-up) becomes
  visible without a manual refresh.
- The re-render is change-gated: identical poll responses do not rebuild the
  turn timeline or disturb scroll position, composer draft, or an in-flight
  render.
- No manual refresh is required at any point in the flow.

### R-2: Bounded polling

Polling runs only while it can observe a change.

Acceptance criteria:

- No polling occurs when the session has no pending confirmation card
  (idle sessions, decided-only transcripts, empty sessions).
- No polling occurs while any chat stream is active (sending a message or
  answering a confirmation from this window), so the poll can never abort
  or interleave with a live stream.
- Polling stops automatically once the last pending card resolves; the
  session list's existing refresh cadence carries the sidebar's
  `awaiting approval` tag back to normal on its own.

### R-3: Outcome parity

The sync treats every resolution identically.

Acceptance criteria:

- Denials surface with the same flip-and-attribution behavior as approvals
  (decided-by note, read-only card).
- Expirations (the HITL TTL passing, surfaced after a restart sweep or a
  live expiry) flip the card to `expired` on the same poll path.
- A decision made from this same window (a tier_1 self-confirmation) keeps
  its existing stream-driven update; the poll never fights or duplicates it.

## Non-Goals

- Server push (SSE/WebSocket session-event channel): rejected for now — the
  platform's live surfaces all poll, and the bounded poll is portal-only.
  Revisit if more surfaces need sub-second sync.
- Cross-tab sync within the owner's own browser tabs beyond what a refresh
  already provides.
- Any backend change: the session detail already carries live confirmation
  state (SPEC-031 R-1/R-2) and the completed resumed transcript.

## Impact

- products touched: `products/operator-portal/web-ui/app` (chat view)
- contracts touched: none
- identity / policy / audit / execution safety impact: none (read-only poll
  on an already-authorized surface; decisions keep the SPEC-030 bridge)
- living state docs to update on delivery: `docs/guides/approval-and-hitl.md`,
  `docs/guides/portal-user-guide.md`, CHANGELOG, release notes

## Open Questions

- none — the poll interval (5s, matching "near-instant but bounded") is
  recorded in the plan rather than gated here.

## Changelog

- 2026-08-25: created as `draft`, drafted directly from the v0.13.1 live
  validation finding (owner window deaf to external decisions).
