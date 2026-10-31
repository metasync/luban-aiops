---
kind: design
name: Bind browser-initiated OAuth through platform-gateway with cookie proof and dedicated workload JWT audiences
source: session
category: adr
---

# Bind browser-initiated OAuth through platform-gateway with cookie proof and dedicated workload JWT audiences

_Source: coding plans from commit period 83e0f94 → e41007f — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
Browser navigation cannot be trusted with a bearer, yet the portal must start an OAuth flow without exposing secrets or allowing arbitrary redirect targets.

## Decision drivers
- browser binding security
- separation of human vs. workload routes
- no stored human bearer for callbacks
- bounded UI stop behavior

## Considered options
- **Five ratified portal routes plus `browser-reset`, with 256-bit per-challenge cookie secret, hashed state/PKCE ciphertext, workload JWTs pinned to `luban-target-authorization-handoff`, and a bounded kernel stop latch** — pros: cookie proof checked before consuming start/state and again at callback; callback returns bare 302 with no-store/no-cache; UI shows inline Authorize/status/Cancel controls without model-authored challenges; cons: requires custody v3 migration for browser/attempt fields, explicit runbook for admission fencing, and careful separation of gateway result metadata from model text
- **Let the portal call the provider directly or expose challenge-ID routes that bearerless navigation can consume** — pros: fewer hops; cons: exposes secrets to the browser or trusts unauthenticated challenge IDs; violates the ratified route set

## Decision
Keep the five ratified portal routes and add `POST /api/v1/targets/authorizations/browser-reset`. Tool-gateway exposes `/start`, `/provider-url`, `/callback`, status, cancel, and reset; the last three are platform-gateway workload-only using RS256 projected service-account tokens with audience `luban-target-authorization-handoff`. Browser initiation creates a 256-bit opaque per-challenge secret sent as `__Host-luban-oauth-<challenge_uuid>` with Secure/HttpOnly/SameSite=Lax/Path=/ and no Domain, limited to eight outstanding cookies per browser. Callback outcomes return bare 302 with empty body, no-store/no-cache, and no-referrer. A bounded per-turn latch serializes tool execution within an enabled turn and stops further tool calls after the first authorization-required result, surfacing a safe guidance frame instead of another provider call.

## Consequences
State and PKCE are stored as hash/authenticated ciphertext; custody v3 migration fences incompatible pending prototype transactions. No provider code/state/token/URL enters portal JavaScript or storage. Status is informational — acquisition rechecks revocation/configuration. Continue is a new user turn requiring current policy, HITL, signed request, and fresh durable claim. Authorization frames go into durable evidence allowlists but never include browser proofs.