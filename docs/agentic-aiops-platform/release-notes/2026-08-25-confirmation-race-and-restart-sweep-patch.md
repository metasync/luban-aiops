# v0.13.1 — Confirmation Race and Restart-Sweep Patch

Date: 2026-08-25
Release type: patch (agent-platform correctness fixes from the v0.13.0
code review; no new surfaces, no breaking changes)

## Summary

v0.13.1 is a follow-up patch to v0.13.0 that ships the two Major
remediations from the SPEC-031 post-delivery code review, plus release
housekeeping (version lockstep and dependency lockfiles refreshed,
guide wording synced).

## Change Set

### Fixed

- **Confirm race window between claim and stream end**: the durable
  confirmation outcome was written only in the resumed turn's `finally`
  block, so a racing approver answering while the winner's turn still
  streamed got a bare `404` instead of the structured outcome. The
  confirm route now persists the outcome at claim time — the claim is
  single-flight and the decision irrevocable once claimed — so racers
  get `409 already_resolved` the moment the winner claims. The resume's
  `finally` write remains as an idempotent safety net, and
  `mark_resolved` is first-write-wins in both backends (in-memory
  pending-guard + SQL `AND status = 'pending'`).
- **Startup sweep expired every pending row globally**: the Postgres
  backend's startup sweep flipped all pending rows to `expired`, so a
  sibling replica's restart killed another pod's live park and defeated
  cross-replica durability. The sweep (`_CLOSE_STALE_PENDING`) is now
  scoped to rows parked longer ago than the HITL confirmation TTL
  (`AGENT_HITL_CONFIRM_TIMEOUT`, default 600s): a park past its TTL
  answers no confirmation on any replica (claim raises
  `ConfirmationExpired`), so closing it is safe across replicas;
  younger rows stay untouched.

### Changed

- Version lockstep bumped to 0.13.1 (VERSION, pyproject, metadata,
  `__version__`) and per-product `uv.lock` files refreshed.
- Changelog, release notes, `approval-and-hitl.md`, and
  `troubleshooting.md` wording synced to the TTL-scoped sweep and the
  claim-time outcome write.

## Validation

- New tests cover all three remediations: claim-time persistence before
  the stream drains plus the racing `already_resolved` 409, idempotent
  `mark_resolved` in both backends, TTL-scoped sweep SQL shape and
  factory wiring (`AGENT_HITL_CONFIRM_TIMEOUT` honored, bad value falls
  back to 600s).
- agent-platform 467 passed; portal vitest 117 passed; `make verify`
  gate green at 0.13.1.
- L3 deep security review at the push gate returned zero findings.

## Upgrade Notes

- No breaking changes; no new knobs (the sweep reads the existing
  `AGENT_HITL_CONFIRM_TIMEOUT`). Rebuild and redeploy to pick up the
  fixes — clusters running a v0.13.0 image keep working but retain the
  narrow mid-stream race window and the global restart sweep.
