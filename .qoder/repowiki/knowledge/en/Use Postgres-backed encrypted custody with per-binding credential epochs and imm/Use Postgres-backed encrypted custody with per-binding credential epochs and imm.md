---
kind: design
name: Use Postgres-backed encrypted custody with per-binding credential epochs and immutable operation fences
source: session
category: adr
---

# Use Postgres-backed encrypted custody with per-binding credential epochs and immutable operation fences

_Source: coding plans from commit period 199331f → 83e0f94 — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
SPEC-070 foundation must provide durable, multi-replica-safe OAuth refresh-token custody for delegated targets. In-memory storage is insufficient for production replicas, and plaintext persistence would expose secrets if the database were compromised.

## Decision drivers
- multi-replica safety
- secrecy of refresh tokens
- idempotent recovery
- bounded rotation

## Considered options
- **In-memory transaction store with file-based secret cache** _(rejected)_ — pros: simplest implementation; no external dependency; cons: no cross-process coordination; process restart loses state; cannot prove durability under concurrent replicas
- **Postgres-backed AuthorizationTransactionStore with AES-256-GCM envelopes and per-binding epochs** — pros: atomic single-use claims, fenced refresh/authorization, versioned keyring rotation, tombstoned revocation, deterministic cleanup; cons: requires a dedicated gateway role, schema migrations, and mounted keyring; adds operational surface

## Decision
Implement `AuthorizationTransactionStore` with memory (dev/tests only) and Postgres backends behind a fail-closed factory. Persist only encrypted refresh credentials and PKCE verifiers using `cryptography` AES-256-GCM with a fresh 96-bit nonce; bind envelope AAD to owner, target, set ID, configuration generation, credential epoch, scopes, verified account, challenge ID, and expiry. Use per-binding credential epochs plus random immutable `attempt_id` on unpublished operations so callback installation, refresh completion, and uncertainty cleanup are compare-and-set safe. Keyring files carry versioned 32-byte keys and a separately mounted HMAC key; unknown or stale keys fail closed without retained-key fallback.

## Consequences
Durable custody works across replicas but requires Postgres, a non-superuser gateway role, and a mounted keyring. Refreshes and authorization callbacks are serialized through single-use claims; uncertain commits never release access tokens or retry consumed refresh secrets. Backup/restore is an operator-controlled fenced procedure that advances the recovery epoch and forces reauthorization — automatic rollback detection is not claimed.