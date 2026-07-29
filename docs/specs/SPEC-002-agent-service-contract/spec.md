# SPEC-002: Platform-Owned Agent-Service Contract

## Status

- status: `delivered`
- owner: workspace maintainers
- created: 2026-07-28
- release slice: `Release 1` (architecture seam before R1 feature work)
- related ADRs: `ADR-0002`, `ADR-0003`

## Summary

Replace the dual-surface agent-platform (transitional FastAPI adapter + native AgentScope serving) with a single platform-owned HTTP+SSE contract, implemented by an adapter over the AgentScope kernel. Migrate tool-gateway to consume only this contract, and retire the transitional surface and the gateway's `auto` backend probe.

## Motivation

`ADR-0003` (accepted 2026-07-28) decided that:

- the platform needs one stable, versioned agent-service boundary owned by the platform, not by a framework
- the AgentScope kernel sits behind an adapter inside `agent-platform`; consumers never bind to AgentScope's wire protocol
- a future framework swap (e.g. LangGraph) must be a single-adapter change with zero consumer migration

Today, `tool-gateway` maintains dual-backend adapters (transitional + native), probes both at runtime in `auto` mode, and translates between two incompatible wire protocols. This is the maintenance burden and undefined-boundary risk that `ADR-0003` resolves.

## Requirements

### R-1: Agent-service contract definition

A platform-owned contract is defined as JSON Schema files in `shared/shared-contracts/schemas/`, covering the full agent-service surface consumed by the gateway and (indirectly) the portal.

Acceptance criteria:

- schemas exist for: `agent-chat-request`, `agent-chat-response`, `agent-stream-event`, `agent-session`, `agent-runtime-metadata`, `agent-health`
- the chat and session schemas are compatible with (extend or reference) the existing `chat-request`, `chat-response`, `session`, and `stream-event` schemas already in `shared-contracts`
- identity forwarding (`X-User-ID`, `x-request-id`) is part of the contract's header conventions, documented alongside the schemas
- the contract is versioned under a `/api/v2/` path prefix to coexist with the transitional `/api/v1/` during migration

### R-2: AgentScope adapter

`agent-platform` exposes the contract as its single external HTTP surface, backed by the native AgentScope kernel.

Acceptance criteria:

- a new adapter module implements the `/api/v2/` routes by delegating to the AgentScope kernel (`AgentKernel` / native runtime)
- session semantics from `SPEC-001` are preserved: server-generated IDs, user ownership, TTL/max-entry eviction, per-session agent isolation
- streaming responses emit `agent-stream-event` conformant SSE frames
- the runtime metadata endpoint reports kernel mode, provider, and state without exposing AgentScope internals
- the adapter does not leak AgentScope-specific types into the contract layer (no `Msg`, `AgentApp`, `Toolkit` in route signatures or response bodies)

### R-3: Gateway consumer migration

`tool-gateway` consumes the platform-owned contract exclusively; the dual-backend abstraction is removed.

Acceptance criteria:

- the gateway's `agent_backends.py` dual-backend classes (`TransitionalAgentServiceBackend`, `NativeAgentServiceBackend`) and `resolve_agent_backend` are removed
- `AGENT_BACKEND_MODE` and `BACKEND_RESOLUTION_TTL_SECONDS` settings are removed; the gateway targets the contract directly
- gateway typed models (from `SPEC-001` R-4) align with the new contract schemas; contract tests updated
- all existing gateway route behavior (auth enforcement, role logging, identity forwarding) is preserved
- the gateway's overlay `runtime-config.env` files drop `AGENT_BACKEND_MODE` entries

### R-4: Transitional surface retirement

The transitional FastAPI routes in `agent-platform` (`/api/v1/chat`, `/api/v1/sessions`, `/api/v1/chat/stream`, `/api/v1/runtime`) are removed once the gateway migration lands.

Acceptance criteria:

- the `/api/v1/` routes no longer exist in `agent-platform`
- `entrypoints/transitional.py` and the transitional `app.py` bootstrap are removed or reduced to a thin redirect/shim for one release cycle
- the native AgentScope entrypoints (`entrypoints/runtime.py`, `entrypoints/native.py`) remain for direct AgentScope-native consumers (e.g. AgentScope Studio) but are not the platform's stable boundary
- the `agent-platform` README documents the contract as the sole external interface

### R-5: Contract enforcement and CI

The contract stays mechanically enforced.

Acceptance criteria:

- `agent-platform` tests validate adapter responses against the new JSON Schema files (mirroring `SPEC-001` R-4 pattern)
- `tool-gateway` contract tests bind gateway models to the new schemas
- CI (`ci.yml`) continues to pass for both products
- a schema/model mismatch fails the test suite in either product

## Non-Goals

- changing the portal's direct behavior (it talks to the gateway, not agent-platform directly)
- modifying the native AgentScope entrypoints' internal protocol (they remain for AgentScope-native tooling)
- persistent session storage (still in-memory with TTL; durable store is a later spec)
- policy enforcement or role-based denial (lands with policy-center)
- renaming the `api_gateway` package or `tool-gateway` directory (deferred per SPEC-001)

## Impact

- products touched: `products/agent-platform` (adapter + transitional removal), `products/tool-gateway` (backend simplification), `shared/shared-contracts` (new schemas)
- contracts touched: new `agent-*` schemas added; existing `chat-*`, `session`, `stream-event` schemas referenced/extended, not broken
- deployment impact: `dev-k8s-transitional` overlay's `AGENT_BACKEND_MODE` entries removed; gateway targets agent-service directly
- living state docs to update on delivery: root `README.md`, `products/agent-platform/README.md`, `products/tool-gateway/README.md`, `CHANGELOG.md`

## Open Questions

None — all resolved (see Changelog).

## Changelog

- 2026-07-28: created as `draft` implementing `ADR-0003`
- 2026-07-28: resolved open questions — (1) the `/api/v2/` contract may simplify the response envelope where warranted, not purely additive; (2) the transitional `/api/v1/` surface is removed in the same delivery, no deprecated shim; status → `approved`
- 2026-07-28: implementation started; status → `in-progress`
- 2026-07-28: all requirements implemented and verified (87 tests green, both overlays render); status → `delivered`
