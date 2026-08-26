# SPEC-034 Implementation Plan

Portal-only changes under `products/operator-portal/web-ui/app`. No
backend, contract, or schema edits.

## R-1 arrival highlight

- `src/chat/transcript.ts`: add `detectArrivalSpan(previous, next)` —
  pure comparison over `ChatTurn[]`. Returns `null` when `next` carries no
  additional content, otherwise the index of the first turn that gained
  content (longer `replyText`, more confirmations with resumed text, or an
  appended turn). New turns beyond `previous.length` return
  `previous.length`.
- `src/chat/ChatView.tsx`: `applyDetail` computes
  `detectArrivalSpan(chat.turns, reseeded)` before reseeding; when a span
  is detected, stores it in `arrivedFrom` state and clears it after
  `ARRIVAL_FLASH_MS` (3000). `TurnGroup` gains a `justArrived` prop →
  `turn-group turn-arrived` class.
- `src/theme/global.css`: `.turn-group.turn-arrived` keyframe flash from
  an accent tint (`color-mix` of `--accent`) to transparent, 3 s ease-out,
  plus a reduced-motion guard.

## R-2 instant session-list refresh

- `ChatView.applyDetail`: after `chat.reseedTurns`, call `void refresh()`
  (the workspace refresh already in scope).
- `useApprovalsInbox(enabled, onDecisionApplied?)`: fire the callback
  after the optimistic patch on success and after a 409 race patch (both
  mean a decision just became true somewhere).
- `App.tsx`: pass `() => void workspace.refresh()` as the callback.

## R-3 tabs

- `ApprovalsView`: replace the two inline sections with antd `Tabs`
  (items API): `Pending (n)` default, `History (n)`. Empty-state wording
  stays. Counts derive from the same `records` split already computed.

## R-4 entry cards and headers

- `InboxEntry` restructure:
  - outer `.approvals-entry` card (surface, border, radius, 16 px gap);
  - header line 1: session title (`Text strong`, ellipsis) — falls back to
    session id;
  - header line 2: `owner: {owner_user_id} · parked {relative}`; history
    entries append `· {decision} {relative decided_at}`;
  - `ConfirmationCardView` below, unchanged.
- `global.css`: `.approvals-entry`, `.approvals-entry-header`,
  `.approvals-entry-title`, `.approvals-entry-sub` using `--surface`,
  `--surface-alt`, `--border`, `--radius`, `--text-muted`.

## R-5 banner expiry note

- Banner text becomes: "Pending confirmations park here until decided —
  unanswered requests expire after the confirmation timeout (10 minutes by
  default). History keeps decisions for 30 days."

## Tests

- `transcript.test.ts`: `detectArrivalSpan` — identical, reply-grew,
  appended-turns, card-only flip (null).
- new `views/control/__tests__/ApprovalsView.test.tsx`: default Pending
  tab filters records, History tab shows decided entries with the
  structured header fields, banner mentions expiry. Mock
  `getApprovalsInbox` and the stream transport; drive via the exported
  hook state (pass a fake `ApprovalsInboxState`) to avoid poll timers.

## Release

v0.16.0 lockstep + CHANGELOG + release notes + guides note
(approval-and-hitl.md) + roadmap/specs README rows, then the standard
build → deploy → smoke → tag → gate → push train.
