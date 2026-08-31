# SPEC-046 Tasks

## R-1: Summary aggregate endpoint in audit-service (W-1)

- [x] `AuditStore.summarize(filters)` on the protocol;
      `InMemoryAuditStore` Counter-based implementation over the
      existing `_matches` pass (deterministic sort: count desc,
      name asc; `top_actors` top 10 non-null usernames);
      `PostgresAuditStore` grouped SQL over envelope columns only
      (`details` never touched) with one shared WHERE-builder
      extracted from `query()`
- [x] `AuditSummary` response shape: `total_events`, `window` echo
      (null fields omitted), `by_event_type`, `by_outcome`,
      `by_service`, `top_actors`, `decision_chain`
      (`confirmation_decided` / `execution_requested` /
      `execution_completed` / `execution_rejected`, zero when
      absent)
- [x] `GET /api/v1/audit/summary` route: query-route structure
      verbatim (`authenticate_caller`, same filter params, 400/401
      postures); `audit_summary_queried` log line via `log_event`
      (stdout JSON, never self-ingested);
      `audit_summary_query_total` counter
- [x] Tests: in-memory ↔ fake-driver Postgres summarize parity,
      deterministic ordering, top-actor cap + null-username
      exclusion, decision-chain zeros, empty window answers zeros
      (not an error), auth rejection

## R-2: Bounded CSV export in audit-service (W-2)

- [x] `AUDIT_EXPORT_MAX_ROWS` knob (default 10 000, validated
      positive) in `core/config.py`
- [x] `GET /api/v1/audit/export`: `StreamingResponse` (`text/csv`)
      paging `store.query` at 200 rows until trail end or the cap;
      fixed columns `occurred_at, event_type, service, outcome,
      username, actor, subject, session_id, request_id, details`
      (RFC-3339 UTC timestamp, sorted-key JSON details, RFC-4180
      quoting); `X-Audit-Export-Truncated` and
      `X-Audit-Export-Rows` always present; deterministic
      `Content-Disposition` filename
- [x] `audit_export_generated` log line (caller, rows) +
      `audit_exports_total` counter
- [x] Tests: cap truncation (cap + 1 rows → exactly cap rows,
      truncated true), exact-count headers under the cap, CSV
      quoting of commas/quotes/newlines in `details`,
      deterministic column order, filter passthrough, auth
      rejection

## R-3: Gateway pass-through under `audit:read` (W-3)

- [x] `GET /api/v1/audit/summary` proxy: existing `audit:read`
      gate, verbatim JSON pass-through, filter params forwarded,
      router error mapping (503 unconfigured, 4xx passthrough,
      502 transport/5xx), 10 s timeout
- [x] `GET /api/v1/audit/export` proxy: byte pass-through with
      `Content-Type` / `Content-Disposition` / `X-Audit-Export-*`
      forwarded, 30 s named-constant timeout, same gate and
      mapping; gateway holds no report state
- [x] Tests: policy denial for ungranted roles on both routes,
      header forwarding on export, verbatim summary pass-through,
      error mapping; route-inventory update (no new policy-matrix
      cells)

## R-4: Shared contract and drift guards (W-3, W-4)

- [x] `shared/shared-contracts/schemas/audit-summary.schema.json`
      (additive; `audit-event.schema.json` untouched)
- [x] audit-service `test_contracts.py`: summary-model ↔ schema
      binding beside the enum parity class
- [x] Portal `views/audit/constants.ts`: `EVENT_TYPES` (all 20
      enum values) + `EMITTER_SERVICES` (the seven emitter names);
      vitest drift guard reads the shared `audit-event.schema.json`
      and asserts set equality

## R-5: Portal Audit view upgrade (W-4)

- [x] `AuditView` restructured: shared filter toolbar above antd
      `Tabs`; **Events** tab carries the existing table (filters,
      cursor pagination, expandable envelopes) unchanged;
      **Summary** tab renders the total line, type/outcome/service
      tables, top-actors table, and the decision-chain strip
- [x] **Export CSV** in the toolbar: Blob fetch of
      `/api/v1/audit/export?<current filters>`, server
      `Content-Disposition` filename (SPEC-040 R-4 download
      posture), truncation notice from
      `X-Audit-Export-Truncated`
- [x] Error toasts (403/502/503) on both tabs and the export;
      busy states; role gate unchanged
- [x] Vitest: tab switch preserves filters, summary fixture
      rendering, decision-chain zeros, export Blob call +
      filename, truncation notice, error toasts; zero-deprecation
      guard green

## R-6: Living-state docs and release train (W-5)

- [x] `authorization-matrix.md` (reporting rides the existing
      `audit:read` grant), `portal-user-guide.md` (Audit tabs +
      export), `configuration-reference.md`
      (`AUDIT_EXPORT_MAX_ROWS`)
- [x] Version lockstep 0.27.6 → 0.28.0; `make verify` green before
      **and** after `make build`; `make deploy`
- [x] Browser live check: filtered summary, export download +
      truncation notice (small cap override), operator/observer
      denial (API 403 + view gate), stale-vocabulary regression
      (skill and execution events now filterable)
- [x] CHANGELOG 0.28.0 + release note + index; commit/scan/tag/push
      per the house train (never combined)
