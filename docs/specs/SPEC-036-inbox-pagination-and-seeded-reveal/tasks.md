# SPEC-036 Tasks

## R-1 seeded-transcript reveal

- [ ] `transcript.ts`: `seedRevealIndex` helper + unit tests.
- [ ] `ChatView.tsx`: cold-seed reveal state, timer, switch-cancel,
      render wiring (arrival wins).

## R-2 split inbox store queries

- [ ] Protocol: `load_pending_inbox` / `load_inbox_history`.
- [ ] Postgres backend: pending/history/count SQL.
- [ ] Memory backend parity.
- [ ] Store tests adapted + pagination/retention cases.

## R-3 paginated inbox API

- [ ] `GET /api/v2/confirmations`: query params + split response.
- [ ] Route tests: shape, default page, explicit page.

## R-4 gateway pass-through

- [ ] Route params + split log counts.
- [ ] `gateway_service` / `agent_client` forwarding.
- [ ] Proxy tests: shape + param forwarding + matrix.

## R-5 server-driven History tab

- [ ] `api/approvals.ts`: new query/response shape.
- [ ] `useApprovalsInbox`: split state, offset-aware refresh,
      `setPageOffset`, decide/race move-to-history.
- [ ] `ApprovalsView`: server page render + pager.
- [ ] Portal tests updated (hook flows + layout/pager).

## Verification & release

- [ ] Portal suite green; agent-platform suite green; gateway suite
      green.
- [ ] `make verify` green; version lockstep 0.18.0.
- [ ] Docs: guide note, CHANGELOG, release notes, spec status flip,
      specs README, roadmap row + narrative, release-notes index.
- [ ] Commit train, build, deploy, smoke (inbox shape via gateway),
      tag v0.18.0, push gate, push.
