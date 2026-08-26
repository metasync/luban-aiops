# SPEC-036: Server Inbox Pagination and Seeded Transcript Reveal

## Status

- status: `draft`
- owner: luban-platform-team
- created: 2026-08-26
- release slice: R4 — Approval-Gated Bounded Actions
- related ADRs: none

## Summary

Two follow-ups from the v0.17.0 review: the approvals inbox moves its
History tab to server-side pagination (the API previously truncated the
combined payload at 100 rows, silently dropping older decisions as volume
grows), and the progressive typewriter reveal extends from arrived
content to cold-seeded transcripts, so opening a session re-types its
most recent reply instead of popping it in fully formed.

## Motivation

- **The inbox history is quietly truncated.** `GET
  /api/v1/approvals/inbox` serves one combined query — pending plus 30
  days of decided records — under a hard `LIMIT 100`. SPEC-035's
  client-side pagination only sliced that already-truncated payload.
  With 50 records retained per session over 30 days, a busy approver
  exceeds 100 rows easily, and anything past the newest 100 is
  invisible — data loss, not just a layout concern. The operator
  expects the list to grow and asked for server-side pagination.
- **Cold transcripts appear in one silent jump.** SPEC-035's arrival
  reveal covers content that lands via the decision-sync poll, but a
  session opened cold (first load in a tab) renders its whole
  transcript at once. The operator asked for the same progressive
  reveal there for presentation consistency: the eye should follow the
  most recent reply being re-typed, not catch a wall of text appearing
  instantly.

## Requirements

Each requirement is stable once the spec is `approved` and carries
testable acceptance signals.

### R-1: Seeded-transcript reveal

When a session's transcript is cold-seeded from the session detail
(first fetch in this tab — not a cache-restore switch and not an
arrival reseed), the most recent turn with reply text reveals
progressively using the same typewriter mechanism as arrivals: bounded
total duration (~6 s), chunk size scaling with length, and
`prefers-reduced-motion` degradation to instant render. The reveal
carries no arrival flash (nothing new arrived) and does not hijack
scrolling (the standard scroll-to-bottom applies). Switching sessions
cancels any in-flight reveal.

Acceptance signals:

- A pure helper reports the index of the last turn with non-empty
  reply text (null for empty or reply-less transcripts); unit tests
  pin the behavior.
- ChatView wires the helper into the cold-seed path only, clears the
  reveal when the window lapses or the session switches, and never
  applies it on top of an active arrival.

### R-2: Split inbox store queries

The confirmation record store replaces the single combined
`load_inbox` with two queries: all pending records (newest first,
never truncated below the existing sanity cap) and the resolved
history page (`limit`/`offset`, newest first) plus the total resolved
count within the retention window. Both backends (memory, Postgres)
implement both; history ordering is stable (`parked_at` desc with a
`confirm_id` tiebreak).

Acceptance signals:

- Store tests: pending and history split correctly; history paginates
  with a correct total; resolved rows outside the retention window are
  excluded from history but their count is unaffected elsewhere.

### R-3: Paginated inbox API

`GET /api/v2/confirmations` accepts `history_limit` (1–50, default 10)
and `history_offset` (≥ 0, default 0) and returns `{ confirmations:
[…pending…], history: […page…], history_total: N }`. Pending rows keep
their sanity cap and are never paginated — hiding parked work remains
impossible. Invalid params produce the framework's standard 422.

Acceptance signals:

- Route tests: default call returns the first history page with the
  total; explicit limit/offset shift the page; the combined shape
  separates pending from history.

### R-4: Gateway pass-through

`GET /api/v1/approvals/inbox` accepts the same two query params and
forwards them verbatim to the agent service; the policy gate
(`approvals:list`), error mapping (upstream 4xx pass-through, 5xx /
transport → 502), and audit logging are unchanged apart from logging
pending and history counts separately.

Acceptance signals:

- Proxy tests: params reach the upstream client call; the existing
  allow/deny/error matrix stays green with the new payload shape.

### R-5: Server-driven History tab

The portal's History tab renders the server page instead of slicing a
combined payload: the tab label carries `history_total`, the pager
(antd, 10 per page, hidden while one page suffices) navigates by
offset, page navigation refetches, and the 30 s poll / manual refresh
re-reads the *current* page so browsing is not snapped back to page
one. A decision made from the Pending tab appears on the first history
page immediately (local move) and normalizes on the next refresh. The
Pending tab and its badge semantics are unchanged.

Acceptance signals:

- Hook tests against the new response shape: pending/history/total
  state, page navigation refetch, decision moves the record to the
  history page, last-good state survives a failed poll.
- Component tests: pager renders when `history_total` exceeds the page
  size and navigation calls through with the right offset.

## Non-Goals

- Keyset/cursor pagination — offset suffices for the bounded retention
  window (see Open Questions for the trade-off).
- Cross-owner session review, shift-summary artifacts, or session
  inheritance — separate future specs.
- Any change to pending-record behavior, retention windows, or caps.
- Revealing historical turns other than the most recent reply on
  cold-seed.

## Open Questions

- **Offset vs keyset.** Keyset cursors were considered and dropped for
  this surface: the antd pager supports random page access (awkward
  with forward-only cursors), the retention window is bounded, and the
  opportunistic sweep only deletes rows aging out of the window — so
  offset drift is confined to the retention tail and benign. Revisit
  only if the inbox ever loses its retention bound.
- The future cross-owner session review spec (agreed direction:
  role-gated, read-only, audit-logged) and the shift-summary artifact
  spec are tracked on the roadmap; neither is in scope here.

## Change Log

- 2026-08-26: drafted from the v0.17.0 post-release review.
