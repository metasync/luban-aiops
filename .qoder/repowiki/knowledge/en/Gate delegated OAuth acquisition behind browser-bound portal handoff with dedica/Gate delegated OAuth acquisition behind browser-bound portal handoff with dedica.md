---
kind: design
name: Gate delegated OAuth acquisition behind browser-bound portal handoff with dedicated workload JWTs
source: session
category: adr
---

# Gate delegated OAuth acquisition behind browser-bound portal handoff with dedicated workload JWTs

_Source: coding plans from commit period b4148f4 → c4214cf — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
Browser-initiated OAuth enrollment must bind the initiating tab to a server-side transaction without exposing provider secrets to JavaScript, and platform-gateway ↔ tool-gateway handoffs must be authenticated without reusing human bearer tokens.

## Decision drivers
- browser-to-server binding integrity
- no secret leakage to client JS
- strict workload authentication between services
- bounded challenge lifetime

## Considered options
- **256-bit opaque browser secret stored as cookie hash, PKCE as authenticated ciphertext, consumed in one transaction; workload JWTs with pinned audiences `luban-target-authorization-handoff` and `luban-target-execution-handoff`** — pros: cookie bound to `__Host-*` path; single-use start token; callback claim commits before provider redemption; no Basic/static-auth fallback; internal routes not exposed by portal proxy
- **Reuse existing challenge-ID route for bearerless navigation or pass human bearer to platform-gateway** _(rejected)_ — pros: less code; cons: bearerless navigation cannot prove ownership; passing human bearer across services increases exposure surface

## Decision
Initiation creates a per-challenge 256-bit browser secret sent as `__Host-luban-oauth-<challenge_uuid>` (Secure, HttpOnly, SameSite=Lax, Path=/, no Domain), limited to eight outstanding cookies per browser. State is hashed and PKCE is authenticated ciphertext. New gateway routes handle `start`, `provider-url`, `callback`, `/{challenge_id}`, `/{challenge_id}/cancel`, and `browser-reset`. Platform-gateway calls `provider-url` and `callback` with a bounded `{start_token, browser_bindings}` body under RS256 workload JWTs with dedicated audiences; tool-gateway validates the browser proof before returning the secret provider URL or committing the callback claim.

## Consequences
Callback outcomes return bare 302 redirects with empty bodies; no provider code/state/token enters portal JS. The portal performs authenticated owner status retrieval on the return path and renders durable authorization frames (challenge/target/expiry only) instead of rendering HTML or dispatching tools. Browser reset cancels matching pending transactions and expires cookies without revoking target credentials.