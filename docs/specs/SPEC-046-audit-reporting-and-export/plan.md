# SPEC-046 Implementation Plan

## Approach

One vertical slice across two backend products and the portal —
no new services, no new clients, no policy-bundle changes, one new
knob (`AUDIT_EXPORT_MAX_ROWS`). Backend: audit-service gains a
summary aggregate route and a bounded CSV export route on top of
the existing store and caller-auth posture (R-1/R-2);
platform-gateway proxies both under the existing `audit:read` gate
(R-3). Contracts: one additive shared schema with a parity test,
plus a portal drift guard pinning the filter vocabulary to the
unchanged audit-event schema (R-4). Portal: the Audit view gains a
Summary tab, an export button, and the full pinned vocabulary
(R-5). Version lockstep to 0.28.0.

## Workstreams

### W-1: Summary aggregate in audit-service (R-1)

- `services/audit_store.py`: `AuditStore.summarize(filters)` on
  the protocol; `InMemoryAuditStore` implements it over the
  existing `_matches` pass (Counter-based, deterministic sort:
  count desc, name asc; `top_actors` = top 10 non-null usernames);
  `PostgresAuditStore` implements it as grouped SQL over envelope
  columns only — one shared WHERE-builder extracted from
  `query()` so the two routes cannot drift, `GROUP BY` per
  section, `details` never touched. The response dataclass
  (`AuditSummary`: `total_events`, `window` echo, `by_event_type`,
  `by_outcome`, `by_service`, `top_actors`, `decision_chain`)
  lives beside the pydantic response model.
- `schemas/audit.py` (or a sibling `schemas/summary.py`): pydantic
  response model bound to `audit-summary.schema.json` (W-3).
- `api/routes/summary.py`: `GET /api/v1/audit/summary` — the
  query route's structure verbatim (same `authenticate_caller`,
  same filter params, same 400/401 postures), returning the model;
  `audit_summary_queried` log line via `log_event` (stdout JSON,
  never self-ingested).
- `core/metrics.py`: `audit_summary_query_total` counter +
  `record_summary_query()`.
- Tests: in-memory and fake-driver Postgres summarize parity
  (same inputs, same output), deterministic ordering, top-actor
  cap and null-username exclusion, decision-chain zeros, empty
  window (all zeros, not an error), auth rejection.

### W-2: Bounded CSV export in audit-service (R-2)

- `core/config.py`: `export_max_rows: int = 10_000` from
  `AUDIT_EXPORT_MAX_ROWS` (validated positive).
- `api/routes/export.py`: `GET /api/v1/audit/export` — same
  filter params and caller auth; a `StreamingResponse`
  (`text/csv`) whose generator pages `store.query(filters,
  cursor, 200)` until the trail ends or `export_max_rows` rows
  have been written. Fixed header row; RFC-4180 quoting (the csv
  module, `io.StringIO` per row); `occurred_at` RFC-3339 UTC,
  `details` JSON-encoded with sorted keys; always emits
  `X-Audit-Export-Truncated` and `X-Audit-Export-Rows`, and a
  deterministic `Content-Disposition` filename
  (`audit-export-<YYYYMMDDTHHMMSSZ>.csv`).
  `audit_export_generated` log line (caller, rows); `core/metrics.py`
  gains `audit_exports_total` + `record_export()`.
- Tests: row-cap truncation (cap + 1 rows → exactly cap rows,
  truncated header true), exact-count headers when under the cap,
  CSV quoting of commas/quotes/newlines in `details`, deterministic
  column order and sorted-key details, filter passthrough, auth
  rejection.

### W-3: Gateway pass-through and contracts (R-3, R-4)

- `shared/shared-contracts/schemas/audit-summary.schema.json`:
  additive schema for the R-1 response (required sections, item
  shapes `{name, count}`); `audit-event.schema.json` untouched.
- audit-service `tests/test_contracts.py`: extend the enum-parity
  class with the summary-model ↔ schema binding.
- platform-gateway `api/routes/audit.py`: two new handlers on the
  existing router — `GET /api/v1/audit/summary` (JSON
  pass-through, same filter params, 10 s timeout) and
  `GET /api/v1/audit/export` (`httpx` stream read into a `Response`
  with `Content-Type` / `Content-Disposition` /
  `X-Audit-Export-*` forwarded, 30 s named-constant timeout).
  Both enforce the existing `audit:read` via `enforce_policy` and
  keep the router's error mapping (503 unconfigured, 4xx
  passthrough, 502 transport/5xx). No policy-engine changes, no
  new action constants.
