# v0.17.0 — Decision-Sync Robustness and Arrival Polish (SPEC-035)

Date: 2026-08-26
Release type: minor (one agent-service read-path fix plus portal UX;
no contract, schema, or policy changes)

## Summary

v0.17.0 closes the four findings from the v0.16.0 live approval test.
The owner window now reliably surfaces the resumed turn's content after
an external decision — even when the tool run and summary generation
trail the decision by minutes — and presents the arrived text so it
cannot be missed: a typewriter reveal from where the old reply ended,
a stronger flash with an accent edge, and scroll-into-view. Reconstructed
transcripts stop gluing kernel text segments together, so
`## Pod Restart Summary` renders as a heading instead of raw markdown.

## What Changed

### Transcript block separators (R-1, R-2)

- **Backend.** The kernel persists an assistant message as one text
  block per reasoning segment between tool calls. The transcript
  read path joined those blocks with an empty string, gluing a
  segment-start heading onto the previous segment's last sentence
  (`...controller.## Pod Restart Summary`) so block markdown never
  matched. `_extract_text` now joins with a blank line; the kernel's
  own memory is untouched (read-path only).
- **Live stream parity.** `useChatStream` sets a segment-break flag on
  tool frames and the next delta opens a new paragraph, so approve
  streams and parked-turn resumes render block markdown live as well.

### Robust settle window (R-3)

- The SPEC-032 poll's settle window is now a five-minute deadline
  instead of a 12-tick (60 s) budget: every applied change resets it,
  and a `visibilitychange`/`focus` kick ticks immediately when the tab
  returns to the foreground (background tabs throttle `setInterval`).
  A resumed turn that runs tools before summarizing — the exact live
  failure — now lands without a manual refresh.

### Arrival presentation (R-4)

- `detectArrivalSpan` returns the first changed turn plus how many
  reply chars were already on screen. The reply bubble re-types itself
  from that offset (chunk size scales with the landed text; bounded to
  a 6 s window), evidence and cards render at once, the first arrived
  group scrolls into view, and the flash gains a heavier tint and a
  2 px accent left edge. `prefers-reduced-motion` degrades to instant
  reveal with the static tint.

### Session tag timing (R-5)

- ChatView refreshes the session workspace at every pending-card
  transition (covering the parking moment of the owner's own stream;
  the decision moment was already covered), and the workspace refresh
  keeps a monotonic sequence so a stale in-flight list response can no
  longer overwrite fresher `pending_confirmation` flags.

### Approvals layout (R-6, R-7)

- The info banner sits on its own line under the title row.
- The History tab paginates ten entries per page (client-side; the
  server already caps the payload), with the page clamping when the
  retained list shrinks.

## Validation

- Portal suite: 150 tests across 16 files, including the new arrival
  span shape, settle-window deadline/kick tests, live segment-break
  tests, banner-line and history-pagination component tests.
- agent-platform: 21 session-workspace tests including the new
  blank-line block join case.
- `make verify` green: full multi-product test suite, kustomize overlay
  builds, policy validation, version lockstep at 0.17.0.

## Compatibility

- Read-path and portal-only: no wire-contract, schema, policy, or
  storage changes; no migration or restart coordination required. The
  agent-service image rebuild carries the transcript fix.
