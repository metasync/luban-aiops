# Troubleshooting Guide

A symptom-based diagnostic guide for the most common deployment and runtime issues.
Each symptom includes the likely cause, diagnostic commands, and resolution steps.

## General Diagnostic Commands

```bash
# List all pods and their status
kubectl -n dev-luban-aiops get pods

# View logs for a specific service
kubectl -n dev-luban-aiops logs deployment/<service-name> --tail=50

# Check readiness of a specific service
kubectl -n dev-luban-aiops exec deployment/<service-name> -- \
  curl -s localhost:8000/health/ready | jq

# View environment variables of a running pod
kubectl -n dev-luban-aiops exec deployment/<service-name> -- env | sort

# Port-forward for direct service access
kubectl -n dev-luban-aiops port-forward service/<service-name> <local-port>:8000

# View Prometheus metrics
kubectl -n dev-luban-aiops exec deployment/<service-name> -- \
  curl -s localhost:8000/metrics
```

---

## Symptom: "Agent says access not granted" or "no tools available"

**Most likely cause:** Token delegation secrets are missing or mismatched.

The agent needs a working token delegation chain to invoke tools. platform-gateway exchanges
the user's portal JWT for a short-lived delegated token via identity-service. Without matching
secrets, the exchange fails and tool calls are silently skipped.

**Diagnostic:**

```bash
# Check delegation metrics
kubectl -n dev-luban-aiops exec deployment/platform-gateway -- \
  curl -s localhost:8000/metrics | grep delegation

# Check identity-service logs for exchange errors
kubectl -n dev-luban-aiops logs deployment/identity-service --tail=30 | grep -i exchange

# Verify both secrets exist
kubectl -n dev-luban-aiops get secret platform-gateway-runtime-secrets identity-service-runtime-secrets
```

**Resolution:**

```bash
# Re-provision delegation secrets (generates a new shared secret if not exported)
shared/platform-ops/gitops/sync-delegation-secrets.sh

# Restart the affected deployments
kubectl -n dev-luban-aiops rollout restart deployment/platform-gateway deployment/identity-service
kubectl -n dev-luban-aiops rollout status deployment/platform-gateway --timeout=120s
kubectl -n dev-luban-aiops rollout status deployment/identity-service --timeout=120s
```

After restart, verify `delegation_exchange_total{result="success"}` increments when you send
a chat message.

---

## Symptom: "Agent has no tools" or tool list is empty

**Most likely cause:** `TOOL_GATEWAY_URL` is unset, the tool-gateway pod is unhealthy, or the
Kubernetes connector is not configured.

**Diagnostic:**

```bash
# Check agent-service environment
kubectl -n dev-luban-aiops exec deployment/agent-service -- env | grep TOOL_GATEWAY

# Check tool-gateway readiness
kubectl -n dev-luban-aiops exec deployment/tool-gateway -- \
  curl -s localhost:8000/health/ready | jq

# List registered tools directly
kubectl -n dev-luban-aiops port-forward service/tool-gateway 18100:8000
curl -s http://127.0.0.1:18100/api/v1/tools | jq '.[].name'
```

**Resolution:**

- If `TOOL_GATEWAY_URL` is empty: set `TOOL_GATEWAY_URL=http://tool-gateway:8000` in
  `agent-platform/runtime-config.env` and redeploy.
- If tool-gateway readiness shows `degraded` with a `policy_error`: the policy ConfigMap is
  missing or malformed. Re-apply the overlay: `make deploy`.
- If the K8s connector returns `K8S_NOT_CONFIGURED`: verify `GATEWAY_K8S_ENABLED=true` and
  the RBAC Role/RoleBinding exist. See [Tool Configuration](tool-configuration.md).

---

## Symptom: Portal login fails

**Most likely cause:** OIDC misconfiguration or Keycloak unreachable.

**Diagnostic:**

```bash
# Check identity-service logs for OIDC errors
kubectl -n dev-luban-aiops logs deployment/identity-service --tail=30 | grep -i oidc

# Verify Keycloak is reachable from the cluster
kubectl -n dev-luban-aiops exec deployment/identity-service -- \
  curl -s -o /dev/null -w '%{http_code}' \
  $(kubectl -n dev-luban-aiops exec deployment/identity-service -- printenv KEYCLOAK_BASE_URL)/realms/$(kubectl -n dev-luban-aiops exec deployment/identity-service -- printenv KEYCLOAK_REALM)/.well-known/openid-configuration

# Check OIDC configuration
kubectl -n dev-luban-aiops exec deployment/identity-service -- env | grep -E 'KEYCLOAK|OIDC'
```

**Resolution:**

- If Keycloak is unreachable: check network policies, DNS resolution, and the
  `KEYCLOAK_BASE_URL` value.
- If the OIDC callback fails with a redirect URI mismatch: verify `OIDC_REDIRECT_URI` matches
  the browser-accessible URL (default `http://localhost:18080/callback`). Reconcile the
  Keycloak client: `shared/platform-ops/gitops/dev-k8s/reconcile-portal-oidc-client.sh`.
- If login completes but the portal shows an error: check the platform-gateway logs for JWT
  verification failures (`kubectl logs deployment/platform-gateway | grep -i token`).

---

## Symptom: Stream never completes or agent returns empty response

**Most likely cause:** agent-service is not configured with an LLM provider or the API key is
invalid.

**Diagnostic:**

