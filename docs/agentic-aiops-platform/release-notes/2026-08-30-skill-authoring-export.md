# v0.26.0 — Skill Authoring Export from Sessions (SPEC-044)

Date: 2026-08-30
Release type: feature (sixth R5 slice; one new deny-by-default policy
action, one new audit event type, ephemeral by construction — nothing
about a draft is persisted anywhere on the platform)

## Summary

One new route turns the durable record of a session into a Skill
Format v1 Markdown draft and hands it over as a client-side download.
The generation input is the session's digest bundle only — the same
session-fact assembly the shift summary uses, plus the validated triage
report when the session is incident-linked; raw transcripts, alert
payloads, and evidence payloads never reach the builder. Before a draft
reaches the operator it is validated on skills-hub's own ingestion code
path — an unvalidated draft is never returned. Any generation or parse
failure degrades to a facts-only skeleton that is always format-valid,
so generation never raises a 500. The portal gains a **Draft as skill**
session action; the download toast distinguishes the generated draft
from the skeleton.

## What Changed

### skills-hub validation route (R-2)

- `POST /api/v1/skills/validate` reuses the existing ingestion code
  path (`_validate_frontmatter` via a thin `validate_document`
  wrapper) — no re-implementation. Read-only: no store write, no sync
  trigger, no audit emission. Auth rides the Basic query-credential
  registry (`SKILLS_QUERY_CLIENTS`).
- Fixture-parity tests pin the route and the CLI
  (`ingest_directory`) to identical `(valid, reason)` verdicts over 13
  shared fixtures, so the two surfaces cannot drift.

### Digest-only generation and deterministic guardrails (R-1/R-6)

- New `services/skill_draft.py` in agent-platform: the prompt receives
  the assembled digest bundle JSON and nothing else (signature-bound
  input); the model proposes within a fenced `skill-frontmatter`
  contract, and the platform parses, applies the gateway's redaction
  vocabulary, clamps the Skill Format v1 caps, and validates the
  result on skills-hub — guardrails are deterministic, never model
  obedience.
- Every draft begins with an HTML-comment provenance block: session
  id, covered incident id when present, generation date, platform
  version, and mode — body content the team may keep or strip on merge
  without breaking ingestion.
- One bounded regeneration with the rejection reason in the prompt; a
  second validation failure degrades to the skeleton, validated on the
  same path. Validation legs fail closed: 503 not configured, 502
  unreachable — never an unvalidated draft, never a 500.
- New `services/skills_client.py` (modeled on the SPEC-043 incident
  client) + `AGENT_SKILLS_SERVICE_URL` / `AGENT_SKILLS_CLIENT_ID` /
  `AGENT_SKILLS_CLIENT_SECRET` / `AGENT_SKILLS_CLIENT_TIMEOUT_SECONDS`
  knobs; dev-k8s wires the URL and client id in runtime-config and
  `sync-skills-secrets.sh` adds the agent-service credential to the
  query registry and upserts it into the runtime-profile secret file
  without wiping sibling keys.

### Policy gate, gateway pass-through, audit (R-3/R-4)

- One new rule `allow-operators-skill-draft` in the canonical policy
  bundle (synced byte-for-byte to both gateway copies and the dev-k8s
  ConfigMap): `session:skill_draft` granted to `platform-admin`,
  `approver`, and `operator` — the documents-create grant pattern;
  `developer` and `read-only-observer` stay denied by default.
- platform-gateway passes through
  `POST /api/v1/sessions/{session_id}/skill-draft` with the policy
  gate, delegated-identity forwarding, and structured error mapping
  (403 policy / 404 anti-enumeration / 502+503 verbatim dependency
  postures); the response rides verbatim and the gateway holds no
  draft state.
- `skill_draft_generated` joins the audit-service event enum with the
  SPEC-029 parity-guard members (shared `audit-event.schema.json`);
  agent-service emits on the canonical fire-and-forget emitter with
  session, mode, validation outcome, and the covered incident id when
  present.

### Portal session action and download (R-5)

- The chat header gains **Draft as skill** beside the session-id copy,
  visible exactly when the caller's role holds the action
  (client-side mirror; the gateway re-enforces). Busy state during
  generation; the validated Markdown downloads as
  `<suggested-slug>.md` via the SPEC-040 R-4 Blob pattern; the toast
  distinguishes **generated** from the facts-only **skeleton**;
  structured error toasts for 403/502/503. The zero-deprecation vitest
  guard stays green.

## Invariants preserved

- An unvalidated draft is never returned (fail-closed 503/502).
- No durable draft record anywhere — the response is built in memory
  and downloaded client-side.
- Generation never 500s: any failure degrades to the facts-only
  skeleton, which is always format-valid.
- The prompt input is the digest bundle only; ownership stays
  enforced by the anti-enumeration 404; no execution-path change.

## Verification

- skills-hub 50 tests (incl. the 13-fixture route/CLI parity class),
  agent-platform 714, platform-gateway 266 (incl. the skill-draft
  proxy class, policy-matrix and route-inventory updates),
  audit-service 91 (enum parity guard), portal 202 vitest tests —
  all green; `make verify` green at 0.26.0 before and after
  `make build`.
