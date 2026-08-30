# SPEC-045: Incident-Anchored Skill Drafts and Draft Preview

## Status

- status: `delivered`
- owner: luban-platform-team
- created: 2026-08-30
- approved: 2026-08-30
- delivered: 2026-08-30
- release slice: R5 — Hardening and External Consumption (seventh R5
  slice, target v0.27.0)
- related ADRs: none (lineage: the 2026-08-30 post-delivery design
  exchange on SPEC-044 — operator adjudicated the two-use-case split
  (incident-anchored drafts without session ownership; session-scoped
  drafts stay owner-only) and the preview-before-download experience;
  extends SPEC-015 incident triage sessions, SPEC-043 incident bundle
  client, SPEC-044 skill authoring export)

## Summary

SPEC-044 shipped skill drafting anchored to the caller's own session.
The operator's mental model for *why* a session becomes a skill,
however, starts one step earlier: repeated troubleshooting steps and
well-worn techniques are visible on the **incident** — the operator
re-reads the triage report and decides it deserves to become a
runbook. Two follow-ups, adjudicated 2026-08-30:

1. **Incident-anchored drafting.** The incident detail page gains
   **Draft as skill** beside *Run/Re-run triage* and *Continue in
   chat*. The draft is generated from the incident envelope plus the
   **validated triage report** — never from anyone's session — so the
   flow never touches session ownership: any role that can read the
   incident and holds the new action can convert its triage, no
   matter who ran it. The session-scoped route stays exactly as
   delivered (owner-only) — two separate use cases, two separate
   anchors.
2. **Preview before download.** Both entry points open a preview of
   the validated draft — rendered markdown with a raw toggle, the
   mode badge (generated vs facts-only skeleton), the validation
   status — and the operator chooses **Download .md** or **Discard**.
   Nothing is persisted either way; Cancel is free by construction.

Everything else is inherited from SPEC-044 and holds unchanged: the
draft is validated on skills-hub's own ingestion code path before it
is shown (an unvalidated draft is never surfaced, preview included),
generation never raises a 500, deterministic post-processing
(redaction vocabulary + Skill Format v1 caps) applies on every path,
and the artifact of record stays in the team's Git skills repo — the
platform drafts, humans merge.

## Requirements

### R-1: Incident-anchored generation in agent-platform

Agent-platform gains an incident-scoped skill-draft generator beside
the SPEC-044 session-scoped one:

