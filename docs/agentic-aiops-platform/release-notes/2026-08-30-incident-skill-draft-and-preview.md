# v0.27.0 — Incident-Anchored Skill Drafts and Draft Preview (SPEC-045)

Date: 2026-08-30
Release type: feature (seventh R5 slice; one new deny-by-default policy
action, one new audit event type, ephemeral by construction — nothing
about a draft is persisted anywhere on the platform)

## Summary

A triaged incident is team property: any caller holding the new grant can
draft a validated Skill Format v1 Markdown from the incident's validated
triage report — no matter who ran the triage session. The bundle is the
incident envelope (minus the raw failed-triage output) plus the validated
report only; it never touches anyone's session or connector dispatches.
An incident without a validated report answers a deterministic 409 — the
platform never guesses. Both entry points — the new incident action and
the existing chat session action — now open the validated draft in a
read-only preview modal (rendered + raw toggle, mode badge, Download .md
/ Discard) before any client-side download. Everything else reuses the
SPEC-044 generator internals and the SPEC-043 incident client verbatim:
digest-only prompt purity, deterministic redaction and Skill Format caps,
facts-only skeleton degradation (generation never 500s), and fail-closed
validation legs (503 not configured, 502 unreachable).

## What Changed

### Incident-anchored generation (R-1/R-2)

- agent-service gains `POST /api/v2/incidents/{incident_id}/skill-draft`.
  The bundle assembler fetches the incident through the SPEC-043 client
  (one bounded GET, structured 503/502/404 hierarchy), strips
  `triage_raw` and the triage `session_id` from the envelope
  comprehension and `session_id` from the report, and
  raises a typed 409 when no validated report exists — `report is None`
  ⇔ no validated triage report, for new, triaging, and `triage_failed`
  incidents alike.
- Generation rides the same `_validated_draft_sequence` as the session
  anchor: generate → skeleton fallback → assemble → validate → one
  bounded regeneration → skeleton re-validate → 502 if even the skeleton
  fails. The anchor is prompt-visible (the model writes "from the
  validated triage report of one incident") and provenance-visible
  (`incident:` line, no `session:` line). The v0.26.0 session call shape
  stays byte-pinned — the session suite passes untouched.
- A test asserts connector dispatches never enter the prompt input
  (Q-3 guard), and skeleton/provenance/error-mapping classes pin the
  route's postures.

### Policy gate, gateway pass-through, audit (R-3/R-4)

- One new rule `allow-operators-incident-skill-draft` in the canonical
  policy bundle (synced byte-for-byte to both gateway copies and the
  dev-k8s ConfigMap): `incident:skill_draft` granted to
  `platform-admin`, `approver`, and `operator`; `developer`,
  `read-only-observer`, and `auditor` stay denied by default.
- The gateway route is dual-gated exactly like the SPEC-043 incident
  report creation: `incident:skill_draft` evaluates first, then
  `incident:read`; a denial reports the first failing action in the
  standard structured shape. The proxy passes 4xx through (including the
  deterministic 409), rides 502/503 dependency postures verbatim, and
  holds no draft state.
- `incident_skill_draft_generated` joins the audit-service event enum
  with the SPEC-029 parity-guard members (shared
  `audit-event.schema.json`); one event per generation carrying the
  incident id, mode, and validation outcome — emitted regardless of
  whether the operator downloads or discards.

### Shared preview modal and both entry points (R-5)

- New `chat/SkillDraftPreview.tsx`: bounded scrollable read-only modal —
  rendered view through the escape-first renderer (the YAML frontmatter
  fence and provenance HTML comment are display-stripped, since the
  escape-first renderer would otherwise surface them as literal text)
  plus a **Raw** toggle showing the full markdown, a **generated** /
  **facts-only skeleton** mode badge, validation status, and suggested
  filename. **Download .md** hands over the raw markdown via the
  SPEC-040 R-4 Blob pattern; **Discard** drops the in-memory response.
  Nothing is persisted on either path.
- The chat header's **Draft as skill** (SPEC-044) now opens the preview
  instead of downloading blindly; the generated/skeleton toast becomes
  the modal badge, and every existing error toast is kept. The incident
  detail toolbar gains **Draft as skill** beside Run/Re-run triage and
  Continue in chat, visible exactly when the caller's role holds the
  action (client-side mirror; the gateway re-enforces), with structured
  403/404/409/502/503 toasts — the 409 names the precondition: run
  triage first, then draft the skill. The zero-deprecation vitest guard
  stays green.

## Invariants preserved

- An unvalidated draft is never returned (fail-closed 503/502).
- No durable draft record anywhere — preview or download, the platform
  stores nothing; the audit event is the only trace.
- Generation never 500s: any failure degrades to the facts-only
  skeleton, which is always format-valid.
- The incident bundle never includes anyone's session, `triage_raw`, or
  connector dispatches; session-scoped drafting stays owner-only with
  zero backend movement.

## Verification

- agent-platform 735, platform-gateway 276 (incl. the new
  incident-skill-draft proxy class, dual-gate denial-order and 409
  passthrough tests, policy-matrix and route-inventory updates),
  audit-service 92 (enum parity guard), portal 221 vitest tests (incl.
  the preview suite, the migrated session-button suite, and the new
  incident-detail suite) — all green; `make verify` green at 0.27.0
  before and after `make build`.
- Browser live check on aiops.luban.metasync.cc, five scenarios green:
  non-owner (approver) draft + preview + download on an
  operator-triaged incident, 409 precondition toast on an untriaged
  incident, observer denial (hidden button + authenticated API 403),
  preview discard without download, and the session entry still working
  through the preview. Two `incident_skill_draft_generated` audit rows
  persisted for the non-owner drafter.
