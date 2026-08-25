# SPEC-032 Tasks: Owner-Side Live Decision Sync

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Poll-while-pending on the active session

- [x] add `usePendingDecisionPoll` hook with change-gated session-detail polling (`products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts`)
- [x] wire the hook into `ChatView` reusing the initial-load seeding path (`products/operator-portal/web-ui/app/src/chat/ChatView.tsx`)
- [x] test: external approval flips the pending card and surfaces the resumed turn without refresh (`products/operator-portal/web-ui/app/src/chat/__tests__/usePendingDecisionPoll.test.ts`)

## R-2: Bounded polling

- [x] gate the interval on pending-card presence and stream idleness; tear down on either change (`products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts`)
- [x] test: no polling while idle or streaming; in-flight response dropped when a stream starts (`products/operator-portal/web-ui/app/src/chat/__tests__/usePendingDecisionPoll.test.ts`)

## R-3: Outcome parity

- [x] test: deny and expired resolutions flip via the same poll path (`products/operator-portal/web-ui/app/src/chat/__tests__/usePendingDecisionPoll.test.ts`)

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified
- [x] living state docs updated (`docs/guides/approval-and-hitl.md`, `docs/guides/portal-user-guide.md`)
- [x] `CHANGELOG.md` entry added referencing the spec ID
- [x] spec index in `docs/specs/README.md` updated
- [x] spec status set to `delivered`
