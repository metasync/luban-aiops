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
- If the OIDC callback fails with a redirect URI mismatch: verify `OIDC_REDIRECT_URI` (plus
  `OIDC_EXTRA_REDIRECT_URIS`) cover the browser-accessible URL — the gateway hostnames
  `https://aiops.luban.metasync.cc/callback` / `https://aiops.luban.k8s.orb.local/callback`
  and the port-forward path `http://localhost:18080/callback`. Reconcile the
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

- If the user has an unexpected role: check their OIDC group membership in Keycloak (realm
  `luban-aiops`). The role mapping is: `ops-admins` → `platform-admin`,
  `ops-approvers` → `approver`, `ops-operators` → `operator`,
  `ops-observers` → `read-only-observer`, `ops-auditors` → `auditor`,
  `ops-developers` → `developer`.
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

---

## Symptom: Audit view is empty or recent events are missing

**Most likely cause:** An emitter's `*_AUDIT_SERVICE_URL` is unset, the audit-service is
unhealthy, or the ingest credential is mismatched (events then fail with 401 and are only
counted, not stored).

Audit delivery is fire-and-forget: a broken audit path never fails a user-facing request,
so missing events show up silently.

**Diagnostic:**

```bash
# Emitter delivery counters — result="error" means delivery is failing
kubectl -n dev-luban-aiops exec deployment/tool-gateway -- \
  curl -s localhost:8000/metrics | grep audit_emit
kubectl -n dev-luban-aiops exec deployment/platform-gateway -- \
  curl -s localhost:8000/metrics | grep audit_emit
kubectl -n dev-luban-aiops exec deployment/identity-service -- \
  curl -s localhost:8000/metrics | grep audit_emit

# Audit-service readiness (also reports store backend and size)
kubectl -n dev-luban-aiops exec deployment/audit-service -- \
  curl -s localhost:8000/health/ready | jq

# Emitter configuration
kubectl -n dev-luban-aiops exec deployment/tool-gateway -- env | grep AUDIT
```

**Resolution:**

- If `*_AUDIT_SERVICE_URL` is empty: the emitter is in log-only mode by design. Set the URL
  (dev-k8s default `http://audit-service:8000`) in the emitter's `runtime-config.env` and
  redeploy.
- If readiness shows the store is not ready: check the `postgres` StatefulSet
  (`kubectl -n dev-luban-aiops get pods -l app=postgres`) and `AUDIT_DB_URL`.
- If counters show `result="error"` with 401s in the audit-service logs: see the next
  symptom.
- Remember retention: events older than `AUDIT_RETENTION_DAYS` (default 30) are evicted by
  design, and the store is capped at `AUDIT_MAX_EVENTS`.

---

## Symptom: Audit ingest rejected with 401

**Most likely cause:** An emitter's `*_AUDIT_CLIENT_SECRET` does not match the secret
registered for its client id in `AUDIT_INGEST_CLIENTS`.

**Diagnostic:**

```bash
# Audit-service logs name the rejected client id
kubectl -n dev-luban-aiops logs deployment/audit-service --tail=30 | grep -i ingest

# Verify the registry secret exists
kubectl -n dev-luban-aiops get secret audit-service-runtime-secrets
```

**Resolution:**

```bash
# Regenerate one shared ingest secret and sync all four K8s secrets
shared/platform-ops/gitops/sync-audit-secrets.sh

# Restart the emitters and the audit service
kubectl -n dev-luban-aiops rollout restart \
  deployment/audit-service deployment/tool-gateway \
  deployment/platform-gateway deployment/identity-service
```

---

## Symptom: Audit query returns 403 in the portal or via platform-gateway

**Most likely cause:** The caller's roles do not hold `audit:read`. The action is granted
only to `auditor` and `platform-admin` (rule `allow-auditors-audit-read`); all other roles
are denied by default. The portal also hides the audit navigation entry for unauthorized
identities.

**Diagnostic:**

```bash
# The structured 403 body names the denied action
kubectl -n dev-luban-aiops logs deployment/platform-gateway --tail=30 | grep "audit:read"

# Confirm the deployed policy bundle contains the audit rule
kubectl -n dev-luban-aiops exec deployment/platform-gateway -- \
  cat /etc/luban/policy/policy.yaml | grep -A6 allow-auditors-audit-read
```

**Resolution:**

