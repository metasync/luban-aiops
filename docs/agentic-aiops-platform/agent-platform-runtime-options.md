# Agent Platform Runtime Options

## Objective

Clarify the implementation choice for `products/agent-platform` between:

- a custom `FastAPI` shell with an `AgentScope` adapter
- a more native `AgentScope` Agent Service or `AgentApp`-style runtime service

This document explains why the two approaches can look similar while serving different purposes, and recommends how this repository should evolve.

## Why This Decision Matters

The reference architecture already establishes that:

- `AgentScope 2.0` is the runtime kernel
- the platform still requires surrounding services for identity, policy, approvals, skills, tools, and observability
- the `agent-service` should expose session-aware and stream-oriented interfaces

At the same time, the current `Release 0` implementation intentionally began with a thin service scaffold so the workspace could stand up a minimal request path quickly.

## The Two Options

### Option A: `FastAPI` Shell Plus `AgentScope` Adapter

In this model:

- `FastAPI` owns the HTTP routes
- `pydantic` owns request and response validation
- custom code owns session endpoints and response shaping
- `AgentScope` is used inside the chat and streaming logic

Current repository status:

- this is the implementation shape currently used in `products/agent-platform`
- the outer service interface remains explicit and easy to customize
- the runtime path now attempts to use `AgentScope` when credentials are configured

### Option B: Native `AgentScope` Agent Service / `AgentApp`

In this model:

- the service is built around AgentScope's own service abstractions
- session lifecycle, event delivery, and agent-serving concerns are more directly owned by AgentScope
- the platform integrates around that runtime instead of re-implementing as much of the serving layer itself

This is closer to the long-term intent implied by the reference architecture.

## What Overlaps

Both approaches can expose:

- `REST` endpoints
- `SSE` streaming
- health endpoints
- session-oriented request flows
- JSON contracts at the service boundary

This overlap is why they can appear interchangeable at first glance.

## What Is Different

### `FastAPI` + `pydantic`

Primary role:

- generic service framework

What it gives:

- route definition
- request and response validation
- dependency injection
- middleware hooks
- OpenAPI and docs generation

What it does not give by itself:

- agent lifecycle management
- built-in multi-session runtime semantics
- workspace lifecycle management
- agent-specific event protocol
- built-in tool, skill, or MCP execution model

### `AgentScope` Agent Service / `AgentApp`

Primary role:

- agent-serving framework

What it gives:

- multi-session and multi-tenant runtime semantics
- richer event streaming model
- workspace and sandbox integration
- stronger alignment with AgentScope tools, skills, and MCP patterns
- a more direct path to resumable runs and richer frontend event delivery

What it still does not replace:

- enterprise identity architecture
- policy service ownership
- approval workflows
- external gateway control
- broader platform product boundaries

## Evaluation For This Repository

### Option A Strengths

- easiest incremental path from the current scaffold
- explicit route ownership for the platform team
- simple integration with `identity-broker`, `tool-gateway`, and future `policy-center`
- lower initial migration cost for `Release 0`

### Option A Weaknesses

- risks re-implementing runtime behaviors AgentScope already provides
- increases platform-owned maintenance for sessions and streaming
- can drift from AgentScope-native patterns over time
- makes workspace and richer event semantics harder to adopt cleanly later

### Option B Strengths

- better alignment with the selected runtime kernel
- better fit for session-aware, event-rich agent serving
- cleaner path to workspace-backed tools, skills, and MCP execution
- reduces custom runtime-service logic the platform must own

### Option B Weaknesses

- higher short-term integration effort
- requires earlier decisions about storage, message bus, and workspace management
- may force more refactoring while the surrounding platform services are still placeholders

## Reference Architecture Fit

The reference architecture expects the `agent-service` to expose:

- session-aware `REST` endpoints
- `SSE` endpoints for live execution streams
- resumable runs
- multi-turn session support
- rich event delivery to the frontend

It also expects the workspace abstraction to become the execution boundary for:

- tools
- skills
- offloaded context
- `MCP` processes

That expectation is more naturally aligned with Option B than with a long-lived custom Option A stack.

## Recommendation

Use a phased strategy:

### Phase 1: Keep Option A For Early `Release 0`

Use the current `FastAPI` shell plus `AgentScope` adapter to preserve momentum while:

- service boundaries are still being established
- identity and gateway integration are still evolving
- the platform only needs a minimal end-to-end request path

### Phase 2: Move `agent-platform` Toward Option B

Refactor the runtime service toward a more native `AgentScope` Agent Service once the following are ready:

- session and identity propagation contracts are stable
- event protocol expectations between portal and runtime are clearer
- workspace strategy is chosen for development and shared environments
- storage and message bus choices are ready for adoption

### Phase 3: Keep Other Products On Plain Service Frameworks

Even after `agent-platform` moves toward Option B, keep the other products on conventional service stacks:

- `identity-broker`
- `tool-gateway`
- `policy-center`

These services are platform control-plane components, not agent runtime kernels.

## Practical Decision

For this repository, the recommended target is:

- `agent-platform`: evolve toward native `AgentScope` Agent Service semantics
- other backend products: remain conventional services with explicit HTTP contracts

This avoids overusing AgentScope where it does not add value, while still honoring the architectural decision that AgentScope should be the runtime kernel.

## Immediate Next Steps

1. keep the current `FastAPI` shell only as a transitional adapter
2. define the desired session and stream contract between portal and runtime
3. choose the first storage, message bus, and workspace strategy for development
4. introduce a more native AgentScope service integration inside `agent-platform`
5. avoid expanding custom runtime behavior in `FastAPI` if AgentScope already owns that concern

## Final Recommendation

The right long-term answer for `products/agent-platform` is not "`FastAPI` or `AgentScope`."

The better split is:

- `FastAPI` for generic platform services and explicit boundary control
- `AgentScope` Agent Service semantics for the runtime kernel itself

That gives the platform the cleanest alignment with the reference architecture without forcing every product into an agent-native serving model.
