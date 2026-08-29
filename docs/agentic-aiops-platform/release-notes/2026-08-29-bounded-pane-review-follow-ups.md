# v0.25.2 — Bounded-Pane Review Follow-Ups

Date: 2026-08-29
Release type: patch (code-review follow-ups on the v0.25.1 portal
polish; operator portal rendering and tests only — no backend runtime
behavior, routes, actions, event types, or dependency versions change)

## Summary

The v0.25.1 code review passed with two minor follow-ups. This patch
closes both: the bounded-pane height is now single-sourced, and the
post-motion re-measure race fix gains a dedicated regression test.

## Single-sourced bounded-pane height

The 320px bound previously lived in two places: the CSS rules in
`global.css` and the `BOUNDED_PANE_MAX_HEIGHT` constant driving the
overflow comparison in `DocumentsView.tsx`. The view now sets a
`--bounded-pane-max-height` custom property on each bounded wrapper
(from the same constant), and the `.digest-bounded` /
`.prose-bounded` rules consume it — the presentation bound and the
affordance logic can no longer drift apart.

## Regression test for the first-reveal race

The v0.25.1 fix for the antd enter-motion measurement race (a delayed
re-measure so the *Expand to full height* affordance appears on first
reveal of long content) was previously covered only by live browser
verification. A fake-timer test now pins it: with the immediate
measurement reading a pre-motion height, the affordance must appear
only once the delayed re-measure runs.

## Validation

- Portal suite: 18 files / 190 tests green (one new test over
  v0.25.1); `tsc --noEmit` clean.
- `make verify`: full backend suite, kustomize overlays, policy
  validation, and version lockstep (0.25.1 → 0.25.2) green.
