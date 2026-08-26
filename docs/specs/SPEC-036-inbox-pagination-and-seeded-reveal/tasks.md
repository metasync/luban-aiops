# SPEC-036 Tasks

## R-1 seeded-transcript reveal

> Reverted in the 0.18.1 patch after live-check feedback; boxes below
> remain ticked as the historical delivery record.

- [x] `transcript.ts`: `seedRevealIndex` + `seedRevealDelay` helpers
      + unit tests.
- [x] `ChatView.tsx`: cold-seed cascade state, timer, switch-cancel,
      TurnGroup `revealDelayMs` stagger, render wiring (arrival wins).

## R-2 split inbox store queries

- [x] Protocol: `load_pending_inbox` / `load_inbox_history`.
- [x] Postgres backend: pending/history/count SQL.
- [x] Memory backend parity.
- [x] Store tests adapted + pagination/retention cases.

## R-3 paginated inbox API

- [x] `GET /api/v2/confirmations`: query params + split response.
- [x] Route tests: shape, default page, explicit page.

## R-4 gateway pass-through

- [x] Route params + split log counts.
- [x] `gateway_service` / `agent_client` forwarding.
- [x] Proxy tests: shape + param forwarding + matrix.

## R-5 server-driven History tab

- [x] `api/approvals.ts`: new query/response shape.
- [x] `useApprovalsInbox`: split state, offset-aware refresh,
      `setPageOffset`, decide/race move-to-history.
- [x] `ApprovalsView`: server page render + pager.
- [x] Portal tests updated (hook flows + layout/pager).

## Verification & release

- [x] Portal suite green; agent-platform suite green; gateway suite
      green.
- [x] `make verify` green; version lockstep 0.18.0.
- [x] Docs: guide note, CHANGELOG, release notes, spec status flip,
      specs README, roadmap row + narrative, release-notes index.
- [x] Commit train, build, deploy, smoke (inbox shape via gateway),
      tag v0.18.0, push gate, push.
