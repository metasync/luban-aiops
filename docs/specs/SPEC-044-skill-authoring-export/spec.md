# SPEC-044: Skill Authoring Export from Sessions

## Status

- status: `draft`
- owner: luban-platform-team
- created: 2026-08-29
- approved: —
- delivered: —
- release slice: R5 — Hardening and External Consumption (sixth R5
  slice, target v0.26.0)
- related ADRs: none (lineage: skill-authoring spike
  `docs/workspace/skill-authoring-spike.md` promoted by operator
  sign-off 2026-08-29; SPEC-014 skills federation, SPEC-015 fenced
  triage-report contract, SPEC-022/025 session surfaces, SPEC-040
  client-side export, SPEC-043 digest-anchored generation posture)

## Summary

Operators turn a session's troubleshooting into reusable team
knowledge: the platform generates a **skill Markdown draft** from the
session's durable facts, validates it against Skill Format v1 before
it reaches the operator, and hands it over as a client-side `.md`
download for contribution to the team's Git skills repo — already
ingestible through skills-hub federation. The draft is ephemeral:
nothing is persisted on the platform, the artifact of record stays in
Git-managed team knowledge, and the team's review plus skills-hub's
sync remain the only road to live grounded guidance. The platform
drafts; humans merge.

## Motivation

- **The loop is open today.** A session's triage leaves the platform
  only as prose (shift summaries, incident reports) that the agent
  can never ground on, because skills enter exclusively through
  skills-hub's federated sources. The 2026-08-27 operator review
  raised the loop-closer beside the document repository; the spike
  memo answered the draft/validate/export shape and the operator
  signed off on its recommendation.
- **Every leg reuses a shipped pattern.** Digest-anchored generation
  (`document_prose` posture, SPEC-040/043), the fenced-JSON output
  contract (SPEC-015 triage report), the client-side Markdown export
  (SPEC-040 R-4), the Skill Format v1 validation
  (`skills_hub.validate` shares the ingestion code path), and the
  Basic-query internal client posture (SPEC-043 incident client).
- **Fabrication blast radius is bounded by construction.** A
  hallucinated claim merged as a skill would mislead every future
  triage that retrieves it. The draft is generated from the session
  digest only (never raw transcripts), post-processed
  deterministically, validated against the format contract, and
  marked as generated — and it still passes through team code review
  before it can ever ground an agent reply.

## Requirements

Each requirement is stable once the spec is `approved` and carries
testable acceptance criteria.

### R-1: Skill-draft generation in agent-platform

Agent-platform gains a skill-draft generator beside `document_prose`:
one route over the caller's own session that assembles the generation
input deterministically, runs one bounded LLM call, and returns a
Markdown skill draft.

Acceptance criteria:

- New route `POST /api/v2/sessions/{session_id}/skill-draft`,
  server-scoped to the caller's own sessions (foreign ids answer the
  same structural `404` the session surfaces return — ownership by
  404, the house posture).
- The generation input is the **session digest only**: the same
  deterministic session-fact assembly the shift-summary uses
  (sessions, confirmations, executions, evidence counts/handover
  facts), plus the validated triage report when the session is
  incident-linked (fetched through the existing SPEC-043 incident
  client). Raw transcripts, raw alert payloads, and evidence payloads
  never reach the prompt; a regression test asserts the prompt
  builder receives nothing outside the digest bundle.
- The model emits a fenced `skill-frontmatter` JSON block plus the
  Markdown body (the SPEC-015 fenced-contract pattern): frontmatter
  fields are bounded by Skill Format v1 (`title` ≤ 200, `description`
  ≤ 500, ≤ 10 tags, only contract keys). Parse failure or
  out-of-bounds fields degrade to the deterministic skeleton (below),
  never a 500.
- **Facts-only skeleton fallback:** a deterministic draft — contract
  frontmatter derived from the session/incident facts plus
  evidence/outcome tables copied verbatim from the digest — is the
  degradation for any generation or parse failure and is always
  format-valid. The response distinguishes `generated` from
  `skeleton`.
- The response carries the Markdown draft, the generation mode
  (`generated` / `skeleton`), the validation outcome (R-2), and a
  suggested filename slug derived from the title.

### R-2: Validation leg on skills-hub's own code path

The draft is validated against Skill Format v1 **before it reaches
the operator**: an invalid draft is a generation defect, not an
operator problem.

Acceptance criteria:

