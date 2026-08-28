# SPEC-043: Incident Report Document Type

## Status

- status: `draft`
- owner: luban-platform-team
- created: 2026-08-28
- delivered: —
- release slice: R5 — Hardening and External Consumption (fifth R5
  slice, planned as v0.25.0)
- related ADRs: none (lineage: SPEC-039 non-goal "incident reports —
  next slice", SPEC-015 incident triage, SPEC-040/041 document
  rendering conventions)

## Summary

The operations document repository gains its second document type:
`incident_report`. An operator selects an incident and the platform
assembles a durable, attributed report — the incident envelope, the
validated triage report, the connector dispatch outcomes, and the
linked triage session's digest under the existing two-tier ownership
posture — with the same optional digest-anchored prose layer, the same
draft→publish lifecycle, and the same role-based access matrix as
shift summaries. No new policy actions, no new audit event types, no
incident-state mutation: the slice is a read-only assembly over facts
that are already durable.

## Motivation

- **SPEC-039 named this as the next type.** The substrate's non-goals
  record: "Incident reports (`incident_report` type) — next slice; its
  assembly additionally reaches incident-service data and earns its
  own vertical slice." The substrate was built for exactly this: the
  type discriminator, the role × type matrix, provenance anchoring,
  and the audited cross-owner read path all exist; only the incident
  assembly leg is missing.
- **The incident story is assembled by hand today.** Triage produces a
  validated report and connector dispatches, but once the shift ends,
  review relies on re-opening the incidents view and whichever session
  ran the triage. A published incident report gives incident review
  the same durable, attributed, cross-owner-readable artifact that
  shift handover got in v0.21.0.
- **Provenance is already the safety property.** The report copies
  incident and triage facts verbatim with record-id anchors — role-wide
  document visibility never opens the underlying session beyond the
  metadata-only foreign tier, and cross-owner reads stay audited.
- **R5 timing.** The slice extends a stable substrate with one new
  internal client leg; it carries none of the architectural weight of
  the other backlog candidates (MCP exposure, semantic retrieval),
  which still owe spike memos.

## Requirements

Each requirement is stable once the spec is `approved` and carries
testable acceptance criteria.

### R-1: The `incident_report` type on the existing substrate

The typed-document discriminator extends from `shift_summary` to
include `incident_report`; the document lifecycle, store conventions,
and envelope-only listing posture of SPEC-039 R-1 / v0.21.1 apply
unchanged.

Acceptance criteria:

- `shared/shared-contracts/schemas/operation-document.schema.json`
  extends the `document_type` enum with `incident_report` and defines
  the type's digest shape (see R-2); the substrate's Pydantic models
  mirror the schema bounds exactly (the SPEC-015 contract-parity
  convention).
- Retention adjudication (the SPEC-039 R-1 commitment that per-type
  retention tuning travels with the next document type):
  `incident_report` **inherits the substrate defaults unchanged** —
  20 documents per owner, 30-day TTL, oldest-eviction. Rationale: the
  report's value horizon matches the inbox history window it aligns
  with, and a per-type retention knob would be the first store-config
  divergence with no operator ask. A retention bump is parked with an
  explicit promotion trigger (first operator ask to keep a report
  longer) — see Non-Goals.
- The digest is copied verbatim from durable records at assembly time;
  no model output appears outside the labeled prose section; the
  document stays immutable after publishing.

### R-2: Incident-report assembly

An incident-report assembler in agent-platform builds the digest from
two sources: incident-service (via the new internal client, R-3) and
the platform's own durable stores for the linked session. The digest
carries four deterministic sections:

- `incident` — the incident envelope copied verbatim
  (`incident_id`, `fingerprint`, `source`, `severity`, `status`,
  `title`, `summary`, `labels`, `reported_by`, `session_id`,
  timestamps);
- `triage` — the validated triage report copied verbatim when present
  (summary, severity assessment, evidence refs, hypotheses, next
  steps, skills cited, generator and timestamp), or the marker
  `not_triaged` when the incident has none (the incident status
  distinguishes never-triaged from `triage_failed`, whose raw text is
  carried in the incident envelope);
