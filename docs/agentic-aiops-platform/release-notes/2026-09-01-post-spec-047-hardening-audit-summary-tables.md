# Post-SPEC-047 Hardening: Audit Summary Bucket Tables (v0.29.1)

Date: 2026-09-01

Patch hardening batch on top of the SPEC-047 delivery (v0.29.0),
prompted by operator review of the live Summary tab on the canonical
deployment. One component touched — `AuditSummaryPanel.tsx` — no API,
contract, route, policy, or test-posture changes.

## What the live check surfaced

- The SPEC-047 share cell rendered a percentage and a thin progress
  bar in one inline-flex span. At live table widths the cell column
  was squeezed by antd's width distribution, so the span wrapped onto
  multiple lines.
- The progress bar itself carried little signal at 4px height and a
  15% track, and the `name` column absorbed the table width unevenly.

## What changed

- **Progress bar retired.** SPEC-047 R-4's proportion survives as the
  one-decimal percentage only, still computed by the one shared
  deterministic formatter; the share cell is now a single
  right-aligned, non-wrapping value. The pie-chart alternative raised
  in the same review was adjudicated and withdrawn by the operator in
  favor of the compact table.
- **Fixed numeric tracks.** The bucket tables switch to a fixed
  layout with narrow fixed-width, right-aligned count and share
  columns, so the `name` column — the only variable-content column —
  absorbs the width evenly and the rows read compactly.

## Untouched

Drill-down from every aggregate value, the statistic row, the
default-expanded collapse, the zero-total empty posture, the outcome
filter dimension end-to-end, and all 259 portal tests (green
unchanged). Version lockstep 0.29.1 validated across all products and
the portal; `make verify` green before and after `make build`.
