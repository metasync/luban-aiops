# Spike: Cross-Owner Session Review and Shift-Summary Artifacts

Status: spike complete — operator sign-off granted 2026-08-27; Option B (shift-summary artifact) promoted to SPEC-039 draft the same day; Option A parked behind its recorded trigger
Date: 2026-08-27
Roadmap home: exploration backlog rows "Cross-owner session review" and "Shift-summary artifacts" (paired candidates; promoted together per the SPEC-035 open question)
Raised by: v0.16.0 live approval test (SPEC-035 open question); re-stated by SPEC-036 non-goals
Verified against: session workspace and approval surfaces at 0.20.0 (SPEC-022/025/031/033/036/037 as delivered)

## 1. Question

Operators running incident review and 7x24 roster handover need context
from work done by **another** operator. Today every session surface is
strictly owner-scoped: foreign session ids answer `404`
(anti-enumeration), and the inbox deliberately serves metadata only.
The SPEC-035 open question parked two candidate directions — a
read-only cross-owner session review surface (agreed direction:
role-gated, read-only, audit-logged) and an agent-generated
shift-summary artifact — and discouraged session inheritance
(never-expiring sessions, ambiguous HITL ownership). What is already
in place, what does each candidate actually cost, and which one
should be promoted first?

## 2. Findings — verified current state

- **All handover-relevant facts are already durable and attributed.**
  A session's story is reconstructable today from four stores on the
  shared Postgres posture: the kernel state snapshot (transcript,
  reconstructed by `extract_transcript`), `session_evidence`
  (SPEC-025 tool frames grouped by assistant turn),
  `confirmation_records` (SPEC-031 — decision, decider, timestamps,
  SPEC-033 turn anchoring), and `execution_records` (SPEC-037 —
  signed requests, receipts, first-write-wins). The owner transcript
  view already merges all four (`GET /api/v2/sessions/{id}`).
- **Cross-user visibility exists exactly once, and it is
  metadata-only.** The approvals inbox (SPEC-031 R-3) lets designated
  approvers see another operator's parked requests — metadata only,
  never transcript text (SPEC-030 Q-1 posture) — behind the
  `approvals:list` policy action. That is the only existing precedent
  for crossing the owner boundary, and it is deliberately narrow.
- **Ownership is enforced by 404, not 403.** `_assert_session_owner`
  answers `404` for foreign ids so foreign session ids stay
  indistinguishable from unknown ones. Any cross-owner surface must
  be a **separate, role-gated endpoint family** — never a relaxation
  of the owner check on the existing routes.
- **The audit substrate is ready.** The canonical fire-and-forget
  emitter and the forwarded `x-request-id` correlation convention
  (SPEC-029 pattern) make an audited cross-owner read event a small
  addition, not new infrastructure.
- **Summary generation has an untested dependency.** An
  LLM-generated summary over a transcript means feeding operator
  conversation content back through the model with a summarization
  prompt. That works for triage (SPEC-017 structured output proves
  the mechanics) but introduces fabrication risk on a surface whose
  whole purpose is trustworthy handover.

## 3. Options considered

### Option A — cross-owner session review (full read-only exposure)

A role-gated read-only endpoint family exposing another operator's
session list and detail (transcript + evidence + confirmations +
executions), with every read emitting an audited event naming reader,
owner, and session.

- **Pros:** maximum fidelity — reviewers see exactly what happened;
  no generation step, so nothing can be fabricated; reuses the
  existing session-detail assembly almost verbatim.
- **Cons:** the hard exposure decision lands immediately and
  unresolved: which roles can read whose sessions (all sessions of
  all operators is a significant privacy posture change); every raw
  transcript becomes reviewable content (including half-formed
  hypotheses and sensitive identifiers the operator typed); and the
  HITL ambiguity remains — a reviewer looking at someone else's
  parked confirmation can neither decide it (decider roles are
  separate) nor should inherit it.

### Option B — shift-summary artifact (agent-generated digest)

A durable per-shift (or per-session-set) artifact summarizing what
happened: sessions touched, questions answered, confirmations parked
and decided with decider attribution, executions with receipt status,
and open items still pending. The reviewer reads the artifact, not
the raw sessions.

