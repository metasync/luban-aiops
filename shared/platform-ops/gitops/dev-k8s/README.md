# Dev K8s Overlay

## Purpose

This directory contains the development Kubernetes overlay for the platform baseline services:

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
- provide an in-cluster `Redis` dependency for session storage and AgentScope coordination

The `dev-k8s` overlay is the single development deployment for the platform. It deploys the v2 agent-service contract surface consumed by `api-gateway`.

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

`make build` and `make deploy` replace those placeholders with the generated `IMAGE_TAG` for each rollout.

This development baseline also uses the upstream `redis:7.2-alpine` image for in-cluster runtime state and message coordination.

## Runtime Wiring

The `platform-runtime-config` `ConfigMap` is assembled from product-scoped env fragments:

- `shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env`
- `shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env`
- `shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-config.env`

The identity-broker config fragment defines the browser callback and logout redirect defaults for the `OIDC` flow. The committed baseline matches the validated shared development IdP path in `dev-luban-aiops`:

- `KEYCLOAK_BASE_URL=https://idp.apps.metasync.cc`
- `KEYCLOAK_REALM=snd`
- `OIDC_CLIENT_ID=snd-luban-aiops-portal`
- `OIDC_REDIRECT_URI=http://localhost:18080/callback`
- `OIDC_POST_LOGOUT_REDIRECT_URI=http://localhost:18080/`
- `OIDC_SCOPES=openid groups`

The corresponding keys remain:

- `KEYCLOAK_BASE_URL`
- `KEYCLOAK_REALM`
- `OIDC_CLIENT_ID`
- `OIDC_REDIRECT_URI`
- `OIDC_POST_LOGOUT_REDIRECT_URI`
- `OIDC_SCOPES`

The overlay also carries a Git-tracked reconciliation script for the shared
Keycloak browser client:

- `shared/platform-ops/gitops/dev-k8s/reconcile-portal-oidc-client.sh`

That script treats the overlay `identity-broker/runtime-config.env` values as
the desired browser client contract for `snd-luban-aiops-portal`. It reconciles:

- client existence and PKCE/public-client settings
- `redirectUris`
- `webOrigins`
- `post.logout.redirect.uris`
- client protocol mappers for `preferred_username` and `email`

The `agent-service` deployment runs the v2 FastAPI adapter entrypoint (`uv run agent-service`). The `api-gateway` connects to `http://agent-service:8000` and consumes the `/api/v2/` contract exclusively (see SPEC-002 and ADR-0003).

