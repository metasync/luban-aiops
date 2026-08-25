# SPEC-033: Confirmation Card Turn Anchoring

## Status

- status: `delivered`
- owner: luban-platform-team
- created: 2026-08-26
- release slice: R4 — Approval-Gated Bounded Actions
- related ADRs: none

## Summary

Confirmation records persist the ordinal of the user turn that parked them,
the session-detail surface carries it, and the portal's transcript seeding
anchors each confirmation card under the exchange that created it — instead
of stacking every card under the newest turn.

## Motivation

- **v0.14.1 live validation (2026-08-26) exposed the misanchoring.** After
  the SPEC-032 live sync landed, an operator re-ran the bounded-restart demo
  several times in the same session and watched the owner window: every
  approval surfaced correctly, but the transcript listed *all* approved
  requests — four decided cards stacked under the newest turn group — rather
  than showing each card under the exchange that parked it. The store is
  correctly session-scoped (`WHERE session_id = ...`); the defect is purely
  anchoring.
- **Records carry no turn correlation today.** SPEC-031's seeding path
  documents the compromise: "Records carry no turn index, so every card
  anchors to the most recent turn — exact for the latest park, approximate
  for older decided cards." That approximation is invisible in single-park
  sessions and misleading in multi-park sessions.
- **The correlation already exists at park time.** Both kernel stream paths
  compute `turn_index = _count_user_turns(agent)` before the turn runs —
  the exact convention SPEC-025 evidence groups use, and the exact index the
  portal's seeded turn array uses. The park write simply never stored it.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable
acceptance criteria.

### R-1: Turn ordinal persisted at park time

The durable confirmation record stores the ordinal of the user turn under
which the park occurred, using the same convention as persisted evidence
(`_count_user_turns`, 0-based over the seeded turn timeline).

Acceptance criteria:

- A parked record written by either stream path (first turn or resumed turn)
  carries its `turn_index`; a round-trip through the Postgres and in-memory
  stores returns it unchanged.
- The additive column never breaks the existing store behaviors: per-session
  cap eviction, inbox window, single-resolution claim, and startup sweep all
  keep their current semantics.
- A store write failure still degrades to live-only cards (best-effort
  persistence unchanged from SPEC-031 R-1).

### R-2: Session detail carries the ordinal

The session-detail `confirmations` records expose `turn_index` as an
additive nullable field.

Acceptance criteria:

- `GET /api/v2/sessions/{id}` records include `turn_index` (integer ≥ 0)
  for records parked after delivery, and `null` for records that predate it.
- The inbox surface (`GET /api/v2/confirmations`) is unaffected in shape
  beyond carrying the same additive field through its shared record model.
- The `agent-session.schema.json` contract gains the additive property;
  nothing existing is re-typed or removed.

### R-3: Cards anchor to their own turn

The portal's transcript seeding places each confirmation card under the
turn group that parked it.

Acceptance criteria:

- A session with multiple decided records renders each card under its own
  turn group; the newest turn no longer accumulates the session's history.
- A record with a null, missing, or out-of-range `turn_index` falls back to
  the pre-spec anchoring (newest turn, or the synthetic turn for an empty
  transcript), so pre-delivery records keep rendering exactly as today.
- Pending-record behavior is unchanged: the pending card still anchors to
  its parking turn and still drives `confirmationPending` on that turn.

## Non-Goals

- Rewriting pre-delivery records to recover their turn ordinals: the
  correlation is only knowable at park time; legacy rows fall back.
- Changing the approver inbox layout: inbox cards are not anchored to a
  transcript at all.
- Any change to decision mechanics, TTLs, or the SPEC-032 poll.

## Impact

- products touched: `products/agent-platform` (record store, kernel park
  path, v2 schemas), `products/operator-portal/web-ui/app` (transcript
  seeding)
- contracts touched: `shared/shared-contracts/schemas/agent-session.schema.json`
  (additive `turn_index` on confirmation records)
- identity / policy / audit / execution safety impact: none (display-only
  correlation on existing records)
- living state docs to update on delivery: CHANGELOG, release notes,
  `docs/guides/approval-and-hitl.md` (card placement note)

## Open Questions

- none.

## Changelog

- 2026-08-26: created as `draft`, drafted directly from the v0.14.1 live
  validation finding (all approved requests stacked under the newest turn).
- 2026-08-26: delivered in the 0.15.0 train — the park path stores the
  parking turn ordinal (additive `turn_index` column with in-place
  migration), the session-detail/inbox record model and the
  `agent-session.schema.json` contract carry it additively, and the
  portal's transcript seeding anchors each card under its parking turn
  with the legacy newest-turn anchoring kept as the fallback for
  pre-delivery records.
