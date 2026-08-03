# SPEC-010: Platform Gateway Extraction — Splitting `tool-gateway` into `platform-gateway` and `tool-gateway`

## Status

- status: `draft`
- owner: chi
- created: 2026-07-30
- release slice: R2 start — structural prerequisite before any new edge
  feature (execution approvals, policy dimensions) lands
- related ADRs: `docs/adr/0005-platform-gateway-extraction.md`

## Summary

Implement ADR-0005: extract the portal-facing API edge out of
`products/tool-gateway` into a new product `products/platform-gateway`
(token verification, policy enforcement, chat/session proxying, token
delegation, portal routes), leaving `tool-gateway` as the tool/connector
home (registry, connectors, `tools:list`/`tools:invoke`, redaction, tool
audit). External behavior is preserved: the portal keeps one browser
entrypoint, all HTTP contract shapes are unchanged, and the delegation /
deny-by-default trust model is not weakened.

## Motivation

- `tool-gateway` currently hosts two roles the workspace model assigns to
  different products and teams: a security/control-plane edge and a
  connector/integrations framework (`product-boundaries.md` Rule 5 names
  `tool-gateway` as the connector standardization authority only).
- Every release since SPEC-003 has grown the security-critical surface
  (token verification, policy engine, delegation client, redaction choke
  point) inside the connector product; Release 4's execution-approvals
  edge would compound the problem.
- SPEC-009 is delivered and `make verify` is green — the cheapest moment
  for the extraction (same reasoning ADR-0005 applied to timing).

## Requirements

Each requirement gains testable acceptance criteria at approval.

### R-1: New `platform-gateway` product carrying the portal edge

A new product `products/platform-gateway` hosts the portal-facing edge,
following the existing FastAPI service layout convention (the current
reference pattern).

Acceptance criteria:

- the edge modules move intact: token verification (JWKS), action policy
  enforcement, chat and session proxying to `agent-platform`, the
  delegation client (exchange, per-user cache, dev subject-token minting,
  workload-token preference), and the portal-facing routes (`chat`,
  `sessions`, `auth`, `identity`, `runtime`, health, metrics)
- request/response contract shapes are byte-compatible for portal callers
  (chat/session/auth responses unchanged; `x-request-id` correlation kept)
- the edge service's test suite covers verification, policy deny-by-default,
  delegation cache/fallback, and the proxy routes at parity with today
- `make verify` runs the new suite as part of the gate

### R-2: `tool-gateway` reduced to the tool/connector home

`tool-gateway` loses the portal edge and becomes an internal service.

Acceptance criteria:

- removed from `tool-gateway`: chat/session proxy routes and agent client,
  portal auth/identity routes, the delegation client, and portal-facing
  policy actions; retained: `ToolRegistry`, connectors, `tools:list` /
  `tools:invoke`, redaction choke point, tool audit, readiness/metrics
- inbound tool calls keep the exact ADR-0004 verification path
  (delegated bearer token, audience `tool-gateway`, roles from the token,
  `tools:invoke` / `tools:list` actions) — no auth regression and no
  identity-in-body trust
- removed surface is proven gone (route inventory / test parity), not just
  unreferenced

### R-3: Identity plumbing across the new boundary

The identity model adapts to the split without weakening it.

Acceptance criteria:

- the edge authenticates to the broker exchange as its own registered
  service client (its own credential / workload-token path), and
  delegated tokens minted for the tool path keep `aud = tool-gateway`
  with `act` naming the edge — the tool side sees no claim-shape change
- portal-issued platform tokens are audience-bound to the edge (per the
  resolution of Q-3) and the edge enforces that audience on verification
- deny-by-default policy stays intact: the policy bundle is loaded by the
  edge (portal actions) and by `tool-gateway` (tool actions) with the same
  deny semantics; no action is granted that was not granted before
- `identity-token.schema.json` / shared contracts updated only where the
  audience naming resolution (Q-3) requires it, with contract tests binding
  both services

### R-4: Overlay, build, and deployment alignment

The dev-k8s overlay and build system grow the new product.

Acceptance criteria:

- new `platform-gateway` deployment/service in the dev-k8s overlay with
  the edge's config and secret fragments; `kustomize build` renders all
  overlays
- root Makefile builds the new image alongside the existing ones; portal
  (`web-ui` nginx) proxies `/api/` to the edge service
- `CODEOWNERS` and label conventions gain the new product area
- the dev smoke path still works end to end: SSO login → portal shell →
  session create → streamed chat → tool invocation through the relayed
  delegated token

### R-5: Living-state docs advanced

Acceptance criteria:

- `workspace-model.md`, `product-boundaries.md`,
  `backend-service-layout-convention.md`, root `README.md`, and product
  READMEs reflect the two products and their mandates
- `CHANGELOG.md` entry; Release 1 notes / spec index updated at delivery

## Non-Goals

- any behavior change beyond the split: no new policy dimensions, no
  execution/mutating tools (Release 4), no multi-replica or HA changes
- shared-sdk extraction or cross-service code packaging — duplication of
  the small shared modules (config/observability helpers) is accepted for
  now, consistent with the existing per-product pattern
- changes to `identity-broker` beyond registry/audience naming entries
- renaming unrelated products or touching agent-platform's contract

## Impact

- products touched: new `products/platform-gateway`; `products/tool-gateway`
  (removals); `products/identity-broker` (registry/audience entries);
  `products/operator-portal` (nginx proxy target)
- contracts touched: `identity-token.schema.json` only if Q-3 renames the
  portal audience; policy bundle split into edge-owned and tool-owned
  action sets (same file convention)
- identity / policy / audit impact: no weakening — verification paths,
  audiences, deny-by-default, and audit fields preserved; one new service
  credential/workload subject registered at the broker
- living state docs to update on delivery: per R-5

## Open Questions

- **Q-1: env prefix scope.** Do the edge's `GATEWAY_*` environment names
  rename to `PLATFORM_*` (clean naming, touches config, overlays, docs,
  tests) or stay `GATEWAY_*` on the new product (minimal churn, name no
  longer matches the product)? Recommendation pending discussion.
- **Q-2: Kubernetes/image naming.** Rename the `api-gateway` deployment,
  service, and image to `platform-gateway` (consistent, touches portal
  nginx and operator habits like port-forward names) or keep `api-gateway`
  as the deployed name (zero overlay churn, diverges from product name)?
- **Q-3: portal token audience.** Platform JWTs issued for the portal are
  audience-bound to `tool-gateway` today. After the split, rename the
  audience to `platform-gateway` (accurate binding, a deliberate identity
  contract change shipped together) or keep `tool-gateway` (no contract
  change, but the audience name becomes false)?
- **Q-4: edge's broker client id.** Register the edge's exchange client as
  a new `platform-gateway` client (delegated tokens' `act.sub` becomes
  `platform-gateway`, audit gets more accurate attribution) or reuse the
  existing `tool-gateway` client entry (no broker-side rename, but `act`
  misattributes the acting service)?

## Changelog

- 2026-07-30: created as `draft`, implementing ADR-0005; open questions
  Q-1…Q-4 recorded for maintainer resolution before approval