The active runtime provider is selected via the root `kustomization.yaml`, which includes exactly one provider profile from:

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
curl http://127.0.0.1:18000/api/v2/runtime
```

When configured correctly, `runtime_mode` should be `agentscope` and `runtime_state` should be `ready`, and the response shows the active provider and model. `/api/v2/health` reports `configured: true`.

## Profile Selection

To switch the active provider profile for the `dev-k8s` overlay:

```bash
shared/platform-ops/gitops/select-runtime-profile.sh deepseek
```

This updates the root `kustomization.yaml` files so the selected profile becomes the declared desired state in Git.

Verify the active profile overlays still render cleanly:

```bash
shared/platform-ops/gitops/verify-runtime-profile.sh
```

The runtime settings layer also validates that `AGENTSCOPE_PROFILE` matches `AGENTSCOPE_PROVIDER`, so a mismatched overlay fails fast at service startup.

For confidential `OIDC` clients, the `identity-service` deployment also supports an optional Kubernetes secret named `identity-service-runtime-secrets`.

At minimum, provide:

- `OIDC_CLIENT_SECRET`

For broker-mediated token delegation (SPEC-008), two optional secrets carry the service-identity credential. The non-secret halves (`GATEWAY_TOKEN_AUDIENCE`, `GATEWAY_SERVICE_CLIENT_ID`, `IDENTITY_TOKEN_AUDIENCE`, `IDENTITY_DELEGATED_TOKEN_TTL_SECONDS`) are committed in the `runtime-config.env` fragments above; only the secrets live here:

- `api-gateway-runtime-secrets` (optional, referenced by the `api-gateway` deployment), providing `GATEWAY_SERVICE_CLIENT_SECRET` — see `base/tool-gateway/runtime-secrets.example.env`
- `identity-service-runtime-secrets` (optional, referenced by the `identity-service` deployment), additionally providing `IDENTITY_SERVICE_CLIENTS` (the service-client registry, format `client_id:secret:aud1|aud2`) — see `base/identity-broker/runtime-secrets.example.env`

The gateway's `GATEWAY_SERVICE_CLIENT_SECRET` must match the secret registered for client `tool-gateway` in the broker's `IDENTITY_SERVICE_CLIENTS`. The credential confers no user authority; it only authorizes the token-exchange operation. In this dev overlay the static secret remains the configured path; projected workload-identity tokens (SPEC-009) are the production upgrade — see below.

## Tool Output Redaction (SPEC-009)

Tool-output redaction is on by default in the gateway and needs no overlay change: every tool result passes through a single choke point that replaces credential-shaped spans (JWTs, `Bearer`/`Basic` values, PEM private keys, sensitive key-list fields) with `[REDACTED]` before the response and the audit log. When the redacted fraction of a result exceeds the threshold, the output is withheld with a `REDACTION_OVERFLOW` error (fail-closed).

The only knob is a dev-debugging opt-out, added to the gateway fragment of `runtime-config.env` when needed:

```env
GATEWAY_REDACTION_ENABLED=false
```

Do not carry this into non-dev overlays; the redaction metrics (`gateway_tool_redacted_spans_total`) are the diagnostic surface instead.

## Workload-Identity Service Tokens (SPEC-009)

The exchange endpoint accepts Kubernetes projected service-account tokens as the service credential (`Authorization: Bearer`) instead of the static client secret. This dev overlay keeps the static secret as the fallback (dev clusters have no registered workload registry); a non-dev deployment wires the projected path with:

- gateway: `GATEWAY_WORKLOAD_TOKEN_PATH=/var/run/secrets/tokens/identity-broker` plus a projected volume, e.g.

  ```yaml
  volumes:
    - name: workload-token
      projected:
        sources:
          - serviceAccountToken:
              audience: identity-broker
              expirationSeconds: 3600
              path: identity-broker
  volumeMounts:
    - name: workload-token
      mountPath: /var/run/secrets/tokens
      readOnly: true
  ```

- broker: `IDENTITY_WORKLOAD_ISSUER_URL` (the cluster OIDC issuer), `IDENTITY_WORKLOAD_AUDIENCE` (default `identity-broker`), and `IDENTITY_WORKLOAD_CLIENTS` mapping the service-account subject to a registered client (`system:serviceaccount:<ns>:<sa>=<client_id>:<aud1>|<aud2>`)

When `GATEWAY_WORKLOAD_TOKEN_PATH` is set but the token file is missing, the gateway falls back to the static secret and warns once per process. Unsetting the path is the rollback switch; the dev path (no workload issuer configured) is unchanged.

## Build Images

```bash
make build
```

This builds all four product images with a coordinated `IMAGE_TAG` (delegating to each product's Makefile) and saves the resulting image names in:

- `shared/platform-ops/gitops/dev-k8s/.images.env`

By default the generated tag uses the overlay name for clarity:

- clean build: `dev-k8s-<gitsha>`
- dirty local build: `dev-k8s-<gitsha>-dirty-<timestamp>`

If you want extra traceability in local experiments, you can optionally add a profile suffix:

```bash
make build IMAGE_TAG_PROFILE=deepseek
```

That avoids the stale same-tag rollout problem caused by reusing a single static placeholder tag across multiple development rebuilds.

If your development cluster does not automatically see Docker images from the host runtime, you can load the images into `kind` as part of the same step:

```bash
make build AUTO_LOAD_KIND=true KIND_CLUSTER_NAME=<your-kind-cluster>
```

## Apply

```bash
make deploy
```

This apply path uses the latest `IMAGE_TAG` from `.images.env`, applies the active root GitOps overlay, updates each deployment to the explicit image tag, waits for rollout completion, then reconciles the shared Keycloak browser client for the committed `OIDC` settings.

If you need to override the namespace or image tag manually:

```bash
NAMESPACE=dev-luban-aiops IMAGE_TAG=<explicit-tag> \
  shared/platform-ops/gitops/dev-k8s/deploy.sh
```

If you want to skip the Keycloak step temporarily:

```bash
RECONCILE_OIDC_PORTAL_CLIENT=false \
  shared/platform-ops/gitops/dev-k8s/deploy.sh
```

To reconcile only the browser client without redeploying the workloads:

```bash
shared/platform-ops/gitops/dev-k8s/reconcile-portal-oidc-client.sh
```

## Verify

```bash
kubectl -n dev-luban-aiops get pods,svc
kubectl -n dev-luban-aiops logs deployment/redis
```

To reach the portal in this development cluster through a single browser entrypoint:

```bash
kubectl -n dev-luban-aiops port-forward service/web-ui 18080:80
```

Then open `http://localhost:18080`. The committed `OIDC` redirect URIs in this overlay assume that same local browser entrypoint, and `nginx` forwards `/api/` calls to `api-gateway`.

Once the pods are running, verify that `agent-service` starts successfully and that the portal can:

- start `SSO` login
- complete the callback back into the portal shell
- create a session through `api-gateway`
- send one prompt and receive one streamed response through the proxied gateway path

You can also verify that the gateway proxies the agent-service runtime metadata directly:

```bash
kubectl -n dev-luban-aiops port-forward service/api-gateway 18080:8000
curl http://127.0.0.1:18080/api/v1/runtime
```

The gateway's `/api/v1/runtime` mirrors the agent-service `/api/v2/runtime` metadata and should include:

- `runtime_mode` (`agentscope` when configured)
- `runtime_state` (`ready` when healthy)
- `provider` and `model_name`
