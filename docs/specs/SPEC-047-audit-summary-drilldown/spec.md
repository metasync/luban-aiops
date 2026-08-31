# SPEC-047: Audit Summary Drill-Down and Readability

## Status

- status: `delivered`
- owner: luban-platform-team
- created: 2026-08-31
- approved: 2026-08-31
- delivered: 2026-08-31
- release slice: R5 — Hardening and External Consumption (ninth R5
  slice, target v0.29.0)
- related ADRs: none (lineage: UX iteration on the SPEC-046 Summary
  tab, promoted memo-free from the 2026-08-31 operator review of the
  v0.28.0 live check; extends SPEC-013 durable audit trail, SPEC-046
  audit reporting and export)

## Summary

SPEC-046 shipped the Summary tab: a total line, the SPEC-037
decision-chain strip, and four bucket tables (by event type, by
outcome, by service, top actors) rendered from one deterministic
aggregate fetch. An operator UX review of the live v0.28.0 surface
identified four flat spots that together make the summary a static
dead-end rather than an investigation hub:

- **No drill-down.** The auditor's real workflow is "spot an anomaly
  in the aggregate, then inspect the raw envelopes behind it." Today
  that means memorizing a bucket value, switching tabs, and
  re-entering the filter by hand — and `outcome` cannot even be
  filtered, because the query surface has no outcome dimension.
- **Counts without proportion.** Rows show raw counts only; across a
  20-row event-type table the relative weight of each bucket is not
  visible at a glance.
- **Flat hierarchy.** The total line is prose and the decision-chain
  numbers are inline text; the headline numbers do not read as
  headline numbers.
- **Fixed layout.** All four tables render unconditionally in a
  rigid 2×2 grid; an auditor who has finished with a section cannot
  fold it away, and the layout cannot accommodate a future section
  without a redesign.

The review explicitly adjudicated the multi-tab alternative (one tab
per report): rejected. The summary sections are complementary facets
of one filtered window, not mutually exclusive contexts; per-report
tabs would nest a second tab row inside the existing Events/Summary
tabs, hide correlated data behind clicks, and destroy the
at-a-glance overview the summary exists to provide. Collapsible
sections on one page preserve the overview while giving the auditor
control.

This slice makes every aggregate value clickable into the Events
tab, adds proportion (percentage + bar) to every bucket row, promotes
the headline numbers to a statistic row, and wraps the bucket tables
in collapsible sections. It adds exactly one additive API dimension —
an `outcome` filter on the existing audit routes — to make outcome
drill-down possible. The slice introduces **no new policy actions
and no new audit event types**; the auditor stays read-only and the
summary remains facts-only.

## Requirements

### R-1: Outcome filter dimension on the existing audit routes

Audit-service adds `outcome` as a filter dimension to the existing
read surface, verbatim against the shared schema:

- `GET /api/v1/audit/events`, `GET /api/v1/audit/summary`, and
  `GET /api/v1/audit/export` each accept an optional `outcome`
  query parameter whose legal values are exactly the
  `audit-event.schema.json` `outcome` enum (`allow`, `deny`,
  `success`, `error`); any other value is a 422 under the existing
  validation posture.
- Both store backends implement it: PostgreSQL as an equality
  predicate on the `outcome` envelope column (same parameterized
  posture as `event_type`/`service`), the in-memory store as the
  same `_matches` pass. The dimension applies to summary aggregates
  and export rows exactly as it applies to events — no special
  casing.
- Platform-gateway forwards the parameter on its existing audit
  pass-through routes; the gate stays the existing `audit:read`
  action — no policy-bundle changes, no new audit event types. The
  route inventory and policy-matrix tests keep pinning the same
  routes and cells.
- Portal filter vocabulary gains one pinned constant `OUTCOMES`
  (the four schema enum values) beside `EVENT_TYPES` and
  `EMITTER_SERVICES`, guarded by the same vitest drift-guard
  pattern: the test reads `audit-event.schema.json` and asserts
  equality, so a future outcome value can never silently drop out
  of the filter or the drill-down targets.

### R-2: Outcome control in the shared toolbar

The Audit view's shared toolbar (the SPEC-046 one that drives both
tabs and the export) gains an `outcome` select built on `OUTCOMES`
("all outcomes" placeholder), in the same pinned-vocabulary posture
as the event-type and service selects. The drill-down state (R-3)
must be visible in the toolbar — a programmatically applied filter
that the toolbar cannot show or clear is forbidden.

