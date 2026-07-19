# Platform Ops

## Purpose

`platform-ops` contains the shared operational assets for running the workspace in Kubernetes and exposing it through enterprise infrastructure.

Typical contents include:

- Kubernetes manifests or Helm charts
- gateway configuration
- environment overlays
- shared deployment assets

## Ownership

Recommended owner:

- platform operations or platform engineering team

## Current Scope

This module currently provides the workspace placeholder and boundary definition for:

- Kubernetes deployment assets
- gateway and ingress configuration
- environment overlays and release wiring
- shared operational conventions across workspace products

## Expected Integration Points

- all deployable `products/` services
- `shared/shared-contracts` and `shared/shared-sdk` where runtime configuration depends on shared platform conventions
- cluster, ingress, and secret-management infrastructure

## Boundary

This module supports deployment and operations, but should not own application business logic.