- skills-hub gains `POST /api/v1/skills/validate` — body: one
  candidate skill document (frontmatter + body); response:
  `valid: true` or `valid: false` with the rejection reason in the
  ingestion report vocabulary. The route calls the same ingestion
  validation functions sync uses (one code path; the CLI
  `python -m skills_hub.validate` stays the operator-side twin). The
  route is read-only: nothing is stored, synced, or emitted.
- The route sits behind skills-hub's existing Basic query-credential
  registry (`SKILLS_QUERY_CLIENTS`); no new auth mechanism.
- agent-platform gains a bounded skills client modeled on the
  SPEC-043 incident client: registered Basic query credential,
  bounded timeout knob, `x-request-id` forwarding, structured error
  mapping; configured by `AGENT_SKILLS_SERVICE_URL`,
  `AGENT_SKILLS_CLIENT_ID`, `AGENT_SKILLS_CLIENT_SECRET` (empty
  default = not configured).
- Validation unavailable (not configured → `503`, unreachable →
  `502`) fails the request — the draft is not returned unvalidated;
  consistency outranks availability on a knowledge-production path.
- A draft that fails validation triggers exactly one bounded
  regeneration with the rejection reason in the prompt; a second
  failure degrades to the facts-only skeleton (which is validated on
  the same path). The response carries `validation: passed` plus the
  mode, so the operator always holds a format-valid file.

### R-3: Policy gate and audit

The gateway gates the new surface behind one new action; the durable
trail gains one new event.

Acceptance criteria:

- New policy action `session:skill_draft` in
  `shared/shared-contracts/policies/policy-default.yaml`, granted to
  `platform-admin`, `approver`, and `operator` (the documents-create
  grant posture: skill authoring is an operational knowledge-production
  act; `developer` and `read-only-observer` are denied by default —
  extending the grant is a deliberate bundle edit). Synced to both
  gateway copies via `make sync-policy`; `make validate-policy` green.
- The gateway enforces `session:skill_draft` and forwards to
  agent-platform; agent-platform re-checks session ownership
  server-side (R-1). The agent layer never trusts the gateway's
  ownership word alone (the SPEC-039 posture).
- New audit event `skill_draft_generated` on the canonical emitter:
  requester, `session_id`, covered `incident_id` when present, mode
  (`generated` / `skeleton`), validation outcome, and the forwarded
  `x-request-id` correlation (SPEC-029 convention). The event joins
  the audit-service event enum and its parity guard; no event is
  emitted for rejected requests (the gateway's blocked-attempt audit
  covers those).

### R-4: Gateway pass-through

The portal reaches the generator through the gateway's v1 surface,
matching the sessions/documents proxy posture.

Acceptance criteria:

- New gateway route `POST /api/v1/sessions/{session_id}/skill-draft`
  in the existing sessions route module: enforces R-3's action,
  forwards the delegated operator identity and `x-request-id`, maps
  structured errors (403/404/502/503) without leaking upstream
  details.
- The response passes the draft, mode, validation outcome, and
  suggested filename through verbatim; the gateway holds no draft
  state.

### R-5: Portal session action and download

The operator reaches the flow from the session surface; the export is
a client-side download.

Acceptance criteria:

- The session actions in the chat view (beside the SPEC-039 R-7
  rename and session-id copy) gain a **Draft as skill** action,
  visible exactly when the caller's role holds `session:skill_draft`
  (the client-side gate mirrors the documents matrix rendering; the
  server re-enforces regardless).
- The action calls the gateway route, shows a busy state during
  generation, and downloads the returned Markdown as
  `<suggested-slug>.md` via the SPEC-040 R-4 client-side Blob
  pattern. The download toast distinguishes the mode (generated vs
  facts-only skeleton) so the operator knows what they hold.
- Dark-theme antd conventions and the zero-deprecation guard hold
  (no deprecated antd APIs; the vitest guard stays green).

### R-6: Provenance marker and content guardrails

Every draft carries its origin and is scrubbed before validation.

Acceptance criteria:

- The draft begins with a deterministic HTML-comment provenance
  block: session id, covered incident id when present, generation
  date, platform version, and the generated/skeleton mode — content
  the team may keep or strip on merge without breaking ingestion
  (comments are body content, not frontmatter).
- The generated body passes deterministic post-processing before
  validation: the gateway's redaction vocabulary applied to the
  model output (the same scrubbing tool output receives), plus the
  Skill Format caps enforced by post-processing regardless of model
  obedience.
- The prompt contract forbids secrets, hostnames, and customer data
  in the draft (the skills-guide content rule); the regression test
  asserts the prompt carries the prohibition and the digest-only
  input bound together.

