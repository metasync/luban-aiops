# Dev K8s Transitional Overlay

## Purpose

This directory contains the development-oriented Kubernetes transitional overlay for the current platform baseline services:

- `web-ui`
- `api-gateway`
- `agent-service`
- `identity-service`
- `redis`

## Scope

These manifests are intended to:

- establish service names and ports
- define baseline environment variables
- show the expected request path between services
- provide an in-cluster `Redis` dependency for `agent-service-native`

The `dev-k8s-transitional` name means this overlay is for development workflows on Kubernetes and keeps the current transitional HTTP request path intact. The service images and product packages remain intended for other environments as well, with different overlays and configuration for those targets.

These manifests do not yet provide:

- production hardening
- ingress policy
- autoscaling
- durable `Redis` persistence beyond the pod lifecycle

## Expected Images

The base deployment manifest uses neutral placeholder image tags:

- `luban-aiops/web-ui:dev-local`
- `luban-aiops/api-gateway:dev-local`
- `luban-aiops/agent-service:dev-local`
- `luban-aiops/identity-service:dev-local`

`build-images.sh` and `deploy.sh` replace those placeholders with the generated `IMAGE_TAG` for each rollout.

This development baseline also uses the upstream `redis:7.2-alpine` image for in-cluster runtime state and message coordination.

## Runtime Wiring

The `platform-runtime-config` `ConfigMap` keeps `agent-service` ready for a native AgentScope-compatible runtime path with:

- `AGENT_BACKEND_MODE=auto`
- `AGENT_TRANSITIONAL_PORT=8000`
- `AGENTSCOPE_AGENT_NAME=LubanOpsRuntime`
- `AGENTSCOPE_SYSTEM_PROMPT=...`
- `AGENTSCOPE_REDIS_HOST=redis`
- `AGENTSCOPE_REDIS_PORT=6379`
- `AGENTSCOPE_REDIS_DB=0`
- `AGENTSCOPE_WORKSPACE_DIR=/var/lib/luban-aiops/workspaces/agent-platform`

In the source tree this shared config is now assembled from product-scoped env fragments:

- `shared/platform-ops/gitops/dev-k8s-transitional/base/agent-platform/runtime-config.env`
- `shared/platform-ops/gitops/dev-k8s-transitional/base/tool-gateway/runtime-config.env`
- `shared/platform-ops/gitops/dev-k8s-transitional/base/identity-broker/runtime-config.env`

`AGENT_BACKEND_MODE` controls how `api-gateway` talks to `agent-service`:

- `transitional`
  - force the current `/api/v1/...` adapter path
- `native`
  - force the native `AgentScope` service surface
- `auto`
  - probe and resolve the backend mode at runtime

The `agent-service` image in this overlay starts the transitional `FastAPI` adapter entrypoint so the existing `/api/v1/...` gateway contract continues to work end-to-end. The same image still contains `agent-service-native`, so the sibling native overlay can switch to the native AgentScope service once the surrounding request path is aligned.

For entrypoint-specific overrides:

- use `AGENT_TRANSITIONAL_HOST` and `AGENT_TRANSITIONAL_PORT` for the transitional `FastAPI` surface
- use `AGENT_NATIVE_HOST`, `AGENT_NATIVE_PORT`, `AGENT_NATIVE_TITLE`, and `AGENT_NATIVE_VERSION` for the native `AgentScope 2.0` service surface
- do not use the old `AGENT_SERVICE_*` entrypoint variables any more

For the native-focused development variant, use the sibling overlay:

- `shared/platform-ops/gitops/dev-k8s-native`

The current `api-gateway` image now defaults to `auto` backend resolution. In this mode it prefers the transitional runtime metadata endpoint when available, but it can also fall back to the native AgentScope service surface without hardcoding that choice into every gateway route.

The active runtime provider is no longer hardcoded in this overlay root. Instead, the root `kustomization.yaml` includes exactly one provider profile from:

- `shared/platform-ops/gitops/runtime-profiles/deepseek`
- `shared/platform-ops/gitops/runtime-profiles/dashscope`
- `shared/platform-ops/gitops/runtime-profiles/openai`

Each profile contributes a committed non-secret `ConfigMap` named `agent-platform-runtime-profile`, which injects:

- `AGENTSCOPE_PROFILE`
- `AGENTSCOPE_PROVIDER`
- `AGENTSCOPE_MODEL_NAME`
- `AGENTSCOPE_BASE_URL`

That keeps provider switching Git-diffable and aligned with a future GitOps reconciliation flow.

The `web-ui` image serves the static portal through `nginx` and proxies `/api/` requests to the in-cluster `api-gateway` service. That keeps the browser entrypoint simple for development verification and avoids a separate CORS layer in this first slice.

The `redis` deployment uses `emptyDir` storage in this development baseline. That keeps setup simple for Kubernetes development testing, but it is not a durable production persistence model.

