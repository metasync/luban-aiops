# SPEC-036 Implementation Plan

Two surfaces: the inbox pagination path (agent-service store + route,
gateway proxy, portal client/hook/view) and one portal chat touch
(seeded reveal). No contract schema files change; the inbox response
shape is restructured monorepo-wide in one train (all consumers ship
together).

## R-1 seeded-transcript reveal (portal)

- `src/chat/transcript.ts`: new pure helper
  `seedRevealIndex(turns: ChatTurn[]): number | null` — the index of
  the last turn with non-empty `replyText`, null otherwise.
- `src/chat/ChatView.tsx`:
  - new `seedReveal` state + timer ref, cleared on session switch and
    after `ARRIVAL_WINDOW_MS`;
  - in the cold-seed branch of the session-switch effect (the
    `getSession(...).then` path — never the cache-restore or
    missing-session branches), compute the index over the seeded turns
    and arm the reveal;
  - render: `revealFromChars={0}` on the seeded index unless an
    arrival is active (arrival wins); no `justArrived` flash, no
    scroll hijack — the existing scroll-to-bottom effect applies.
  - TurnGroup's existing reveal machinery (chunk sizing, reduced
    motion) is reused unchanged.
- Tests: `transcript.test.ts` — `seedRevealIndex` last-reply index,
  null for empty / reply-less transcripts, skips trailing user-only
  turns.

## R-2 split inbox store queries (agent-service)

- `src/agent_service/services/confirmation_records.py`:
  - protocol: replace `load_inbox()` with
    `load_pending_inbox() -> list` and
    `load_inbox_history(limit, offset) -> tuple[list, int]`;
  - Postgres: `_LOAD_INBOX` splits into `_LOAD_INBOX_PENDING`
    (`status = 'pending'`, `parked_at DESC`, `LIMIT` sanity cap) and
    `_LOAD_INBOX_HISTORY` (`status <> 'pending'`, retention window,
    `ORDER BY parked_at DESC, confirm_id DESC`,
    `LIMIT %s OFFSET %s`) plus `_COUNT_INBOX_HISTORY`;
  - memory backend mirrors the same split, ordering, and window.
- Tests: `tests/test_confirmation_records.py` — adapt the existing
  inbox tests to the split API; add a history pagination case
  (limit/offset/total) and a retention-window exclusion case.

## R-3 paginated inbox API (agent-service)

- `src/agent_service/api/v2/routes.py`: `GET /confirmations` gains
  `history_limit: int = Query(10, ge=1, le=50)` and
  `history_offset: int = Query(0, ge=0)`; response becomes
  `{"confirmations": [...pending...], "history": [...page...],
  "history_total": N}` with the same per-record session-title join.
- Tests: route tests assert the new shape, default page, and an
  explicit offset/limit page.

## R-4 gateway pass-through (platform-gateway)

- `api/routes/approvals.py`: accept the same two query params and pass
  them to the service layer; log `pending_count` and `history_count`
  separately.
- `services/gateway_service.py` / `services/agent_client.py`:
  `approvals_inbox` / `fetch_approvals_inbox` take and forward the
  params (`params=` on the upstream GET). Policy gate and error
  mapping unchanged.
- Tests: `tests/test_workspace_proxies.py` — payload shape update, a
  param-forwarding assertion, existing matrix intact.

## R-5 server-driven History tab (portal)

- `src/api/approvals.ts`: `getApprovalsInbox({ historyLimit?,
  historyOffset?, signal? })` returns
  `{ confirmations, history, history_total }`, sending
  `history_limit`/`history_offset` query params.
- `src/views/control/ApprovalsView.tsx`:
  - `ApprovalsInboxState`: replace `records` with `pending`,
    `history`, `historyTotal`, `historyOffset`, `setPageOffset`;
  - `useApprovalsInbox`: refresh reads the current offset (poll never
    snaps the browser back to page 1); `setPageOffset(offset)` moves
    the offset and refetches; `decide` patches the pending record and
    moves it onto the first history page locally when that page is on
    screen (offset 0), normalizing on refresh; 409/410 race paths use
    the same move; disabled state clears all four slots;
  - view: Pending tab renders `pending` filtered to status pending
    (label uses `pendingCount`); History tab renders the server page,
    labels with `history_total`, paginates via antd
    (`current` from offset, `onChange → setPageOffset`), pager hidden
    while one page suffices.
- Tests: `views/__tests__/ApprovalsView.test.tsx` (hook + flows on
  the new shape) and `views/control/__tests__/ApprovalsView.test.tsx`
  (layout helper + server-driven pager tests).

## Release

v0.18.0 lockstep + CHANGELOG + release notes + guides note
(approval-and-hitl.md: server-side history pagination) +
roadmap/specs README rows, then the standard build → deploy → smoke →
tag → gate → push train. The smoke re-checks the inbox endpoint shape
through the gateway port-forward.
