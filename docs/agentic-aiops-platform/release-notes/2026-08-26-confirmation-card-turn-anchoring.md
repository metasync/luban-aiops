# v0.15.0 — Confirmation Card Turn Anchoring (SPEC-033)

Date: 2026-08-26
Release type: minor (additive persisted field + wire field + portal
seeding behavior; no breaking changes)

## Summary

v0.15.0 fixes the v0.14.1 live-validation finding that a session with
several parked requests listed *every* confirmation card under the
newest turn. Each card now renders under the exchange that parked it,
including decided cards from earlier rounds.

## Root Cause

The record store is correctly session-scoped (`WHERE session_id = ...`),
so the owner window was never showing another session's requests — the
defect was anchoring. Confirmation records carried no turn correlation,
so SPEC-031's seeding path documented the compromise: "every card
anchors to the most recent turn — exact for the latest park,
approximate for older decided cards." That approximation is invisible in
single-park sessions and misleading once a session accumulates several
parks: all four approved cards from repeated live-test rounds stacked
under the newest turn group.

Meanwhile the correlation already existed at park time — both kernel
stream paths compute `turn_index = _count_user_turns(agent)` before the
turn runs, the exact convention SPEC-025 evidence groups use and the
exact index the portal's seeded turn array uses. The park write simply
never stored it.

## What Shipped

- **R-1 — persisted at park time.** `make_record` and the kernel park
  path (both the first-turn and resumed-turn streams) store the parking
  turn ordinal. The Postgres table gains an additive `turn_index
  INTEGER` column; `initialize()` runs an idempotent `ADD COLUMN IF NOT
  EXISTS` migration so clusters with a pre-spec table migrate in place
  (pre-delivery rows stay NULL). All load queries and both store
  backends round-trip the field.
- **R-2 — additive on the session-detail surface.** The confirmation
  record model and the `agent-session.schema.json` contract gain
  `turn_index` (integer, nullable, not required). Both the session
  detail and the approver inbox ride the shared model, so the field
  flows through both without surface changes.
- **R-3 — anchored seeding.** The portal's transcript seeding places
  each card under `turns[record.turn_index]` when the ordinal is in
  range; null, absent, or out-of-range ordinals fall back to the legacy
  newest-turn anchoring, so pre-delivery records render exactly as
  today. Pending cards keep their existing behavior — anchored to the
  parking turn, driving `confirmationPending` there.

## Validation

- `make verify` green: agent-platform pytest (including new store
  round-trip, legacy-row mapping, in-place migration, park-path ordinal,
  and session-detail tests), portal vitest (three new anchoring tests:
  per-exchange anchoring, pending anchoring, legacy fallback), tsc
  clean, kustomize builds, and the version lockstep check.

## Notes

- Legacy rows are never rewritten: the correlation is only knowable at
  park time, and the fallback keeps them visible exactly as before.
- The approver inbox layout is unchanged — inbox cards are not anchored
  to a transcript at all.
