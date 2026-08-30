# v0.27.4 — Dotted Canonical Tool Names in Chat Prose

**Date:** 2026-08-31
**Type:** same-day portal patch in the v0.27 train
**Scope:** operator-portal only; no backend, contract, policy, or route changes

## Why

The model can only ever see the sanitized tool names from its
function-calling schema (provider name constraints turn dots into
underscores: `k8s.get_pods` → `k8s_get_pods`), so replies naturally
mention the underscore form in prose. Everything else in the portal —
evidence cards, confirmation cards, execution receipts — already shows
the registry's dotted canonical name, so prose mentions read as a
different tool. This patch makes prose agree with the rest of the UI.

## What changed

- **Presentation-only rewrite at render time.** A sanitized → canonical
  map is built once per page session from the existing `/api/v1/tools`
  catalog (module-cached; all chat-facing roles already hold
  `tools:list`). Chat reply bubbles and incident triage-report
  summaries rewrite mapped names to the dotted form before the
  escape-first markdown pipeline — the replacement introduces no
  markup, so the safe-by-construction contract is untouched.
- **Code regions are shielded.** Inline code spans and fenced blocks
  keep the sanitized form: `AGENT_GATEWAY_TOOL_AUTO_ALLOW` and similar
  configuration surfaces expect it, so copy-paste out of a code block
  stays correct. Word boundaries plus longest-match-first ordering keep
  shared prefixes (`k8s_get_pods` vs `k8s_get_pod_logs`) unambiguous.
- **The durable record is untouched.** Transcripts keep the model's
  original words; the rewrite re-applies on every render, so historical
  sessions benefit retroactively with no migration.
- **Graceful degradation.** A failed catalog fetch renders text exactly
  as written and retries on the next mount; names without dots map to
  themselves; an ambiguous sanitized collision (impossible while
  function-calling requires unique names) is skipped, never guessed.
- **Skill drafts are intentionally excluded.** The draft preview must
  match the downloaded markdown byte-for-byte, so it renders the text
  as generated.

## Verification

- 12 new unit tests (map building, collision skip, prose rewrite,
  longest-match, word boundaries, code shielding, control-character
  stripping); portal suite 242 green, `tsc` clean.
- House train: `make verify` green before and after `make build`
  (IMAGE_TAG=0.27.4-dev-k8s-a6fe49a-dirty-…), `make deploy` green,
  all pods Running.
- Live check on aiops.luban.metasync.cc (platform version v0.27.4):
  a reply whose stored transcript carries plain-text `k8s_list_pods`
  renders `k8s.list_pods` in prose, while the same name in a fenced
  block and an inline code span keeps underscores; zero `<em>`
  artifacts.

## Non-goals

- The model-visible schema names stay sanitized (provider constraint).
- No server-side text rewriting of replies or transcripts.
