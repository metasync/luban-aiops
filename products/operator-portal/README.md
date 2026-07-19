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

This project currently provides the workspace placeholder and boundary definition for:

- portal shell and navigation
- chat and evidence presentation flows
- approval queue and approval response UX
- operator-visible audit and status views

## Expected Integration Points

- `identity-broker` for `SSO` and normalized identity context
- `agent-platform` for chat sessions and streaming responses
- `policy-center` for approval queue and decision state
- `shared/shared-contracts` for typed API and event payloads

## Boundary

This project does not own policy decisions, identity normalization, or privileged execution logic.