```bash
# Check agent-service runtime metadata
kubectl -n dev-luban-aiops port-forward service/agent-service 18000:8000
curl -s http://127.0.0.1:18000/api/v2/runtime | jq
# Look for: runtime_mode, runtime_state, provider, model_name

# Check health endpoint
curl -s http://127.0.0.1:18000/api/v2/health | jq
# Look for: configured: true

# Check agent-service logs for provider errors
kubectl -n dev-luban-aiops logs deployment/agent-service --tail=30 | grep -iE 'provider|error|api_key'
```

**Resolution:**

- If `runtime_state` is `placeholder` or `configured` is `false`: the API key is missing or
  invalid. Re-provision: `shared/platform-ops/gitops/sync-runtime-secret.sh <profile>`, then
  restart: `kubectl -n dev-luban-aiops rollout restart deployment/agent-service`.
- If the provider returns 401/403: the API key is expired or invalid. Update the secret and
  re-sync.
- If the stream starts but stalls: check the chat timeout
  (`CHAT_RESPONSE_TIMEOUT_SECONDS`, default 120s) and the provider's rate limits.

---

## Symptom: Tool returns "denied by policy"

**Most likely cause:** The user's role lacks the required action in the policy bundle.

**Diagnostic:**

```bash
# Check tool-gateway logs for policy decisions
kubectl -n dev-luban-aiops logs deployment/tool-gateway --tail=30 | grep "policy decision"
# Look for: action, decision, subject, roles

# Verify the mounted policy bundle
kubectl -n dev-luban-aiops exec deployment/tool-gateway -- \
  cat /etc/luban/policy/policy.yaml

# Check the user's roles from the platform-gateway logs
kubectl -n dev-luban-aiops logs deployment/platform-gateway --tail=30 | grep "identity verified"
```

**Resolution:**

- If the user has an unexpected role: check their OIDC group membership in Keycloak. The
  role mapping is: `ops-admins` → `platform-admin`, `ops-operators` → `operator`,
  `ops-observers` → `read-only-observer`.
- If the policy bundle is outdated: edit the canonical source
  (`shared/shared-contracts/policies/policy-default.yaml`), validate
  (`make validate-policy`), sync (`make sync-policy`), and redeploy.
- Users with no matching OIDC group default to `read-only-observer`, which has tool access
  for read-only tools.

---

## Symptom: Tool returns "ELASTIC_NOT_CONFIGURED"

**Most likely cause:** The Elastic connector is not enabled or not configured.

**Diagnostic:**

```bash
# Check tool-gateway configuration
kubectl -n dev-luban-aiops exec deployment/tool-gateway -- env | grep ELASTIC
```

**Resolution:**

1. Set `GATEWAY_ELASTIC_ENABLED=true` in `tool-gateway/runtime-config.env`.
2. Set `GATEWAY_ELASTIC_URL` to your Elasticsearch cluster URL.
3. Provide authentication: `GATEWAY_ELASTIC_API_KEY` (preferred) or
   `GATEWAY_ELASTIC_USERNAME` + `GATEWAY_ELASTIC_PASSWORD`.
4. Redeploy: `make build && make deploy`.

See the [Elastic Connector Checklist](tool-configuration.md#elastic-connector) for the full
activation procedure.

---

## Symptom: Pods fail with ErrImagePull after deployment

**Most likely cause:** Image tags were reset to the `dev-local` placeholder by a raw
`kubectl apply -k` command.

**Diagnostic:**

```bash
kubectl -n dev-luban-aiops get pods
# Look for: ErrImagePull or ImagePullBackOff

kubectl -n dev-luban-aiops get deployment -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.template.spec.containers[0].image}{"\n"}{end}'
# If images show :dev-local, tags were not patched
```

**Resolution:**

Always deploy via `make deploy` (which handles image tag patching). To fix manually:

```bash
# Re-run the deploy overlay script which sets correct image tags
shared/platform-ops/gitops/deploy-overlay.sh
```

---

## Symptom: Policy bundle fails to load (readiness shows "degraded")

**Most likely cause:** The policy ConfigMap is missing or the YAML is malformed.

**Diagnostic:**

```bash
# Check readiness
kubectl -n dev-luban-aiops exec deployment/tool-gateway -- \
  curl -s localhost:8000/health/ready | jq
# Look for: policy_error field

# Check if the ConfigMap exists
kubectl -n dev-luban-aiops get configmap platform-policy -o yaml | head -20

# Check the mounted policy file
kubectl -n dev-luban-aiops exec deployment/tool-gateway -- \
  cat /etc/luban/policy/policy.yaml | head -20
```

**Resolution:**

1. Validate the canonical policy file: `make validate-policy`
2. Re-sync to all locations: `make sync-policy`
3. Re-apply the overlay: `make deploy`

---

## Symptom: "Stream never completes" with token expiry errors

**Most likely cause:** The delegated token TTL has expired during a long-running operation.

**Diagnostic:**

```bash
# Check delegated token TTL
kubectl -n dev-luban-aiops exec deployment/identity-service -- \
  env | grep DELEGATED_TOKEN_TTL

# Check platform-gateway delegation cache behavior
kubectl -n dev-luban-aiops logs deployment/platform-gateway --tail=30 | grep delegation
```

**Resolution:**

Increase `IDENTITY_DELEGATED_TOKEN_TTL_SECONDS` (default 300s) in the identity-broker
runtime config, or investigate why tool invocations are taking longer than the TTL window.
