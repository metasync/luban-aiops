---
kind: design
name: Gate delegated acquisition behind strict configuration validation, origin allowlists, and a process-local LRU access cache with no positive validity cache
source: session
category: adr
---

# Gate delegated acquisition behind strict configuration validation, origin allowlists, and a process-local LRU access cache with no positive validity cache

_Source: coding plans from commit period 199331f → 83e0f94 — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
Delegated OAuth client configuration must reject malformed endpoints, disallow discovery, and prevent accidental reuse of revoked or stale grants across replicas.

## Decision drivers
- explicit configuration over discovery
- origin pinning
- replica consistency
- bounded memory

## Considered options
- **Auto-discover OAuth endpoints and rely on provider metadata** _(rejected)_ — pros: less configuration; cons: allows unexpected endpoints; violates the explicit-configuration mandate; opens redirect/proxy attack surface
- **Strictly parsed `oauth2_authorization_code` config with space-delimited `oauth_origins`/`resource_origins`, S256 PKCE, `client_secret_basic`/`client_secret_post`, `store=postgres`, and a process-local LRU access cache keyed by owner/set/target/scopes/generation/epoch/recovery_epoch** — pros: rejects invalid values, pins HTTPS origins, bounds memory to 1,024 entries, rereads policy/linkage before every release; cons: operator must supply all endpoints and scopes; missing refresh support is explicitly unsupported

## Decision
Delegated configuration is parsed by a dedicated parser behind `tools/credential_sets.py` that pins required fields (`target`, `authorization_url`, `token_url`, `client_id`, `client_secret`, `client_auth`, `redirect_uri`, `scope`, `allowed_scopes`, `oauth_origins`, `resource_origins`, `pkce_method=S256`, `store=postgres`, `config_revision`, `identity_profile=json_immutable_id`, `identity_claim`, `identity_mapping_path`) and rejects unknown keys, invalid URLs, duplicate/blank scopes, and origins outside the set's allowlists. Access caching is process-local, LRU-bounded to 1,024 entries, and invalidated on local revocation/configuration change/key rotation; there is no positive generation-validity cache, so every checkout checks the authoritative database generation.

## Consequences
Configuration errors fail fast instead of silently falling back to other schemes. Origin allowlists replace connector-wide general allowlists. Missing refresh/renewal endpoints are typed as unsupported rather than retried. Cross-process refresh is serialized through the corrected durable claim; another replica may perform a subsequent serialized refresh but never shares the access token.