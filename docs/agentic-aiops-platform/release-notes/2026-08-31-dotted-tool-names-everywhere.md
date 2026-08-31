# v0.27.5 — Dotted Tool Names Everywhere (Code Regions Unshielded)

**Date:** 2026-08-31
**Type:** same-day portal patch broadening v0.27.4
**Scope:** operator-portal only; no backend, contract, policy, or route changes

## Why

v0.27.4 shipped a render-time rewrite from the sanitized tool names the
model writes (`k8s_get_pods`) to the registry's dotted canonical names
(`k8s.get_pods`), but deliberately shielded inline code spans and fenced
blocks on the assumption that configuration surfaces expect the
sanitized form and copy-paste must preserve it. A live test immediately
showed the gap: asked to list all tools, the model backticks every name,
so the entire list rendered as underscored code chips and the rewrite
never applied.

Re-examining the assumption: the sanitized form has **no external
consumer** besides the model's function-calling schema (invisible to
users), and the one configuration surface that lists tool names —
`AGENT_GATEWAY_TOOL_AUTO_ALLOW` — normalizes dots to underscores on
input, so the dotted form is equally safe to copy-paste. The shield was
protecting against a risk that does not exist.

## What changed

- **The rewrite now applies to every rendered surface** — prose, inline
  code spans, and fenced blocks — in chat reply bubbles and incident
  triage-report summaries. The sentinel-based shielding machinery is
  deleted outright; `displayToolNames` is a single word-boundary,
  longest-match-first substitution on the raw text before the
  escape-first markdown pipeline.
- **Everything else from v0.27.4 is unchanged**: the map is built once
  per page session from `/api/v1/tools`; failed fetches degrade to no
  mapping; ambiguous collisions are skipped; durable transcripts keep
  the model's original words and historical sessions re-render dotted
  retroactively; skill drafts still render exactly as generated so the
  preview matches the download.

## Verification

- Existing unit tests flipped to assert code-region rewriting (11
  tests); portal suite 241 green (one known inter-test-pollution flake
  in DocumentsView.test.tsx passed in isolation and on full-suite
  rerun), `tsc` clean.
- House train: `make verify` green before and after `make build`
  (IMAGE_TAG=0.27.5-dev-k8s-99fde71-dirty-…), `make deploy` green,
  all pods Running.
- Live check on aiops.luban.metasync.cc (platform version v0.27.5):
  the "list all the tools available?" reply renders every name as a
  dotted code chip (`k8s.list_pods`, `k8s.delete_pod`,
  `skills.search`, `incidents.list`, …).

## Non-goals

- The model-visible schema names stay sanitized (provider constraint).
- No server-side text rewriting of replies or transcripts.
