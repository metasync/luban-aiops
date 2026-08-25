# SPEC-032 Plan: Owner-Side Live Decision Sync

## Approach

Portal-only change. A new `usePendingDecisionPoll` hook watches the active
chat session's turns and, while at least one confirmation card is pending
and no stream is active, polls the existing session-detail surface every
`PENDING_SYNC_INTERVAL_MS` (5s). Responses are change-gated by a cheap
fingerprint (confirmation statuses + transcript length); a moved state
rebuilds the turn timeline through the same `transcriptToTurns` path the
initial load uses, so the decided card and the resumed turn's content appear
exactly as they would after a manual refresh. No backend, contract, or
policy surface changes.

## Design Per Requirement

### R-1: Poll-while-pending on the active session

- affected files: `products/operator-portal/web-ui/app/src/chat/
  usePendingDecisionPoll.ts` (new), `src/chat/ChatView.tsx` (wiring),
  `src/api/sessions.ts` (reuse `getSession`)
- approach: `setInterval`-driven `getSession(sessionId)` while active; on a
  moved fingerprint, call `applyDetail(detail)` which runs
  `transcriptToTurns(detail.transcript, detail.evidence_turns,
  detail.confirmations)` and `chat.setSession(sessionId, turns)` — the same
  seeding path as the initial load (SPEC-031 R-2). Change-gating keeps
  identical responses no-ops (no turn rebuild, no scroll disturbance).
- alternatives rejected: (a) unconditional periodic re-render — disturbs
  scroll/focus on every tick; (b) SSE session channel — new backend surface
  for a 5s-acceptable latency (Non-Goals).

### R-2: Bounded polling

- the effect's dependency set derives `active = Boolean(sessionId) &&
  !streaming && turns.some(t => t.confirmationPending)`; the interval exists
  only while `active`. A stream starting, the session switching, or the last
  card resolving all tear the interval down via effect cleanup.
- in-flight guard: a fetch started under `active` can resolve after a stream
  begins; the apply callback re-checks a `shouldApply()` closure (streaming
  flag + session match) before touching turn state, so a poll can never
  abort or interleave with a live stream (`setSession` aborts controllers —
  it must not run mid-stream).

### R-3: Outcome parity

- the fingerprint covers every status (`pending` → `approved` | `denied` |
  `expired`), and the rebuild path is status-agnostic: `transcriptToTurns`
  already renders all four card states with attribution (SPEC-031 R-2/R-5
  coverage). A same-window decision (tier_1) arrives via the confirm stream
  first; once the card is no longer pending the poll is already torn down,
  so no duplication.

## Sequencing And Dependencies

1. `usePendingDecisionPoll` hook + unit tests — depends on nothing
2. ChatView wiring — depends on stage 1
3. Guide wording (approval-and-hitl, portal-user-guide) — depends on stage 2
4. Delivery gate (spec closure, changelog, release notes, version train) —
   depends on stages 1–3

## Test Strategy

- unit tests (vitest, fake timers, mocked `getSession`): flip-on-approve
  rebuilds turns with attribution + resumed content; deny and expired parity;
  no interval when no card is pending; no interval while streaming; in-flight
  response dropped when a stream starts; unchanged fingerprint never rebuilds.
- contract tests: none (no contract change).
- integration / overlay validation: `make verify` gate; live validation by
  re-running the v0.13.1 walkthrough step 2 and watching the owner's window
  flip without a refresh.

## Rollout And Migration

- deployment: portal image rebuild + redeploy only; no configuration,
  secrets, or schema changes.
- backward compatibility: additive client behavior against the existing
  `GET /api/v1/sessions/{id}` surface.
- rollback: revert the portal commit and redeploy — the owner-side view
  returns to refresh-to-see semantics with no data impact.
