# Release 0 Implementation Checklist

## Objective

Turn `Release 0 - Platform Foundation` into an executable checklist that can guide the first implementation wave across the workspace.

This checklist translates the backlog into:

- concrete workspace ownership
- implementation order
- first deliverables per product
- validation checkpoints

## Source Documents

This checklist is derived from:

- `implementation-backlog.md`
- `delivery-roadmap.md`
- `../workspace/product-boundaries.md`
- `../workspace/repository-reorganization-plan.md`

## Release 0 Goal

Create a runnable and observable baseline platform in Kubernetes with:

- portal entry
- basic `SSO`
- agent request path
- session-aware streaming
- traceable logs and request IDs

## Release 0 Scope

This release covers the first-wave workspace projects:

- `products/operator-portal`
- `products/agent-platform`
- `products/identity-broker`
- `products/tool-gateway`
- `shared/platform-ops`
- `shared/shared-contracts`
- `shared/shared-sdk`

`products/policy-center`, `products/skills-hub`, and `products/execution-runtime` stay out of the implementation critical path for this release.

## Suggested Implementation Sequence

1. establish shared contracts and deployment baseline
2. stand up portal shell and identity entry
3. stand up agent runtime and session path
4. connect portal to agent runtime through a gateway path
5. add streaming, correlation IDs, logs, and trace propagation
6. validate the full login-to-response path in one Kubernetes environment

## Epic Checklist

### `EPIC-00` Repository And Deployment Baseline

Primary owners:

- `shared/platform-ops`
- `shared/shared-contracts`
- `shared/shared-sdk`

Checklist:

- [ ] define initial service names and repository placement for `web-ui`, `api-gateway`, and `agent-service`
- [ ] define shared request and response schemas for chat, session, and health endpoints
- [ ] define shared correlation and trace metadata fields
- [ ] create initial Kubernetes or Helm layout for one target environment
- [ ] define environment variable conventions for local and cluster deployment
- [ ] document initial service ports, routes, and ingress expectations

Outputs:

- initial service layout under the workspace
- shared contract placeholders
- deployable baseline manifests or charts

### `EPIC-01` Web Portal Shell

Primary owner:

- `products/operator-portal`

Supporting owners:

- `products/identity-broker`
- `shared/shared-contracts`

Checklist:

- [ ] create the first portal application skeleton
- [ ] add a basic authenticated shell with room for chat and session views
- [ ] add login entry and logout entry points
- [ ] define the initial portal-to-gateway API contract
- [ ] add a minimal session page for sending one prompt and rendering one streamed reply
- [ ] expose correlation IDs or request references in a debug-friendly way

Outputs:

- first runnable `web-ui`
- authenticated shell layout
- minimal prompt and response view

### `EPIC-02` API Gateway Baseline

Primary owners:

- `products/tool-gateway`
- `shared/platform-ops`

Supporting owners:

- `products/identity-broker`
- `shared/shared-contracts`

Checklist:

- [ ] create an `api-gateway` service boundary in the workspace
- [ ] define routes for portal auth handoff, session creation, prompt send, and streaming
- [ ] validate token forwarding or session propagation to backend services
- [ ] add health endpoints for gateway readiness and liveness
- [ ] add request ID propagation and structured access logging
- [ ] document ingress or internal service exposure assumptions

Outputs:

- first gateway service placeholder
- baseline route map
- observable request path between portal and runtime

### `EPIC-03` Agent Runtime Baseline

Primary owner:

- `products/agent-platform`

Supporting owners:

- `shared/shared-contracts`
- `shared/shared-sdk`

Checklist:

- [ ] create an `agent-service` skeleton aligned to the selected runtime approach
- [ ] add a simple prompt handler that returns deterministic placeholder output
- [ ] define session creation and session retrieval behavior
- [ ] add health and readiness endpoints
- [ ] emit structured logs with request ID and session ID
- [ ] prepare runtime configuration for later tool and policy integration without implementing those paths yet

Outputs:

- first runnable `agent-service`
- session-aware prompt path
- structured baseline logging

### `EPIC-04` Session And Event Streaming Baseline

Primary owner:

- `products/agent-platform`

Supporting owners:

- `products/operator-portal`
- `shared/shared-contracts`

Checklist:

- [ ] choose the initial session store strategy for the first environment
- [ ] define the event format for streamed responses
- [ ] implement a basic `SSE` path from runtime to portal
- [ ] preserve request ID and session ID across the full streaming path
- [ ] verify reconnect or refresh behavior for an in-progress session
- [ ] log session lifecycle events in a traceable way

Outputs:

- working session model
- streamed response path
- traceable session lifecycle

### `EPIC-05` Enterprise SSO Baseline

Primary owner:

- `products/identity-broker`

Supporting owners:

- `products/operator-portal`
- `shared/platform-ops`

Checklist:

- [ ] define `OIDC` client configuration expectations for the portal
- [ ] integrate the first `Keycloak` login flow
- [ ] normalize essential identity fields needed by downstream services
- [ ] document how user identity is passed from portal to gateway and runtime
- [ ] add logout behavior for the initial portal scope
- [ ] validate the login flow in one Kubernetes environment

Outputs:

- first working `SSO` integration
- normalized identity context contract
- documented identity propagation path

## Cross-Product Integration Checklist

- [ ] `operator-portal` can authenticate through `identity-broker`
- [ ] `operator-portal` can call `api-gateway`
- [ ] `api-gateway` can forward the request to `agent-platform`
- [ ] `agent-platform` can create and retrieve session state
- [ ] streamed responses can reach the portal over the agreed `SSE` path
- [ ] request IDs, session IDs, and user identity are visible in logs across the request chain

## Validation Checklist

- [ ] operator can log in through `SSO`
- [ ] operator can open a portal session
- [ ] operator can send one prompt and receive one streamed response
- [ ] core services expose health endpoints
- [ ] logs show request ID and session ID
- [ ] deployment works in one target Kubernetes environment

## Exit Criteria

Release 0 is complete when all of the following are true:

- [ ] the workspace contains initial runnable placeholders for `web-ui`, `api-gateway`, and `agent-service`
- [ ] one end-to-end authenticated request path works in Kubernetes
- [ ] session-aware streaming is functional
- [ ] structured logs and trace metadata exist for core services
- [ ] the implementation artifacts remain aligned with the workspace boundary model

## Recommended First Implementation Cut

If work starts immediately, the smallest credible first cut is:

1. `shared/shared-contracts`
   - add chat request, chat response, session, and health schemas
2. `products/agent-platform`
   - create `agent-service` placeholder with health and prompt endpoints
3. `products/operator-portal`
   - create `web-ui` placeholder with one prompt form and streamed response panel
4. `shared/platform-ops`
   - add a single environment deployment path for the above services
5. `products/identity-broker`
   - add the first `Keycloak` integration path

This gives the workspace the smallest end-to-end slice that can be demonstrated and then extended in `Release 1`.
