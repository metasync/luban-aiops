# SPEC-001 Tasks: Release 1 Platform Hardening

Task states: `[ ]` pending, `[x]` done. Implementation starts when the spec is `approved`.

## R-4: Contract enforcement at the gateway (first: R-1/R-2 build on it)

- [x] add `api_gateway/schemas/` with chat, session, and identity-context `pydantic` models (`products/tool-gateway`)
- [x] switch chat and session routes from raw `request.json()` to typed bodies returning `422` (`products/tool-gateway`)
- [x] add contract tests binding models to `shared/shared-contracts/schemas/` (`products/tool-gateway/tests`)

## R-1: Gateway authentication enforcement

- [x] add `GATEWAY_REQUIRE_AUTH` to `GatewaySettings` with explicit overlay entries (`products/tool-gateway`, `shared/platform-ops/gitops`)
- [x] add identity-resolution dependency raising `401` when required and missing (`products/tool-gateway`)
- [x] disable payload/header/default `user_id` fallback in required-auth mode (`products/tool-gateway`)
- [x] unit tests for both auth modes (`products/tool-gateway/tests`)

## R-2: Role propagation baseline

- [x] expose typed `roles` from identity resolution and add to structured log events (`products/tool-gateway`)
- [x] handle malformed identity payloads with a `502`-class error (`products/tool-gateway`)
- [x] unit tests for role propagation and malformed identity (`products/tool-gateway/tests`)

## R-3: Session integrity in the transitional runtime

- [x] reject unknown client-supplied `session_id` with `404` (`products/agent-platform`)
- [x] scope session read/continue to the owning `user_id` (`products/agent-platform`)
- [x] add TTL and max-entry eviction to `SessionStore` with env configuration (`products/agent-platform`)
- [x] key kernel agent instances by `session_id`; regression test for cross-session memory isolation (`products/agent-platform`)
- [x] document in-memory store limitations (`products/agent-platform/README.md`)

## R-5: Gateway resilience

- [x] cache backend resolution with configurable TTL (`products/tool-gateway`)
- [x] bound the non-streaming chat timeout; keep streaming read unbounded with bounded connect (`products/tool-gateway`)
- [x] move backend context types to `core`; remove `core` → `services` import (`products/tool-gateway`)
- [x] unit tests for cache TTL behavior (`products/tool-gateway/tests`)

## R-6: CI baseline and living-doc alignment

- [x] add `ci.yml` running `uv run pytest` across the three Python products (`.github/workflows`)
- [x] add overlay render workflow with `kustomize build` (`.github/workflows`)
- [x] refresh root `README.md` current-state section and SDD links
- [x] document `tool-gateway` transitional versus target role (`products/tool-gateway/README.md`)

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified
- [x] living state docs updated (see spec `Impact` section)
- [x] `CHANGELOG.md` entry added referencing `SPEC-001`
- [x] spec index in `docs/specs/README.md` updated
- [x] spec status set to `delivered`
