# v0.27.6 — Post-Review Hardening of the Dotted Tool-Name Rewrite

**Date:** 2026-08-31
**Type:** review-remediation patch closing the v0.27.4/v0.27.5 review
**Scope:** operator-portal only; no backend, contract, policy, or route changes

## Why

The code & doc review of the v0.27.4/v0.27.5 dotted tool-name rewrite
returned **approve-with-minor**: all safety claims verified (XSS-safety
relative to the escape-first renderer, regex correctness, async
lifecycle, transcript durability), with two Low findings worth closing.

## What changed

- **Asymmetric match boundaries.** The leading boundary now excludes a
  dot as well as word characters — an already-dotted mention
  (`k8s.get_pod_logs`) can never re-match a suffix key should the
  registry ever contain one (a hypothetical `get.pod_logs` entry
  sanitizing to `get_pod_logs`). The trailing boundary stays word-only:
  the symmetric dot-exclusion suggested in review would have stopped
  sentence-final names ("I called `k8s_get_pods`.") from rewriting —
  a regression for ordinary prose.
- **Test coverage.** Four new assertions: leading-boundary adjacency
  (`xk8s_get_pods`, `my_k8s_get_pods` stay untouched), sentence-final
  rewrite, the pathological suffix-key registry, and the
  third-colliding-entry skip branch in the map builder.

## Verification

- toolNames suite 15 green; portal suite 245 green; `tsc` clean.
- House train: `make verify` green before and after `make build`
  (IMAGE_TAG=0.27.6-dev-k8s-882a75f-dirty-…), `make deploy` green,
  all pods Running.
- Live check on aiops.luban.metasync.cc (platform version v0.27.6):
  the tool-list reply still renders every name as a dotted code chip;
  a plain-text mid-sentence mention and a sentence-final mention both
  render dotted (`…was k8s.list_pods.`) with the period correctly
  excluded from the name.

## Doc review outcome

No doc findings: the guides already describe `AGENT_GATEWAY_TOOL_AUTO_ALLOW`
as dotted names with dots→underscores normalization, matching the shipped
behavior; release notes for v0.27.4/v0.27.5 remain accurate as
point-in-time records.
