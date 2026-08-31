# SPEC-047 Implementation Plan

## Approach

One UX iteration on the SPEC-046 Summary tab plus the one additive API
dimension that makes it complete. Backend: audit-service gains an
`outcome` filter dimension on its three read routes (events, summary,
export) across both store backends, schema-verbatim; platform-gateway
forwards the parameter on its existing pass-through routes (R-1).
Portal: the pinned vocabulary gains `OUTCOMES` behind the same drift
guard and an outcome select joins the shared toolbar (R-2); the
Summary tab is rebuilt so every aggregate value drills into the
Events tab under merged filters (R-3), every bucket row carries
proportion (R-4), the bucket tables fold into collapsible sections
(R-5), and the headline numbers become a statistic row (R-6). No new
routes, no new gates, no new policy actions, no new event types; both
contract schemas keep their shapes. Version lockstep to 0.29.0.

## Workstreams

### W-1: Outcome dimension in audit-service (R-1)

- `services/audit_store.py`: the shared WHERE-builder that SPEC-046
  extracted from `query()` gains the `outcome` equality predicate
  (Postgres: parameterized on the envelope column, same posture as
  `event_type`/`service`); the in-memory store's `_matches` pass
  gains the same field check. Because both `summarize()` and the
  export route already ride that builder/`_matches`, the dimension
  reaches all three read surfaces with no per-route special casing.
  The store filter dataclass gains `outcome: str | None`.
- `api/routes/query.py`, `summary.py`, `export.py`: each gains an
  optional `outcome` query parameter validated against the four
  schema enum values (`allow`, `deny`, `success`, `error`) — invalid
  values are a 422 under the existing validation posture — and pass
  it into the store filters. Caller auth, log lines, and metrics are
  untouched (the read is already recorded).
- Tests (`test_audit_store.py`, `test_reporting.py`,
  `test_routes.py`): outcome filtering on events/summary/export in
  both backends, in-memory ↔ fake-driver Postgres parity, invalid
  outcome → 422, absent outcome → unchanged behavior (the dimension
  is additive).

### W-2: Gateway outcome pass-through (R-1)

- platform-gateway `api/routes/audit.py`: the existing events /
  summary / export handlers already forward the filter params;
  `outcome` joins the forwarded set on all three. Gate stays the
  existing `audit:read`; error mapping and timeouts unchanged.
- Tests: route-inventory assertion gains the `outcome` parameter
  where the inventory pins param names; one pass-through test
  asserts the parameter reaches the upstream request; policy-matrix
  test unchanged in shape (no new cells).

### W-3: Portal vocabulary and toolbar (R-1, R-2)

- `views/audit/constants.ts`: `OUTCOMES` = the four schema enum
  values, beside `EVENT_TYPES` / `EMITTER_SERVICES`.
- `views/audit/__tests__/constants.test.ts`: the existing drift
  guard extends to assert `OUTCOMES` equals the
  `audit-event.schema.json` `outcome` enum.
- `AuditView.tsx`: the shared toolbar gains an outcome select
  ("all outcomes" placeholder) in the same pinned-vocabulary posture;
  the `Filters` state, `filterParams()`, and the export URL all pick
  up the `outcome` field.

### W-4: Summary tab rebuild (R-3…R-6)

- `AuditSummaryPanel.tsx` rebuild:
  - **Statistic row (R-6):** antd `Statistic` cards — total events
    plus the four decision-chain steps, zeros as 0, each chain step
    clickable (R-3).
  - **Bucket tables (R-4):** each row gains a percentage column
    (one decimal place, deterministic rounding of
    `count / total_events`) and a thin antd `Progress` bar at the
    same percentage (neutral color, no status semantics). When
    `total_events` is zero the panel renders its empty posture and
    no division is attempted.
  - **Collapse (R-5):** the four tables live in antd `Collapse`
    panels (By event type, By outcome, By service, Top actors),
    header = section title + section total, all expanded by
    default, state per-render (no persistence).
  - **Drill-down (R-3):** every bucket row and every chain step is
    a keyboard-reachable interactive element carrying its target
    filter (`event_type` / `service` / `outcome` / `username`, or
    the chain step's event type); invoking it calls one
    `onDrilldown(patch)` callback prop.
- `AuditView.tsx`: `onDrilldown` merges the patch into the current
  filters (merge, never reset — Q-3), switches to the Events tab,
  and triggers one refresh; the Events table's existing empty-state
  and error postures cover the result.
- Vitest: percentage math + zero-total guard, drill-down merge
  semantics (preserves time range, replaces only the targeted
  dimension), chain-step targets, collapse default-expanded,
  outcome select present in the toolbar; zero-deprecation guard
  green.

### W-5: House train (R-7 + release)

- Version lockstep 0.28.0 → 0.29.0 (VERSION, pyproject.toml,
  metadata.py, `__init__.py`, uv.lock across products); `make
  verify` before **and** after `make build`; `make deploy`.
- Browser live check on the canonical deployment: drill-down
  landings from each section incl. outcome (with a time range set,
  to prove the merge), zero-count navigation, proportion math
  against the displayed total, collapse behavior, and the
  operator/observer denial regression on the audit surface.
- Living-state docs per spec.md Impact (`portal-user-guide.md`;
  `configuration-reference.md` and `authorization-matrix.md` only
  if implementation adds a knob or enumerates filter dimensions);
  CHANGELOG 0.29.0 + release note + index; commit → scan gate →
  tag v0.29.0 → push (never combined); final clean rebuild +
  redeploy.

## Sequencing

1. **W-1** first — the store extension pins the outcome semantics
   before any consumer relies on them.
2. **W-2** next — the gateway forwards what W-1 accepts.
3. **W-3** after W-2 — the portal vocabulary and toolbar consume
   the finalized dimension.
4. **W-4** after W-3 — the Summary rebuild uses the pinned
   vocabulary and the wired filter state.
5. **W-5** last, per the house train.

## Risks

- **Outcome index absence.** The Postgres store indexes the SPEC-013
  hot columns; `outcome` may not be indexed, so an outcome-only
  filter scans within the retention window. Mitigation: acceptable
  at dev-cluster scale (same recorded posture as the `service`
  filter in the SPEC-046 plan); no index migration in this slice.
- **Drill-down state surprise.** A merged filter that the user did
  not type can feel invisible. Mitigation: R-2 requires every
  drill-down target to surface in the shared toolbar, and clearing
  stays explicit there; pinned by a vitest assertion.
- **Percentage rounding drift between client tests and display.**
  Mitigation: one shared formatter in `AuditSummaryPanel`
  (one decimal place, deterministic rounding) exercised by tests —
  no per-call inline math.
- **Collapse swallowing the overview.** Folding is opt-in per
  render; all panels default expanded (R-5), so the as-shipped view
  is byte-for-byte the overview, just with fold affordances.
- **Scope creep toward dashboards.** Colors, trends, and exports of
  the aggregate remain parked per spec.md; the Summary tab stays a
  facts-only rendering of one aggregate payload.
