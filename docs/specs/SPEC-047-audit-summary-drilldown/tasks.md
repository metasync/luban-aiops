# SPEC-047 Tasks

## R-1: Outcome dimension on the existing audit routes (W-1, W-2)

- [x] `schemas/audit.py`: `AuditQuery` gains `outcome: Outcome | None`
      (the existing `Outcome` Literal — invalid values are a 422
      under FastAPI's existing validation posture)
- [x] `services/audit_store.py`: `_filter_clause` gains the
      `outcome = %(outcome)s` predicate; `_matches` gains the same
      field check — summarize and export ride both paths, no
      per-route special casing
- [x] `api/routes/query.py`, `summary.py`, `export.py`: optional
      `outcome` parameter validated by the `Outcome` Literal, passed
      into `AuditQuery`; auth, log lines, and metrics untouched
- [x] Tests: outcome filtering on events/summary/export in both
      backends, in-memory ↔ fake-driver Postgres parity, invalid
      outcome → 422, absent outcome → unchanged behavior
- [x] Gateway `api/routes/audit.py`: `outcome` joins `_filter_params`
      and the three handler signatures; gate, error mapping, and
      timeouts unchanged
- [x] Gateway tests: outcome pass-through reaches the upstream
      request on all three routes; route-inventory/policy-matrix
      updates where param names are pinned (no new matrix cells)

## R-2: Outcome control in the shared toolbar (W-3)

- [x] `views/audit/constants.ts`: `OUTCOMES` (the four schema enum
      values) beside `EVENT_TYPES` / `EMITTER_SERVICES`
- [x] `views/audit/__tests__/constants.test.ts`: drift guard asserts
      `OUTCOMES` equals the `audit-event.schema.json` outcome enum
- [x] `AuditView.tsx`: `Filters` state + `filterParams()` + export
      URL gain `outcome`; toolbar gains the outcome select ("all
      outcomes" placeholder) in the pinned-vocabulary posture

## R-3: Drill-down from every aggregate value (W-4)

- [x] `AuditSummaryPanel.tsx`: every bucket row and every
      decision-chain step is a keyboard-reachable interactive
      element carrying its target filter patch (`event_type` /
      `service` / `outcome` / `username`, or the chain step's event
      type) and invoking `onDrilldown(patch)`
- [x] `AuditView.tsx`: `onDrilldown` merges the patch into the
      current filters (merge, never reset), switches to the Events
      tab, triggers one refresh; zero-count buckets still navigate
- [x] Vitest: drill-down merge semantics (preserves time range,
      replaces only the targeted dimension), chain-step targets,
      zero-count navigation

## R-4: Proportion on every bucket row (W-4)

- [x] Percentage column (one decimal place, deterministic rounding
      via one shared formatter) + thin neutral antd `Progress` bar
      per bucket row, computed client-side from the existing payload
- [x] Vitest: percentage math, zero-total guard (empty posture, no
      division)

## R-5: Collapsible sections, single page (W-4)

- [x] The four bucket tables in antd `Collapse` panels (header =
      title + section total), all expanded by default, state
      per-render; statistic row outside the folding
- [x] Vitest: panels render expanded by default and fold on demand

## R-6: Headline statistic row (W-4)

- [x] antd `Statistic` cards: total events + the four
      decision-chain steps, zeros as 0, chain steps clickable
      (R-3); prose total line and inline strip removed
- [x] Vitest: statistic row renders the fixture values incl. zeros

## R-7: Living-state docs and release train (W-5)

- [x] `portal-user-guide.md` Summary tab section (statistic row,
      drill-down, proportion, collapse, outcome filter);
      `configuration-reference.md` / `authorization-matrix.md` only
      if implementation adds a knob or enumerates filter dimensions
- [x] Version lockstep 0.28.0 → 0.29.0; `make verify` green before
      **and** after `make build`; `make deploy`
- [x] Browser live check: drill-down landings from each section
      incl. outcome (time range set, proving the merge), zero-count
      navigation, proportion math, collapse behavior,
      operator/observer denial regression
- [x] CHANGELOG 0.29.0 + release note + index; commit/scan/tag/push
      per the house train (never combined); final clean rebuild +
      redeploy