- Check the user's OIDC group membership: `audit:read` is held by `platform-admin`
  (from `ops-admins`) and `auditor` (from `ops-auditors`). The dev realm ships test users
  for both (`luban-admin`, `luban-auditor`).
- If the bundle is missing the rule, it drifted from the canonical source: run
  `make sync-policy` and redeploy.

---

## Symptom: Skills searches return nothing or the agent reports no guidance

**Most likely cause:** One of — a skill source never synced (rejections or a sync
error), the skills connector is not registered in tool-gateway, or the query
secret halves do not match.

**Diagnostic:**

```bash
# Per-source sync state (auth-exempt): check accepted counts, rejections, last_error
kubectl -n dev-luban-aiops exec deployment/skills-hub -- \
  curl -fsS http://localhost:8000/api/v1/skills/status

# Catalog as the agent sees it (requires the query credential)
QUERY_CLIENTS=$(kubectl -n dev-luban-aiops get secret skills-hub-runtime-secrets \
  -o jsonpath='{.data.SKILLS_QUERY_CLIENTS}' | base64 -d)
kubectl -n dev-luban-aiops exec deployment/skills-hub -- \
  curl -fsS -u "tool-gateway:${QUERY_CLIENTS#tool-gateway=}" \
  "http://localhost:8000/api/v1/skills?limit=100"

# Connector registration is gated on this URL
kubectl -n dev-luban-aiops exec deployment/tool-gateway -- \
  sh -c 'echo "${GATEWAY_SKILLS_SERVICE_URL:-<unset>}"'
```

**Resolution:**

- Source shows `rejections`: fix the reported documents
  (`python -m skills_hub.validate <dir>`), then redeploy or restart skills-hub.
- Source shows `last_error`: fix the git URL/credential or mount path; the
  previous slice keeps serving until the next successful sync.
- `GATEWAY_SKILLS_SERVICE_URL` unset or the secrets mismatched: re-run
  `shared/platform-ops/gitops/sync-skills-secrets.sh` and
  `kubectl rollout restart deployment/tool-gateway deployment/skills-hub`.
- Content-level operations (add/revise/remove skills and sources) are covered
  by the [Skills and Guidance Guide](skills-guide.md).

## Symptom: Alertmanager alerts never create incidents (401/503 from webhook)

**Most likely cause:** One of — the bearer token Alertmanager sends does not
match `INCIDENT_WEBHOOK_TOKEN` (401 `UNAUTHORIZED`), or the token was never
provisioned and the webhook fails closed (503 `WEBHOOK_NOT_CONFIGURED`).

**Diagnostic:**

```bash
# Is the token configured at all?
kubectl -n dev-luban-aiops get secret incident-service-runtime-secrets \
  -o jsonpath='{.data.INCIDENT_WEBHOOK_TOKEN}' | base64 -d | wc -c

# Probe the webhook from inside the cluster with the configured token
TOKEN=$(kubectl -n dev-luban-aiops get secret incident-service-runtime-secrets \
  -o jsonpath='{.data.INCIDENT_WEBHOOK_TOKEN}' | base64 -d)
kubectl -n dev-luban-aiops exec deployment/incident-service -- \
  curl -s -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: Bearer ${TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"status":"resolved","groupKey":"probe://diag","commonLabels":{}}' \
  http://localhost:8000/api/v1/webhooks/alertmanager
# expected: 200 (idempotent "ignored" resolution for an unknown fingerprint)
```

**Resolution:**

- 503: run `shared/platform-ops/gitops/sync-incident-secrets.sh` and roll
  `deployment/incident-service` so the new secret is mounted.
- 401 with a configured token: rotate both halves together — re-run the sync
  script with an exported `INCIDENT_WEBHOOK_TOKEN` and update the
  Alertmanager receiver's `bearer_token`. Alertmanager retries on 401, so no
  alerts are lost once the token matches.
- Full intake semantics (dedupe, resolve) are covered by the
  [Incident Triage and Collaboration Guide](incident-guide.md).

## Symptom: Run triage fails or an incident is stuck in "triaging"/"triage_failed"

**Most likely cause:** One of — the incident-service → platform-gateway relay
or the token-delegation chain is down (surfaced as a triage error banner),
agent-platform rejected both candidate triage sessions, or the agent turn
timed out. A stuck `triaging` status means the triage turn never completed.

**Diagnostic:**

