# Audit Summary Drill-Down and Readability (v0.29.0)

Date: 2026-08-31

Delivers **SPEC-047** — one UX iteration on the SPEC-046 audit Summary
tab plus the one additive API dimension that makes it complete. The
Summary becomes a page you can *act on*: every aggregate value drills
into the Events tab, every bucket row carries its proportion, the
sections fold on demand, and the headline numbers sit in a statistic
row. No new routes, no new gates, no new policy actions, no new event
types; both contract schemas keep their shapes.

## What changed

### Outcome filter dimension (backend)

- audit-service gains an optional `outcome` query parameter on its
  three read routes — `GET /api/v1/audit/events`,
  `GET /api/v1/audit/summary`, and `GET /api/v1/audit/export` —
  validated against the four contract enum values (`allow`, `deny`,
  `success`, `error`); anything else is a 422 under FastAPI's existing
  validation posture.
- The predicate lives in the shared WHERE-builder that SPEC-046
  extracted, so both store backends (in-memory and Postgres) and all
  three read surfaces inherit the dimension with no per-route special
  casing; the summary's window echo carries the active outcome.
- platform-gateway forwards `outcome` on its existing pass-through
  routes; the gate stays `audit:read`, error mapping and timeouts are
  untouched, and the policy matrix gains no cells.

### Portal vocabulary and toolbar

- The pinned filter vocabulary gains `OUTCOMES` beside `EVENT_TYPES` /
  `EMITTER_SERVICES`; the vitest drift guard reads the contract schema
  enum and asserts equality, so the new dimension can never silently
  drop out of the selects.
- The shared toolbar gains the outcome select ("all outcomes"
  placeholder) in the pinned-vocabulary posture; it drives both tabs
  and the CSV export like the existing dimensions.

### Summary tab rebuild

- **Statistic row:** total events plus the four decision-chain steps
  (`confirmation_decided → execution_requested → execution_completed →
  execution_rejected`) as antd statistic cards; zeros render as 0.
- **Drill-down:** every statistic card, bucket row, and chain step is a
  keyboard-reachable control that lands on the Events tab with its
  value merged into the current filters — merge, never reset, so the
  time range and the other dimensions survive; zero-count buckets
  still navigate.
- **Proportion:** each bucket row shows its share of the total as a
  one-decimal percentage and a thin neutral progress bar, computed
  client-side from the existing payload by one shared formatter; a
  zero total renders the empty posture without division.
- **Collapse:** the four bucket sections (By event type, By outcome,
  By service, Top actors) fold per render — all expanded by default,
  section total in the header, statistic row outside the folding.

## Validation

- audit-service: 137 tests (outcome filtering on events/summary/export
  in both backends, in-memory ↔ fake-driver Postgres parity, invalid
  outcome → 422, absent outcome → unchanged behavior).
- platform-gateway: 297 tests (outcome pass-through reaches the
  upstream request on all three routes; inventory/matrix shapes
  unchanged).
- operator-portal: 259 tests (drift guard, outcome select, drill-down
  merge semantics incl. time-range preservation and zero-count
  navigation, percentage math, zero-total guard, collapse
  default-expanded).
- Version lockstep 0.29.0 validated across all products and the
  portal; `make verify` green before and after `make build`.