- The generation input is the **incident bundle only**: the incident
  envelope (with `triage_raw` and the triage `session_id` stripped —
  the raw, unvalidated agent output never reaches the builder, and
  the draft never names anyone's session) plus the **validated triage
  report**. The bundle is fetched through the existing SPEC-043
  incident client (one bounded GET, Basic query credential,
  structured error hierarchy) — no new client, no new knobs.
  Connector dispatch outcomes are **excluded** (adjudicated: the
  skill captures the diagnostic technique, not the action history;
  the dispatch leg stays parked).
- The prompt posture, fenced `skill-frontmatter` contract, parser,
  deterministic post-processing (redaction vocabulary, Skill Format
  v1 caps), and facts-only skeleton are **reused verbatim** from the
  SPEC-044 generator — the incident variant supplies a different
  bundle, not different guardrails. Generation never raises a 500:
  any failure degrades to the facts-only skeleton assembled from the
  same incident facts, which is always format-valid.
- **Triage-required gate.** The whole point of this use case is
  converting a validated triage into a skill. An incident without a
  validated triage report (`new`, `triaging`, or `triage_failed`)
  answers a deterministic structured **409** ("no validated triage
  report to draft from") before any generation work — never a thin
  guess, never a 500.
- The provenance HTML-comment block carries the **incident id** (no
  session id), generation date, platform version, and mode — the same
  strip-safe shape as SPEC-044 R-6. The suggested filename slug
  derives from the incident title with the existing sanitization.
- Route: `POST /api/v2/incidents/{incident_id}/skill-draft` with the
  delegated `X-User-ID`; response shape identical to the session
  route (`{markdown, mode, validation, suggested_filename}`).
  Nothing is persisted.

### R-2: Gateway pass-through and error mapping

Platform-gateway adds `POST /api/v1/incidents/{incident_id}/skill-draft`
on the incidents router:

- Dual-action gate: **`incident:skill_draft`** **and**
  **`incident:read`** — the SPEC-043 incident-report pattern, so the
  skill-draft surface never bypasses the incident visibility matrix.
  Denials report the first failing action in the standard structured
  shape; blocked attempts ride the gateway's existing blocked-attempt
  audit.
- Delegated-identity and `x-request-id` forwarding; verbatim response
  pass-through; the gateway holds no draft state.
- Structured error mapping: 403 policy / 404 unknown incident id
  (anti-enumeration) / 409 no validated triage report (passed
  through with its structured detail) / 503 dependency not configured
  (incident client or skills validation) / 502 transport or upstream
  5xx — never a 500, never an unvalidated draft.

### R-3: Policy gate and audit

- One new rule `allow-operators-incident-skill-draft` in the
  canonical policy bundle (synced byte-for-byte to both gateway
  copies and the dev-k8s ConfigMap): `incident:skill_draft` granted
  to `platform-admin`, `approver`, and `operator` — the
  session-skill-draft grant pattern. `developer` and
  `read-only-observer` stay denied by default (they keep
  `incident:read`, so the dual gate's second leg alone never
  admits them).
- One new audit event `incident_skill_draft_generated` joins the
  audit-service enum and the shared `audit-event.schema.json` under
  the SPEC-029 parity guard; agent-service emits it on the canonical
  fire-and-forget emitter with the requester, incident id, mode,
  validation outcome, and the forwarded `x-request-id`. The session
  route's `skill_draft_generated` event is untouched — two entry
  points, two explicit events.

### R-4: Portal incident-detail action

The incident detail toolbar gains **Draft as skill** beside
*Run/Re-run triage* and *Continue in chat*:

- Client-side visibility mirrors the policy grant exactly (the
  gateway re-enforces); busy state during generation; structured
  error toasts for 403 / 404 / 409 / 502 / 503 — the 409 toast names
  the cause ("run triage first — a validated triage report is
  required").
- On success the preview opens (R-5) — the incident entry point never
  downloads blindly.

### R-5: Skill-draft preview before download

Both entry points (chat header and incident detail) route their
response through one shared preview surface:

- A bounded, scrollable modal renders the draft: **rendered markdown
  view by default with a raw-markdown toggle** (the provenance block
  is an HTML comment, so the raw view is where it shows), a **mode
  badge** (*generated* vs *facts-only skeleton*), the validation
  status, and the suggested filename.
- **Download .md** (primary) performs the existing SPEC-040 R-4
  client-side Blob download of the raw validated markdown;
  **Discard** closes and drops the in-memory response. Nothing is
  persisted on either path — the preview never becomes a durable
  draft record.
- The preview is **read-only**: no in-platform editing. Editing
  belongs in the team's Git flow ("the platform drafts, humans
  merge"); edit-then-revalidate on download is parked behind the
  promotion triggers below.
- The zero-deprecation vitest guard stays green.

### R-6: Session surface unchanged (the two-use-case split)

The session-scoped route, policy action, audit event, and chat
header button ship in v0.26.0 stay exactly as delivered:

- Drafting from a session remains owner-only (ownership-by-404). The
  chat workspace lists only the caller's own sessions, and a foreign
  incident session deep-linked via *Continue in chat* cannot load
  its transcript for a non-owner — so the session button is never
  offered on a session the caller does not own. No backend movement.
- An operator who does **not** own an incident's triage session uses
  the incident entry point (R-4) instead — the incident-anchored
  draft needs no session at all, which is precisely why it exists.
- The session-scoped bundle keeps its incident leg (validated triage
  report when the session is incident-linked); the two anchors
  compose without overlap.

## Design Decisions

The 2026-08-30 design exchange (post-v0.26.0 delivery review)
resolved the open questions:

- **Q-1: Which entry shape for the incident use case?** Options were
  (a) visibility-gated session button, (b) graceful denial, (c)
  incident-anchored drafting. **Resolved: (c) implemented for the
  incident use case, (a) kept for the session use case** — two
  separate use cases with separate anchors. (c) matches the
  operator's stated mental model (review the incident and its
  triage, then convert), never touches session ownership, and works
  even when the triage session belongs to another operator — the
  exact 404 the live check surfaced.
- **Q-2: What if the incident has no validated triage report?**
  **Resolved: deterministic 409.** This use case converts *triage*
  into a skill; an envelope-only guess would be a thin artifact the
  team would discard anyway, and a `triage_failed` record's raw
  output is purity-forbidden input. Run triage first.
- **Q-3: What rides the generation bundle?** **Resolved: envelope
  (minus `triage_raw` and the triage `session_id`) + validated
  triage report only.** Connector dispatches are action history,
  not diagnostic technique — parked with a promotion trigger. The
  digest-only purity invariant holds: raw alert payloads and
  unvalidated agent output never reach the builder.
- **Q-4: Preview shape.** **Resolved: read-only modal, rendered +
  raw toggle, mode badge, Download .md / Discard.** Labels avoid a
  bare "Save" — the platform stores nothing; the artifact downloads
  to the operator's machine en route to the team's Git repo. Cancel
  is free by construction (ephemeral response, no record).
- **Q-5: Does preview change the audit?** **Resolved: no.**
  Generation remains the truthful platform fact; whether the
  operator downloads or discards afterwards is a client-side act the
  platform cannot honestly attest. One event per generation, on both
  entry points (typed per R-3).
- **Q-6: One action or two?** **Resolved: new `incident:skill_draft`
  action.** The resource is the incident, the verb matches the
  session sibling; the dual gate with `incident:read` mirrors
  SPEC-043 exactly. Reusing `session:skill_draft` for a
  session-less route would misname the resource in every policy and
  audit surface.
- **Q-7: Editing in the preview?** **Resolved: parked.** In-platform
  editing would shift "humans merge" into the portal; the W-1
  validate route could support edit-then-revalidate later if
  operators ask. Promotion trigger recorded in the plan's risks.

## Invariants preserved

- An unvalidated draft is never surfaced — not in a download, not in
  a preview (fail-closed 503/502).
- No durable draft record anywhere — preview and discard are both
  in-memory; the audit event remains the platform's only trace.
- Generation never 500s: any failure degrades to the facts-only
  skeleton; a missing triage report answers a deterministic 409.
- Digest-only generation input: envelope without `triage_raw` or the
  triage `session_id` plus the validated triage report — raw alert
  payloads, unvalidated agent output, session identifiers, and
  session transcripts never reach the builder.
- Session ownership is untouched: the incident surface is incident
  visibility, never session access; the session surface stays
  owner-only.

## Impact

- `docs/guides/skills-guide.md` — incident entry point and the
  preview step in the authoring-from-sessions section.
- `docs/guides/portal-user-guide.md` — incident detail actions and
  the preview/download flow.
- `docs/guides/incident-guide.md` — the new toolbar action beside
  Run/Re-run triage and Continue in chat.
- `docs/agentic-aiops-platform/authorization-matrix.md` — the
  `incident:skill_draft` dual gate and the new audit event.
- `docs/guides/configuration-reference.md` — no new knobs (the
  incident client and skills validation are already wired).

## Parked / promotion triggers

- Connector dispatch outcomes in the incident bundle (Q-3) — promote
  if operators want the action history reflected in drafted skills.
- Edit-then-revalidate in the preview (Q-7) — promote on the first
  operator ask; the skills-hub validate route already supports it.
- Session-transcript awareness in the incident-anchored draft — the
  two anchors compose; a combined "incident + my session" bundle is
  a distinct future shape, not this slice.

## Changelog

- 2026-08-30: created as `draft` from the post-v0.26.0 design
  exchange; the operator adjudicated the two-use-case split
  (incident-anchored option (c) + session-scoped option (a)) and the
  preview-before-download experience the same day.
- 2026-08-30: operator approved the draft (`draft` → `approved`);
  delivery proceeds under the house train as v0.27.0.
- 2026-08-30: delivered as v0.27.0 (`approved` → `delivered`) —
  incident-anchored route + dual-gated gateway pass-through + audit
  event, shared preview modal with both entry points rewired through
  it, session surface byte-untouched; `make verify` green before and
  after `make build`, browser live check 5/5 scenarios on the
  canonical deployment (non-owner draft + preview + download, 409
  precondition, observer denial, discard, session entry).
- 2026-08-30: post-delivery code & doc review found the envelope
  comprehension stripped `triage_raw` but not the triage `session_id`
  (the purity fixture omitted the field, masking the gap); remediated
  as v0.27.1 — envelope strip extended, fixture and purity assertion
  hardened, this spec's bundle wording corrected to match.
