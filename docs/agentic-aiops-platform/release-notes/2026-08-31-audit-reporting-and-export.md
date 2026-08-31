# v0.28.0 — Audit Reporting and Export (SPEC-046)

Date: 2026-08-31
Release type: feature (audit reporting surfaces; no new policy action,
no new event type — both surfaces ride the existing `audit:read` grant
and aggregate envelope columns only)

## Summary

The audit trail stops being a scroll-and-eyeball surface: auditors and
platform admins now get deterministic aggregates over any filter window
and a bounded CSV export of the filtered envelopes, in the portal and
at the API. The summary answers "what happened, how often, and through
which decision chain" without paging through rows; the export feeds the
same envelopes into spreadsheet and archival workflows. Both surfaces
are read-only by construction: they reuse the `audit:read` gate, add no
policy action and no event type, and never aggregate over event
payloads — the auditor's read-only invariant is unchanged. Along the
way the portal's filter vocabulary re-syncs with the shared contract
(20 event types and 7 emitter services instead of the stale 7 and 4),
pinned by a vitest drift guard so it cannot go stale again.

## What Changed

### Summary aggregate endpoint (R-1)

- audit-service gains `GET /api/v1/audit/summary`, behind the same
  `authenticate_caller` posture as the event query: total event count,
  the echo of the effective filter window, bucket tables by event type
  / outcome / service (count desc, name asc), top actors (cap 10,
  null usernames excluded), and the decision-chain counters
  (`confirmation_decided → execution_requested → execution_completed →
  execution_rejected`, zeros included — a quiet window renders four
  zeros, never an error).
- Both store backends compute identical results: the in-memory store
  filters and counts in-process; the Postgres store runs six bounded
  GROUP BY queries over envelope columns behind one shared filter-clause
  builder, sorted with the same comparators. `details` is never
  referenced on either path, and the Postgres result set is pinned
  against the in-memory computation in a parity test.
- New counters `audit_summary_query_total` and `audit_exports_total`;
  each summary query is recorded in the structured service log.

### Bounded CSV export (R-2)

- audit-service gains `GET /api/v1/audit/export`: an RFC-4180 CSV of
  the filtered envelopes with ten fixed columns
  (`occurred_at, event_type, service, outcome, username, actor,
  subject, session_id, request_id, details`), RFC-3339 UTC `Z`
  timestamps, and sorted-key compact `details` JSON as the final
  column. Rows are capped at `AUDIT_EXPORT_MAX_ROWS` (default `10000`,
  positive-int validated); a truncated export still downloads and
  says so — `X-Audit-Export-Truncated` and `X-Audit-Export-Rows` are
  always set before the first byte streams, and the filename is
  deterministic (`audit-export-<timestamp>.csv`).
- Collection is cap-bounded up front (page loop over the existing
  keyset query), so the streaming response never discovers its own
  headers mid-flight.

### Contract and gateway pass-through (R-3/R-4)

- shared-contracts gains `audit-summary.schema.json`
  (`additionalProperties: false`), bound by the service's contract
  tests the same way the event schema is.
- platform-gateway proxies both routes behind the existing `audit:read`
  gate with the house 503/4xx-passthrough/502 mapping. The export leg
  uses a dedicated 30 s timeout and forwards only the allowlisted
  content headers (`content-type`, `content-disposition`, and the two
  `X-Audit-Export-*` posture headers) — internal headers never leak
  through.

### Portal Audit view tabs, export, and drift guard (R-4/R-5)

- The Audit view becomes tabbed: **Events** (the existing table moved
  intact, including the expandable envelopes and **Load more** bar) and
  **Summary** (total, decision-chain strip, and the four bucket tables;
  fetched lazily on tab entry and refetched whenever the filters
  moved). One shared filter toolbar — username, event type, emitter
  service, since/until — drives both tabs and the export.
- **Export CSV** rides the SPEC-040 R-4 Blob posture: the server
  filename from `Content-Disposition` wins, and the
  `X-Audit-Export-Truncated` header becomes a warning notice naming
  the row cap. 403/502/503 get structured messages on both surfaces.
- The filter selects now read from pinned constants mirroring the
  shared `audit-event.schema.json` — all 20 event types in schema enum
  order and all 7 emitter services — with a vitest drift guard that
  fails the suite if the contract moves without the portal. That closes
  the stale-vocabulary defect (7-of-20 types, 4-of-7 services) that
  made skill and execution events unfilterable.

## Invariants preserved

- No new policy action, no new event type; both surfaces ride
  `audit:read` (auditor / platform-admin), and operator /
  read-only-observer receive the standard audited policy 403 on both
  routes.
- Aggregation touches envelope columns only — never the `details`
  payload — on both store backends.
- audit-service never self-emits; the emitter vocabulary stays the
  seven registered services.
- The export is bounded by construction: one knob, one honest header,
  no unbounded scan.

## Verification

- audit-service 124 tests (store parity on both backends, full HTTP
  coverage of both routes incl. the truncation cap, contract binding,
  config knobs), platform-gateway suite green incl. the twelve new
  summary/export proxy tests and the route inventory, portal 254
  vitest tests incl. the new summary/export suites and the drift
  guard — all green; `make verify` green at 0.28.0 before and after
  `make build`.
- Browser live check on aiops.luban.metasync.cc: summary under a
  filter window, export download with the truncation posture, auditor
  end-to-end, operator/observer denial on both routes, and the
  stale-vocabulary regression (skill and execution events now
  filterable). The first live pass surfaced one Postgres-only defect
  in the summary path — `event_type IN $1` rejects the adapted list
  parameter (500 upstream, 502 through the gateway) while the
  fake-driver parity tests stayed green; the store now uses
  `= ANY(%(chain_types)s)` with a pinned list-shape test, and every
  scenario ran green on the re-check.
