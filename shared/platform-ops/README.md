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

- `gitops/dev-k8s/README.md`
- `gitops/dev-k8s/kustomization.yaml`
- `gitops/dev-k8s/base/`
- `gitops/runtime-profiles/`

The current implementation provides a single development Kubernetes overlay under a durable `gitops/` root. The `dev-k8s` overlay deploys all platform services (agent-platform, tool-gateway, identity-broker, operator-portal, Redis) into the `dev-luban-aiops` namespace. Provider choice is modeled as a separate shared runtime profile layer so the active profile remains reviewable and Git-diffable. The source manifests are grouped by shared infrastructure and product ownership so the overlay stays maintainable as the workspace grows.

## Expected Integration Points

- all deployable `products/` services
- `shared/shared-contracts` and `shared/shared-sdk` where runtime configuration depends on shared platform conventions
- cluster, ingress, and secret-management infrastructure

## Boundary

This module supports deployment and operations, but should not own application business logic.
