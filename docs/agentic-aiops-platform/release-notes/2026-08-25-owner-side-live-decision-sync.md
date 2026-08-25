# v0.14.0 — Owner-Side Live Decision Sync (SPEC-032)

Date: 2026-08-25
Release type: minor (portal-only feature closing a v0.13.1 live-validation
finding; no backend, contract, or policy changes)

## Summary

v0.14.0 closes the last presentation gap in the approval-gated bounded
action flow: while a confirmation card is parked, the session owner's open
chat window now learns about a decision made elsewhere — the approver
inbox, a second browser session — without a manual refresh. The card flips
to its resolution with decider attribution, and the agent's resumed reply
appears in the transcript as it lands.

The finding came from the v0.13.1 live validation: an operator parked a
tier_2 confirmation and watched their chat window while the designated
approver approved from the Approvals view. Nothing happened in the owner's
window until a manual refresh. The bounded action itself had already
executed server-side at approval time — the gap was purely presentation:
the `confirmation_result` frame only rides the answering stream, and the
owner's chat view had no sync path for anyone else's decision.

## Change Set

### Added

- **`usePendingDecisionPoll` hook** (portal chat): while the active
  session renders at least one pending confirmation card, polls the
  existing session-detail surface (`GET /api/v1/sessions/{id}` — the same
  surface that seeds durable cards per SPEC-031 R-2) every 5 seconds.
  Responses are change-gated by a cheap fingerprint (confirmation
  statuses + transcript shape), so identical responses never rebuild the
  turn timeline — no scroll disturbance, no flicker, no composer loss.
  A moved state re-seeds the timeline through the same `transcriptToTurns`
  path the initial load uses.
- **Settle window**: after the last pending card resolves, polling
  continues for a bounded number of ticks (12) because the resumed turn's
  transcript content lands when the resume stream ends — which can trail
  the claim-time record write (SPEC-031 review fix) by a few seconds.
  The window is scoped to its session and stops on its own.
- **Bounded by construction**: no polling when no card is pending (idle
  or decided-only sessions), no polling while any chat stream is active
  (a poll can neither abort nor interleave with a live stream), and
  in-flight responses are dropped if a stream starts or the session
  switches before they land. Transport errors keep the last-good view
  and retry on the next tick.
- Outcome parity: approvals, denials, and expirations all flip through
  the same poll path with the same attribution rendering.

### Changed

- Version lockstep bumped to 0.14.0 (VERSION, pyproject, metadata,
  `__version__`) and per-product `uv.lock` files refreshed.
- `approval-and-hitl.md` and `portal-user-guide.md` document the live
  owner-side sync.

## Explicitly Not Changed

- No backend surface: the session detail already carries live
  confirmation state and the completed resumed transcript.
- No server push (SSE/WebSocket): the platform's live surfaces all poll
  (the approver inbox polls at 30s + focus); the bounded 5s poll keeps
  the idiom and stays portal-only. Revisit only if more surfaces need
  sub-second sync.
- Decision semantics are untouched: SPEC-030 tier enforcement, SPEC-031
  claim-time outcome writes and `already_resolved` race responses all
  behave exactly as in v0.13.1.

## Validation

- 9 new hook tests: external approval flips the pending card and
  re-seeds once (change gate holds afterwards), no polling while idle or
  streaming, in-flight response dropped when a stream starts, settle
  window survives the pending → settled rerun and stops on its own,
  deny/expired parity through the same path, transport errors keep the
  last-good view, session-switch drops stale responses.
- Portal vitest 124 passed; `tsc --noEmit` clean.

## Upgrade Notes

- No breaking changes; no new knobs. Rebuild and redeploy to pick up the
  live sync — clusters running a v0.13.x image keep working, but the
  owner's open window still needs a manual refresh to see externally
  made decisions.
