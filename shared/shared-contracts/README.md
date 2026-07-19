# Shared Contracts

## Purpose

`shared-contracts` contains the cross-project contracts that keep the workspace integrated without tight coupling.

Typical contents include:

- API schemas
- event schemas
- policy request and response models
- approval payloads
- audit record schemas

## Ownership

Recommended owner:

- platform architecture or core platform team

## Current Scope

This module currently provides the workspace placeholder and boundary definition for:

- shared API schemas
- event and streaming payloads
- policy, approval, execution, and audit models
- versioned contracts consumed across workspace products

## Expected Integration Points

- all `products/` modules that publish or consume shared interfaces
- `shared/shared-sdk` for generated or hand-written client helpers
- `docs/` for documented canonical contract definitions

## Boundary

This module should remain dependency-light and should not accumulate business logic.
