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

## Expected Integration Points

- `identity-broker` for `SSO` and normalized identity context
- `agent-platform` for chat sessions and streaming responses
- `policy-center` for approval queue and decision state
- `shared/shared-contracts` for typed API and event payloads

## Boundary

This project does not own policy decisions, identity normalization, or privileged execution logic.