## Runtime Secrets

The `agent-service` deployment in this overlay supports an optional Kubernetes secret named `agent-platform-runtime-secrets`.

At minimum, provide:

- `AGENTSCOPE_API_KEY`

If Luban CI injects secrets for this deployment, that pipeline can provide the same secret contract directly and you can skip the local fallback workflow below.

Use the example file that matches the selected runtime profile:

- `shared/platform-ops/gitops/runtime-profiles/deepseek/runtime-secrets.example.env`
- `shared/platform-ops/gitops/runtime-profiles/dashscope/runtime-secrets.example.env`
- `shared/platform-ops/gitops/runtime-profiles/openai/runtime-secrets.example.env`

For manual local testing only, create the local secret file for the selected profile, for example:

```bash
cp shared/platform-ops/gitops/runtime-profiles/deepseek/runtime-secrets.example.env \
  shared/platform-ops/gitops/runtime-profiles/deepseek/runtime-secrets.env
```

Edit the copied `runtime-secrets.env` file and replace the placeholder value with your real key, then sync the selected profile secret into the cluster:

```bash
shared/platform-ops/gitops/sync-runtime-secret.sh deepseek
```

Restart `agent-service` so it picks up the new secret:

```bash
kubectl -n dev-luban-aiops rollout restart deployment/agent-service
kubectl -n dev-luban-aiops rollout status deployment/agent-service --timeout=120s
```

You can verify that the runtime left placeholder mode by port-forwarding `agent-service` directly:

```bash
kubectl -n dev-luban-aiops port-forward service/agent-service 18000:8000
curl http://127.0.0.1:18000/api/v1/runtime
```

When configured correctly, `agentscope_enabled` should become `true` and the response should also show the active provider, model, and runtime state.

## Profile Selection

To switch the active provider profile for both `dev-k8s-transitional` and `dev-k8s-native`:

```bash
shared/platform-ops/gitops/select-runtime-profile.sh deepseek
```

This updates the root `kustomization.yaml` files so the selected profile becomes the declared desired state in Git.

Verify the active profile overlays still render cleanly:

```bash
shared/platform-ops/gitops/verify-runtime-profile.sh
```

The runtime settings layer also validates that `AGENTSCOPE_PROFILE` matches `AGENTSCOPE_PROVIDER`, so a mismatched overlay fails fast at service startup.

## Build Images

```bash
shared/platform-ops/gitops/dev-k8s-transitional/build-images.sh
```

This script now emits an explicit `IMAGE_TAG` and saves the resulting image names in:

- `shared/platform-ops/gitops/dev-k8s-transitional/.images.env`

By default the generated tag uses the overlay name for clarity:

- clean build: `dev-k8s-transitional-<gitsha>`
- dirty local build: `dev-k8s-transitional-<gitsha>-dirty-<timestamp>`

If you want extra traceability in local experiments, you can optionally add a profile suffix:

```bash
IMAGE_TAG_PROFILE=deepseek \
  shared/platform-ops/gitops/dev-k8s-transitional/build-images.sh
```

That avoids the stale same-tag rollout problem caused by reusing a single static placeholder tag across multiple development rebuilds.

If your development cluster does not automatically see Docker images from the host runtime, you can ask the build script to load the images into `kind` as part of the same step:

```bash
AUTO_LOAD_KIND=true KIND_CLUSTER_NAME=<your-kind-cluster> \
  shared/platform-ops/gitops/dev-k8s-transitional/build-images.sh
```

## Apply

```bash
shared/platform-ops/gitops/dev-k8s-transitional/deploy.sh
```

This apply path uses the latest `IMAGE_TAG` from `.images.env`, applies the active root GitOps overlay, then updates each deployment to the explicit image tag and waits for rollout completion.

If you need to override the namespace or image tag manually:

```bash
NAMESPACE=dev-luban-aiops IMAGE_TAG=<explicit-tag> \
  shared/platform-ops/gitops/dev-k8s-transitional/deploy.sh
```

## Verify

```bash
kubectl -n dev-luban-aiops get pods,svc
kubectl -n dev-luban-aiops logs deployment/redis
```

To reach the portal in this development cluster through a single browser entrypoint:

```bash
kubectl -n dev-luban-aiops port-forward service/web-ui 8080:80
```

Then open `http://localhost:8080`. The portal defaults its gateway URL to the current origin, and `nginx` forwards `/api/` calls to `api-gateway`.

Once the pods are running, verify that `agent-service` starts successfully and that the portal can create a session and stream a response through the proxied gateway path.

You can also verify the gateway-side backend resolution directly:

```bash
kubectl -n dev-luban-aiops port-forward service/api-gateway 18080:8000
curl http://127.0.0.1:18080/api/v1/runtime
```

The response should now include:

- `configured_agent_backend_mode`
- `resolved_agent_backend_mode`
- `resolution_reason`
