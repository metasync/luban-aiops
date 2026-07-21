# Release 0 Local Environment

## Purpose

This directory contains the first Kubernetes deployment path for the `Release 0` service placeholders:

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

These manifests do not yet provide:

- production hardening
- secret management
- ingress policy
- autoscaling
- durable `Redis` persistence beyond the pod lifecycle

## Expected Images

The deployment manifest references placeholder image names that should be replaced with real build outputs later:

- `ghcr.io/metasync/luban-aiops/web-ui:release-0-dev`
- `ghcr.io/metasync/luban-aiops/api-gateway:release-0-dev`
- `ghcr.io/metasync/luban-aiops/agent-service:release-0-dev`
- `ghcr.io/metasync/luban-aiops/identity-service:release-0-dev`

The local baseline also uses the upstream `redis:7.2-alpine` image for in-cluster runtime state and message coordination.

## Runtime Wiring

The `release-0-runtime-config` `ConfigMap` configures `agent-service` for a native AgentScope-compatible runtime path with:

- `AGENTSCOPE_REDIS_HOST=redis`
- `AGENTSCOPE_REDIS_PORT=6379`
- `AGENTSCOPE_REDIS_DB=0`
- `AGENTSCOPE_WORKSPACE_DIR=/var/lib/luban-aiops/workspaces/agent-platform`

The `redis` deployment uses `emptyDir` storage in this local baseline. That keeps setup simple for local Kubernetes testing, but it is not a durable production persistence model.

## Apply

```bash
kubectl apply -k shared/platform-ops/release-0/local
```

## Verify

```bash
kubectl -n luban-aiops-local get pods,svc
kubectl -n luban-aiops-local logs deployment/redis
```

Once a real `agent-service` image exists, verify that it resolves the in-cluster `redis` service and starts with the mounted workspace directory.
