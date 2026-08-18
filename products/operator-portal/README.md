# Operator Portal

## Purpose

`operator-portal` is the operator-facing web application for the platform.

It is responsible for:

- portal login and session entry
- chat and interaction UX
- evidence and incident context views
- approval queue and approval actions
- operator-visible execution status and audit visibility

## Ownership

Recommended owner:

- frontend or user experience team

## Current Scope

This project covers:

- portal shell and navigation
- chat and evidence presentation flows
- approval queue and approval response UX
- operator-visible audit and status views

Current implementation artifacts:

- `Dockerfile`
- `nginx.conf`
- `web-ui/index.html`
- `web-ui/app.js`
- `web-ui/styles.css`

Current browser baseline capabilities:

- two-column app shell: a left sidebar carries the logo and the function
  list; the main column shows one function view at a time (Chat, Settings &
  Debug, Audit trail) with state preserved across switches; narrow
  screens collapse the sidebar into a hamburger-triggered off-canvas
  drawer
- sidebar footer: a user card (initials avatar, username, icon-only
  Sign in / Sign out with tooltips; clicking the user opens a popup menu
  showing granted roles and — later — other user-related info) and a
  platform version card, kept separate from the function list
- `OIDC` login start through `platform-gateway`
- authorization-code callback completion through `identity-broker`
- authenticated portal logout entry point
- silent background token refresh roughly 60 seconds before JWT expiry (via
  `POST /api/v1/auth/refresh`); on failure the session is cleared and
  re-authentication is prompted
- session creation, prompt send, and streamed response rendering through the
  proxied gateway path
- request ID visibility for debug-oriented validation
- evidence panel rendering tool trace events (`tool_call` and `tool_result`)
  as cards with status badges, collapsible parameters and data summaries, and
  evidence metadata — visible when the agent invokes tools, hidden otherwise
  (SPEC-011)
- read-only durable audit trail view: filter bar, newest-first table, cursor
  pagination with a persistent "Load more" bar, and expandable event
  envelopes; the navigation entry renders only for identities whose roles
  hold `audit:read` (the gateway re-enforces the action server-side)
  (SPEC-013)
- Incidents panel: filterable incident list with auto-refresh, incident
  detail with the full triage report (severity assessment, evidence,
  hypotheses, ranked advisory next steps, cited skills), connector dispatch
  outcomes, Run triage with live triaging/failed states (failed runs expose
  the raw agent text), a Report incident form, and Continue in chat on the
  incident's dedicated session; viewing is gated by `incident:read`, acting
  by `incident:create` / `incident:triage` (SPEC-015)

## Expected Integration Points

- `identity-broker` for `SSO` and normalized identity context
- `agent-platform` for chat sessions and streaming responses
- `policy-center` for approval queue and decision state
- `shared/shared-contracts` for typed API and event payloads

## Boundary

This project does not own policy decisions, identity normalization, or privileged execution logic.
