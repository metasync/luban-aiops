# Policy Center

## Purpose

`policy-center` is the control authority for authorization, policy evaluation, and approval routing.

It is responsible for:

- evaluating policy requests
- returning `allow`, `deny`, `require_approval`, or `allow_with_conditions`
- managing approval requirements and decision flow
- enforcing role, environment, and action boundaries

## Ownership

Recommended owner:

- platform security or control-plane team

## Current Scope

This project currently provides the workspace placeholder and boundary definition for:

- policy evaluation service boundaries
- approval routing and decision-state handling
- environment and role-based control logic
- future integration points for bounded action authorization

Current implementation status:

- `policy-center` is still a stub with no running service
- the policy contract it will serve is already defined in `shared/shared-contracts` (`schemas/policy-rule.schema.json`, `schemas/policy-decision.schema.json`, `policies/policy-default.yaml`) per `SPEC-004`
- the `action_authz` slice (`allow`/`deny`, deny-by-default) is currently evaluated inside `tool-gateway` (`services/policy_engine.py`); when this product becomes a service, that module lifts behind a `POST /policy/evaluate` endpoint returning the same decision object

## Expected Integration Points

- `identity-broker` for normalized user and group context
- `agent-platform` for policy evaluation requests
- `operator-portal` for approval workflows and decision visibility
- `execution-runtime` for signed execution authorization handoff
- `shared/shared-contracts` for policy and approval schemas

## Boundary

This project does not own portal UX, identity federation, or direct connector execution.
