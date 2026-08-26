# SPEC-035 Implementation Plan

One backend fix (agent-service transcript reconstruction), the rest
portal-only under `products/operator-portal/web-ui/app`. No contract or
schema changes.

## R-1 transcript block separators (backend)

- `products/agent-platform/src/agent_service/services/session_transcript.py`:
  `_extract_text` joins the message's text blocks with `"\n\n"` instead
  of `""`. Empty blocks stay skipped. Nothing else consumes
  `_extract_text`; the kernel's own memory is untouched.
- Test: new case in `tests/test_session_workspace.py` — a snapshot whose
  assistant message carries `text / tool_call / tool_result / text`
  blocks reconstructs with a blank line between the two text parts.

## R-2 live-stream segment break (portal)

- `src/stream/useChatStream.ts`: `ChatTurn` gains an internal
  `segmentBreak?: boolean`. `handleEvent` sets it on `tool_call` and
  `tool_result` frames; on the next `delta` it prefixes `"\n\n"` to the
  accumulating `replyText` (only when the reply is non-empty) and clears
  the flag. Live approve streams and parked-turn resumes share this path.
- Test: `useChatStream.test.ts` — deltas → tool pair → deltas accumulate
  with exactly one `\n\n` at the boundary.

## R-3 robust settle window (portal)

- `src/chat/usePendingDecisionPoll.ts`:
  - replace `SETTLE_TICKS` (12 × 5 s) with `SETTLE_WINDOW_MS = 300_000`;
    track `settleUntilRef` (epoch ms) alongside the existing
    session-scoped ref; every applied change resets the deadline;
  - tick body: while settling, an unchanged fingerprint past the deadline
    stops the poll (clear interval);
  - the poll effect additionally registers `document.visibilitychange`
    and `window.focus` listeners that run `tick()` immediately when the
    tab comes back, so background-tab timer throttling cannot starve the
    window.
- Tests: `usePendingDecisionPoll.test.ts` with vi fake timers — a change
  landing at ~90 s (past the old budget) still applies; five quiet
  minutes stop the poll; a visibilitychange kick fetches immediately.

## R-4 arrival presentation (portal)

- `src/chat/transcript.ts`: `detectArrivalSpan` returns
  `{ from: number; prevReplyChars: number } | null` — the index of the
  first turn that gained content and that turn's previous reply length
  (0 for appended turns), so the reveal starts where the old text ended.
- `src/chat/ChatView.tsx`:
  - arrival state stores the span; `ARRIVAL_WINDOW_MS` grows to 6000;
  - `TurnGroup` gains `revealFromChars?: number` — when set, the reply
    bubble reveals from that offset with a ~25 ms interval adding a
    chunk proportional to the total (bounded to finish within the
    arrival window); evidence and cards render immediately;
  - `prefers-reduced-motion` skips the reveal (full text at once) and
    keeps the static tint;
  - first arrived group scrolls into view (`block: "nearest"`, smooth
    unless reduced motion); the auto-scroll-to-bottom effect yields
    while an arrival presentation is active.
- `src/theme/global.css`: stronger `.turn-arrived` — 4 s flash from a
  slightly heavier accent tint plus a 2 px accent left edge
  (`box-shadow` inset), reduced-motion keeps the static tint.

## R-5 session tag timing (portal)

- `src/sessions/useSessionWorkspace.ts`: monotonic `seqRef` in
  `refresh` — a response applies only when its sequence is still the
  latest; stale responses drop silently.
- `src/chat/ChatView.tsx`: an effect watching the pending-card count of
  `chat.turns` calls `void refresh()` on every transition while
  authenticated (covers the parking moment of the owner's own stream;
  the decision moment is already covered by `applyDetail`).

## R-6 banner line (portal)

- `ApprovalsView`: keep title + Refresh in the first row; render the
  secondary banner text as its own block line under the row.

## R-7 history pagination (portal)

- `ApprovalsView`: `HISTORY_PAGE_SIZE = 10`; local `historyPage` state;
  the History tab renders the page slice plus antd `Pagination`
  (`size="small"`, `showSizeChanger={false}`) when more than one page
  exists. Page clamps when the record list shrinks.

## Tests

- Updated: `transcript.test.ts` (new arrival shape),
  `usePendingDecisionPoll.test.ts` (window + kick),
  `useChatStream.test.ts` (segment break),
  `views/control/__tests__/ApprovalsView.test.tsx` (banner line,
  pagination), agent-platform `test_session_workspace.py` (block join).

## Release

v0.17.0 lockstep + CHANGELOG + release notes + guides note
(approval-and-hitl.md) + roadmap/specs README rows, then the standard
build → deploy → smoke → tag → gate → push train. The agent-service
image rebuild carries the R-1 fix; the smoke re-checks a session detail
for blank-line-separated segments.
