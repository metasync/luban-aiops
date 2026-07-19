# Release 0 Local Environment

## Purpose

This directory contains the first Kubernetes deployment path for the `Release 0` service placeholders:

- `web-ui`
- `api-gateway`
- `agent-service`
- `identity-service`

## Scope

These manifests are intended to:

- establish service names and ports
- define baseline environment variables
- show the expected request path between services

These manifests do not yet provide:

- production hardening
- secret management
- ingress policy
- autoscaling
- persistent session storage

## Expected Images

The deployment manifest references placeholder image names that should be replaced with real build outputs later:

- `ghcr.io/metasync/luban-aiops/web-ui:release-0-dev`
- `ghcr.io/metasync/luban-aiops/api-gateway:release-0-dev`
- `ghcr.io/metasync/luban-aiops/agent-service:release-0-dev`
- `ghcr.io/metasync/luban-aiops/identity-service:release-0-dev`

## Apply

```bash
kubectl apply -k shared/platform-ops/release-0/local
```
