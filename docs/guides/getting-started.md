# Getting Started

A task-oriented walkthrough that takes you from "I have a Kubernetes cluster" to "the agent
can invoke tools and I can see evidence in the portal."

## Prerequisites

| Tool | Minimum Version | Purpose |
|---|---|---|
| Kubernetes cluster | 1.28+ | Target deployment environment (kind, minikube, or real cluster) |
| `kubectl` | 1.28+ | Cluster interaction |
| `make` (GNU) | 4.x | Build and deploy orchestration |
| Docker or Podman | 24+ | Container image builds |
| `kustomize` | 5.x | Overlay rendering (bundled with `kubectl` 1.28+) |
| `uv` | 0.8+ | Python dependency management (installed automatically by Makefile targets) |

For local development, [kind](https://kind.sigs.k8s.io/) is recommended. The build system
supports auto-loading images into kind via `AUTO_LOAD_KIND=true`.

## Step 1: Clone and Sync Dependencies

```bash
git clone <repository-url> && cd luban-aiops
make sync
```

This runs `uv sync --frozen` for each Python product, installing dependencies from the
committed lockfiles.

## Step 2: Select a Runtime Profile

Choose an LLM provider profile before building:

```bash
shared/platform-ops/gitops/select-runtime-profile.sh deepseek
```

Available profiles: `deepseek`, `dashscope`, `openai`. This updates the Kustomize overlay to
include the selected provider's ConfigMap.

## Step 3: Provision the LLM API Key

Copy the example secrets file for your chosen profile and fill in your real API key:

```bash
cp shared/platform-ops/gitops/runtime-profiles/deepseek/runtime-secrets.example.env \
   shared/platform-ops/gitops/runtime-profiles/deepseek/runtime-secrets.env
```

Edit `runtime-secrets.env` and replace the placeholder with your actual API key. Then sync
the secret into the cluster:

```bash
shared/platform-ops/gitops/sync-runtime-secret.sh deepseek
```

## Step 4: Build Images

```bash
make build
```

This builds all product images with a coordinated image tag (e.g. `dev-k8s-<gitsha>`) and
writes the tag to `shared/platform-ops/gitops/dev-k8s/.images.env`.

For kind clusters, auto-load images:

```bash
make build AUTO_LOAD_KIND=true KIND_CLUSTER_NAME=<your-cluster-name>
```

## Step 5: Deploy

```bash
make deploy
```

This single command:

1. Applies the Kustomize overlay (`kubectl apply -k`)
2. Sets the correct image tags on all deployments (from `.images.env`)
3. Waits for rollout completion
4. Provisions token delegation secrets (shared credential between platform-gateway and
   identity-service)
5. Reconciles the portal's Keycloak OIDC client

> **Important:** Never deploy with raw `kubectl apply -k` — it resets image tags to the
> `dev-local` placeholder, causing `ErrImagePull`. Always use `make deploy` or run the
> deploy-overlay script which handles image tag patching.

To skip delegation secret provisioning (e.g. when secrets are managed externally):

```bash
SKIP_DELEGATION_SECRETS=true make deploy
```

## Step 6: Verify Pods

```bash
kubectl -n dev-luban-aiops get pods,svc
```

All pods should be `Running` with `READY 1/1`:

```
NAME                              READY   STATUS
web-ui-...                        1/1     Running
platform-gateway-...              1/1     Running
tool-gateway-...                  1/1     Running
agent-service-...                 1/1     Running
identity-service-...              1/1     Running
redis-...                         1/1     Running
```

## Step 7: Access the Portal

The dev-k8s overlay ships an `HTTPRoute` exposing the portal through the shared Envoy
Gateway. If your cluster's wildcard DNS is reachable, open either hostname directly:

- `https://aiops.luban.k8s.orb.local`
- `https://aiops.luban.metasync.cc`

Otherwise port-forward the web-ui service:

```bash
kubectl -n dev-luban-aiops port-forward service/web-ui 18080:8080
```

and open `http://localhost:18080` in your browser.

> Login uses the self-contained `luban-aiops` Keycloak realm. `make deploy` reconciles the
> realm, role groups, and one test user per role (`luban-admin`, `luban-approver`,
> `luban-operator`, `luban-observer`, `luban-auditor`, `luban-developer`); see the dev-k8s
> README for the shared dev password.

## End-to-End Verification Checklist

Use this checklist to confirm the full platform is operational:

- [ ] **Portal login**: click Login, complete Keycloak OIDC authentication, return to the portal
- [ ] **Session creation**: create a new chat session
- [ ] **Agent reply**: send a prompt (e.g. "What pods are running?") and receive a streamed
  response
- [ ] **Tool invocation**: the agent should invoke `k8s.list_pods` (visible in the response)
- [ ] **Evidence panel**: tool call details appear in the collapsible evidence group below
  the reply (tool name, status badge, duration, data summary)
- [ ] **Delegation working**: check metrics for successful token exchange:

```bash
kubectl -n dev-luban-aiops exec deployment/platform-gateway -- \
  curl -s localhost:8000/metrics | grep delegation
```

Look for `delegation_exchange_total{result="success"}` with a non-zero count.

## Secrets Summary

The following secrets must be provisioned before the platform is fully operational:

| Secret | K8s Secret Name | Purpose | Provisioning |
|---|---|---|---|
| LLM API key | `agent-platform-runtime-secrets` | Agent LLM calls | `sync-runtime-secret.sh <profile>` |
| Token delegation | `platform-gateway-runtime-secrets` + `identity-service-runtime-secrets` | Tool invocation auth | `sync-delegation-secrets.sh` (automatic with `make deploy`) |
| OIDC client secret | `identity-service-runtime-secrets` | Confidential OIDC client | Manual (if required by your IdP) |

## Next Steps

- [Configuration Reference](configuration-reference.md) — full environment variable map
- [Tool and Connector Guide](tool-configuration.md) — enable Elastic, understand K8s RBAC
- [Troubleshooting](troubleshooting.md) — resolve common deployment issues
