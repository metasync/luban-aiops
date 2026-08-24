# SPEC-029: Skills Usage Audit Trail

## Status

- status: `delivered`
- owner: chi
- created: 2026-08-25
- release slice: 0.11.0
- related ADRs: `docs/adr/0006-contract-purpose-invariant-enforcement.md`
- extends: `docs/specs/SPEC-013-durable-audit-trail/spec.md` and
  `docs/specs/SPEC-014-skills-and-grounded-guidance/spec.md`

## Summary

skills-hub answers search and retrieval queries for every skills consumer
but emits no audit events, so the platform cannot answer "which skills are
actually used, how often, and which searches come up empty". SPEC-029 adds
the canonical fire-and-forget audit emitter to skills-hub, extends the
shared audit-event vocabulary with `skill_searched`, `skill_retrieved`,
and `skills_synced`, and forwards the caller's `x-request-id` from
tool-gateway so usage events join the existing per-user `tool_invoked`
trail. Usage frequency, dead searches (demand without supply), and catalog
churn all become queryable through the existing audit API — no new query
surface, portal view, or storage machinery.

## Motivation

- Skill usage frequency is a metric the team wants to track: it tells us
  which runbooks earn their maintenance cost, which are dead weight, and
  which searches find nothing (missing-skill demand). Today the only
  signal is an unlabeled Prometheus counter (`skills_searches_total`) —
  no skill ids, no query text, no durability.
- The audit trail is the platform's established answer for exactly this
  shape of question (SPEC-013): durable, queryable envelopes with a
  closed event vocabulary. tool-gateway, platform-gateway,
  identity-broker, and incident-service already emit; skills-hub is the
  gap.
- Skill access flows through tool-gateway's `skills.*` tools, which are
  audited only as generic `tool_invoked` events (tool name, not skill
  outcome shape) and only for agent traffic. Emitting at skills-hub
  captures every consumer uniformly and at skill-id granularity, while
  request-id correlation preserves the user attribution that lives in the
  caller's events.

## Requirements

### R-1: Audit event vocabulary extension

The closed audit vocabulary gains three skills event types; the contract
and the audit-service model stay bound by the existing parity test.

Acceptance criteria:

- `shared/shared-contracts/schemas/audit-event.schema.json` `event_type`
  enum gains `skill_searched`, `skill_retrieved`, `skills_synced`; the
  `details` description documents each new per-event-type payload.
- audit-service `EventType` Literal
  (`products/audit-service/src/audit_service/schemas/audit.py`) gains the
  same three values; the existing enum-parity test in
  `products/audit-service/tests/test_contracts.py` passes unchanged.
- An ingest route test proves a `skill_searched` event round-trips
  through `POST /api/v1/audit/events` and the query API.

### R-2: skills-hub usage emission

skills-hub emits usage events through the canonical fire-and-forget
emitter pattern; emission can never degrade the retrieval path.

Acceptance criteria:

- New `products/skills-hub/src/skills_hub/services/audit_emitter.py`
  replicating the canonical emitter byte-for-byte modulo package and
  settings-class names (`build_audit_event` / `emit_audit_event` /
  `_deliver`, daemon-thread delivery, 2.0s timeout, unset
  `SKILLS_AUDIT_SERVICE_URL` keeps a byte-for-byte no-op); the module
  joins `AuditEmitterParityTest` in
  `products/tool-gateway/tests/test_module_parity.py`.
- `skills_hub/core/metrics.py` gains `record_audit_emit`
  (`audit_emits_total{result}`, the canonical emitter counter — the
  service dimension comes from the scrape target), mirroring the other
  emitters.
- `SkillsSettings` gains `audit_service_url` (`SKILLS_AUDIT_SERVICE_URL`,
  default empty = disabled), `audit_client_id` (`SKILLS_AUDIT_CLIENT_ID`,
  default `skills-hub`), `audit_client_secret`
  (`SKILLS_AUDIT_CLIENT_SECRET`).
- `GET /api/v1/skills/search` emits `skill_searched` with
  `outcome=success` and details `{query, limit, result_count, skill_ids}`
  (plus `source`/`tag` when the filters are set); `actor` is the
  authenticated caller's client_id; `request_id` is the inbound
  `x-request-id` (via `resolve_request_id`).
- `GET /api/v1/skills/{skill_id}` emits `skill_retrieved`: hits with
  `outcome=success` and details `{skill_id, source}`; misses with
  `outcome=error` and details `{skill_id, reason: "not_found"}` — the
  miss signal is demand for skills that do not exist.
- `GET /api/v1/skills` (list/browse) and the status endpoint are NOT
  audited; unauthenticated (401) requests are NOT audited (they remain
  log/metric surface only).

