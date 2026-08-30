# v0.27.2 — Session-Availability Gate and Gateway Sign-In Postures

Date: 2026-08-30
Release type: patch (same-day follow-up to a live test of v0.27.1: one
portal UX gate and two gateway robustness fixes — no routes added, no
policy actions, no audit event types, no response shapes changed)

## Summary

A live test of the v0.27.1 remediation surfaced a confusing edge of the
SPEC-015/SPEC-023 deep link: on an incident whose triage session had
expired, **Continue in chat** opened the chat view and the session-scoped
**Draft as skill** answered a raw "Request failed 404". This patch gates
the deep link at render time and hardens two adjacent gateway surfaces.

## The report

Triage sessions are single-owner and ephemeral (idle TTL sweep, 1 hour
default). Once the triage session expires — or when another operator owns
it — the incident still carries the session id, but the session store no
longer answers for this caller. The deep link then lands on a session the
backend legitimately 404s, which surfaced as a confusing failure instead
of an explanation.

## What changed

### Continue-in-chat availability gate (portal)

- The incident-detail **Continue in chat** button now renders disabled,
  with an explanatory tooltip, whenever the incident's triage session is
  not among the caller's own live sessions — expired, not yet visible,
  or owned by another operator. The gate reads the portal's existing
  caller-scoped session list (the same list the session panel polls);
  no extra API call and no new endpoint.
- Ownership is opaque by design (a foreign session answers the same 404
  as a gone one), so the tooltip names all three causes and points at
  the ownership-free alternative: **Draft as skill** on the incident
  never depends on session ownership.
- The chat header's **Draft as skill** keeps a 404 toast as a
  race-window safety net: a session can expire between render and click,
  so the proactive gate handles the common path and the toast handles the
  rest. The toast names the cause and the incident-anchored alternative.

### Runtime version surface (gateway)

- `GET /api/v1/runtime` now carries the platform `version` alongside the
  agent runtime metadata, so probes and the portal's Settings inventory
  can read the deployed release without another endpoint.

### Sign-in leg hardening (gateway)

- The identity-service legs (login-url, login, callback, logout-url,
  refresh) now ride the house proxy error model: the identity service's
  own 4xx postures pass through with their detail, while 5xx and
  transport failures answer a structured 502 — the sign-in surface never
  answers a raw 500 when a leg races a rollout.

## Surfaces deliberately unchanged

- Session-scoped drafting stays owner-only; incident-anchored drafting
  stays dual-gated and ephemeral. No policy actions, audit event types,
  routes, or response shapes changed.
- The 404 itself is correct behavior — a gone or foreign session is not
  found; the patch fixes the *presentation*, not the posture.

## Verification

- Gateway 285 tests (incl. the new runtime-version and auth-leg
  suites), portal 225 vitest tests (incl. the gate visibility, tooltip,
  and 404-toast suites) — all green; `make verify` green before and
  after `make build`; `make deploy` green.
- Browser live check on aiops.luban.metasync.cc, four scenarios green:
  clean sign-in (auth legs), `/api/v1/runtime` reporting `0.27.2`,
  **Continue in chat** disabled with the tooltip on the exact incident
  from the report, and **Draft as skill** preview still working on the
  same incident.