### R-3: Drill-down from every aggregate value

Every aggregate on the Summary tab becomes clickable and lands on
the Events tab with the corresponding filter merged into the
current filter state:

- **Bucket rows.** Clicking a row in By event type sets
  `event_type`; By service sets `service`; By outcome sets
  `outcome` (R-1); Top actors sets `username`. All other current
  filters (including the time range) are preserved — drill-down
  narrows, it does not reset.
- **Decision-chain steps.** Clicking a step statistic sets
  `event_type` to the corresponding chain event type
  (`confirmation_decided`, `execution_requested`,
  `execution_completed`, `execution_rejected`), under the same
  merge semantics.
- **Landing behavior.** A drill-down switches to the Events tab,
  applies the merged filters, and triggers one refresh; the Events
  table's existing empty-state and error postures cover the result
  unchanged. Drill-down never fetches anything new — it reuses the
  existing events query with one more filter.
- **Accessibility.** Every clickable value is a real interactive
  element (keyboard reachable, `Enter`/`Space` operable, labelled
  by bucket name and section); hover affordance only on top of
  that, never instead.
- **Guard.** Drill-down targets with a zero count still navigate —
  a zero bucket is a fact the auditor may want to confirm against
  the trail; the Events tab's existing "no events match" state is
  the answer.

### R-4: Proportion on every bucket row

Each bucket row in the four tables shows, beside the count:

- The percentage of `total_events` from the same summary payload
  (one decimal place, deterministic rounding), and
- A thin inline progress bar at that same percentage (antd
  `Progress`, neutral color, no status semantics).

Both are computed client-side from the existing payload — no API
change. When `total_events` is zero the panel renders the existing
empty posture; no row renders and no division is attempted.

### R-5: Collapsible sections, single page

The Summary tab keeps one scrollable page (no second tab row) and
gains section folding:

- The four bucket tables live in antd `Collapse` panels — By event
  type, By outcome, By service, Top actors — each panel header
  carrying the section title and the section's total event count.
- All panels are expanded by default; folding is an auditor
  convenience, never a default hide. Panel state is per-render
  (no persistence) — the summary is an ephemeral surface (the
  SPEC-046 Q-1 posture).
- The statistic row (R-6) sits above the panels, outside the
  folding, so the headline numbers are always visible.

### R-6: Headline statistic row

The prose total line and the inline decision-chain strip are
replaced by one statistic row (antd `Statistic` cards):

- Total events matching the current filters;
- The four SPEC-037 decision-chain steps
  (`confirmation_decided` → `execution_requested` →
  `execution_completed` / `execution_rejected`) with their counts,
  zeros rendered as 0 (an absent event type is a fact, not an
  error — the SPEC-046 posture), and each step clickable per R-3.

Facts only: no prose, no charts, no interpretation — the SPEC-046
facts-only invariant carries over untouched.

### R-7: Living-state docs and release train

- `docs/guides/portal-user-guide.md` — the Audit view Summary tab
  section: the statistic row, drill-down behavior, proportion
  display, collapsible sections, and the new outcome filter.
- `docs/guides/configuration-reference.md` — no new knobs expected;
  touch only if implementation adds one.
- `docs/agentic-aiops-platform/authorization-matrix.md` — no
  matrix change expected (existing `audit:read` cells); touch only
  to record the outcome dimension if the matrix text enumerates
  filter dimensions.
- CHANGELOG 0.29.0 entry + release note + release-notes index;
  version lockstep; `make verify` green before and after
  `make build`; live check on the canonical deployment (drill-down
  landings incl. outcome, zero-count guard, proportion math,
  collapse behavior, operator/observer denial regression).

## Design Decisions

Drafted memo-free per the SPEC-042/045/046 precedent; the
adjudications are recorded here:

- **Q-1: Per-report tabs or one page?** **Resolved: one page with
  collapsible sections; per-report tabs rejected.** The sections
  are facets of one filtered window, and the auditor's core task is
  correlating them (error outcomes × service × actor); tabs would
  nest a second tab row inside Events/Summary, hide correlated
  data, and trade one overview for five clicks. Collapse keeps the
  overview default and adds folding only where the auditor wants
  it. Tabs become justified only if the report family grows beyond
  roughly six sections (promotion trigger below).
