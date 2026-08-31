# SPEC-046: Audit Reporting and Export

## Status

- status: `approved`
- owner: luban-platform-team
- created: 2026-08-31
- approved: 2026-08-31
- delivered: —
- release slice: R5 — Hardening and External Consumption (eighth R5
  slice, target v0.28.0)
- related ADRs: none (lineage: the R5 "richer audit reporting"
  deliverable (`audit-service <-> reporting interface`) promoted
  memo-free per the SPEC-042/045 precedent directly from the
  2026-08-31 roadmap review; extends SPEC-013 durable audit trail,
  SPEC-029 skills usage audit parity discipline, SPEC-037
  execution-chain events)

## Summary

SPEC-013 made the audit trail durable and queryable; SPEC-029 and
SPEC-037 grew the vocabulary to twenty event types across seven
emitter services, including the skills-usage events and the full
decision-to-execution chain (`confirmation_decided` →
`execution_requested` → `execution_completed` /
`execution_rejected`). Governance consumption, however, still stops
at paginated raw envelopes:

- There is **no aggregate surface** — answering "how many mutating
  executions were approved this week" or "what did each service
  emit" requires paging through events by hand.
- There is **no export** — offline review, ticket attachments, and
  compliance hand-offs have nothing to take out of the portal.
- The portal Audit view's filter vocabulary is **stale by
  construction**: its hardcoded lists name 7 of the 20 event types
  and 4 of the 7 emitter services (`agent-service`, `skills-hub`,
  and `execution-runtime` are absent), so the newest events —
  precisely the SPEC-029/037 ones this slice exists to surface —
  cannot even be filtered for.

This slice adds two deterministic, read-only reporting surfaces on
the existing trail — a summary aggregate endpoint and a bounded CSV
export — proxied by platform-gateway under the existing
`audit:read` action, and a portal Audit view upgrade (Summary tab,
export button, full vocabulary pinned by a drift guard). The slice
introduces **no new policy actions and no new audit event types**,
and the `auditor` role stays read-only: reporting rides the one
action auditors already hold.

## Requirements

### R-1: Summary aggregate endpoint in audit-service

Audit-service gains `GET /api/v1/audit/summary`:

- Accepts the same filter dimensions as the SPEC-013 R-4 query
  route (`username`, `session_id`, `request_id`, `event_type`,
  `service`, `since`, `until`). There is **no default window**: the
  selected range is whatever the filters say, and the store is
  already retention-bounded (`AUDIT_RETENTION_DAYS`,
  `AUDIT_MAX_EVENTS`), so every aggregate is structurally bounded.
- The `AuditStore` protocol gains `summarize(filters)`, implemented
  by both backends: PostgreSQL as grouped SQL over envelope columns
  only (`GROUP BY event_type / outcome / service / username` —
  **never `details` JSONB excavation**), the in-memory store as the
  same `_matches` filter pass. Response shape (all sections sorted
  deterministically — count descending, then name ascending):
  - `total_events`: total matching count;
  - `window`: echo of the applied filters (null fields omitted);
  - `by_event_type`, `by_outcome`, `by_service`: name/count lists;
  - `top_actors`: the top 10 non-null `username` values with
    counts;
  - `decision_chain`: an explicit projection of the SPEC-037
    lineage — counts for `confirmation_decided`,
    `execution_requested`, `execution_completed`, and
    `execution_rejected` (zero when absent) — so governance can
    reconcile approvals against executions without a derived
    reading of the type table.
- Caller authentication reuses the query route's registered-service
  posture (`authenticate_caller`); the response is computed
  verbatim from stored envelopes — no rewriting, no interpretation.
- Observability posture mirrors the query route: a structured
  `audit_summary_queried` log line via `log_event` (stdout JSON —
  **not** self-ingested into the store, the existing
  `audit_events_queried` posture), one `audit_summary_query_total`
  counter under the observability conventions.

### R-2: Bounded CSV export in audit-service

Audit-service gains `GET /api/v1/audit/export`:

- Same filter dimensions as R-1; rows stream newest-first in the
  trail's verbatim envelope values through a fixed column set:
  `occurred_at, event_type, service, outcome, username, actor,
  subject, session_id, request_id, details`. `details` is the
  JSON-encoded object (deterministic key order); `occurred_at` is
  RFC-3339 UTC. RFC-4180 quoting throughout.
- One new knob `AUDIT_EXPORT_MAX_ROWS` (default `10000`): a hard
  row cap, enforced by paging the existing store query (200-row
  pages) through a `StreamingResponse` so memory stays bounded at
  one page. When the cap truncates, the response carries
  `X-Audit-Export-Truncated: true` and `X-Audit-Export-Rows: <n>`;
  the headers are present (with `false` / the exact count) even
  when it does not, so consumers can always tell them apart.
