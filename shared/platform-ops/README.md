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

Current implementation artifacts:

- `gitops/dev-k8s-transitional/README.md`
- `gitops/dev-k8s-transitional/kustomization.yaml`
- `gitops/dev-k8s-transitional/base/`
- `gitops/dev-k8s-native/README.md`
- `gitops/dev-k8s-native/kustomization.yaml`
- `gitops/dev-k8s-native/base/`
- `gitops/runtime-profiles/`

The current implementation provides development-oriented Kubernetes overlays under a durable `gitops/` root, while the milestone-specific `Release 0` naming remains in planning and release documentation. `dev-k8s-transitional` keeps the current gateway and portal contract running through the transitional HTTP adapter, while `dev-k8s-native` switches `agent-service` to the native `AgentScope` service surface. The transitional baseline includes an in-cluster `Redis` deployment so the native runtime path remains available in the same development cluster family. Provider choice is now modeled as a separate shared runtime profile layer so the active profile remains reviewable and Git-diffable. The source manifests are grouped by shared infrastructure and product ownership so each overlay stays maintainable as the workspace grows.

## Expected Integration Points

- all deployable `products/` services
- `shared/shared-contracts` and `shared/shared-sdk` where runtime configuration depends on shared platform conventions
- cluster, ingress, and secret-management infrastructure

## Boundary

This module supports deployment and operations, but should not own application business logic.
