# v0.25.1 — Portal Live-Check Polish

Date: 2026-08-29
Release type: patch (follow-up to the v0.25.0 live check; operator
portal rendering and documentation polish only — no backend runtime
behavior, routes, actions, event types, or dependency versions change)

## Summary

The post-release live check of v0.25.0 returned six feedback points.
Two needed no code (incident reports already carry the AI one-liner
and the digest-anchored narrative — the e2e documents were simply
created with `include_prose=false`), one needed only a name, and the
rest were portal rendering and documentation polish. This patch
delivers the rendering and documentation changes.

## Pinned chrome for bounded panes

The fixed-height bound on long digest and narrative blocks previously
wrapped the whole pane, so the tab bar (digest) and the collapse
header (narrative) scrolled away with the content. The bound now
applies to the content region only:

- the digest's tab bar stays pinned; only the active tab's content
  scrolls inside the bound (`.digest-bounded .ant-tabs-body-holder`);
- the narrative's collapse header stays pinned; only the narrative
  body scrolls inside the bound (`.prose-bounded .ant-collapse-body`).

Releasing the bound removes the class entirely, so expanded panes
render with no height constraint. The *Expand to full height*
affordance stays on both document types and appears only when the
content actually overflows the bound; overflow detection re-measures
after antd's enter motion settles, so the affordance appears reliably
the first time long content is revealed (browser verification caught
and fixed a pre-motion measurement race). Bounding remains
presentation only — content, export, and the stored document are
untouched.

## Raw JSON → Digest data

The last tab of both document types is renamed **Digest data**. The
tab has always rendered the stored digest through the typed renderers
with a typed-but-open fallback (SPEC-041 R-2) rather than a JSON
dump; the name now says what the tab shows. Rendering is unchanged —
the complete stored digest, field by field, remains the artifact of
record, inspectable in place.

## House layout rule, codified and audited

The digest reference gains a **How the tabs lay out content** section
fixing one mechanical rule: repeated records sharing scalar fields
render as tables; a single object renders as a description list;
heterogeneous or long-text items render as bullets; identifiers and
short labels render as chips. Auditing the existing tabs against the
rule changed one: the incident report **Triage** tab now renders
evidence and next steps as tables (they are repeated records with
shared scalar fields), keeps hypotheses as bullets, and renders cited
skills as chips. Every other tab already satisfied the rule.

## What does not change

- No backend route, action, event type, approval path, or audit
  change; no dependency version moves.
- The stored digest shape, the audited fetch, and the Markdown export
  are untouched — every change here is portal rendering and docs.
- Version lockstep only: every product and the portal report 0.25.1.

## Verification

- Portal suite green: 18 files / 189 tests (`vitest run`), including
  the bounded-pane expansion test re-anchored on the new antd v6
  content-region classes and new triage layout assertions.
- `tsc --noEmit` clean.
- Full `make verify` suite green before deploy; live browser
  verification of pinned tab bar, pinned narrative header, the expand
  affordance, and the Digest data tab on a document with narrative.
