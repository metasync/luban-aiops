# v0.22.0 — Shift-Summary Handover Narrative and Export (SPEC-040)

Date: 2026-08-28
Release type: feature (second R5 slice, extending the SPEC-039 document
repository; no new policy actions, no new audit event types)

## Summary

Operator feedback on the v0.21.0/0.21.1 document repository identified
two gaps: the shipped digest is a pile of receipts without the story —
the relieving operator cannot tell what happened in the shift — and the
Documents view sat under Control although shift handover is an everyday
workspace activity. v0.22.0 delivers SPEC-040: a deterministic
`handover` digest section that tells the shift story without a model in
the loop, the generated narrative flipped to default with a tightened
digest-anchoring prompt contract, the Documents entry moved to
Workspace, and a client-side Markdown export for offline handover.

## What Changed

### Deterministic handover section (agent-service, R-1)

- Every shift-summary digest now carries a `handover` section assembled
  mechanically from the per-session entries: covered/own/foreign session
  counts, own-coverage decisions (action, decision, decider, time) and
  execution outcomes (tool, receipt status, completion time) with stable
  sorting, still-open items and the sessions that hold them, and an
  honest `quiet` flag when the shift recorded no decisions or
  executions. Foreign sessions stay counts-only — never titles or
  details — and degraded sources contribute nothing, so the section
  degrades with the rest of the digest instead of failing creation.
  Old documents keep their original digests (documents are immutable);
  new digests are additive, with a description-only note on
  `operation-document.schema.json`.

### Narrative as the default, digest-anchored (agent + portal, R-2)

- `include_prose` now defaults to true; the portal create dialog's
  switch becomes the opt-out. The prompt contract keeps its guardrail
  (the model sees the assembled digest JSON only) and gains explicit
  anchoring rules: state only facts present in the digest, tie each
  statement to its digest section, never introduce record ids, causes,
  or recommendations the digest does not contain, and report a quiet
  shift plainly. Fail-soft semantics are unchanged — a generation
  failure ships a digest-only document (`prose_status=failed`).
- The portal panel is relabeled *AI-generated narrative — from this
  document's digest facts*.

### Documents moved to Workspace (portal, R-3)

- The Documents entry moves from the Control section to Workspace; role
  gating (the `documents:read` authoring-roles mirror) and every route
  permission are unchanged.

### Client-side Markdown export (portal, R-4)

- The document drawer gains *Export .md*: metadata, provenance, the
  digest as fenced JSON, and the narrative when included (a failed
  narrative exports the digest alone). Export serializes the document
  the drawer already fetched through the audited single-read surface —
  no gateway call, no policy action, and no new audit event type. A
  server-side export endpoint was explicitly rejected: it would add a
  parallel read path for zero new capability.

## Verification

- New `TestHandoverSection` pins determinism, the two-tier foreign
  counts-only posture, the quiet-shift empty state, open items, and
  degraded-source assembly; the route-created document assertion
  requires the `handover` skeleton; the prompt-contract test asserts
  the R-2 anchoring rules; the portal suite covers the narrative
  default, the drawer export affordance, and the Markdown serializer
  (agent-platform 612 tests green; portal suite green).
- `make verify` green at 0.22.0.
- Live check: rebuilt and redeployed to the dev cluster;
  `shared/platform-ops/e2e/documents-demo.sh` passes, now asserting the
  created digest carries the `handover` section, plus the browser
  walkthrough (Documents under Workspace, narrative default, drawer
  export).
