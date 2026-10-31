---
kind: design
name: Bind browser-initiated OAuth flows to per-challenge cookies and signed workload JWTs rather than bearerless challenge IDs
source: session
category: adr
---

# Bind browser-initiated OAuth flows to per-challenge cookies and signed workload JWTs rather than bearerless challenge IDs

_Source: coding plans from commit period 199331f → 83e0f94 — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
The portal must start an OAuth flow from a user's browser and hand the resulting provider URL to tool-gateway without exposing secrets in URLs or relying on unauthenticated request bodies.

## Decision drivers
- browser-to-server binding
- no secret in URLs
- workload identity verification
- single-use guarantees

## Considered options
- **Return opaque challenge UUID and let the browser call `/provider-url/{challenge_id}` directly** _(rejected)_ — pros: minimal backend state; cons: bearerless endpoint can be guessed/replayed; does not bind to the initiating browser tab
- **Per-challenge 256-bit browser secret stored as a hash in transaction-secret state, issued via a `__Host-luban-oauth-<uuid>` cookie, then validated by a platform-gateway-only `/authorizations/provider-url` route** — pros: cookie scope + `SameSite=Lax` + `Secure` + `HttpOnly` binds the tab; start token remains single-use; workload JWT pins the caller; cons: requires two new internal routes, browser cookie bookkeeping, and explicit migration fields

## Decision
On initiation, create a 256-bit per-challenge browser secret, store its hash in transaction-secret state, and return it in a `__Host-luban-oauth-<challenge_uuid>` cookie (`Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/`, no Domain). The portal calls the platform-gateway-only `POST /api/v2/targets/authorizations/provider-url` with `{start_token, browser_bindings}` after verifying the cookie and consuming the matching stored transaction. Callbacks use the same discriminated body with state and browser bindings. Internal routes are authenticated with RS256 service-account JWTs pinned to audience `luban-target-authorization-handoff`; no Basic/static-auth fallback is allowed.

## Consequences
A replayed or cross-tab request fails because the cookie is host-scoped and the start token is single-use. The browser proof is checked again at callback claim. Browser-reset cancels pending transactions and expires cookies without revoking target credentials. The approach adds cookie and migration bookkeeping but eliminates bearerless secret exposure.