---
kind: external_dependency
name: Kubernetes Deployment Platform
slug: kubernetes
category: external_dependency
category_hints:
    - vendor_identity
    - framework_behavior
scope:
    - '**'
source_files:
    - shared/platform-ops/gitops/dev-k8s/kustomization.yaml
    - shared/platform-ops/gitops/deploy-overlay.sh
---

The platform deploys to Kubernetes using kustomize overlays for environment-specific configurations. The dev-k8s overlay provides a complete development environment including all four services (agent-platform, identity-broker, tool-gateway, operator-portal) plus Redis infrastructure. The build system supports kind cluster loading via AUTO_LOAD_KIND and KIND_CLUSTER_NAME environment variables for local development workflows.