# Release Notes: 2026-07-26

## Summary

This implementation wave advances `Release 0` in two related areas:

- the runtime/provider path inside `products/agent-platform`
- the Kubernetes development overlay path for the Release 0 baseline stack

Together, these changes make provider switching easier, reduce gateway coupling
to the transitional runtime shape, and make development-overlay image rollout
more predictable.

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
- added deterministic image build and deploy scripts for the Release 0
  development Kubernetes overlays
- updated development-overlay config and runbook documentation to match the new
  rollout path

### Why It Matters

- development Kubernetes rollout is now more repeatable and closer to the
  intended Kubernetes-first deployment model
- image rollout no longer depends on reusing a static development tag
- browser validation is simpler because the development portal and gateway can
  be exercised through a single entrypoint

### Validation

- fresh development-overlay images built with an explicit timestamped tag
- deployments rolled out successfully in the `dev-luban-aiops` namespace
- session creation and chat requests succeeded through the refreshed
  development-overlay
  `api-gateway` path

## Known Limitations

- the checked-in `dev-k8s-transitional` overlay still starts the transitional
  `agent-service` entrypoint even though the gateway can now reason about both
  transitional and native backends
- the sibling `dev-k8s-native` overlay exists for native AgentScope service
  validation, but the broader request path still defaults to the transitional
  profile
- native AgentScope service mode still depends on later agent bootstrap and
  surrounding request-path alignment work
- model output should not be treated as the source of truth for runtime
  provider state; `/api/v1/runtime` remains authoritative

## Related Documents

- `../release-0-implementation-checklist.md`
- `../agent-platform-runtime-options.md`
- `../../workspace/product-boundaries.md`
- `../../../CHANGELOG.md`
