# v0.13.0 — Approval Inbox and Persistent Confirmation Cards

Date: 2026-08-25
Release type: minor (new read surface + durable records; no breaking changes)

## Summary

v0.13.0 delivers SPEC-031 — the tier_2 approval workflow becomes end-to-end
usable in the portal: confirmation cards persist across re-login in the
owner's transcript, designated approvers get a cross-session approvals inbox
with decision history, and concurrent-approver races resolve into a
structured outcome instead of an opaque error.

- **Durability becomes the source of truth for history.** Every parked
  confirmation and its resolution persist in Postgres on the shared
  `AGENT_STATE_DB_URL` posture: the record is written before the
  `confirmation_request` frame reaches the client and the outcome before
  `confirmation_result` flows. Records are bounded (most recent 50 per
  session, evicted oldest-first), cascade-deleted with their session, and
  stale pendings flip to `expired` on restart (a parked kernel reply never
  survives its process). The in-memory registry stays the hot path, with
  startup + on-miss rehydration across restarts and replicas.
- **Owner-side cards survive everything.** The session detail grows an
  additive `confirmations` array reconstructed from the durable records,
  relayed by the gateway session routes. Cards survive re-login, page
  reloads, pod restarts, and replica boundaries; decided cards render
  read-only with decider attribution, pending cards stay actionable,
  expired cards surface instead of vanishing. Transcript text
  reconstruction is unchanged — cards ride the additive surface.
- **Approvers get an inbox.** `GET /api/v1/approvals/inbox` (backed by
  `GET /api/v2/confirmations`) is gated by a new `approvals:list` policy
  action granted to `approver` and `platform-admin` (bundle rule
  `allow-approvers-approvals-list`). Items are metadata only — session,
  owner, parked calls, outcome — never the owner's transcript text,
  preserving SPEC-030 Q-1's no-cross-user-transcript-exposure posture.
  The inbox lists pending items plus the last 30 days of history
  (expired items included) most recent first.
- **Races resolve, they don't error.** A decision against an
  already-resolved confirmation answers `409 already_resolved` carrying
  the winner's status, decider, decision, and decided-at timestamp;
  exactly one execution and one audit event per confirmation. Unknown
  confirm ids keep 404.
- **Portal Approvals view.** Decider-role users see an Approvals nav
  entry with a pending-count badge (single shared 30s/focus poll); the
  view lists pending items first, then history, reuses the SPEC-030
  confirmation card component, and decides through the existing
  `chat/confirm` bridge — tier enforcement, self-approval blocking,
  audit, and resume-under-confirmer-token semantics unchanged. Losing a
  race flips the card to the winner's outcome in both the inbox and the
  owner's chat.

## Change Set

### Added — SPEC-031: inbox + durable cards

- Agent-platform: `confirmation_records.py` Postgres-backed store
  (park/resolve/expire, cap 50 evict-oldest, cascade on session delete),
  park/resolve wiring in the runtime kernel and v2 routes, registry
  rehydration, additive `confirmations` on session detail,
  `GET /api/v2/confirmations` (cross-session, 30-day window,
  metadata-only).
- Platform-gateway: `GET /api/v1/approvals/inbox` route with
  `enforce_policy(approvals:list)` + relay; structured 409 passthrough
  on `chat/confirm`.
- Default bundle: `allow-approvers-approvals-list` rule; synced across
  packaged and overlay copies.
- Shared contracts: confirmation-record shape in
  `agent-session.schema.json`.
- Portal: `ApprovalsView` (pending/history, badge, 30s/focus polling),
  `api/approvals.ts`, session-detail confirmation seeding into the turn
  timeline, `StreamOpenError.detail` + `alreadyResolvedDetail` race
  handling, decider attribution on resolved cards.

### Changed

- Confirm races answer `409 already_resolved` (structured detail)
  instead of an opaque error; the portal flips losing cards to the
  winner's outcome.
- `mutating-demo.sh` HITL leg asserts the three SPEC-031 surfaces:
  owner session-detail card, approver inbox item with outcome, and the
  second-approve `already_resolved` 409.

## Validation

- agent-platform and platform-gateway suites green (store write order,
  cap/eviction, cascade, rehydration, inbox window/ordering/scoping,
  race semantics, relay passthrough).
- Portal vitest green (inbox pending/history/empty, badge, race-response
  handling, owner-side persisted card for all four states) plus
  `tsc --noEmit`.
- `make sync-policy` + `make validate-policy` across all bundle copies;
  `make verify` for the full gate.
- Live cluster: e2e HITL leg with the three SPEC-031 assertions passed;
  browser validation covered approver inbox decide + history
  attribution, operator no-Approvals-nav, and the owner's durable card
  after re-login.

## Rollback

The surfaces are additive: reverting removes the inbox route, the
`approvals:list` rule, and the `confirmations` field; live HITL
confirmation keeps working through the in-memory registry exactly as
before SPEC-031.