- **Q-2: Outcome drill-down without an outcome filter.**
  **Resolved: add `outcome` as an additive dimension on the
  existing events/summary/export routes.** A client-side-only
  outcome drill-down is impossible (the events page cannot filter
  what the API cannot express), and skipping outcome would leave
  one of the four tables undrillable — precisely the table
  governance most often investigates (`deny`/`error`). The
  dimension is verbatim against the shared schema enum and reuses
  every existing posture; no new route, no new gate.
- **Q-3: Drill-down filter semantics.** **Resolved: merge, do not
  reset.** Drill-down narrows the current view — a time-windowed
  summary must drill into the same window. Resetting would silently
  widen the scope and contradict the summary the auditor clicked
  from. Clearing stays explicit via the toolbar.
- **Q-4: Proportion representation.** **Resolved: percentage +
  neutral inline bar, client-side only.** Counts alone do not
  convey relative weight across a 20-row table; a bar per row is
  the minimal honest encoding. Color semantics (e.g. red for
  `error` rows) are deliberately excluded — the Events table
  already owns outcome tagging, and the summary stays facts-only.
- **Q-5: Version target.** **Resolved: v0.29.0 (minor).** The
  outcome filter dimension is additive API capability, so semver
  asks for a minor even though the slice is otherwise portal UX
  work.

## Invariants preserved

- No new policy actions, no new audit event types; deny-by-default
  and the auditor read-only invariant are unchanged — drill-down
  rides the existing `audit:read` query exactly as today.
- The audit event vocabulary and envelope shape are untouched;
  `audit-event.schema.json` gains no values (the portal's new
  `OUTCOMES` constant consumes the existing enum).
- `audit-summary.schema.json` is untouched — the R-1 `outcome`
  filter reaches the summary via the existing window echo (null
  fields omitted), no new response fields.
- The summary remains facts-only: deterministic aggregates over
  stored envelopes, no prose layer, no LLM involvement, no
  interpretation.
- Drill-down never fetches new endpoints; it re-applies the
  existing events query under one more filter.

## Impact

- `products/audit-service` — `outcome` dimension on events query,
  summary, and export (both store backends) + tests.
- `products/platform-gateway` — parameter pass-through on existing
  audit routes + route-inventory/policy-matrix test updates.
- `products/operator-portal/web-ui` — Summary tab rebuild per
  R-2…R-6 (`AuditView.tsx`, `AuditSummaryPanel.tsx`, `constants.ts`
  + drift guard) + vitest coverage.
- `docs/guides/portal-user-guide.md` — Summary tab documentation.
- contracts touched: none changed — `audit-event.schema.json` and
  `audit-summary.schema.json` keep their shapes; the policy bundle
  is untouched.

## Parked / promotion triggers

- **Time-bucketed trends** (per-day volumes, sparklines) — still
  deferred per SPEC-046 D6; promote on the first governance ask for
  a trend the bucket tables cannot express, and give it its own tab
  when it lands.
- **Summary CSV export** (exporting the aggregate itself) — parked;
  promote on the first compliance ask, alongside an adjudication of
  filename and column layout.
- **Per-report tabs** — parked behind Q-1; promote only if the
  report family grows beyond roughly six sections.
- **Bucket color semantics** — parked behind Q-4; promote only with
  a deliberate visual-language decision covering the Events table
  too.

## Changelog

- 2026-08-31: created as `draft`, promoted memo-free from the
  operator UX review of the v0.28.0 Summary tab live check (the
  multi-tab alternative adjudicated and rejected, recorded in Q-1);
  pending operator approval.
- 2026-08-31: operator approved the draft (`draft` → `approved`)
  with no requirement changes; delivery proceeds under the house
  train as v0.29.0.
- 2026-08-31: delivered as v0.29.0 with no requirement changes —
  outcome dimension on the three audit read routes in both store
  backends (137 audit-service tests, 297 gateway tests), `OUTCOMES`
  behind the drift guard plus the toolbar select, Summary rebuilt
  (statistic row, drill-down under merged filters, share column,
  default-expanded collapse; 259 portal tests); the browser live
  check on the canonical deployment passed all twelve scenarios
  incl. time-range-preserving drill-down, zero-count navigation,
  outcome end-to-end, collapse behavior, and the operator denial
  regression.
