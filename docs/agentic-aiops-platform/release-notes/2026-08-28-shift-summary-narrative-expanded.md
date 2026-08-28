# v0.23.2 — Shift-Summary Narrative Opens Expanded

Date: 2026-08-28
Release type: patch (portal presentation polish; no new actions, event
types, or approval-path change)

## Summary

Operator live-test feedback on v0.23.1: the AI-generated handover
narrative in the Documents drawer opened collapsed, so the relieving
operator had to click through before reading the shift story — the one
block they open the document for. v0.23.2 flips the default: the
narrative panel opens expanded and stays collapsible to its header.

## What Changed

### Portal (operator-portal web-ui)

- `ProsePanel` in `DocumentsView.tsx` now renders the narrative
  `Collapse` with `defaultActiveKey` set, so an included narrative opens
  expanded in the document drawer. The label — *AI-generated narrative —
  from this document's digest facts* — is unchanged, as are the failed
  and not-requested states.

### Tests

- The DocumentsView drawer test now asserts the narrative body renders
  immediately (without a click), locking the expanded default while the
  panel remains collapsible.

### Documentation

- The portal user guide's Documents section was corrected: the narrative
  opens expanded rather than collapsed.

## Posture

Presentation only. The digest remains the artifact of record; export,
storage, provenance, audit, and the envelope-only listing posture are
untouched. No policy actions or audit event types change.