- Tests: policy denial for ungranted roles on both routes (the
  existing 403 assertion pattern), header forwarding on export,
  verbatim summary pass-through, error mapping; route-inventory
  update; policy-matrix test unchanged in shape (no new cells).

### W-4: Portal Audit view upgrade (R-4, R-5)

- `views/audit/constants.ts` (new): `EVENT_TYPES` (all 20 values,
  order of the shared schema enum) and `EMITTER_SERVICES` (the
  seven emitter names, alphabetical);
  `views/audit/__tests__/constants.test.ts` drift guard reads
  `shared/shared-contracts/schemas/audit-event.schema.json`
  (relative path, `fs.readFileSync` in the vitest node env) and
  asserts set equality — the SPEC-029 parity lesson applied to
  the portal.
- `views/audit/AuditView.tsx`: antd `Tabs` — **Events** (the
  existing table, moved intact) and **Summary** (new
  `AuditSummaryPanel`: total line, type/outcome/service tables,
  top-actors table, decision-chain strip with arrows and counts,
  one fetch per apply). The filter toolbar hoists above the tabs
  and drives both; **Export CSV** button streams
  `/api/v1/audit/export?<filters>` via a Blob fetch (response
  body + `Content-Disposition` filename, the SPEC-040 R-4
  download posture) and shows a truncation notice from
  `X-Audit-Export-Truncated`.
- Error postures: 403/502/503 toasts on both tabs and the export;
  busy states; the role gate and its server re-enforcement are
  unchanged.
- Vitest: tab switch preserves filters, summary sections render
  deterministic fixtures, decision-chain zeros render as 0,
  export Blob call with server filename, truncation notice,
  error toasts; zero-deprecation guard green.

### W-5: House train (R-6 + release)

- Version lockstep 0.27.6 → 0.28.0 (VERSION, pyproject.toml,
  metadata.py, `__init__.py`, uv.lock across products); `make
  verify` before **and** after `make build`; `make deploy`.
- Browser live check on the canonical deployment: summary under a
  filter (e.g. `event_type=execution_completed`, since/until
  window), export download with a small cap override to exercise
  the truncation notice, operator/observer denial on both routes
  (API 403, view gate), and the stale-vocabulary regression (the
  skill and execution events now filterable).
- Living-state docs per spec.md Impact (authorization-matrix,
  portal-user-guide, configuration-reference); CHANGELOG 0.28.0 +
  release note + index; commit → scan gate → tag v0.28.0 → push
  (never combined).

## Sequencing

1. **W-1 and W-2** first — the store extensions and their tests
   pin the aggregate and export semantics before anything consumes
   them (they share the extracted WHERE-builder).
2. **W-3** next — the contract schema is written against the W-1
   model; the gateway pass-through follows.
3. **W-4** after W-3 — the portal consumes the finalized response
   shape and the pinned vocabulary.
4. **W-5** last, per the house train.

## Risks

- **Large exports.** A 10 000-row CSV is a real artifact; the cap
  is a knob, not a promise. Mitigation: truncation is always
  visible (headers + portal notice), and the cap defaults low
  enough that a full export stays a conscious operator act.
- **Streaming headers.** `X-Audit-Export-Truncated` must be known
  before the first byte streams. Mitigation: the generator counts
  against the cap up front per page and the truncation flag is
  decided from the cap-vs-remaining check at page boundaries —
  pinned by a test.
- **Postgres GROUP BY cost.** Four grouped queries per summary on
  a 100 000-row cap is cheap on the dev cluster, but unindexed
  filters could scan. Mitigation: the shared WHERE-builder reuses
  the existing indexed columns (`occurred_at`, `username`,
  `session_id`, `request_id`, `event_type`); the `service` filter
  scans within the time window only — acceptable at this scale,
  recorded here.
- **Portal schema path coupling.** The drift guard reads the shared
  contract by relative path; a vitest `resolve.alias` or the
  relative path pins it. Mitigation: one test, one path constant,
  fail loudly if the file moves.
- **Summary vs Events filter drift.** One shared toolbar drives
  both tabs and the export; a test asserts a filter change
  re-fetches whichever tab is active and applies to the export
  URL.
- **Scope creep toward dashboards.** Charts and trends are out of
  scope — the Summary tab renders deterministic tables. Promote
  only via a new spec if governance asks.