```bash
# Triage runs are logged structured with the incident id and session used
kubectl -n dev-luban-aiops logs deployment/incident-service --tail=100 \
  | grep -E 'triage|incident-'

# The relay target and credential must be configured on platform-gateway
kubectl -n dev-luban-aiops exec deployment/platform-gateway -- \
  sh -c 'echo "${PLATFORM_GATEWAY_INCIDENT_SERVICE_URL:-<unset>}"'

# Delegation chain health (platform-gateway exchanges the operator token at
# identity-service and relays it to incident-service as X-Delegated-Token)
kubectl -n dev-luban-aiops logs deployment/platform-gateway --tail=100 \
  | grep -iE 'delegat|exchange'
```

**Resolution:**

- Relay 401s: re-run `shared/platform-ops/gitops/sync-incident-secrets.sh`
  (it keeps `INCIDENT_QUERY_CLIENTS` and the gateway client secret in sync)
  and roll incident-service and platform-gateway.
- Session 404 errors in the logs: triage tries `incident-<id>` then
  `incident-<id>--<operator>`; both failing means agent-platform is
  unreachable or its session store is degraded — check agent-platform logs.
- `triage_failed` is terminal-by-design: fix the underlying cause and click
  **Re-run triage**; the latest successful outcome replaces the failure.

## Symptom: Agent cannot see incidents ("incidents.list" tool missing)

**Most likely cause:** The incidents connector is not registered in
tool-gateway — `GATEWAY_INCIDENTS_SERVICE_URL` is unset, or the query secret
halves do not match between tool-gateway and incident-service.

**Diagnostic:**

```bash
# Connector registration is gated on this URL
kubectl -n dev-luban-aiops exec deployment/tool-gateway -- \
  sh -c 'echo "${GATEWAY_INCIDENTS_SERVICE_URL:-<unset>}"'

# Query visibility as the agent sees it (HTTP Basic service credential)
QUERY_CLIENTS=$(kubectl -n dev-luban-aiops get secret incident-service-runtime-secrets \
  -o jsonpath='{.data.INCIDENT_QUERY_CLIENTS}' | base64 -d)
kubectl -n dev-luban-aiops exec deployment/incident-service -- \
  curl -fsS -u "tool-gateway:${QUERY_CLIENTS##*tool-gateway=}" \
  "http://localhost:8000/api/v1/incidents?limit=5"
```

**Resolution:**

- URL unset or secrets mismatched: re-run
  `shared/platform-ops/gitops/sync-incident-secrets.sh` and
  `kubectl rollout restart deployment/tool-gateway deployment/incident-service`.
- The connector is read-only by design; mutating flows (report, triage) go
  through the portal and platform-gateway — see the
  [Incident Triage and Collaboration Guide](incident-guide.md).

## Symptom: No traces/metrics/logs appear in OpenObserve

**Most likely cause:** One of — the OTLP ingest auth header is missing from a
service's secret (OpenObserve answers 401 and the exporter drops batches),
`OTEL_ENABLED` is false, or `OTEL_EXPORTER_OTLP_ENDPOINT` points at the wrong
org/path. Telemetry always fails open, so services themselves look healthy.

**Diagnostic:**

```bash
# Gate + endpoint come from the shared ConfigMap
kubectl -n dev-luban-aiops get configmap platform-runtime-config \
  -o jsonpath='{.data.OTEL_ENABLED}{"\n"}{.data.OTEL_EXPORTER_OTLP_ENDPOINT}{"\n"}'

# The auth header must be present in each service's runtime-secrets Secret
kubectl -n dev-luban-aiops get secret skills-hub-runtime-secrets \
  -o jsonpath='{.data.OTEL_EXPORTER_OTLP_HEADERS}' | base64 -d | cut -c1-40

# Exporter errors surface in pod logs ("otel telemetry setup failed",
# "401" from the batch exporter)
kubectl -n dev-luban-aiops logs deployment/skills-hub --tail=50 | grep -i otel
```

**Resolution:**

- Header missing or 401s in the logs: export the OpenObserve root credentials
  (luban-bootstrapper `openobserve/secrets/openobserve.env`) and re-run
  `shared/platform-ops/gitops/sync-otel-secrets.sh` (or `make deploy` with the
  variables exported); it upserts the header into all six secrets and restarts
  the workloads.
- `OTEL_ENABLED=false`: set it to `true` in
  `dev-k8s/base/shared/runtime.env` and redeploy.
