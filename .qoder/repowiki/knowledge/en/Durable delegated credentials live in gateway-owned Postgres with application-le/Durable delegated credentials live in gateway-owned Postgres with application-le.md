---
kind: design
name: Durable delegated credentials live in gateway-owned Postgres with application-level authenticated encryption and separate key mounts
source: session
category: adr
---

# Durable delegated credentials live in gateway-owned Postgres with application-level authenticated encryption and separate key mounts

_Source: coding plans from commit period a96f2ac → 102c0b4 — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
Delegated tokens may need persistence across process restarts and replicas, but access tokens themselves must remain memory-only. The plans require atomic rotation, revocation invalidation across replicas, and protection against plaintext leakage on disk.

## Decision drivers
- cross-process concurrency control
- separation of encrypted data from keys
- no fallback to files or machine credentials
- bounded refresh-token storage only when the grant requires it

## Considered options
- **Gateway-owned Postgres tables with application-level authenticated encryption and separately mounted keys** — pros: uses existing infrastructure, supports atomic rotation/revocation, binds ciphertext to owner/target, avoids plaintext files
- **File-based secret store or OS keyring** _(rejected)_ — pros: simpler single-process setup; cons: no cross-process coordination, harder rotation/revocation, risk of plaintext exposure, weaker isolation

## Decision
Use gateway-owned Postgres tables keyed by trusted identity namespace, subject, target, and configuration generation. Encrypt required durable secrets with authenticated encryption, bind ciphertext to owner/target, store key identifiers/versions, mount keys separately from database credentials/data, and invalidate cached acquisitions on rotation or revocation. Access tokens stay in memory; durable refresh tokens exist only as encrypted records if the approved grant issues them.

## Consequences
Adds a Postgres dependency and dedicated database role for the tool-gateway. Requires real disposable-Postgres tests for ciphertext-only persistence, wrong-key rejection, concurrent rotation, crash recovery, revocation racing refresh, and restart behavior. Store failure must fail closed — never fall back to a file or machine credential.