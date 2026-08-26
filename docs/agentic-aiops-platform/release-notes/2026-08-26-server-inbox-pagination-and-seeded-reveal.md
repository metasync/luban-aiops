# v0.18.0 — Server Inbox Pagination and Seeded Transcript Reveal (SPEC-036)

Date: 2026-08-26
Release type: minor (inbox response shape restructured monorepo-wide;
no contract schema or policy changes)

## Summary

v0.18.0 closes two follow-ups from the v0.17.0 review. The approvals
inbox History tab moves to server-side pagination: the combined inbox
payload's old 100-row cap silently dropped decisions past the newest
100 as volume grew, so the store now serves an always-complete pending
queue plus an offset-paginated history page with its retention-window
total, forwarded verbatim through the gateway and rendered
server-driven in the portal. The progressive typewriter reveal extends
from arrived content to cold-seeded transcripts: opening a session now
cascades every seeded reply top-to-bottom instead of popping the whole
transcript in at once. *(The seeded-transcript reveal was reverted in
v0.18.1 after live-check feedback — see the patch notes; the typewriter
applies to live arrivals only.)*

## What Changed

### Split inbox store queries (R-2)

- `load_inbox` is replaced by `load_pending_inbox` (all pending rows,
  newest first, sanity-capped — hiding parked work must stay
  impossible) and `load_inbox_history(limit, offset)` (resolved rows
  within the 30-day `decided_at` window, `parked_at DESC` with a
  `confirm_id` tiebreak) returning the page plus the windowed total.
- Both backends implement both queries; Postgres adds a dedicated
  `COUNT(*)` over the same window so the pager total matches the page
  filter exactly.

### Paginated inbox API (R-3)

- `GET /api/v2/confirmations` accepts `history_limit` (1–50, default
  10) and `history_offset` (≥ 0, default 0) and returns
  `{ confirmations: […pending…], history: […page…], history_total: N }`.
  Pending rows keep their sanity cap and are never paginated.

### Gateway pass-through (R-4)

- `GET /api/v1/approvals/inbox` forwards both params verbatim to the
  agent service; the `approvals:list` policy gate, upstream 4xx
  pass-through / 5xx→502 error mapping, and audit logging are
  unchanged apart from logging pending and history counts separately.

### Server-driven History tab (R-5)

- The portal History tab renders the server page: the tab label carries
  `history_total`, the antd pager (10 per page, hidden while one page
  suffices) navigates by offset, page navigation refetches, and the
  30 s poll / manual refresh re-reads the *current* page so browsing is
  never snapped back to page one. A decision made from the Pending tab
  appears on the first history page immediately (local move) and
  normalizes on the next refresh. Pending tab and badge semantics are
  unchanged.

### Seeded-transcript reveal cascade (R-1)

*(Reverted in v0.18.1 after live-check feedback; retained here as the
shipped 0.18.0 record.)*

- A cold-seeded transcript (first fetch of a session in a tab — never a
  cache-restore switch) reveals every reply with the same typewriter as
  arrivals: turns cascade top-to-bottom with a per-turn stagger
  (≤ 150 ms, compressed so the whole cascade starts within ~3 s on long
  transcripts), each turn bounded to ~6 s with chunk size scaling with
  length. No arrival flash (nothing new arrived), no scroll hijack;
  `prefers-reduced-motion` degrades to instant render, and switching
  sessions cancels any in-flight cascade. An active arrival still owns
  the presentation at its start turn.

## Validation

- Portal suite 160/160 (vitest) + `tsc --noEmit` clean; agent-platform
  suite 474 passed (store split, retention, pagination, SQL-shape,
  route shape); gateway suite 228 passed (param forwarding + matrix).
- `make verify` green: version lockstep 0.18.0, four kustomize
  overlays, policy validation.
- Smoke: inbox endpoint shape re-checked through the gateway
  port-forward (`confirmations` / `history` / `history_total` split).
