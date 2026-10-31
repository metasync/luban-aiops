---
kind: design
name: Introduce immutable attempt_id and versioned custody schema for credential operations
source: session
category: adr
---

# Introduce immutable attempt_id and versioned custody schema for credential operations

_Source: coding plans from commit period 83e0f94 → e41007f — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
The delegated-custody layer had unresolved P1 concurrency defects where stale invalidations, late cleanup, and overlapping uncertainty could revoke successor claims or invalidate the wrong generation of a credential store.

## Decision drivers
- concurrency safety under rollback/replay
- durable correctness over performance
- explicit migration over runtime DDL

## Considered options
- **Add random immutable attempt_id to unpublished operations and make uncertainty blocks attempt-scoped** — pros: prevents stale cleanup from revoking successors; ties lifecycle to one logical operation; works with epoch reuse after rollback; cons: requires custody schema v2 migration and careful handling of legacy rows without attempt identity
- **Fix races by adding more locks or timeouts around existing fields** — pros: smaller change surface; cons: does not address cross-process claim/epoch reuse or stale-generation invalidation; timing-based fixes are fragile

## Decision
Add a random immutable `attempt_id` to unpublished credential operations, scope process-local uncertainty blocks per attempt, and migrate the custody prototype schema to version 2 with explicit readiness checks. Observed-generation snapshots in `invalidate_observed` are captured before the first await so stale invalidations cannot affect newer generations.

## Consequences
Custody code paths (`delegated_custody.py`, `authorization_transaction_store.py`, `custody_schema.py`) must carry attempt identity through claim/staging/publication/cleanup. Legacy rows lacking attempt identity are fenced during migration. Tests use deterministic barriers instead of sleeps to prove failure-first behavior across refresh, authorization staging, cleanup, and observed-generation races.