### R-3: Caller correlation via request id

Usage events join the caller's existing audit trail on `request_id`, so
per-user attribution needs no identity forwarding to skills-hub.

Acceptance criteria:

- tool-gateway's invoke dispatch adds `request_id` to the identity dict
  handed to tools (`gateway_service.py`), and `SkillsConnector._get`
  forwards it as the `x-request-id` header on skills-hub calls; other
  connectors are unchanged in this slice.
- Result: a `skill_searched` event stored by skills-hub shares its
  `request_id` with the caller's `tool_invoked` event, which carries the
  user's subject/username/roles.

### R-4: Sync trail

Catalog changes are audited so usage numbers can be read against catalog
state (a skill with zero retrievals since its source went red is a sync
problem, not a dead skill).

Acceptance criteria:

- `SyncManager.sync_once` emits one `skills_synced` event per cycle:
  success with details `{source_id, source_type, ref, accepted,
  rejected}`; failure with `outcome=error` and details `{source_id,
  source_type, error}` using the already-token-scrubbed message.
- Sync events pass `request_id=None` and inherit the builder's
  `"unknown"` fallback (no inbound request exists); they carry no
  identity fields.

### R-5: Deployment wiring

The dev-k8s overlay registers skills-hub as an ingest client with the
same shared-secret discipline as the other emitters.

Acceptance criteria:

- `shared/platform-ops/gitops/sync-audit-secrets.sh` adds `skills-hub` to
  the `AUDIT_INGEST_CLIENTS` registry line, upserts
  `SKILLS_AUDIT_CLIENT_SECRET` into
  `dev-k8s/base/skills-hub/runtime-secrets.env`, syncs
  `skills-hub-runtime-secrets`, and restarts the skills-hub deployment
  (header comment updated to name skills-hub).
- `dev-k8s/base/skills-hub/runtime-config.env` gains
  `SKILLS_AUDIT_SERVICE_URL=http://audit-service:8000` and
  `SKILLS_AUDIT_CLIENT_ID=skills-hub`.
- `docs/guides/configuration-reference.md` gains the `SKILLS_AUDIT_*`
  rows.

## Non-Goals

- No usage aggregation/reporting UI and no portal changes — the audit
  query API already filters by `event_type`, and Prometheus counters
  cover rate dashboards; a reporting view is a future spec if raw
  queries prove insufficient.
- No end-user identity forwarding to skills-hub — attribution stays with
  the caller's `tool_invoked` events, joined via R-3.
- No retention or storage changes — skills traffic is low-rate,
  agent-driven; existing eviction (SPEC-013 R-6) absorbs it.
- No emission from list/browse or auth-failure paths (R-2).

## Impact

- products touched: `products/skills-hub` (emitter, settings, routes,
  sync, metrics, tests), `products/tool-gateway` (identity dict +
  skills-connector header, emitter parity family), `products/audit-service`
  (EventType Literal, route test), `shared/shared-contracts`
  (audit-event schema)
- contracts touched: `audit-event.schema.json` — additive enum extension
- identity / policy / audit / execution safety impact: one new ingest
  client registration (existing SPEC-008 credential vocabulary); no
  policy changes; emission is fire-and-forget and cannot block retrieval
- living state docs to update on delivery: configuration-reference,
  skills-hub README, CHANGELOG, delivery-roadmap, spec index

## Open Questions

All resolved at spec review (2026-08-25):

- Q-1 (granularity): per-request events, not pre-aggregated counters —
  the audit trail stores envelopes verbatim and aggregation is a query
  concern; Prometheus already covers rates -> R-2.
- Q-2 (sync events): included — usage numbers are only interpretable
  against catalog state, and the status endpoint is ephemeral -> R-4.
- Q-3 (user attribution): request-id correlation instead of forwarding
  user identity to skills-hub, keeping skills-hub outside the
  user-identity trust surface -> R-3.

## Changelog

- 2026-08-25: created as `draft` from the pre-milestone review finding
  (M2): skills usage frequency is untracked; owner requested a skills
  audit trail to see which skills are used often and which are not.
- 2026-08-25: approved — event vocabulary fixed at three types;
  correlation via `x-request-id` forwarding; sync trail included;
  reporting UI explicitly deferred.
- 2026-08-25: delivered — contract + audit-service vocabulary, skills-hub
  emitter (fourth member of the audit-emitter parity family), search/get/
  sync emission, tool-gateway `x-request-id` forwarding, gitops secret
  provisioning, and docs; shipped in 0.11.0; metric named
  `audit_emits_total{result}`
  (canonical emitter counter) instead of the drafted
  `skills_audit_emit_total{status}` to preserve byte-parity.
