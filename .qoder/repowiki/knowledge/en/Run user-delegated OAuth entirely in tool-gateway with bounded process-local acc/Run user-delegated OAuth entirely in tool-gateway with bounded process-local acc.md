---
kind: design
name: Run user-delegated OAuth entirely in tool-gateway with bounded process-local access cache and strict provider contract
source: session
category: adr
---

# Run user-delegated OAuth entirely in tool-gateway with bounded process-local access cache and strict provider contract

_Source: coding plans from commit period 83e0f94 → e41007f — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
Delegated target credentials need atomic grant publication/status, safe browser-initiated enrollment, and protection against malformed or malicious provider responses while keeping machine-grant behavior unchanged.

## Decision drivers
- atomicity of custody + transaction state
- bounded resource usage
- strict validation over convenience
- no fallback to weaker auth mechanisms

## Considered options
- **Dedicated user-delegated client with Postgres-backed transactions, PKCE S256, explicit confidential-client auth, bounded HTTP deadlines/responses, and LRU access cache capped at 1,024 entries** — pros: isolates delegated flow; enforces hard caps on TTLs, response size, redirect chains, and session pooling; fails closed on missing infrastructure; cons: more configuration fields (`access_cache_ttl_seconds`, `refresh_max_lifetime_seconds`), stricter provider contract, no automatic retry/proxy inheritance
- **Reuse existing machine-grant client or rely on provider discovery and default HTTP settings** — pros: less code; cons: mixes machine and user flows; lacks bounded response sizes, redirect control, and strict scope/lifetime validation

## Decision
Wire a separate user-delegated client into tool-gateway lifespan and the HTTP/MCP authentication seam. Authorization URLs are built server-side with configured endpoint, client, callback, scope, audience/resource, state, and PKCE S256. All OAuth/token/identity/revocation calls use explicit Basic or POST auth, no redirects, no environment proxy inheritance, 10-second deadline, and 64-KiB response cap. Access cache is process-local, memory-only, LRU-bounded to 1,024 entries keyed by owner/set/target/audience/resource/scopes/configuration generation/credential epoch/recovery epoch. Delegated mode stays off until configuration, schema, key mount, trusted callback, identity linkage, and service auth are ready.

## Consequences
Provider responses are strictly validated: Bearer type, bounded values, usable lifetime, granted scope subset, and `json_immutable_id` profile identity claim compared against administered namespace/sub mapping. Missing refresh token or renewal endpoint is unsupported. Target 401 triggers grant-fenced invalidation; 403 remains a permission denial. HTTP requires destination policy plus exact resource-origin allowlist on every GET redirect hop; MCP supports only bearer-capable HTTP with no redirects or auto-reconnect retries. No pooled authenticated sessions across users.