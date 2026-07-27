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

## Current Closure Status

As of `2026-07-27`, `Release 0` closure is validated in a live Kubernetes
environment:

- the portal completes `OIDC` login, callback handling, and logout entry points
- `identity-broker` exchanges authorization codes, normalizes user info, and
  resolves bearer-backed identity
- `api-gateway` propagates authenticated identity to session and chat routes
  instead of relying only on manual `user_id` entry
- core services emit structured JSON access and session logs with `request_id`
  and `session_id` fields
- the authenticated request path was verified live against the shared sandbox
  `Keycloak` realm in the `dev-k8s-transitional` overlay deployed to the
  `dev-luban-aiops` namespace

Focused unit tests, GitOps overlay render checks, and live browser validation
now pass for the `Release 0` acceptance path. Remaining work is limited to
post-`Release 0` follow-up items and non-blocking UX polish, not acceptance
blockers.

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

- [x] define initial service names and repository placement for `web-ui`, `api-gateway`, and `agent-service`
- [x] define shared request and response schemas for chat, session, and health endpoints
- [x] define shared correlation and trace metadata fields
- [x] create initial Kubernetes or Helm layout for one target environment
- [x] define environment variable conventions for local and cluster deployment
- [x] document initial service ports, routes, and ingress expectations

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

- [x] create the first portal application skeleton
- [x] add a basic authenticated shell with room for chat and session views
- [x] add login entry and logout entry points
- [x] define the initial portal-to-gateway API contract
- [x] add a minimal session page for sending one prompt and rendering one streamed reply
- [x] expose correlation IDs or request references in a debug-friendly way

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

- [x] create an `api-gateway` service boundary in the workspace
- [x] define routes for portal auth handoff, session creation, prompt send, and streaming
- [x] validate token forwarding or session propagation to backend services
- [x] add health endpoints for gateway readiness and liveness
- [x] add request ID propagation and structured access logging
- [x] document ingress or internal service exposure assumptions

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

- [x] create an `agent-service` skeleton aligned to the selected runtime approach
- [x] add a simple prompt handler that returns deterministic placeholder output
- [x] define session creation and session retrieval behavior
- [x] add health and readiness endpoints
- [x] emit structured logs with request ID and session ID
- [x] prepare runtime configuration for later tool and policy integration without implementing those paths yet

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

- [x] choose the initial session store strategy for the first environment
- [x] define the event format for streamed responses
- [x] implement a basic `SSE` path from runtime to portal
- [x] preserve request ID and session ID across the full streaming path
- [x] defer reconnect or refresh behavior for an in-progress session to post-`Release 0` follow-up
- [x] log session lifecycle events in a traceable way

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

- [x] define `OIDC` client configuration expectations for the portal
- [x] integrate the first `Keycloak` login flow
- [x] normalize essential identity fields needed by downstream services
- [x] document how user identity is passed from portal to gateway and runtime
- [x] add logout behavior for the initial portal scope
- [x] validate the login flow in one Kubernetes environment

Outputs:

- first working `SSO` integration
- normalized identity context contract
- documented identity propagation path

## Cross-Product Integration Checklist

- [x] `operator-portal` can authenticate through `identity-broker`
- [x] `operator-portal` can call `api-gateway`
- [x] `api-gateway` can forward the request to `agent-platform`
- [x] `agent-platform` can create and retrieve session state
- [x] streamed responses can reach the portal over the agreed `SSE` path
- [x] request IDs, session IDs, and user identity are visible in logs across the request chain

## Validation Checklist

- [x] operator can log in through `SSO`
- [x] operator can open a portal session
- [x] operator can send one prompt and receive one streamed response
- [x] core services expose health endpoints
- [x] logs show request ID and session ID
- [x] deployment works in one target Kubernetes environment

## Exit Criteria

Release 0 is complete when all of the following are true:

- [x] the workspace contains initial runnable placeholders for `web-ui`, `api-gateway`, and `agent-service`
- [x] one end-to-end authenticated request path works in Kubernetes
- [x] session-aware streaming is functional
- [x] structured logs and trace metadata exist for core services
- [x] the implementation artifacts remain aligned with the workspace boundary model

## Post-Release 0 Follow-Up

- verify reconnect or refresh behavior for an in-progress session
- continue portal UX polish that does not change the validated authenticated
  request path or closure decision

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