- `dispatches` — the connector dispatch outcomes copied verbatim
  (connector, status, reference, timestamp), possibly empty;
- `session` — the linked triage session's digest under the SPEC-039
  R-3 two-tier posture: full digest when the requester owns the
  session; metadata-only (decisions, execution receipts, record
  counts — never titles, transcript excerpts, or evidence content)
  when the session is foreign and the requester holds `approvals:list`;
  `foreign_denied` when foreign without `approvals:list`; `missing`
  when the incident carries no session id.

Acceptance criteria:

- The creation request carries exactly one incident id plus label and
  prose toggle; unknown incident ids answer the same structural `404`
  the incidents surface returns. No session-id input ships — coverage
  is the incident's own linked session only (additional sessions stay
  the shift-summary's job).
- Creation does not mutate incident state: no status change, no
  re-triage, no dispatch.
- An incident that failed triage still assembles (the digest carries
  the incident envelope with `triage_failed` status, the raw-triage
  marker, and the session digest); assembly never 500s on incident
  content.
- Foreign-session metadata-only coverage fails closed exactly as
  SPEC-039 R-3 does (the gateway's trusted `X-Foreign-Coverage`
  header; the agent layer rejects any value other than `allowed`).

### R-3: Internal incident client and dual-action gate

Agent-platform gains a bounded incident-service client; the gateway
gates incident-report creation behind the combination of two existing
actions.

Acceptance criteria:

- The client speaks to incident-service with agent-platform's own
  registered Basic query credential (the same posture the gateway's
  `incident_client` uses today — no new auth mechanism), forwards
  `x-request-id`, honors a bounded timeout knob, and is configured by
  three new knobs: `AGENT_INCIDENT_SERVICE_URL`,
  `AGENT_INCIDENT_CLIENT_ID`, `AGENT_INCIDENT_CLIENT_SECRET`.
- Missing configuration answers `503` (dependency not configured —
  the house posture) at creation time; an unreachable incident-service
  answers `502`; neither surfaces a raw stack trace.
- The gateway requires **both** `documents:create` and `incident:read`
  to create an `incident_report` (one action each for `shift_summary`,
  unchanged). Rationale: incident facts must reach only holders of
  `incident:read`; the document surface may not bypass the incident
  visibility matrix. No new policy action and no policy-bundle change
  beyond the combined evaluation. `read-only-observer` holds
  `incident:read` but not `documents:create`, so observers are
  naturally excluded from creation without any new rule.
- The incident client secret ships through the existing dev-k8s
  Secret-sync conventions; nothing lands in Git.

### R-4: Prose layer (inherited, digest-only)

The SPEC-039 R-4 prose contract applies unchanged: the prompt receives
the assembled digest JSON only — never the incident's raw alert
payload, triage raw text, or transcript — generation failure degrades
to `prose_status=failed` with a digest-only document, and the portal
renders prose only in the labeled "Generated narrative" panel.

Acceptance criteria:

- The prose prompt contract for `incident_report` feeds the digest
  alone; a regression test asserts no incident field outside the
  digest reaches the prompt.
- `prose_status` vocabulary and portal rendering are identical to
  shift summaries (the SPEC-040 default-expanded narrative posture
  included).

### R-5: Audit (no new event types)

The repository's existing events cover the new type:
`document_created` carries `document_type=incident_report` and adds
the covered `incident_id` as provenance (the only payload addition —
the emitter and event names stay unchanged); `document_published` and
the cross-owner `document_read` apply verbatim.

Acceptance criteria:

- `document_created` for incident reports records the incident id in
  addition to the existing fields; no other event shape changes.
- Cross-owner reads of published incident reports emit `document_read`
  exactly as shift summaries do; own reads stay unaudited.

### R-6: Portal Documents support

The Documents view grows incident-report creation and rendering inside
the existing surfaces — no new route or view.

Acceptance criteria:

- The creation dialog offers a type choice (Shift summary / Incident
  report); choosing Incident report swaps the session picker for an
  incident picker fed by the existing incidents list surface
  (id + title + severity + status), keeping the label field and prose
  toggle.
