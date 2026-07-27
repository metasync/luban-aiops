# Release Notes: 2026-07-26

## Summary

This implementation wave advances `Release 0` in three related areas:

- the runtime/provider path inside `products/agent-platform`
- the Kubernetes development overlay path for the Release 0 baseline stack
- the authenticated portal-to-gateway-to-runtime path needed for formal closure

Together, these changes make provider switching easier, reduce gateway coupling
to the transitional runtime shape, and make the development-overlay rollout
path more predictable, maintainable, and GitOps-friendly. With the live
Kubernetes validation path and the final closure-document cleanup now in place,
`Release 0` is complete.

## Change Set 3: Authenticated Portal Closure Path

### Highlights

- added a minimal `OIDC` authorization-code login flow for
  `products/operator-portal` using browser `sessionStorage`
- added `identity-broker` endpoints for login start, authorization-code
  exchange, logout URL generation, and bearer-backed current-identity
  resolution
- updated `api-gateway` so authenticated bearer identity overrides manual
  `user_id` values for session creation, prompt submission, and streaming
- added optional `identity-service-runtime-secrets` injection and
  `OIDC_POST_LOGOUT_REDIRECT_URI` configuration to the GitOps baseline overlay
- added structured JSON access and session logs across the core services so
  `request_id`, `session_id`, and authenticated user identity are visible in
  the request chain
- added a Git-tracked Keycloak browser-client reconciliation step for
  `dev-k8s-transitional` so the validated portal client redirect and identity
  claim settings remain durable across later overlay deploys

### Why It Matters

- the portal no longer stops at "get login URL"; it can now complete a real
  callback and hold an authenticated browser session for downstream calls
- the gateway can now derive runtime identity from an authenticated bearer
  token instead of depending only on manually supplied usernames
- the deployment baseline now has a clear configuration contract for the
  identity-service `OIDC` flow, including optional client-secret injection
- the validated sandbox `Keycloak` browser client no longer drifts away from
  the portal's required redirect and identity-claim contract after redeploys
- request tracing is more useful during closure validation because the same
  identifiers now show up in service logs as well as response payloads

### Validation

- `identity-broker`: focused auth and identity tests passed
- `tool-gateway`: focused authenticated-identity propagation tests passed
- `agent-platform`: focused runtime/session tests passed with the new logging
  hooks in place
- both `dev-k8s-transitional` and `dev-k8s-native` overlays still render
  cleanly via `kubectl kustomize`
- live browser validation now passes in Kubernetes for:
  - `SSO` login through the shared sandbox `Keycloak` realm
  - portal callback completion in `operator-portal`
  - session creation through `api-gateway`
  - streamed prompt completion through `agent-service`
- live validation environment:
  - overlay: `dev-k8s-transitional`
  - namespace: `dev-luban-aiops`
  - portal entry: `kubectl port-forward service/web-ui 18080:80`

## Change Set 1: Runtime Provider And Gateway Refactor

### Highlights

- added typed provider-specific runtime options for `dashscope`, `deepseek`,
  and `openai`
- introduced provider adapters that map workspace runtime configuration to
  concrete AgentScope chat model classes
- added a provider registry and provider-owned defaults for model and endpoint
  resolution
- expanded runtime metadata to expose resolved provider configuration and last
  provider error state
- refactored `products/tool-gateway` to resolve backend mode through shared
  backend adapters with `auto`, `transitional`, and `native` handling

### Why It Matters

- runtime configuration is now easier to evolve without leaking provider
  details through the rest of the service
- gateway request handling no longer scatters backend-mode branching across
  multiple endpoints
- runtime status is clearer for operators and for downstream diagnostics

### Validation

- `agent-platform`: focused runtime/provider tests passed
- `tool-gateway`: backend adapter tests passed
- live development-overlay runtime metadata confirmed
  `configured_agent_backend_mode=auto`
  and a successful `transitional` resolution path through `api-gateway`

## Change Set 2: Release 0 Dev K8s Containerization And Rollout

### Highlights

- added Dockerfiles for `agent-service`, `api-gateway`, `identity-service`, and
  `web-ui`
- added an `nginx` proxy baseline for `products/operator-portal`
- updated the portal browser baseline to use the current origin by default for
  API traffic
- added deterministic image build and deploy scripts for both
  `dev-k8s-transitional` and `dev-k8s-native`
- moved the active operational assets to the durable
  `shared/platform-ops/gitops/` root and kept `Release 0` as milestone wording
  in planning documents only
- added shared runtime profile overlays plus selector and verification helpers
  so provider choice is declared in Git
- updated development-overlay config and runbook documentation to match the new
  rollout path, product-oriented manifest layout, and stable runtime profile
  contract
- added overlay-specific image tag generation and per-overlay `.images.env`
  state tracking for clearer rollout traceability
- aligned native-overlay image build and deploy wrappers with the documented
  direct-execution workflow

### Why It Matters

- development Kubernetes rollout is now more repeatable and closer to the
  intended Kubernetes-first deployment model
- image rollout no longer depends on reusing a static development tag and now
  makes the active overlay visible directly in the image tag
- browser validation is simpler because the development portal and gateway can
  be exercised through a single entrypoint
- operational assets are now easier to evolve because product ownership,
  profile selection, and overlay state are separated more cleanly

### Validation

- fresh development-overlay images built with explicit overlay-aware tags
- deployments rolled out successfully in the `dev-luban-aiops` namespace
- session creation and chat requests succeeded through the refreshed
  development-overlay
  `api-gateway` path
- both `dev-k8s-transitional` and `dev-k8s-native` overlays render cleanly via
  `kubectl kustomize`

## Known Limitations

- the checked-in `dev-k8s-transitional` overlay still starts the transitional
  `agent-service` entrypoint even though the gateway can now reason about both
  transitional and native backends
- the sibling `dev-k8s-native` overlay exists for native AgentScope service
  validation, but the broader request path still defaults to the transitional
  profile
- native image/build wrapper parity is now in place, but manual local smoke
  runs still need care because regenerating `.images.env` updates local
  deployment state by design
- the streaming request completes successfully, but the browser still reports
  a client-side `net::ERR_ABORTED` entry after the final `SSE` event
- model output should not be treated as the source of truth for runtime
  provider state; `/api/v1/runtime` remains authoritative

## Related Documents

- `../release-0-implementation-checklist.md`
- `../agent-platform-runtime-options.md`
- `../../workspace/product-boundaries.md`
- `../../../CHANGELOG.md`
