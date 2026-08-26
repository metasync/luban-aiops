# SPEC-035 Tasks

## 1. Transcript segment boundaries (R-1, R-2)

- [ ] 1.1 agent-service `_extract_text` joins text blocks with `\n\n`;
      workspace test pins the join across tool frames
- [ ] 1.2 useChatStream segment break after tool frames + stream test

## 2. Robust decision sync (R-3)

- [ ] 2.1 Time-based settle window (5 min), reset on applied change
- [ ] 2.2 Visibility/focus kick runs an immediate tick
- [ ] 2.3 usePendingDecisionPoll tests: late change, window lapse, kick

## 3. Arrival presentation (R-4)

- [ ] 3.1 `detectArrivalSpan` returns `{ from, prevReplyChars }`; unit
      tests updated
- [ ] 3.2 TurnGroup progressive reveal from the previous reply length;
      reduced-motion renders instantly
- [ ] 3.3 Stronger flash + accent edge, scroll first arrived group into
      view, auto-scroll yields during the presentation

## 4. Session tag timing (R-5)

- [ ] 4.1 ChatView refreshes the workspace on pending-card-count
      transitions
- [ ] 4.2 useSessionWorkspace monotonic-sequence stale-response guard

## 5. Approvals layout (R-6, R-7)

- [ ] 5.1 Banner on its own line under the title row
- [ ] 5.2 History tab client-side pagination (10/page, control hidden
      for a single page)
- [ ] 5.3 ApprovalsView component tests: banner line, pagination

## 6. Verification

- [ ] 6.1 Portal suite green; agent-platform suite green
- [ ] 6.2 `make verify` green

## 7. Release gate

- [ ] 7.1 v0.17.0 lockstep, CHANGELOG, release notes, guides, roadmap
      and specs README rows
- [ ] 7.2 Build, deploy to dev-k8s, smoke (bundle markers, transcript
      segment separators), tag, security gate, push
