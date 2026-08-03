# ADR-0005: Extract the Platform API Edge into a Separate `platform-gateway` Product

## Status

`accepted`

- date: 2026-07-30
- accepted: 2026-07-30
- deciders: workspace maintainers
- related specs: `SPEC-001`, `SPEC-004`, `SPEC-010`

## Context

`products/tool-gateway` currently hosts two distinct roles that were never meant to share a product:

- a **portal-facing API edge**: token verification (`token_verifier`), deny-by-default policy enforcement (`policy_engine`), chat and session proxying to `agent-platform` (`agent_client`), broker-mediated token delegation (`delegation_client`), and the auth/identity/runtime routes
- a **tool execution framework**: `ToolRegistry`, the Kubernetes read-only connector, the `tools/invoke` choke point with deterministic redaction and audit

The workspace model (`docs/workspace/product-boundaries.md`, `workspace-model.md`) has always defined `tool-gateway`'s responsibility as connector standardization — tool contracts, system connectors, MCP integration — owned by an integrations team, while control-plane concerns (auth, policy) belong to security/control-plane ownership. SPEC-001 deliberately deferred the service naming question, and SPEC-004 left the boundary question to a future ADR rather than entrenching it in policy code.

Since SPEC-009, the security-critical surface has grown: the redaction choke point, the delegation client with its workload-identity preference, and the policy engine all live in a process whose stated purpose is connector access. Continuing to add portal-edge features (and eventually the execution-worker edge in Release 4) into the connector product makes ownership, review scope, and the blast radius of the security-sensitive code harder to reason about.

## Decision

Extract the portal-facing API edge into a new product, `platform-gateway`, and keep `tool-gateway` as the tool/connector home.

- `platform-gateway` owns: inbound token verification and audience enforcement, action policy enforcement, chat and session proxying to `agent-platform`, broker-mediated token delegation (the delegation client and its service credential/workload token), and the portal-facing routes (`chat`, `sessions`, `auth`, `identity`, `runtime`, health/metrics)
- `tool-gateway` keeps: the `ToolRegistry` and connector framework, the `tools:list`/`tools:invoke` routes, the redaction choke point, tool audit, and the Kubernetes connector
- the portal's single browser entrypoint continues to proxy to one edge service (`platform-gateway` after the split); `tool-gateway` becomes an internal service whose callers are `agent-platform` (relayed delegated tokens, per ADR-0004) and, where needed, `platform-gateway`

The split follows the same delegation shape established by ADR-0004 for every service-to-service hop; the audience and service-credential plumbing details are defined by the implementing spec, not here.

## Alternatives Considered

- keep the combined service and name — rejected: the combined surface contradicts the documented product boundary and ownership model (`tool-gateway` = connectors/integrations); security-critical edge code (auth, policy, delegation, redaction) would keep accreting in a process owned conceptually by integrations, blurring review scope and trust boundaries exactly when Release 4 adds the execution edge
- invert the split: keep the edge in `tool-gateway` and move the tool framework out — rejected: inverts the workspace model, which names `tool-gateway` as the connector standardization authority (Rule 5) and never names a portal-edge product called "tool-gateway"; the framework is also the smaller, more stable half, so it is the natural remainder
- defer until Release 4 — rejected: every intervening release adds edge features (identity hardening, policy dimensions) into the wrong product, increasing the eventual extraction cost; SPEC-009 is delivered and `make verify` is green, making this the cheapest moment — the same reasoning used for SPEC-009 itself

## Consequences

- ownership aligns with the workspace model: the security/control-plane edge and the integrations/connectors home are separately owned, reviewed, and deployable
- `tool-gateway` shrinks to its documented mandate and stays close to byte-stable while connectors grow (skills-hub integration, MCP)
- the edge becomes the natural home for future portal-facing concerns (Release 4 execution approvals surface) without touching connector code
- cost: one more product to build, test, image, and deploy; a new overlay entry, CODEOWNERS area label, and living-state doc updates
- cost: one additional service-to-service hop whose identity plumbing (audience binding, service credential or workload token for the edge) must be defined by the implementing spec without weakening the deny-by-default and delegation model
- follow-up: `SPEC-010` implements the extraction; living-state docs (`workspace-model.md`, `product-boundaries.md`, layout conventions, root README) are advanced as part of that delivery