- **Pros:** structurally lower-risk — it sidesteps the raw-transcript
  exposure decision almost entirely; the artifact's scope is
  handover context, which is what the operational ask actually
  describes (incident review recap and roster handover); it is the
  smaller surface to build (one generation path + one durable record
  + one read view).
- **Cons:** an LLM prose layer can misrepresent the underlying
  records; provenance must be anchored so every claim traces to a
  session/record; and if reviewers still need raw sessions after
  reading the summary, Option A gets built anyway (the summary then
  becomes its index page, which is fine).

### Option C — session inheritance

Rejected. Already discouraged in the SPEC-035 open question:
never-expiring sessions and ambiguous HITL ownership of another
operator's parked confirmations. The reviewer should never become the
implicit owner of someone else's pending approvals.

## 4. Recommendation

**Promote the shift-summary artifact first (Option B), with one
design constraint: the artifact is a deterministic digest with an
optional clearly-labeled prose layer — never prose alone.**

The trustworthy core of the artifact is assembled **mechanically from
the durable records** (sessions, confirmations, executions, evidence
counts) so that nothing in the trusted section can be fabricated —
the same posture that keeps the inbox metadata-only and the receipts
signed. An LLM-generated narrative section may ride alongside it for
readability, but it must be visually and structurally marked as
generated, carry no more authority than a chat reply, and the
artifact must list the exact session ids and record ids it covers so
every claim is traceable (provenance anchoring).

**Park cross-owner session review (Option A) behind a recorded
trigger:** promote it on the first concrete operational need to
inspect raw sessions that the summary cannot satisfy. If that day
comes, the artifact's provenance index doubles as its natural entry
point.

### Sequencing rationale

- Option B answers the stated operational need (incident review
  recap, 7x24 handover) with the smallest privacy footprint change.
- It reuses the four existing durable stores and the audit emitter;
  the genuinely new decisions are the artifact's retention/ownership
  (who owns a summary that covers several operators' sessions) and
  its generation posture — both spec-sized, not spike-blocking.
- Option A's blocking question — which roles may read whose raw
  transcripts — is a governance decision that should not be rushed
  while the cheaper artifact has not been tried.

## 5. Open questions for the spec (not blocking promotion)

- **Q-1 Artifact ownership and audience.** Who may request a summary
  covering other operators' sessions, and who owns the resulting
  record — the requester, the shift, or the platform? Candidate
  posture: request behind a policy action (e.g. `shifts:summarize`),
  artifact readable by the requesting role, generation audited.
- **Q-2 Audit posture.** At minimum one `shift_summary_generated`
  event naming requester, covered session ids, and record counts;
  cross-reference via forwarded `x-request-id` per the SPEC-029
  correlation convention. Decide whether reads of the artifact also
  audit.
- **Q-3 Prose-layer guardrails.** Which model generates the prose
  section, what prompt contract bounds it to the digest facts, and
  how the portal renders the generated/verified split. A failed prose
  generation must degrade to digest-only, never block the artifact.
- **Q-4 Retention.** Artifact lifetime relative to the underlying
  sessions (it must not outlive the records it cites, or must mark
  them as aged out).

## 6. Promotion trigger

Promote Option B to a spec when the operator signs off on this memo's
recommendation. Option A stays parked: promote on the first concrete
operational need to read another operator's raw sessions that the
shift-summary artifact cannot satisfy.

**Resolved 2026-08-27:** operator sign-off granted; Option B promoted
to `SPEC-039-shift-summary-artifacts` (draft) the same day with the
memo's Q-1 through Q-4 resolved in the draft's Design Decisions
section. Option A remains parked behind the trigger above.

## Changelog

- 2026-08-27: spike memo drafted from the SPEC-035 open question and
  the SPEC-036 restatement, verified against the 0.20.0 session
  workspace and approval surfaces; recommendation recorded pending
  operator sign-off.
- 2026-08-27: operator sign-off granted; Option B promoted to SPEC-039
  draft; promotion trigger marked resolved.
