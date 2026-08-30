# v0.27.3 — Chat Markdown Rendering of Tool Identifiers

Date: 2026-08-31
Release type: patch (portal-only renderer fix from a live test of
v0.27.2 — no routes, policy actions, audit event types, or response
shapes change; no backend behavior changes at all)

## Summary

A live test of v0.27.2 found that tool names mentioned in agent chat
replies lost their separators: `k8s.delete_pod` surfaced as
"k8sdeletepod". This patch fixes the chat markdown renderer.

## The report

Two facts combine into the symptom:

1. The model never sees dotted tool names. Per the SPEC-021/037
   signed-execution design, tool names are sanitized for the model
   (dots → underscores): the registry knows `k8s.delete_pod`, the
   model writes `k8s_delete_pod`.
2. The portal's escape-first markdown renderer carried a legacy
   underscore-italics pass (`_(.+?)_`) that matched `_delete_` inside
   `k8s_delete_pod` and converted it to `<em>delete</em>` — the
   underscores are consumed by the markup, so the browser showed the
   separators stripped. Even wrapping the name in backticks did not
   protect it: inline code spans were converted *before* the emphasis
   passes and never shielded from them; a fenced code block could
   likewise turn its `# comment` lines into real headings.

## The fix

In `chat/markdown.ts` (the portal's escape-first, regex-based
renderer):

- **Code fencing.** Fenced code blocks and inline code spans are
  stashed behind sentinels right after the escape step and restored at
  the end, so no heading/emphasis/list/table pass can ever rewrite
  code content. The escape-first contract is preserved: every source
  character still passes through the escape step before any markup is
  introduced, and the sentinels cannot collide with source text.
- **CommonMark flanking for underscores.** The `_…_` and `__…__`
  emphasis passes now require non-word context at their outer edges,
  so intra-word underscores in identifiers stay literal; real
  emphasis (`_important_`, `__urgent__`) still renders. Asterisk
  emphasis is untouched.
- The http(s)-only link allow-list (the XSS hardening from the
  walkthrough-review findings) is untouched.

Five regression tests pin the new behavior: plain-text identifiers,
backticked identifiers, fenced-block protection, real underscore
emphasis, and list + link interplay.

## Surfaces deliberately unchanged

- Backend surfaces are untouched — the gateway, agent, and tool
  registries keep their canonical dotted names; evidence cards and
  execution receipts already showed them correctly. This is a
  presentation fix for agent-authored markdown only.

## Verification

- Portal 230 vitest tests green (22 in the markdown suite), `tsc`
  clean; `make verify` green before and after `make build`; `make
  deploy` green.
- Browser live check on aiops.luban.metasync.cc, three scenarios
  green: clean sign-in, `/api/v1/runtime` reporting `0.27.3`, and a
  real chat reply echoing "I called k8s_delete_pod and
  `k8s_get_pod_logs` today." with both identifiers rendered
  underscore-intact — plain text and inside `<code>` — with zero
  emphasis elements in the reply bubble.