- Endpoint wrong: it must stop at the org prefix
  (`.../api/default`); the exporters append `/v1/{traces,metrics,logs}`.
- Conventions and the log-bridge semantics:
  `shared/shared-contracts/observability-conventions.md`.

## Symptom: Mutating tool absent from discovery ("k8s.delete_pod" not listed)

**Most likely cause:** Mutating tools are deny-by-default at the execution
boundary (SPEC-021). `GATEWAY_MUTATING_TOOLS_ENABLED` is `false` (the shipped
default), so write/admin tools are never registered — they are absent from
`GET /api/v2/tools` and invoke answers `TOOL_NOT_FOUND`.

**Diagnostic:**

```bash
kubectl -n dev-luban-aiops exec deployment/tool-gateway -- \
  sh -c 'echo "${GATEWAY_MUTATING_TOOLS_ENABLED:-<unset>}"'
kubectl -n dev-luban-aiops logs deployment/tool-gateway --tail=200 \
  | grep "mutating tool not registered"
```

**Resolution:**

- This is the intended default posture. To opt in, follow the full activation
  checklist in the
  [Tool and Connector Guide](tool-configuration.md#mutating-tool-activation-checklist-k8sdelete_pod)
  — gateway flag, opt-in pod-delete RBAC, HITL bridging, and `tools:mutate`
  grants all need to hold together.
- If the flag is already `true` but the tool is missing, the Kubernetes
  connector itself is off (`GATEWAY_K8S_ENABLED=false`).

## Symptom: Mutating tool invoke returns 403 "denied"

**Most likely cause:** The caller holds `tools:invoke` but not `tools:mutate`.
Read tools keep requiring only `tools:invoke`; write/admin tools additionally
require `tools:mutate`, granted by default only to `platform-admin` and
`operator` (SPEC-021).

**Diagnostic:**

```bash
# The deny is policy-decision logged and audited with action=tools:mutate
kubectl -n dev-luban-aiops logs deployment/tool-gateway --tail=200 \
  | grep "mutating tool invocation denied"

# Live matrix: check the caller's role against tools:mutate
curl -s -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:18000/api/v1/policy/matrix | jq '.matrix["operator"]["tools:mutate"]'
```

**Resolution:**

- Expected behavior for `developer`, `approver`, `auditor`, and
  `read-only-observer`. Extending the grant is a deliberate policy-bundle
  edit — see the
  [Approval and HITL Governance Guide](approval-and-hitl.md#defining-approval-requirements-today).

## Symptom: Agent proposes an action but no confirmation card appears

**Most likely cause:** HITL confirmation bridging is disabled
(`AGENT_HITL_CONFIRM_TIMEOUT=0`). With bridging off, agent-platform excludes
mutating tools from the toolkit entirely, so the agent should not offer them;
if the model still describes an action it cannot perform, the turn carries a
system notice saying mutating actions are unavailable — no card ever appears
and nothing silently runs.

**Diagnostic:**

```bash
kubectl -n dev-luban-aiops exec deployment/agent-service -- \
  sh -c 'echo "${AGENT_HITL_CONFIRM_TIMEOUT:-<unset>}"'
kubectl -n dev-luban-aiops logs deployment/agent-service --tail=200 \
  | grep "HITL bridging disabled"
```

**Resolution:**

- Set `AGENT_HITL_CONFIRM_TIMEOUT` to a positive value (dev-k8s ships `600`)
  and restart agent-service; mutating tools reappear in the toolkit and park
  for confirmation as designed.

## Symptom: Approved a mutating confirmation but it fails with K8S_PERMISSION_DENIED

**Most likely cause:** The platform gates passed (policy + confirmation), but
the tool-gateway's Kubernetes service account lacks `delete` on pods. The
opt-in pod-delete RBAC manifest was not applied.

**Diagnostic:**

```bash
kubectl -n dev-luban-aiops auth can-i delete pods \
  --as=system:serviceaccount:dev-luban-aiops:tool-gateway
# expected: yes (only after the opt-in Role/RoleBinding is applied)
```

**Resolution:**

- Apply the pod-delete Role/RoleBinding
  (`shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-pod-delete.yaml`)
  and retry. The structured error, the `confirmation_decided` audit event, and
  the failed `tool_invoked` event all stay in the trail — nothing half-deleted:
  pod deletion is a single API call that either succeeded or did not.
