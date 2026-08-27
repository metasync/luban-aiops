# v0.21.1 — Document Read Audit Integrity (SPEC-039)

Date: 2026-08-27
Release type: patch (audit-integrity fix on the v0.21.0 document
repository; no new actions, event types, or approval-path change)

## Summary

A same-day code review of the v0.21.0 delivery found that the document
listing (`GET /documents`, both scopes) returned **full rows — digest and
prose included** — while the cross-owner `document_read` audit event only
fires on the single-document fetch. A `documents:read` holder could
therefore read a colleague's published document content straight from the
listing and the portal drawer (which rendered from list results) without
ever landing on the durable trail — contradicting R-5's "cross-owner
reads are always audited". v0.21.1 closes the gap: listings are now
envelope-only, and the portal retrieves the full document through the
audited single fetch, making it the only path to document content.

## What Changed

### Envelope-only listings (agent-service)

- `GET /documents` strips `digest` and `prose` from every row in both
  the `mine` and `published` scopes; the single fetch keeps serving the
  full document and remains the audited surface. Shared contract
  `operation-document.schema.json` description documents the envelope vs
  full-document distinction.

### Audited fetch in the portal drawer

- The Documents view drawer no longer renders from list rows: opening a
  document issues `GET /documents/{id}` (with abort-on-close) and shows
  a spinner until the full document arrives — so every cross-owner read
  a colleague performs through the portal emits `document_read`
  attributed to the reader.

### Docs

- Portal guide: corrected the deletion wording — owners may delete their
  own published documents (they disappear for everyone); document content
  is never edited after creation, publishing only changes visibility.
- Portal guide: added the "Your first shift summary" get-started
  walkthrough (create dialog → digest review → publish).

## Verification

- New regression test `test_list_rows_are_envelope_only` pins both list
  scopes to envelope rows while the single fetch keeps carrying the full
  document (agent-platform suite green).
- `make verify` green at 0.21.1.
- Live check: rebuilt and redeployed to the dev cluster;
  `shared/platform-ops/e2e/documents-demo.sh` passes, now additionally
  asserting the published listing carries no digest/prose content while
  the cross-owner `document_read` stays on the durable trail.
