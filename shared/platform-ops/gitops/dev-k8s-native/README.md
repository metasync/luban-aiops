# Dev K8s Native Overlay

## Purpose

This overlay reuses the current development Kubernetes baseline but switches `agent-service` to the native `AgentScope 2.0` service surface.

Use this overlay when you want to validate:

- native `AgentScope` service exposure
- Redis-backed runtime coordination
- `api-gateway` native backend mode resolution without the transitional `/api/v1/...` adapter

## What Changes

Compared with `../dev-k8s-transitional`, this overlay:

- sets `AGENT_BACKEND_MODE=native`
- points `AGENT_SERVICE_URL` to `http://agent-service:8080`
- sets `AGENT_NATIVE_PORT=8080`
- starts `agent-service` with `uv run agent-service-native`
- changes the in-cluster `agent-service` service port to `8080`
- includes the same selected provider profile overlay as `dev-k8s-transitional`

In the source tree, these native-only overrides are now grouped by product under:

- `shared/platform-ops/gitops/dev-k8s-native/base/agent-platform/`
- `shared/platform-ops/gitops/dev-k8s-native/base/tool-gateway/`

The overlay keeps the shared runtime `ConfigMap` name stable and merges product-scoped native overrides into `platform-runtime-config`.

## Build Images

```bash
shared/platform-ops/gitops/dev-k8s-native/build-images.sh
```

This wrapper reuses the same product image builds as `dev-k8s-transitional`, but writes native-overlay image metadata to:

- `shared/platform-ops/gitops/dev-k8s-native/.images.env`

By default the generated tag uses the native overlay name for clarity:

- clean build: `dev-k8s-native-<gitsha>`
- dirty local build: `dev-k8s-native-<gitsha>-dirty-<timestamp>`

If you want extra traceability in local experiments, you can optionally add a profile suffix:

```bash
IMAGE_TAG_PROFILE=deepseek \
  shared/platform-ops/gitops/dev-k8s-native/build-images.sh
```

## Apply

```bash
shared/platform-ops/gitops/dev-k8s-native/deploy.sh
```

This apply path reads the latest `IMAGE_TAG` from `shared/platform-ops/gitops/dev-k8s-native/.images.env`, applies the native GitOps overlay, then updates each deployment to the explicit image tag and waits for rollout completion.

## Verify

```bash
kubectl -n dev-luban-aiops get pods,svc
kubectl -n dev-luban-aiops logs deployment/agent-service
kubectl -n dev-luban-aiops port-forward service/agent-service 18080:8080
```

Then verify the native surface directly:

```bash
curl http://127.0.0.1:18080/agent/ \
  -H 'X-User-ID: demo.operator'
```

The native AgentScope surface currently expects an `X-User-ID` header on direct `/agent/`, `/sessions/`, and `/chat/` calls.

You can also inspect gateway-side backend resolution:

```bash
kubectl -n dev-luban-aiops port-forward service/api-gateway 18081:8000
curl http://127.0.0.1:18081/api/v1/runtime
```

The gateway runtime payload should show:

- `configured_agent_backend_mode=native`
- `resolved_agent_backend_mode=native`

## Profile Selection

The native overlay shares the same provider profile model as the transitional overlay. The active root `kustomization.yaml` includes exactly one profile from:

- `shared/platform-ops/gitops/runtime-profiles/deepseek`
- `shared/platform-ops/gitops/runtime-profiles/dashscope`
- `shared/platform-ops/gitops/runtime-profiles/openai`

To switch both development overlays to a different provider and keep the desired state aligned in Git:

```bash
shared/platform-ops/gitops/select-runtime-profile.sh dashscope
shared/platform-ops/gitops/verify-runtime-profile.sh
```

If you are testing outside Luban CI and need to inject the secret manually, run:

```bash
shared/platform-ops/gitops/sync-runtime-secret.sh dashscope
```
