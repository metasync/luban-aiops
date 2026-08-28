# SPEC-043 Implementation Plan

## Approach

One vertical slice across three products plus a contract extension.
Backend: agent-platform gains the incident-service client and the
incident-report assembler behind the existing document substrate
(R-2/R-3), platform-gateway applies the dual-action gate on create
(R-3), and the contract schema extends the type enum with the digest
shape (R-1). Portal: the Documents view grows the type choice, the
incident picker, and the tabbed incident-report rendering (R-6).
Prose and audit inherit the shipped contracts unchanged (R-4/R-5).
Everything is additive and read-only with respect to incident state;
the only new configuration is the three agent-platform incident
client knobs. Version lockstep to 0.25.0.

## Workstreams

### W-1: Contract and substrate extension (R-1)

- `shared/shared-contracts/schemas/operation-document.schema.json`:
  extend the `document_type` enum with `incident_report`; add the
  incident-report digest object (sections `incident`, `triage`,
  `dispatches`, `session`) with the same bounds the incident-service
  Pydantic models carry (title ≤200, summary ≤2000, labels bounded per
  the normalization constants, triage evidence ≤20 / hypotheses ≤5 /
  next_steps ≤10 / skills ≤10 — the SPEC-015 contract-parity rule).
- `products/agent-platform/src/agent_service/services/operation_documents.py`:
  accept the new type in the create path; store conventions (memory +
  Postgres backends, cap 20, 30-day TTL, idempotent DDL) untouched —
  the retention adjudication is "inherit".
- No DDL migration beyond what the existing document table already
  stores (digest is a JSON column); verify with both backends.

### W-2: Incident client in agent-platform (R-3)

- New `products/agent-platform/src/agent_service/services/incident_client.py`,
  modeled on the gateway's `incident_client.py`: Basic-auth query
  credential, `httpx.AsyncClient` with bounded timeout, `x-request-id`
  forwarding, 4xx passthrough / 5xx-and-transport → structured error.
- Settings: `AGENT_INCIDENT_SERVICE_URL`, `AGENT_INCIDENT_CLIENT_ID`,
  `AGENT_INCIDENT_CLIENT_SECRET` in the frozen settings dataclass
  (empty default = not configured → 503 at creation).
- dev-k8s wiring: register the agent-platform credential in the
  incident-service query-auth registry Secret, expose the URL knob —
  following the `sync-*-secrets.sh` conventions already used for the
  gateway's incident credential.

### W-3: Incident-report assembler (R-2)

- New `products/agent-platform/src/agent_service/services/incident_report.py`,
  mirroring `shift_summary.py`'s assembly posture: deterministic,
  verbatim copies, per-section provenance ids.
- Fetch order: incident envelope (404 on unknown id) → triage report
  (`not_triaged` marker when absent; `triage_failed` incidents keep
  the raw-triage marker from the envelope) → dispatches (possibly
  empty) → linked session digest.
- Session tier: the incident's `session_id` is resolved against the
  session store; owner match → the full shift-summary-style session
  digest; foreign + `X-Foreign-Coverage: allowed` → metadata-only
  section; foreign + denied → `foreign_denied` marker; absent →
  `missing`. Foreign coverage reuses the gateway's trusted header
  plumbing from the documents create route — no new trust surface.
- Degradation: incident-service unreachable → structured 502 at
  create; store unreadable for the session section → the section
  reports `unavailable` (the shift-summary per-source rule), the
  document still assembles.

### W-4: Gateway dual-action gate (R-3)

- `products/platform-gateway/src/platform_gateway/api/routes/documents.py`:
  when the body's `document_type` is `incident_report`, enforce
  `incident:read` in addition to `documents:create` before proxying
  (both through `enforce_policy`; a denial reports the first failing
  action, same structured shape as today).
- `schemas/api.py` `DocumentCreateRequest`: accept `incident_id`
  (contract pattern `^inc-[a-z0-9-]+$`, validated before use) for the
  incident type; reject `incident_id` for shift summaries and reject
  session lists for incident reports (coverage is server-derived).
- Gateway service layer passes `incident_id` through unchanged; the
  `document_created` gateway log event gains the `incident_id` field
  for the new type.

### W-5: Prose and audit inheritance (R-4/R-5)

- `document_prose.py`: extend the prompt builder with the
  incident-report digest shape (digest JSON only); add the regression
  test asserting no non-digest incident field reaches the prompt.
- `audit_emitter` call sites: `document_created` payload gains
  `incident_id` when the type is `incident_report`; event names and
  the emitter stay unchanged.

### W-6: Portal Documents view (R-6)

- `views/workspace/DocumentsView.tsx` + its components: creation
  dialog type radio (Shift summary default, Incident report), the
  incident picker (reuse the IncidentsView list fetch — same gateway
  surface, `incident:read` already held by the creating roles), label
  and prose toggle retained; invalid combinations surface the
  structured gateway denial verbatim.
- Drawer rendering: tabbed digest per the SPEC-041 posture — Incident
  / Triage / Dispatches / Session / Raw JSON tabs, the Generated
  narrative panel (default-expanded per SPEC-040), metadata-only
  banner for foreign session coverage, `not_triaged` /
  `foreign_denied` / `missing` markers rendered as antd `Alert`
  notes (antd-v6 clean — the zero-deprecation guard enforces).
- Type badge on list rows distinguishes the two types; list stays
  envelope-only (v0.21.1 posture).

## Sequencing And Dependencies

1. W-1 contract + substrate — depends on nothing; the schema is the
   shared surface every other workstream imports.
2. W-2 incident client — depends on nothing (client is unit-testable
   against a stub); dev-k8s wiring lands with W-3.
3. W-3 assembler — depends on W-1 + W-2.
4. W-4 gateway gate — depends on W-1 (request shape); lands alongside
   W-3.
5. W-5 prose/audit — depends on W-3 (digest shape final).
6. W-6 portal — depends on W-4 (API shape final); can start against
   the contract once W-1 lands.
7. Docs + version lockstep + full train — after all workstreams green.

## Test Strategy

- unit tests: incident client (auth header, timeout, 401/404/502
  mapping, not-configured 503), assembler (all four sections, every
  session tier, `not_triaged` / `triage_failed` / dispatches-empty
  cases, verbatim-copy assertions), dual-action gate (both denials),
  prose prompt purity.
- contract tests: `operation-document.schema.json` validates fixture
  envelopes for both types; incident digest bounds parity with the
  incident-service models.
- portal: vitest coverage for the creation dialog type switch, the
  incident picker, and the tabbed rendering incl. markers; suite
  stays at zero antd deprecation warnings (R-2 guard active).
- live validation: create an incident report for a real triaged
  incident in dev-k8s, publish, read cross-owner, verify
  `document_created` / `document_read` on the durable trail; a
  `triage_failed` incident and a session-less incident cover the
  marker paths.

## Rollout And Migration

- No DDL migration (digest stored in the existing JSON column); the
  enum extension is additive — old documents stay `shift_summary`.
- Three new agent-platform env knobs; dev-k8s wires them via the
  Secret-sync script in the same deploy, so the 503 path exists only
  for profiles that deliberately omit the incident client.
- Rollback: the type enum is additive and no incident state is ever
  touched — reverting the images simply removes the creation path;
  already-created incident reports remain readable as documents (the
  digest is a copied snapshot, independent of incident-service).