- `Content-Type: text/csv` and a deterministic
  `Content-Disposition` filename
  (`audit-export-<UTC timestamp>.csv`).
- Caller authentication is the same registered-service posture; a
  structured `audit_export_generated` log line carries the caller
  and the returned row count (stdout JSON, not self-ingested), and
  one `audit_exports_total` counter records exports.
- CSV is the only format this slice ships; JSON/Parquet export is
  parked (promotion triggers below).

### R-3: Gateway pass-through under the existing `audit:read`

Platform-gateway proxies both routes on its audit router:

- `GET /api/v1/audit/summary` (verbatim JSON pass-through) and
  `GET /api/v1/audit/export` (byte pass-through with
  `Content-Type`, `Content-Disposition`, and the two
  `X-Audit-Export-*` headers forwarded).
- The gate stays the **existing `audit:read` action** — no new
  policy actions, no policy-bundle changes, no new audit event
  types (the SPEC-043 lineage). Blocked attempts ride the
  gateway's existing blocked-attempt audit; the export leg is a
  read of already-audited facts, so generation needs no event of
  its own beyond the audit-service's own log line (R-2).
- Error mapping is the audit router's existing posture: 503 when
  the audit service URL is unconfigured, 4xx passthrough (bad
  filter / bad credential), 502 for transport or upstream 5xx.
  The gateway holds no report state; the export proxy timeout is a
  named constant sized for the capped export (30 s), distinct from
  the query leg's 10 s.
- The route inventory and policy-matrix tests pin both routes; the
  matrix gains no cells (`audit:read` already exists).

### R-4: Shared contract and drift guards

- `shared/shared-contracts/schemas/audit-summary.schema.json`
  describes the R-1 response; an audit-service contract test binds
  the pydantic response model to the schema (the SPEC-013
  `test_contracts.py` parity pattern). `audit-event.schema.json`
  is **untouched** — the event vocabulary does not change.
- The portal's filter vocabulary moves from the stale hardcoded
  lists to two pinned constants: `EVENT_TYPES` (all 20 enum values,
  mirroring `audit-event.schema.json`) and `EMITTER_SERVICES` (the
  seven emitter `SERVICE_NAME` values: `agent-service`,
  `execution-runtime`, `identity-service`, `incident-service`,
  `platform-gateway`, `skills-hub`, `tool-gateway` — `audit-service`
  never emits into its own store, so it is not an emitter). A
  vitest drift guard reads the shared
  `audit-event.schema.json` and asserts the constant equals the
  schema enum, so a future event type can never silently drop out
  of the filter again (the SPEC-029 parity-guard lesson applied to
  the portal surface).

### R-5: Portal Audit view upgrade

The Audit view keeps its `AUDIT_ROLES` gate (auditor /
platform-admin; the gateway re-enforces) and gains:

- **Two tabs: Events and Summary.** The existing table (filters,
  cursor pagination, expandable verbatim envelopes) moves into
  Events unchanged; Summary renders the R-1 response as a total
  line, the type/outcome/service tables, the top-actors table, and
  a decision-chain strip (`confirmation_decided` →
  `execution_requested` → `execution_completed` /
  `execution_rejected` with counts).
- **One shared filter toolbar** above the tabs drives both tabs and
  the export; the full pinned vocabulary (R-4) replaces the stale
  selects.
- **Export CSV** in the toolbar: streams the server-side export
  (R-2) under the current filters into the SPEC-040 R-4 client-side
  Blob download, using the server's `Content-Disposition` filename;
  a truncation notice appears when `X-Audit-Export-Truncated` is
  `true`. Export is a rendering of the audited read surface — no
  new audit event (the read itself is recorded at query time).
- Structured error toasts for 403 / 502 / 503; busy states on both
  tabs; the zero-deprecation vitest guard stays green.

### R-6: Living-state docs and release train

- `docs/agentic-aiops-platform/authorization-matrix.md` — the
  reporting surfaces ride the existing `audit:read` grant (auditor
  / platform-admin); the auditor read-only invariant is unchanged.
- `docs/guides/portal-user-guide.md` — the Audit view tabs, the
  summary sections, and the export flow.
- `docs/guides/configuration-reference.md` — the new
  `AUDIT_EXPORT_MAX_ROWS` knob.
- CHANGELOG 0.28.0 + release note + release-notes index; version
  lockstep; `make verify` green before and after `make build`;
  live check on the canonical deployment (summary under filters,
  export download with truncation posture, observer/operator
  denial, stale-vocabulary regression).

