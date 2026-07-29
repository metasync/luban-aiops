# ADR-0003: Platform-Owned Agent-Service Contract

## Status

`accepted`

- date: 2026-07-28
- deciders: workspace maintainers
- related specs: `part-1b-framework-revalidation.md`, `ADR-0002`

## Context

`products/agent-platform` currently exposes two surfaces: a transitional `FastAPI` adapter and a native AgentScope serving stack. The gateway's `auto` backend resolution probes both at runtime. This dual-surface is a maintenance burden and leaves the platform's stable boundary undefined.

At the same time, `ADR-0002` re-affirms AgentScope as the kernel while explicitly keeping the door open to a future framework swap (for example `LangGraph`). For that swap to stay bounded, the rest of the platform must not bind to AgentScope's native wire protocol. Today, nothing outside `agent-platform` imports AgentScope; the boundary is already HTTP. This ADR makes that boundary explicit and platform-owned.

## Decision

Define a platform-owned agent-service contract (REST + SSE) in `shared/shared-contracts`, and make it the single stable boundary that `tool-gateway` and `operator-portal` consume. Inside `products/agent-platform`, the AgentScope kernel sits behind an adapter that implements this contract. Retire the transitional surface and the gateway `auto` probe once the native-backed contract is in place.

## Alternatives Considered

- adopt AgentScope's native protocol as the platform contract (Path A) — rejected: simplest now, but a future kernel swap would force the replacement to re-implement AgentScope's wire protocol or migrate every consumer; higher lock-in
- keep the dual-surface with an anti-drift contract test — rejected: preserves two code paths and the runtime probe indefinitely; does not give the platform a single stable boundary
- defer the contract until after a native-runtime spike — rejected: the contract is kernel-agnostic, so adopting it now is safe and unblocks native adoption without pre-empting `ADR-0002`

## Consequences

- the platform gains one stable, versioned agent-service boundary; gateway and portal bind to it, not to a framework
- a future framework swap becomes a single-adapter change inside `agent-platform`; consumers are unaffected
- resolves the dual-surface risk: the transitional adapter and `auto` probe are retired on a defined path rather than maintained forever
- cost: one extra abstraction layer inside `agent-platform`, and the contract must be designed before the native runtime is fully wired behind it
- follow-up: a spec to define the contract schemas in `shared/shared-contracts`, implement the AgentScope adapter, and sequence transitional retirement
