---
kind: external_dependency
name: Headless Chromium engine in a sidecar container
slug: chromedp-headless-shell
category: external_dependency
category_hints:
    - vendor_identity
    - client_constraint
scope:
    - '**'
source_files:
    - shared/platform-ops/gitops/runtime-profiles/browser-dev/tool-gateway-browser-sidecar.yaml
    - shared/platform-ops/gitops/runtime-profiles/browser-dev/browser-sidecar-network-policy.yaml
---

### Role
The actual browser engine is a separate container sharing the `tool-gateway` pod's network namespace. It exposes Chrome DevTools Protocol (CDP) on loopback so the Playwright connector can drive it without exposing the debug port cluster-wide.

### Integration points
- A default-deny NetworkPolicy denies ingress to the CDP port from other pods.
- The sidecar has its own resource limits; a browser crash degrades only `web.*` tools.

### Stable constraints
- Engine is swappable at deployment level (CDP interface) — the spec records parked alternatives (Obscura, Lightpanda) behind promotion triggers.
- Port binding must be pinned to loopback; the `:stable` tag has drifted between ports 9222 and 9223 across runs.
- Evidence fidelity relies on Chromium rendering; alternative engines require screenshot-fidelity gates before promotion.