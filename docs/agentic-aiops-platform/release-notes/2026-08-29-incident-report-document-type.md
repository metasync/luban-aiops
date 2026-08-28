# v0.25.0 — Incident Report Document Type (SPEC-043)

Date: 2026-08-29
Release type: feature (fifth R5 slice, extending the SPEC-039
operations document repository; no new policy actions, no new audit
event types, read-only with respect to incident state)

## Summary

The operations document repository gains its second type:
`incident_report`. An operator selects an incident and the platform
assembles a durable, attributed report — the incident envelope, the
validated triage report, the connector dispatch outcomes, and the
incident's linked triage session under the existing two-tier own/foreign
coverage — with the same optional digest-anchored narrative, the same
draft→publish lifecycle, the same role-based access matrix, and the
same client-side Markdown export as shift summaries. Creation is gated
by the combination of two existing actions (`documents:create` **and**
`incident:read`), so the document surface never bypasses the incident
visibility matrix; assembly is read-only end to end — no incident state
is mutated anywhere in the path.

## What Changed

### Contract extension (R-1)

- `operation-document.schema.json` accepts `incident_report` and its
  digest object: the `incident` / `triage` / `dispatches` / `session`
  sections with SPEC-015 parity bounds; both types validate in the
  contract tests.

### Incident-report assembly (R-2)

- New `incident_report.py` assembler copies the incident envelope, the
  validated triage report, and the connector dispatch outcomes
  verbatim; the raw alert payload (`triage_raw`) never enters the
  digest — a `has_triage_raw` presence marker replaces it (prose
  purity).
- The linked triage session rides the digest under the SPEC-039 R-3
  two-tier posture: full digest when the requester owns it,
  metadata-only when it is foreign and the requester holds
  `approvals:list` (trusted `X-Foreign-Coverage` header), and honest
  markers otherwise — `foreign_denied`, `missing` (no linked session),
  `unavailable` (store failure). An incident report never fails
  because its session is out of reach.
- A `not_triaged` marker stands in for incidents without a triage
  report; `triage_failed` and session-less incidents still assemble.
- The counts-only list summary reads e.g. *critical · triaged · triage
  report present · 1 dispatch · own session* — never the incident
  title or summary text, so the envelope-only listing posture holds.

### Internal incident client and dual-action gate (R-3)

- New `incident_client.py` in agent-platform: one bounded HTTP GET for
  the incident-service single-incident bundle, Basic query credential
  against the `INCIDENT_QUERY_CLIENTS` registry, `x-request-id`
  forwarding, and a structured error hierarchy mapped to HTTP
  postures: 503 not configured, 502 transport/upstream 5xx, 404
  unknown incident id, other 4xx passed through. Never a 500.
- New settings knobs: `AGENT_INCIDENT_SERVICE_URL`,
  `AGENT_INCIDENT_CLIENT_ID`, `AGENT_INCIDENT_CLIENT_SECRET`,
  `AGENT_INCIDENT_CLIENT_TIMEOUT_SECONDS`; dev-k8s wires the URL and
  client id in runtime-config, and `sync-incident-secrets.sh`
  provisions the `agent-service` entry in the query registry and
  upserts the credential into the active runtime profile's secret
  file — the same source file the audit and OTel sync scripts own for
  `agent-platform-runtime-secrets`, so no sibling key is wiped.
- Gateway create route enforces `incident:read` in addition to
  `documents:create` for `incident_report` (denials report the first
  failing action); `DocumentCreateRequest` accepts `incident_id`
  (pattern-validated) for the incident type and rejects cross-type
  field mixing. Only the type-relevant coverage field rides upstream,
  so the agent never sees a mixed create shape; the gateway forwards
  the agent's statuses and structured details (503/502/404/4xx)
  verbatim.

### Prose layer and audit (R-4/R-5)

- The prose prompt builder extends to the incident-report digest with
  digest-only purity (prompt-purity regression test); `prose_status`
  behavior and rendering are identical to shift summaries.
- `document_created` carries the covered `incident_id` as provenance
  (agent audit + gateway log event); published/cross-owner-read events
  are unchanged — no new audit event types.

### Portal Documents support (R-6)

- The create dialog becomes type-aware (**New document** → Shift
  summary / Incident report radio): the incident branch lists the
  visible incidents in a searchable picker (title, id, severity,
  status) and submits exactly one `incident_id`; label and narrative
  toggle are retained.
- The drawer renders incident digests as Incident / Triage /
  Dispatches / Session / Raw JSON tabs with marker alerts
  (`not_triaged`, `missing`, `foreign_denied`, `unavailable`), the
  foreign metadata banner, and the owner-session confirmation and
  execution tables; list rows carry the incident id; envelope-only
  listings stay intact.
- Creation failures render their posture: unknown incident (404),
  incident reporting not configured (503), incident facts unreachable
  (502).

## Verification

- agent-platform suite green (664 passed) including the new
  incident-client/assembler suites, the incident-report document
  create paths, the prose purity test, and the settings knobs.
- platform-gateway suite green (258 passed) including the dual-gate
  enforcement, the 503/502/404/4xx passthroughs, and the per-type
  payload forwarding.
- Portal vitest suite green (21/21) with the zero-tolerance antd
  deprecation guard active; `tsc --noEmit` clean.
- House train: `make build` → `make verify` (all suites, overlays,
  policy, version lockstep) → `make deploy` → live checks (triaged
  incident report create/publish/cross-owner read on the durable
  trail; `triage_failed` and session-less marker paths).
- L3 deep security review before push.

## Documentation

- Living-state updates: portal user guide (Documents workflows),
  incident guide (capturing an incident as a document), authorization
  matrix (dual-action gate), documents & digest reference
  (incident-report digest sections), configuration reference
  (`AGENT_INCIDENT_*` knobs and the incident chain).
- SPEC-043 flipped to `delivered` across spec.md, the specs index, the
  delivery roadmap, and its tasks list.
