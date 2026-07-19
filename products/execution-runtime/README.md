# Execution Runtime

## Purpose

`execution-runtime` runs approved bounded actions in isolated workers.

It is responsible for:

- receiving signed execution requests
- executing approved bounded actions
- isolating worker runtime behavior
- returning execution status and results
- producing execution audit artifacts

## Ownership

Recommended owner:

- automation or operations execution team

## Current Scope

This project currently provides the workspace placeholder and boundary definition for:

- isolated worker and adapter boundaries
- signed execution request handling
- execution status and result reporting
- execution audit artifact capture

## Expected Integration Points

- `policy-center` for approved and signed execution requests
- `tool-gateway` for action-specific adapters and connector pathways
- `operator-portal` and `agent-platform` for execution status visibility
- `shared/shared-contracts` for execution request, status, and audit schemas

## Boundary

This project does not decide whether an action is allowed and must never bypass policy or approval controls.
