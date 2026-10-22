---
kind: design
name: Defer SPEC-070 server-to-server delegation until target compatibility is evidenced
source: session
category: adr
---

# Defer SPEC-070 server-to-server delegation until target compatibility is evidenced

_Source: coding plans from commit period a96f2ac → 102c0b4 — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
The approved SPEC-070 / ADR-0015 requires one-time target authorization-code enrollment, but the user needs server-to-server acquisition after normal Luban SSO with no extra browser redirects, consent clicks, enrollment commands, or manual token entry. The identity-broker returns a Luban-issued access token (not a reusable Keycloak subject token), `auth_resolution.py` dispatches Basic/bearer/client-credentials without user context, and AAP 2.6's documented MCP OAuth path uses authorization-code authentication — none of which establish the required noninteractive grant.

## Decision drivers
- no additional user interaction after SSO
- target must accept a user-bound credential acquired server-side
- do not implement a speculative grant
- preserve existing machine-grant behavior

## Considered options
- **Implement the planned token-exchange / audience-restricted IdP path immediately** _(rejected)_ — pros: delivers the requested noninteractive flow; cons: unsupported by reviewed AAP 2.6 docs; Keycloak token exchange does not prove another product accepts its output; risks forwarding an internal audience-bound Luban JWT to an unconfigured target
- **Stop at a compatibility report and amend SPEC-070/ADR-0015 before any runtime change** — pros: avoids building an unproven grant, keeps AAP as the planned target, leaves current release version unchanged, gates implementation behind evidence

## Decision
Do not implement the replacement grant in this period. Produce a compatibility assessment for the exact production target/version and Keycloak version, then propose coordinated amendments to SPEC-070 `spec.md`, `plan.md`, `tasks.md`, and ADR-0015 through the repository's revision/supersession convention. Runtime work R-1–R-6 remains gated until a supported end-to-end path is evidenced.

## Consequences
SPEC-070 build-ready status is withheld; all eight R-packages are deferred pending Gate 0 approval. If no supported mechanism is found, the plan stops at a compatibility report naming the missing capability rather than shipping a speculative grant.