## Design Decisions

Drafted memo-free per the SPEC-042/045 precedent; the adjudications
are recorded here:

- **Q-1: Report shape — document type or ephemeral surface?**
  **Resolved: ephemeral server-side aggregate + export, not a
  SPEC-039 document type.** The `auditor` role holds only
  `audit:read` and no document actions; making audit reports a
  document type would either grant a governance role write access
  (against the auditor read-only invariant) or exclude the role the
  reports exist for. Live aggregate + export matches how governance
  consumes a trail: on demand, under the current filters, taken
  offline.
- **Q-2: Access gate.** **Resolved: the existing `audit:read`
  action.** No new policy actions, no new audit event types — the
  SPEC-043 lineage. Reporting is a read of already-audited facts;
  the audit-service records the read in its own structured log
  (stdout JSON, never self-ingested) exactly as the query route
  does today.
- **Q-3: What may the summary aggregate over?** **Resolved:
  envelope columns only** (`event_type`, `outcome`, `service`,
  `username`) — never `details` JSONB excavation. Envelope columns
  are the contract-stable, indexed surface; per-detail breakdowns
  would couple the report to every emitter's payload shape. The
  decision chain is therefore an explicit count projection (R-1),
  not a join.
- **Q-4: Export format and bound.** **Resolved: server-side
  RFC-4180 CSV only, hard row cap `AUDIT_EXPORT_MAX_ROWS`
  (default 10 000), streaming pages of 200, truncation headers.**
  A client-side "export what is loaded" cap (the SPEC-040 Blob
  posture) would make the export depend on how far the auditor had
  paged — governance needs the whole filtered range, deterministically
  bounded server-side instead. JSON export is parked.
- **Q-5: Window semantics.** **Resolved: no default window.** The
  store is already bounded by retention and the hard event cap, so
  an unfiltered summary is already a bounded report; inventing a
  default window would silently hide events the auditor did not ask
  to hide.
- **Q-6: Portal shape.** **Resolved: one view, two tabs, one shared
  toolbar.** Summary and Events answer different questions about
  the same filter state; separate toolbars would invite the two
  tabs to disagree. The export lives in the shared toolbar because
  it exports "the current filters", whichever tab is open.
- **Q-7: Fixing the stale vocabulary.** **Resolved: pinned
  constants + a vitest drift guard against the shared schema.** The
  stale hardcoded selects are the defect that motivated this slice;
  the SPEC-029 parity-guard lesson (a vocabulary member must not
  silently drop out of any surface) extends to the portal via a
  schema-pinning test.

## Invariants preserved

- The audit event vocabulary and envelope shape are untouched —
  `audit-event.schema.json` gains no values; ingest, query, and
  every emitter keep working byte-identically.
- No new policy actions; deny-by-default and the auditor
  read-only invariant are unchanged.
- Reports are facts-only: deterministic aggregates over stored
  envelopes, no prose layer, no LLM involvement, no
  interpretation.
- The export never exceeds its row cap; truncation is always
  visible in the response headers (and the portal notice).
- The gateway remains the only user-facing entry; the audit
  service keeps its registered-service caller posture, and report
  routes add no ingest capability.

## Impact

- `docs/agentic-aiops-platform/authorization-matrix.md` — audit
  reporting surfaces ride the existing `audit:read` grant.
- `docs/guides/portal-user-guide.md` — Audit view tabs and export.
- `docs/guides/configuration-reference.md` — `AUDIT_EXPORT_MAX_ROWS`.
- contracts touched: one **additive** schema
  (`audit-summary.schema.json`); `audit-event.schema.json` and the
  policy bundle untouched.

## Parked / promotion triggers

- **JSON (or Parquet) export format** — promote on the first
  consumer that cannot round-trip CSV `details` JSON.
- **Scheduled / recurring reports** (e.g. a weekly governance
  digest) — promote on the first ask; would need its own delivery
  channel and an adjudication of who receives it.
- **Per-detail breakdowns** (e.g. denied-policy counts per rule id)
  — parked behind Q-3; promote if governance asks for a breakdown
  the envelope columns cannot express, together with a contract for
  the detail field in question.
- **Audit report as a publishable document type** — parked behind
  Q-1; promote only if the auditor read-only invariant is
  deliberately revisited.

## Changelog

- 2026-08-31: created as `draft`, promoted memo-free from the R5
  "richer audit reporting" deliverable per the SPEC-042/045
  precedent; pending operator approval.
- 2026-08-31: operator approved the draft (`draft` → `approved`)
  after review, with no requirement changes; delivery proceeds
  under the house train as v0.28.0.
