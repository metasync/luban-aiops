# Spike: Skill Authoring Export from Sessions

Status: spike complete — operator sign-off granted 2026-08-29; Option A promoted to SPEC-044 (draft) the same day with the memo's Q-1…Q-5 resolved in the draft's Design Decisions
Date: 2026-08-29
Roadmap home: exploration backlog row "Skill authoring export from sessions" (tracked separately from the SPEC-039 document-type lineage)
Raised by: 2026-08-27 operator review, beside the operations document repository discussion
Verified against: skills-hub, session workspace, and document surfaces at 0.25.2 (SPEC-014/025/031/033/037/039/040/043 as delivered)

## 1. Question

Operators turn a session's troubleshooting and triage into reusable
team knowledge. Today that knowledge leaves the platform only as
prose — a shift summary or an incident report — which the agent can
never ground on, because skills enter exclusively through the
skills-hub's federated Git/local sources. The 2026-08-27 operator
review raised the loop-closer: turn a session's triage into **skill
Markdown that the operator contributes to their own team's Git skills
repo** — already ingestible through skills-hub federation (SPEC-014
lineage, git sources with PAT + subpath). The review deliberately
kept this **out of the document repository**: the artifact of record
must stay in Git-managed team knowledge, and the authoring
experience — session → validated Markdown draft, digest-only
generation posture — is the feature. What shape should
draft/validate/export take, and what is genuinely new versus already
built?

## 2. Findings — verified current state

- **The skill format contract is stable, validated, and pre-flightable.**
  Skill Format v1 (`shared/shared-contracts/skill-format.md` +
  `skill.schema.json`): YAML frontmatter with exactly five keys
  (`title` ≤ 200 and `description` ≤ 500 required; `tags` ≤ 10,
  `version`, `source_url` optional; unknown keys rejected), body
  ≤ 64 KiB, slug derived from file path. Validation is one code path:
  `python -m skills_hub.validate <directory>` runs the same checks
  the service's sync uses, so "validated" has a precise, testable
  meaning today.
- **The authoring input is already durable and assembled.** A session's
  reusable knowledge is reconstructable from the same four stores the
  handover spike catalogued: the transcript (`extract_transcript`),
  `session_evidence` (SPEC-025 tool frames per assistant turn),
  `confirmation_records` (SPEC-031/033), and `execution_records`
  (SPEC-037 signed receipts) — merged by the owner-scoped
  `GET /api/v2/sessions/{id}`. For incident-linked sessions the
  validated triage report (incident-service, SPEC-015) adds a
  machine-checked hypotheses/evidence/next-steps bundle that is the
  single highest-signal seed for a skill body.
- **Digest-anchored generation is a proven pattern.** agent-platform's
  `document_prose.generate_prose` / `build_prose_prompt` generates a
  narrative bounded by the digest's facts, fails soft (generation
  failure degrades to digest-only, never blocks), and renders clearly
  labeled as generated (SPEC-040/043 posture). A skill-shaped prompt
  over session facts is the same leg with a different output contract.
- **Client-side export needs no new plumbing.** SPEC-040 R-4's
  `downloadDocumentMarkdown` downloads a client-assembled Blob; the
  same pattern carries a `.md` skill draft with zero new gateway
  surface for the export itself.
- **There is no write path into skills-hub, and there should not be.**
  The agent reaches skills read-only through tool-gateway; ingestion
  is Git/local-sync only. This is a strength for this feature: the
  team Git repo's review process stays the gate between a generated
  draft and live grounded guidance — the platform drafts, humans
  merge.
- **Fabrication risk is the same as the handover spike's, but with a
  worse blast radius.** A hallucinated claim in a shift summary
  misleads a reader; a hallucinated claim merged as a skill misleads
  **every future triage that retrieves it**. The generation posture
  must therefore be facts-bounded at least as strictly as prose, and
  the draft must be unmistakably marked as generated until a human
  edits and merges it.

## 3. Options considered

### Option A — ephemeral draft: generate → validate → download

A generation endpoint in agent-platform produces a skill Markdown
draft from a session's facts (transcript highlights, evidence,
confirmations/executions outcomes; the validated triage report when
the session is incident-linked), runs it through the skill-format
validation, and returns it for client-side `.md` download (SPEC-040
R-4 pattern). Nothing is persisted; the operator commits the file to
their team's Git skills repo through normal review, and skills-hub
ingests it on the next sync.

- **Pros:** smallest possible surface — one generation route, one
  download action, zero new durable records; the "artifact of record
  stays in Git" posture holds structurally (there is nowhere else for
  it to live); team code review stays the publication gate; every
  leg reuses a shipped pattern (document prose generation, client
  export, skill-format validation).
