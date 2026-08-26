# SPEC-034 Tasks

## 1. Arrival detection helper (R-1)

- [ ] 1.1 Add `detectArrivalSpan(previous, next)` to `transcript.ts`
- [ ] 1.2 Unit tests: identical, reply-grew, appended, card-only-flip

## 2. Owner-window wiring (R-1, R-2)

- [ ] 2.1 ChatView `applyDetail`: detect span, set `arrivedFrom`, clear
      after flash timeout, pass `justArrived` to TurnGroup
- [ ] 2.2 ChatView `applyDetail`: invoke workspace refresh after reseed
- [ ] 2.3 `global.css`: `.turn-group.turn-arrived` flash keyframes +
      reduced-motion guard

## 3. Approvals inbox refresh wiring (R-2)

- [ ] 3.1 `useApprovalsInbox` accepts `onDecisionApplied`; fires after
      successful decide and 409 race patches
- [ ] 3.2 App passes `workspace.refresh` as the callback

## 4. Approvals view layout (R-3, R-4, R-5)

- [ ] 4.1 Pending/History tabs with count labels, Pending default
- [ ] 4.2 InboxEntry card separation + two-line provenance header
      (decided entries show outcome + decided relative time)
- [ ] 4.3 Banner text adds the pending-expiry rule (10 minutes default)
- [ ] 4.4 `global.css` entry-card styles on shared tokens

## 5. Tests & verification

- [ ] 5.1 `ApprovalsView.test.tsx`: tabs filtering, header fields, banner
- [ ] 5.2 `make verify` green

## 6. Release gate

- [ ] 6.1 v0.16.0 lockstep, CHANGELOG, release notes, guides, roadmap and
      specs README rows
- [ ] 6.2 Build, deploy to dev-k8s, smoke (bundle version, tabs render),
      tag, security gate, push
