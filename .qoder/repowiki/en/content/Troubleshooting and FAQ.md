# Troubleshooting and FAQ

<cite>
**Referenced Files in This Document**
- [README.md](file://README.md)
- [troubleshooting.md](file://docs/guides/troubleshooting.md)
- [configuration-reference.md](file://docs/guides/configuration-reference.md)
- [servicenow-integration.md](file://docs/guides/servicenow-integration.md)
- [servicenow_native.py](file://products/tool-gateway/src/tool_gateway/ingestion/servicenow_native.py)
- [servicenow_binding.py](file://products/tool-gateway/src/tool_gateway/ingestion/servicenow_binding.py)
- [test_servicenow_native.py](file://products/tool-gateway/tests/test_servicenow_native.py)
- [mock_servicenow_table_api.py](file://shared/platform-ops/gitops/runtime-profiles/servicenow-dev/mock_servicenow_table_api.py)
- [sync-servicenow-credentials.sh](file://shared/platform-ops/gitops/sync-servicenow-credentials.sh)
- [servicenow-check.sh](file://shared/platform-ops/e2e/servicenow-check.sh)
- [SPEC-005-observability-baseline/spec.md](file://docs/specs/SPEC-005-observability-baseline/spec.md)
- [observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [deploy-overlay.sh](file://shared/platform-ops/gitops/deploy-overlay.sh)
- [sync-runtime-secret.sh](file://shared/platform-ops/gitops/sync-runtime-secret.sh)
- [sync-audit-secrets.sh](file://shared/platform-ops/gitops/sync-audit-secrets.sh)
- [sync-incident-secrets.sh](file://shared/platform-ops/gitops/sync-incident-secrets.sh)
- [gateway_service.py](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py)
- [token_verifier.py (platform-gateway)](file://products/platform-gateway/src/platform_gateway/services/token_verifier.py)
- [token_verifier.py (tool-gateway)](file://products/tool-gateway/src/tool_gateway/services/token_verifier.py)
- [test_gateway_auth.py](file://products/platform-gateway/tests/test_gateway_auth.py)
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [session_store.py](file://products/agent-platform/src/agent_service/services/session_store.py)
- [executor.py](file://products/execution-runtime/src/execution_runtime/services/executor.py)
- [metrics.py (execution-runtime)](file://products/execution-runtime/src/execution_runtime/core/metrics.py)
- [observability.py (execution-runtime)](file://products/execution-runtime/src/execution_runtime/core/observability.py)
- [observability.py (audit-service)](file://products/audit-service/src/audit_service/core/observability.py)
- [observability.py (skills-hub)](file://products/skills-hub/src/skills_hub/core/observability.py)
- [observability.py (incident-service)](file://products/incident-service/src/incident_service/core/observability.py)
- [health-response.schema.json](file://shared/shared-contracts/schemas/health-response.schema.json)
- [chat-response.schema.json](file://shared/shared-contracts/schemas/chat-response.schema.json)
- [DocumentsView.tsx](file://products/operator-portal/web-ui/app/src/views/workspace/DocumentsView.tsx)
</cite>

## Update Summary
**Changes Made**
- Added comprehensive ServiceNow integration troubleshooting section with 55 new lines covering connectivity problems, authentication failures, and mock service validation
- Updated tool execution errors section to include ServiceNow-specific diagnostic steps
- Enhanced frequently asked questions with ServiceNow-specific scenarios
- Added ServiceNow integration architecture diagram
- Expanded environment-specific troubleshooting for ServiceNow deployments

## Table of Contents
1. Introduction
2. Project Structure
3. Core Components
4. Architecture Overview
5. Detailed Component Analysis
6. Dependency Analysis
7. Performance Considerations
8. Troubleshooting Guide
9. Conclusion
10. Appendices

## Introduction
This document provides a symptom-based troubleshooting guide for the Luban AIOPS platform, covering deployment failures, authentication problems, tool execution errors, performance issues, data consistency problems, and ServiceNow integration issues. It includes diagnostic steps, log analysis techniques, remediation procedures, frequently asked questions, known limitations, upgrade considerations, and guidance for using observability tools such as metrics, traces, and audit logs across services.

## Project Structure
The platform is organized into product-oriented services with clear boundaries:
- Platform edge: platform-gateway (authentication, policy enforcement, chat/session proxying, token delegation)
- Agent runtime: agent-platform (sessions, streaming, HITL bridging, execution signing/handoff)
- Tool integration: tool-gateway (tool registry, connectors, redaction, tool audit)
- Identity: identity-broker (OIDC flows, JWT issuance, delegation)
- Execution isolation: execution-runtime (bounded worker handoff)
- Observability and evidence: audit-service (durable trail), Elastic connector (optional)
- Skills and incidents: skills-hub, incident-service
- Operator portal: operator-portal

```mermaid
graph TB
Client["Operator / Browser"] --> PGW["Platform Gateway"]
PGW --> IDB["Identity Broker"]
PGW --> AGP["Agent Platform"]
AGP --> TGW["Tool Gateway"]
AGP --> ERW["Execution Runtime Worker"]
TGW --> EXT["External Systems"]
TGW --> SNOW["ServiceNow"]
PGW --> AUD["Audit Service"]
AGP --> AUD
TGW --> AUD
IDB --> AUD
ERW --> AUD
```

**Diagram sources**
- [README.md:24-45](file://README.md#L24-L45)
- [configuration-reference.md:33-126](file://docs/guides/configuration-reference.md#L33-L126)

**Section sources**
- [README.md:15-45](file://README.md#L15-L45)

## Core Components
- Authentication and authorization:
  - Token verification at platform-gateway and tool-gateway via JWKS and audience checks.
  - Policy enforcement through mounted bundles; readiness reports degraded state when bundle is missing or invalid.
- Session and streaming:
  - Agent platform manages sessions, transcripts, and evidence stores with graceful degradation on backend failure.
- Tool execution:
  - Tool gateway exposes tools/connectors; mutating tools are deny-by-default and require explicit activation and approvals.
  - ServiceNow integration provides read-only access to ITSM records through native REST/Table-API connector.
- Audit trail:
  - Fire-and-forget ingestion from multiple emitters to audit-service; counters expose delivery health.
- Observability:
  - Always-on /metrics per service; opt-in OTel push pipeline; structured logging bridge to OTLP.

**Section sources**
- [token_verifier.py (platform-gateway):52-80](file://products/platform-gateway/src/platform_gateway/services/token_verifier.py#L52-L80)
- [token_verifier.py (tool-gateway):52-80](file://products/tool-gateway/src/tool_gateway/services/token_verifier.py#L52-L80)
- [configuration-reference.md:282-327](file://docs/guides/configuration-reference.md#L282-L327)
- [session_store.py:949-969](file://products/agent-platform/src/agent_service/services/session_store.py#L949-L969)
- [configuration-reference.md:128-168](file://docs/guides/configuration-reference.md#L128-L168)
- [SPEC-005-observability-baseline/spec.md:12-35](file://docs/specs/SPEC-005-observability-baseline/spec.md#L12-L35)

## Architecture Overview
End-to-end request flow with authentication, policy, and optional execution approval:

```mermaid
sequenceDiagram
participant U as "User"
participant PGW as "Platform Gateway"
participant IDB as "Identity Broker"
participant AGP as "Agent Platform"
participant TGW as "Tool Gateway"
participant ERW as "Execution Runtime"
participant SNOW as "ServiceNow"
participant AUD as "Audit Service"
U->>PGW : HTTP request (Bearer token)
PGW->>IDB : Verify token / delegate token
IDB-->>PGW : Identity context + delegated token
PGW->>PGW : Policy decision (tools : * / actions)
PGW->>AGP : Proxy chat/session
AGP->>TGW : Invoke tool (read-only or write)
alt Write path requires approval
AGP->>AGP : Park confirmation (HITL)
U->>PGW : Approve/deny
PGW->>AGP : Resume under approver token
end
AGP->>ERW : Handoff approved mutation (signed envelope)
ERW-->>AGP : Result (success/timeout/failure)
alt ServiceNow read operation
AGP->>SNOW : Table API GET request
SNOW-->>AGP : Record data
end
AGP-->>U : Streamed response
PGW-->>AUD : Emit audit events (fire-and-forget)
AGP-->>AUD : Emit audit events
TGW-->>AUD : Emit audit events
SNOW-->>AUD : Audit attribution
```

**Diagram sources**
- [gateway_service.py:130-215](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L130-L215)
- [runtime_kernel.py:1542-1557](file://products/agent-platform/src/agent_service/runtime_kernel.py#L1542-L1557)
- [configuration-reference.md:90-126](file://docs/guides/configuration-reference.md#L90-L126)

## Detailed Component Analysis

### Authentication and Authorization
Symptoms:
- Login fails or portal shows unauthorized
- Tool invocation returns 401/403
- "Stream never completes" due to expired delegated tokens

Diagnostics:
- Check identity broker OIDC configuration and reachability
- Validate token issuer/audience and JWKS endpoint
- Inspect delegation exchange metrics and logs
- Confirm policy bundle loaded and roles mapped correctly

Remediation:
- Reconcile Keycloak client redirect URIs if callback mismatches occur
- Re-provision delegation secrets and restart affected deployments
- Increase delegated token TTL only if necessary and investigate long-running operations
- Ensure policy bundle is valid and synced; restart gateways to pick up changes

Observability:
- Use /metrics to check delegation counters and token verification outcomes
- Correlate x-request-id across services; enable OTel push to join logs and traces

**Section sources**
- [troubleshooting.md:102-135](file://docs/guides/troubleshooting.md#L102-L135)
- [troubleshooting.md:292-311](file://docs/guides/troubleshooting.md#L292-L311)
- [configuration-reference.md:62-75](file://docs/guides/configuration-reference.md#L62-L75)
- [test_gateway_auth.py:34-67](file://products/platform-gateway/tests/test_gateway_auth.py#L34-L67)
- [token_verifier.py (platform-gateway):52-80](file://products/platform-gateway/src/platform_gateway/services/token_verifier.py#L52-L80)
- [token_verifier.py (tool-gateway):52-80](file://products/tool-gateway/src/tool_gateway/services/token_verifier.py#L52-L80)

### Tool Execution Errors
Symptoms:
- "No tools available" or empty tool list
- "ELASTIC_NOT_CONFIGURED"
- Mutating tool absent from discovery
- Mutating tool invoke returns 403 denied
- Confirming a parked mutating call returns 403
- Approved mutation fails with K8S_PERMISSION_DENIED

Diagnostics:
- Verify TOOL_GATEWAY_URL and tool-gateway readiness
- Check GATEWAY_K8S_ENABLED and RBAC for Kubernetes tools
- Confirm GATEWAY_ELASTIC_* settings for Elastic connector
- Validate GATEWAY_MUTATING_TOOLS_ENABLED and HITL bridging flags
- Inspect policy decisions and matrix endpoints for role/action grants
- Check browser connector flags and credential sets for web.* tools

Remediation:
- Set required URLs and credentials; redeploy affected services
- Apply opt-in RBAC manifests for mutating tools
- Enable HITL bridging by setting a positive timeout
- Re-run secret sync scripts to align clients and secrets
- For web tools, ensure CDP endpoint reachable and origins allowlisted

**Section sources**
- [troubleshooting.md:71-99](file://docs/guides/troubleshooting.md#L71-L99)
- [troubleshooting.md:211-231](file://docs/guides/troubleshooting.md#L211-L231)
- [troubleshooting.md:588-613](file://docs/guides/troubleshooting.md#L588-L613)
- [troubleshooting.md:614-644](file://docs/guides/troubleshooting.md#L614-L644)
- [troubleshooting.md:645-673](file://docs/guides/troubleshooting.md#L645-L673)
- [troubleshooting.md:698-718](file://docs/guides/troubleshooting.md#L698-L718)
- [configuration-reference.md:17-21](file://docs/guides/configuration-reference.md#L17-L21)
- [configuration-reference.md:452-494](file://docs/guides/configuration-reference.md#L452-L494)

### ServiceNow Integration Issues
**Updated** Added comprehensive ServiceNow troubleshooting covering connectivity, authentication, and mock service validation

#### Connectivity Problems
Symptoms:
- `SERVICENOW_UNREACHABLE` errors
- DNS resolution failures
- TLS certificate validation errors
- NetworkPolicy blocking egress traffic

Diagnostics:
- Probe from inside the pod using curl: `kubectl exec deployment/tool-gateway -c tool-gateway -- curl -sS -o /dev/null -w '%{http_code} %{ssl_verify_result}\n' --max-time 10 https://<instance>.service-now.com/api/now/table/incident`
- Check SSL certificate trust chain: non-zero ssl_verify_result indicates trust-chain problem
- Verify NetworkPolicy allows egress to ServiceNow on port 443
- Test DNS resolution within the cluster

Remediation:
- Mount custom CA bundle for private CA environments: `SSL_CERT_FILE=/etc/ssl/certs/servicenow-ca-bundle.pem`
- Add egress rules for ServiceNow instance host on port 443
- Verify ServiceNow instance is accessible from outside the cluster first
- Check for corporate proxies or TLS inspection that may interfere

#### Authentication Failures
Symptoms:
- `CREDENTIAL_SET_NOT_FOUND` errors
- `CREDENTIAL_ACQUISITION_FAILED` errors
- 401 Unauthorized responses from ServiceNow
- Invalid client credentials

Diagnostics:
- Verify credential set exists and has correct scheme: `oauth2_client_credentials`
- Check OAuth application configuration in ServiceNow Application Registry
- Validate grant type is enabled: `glide.oauth.inbound.client.credential.grant_type.enabled=true`
- Test credentials locally using smoke test script
- Confirm client_id and client_secret match ServiceNow configuration

Remediation:
- Re-run sync script: `shared/platform-ops/gitops/sync-servicenow-credentials.sh dev-luban-aiops`
- Verify OAuth application user is bound to integration user
- Check ACL permissions for the four tables: incident, change_request, sys_user, cmdb_ci
- Ensure client secret is properly stored without shell metacharacters breaking parsing

#### Mock Service Validation
Symptoms:
- Mock service not responding
- Inconsistent behavior between mock and live ServiceNow
- Test failures in CI environment

Diagnostics:
- Check mock service deployment status: `kubectl get pods -l app=servicenow-mock-table-api`
- Verify mock credentials secret exists: `kubectl get secret servicenow-mock-credentials`
- Test mock service directly: `curl http://servicenow-mock-table-api:8000/api/now/table/incident`
- Review mock service logs for authentication failures

Remediation:
- Restart mock service if needed
- Regenerate mock credentials using sync script
- Verify mock service network policies allow communication
- Test against real ServiceNow instance separately from mock validation

#### Field Projection and Data Issues
Symptoms:
- Missing fields in returned data
- Unexpected columns appearing in results
- Credential columns leaking in responses

Diagnostics:
- Check field projection allowlists in binding configuration
- Verify ServiceNow table schema matches expected columns
- Review audit logs for field-level details
- Test field projection with mock service

Remediation:
- Update field allowlists in `servicenow_binding.py` if tenant schema changed
- Verify no secret-bearing columns in projections
- Confirm credential stripping works for sys_user table
- Test against real ServiceNow instance to validate field mappings

**Section sources**
- [servicenow-integration.md:633-649](file://docs/guides/servicenow-integration.md#L633-L649)
- [servicenow_native.py:96-103](file://products/tool-gateway/src/tool_gateway/ingestion/servicenow_native.py#L96-L103)
- [servicenow_native.py:344-368](file://products/tool-gateway/src/tool_gateway/ingestion/servicenow_native.py#L344-L368)
- [servicenow_binding.py:56-77](file://products/tool-gateway/src/tool_gateway/ingestion/servicenow_binding.py#L56-L77)
- [mock_servicenow_table_api.py:136-158](file://shared/platform-ops/gitops/runtime-profiles/servicenow-dev/mock_servicenow_table_api.py#L136-L158)
- [test_servicenow_native.py:349-423](file://products/tool-gateway/tests/test_servicenow_native.py#L349-L423)

### Performance Issues
Symptoms:
- Long-running streams stall or time out
- High error rates or slow responses
- Missing traces/metrics/logs in OpenObserve

Diagnostics:
- Check provider health and timeouts (CHAT_RESPONSE_TIMEOUT_SECONDS)
- Review /metrics for RED metrics and domain counters
- Validate OTEL_ENABLED and exporter endpoint/auth headers
- Inspect session store backends and fallbacks

Remediation:
- Adjust timeouts and provider rate limits
- Provision OTel headers and correct endpoint
- Ensure Postgres/Redis availability for session/state stores
- Monitor evidence store truncation markers and session budgets

**Section sources**
- [troubleshooting.md:138-168](file://docs/guides/troubleshooting.md#L138-L168)
- [troubleshooting.md:551-586](file://docs/guides/troubleshooting.md#L551-L586)
- [session_store.py:949-969](file://products/agent-platform/src/agent_service/services/session_store.py#L949-L969)
- [SPEC-005-observability-baseline/spec.md:27-35](file://docs/specs/SPEC-005-observability-baseline/spec.md#L27-L35)

### Data Consistency Problems
Symptoms:
- Session workspace shows no history (transcript_available: false)
- Session detail returns evidence_turns: null
- Session delete returns 409 (cannot delete)
- Audit view empty or recent events missing
- Audit ingest rejected with 401

Diagnostics:
- Inspect session API fields and agent-platform logs for transcript/evidence warnings
- Check audit emitter delivery counters and audit-service readiness
- Validate *_AUDIT_SERVICE_URL and *_AUDIT_CLIENT_SECRET alignment

Remediation:
- For transcripts: send a chat turn to populate snapshot; corrupt snapshots degrade gracefully
- For evidence: verify database connectivity; accept truncation markers as design
- Resolve pending HITL confirmations before deleting sessions
- Re-sync audit secrets and restart emitters and audit-service

**Section sources**
- [troubleshooting.md:720-783](file://docs/guides/troubleshooting.md#L720-L783)
- [troubleshooting.md:314-353](file://docs/guides/troubleshooting.md#L314-L353)
- [troubleshooting.md:356-382](file://docs/guides/troubleshooting.md#L356-L382)
- [runtime_kernel.py:1826-1857](file://products/agent-platform/src/agent_service/runtime_kernel.py#L1826-L1857)

### Deployment Failures
Symptoms:
- Pods fail with ErrImagePull after deployment
- Readiness shows "degraded" due to policy bundle load failure

Diagnostics:
- Inspect pod images and overlay state
- Check readiness endpoints for policy_error and bundle fingerprints

Remediation:
- Always deploy via make deploy to patch image tags
- Validate and re-sync policy bundle; restart gateways to reload

**Section sources**
- [troubleshooting.md:235-258](file://docs/guides/troubleshooting.md#L235-L258)
- [troubleshooting.md:261-289](file://docs/guides/troubleshooting.md#L261-L289)
- [deploy-overlay.sh:1-44](file://shared/platform-ops/gitops/deploy-overlay.sh#L1-L44)

### Environment-Specific Troubleshooting
- Dev vs production:
  - Dev overlays include browser-dev and mutating-dev postures; production disables mutating tools by default
  - Ensure workload identity and project-scoped secrets are provisioned
- External integrations:
  - Keycloak reachability and redirect URIs must match portal origins
  - Elastic connector requires URL and auth; output redaction can be toggled
  - Incident intake requires webhook token; misconfigurations return 503 or 401
- ServiceNow integration:
  - ServiceNow base URL must be HTTPS and reachable from cluster
  - OAuth client credentials must be properly configured in ServiceNow Application Registry
  - Network policies must allow egress to ServiceNow on port 443
  - Custom CA bundles may be required for private CA environments

**Section sources**
- [configuration-reference.md:682-724](file://docs/guides/configuration-reference.md#L682-L724)
- [troubleshooting.md:102-135](file://docs/guides/troubleshooting.md#L102-L135)
- [troubleshooting.md:450-484](file://docs/guides/troubleshooting.md#L450-L484)
- [servicenow-integration.md:68-96](file://docs/guides/servicenow-integration.md#L68-L96)

## Dependency Analysis
Cross-service dependency chains that commonly cause failures:
- Token delegation chain: mismatched client IDs/secrets block tool invocation
- Identity verification chain: issuer/audience/JWKS mismatches cause 401
- Tool relay chain: unset URLs prevent tool registration and invocation
- Audit ingestion chain: misaligned secrets lead to 401 ingest rejections
- Skills retrieval chain: missing URL/credentials hides skills tools
- Incident intake/triage chain: webhook token or query clients misconfigured blocks intake and triage
- ServiceNow integration chain: base URL, credential sets, and OAuth configuration must all be aligned

```mermaid
graph LR
PGW["Platform Gateway"] -- "Delegated token" --> IDB["Identity Broker"]
PGW -- "Policy decision" --> PGW
AGP -- "Tool calls" --> TGW
AGP -- "Handoff" --> ERW
PGW -- "Audit events" --> AUD
AGP -- "Audit events" --> AUD
TGW -- "Audit events" --> AUD
IDB -- "Audit events" --> AUD
TGW -- "ServiceNow API" --> SNOW["ServiceNow"]
SNOW -- "Audit attribution" --> AUD
```

**Diagram sources**
- [configuration-reference.md:33-126](file://docs/guides/configuration-reference.md#L33-L126)
- [configuration-reference.md:128-168](file://docs/guides/configuration-reference.md#L128-L168)

**Section sources**
- [configuration-reference.md:33-126](file://docs/guides/configuration-reference.md#L33-L126)
- [configuration-reference.md:128-168](file://docs/guides/configuration-reference.md#L128-L168)

## Performance Considerations
- Prefer read-only tools where possible; enabling mutating tools increases risk and requires approvals
- Tune timeouts for chat responses and worker handoffs to avoid stalls
- Use evidence store size caps and session budgets to bound memory usage
- Keep OTel push enabled for correlation; ensure collector endpoint is reachable
- Monitor RED metrics and domain counters to detect degradation early
- ServiceNow read operations are bounded by limit parameters and timeout settings

[No sources needed since this section provides general guidance]

## Troubleshooting Guide

### Symptom Categories and Procedures

#### Deployment Failures
- ErrImagePull:
  - Diagnose: inspect pod images and overlay state
  - Remediate: run deploy-overlay script or use make deploy
- Policy bundle degraded:
  - Diagnose: check readiness endpoint for policy_error and bundle fingerprint
  - Remediate: validate and re-sync policy bundle; restart gateways

**Section sources**
- [troubleshooting.md:235-289](file://docs/guides/troubleshooting.md#L235-L289)
- [deploy-overlay.sh:1-44](file://shared/platform-ops/gitops/deploy-overlay.sh#L1-L44)

#### Authentication Problems
- Portal login fails:
  - Diagnose: OIDC config, Keycloak reachability, redirect URIs
  - Remediate: reconcile Keycloak client; restart identity-service
- Token verification errors:
  - Diagnose: issuer/audience/JWKS; test with local verification
  - Remediate: fix issuer/audience; refresh JWKS cache

**Section sources**
- [troubleshooting.md:102-135](file://docs/guides/troubleshooting.md#L102-L135)
- [test_gateway_auth.py:48-67](file://products/platform-gateway/tests/test_gateway_auth.py#L48-L67)
- [token_verifier.py (platform-gateway):52-80](file://products/platform-gateway/src/platform_gateway/services/token_verifier.py#L52-L80)

#### Tool Execution Errors
- No tools available:
  - Diagnose: TOOL_GATEWAY_URL, tool-gateway readiness, K8s connector
  - Remediate: set URL; apply RBAC; restart tool-gateway
- ELASTIC_NOT_CONFIGURED:
  - Diagnose: GATEWAY_ELASTIC_* variables
  - Remediate: enable and configure Elastic connector
- Mutating tool absent or denied:
  - Diagnose: GATEWAY_MUTATING_TOOLS_ENABLED, policy grants, HITL bridging
  - Remediate: enable flag; apply RBAC; grant tools:mutate; enable HITL
- Confirmed mutation fails with K8S_PERMISSION_DENIED:
  - Diagnose: service account permissions
  - Remediate: apply pod-delete Role/RoleBinding

**Section sources**
- [troubleshooting.md:71-99](file://docs/guides/troubleshooting.md#L71-L99)
- [troubleshooting.md:211-231](file://docs/guides/troubleshooting.md#L211-L231)
- [troubleshooting.md:588-718](file://docs/guides/troubleshooting.md#L588-L718)
- [configuration-reference.md:17-21](file://docs/guides/configuration-reference.md#L17-L21)

#### ServiceNow Integration Errors
- ServiceNow tools not available:
  - Diagnose: GATEWAY_SERVICENOW_ENABLED, base URL configuration
  - Remediate: enable ServiceNow integration; set base URL
- Connection failures:
  - Diagnose: network reachability, DNS resolution, TLS certificates
  - Remediate: check NetworkPolicy, mount CA bundle, verify ServiceNow accessibility
- Authentication failures:
  - Diagnose: credential set configuration, OAuth application setup
  - Remediate: re-run sync script, verify OAuth configuration in ServiceNow
- Mock service issues:
  - Diagnose: mock deployment status, credential synchronization
  - Remediate: restart mock service, regenerate credentials

**Section sources**
- [servicenow-integration.md:633-649](file://docs/guides/servicenow-integration.md#L633-L649)
- [servicenow_native.py:344-368](file://products/tool-gateway/src/tool_gateway/ingestion/servicenow_native.py#L344-L368)
- [mock_servicenow_table_api.py:136-158](file://shared/platform-ops/gitops/runtime-profiles/servicenow-dev/mock_servicenow_table_api.py#L136-L158)

#### Performance Issues
- Stream stalls or timeouts:
  - Diagnose: provider health, CHAT_RESPONSE_TIMEOUT_SECONDS
  - Remediate: adjust timeouts; check provider rate limits
- Missing telemetry:
  - Diagnose: OTEL_ENABLED, endpoint, headers
  - Remediate: provision OTel headers; redeploy

**Section sources**
- [troubleshooting.md:138-168](file://docs/guides/troubleshooting.md#L138-L168)
- [troubleshooting.md:551-586](file://docs/guides/troubleshooting.md#L551-L586)
- [SPEC-005-observability-baseline/spec.md:27-35](file://docs/specs/SPEC-005-observability-baseline/spec.md#L27-L35)

#### Data Consistency Problems
- Transcript unavailable:
  - Diagnose: session snapshot state; agent-platform logs
  - Remediate: send a chat turn; accept degraded transcript behavior
- Evidence turns null:
  - Diagnose: evidence store backend; metrics for write failures
  - Remediate: restore DB; accept truncation markers
- Session delete 409:
  - Diagnose: pending HITL confirmation
  - Remediate: resolve confirmation before deletion
- Audit view empty or 401 ingest:
  - Diagnose: emitter URLs and secrets; audit-service readiness
  - Remediate: re-sync audit secrets; restart emitters and audit-service

**Section sources**
- [troubleshooting.md:720-783](file://docs/guides/troubleshooting.md#L720-L783)
- [troubleshooting.md:314-382](file://docs/guides/troubleshooting.md#L314-L382)
- [runtime_kernel.py:1826-1857](file://products/agent-platform/src/agent_service/runtime_kernel.py#L1826-L1857)

### Frequently Asked Questions
- Why do I see "denied by policy" for a tool?
  - The user's role lacks the required action; verify OIDC groups and policy bundle grants.
- How do I enable mutating tools safely?
  - Enable GATEWAY_MUTATING_TOOLS_ENABLED, apply RBAC, enable HITL bridging, and grant tools:mutate.
- What happens if audit-service is down?
  - Ingestion degrades to log-only auditing; user requests succeed but events are not stored.
- Can I disable OTel push without affecting /metrics?
  - Yes; /metrics remains always-on; OTel push is gated by OTEL_ENABLED and fails open.
- How do I rotate secrets safely?
  - Use provided sync scripts to regenerate and propagate secrets; restart affected deployments.
- Why are ServiceNow tools not available?
  - Check GATEWAY_SERVICENOW_ENABLED is true and base URL is configured; verify ServiceNow integration is properly deployed.
- How do I troubleshoot ServiceNow connectivity issues?
  - Probe from inside the pod using curl, check NetworkPolicy egress rules, and verify TLS certificate trust chain.
- What causes ServiceNow authentication failures?
  - Verify OAuth application configuration, grant type enablement, and credential set synchronization.

**Section sources**
- [configuration-reference.md:17-21](file://docs/guides/configuration-reference.md#L17-L21)
- [configuration-reference.md:128-168](file://docs/guides/configuration-reference.md#L128-L168)
- [SPEC-005-observability-baseline/spec.md:27-35](file://docs/specs/SPEC-005-observability-baseline/spec.md#L27-L35)
- [servicenow-integration.md:633-649](file://docs/guides/servicenow-integration.md#L633-L649)

### Known Limitations and Workarounds
- Shared query credential for audit-service allows ingest clients to query directly; plan to split registries for non-dev deployments.
- Mutating tools are deny-by-default; enabling them requires full activation checklist including RBAC and HITL.
- Evidence persistence is best-effort; failures do not fail turns but reduce replay fidelity.
- ServiceNow integration is read-only; write operations require separate specification and implementation.
- ServiceNow MCP server is not used; native REST/Table-API connector is employed instead.

**Section sources**
- [configuration-reference.md:159-168](file://docs/guides/configuration-reference.md#L159-L168)
- [troubleshooting.md:588-613](file://docs/guides/troubleshooting.md#L588-L613)
- [troubleshooting.md:750-783](file://docs/guides/troubleshooting.md#L750-L783)
- [servicenow-integration.md:17-57](file://docs/guides/servicenow-integration.md#L17-L57)

### Upgrade Considerations
- Policy bundle rollout requires editing canonical source, validating scenarios, syncing replicas, and restarting gateways to reload bundles.
- Image tag management relies on deploy-overlay; avoid raw kubectl apply -k to prevent placeholder tags.
- Secret provisioning scripts centralize rotation; prefer scripts over manual edits.
- ServiceNow integration upgrades require re-validation of field projections and OAuth configuration.

**Section sources**
- [configuration-reference.md:282-327](file://docs/guides/configuration-reference.md#L282-L327)
- [troubleshooting.md:235-258](file://docs/guides/troubleshooting.md#L235-L258)
- [sync-runtime-secret.sh:1-28](file://shared/platform-ops/gitops/sync-runtime-secret.sh#L1-L28)
- [sync-audit-secrets.sh:71-92](file://shared/platform-ops/gitops/sync-audit-secrets.sh#L71-L92)
- [sync-incident-secrets.sh:71-92](file://shared/platform-ops/gitops/sync-incident-secrets.sh#L71-L92)

### Using Observability Tools
- Metrics:
  - Every service exposes /metrics; use it to inspect RED metrics and domain counters (e.g., delegation, audit emits).
- Traces:
  - Enable OTel push; correlate logs via x-request-id and trace_id; ensure headers and endpoint are configured.
- Audit logs:
  - Check emitter delivery counters; validate audit-service readiness; review retention and max event caps.
- ServiceNow audit attribution:
  - Query durable audit store for target_system=servicenow events; check target_identity_mode=acting_service and failure_class=target_unavailable for connectivity issues.

**Section sources**
- [SPEC-005-observability-baseline/spec.md:12-35](file://docs/specs/SPEC-005-observability-baseline/spec.md#L12-L35)
- [observability-conventions.md:58-69](file://shared/shared-contracts/observability-conventions.md#L58-L69)
- [metrics.py (execution-runtime):93-111](file://products/execution-runtime/src/execution_runtime/core/metrics.py#L93-L111)
- [observability.py (execution-runtime):9-24](file://products/execution-runtime/src/execution_runtime/core/observability.py#L9-L24)
- [observability.py (audit-service):9-23](file://products/audit-service/src/audit_service/core/observability.py#L9-L23)
- [observability.py (skills-hub):9-23](file://products/skills-hub/src/skills_hub/core/observability.py#L9-L23)
- [observability.py (incident-service):9-23](file://products/incident-service/src/incident_service/core/observability.py#L9-L23)

## Conclusion
Use this guide to systematically diagnose and resolve common issues across deployment, authentication, tool execution, performance, data consistency, and ServiceNow integration. Leverage the platform's built-in observability surfaces (/metrics, OTel, audit trail) and follow the documented secret provisioning and policy rollout procedures to maintain reliability and security. When in doubt, start with readiness endpoints, metrics, and structured logs to narrow the problem scope before making configuration changes. For ServiceNow issues, focus on connectivity, authentication, and field projection validation.

[No sources needed since this section summarizes without analyzing specific files]

## Appendices

### Health and Response Schemas
- Health response schema defines status values and service metadata used by readiness endpoints.
- Chat response schema defines status values for streaming responses.

**Section sources**
- [health-response.schema.json:1-20](file://shared/shared-contracts/schemas/health-response.schema.json#L1-L20)
- [chat-response.schema.json:1-25](file://shared/shared-contracts/schemas/chat-response.schema.json#L1-L25)

### Error Mapping and Receipts
- Execution results map to receipt statuses: success → succeeded, TIMEOUT → timeout, other errors → failed.
- Rejection reasons are recorded with digest mismatch detection for signed envelopes.

**Section sources**
- [executor.py:124-151](file://products/execution-runtime/src/execution_runtime/services/executor.py#L124-L151)
- [runtime_kernel.py:1826-1857](file://products/agent-platform/src/agent_service/runtime_kernel.py#L1826-L1857)

### Portal Error Messaging
- Portal maps API errors to user-friendly messages for incident report creation and related operations.

**Section sources**
- [DocumentsView.tsx:70-102](file://products/operator-portal/web-ui/app/src/views/workspace/DocumentsView.tsx#L70-L102)

### ServiceNow Integration Reference
- ServiceNow read-tier tools provide access to incident, change_request, sys_user, and cmdb_ci tables
- All operations are read-only with strict field projection and credential protection
- Integration uses native REST/Table-API connector rather than MCP adapter
- Audit attribution tracks acting_service identity and target_unavailable failures

**Section sources**
- [servicenow-integration.md:17-57](file://docs/guides/servicenow-integration.md#L17-L57)
- [servicenow_binding.py:110-175](file://products/tool-gateway/src/tool_gateway/ingestion/servicenow_binding.py#L110-L175)
- [servicenow_native.py:458-471](file://products/tool-gateway/src/tool_gateway/ingestion/servicenow_native.py#L458-L471)