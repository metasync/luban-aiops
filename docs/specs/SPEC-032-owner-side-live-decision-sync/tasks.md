# SPEC-032 Tasks: Owner-Side Live Decision Sync

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Poll-while-pending on the active session

- [ ] add `usePendingDecisionPoll` hook with change-gated session-detail polling (`products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts`)
- [ ] wire the hook into `ChatView` reusing the initial-load seeding path (`products/operator-portal/web-ui/app/src/chat/ChatView.tsx`)
- [ ] test: external approval flips the pending card and surfaces the resumed turn without refresh (`products/operator-portal/web-ui/app/src/chat/__tests__/usePendingDecisionPoll.test.ts`)

## R-2: Bounded polling

- [ ] gate the interval on pending-card presence and stream idleness; tear down on either change (`products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts`)
- [ ] test: no polling while idle or streaming; in-flight response dropped when a stream starts (`products/operator-portal/web-ui/app/src/chat/__tests__/usePendingDecisionPoll.test.ts`)

## R-3: Outcome parity

- [ ] test: deny and expired resolutions flip via the same poll path (`products/operator-portal/web-ui/app/src/chat/__tests__/usePendingDecisionPoll.test.ts`)

## Delivery Gate

- [ ] all acceptance criteria in `spec.md` verified
- [ ] living state docs updated (`docs/guides/approval-and-hitl.md`, `docs/guides/portal-user-guide.md`)
- [ ] `CHANGELOG.md` entry added referencing the spec ID
- [ ] spec index in `docs/specs/README.md` updated
- [ ] spec status set to `delivered`
