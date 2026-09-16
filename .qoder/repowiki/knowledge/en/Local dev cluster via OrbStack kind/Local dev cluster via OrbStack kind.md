---
kind: external_dependency
name: Local dev cluster via OrbStack kind
slug: kubernetes-kind-orbstack
category: external_dependency
category_hints:
    - client_constraint
    - migration_status
scope:
    - '**'
source_files:
    - shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml
    - shared/platform-ops/gitops/runtime-profiles/browser-dev/
---

### Role
Development and demo deployments target a local Kubernetes cluster provisioned by OrbStack (which runs kind). All kustomize overlays under `shared/platform-ops/gitops/` render against this cluster for `make verify`, `make build`, and `make deploy`.

### Integration points
- `dev-k8s` overlay deploys the full platform (agent-service, tool-gateway, skills-hub, browser sidecar).
- `runtime-profiles/browser-dev` adds the browser sidecar profile, admin target pages ConfigMap, and NetworkPolicy.
- Demo scripts use `kubectl` port-forwards to `http://localhost:8080` (operator portal) and `http://localhost:9090/admin/` (simulated legacy admin panel).

### Stable constraints
- Cluster resources can exhaust under repeated deploys (OrbStack VM becomes unresponsive); prune exited containers and old images regularly.
- NetworkPolicy bugs (wrong port) block inter-pod traffic between agent-service and tool-gateway.