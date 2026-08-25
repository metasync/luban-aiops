# SPEC-031: Approval Inbox and Persistent Confirmation Cards

## Status

- status: `draft`
- owner: luban-platform-team
- created: 2026-08-25
- release slice: R4 — Approval-Gated Bounded Actions
- related ADRs: none

## Summary

Make the tier_2 approval workflow end-to-end usable in the portal: confirmation
cards persist across re-login in the owner's transcript (read-only once
decided), designated approvers get a persistent approvals inbox with full
decision history, and concurrent-approver races resolve into a structured
"already decided" outcome instead of an opaque error.

## Motivation

- **Live validation of SPEC-030 (2026-08-25) exposed two blockers for the
  portal-native tier_2 flow.** First, session lists are owner-scoped
  (SPEC-022 R-1) and SPEC-030 Q-1 deliberately excluded cross-user transcript
  exposure — so a designated approver has *no surface* to discover or open an
  operator's parked session; approval works only via the gateway API (as the
  e2e scripts do). Second, confirmation frames exist only in the live SSE
  stream: `session_transcript.py` reconstructs chat text only, so a parked or
  decided card vanishes when the owner logs out and back in — observed live.
- The approval gate is the trust center of R4 ("operations and governance
  teams agree that bounded actions are sufficiently trustworthy"). A
  designated-approver workflow that cannot be discovered, disappears from the
  record, and answers races with an opaque error undermines that theme
  directly; auditability at the UI layer is the natural completion of
  SPEC-030's transparency work.
- The confirmation registry is a per-process in-memory map; durable records
  also fix restart/replica amnesia (a parked call's history survives pod
  restarts and is consistent across replicas).

## Requirements

Each requirement is stable once the spec is `approved` and carries testable acceptance criteria.

### R-1: Durable confirmation lifecycle records

Every parked confirmation and its resolution are persisted in a
session-scoped durable store owned by agent-platform (same Postgres posture
as the SPEC-016 session store), keyed by session with a random `confirm_id`.
A record carries: session id, owner username, pending calls (tool,
risk level, bridged policy action), parked-at timestamp, status
(`pending` | `approved` | `denied` | `expired`), and — once resolved —
decider username, decision, and decided-at timestamp.

Acceptance criteria:

- Parking a mutating call writes a `pending` record before the
  `confirmation_request` frame reaches the client; resolving writes the
  outcome (decider + decision + timestamp) before the `confirmation_result`
  frame is emitted.
- Records survive agent-platform pod restarts; a pending record after
  restart still answers the confirm bridge and the pending-confirmation
  endpoint.
- Records are bounded: the most recent 50 records per session are kept;
  older records are evicted oldest-first. Records live and die with their
  session (session delete removes them).
- The in-memory registry stays the hot path; durability is the source of
  truth for history and restart recovery — the two never disagree on a
  resolved outcome.

### R-2: Persistent cards in the owner transcript

The session detail surface (`GET /api/v2/sessions/{id}`, relayed by
`GET /api/v1/sessions/{id}`) includes confirmation cards reconstructed from
the durable records, in transcript order, each in its current state. A
decided card renders with its outcome (approved/denied/expired, decider,
timestamp) and is permanently read-only.

Acceptance criteria:

- An operator parks a call, logs out, logs back in, and sees the card —
  pending if undecided, or with the decision outcome if already decided.
- A card approved by a designated approver shows in the owner's transcript
  as decided-by-<approver> and read-only; it does not disappear after
  approval or after any re-login.
- Expired parked calls surface as `expired` cards rather than vanishing.
- Transcript text reconstruction (SPEC-022 R-1) is unchanged — the cards
  ride the additive confirmation surface, not the chat-text transcript.

### R-3: Approvals inbox API

Designated approvers can list parked and historical confirmations across
sessions through the gateway: `GET /api/v1/approvals/inbox` gated by a new
`approvals:list` policy action granted to `approver` and `platform-admin` in
the default bundle. Inbox items carry metadata only — session id, session
title, owner username, pending calls (tool, risk level, action), tier,
status, decider, timestamps — never the owner's transcript text, preserving
SPEC-030 Q-1's no-cross-user-transcript-exposure posture.

Acceptance criteria:

- `luban-approver` lists an operator's parked confirmation without being a
  member of that session; the item carries enough metadata to decide
  (tool, parameters payload as parked, risk level, owner).
- The inbox includes resolved history (approved/denied/expired items with
  decider and timestamps), most recent first; history is bounded to the
  last 30 days.
- Roles outside `decided_by_roles` posture (`operator`, `developer`,
  `read-only-observer`, `auditor`) get a policy 403 on the inbox action;
  the deny is audited like any action denial.
- Opening an inbox item yields the decision surface for that confirmation
  (parked-call details + approve/deny), never the owner's chat transcript.

### R-4: Race-resilient resolution semantics

Concurrent decisions resolve exactly once and everyone involved learns the
outcome. The existing single-flight claim stays; losing or late attempts get
a structured resolution response instead of an opaque error.

Acceptance criteria:

- Two approvers approving the same parked call concurrently: exactly one
  execution, exactly one `confirmation_decided` audit event (unchanged);
  the loser receives a structured `already_resolved` response carrying
  decider username, decision, and decided-at timestamp.
- A confirm attempt against a resolved record (any later time, e.g. a stale
  browser tab) returns the same structured outcome — never a 5xx, never a
  silent success, never a second execution.
- The requester's own session surface reflects the resolution: a pending
  card becomes the decided card with the approver's identity on the next
  session detail fetch.
- Deny races behave identically (first deny wins; the loser sees who
  denied and when).

### R-5: Portal approvals view and persistent cards

The portal gains an Approvals view for designated approvers and renders
owner-side cards from the durable records.

Acceptance criteria:

- Users with a decider role see an Approvals nav entry with a pending-count
  badge (poll-based refresh; no new push channel). Non-decider users do not
  see the nav entry.
- The view lists pending items first, then history; selecting a pending item
  opens the decision panel (reuse of the SPEC-030 confirmation card
  component, tier badge included); history items render read-only with the
  outcome.
- Approving from the inbox drives the same `POST /api/v1/chat/confirm`
  bridge — tier enforcement, self-approval block, audit, and
  resume-under-confirmer-token semantics are unchanged (SPEC-030 R-3).
- Owner-side transcripts render parked and decided cards from R-2 after any
  re-login; decided cards are read-only with the decider attribution.
- Vitest coverage: inbox pending/history/empty renders, badge count, race
  response handling (card flips to resolved), owner-side persisted card
  renders for pending/approved/denied/expired states.

## Non-Goals

- Multi-approver quorum / N-of-M approval semantics (single designated-approver
  decision remains the model; a future spec may extend tiers).
- Push notifications (webhooks, email, browser push) — the inbox polls.
- Cross-session bulk approve; every decision stays an explicit per-card click.
- Exposing owner transcript text to approvers — SPEC-030 Q-1's posture is
  preserved; if governance later asks for richer review context, that is a
  separate spec with its own exposure decision.
- Audit-schema changes: `confirmation_decided` enrichment from SPEC-030 is
  sufficient; the inbox is a read surface over records, not a new audit event.

## Impact

- products touched: `products/agent-platform` (durable records store,
  registry rehydration, confirm-route race response, session detail),
  `products/platform-gateway` (inbox route + relay of confirm-race
  semantics), `products/operator-portal/web-ui` (Approvals view, persisted
  cards)
- contracts touched: `shared/shared-contracts` — confirmation-record shape
  (schema or typed contract), stream schema unchanged
- identity / policy / audit / execution safety impact: new `approvals:list`
  action in the default bundle (grants: `approver`, `platform-admin`),
  synced to all bundle copies via `make sync-policy`; no change to tier
  enforcement, self-approval blocking, or the confirmer-token resume;
  no new audit event types
- living state docs to update on delivery: `docs/guides/approval-and-hitl.md`,
  `docs/guides/portal-user-guide.md`, `docs/guides/troubleshooting.md`,
  `docs/agentic-aiops-platform/authorization-matrix.md`

## Open Questions

All resolved (2026-08-25):

- OQ-1 (inbox retention) — resolved: time-window based, **30 days**; the
  inbox lists pending items plus history from the last 30 days, oldest
  aging out automatically.
- OQ-2 (expired items in history) — resolved: **yes**, expired records
  appear in the inbox history so "nobody decided in time" stays visible
  to governance.

## Changelog

- 2026-08-25: created as `draft` — folded in from the SPEC-030 live-cluster
  validation (approver had no portal surface to discover parked sessions)
  and the user's live-test findings (owner-side card lost on re-login;
  concurrent-approver outcome opacity).
- 2026-08-25: OQ-1/OQ-2 resolved — 30-day time-window retention for inbox
  history; expired items included in history.