## Design Decisions

- **Q-1 (input scope and entry point) → digest-only, session entry.**
  The prompt receives the session digest plus the validated triage
  report when the session is incident-linked — never raw transcripts.
  This is the SPEC-043 R-4 posture applied to knowledge production:
  facts are copied verbatim, the model only shapes them. The incident
  report drawer gets no separate entry — its linked session is the
  input, and the operator reaches it from the session surface.
- **Q-2 (validation hosting) → skills-hub route, one code path.**
  Extracting the validator into a shared package collides with the
  shared-sdk spike's recorded revisit triggers; the validate route
  behind the existing query-credential registry reuses the exact
  ingestion code with zero duplication and zero new mechanism.
- **Q-3 (content guardrails) → fenced contract + deterministic
  post-processing.** The model proposes within the fenced
  `skill-frontmatter` contract and writes the body; the platform
  enforces the caps, applies the redaction vocabulary, and validates —
  model obedience is never a safety property (the NO_TOOLS_NOTICE
  lesson).
- **Q-4 (policy action and audit) → `session:skill_draft` +
  `skill_draft_generated`.** Named per the `<resource>:<verb>`
  convention; the grant mirrors `documents:create` (operational
  knowledge production), not the session lifecycle grants, so
  developer/observer stay denied by default. One audit event names
  the full decision-to-draft chain; blocked attempts ride the
  gateway's existing blocked-attempt audit.
- **Q-5 (provenance marker) → deterministic HTML-comment block.**
  Traceability from a merged skill back to the session that seeded
  it, strip-able without breaking ingestion; complements the
  slug-path identity rule that already makes stale citations visible.
- **Ephemeral by construction.** No durable draft record exists
  anywhere on the platform — there is nowhere for a second,
  non-canonical copy of skill content to live (the spike's Option B
  rejection, made structural). The audit event is the platform's only
  trace.

## Non-Goals

- Any platform write path into skills sources — ingestion stays
  Git/local-sync only; team review stays the publication gate.
- A `skill_draft` document type or any document-repository change —
  adjudicated out in the 2026-08-27 review and the spike.
- Draft persistence, versioning, or edit history on the platform.
- Multi-session drafts (several sessions into one skill) — a session
  digest is the input; cross-session authoring stays manual.
- Semantic/automated skill quality scoring or dedup against existing
  skills at draft time (a search-based "similar skills exist" hint is
  a parked future candidate).
- Agent-side access to the generator — the surface is operator-only.

## Impact

- products touched: `products/agent-platform` (skill-draft generator,
  skills validation client, session route, tests),
  `products/skills-hub` (validate route + registry auth, tests),
  `products/platform-gateway` (pass-through route, policy gate,
  tests), `products/operator-portal` (session action + download)
- contracts touched: `shared/shared-contracts/policies/policy-default.yaml`
  (one new rule) plus the two gateway copies via `make sync-policy`;
  the audit-service event enum gains `skill_draft_generated` with the
  SPEC-029 parity-guard members updated; no Skill Format change, no
  session/document contract change
- identity / policy / audit / execution safety impact: one new
  deny-by-default action; ownership stays enforced by 404; one new
  audit event; no execution-path change (no mutating tools, no HITL
  interaction — generation is a read over durable facts)
- deployment: three new agent-platform env knobs
  (`AGENT_SKILLS_SERVICE_URL`, `AGENT_SKILLS_CLIENT_ID`,
  `AGENT_SKILLS_CLIENT_SECRET`) wired in dev-k8s — the agent-platform
  credential joins the skills-hub query-auth registry Secret via the
  existing `sync-skills-secrets.sh` conventions
- living state docs to update on delivery: `docs/guides/skills-guide.md`
  (authoring-from-sessions section), `docs/guides/portal-user-guide.md`,
  `docs/agentic-aiops-platform/authorization-matrix.md`,
  `docs/guides/configuration-reference.md`, `CHANGELOG.md`, release
  note + index

## Open Questions

- none — the design decisions above resolve the spike's Q-1 through
  Q-5 (input scope, validation hosting, content guardrails, policy
  action/audit, provenance marker); approval can proceed on operator
  review of those resolutions.

## Changelog

- 2026-08-29: created as `draft`, promoted from the skill-authoring
  spike (`docs/workspace/skill-authoring-spike.md`) on operator
  sign-off of its Option A recommendation; the memo's Q-1 through
  Q-5 are resolved in the Design Decisions section.
