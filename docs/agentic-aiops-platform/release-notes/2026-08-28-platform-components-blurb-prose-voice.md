# v0.23.3 — Platform Components Table, Document Blurb, and Prose Voice

Date: 2026-08-28
Release type: patch (operator polish; additive document field, prompt
retune, and a read-only Settings surface — no new actions, event types,
or approval-path change)

## Summary

Three polish items from operator live-test feedback:

1. The Settings Platform tab should help operators, users, and
   developers understand the running platform, not just its portal
   version.
2. The AI one-liner summary was remembered but missing from the
   Documents list, and belongs on the detail card too.
3. The generated handover prose read dry and long; it should brief a
   peer, not file a status report.

## What Changed

### Settings: key platform components (operator-portal web-ui)

- The Platform pane keeps its version / API origin / request-id block
  and adds a **Key platform components** table beneath it: operator
  portal, platform gateway, agent service, agent runtime (LLM provider
  and model), session store, agent-state store, and policy bundle —
  each with its version/backend and a readiness status.
- The table is a live read of two endpoints that are unauthenticated by
  design: the gateway's `/health/ready` (gateway version and status,
  agent-service health, store backends and readiness, policy rule
  count) and `/api/v1/runtime` (provider, model, runtime state).
- Every row degrades to *unavailable* when its probe fails — nothing is
  guessed or cached.

### Documents: the AI one-liner (agent-platform + portal)

- Narrative generation now asks for exactly one `SUMMARY:` line ahead
  of the recap; `parse_blurb()` extracts it as the document's **blurb**
  (bounded to 240 characters) and stores it as an additive nullable
  `blurb` column plus a contract schema property.
- The blurb rides the envelope-only list rows, appears on list rows and
  the detail card (falling back to the SPEC-041 counts-only summary),
  and leads the Markdown export.
- Audit posture is preserved: the digest handed to the prose model is
  already coverage-scoped (foreign sessions counts-only), so a
  digest-anchored one-liner is safe in un-audited listings; full
  digest and prose still require the audited single fetch.

### Prose voice (agent-platform)

- The narrative prompt is retuned to an operator-briefing voice: lead
  with what the relieving operator inherits, at most three short
  paragraphs (~150 words total, down from six), counts woven in only
  where they carry meaning.
- All SPEC-040 R-2 anchoring guardrails are unchanged: digest-only
  input, section-tied facts, no invented ids/causes/recommendations,
  and the honest quiet flag.

### Tests

- SettingsView: component-table rendering from stubbed health probes,
  and degradation to *unavailable* when probes fail.
- DocumentsView: blurb on the list row ahead of the counts-only
  summary, on the detail card, and leading the Markdown export.
- document_prose / operation_documents / documents: the 3-tuple
  `generate_prose` contract, `parse_blurb` edge cases (marker handling,
  bounds, empty input), the blurb column and migration, and prompt
  assertions for the new voice.

## Posture

Additive and presentational. No new policy actions, audit event types,
or approval semantics; the digest remains the artifact of record and
the envelope-only listing posture is unchanged.