- **Cons:** regeneration after a failed download or edits is
  stateless (acceptable — drafts are cheap); the platform keeps no
  record of drafts (mitigated by the generation audit event).

### Option B — `skill_draft` document type in the repository

Rejected. The 2026-08-27 review explicitly adjudicated this out: a
draft stored as a document would create a second, non-canonical home
for skill content that diverges from whatever lands in Git, and the
draft→publish lifecycle would imply the platform publishes skills —
which it must not. Documents record what happened; skills are team
knowledge.

### Option C — operator-side authoring only (no generation)

Document the format, point operators at `skills_hub.validate`, and
let them hand-write skills from session memory. Rejected as the
primary shape: the whole value of the ask is that the platform holds
the session facts the operator would otherwise re-type; but the CLI
pre-flight remains part of the recommended shape as the team-side
gate.

## 4. Recommendation

**Promote Option A — generate → validate → download — with three
design constraints.**

1. **Facts-bounded generation.** The skill-shaped prompt is anchored
   on the session's durable facts (and the validated triage report
   when present), in the `generate_prose` posture: generated content
   is clearly labeled, failure degrades to a facts-only skeleton
   (frontmatter + evidence/outcome tables), and nothing in the draft
   may claim data the session records do not contain.
2. **Validation as a leg, not a footnote.** The draft is validated
   against Skill Format v1 before it reaches the operator; an
   invalid draft is a generation defect, not an operator problem.
   The structural decision — where the validation code lives at call
   time — goes to the spec as Q-2 below, with a recommended posture.
3. **The platform drafts; humans merge.** No platform write path into
   skills sources. The export is a file download; the team Git repo's
   review and skills-hub's sync remain the only road to live grounded
   guidance.

### Sequencing rationale

- Every leg is an extension of a shipped pattern: one new generation
  prompt beside `document_prose`, one download action beside SPEC-040
  R-4, validation reused verbatim, audit via the canonical emitter.
- The genuinely new decisions are spec-sized, not spike-blocking:
  input scope, validation hosting, the policy action, and the
  content-guardrail contract (Q-1…Q-5 below).

## 5. Open questions for the spec (not blocking promotion)

- **Q-1 Input scope and entry point.** Which facts seed the draft —
  transcript highlights + evidence + execution outcomes, or digest-
  only (the shift-summary/incident-report posture)? Candidate:
  session-level entry from the session workspace, and a natural
  second entry from an incident report (whose digest already bundles
  the validated triage report).
- **Q-2 Validation hosting.** Recommended posture: skills-hub exposes
  a validate route behind its existing query-credential posture, and
  agent-platform calls it — one code path, no logic duplication. The
  alternative (extract validation into a shared package) collides
  with the shared-sdk spike's recorded revisit triggers and should
  wait for one of them to fire.
- **Q-3 Content guardrails.** The format guide forbids secrets,
  hostnames, and customer data in skill bodies; the spec needs the
  prompt contract plus any deterministic post-processing (e.g. the
  redaction vocabulary the gateway already uses for tool output).
- **Q-4 Policy action and audit.** Candidate: one new operator-level
  action (e.g. `sessions:skill_draft`) and one `skill_draft_generated`
  audit event naming requester, session id, and outcome, correlated
  via the forwarded `x-request-id` convention (SPEC-029).
- **Q-5 Provenance marker in the draft.** Whether the generated file
  carries a provenance comment (session id, generation date) that a
  team may keep or strip on merge — supports the "stale citation"
  traceability the slug rule already builds into skill identity.

## 6. Promotion trigger

Promote to a spec on operator sign-off of this memo's recommendation.
The 2026-08-27 operator ask stands as the recorded demand; the spike
condition (draft/validate/export shape answered) is satisfied by
section 4.

**Resolved 2026-08-29:** operator sign-off granted; Option A promoted
to `SPEC-044-skill-authoring-export` (draft) the same day, with Q-1
(input scope: digest-only, session entry), Q-2 (validation hosting:
skills-hub validate route behind the existing query-credential
registry), Q-3 (content guardrails: fenced contract + deterministic
post-processing), Q-4 (`session:skill_draft` action +
`skill_draft_generated` audit event), and Q-5 (deterministic
HTML-comment provenance block) resolved in the draft's Design
Decisions section.

## Changelog

- 2026-08-29: spike memo drafted from the 2026-08-27 operator review
  backlog row, verified against the 0.25.2 skills-hub, session
  workspace, and document surfaces; recommendation recorded pending
  operator sign-off.
- 2026-08-29: operator sign-off granted; Option A promoted to
  SPEC-044 draft with Q-1…Q-5 resolved in the draft; promotion
  trigger marked resolved.
