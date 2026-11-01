---
kind: design
name: Introduce immutable attempt_id fencing for unpublished credential operations
source: session
category: adr
---

# Introduce immutable attempt_id fencing for unpublished credential operations

_Source: coding plans from commit period b4148f4 → c4214cf — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
A review of the custody foundation found P1 concurrency defects: stale invalidations and late-arriving uncertainty cleanup could revoke active publications or successor claims that reused an epoch after rollback. The existing operation/publication capability hash was insufficient to distinguish concurrent attempts.

## Decision drivers
- concurrency safety under rollback/replay
- deterministic testability without timing sleeps
- preservation of successor claims after epoch reuse

## Considered options
- **Add random immutable attempt_id per unpublished operation, carried through claim/staging/publication/cleanup** — pros: uniquely identifies each attempt; cleanup can match exact binding+epoch+attempt; process-local blocks become attempt-scoped
- **Rely on existing operation/publication capability hash alone** _(rejected)_ — pros: no schema change; cons: cannot distinguish concurrent attempts on the same epoch; leaves stale invalidation and cleanup races open

## Decision
Generate a random `attempt_id` before any claim/staging operation can suspend, carry it through claim, staging, publication, and uncertainty cleanup; refresh keeps one attempt identity while authorization completion gets a fresh completion-attempt identity. Cleanup matches full binding + generation + epoch + attempt_id + unpublished status, and process-local uncertainty blocks are scoped per attempt.

## Consequences
Requires explicit custody schema migration v2 (not runtime DDL) adding attempt fields; legacy unpublished rows without attempt identity are fenced at upgrade time. Tests must use deterministic barriers rather than sleeps. Successor claims surviving old cleanup are preserved, but cleanup is more selective and must not broadly fail every pending transaction for an owner.