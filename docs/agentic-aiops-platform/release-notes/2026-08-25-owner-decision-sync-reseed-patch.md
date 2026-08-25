# v0.14.1 — Owner Decision Sync Re-seed Patch

Date: 2026-08-25
Release type: patch (portal correctness fix to the v0.14.0 SPEC-032
delivery; no new surfaces, no breaking changes)

## Summary

v0.14.1 fixes the v0.14.0 live-validation finding that the owner's open
chat window still stayed deaf after an external approval. The poll worked
— it observed the moved state and applied a fresh timeline — but it
applied through the wrong path, and the fresh timeline was silently
shadowed by the per-tab turn cache.

## Root Cause

`useChatStream.setSession(sessionId, history)` implements session
*switching*: it stashes the current session's turns into the per-tab
cache, then restores the target session's cached turns, falling back to
`history` only on a cache miss. When the SPEC-032 poll called it for the
session already on screen:

1. `previousId === sessionId`, so the current (stale) turns were stashed
   into the cache under that session id;
2. the restore read the cache back — a guaranteed hit — and the
   `?? history` fallback never applied.

Every successful poll therefore re-seeded the exact same stale turns.
The initial load worked because the cache was empty then, and a manual
refresh worked because the reload wipes the cache — exactly the behavior
observed in live validation.

## Change Set

### Fixed

- **Authoritative same-session re-seed**: `useChatStream` gains
  `reseedTurns(sessionId, turns)`. It replaces both the live turns and
  the cache entry, never moves the session pointer, and never aborts a
  stream; it is a no-op for any session other than the one on screen.
  The SPEC-032 poll's apply path now routes through it instead of
  `setSession`, so the decided card with attribution and the resumed
  turn appear within the poll interval, and a later session switch away
  and back restores the fresh timeline rather than a shadowed stale one.

### Changed

- Version lockstep bumped to 0.14.1 (VERSION, pyproject, metadata,
  `__version__`) and per-product `uv.lock` files refreshed.
- SPEC-032 plan and spec changelog synced to the reseed path.

## Validation

- Three new regression tests: the `setSession` cache-shadow behavior is
  pinned as documented (same-session history never applies), `reseedTurns`
  replaces live turns and the cache entry (switch away and back restores
  the fresh timeline), and a re-seed for a session not on screen is a
  no-op that never poisons the other session's cache.
- Portal vitest 129 passed; `tsc --noEmit` clean.

## Upgrade Notes

- No breaking changes; no new knobs. Rebuild and redeploy to pick up the
  fix — clusters running the v0.14.0 image keep working but retain the
  deaf-owner behavior until a manual refresh.