- The document drawer renders the incident-report digest in the
  SPEC-041 tabbed posture: **Incident** (envelope facts), **Triage**
  (report sections or the `not_triaged` marker), **Dispatches**,
  **Session** (own/foreign tier with the metadata-only banner where
  applicable), plus the Generated narrative panel and the raw-JSON
  tab; the list keeps counts-only creation-time summaries and
  envelope-only listings (the v0.21.1 posture).
- The type badge distinguishes incident reports; dark-theme antd
  conventions and the zero-deprecation guard hold (antd `title`/`size`
  APIs only).

## Design Decisions

- **Coverage scope → linked triage session only.** Allowing extra
  caller-supplied sessions would re-open the foreign-coverage input
  surface for a second time; the shift summary already covers
  arbitrary session sets. The incident's own `session_id` is the
  report's session section (server-derived, not caller-supplied).
- **Retention → inherit defaults, bump parked.** See R-1; the
  promotion trigger is recorded so the decision is revisitable without
  re-litigating it.
- **Visibility → dual-action gate, not new action.** Combining
  `documents:create` + `incident:read` reuses the adjudicated incident
  visibility matrix (operator/approver/platform-admin/read-only-observer
  for read; creation additionally requires the documents action) with
  zero policy-bundle churn.
- **Assembly placement → agent-platform owns the document, a new
  client owns the fetch.** The substrate, store, prose, and document
  audit all live in agent-platform; incident-service gains no document
  knowledge. The fetch uses the already-trusted Basic-query registry
  posture, so the slice adds plumbing, not mechanism.
- **No degradation for the incident section.** Unlike the
  shift-summary's per-source `unavailable` sections, an incident
  report without reachable incident facts is meaningless — missing
  configuration answers 503, unreachable upstream answers 502, unknown
  id answers 404; the document is simply not created.

## Non-Goals

- Per-type retention knobs or a longer incident-report TTL — parked
  with the promotion trigger in R-1.
- Caller-supplied additional session coverage — shift summaries own
  that surface.
- Editing incident state (status, resolution) from the document
  surface — assembly is read-only.
- New connectors, scheduled/automatic report generation, document
  versioning, comments — unchanged from SPEC-039 non-goals.
- Agent-tool access to repository documents — still a future candidate.

## Impact

- products touched: `products/agent-platform` (incident client,
  incident-report assembler, document-type extension, routes, tests),
  `products/platform-gateway` (dual-action gate on create,
  schema/payload mirror, tests), `products/operator-portal` (creation
  dialog type choice + incident picker, tabbed incident-report
  rendering)
- contracts touched: `shared/shared-contracts/schemas/operation-document.schema.json`
  (`incident_report` enum value + digest section); no policy-bundle
  change, no new audit event type, no incident-service contract change
- identity / policy / audit / execution safety impact: combined gate
  over two existing actions; provenance anchoring unchanged; no
  execution-path change (read-only spec — no mutating tools, no HITL
  interaction)
- deployment: three new agent-platform env knobs
  (`AGENT_INCIDENT_SERVICE_URL`, `AGENT_INCIDENT_CLIENT_ID`,
  `AGENT_INCIDENT_CLIENT_SECRET`) wired in dev-k8s through the
  existing Secret-sync conventions
- living state docs to update on delivery: `docs/guides/portal-user-guide.md`,
  `docs/guides/incident-guide.md`,
  `docs/agentic-aiops-platform/authorization-matrix.md`,
  `docs/guides/documents-digest-reference.md`,
  `docs/guides/configuration-reference.md`, `CHANGELOG.md`, release
  note + index

## Open Questions

- none — the design decisions above resolve scope, retention,
  visibility, placement, and degradation; approval can proceed on
  operator review of those resolutions.

## Changelog

- 2026-08-28: created as `draft` from the SPEC-039 recorded next-type
  commitment after the v0.24.0 post-release review recommended it as
  the fifth R5 slice; decision-complete per the Design Decisions
  section.
