# SPEC-004: Deny-By-Default Policy Enforcement

## Status

- status: `delivered`
- owner: workspace maintainers
- created: 2026-07-28
- release slice: `Release 1` (identity before privilege)
- related risks: B2 (no policy enforcement — any identity can invoke any action)

## Summary

Introduce deny-by-default authorization at the gateway: every business request is mapped to a named action, evaluated against a versioned role→action policy, and denied with a structured `403` unless a rule explicitly allows it. Every decision is audit-logged. This is the first enforceable slice of the Tier-1 policy design (`docs/agentic-aiops-platform/policy-specification.md`), scoped to the `action_authz` domain only.

## Motivation

SPEC-003 delivered verified identity: every request now carries cryptographically trustworthy `sub` and `roles` claims (or an explicitly-logged synthetic dev identity). But those roles are decorative — nothing consumes them:

- any authenticated identity (including `read-only-observer`) can invoke chat, create sessions, and read any session the user-id scoping allows
- there is no enforcement point where a future high-risk action (restart, scale, config change) could be gated
- the authorization matrix and policy specification exist as Tier-1 design documents with zero code backing them
- policy-center is an empty stub with no contract to grow into

Without B2, the security arc stops at authentication. Verified identity without authorization is a locked front door with no interior doors.

## Decision: Policy Evaluation In The Gateway, Contract In shared-contracts

The policy decision logic lives in a small, dependency-free module inside the gateway for now; the policy *contract* (rule schema, decision object, default policy bundle) lives in `shared/shared-contracts` so it is product-neutral. When policy-center becomes a real service, the module lifts-and-shifts behind the already-defined contract — callers see the same decision object either way.

- rule model is a strict subset of the Tier-1 policy specification: domain `action_authz` only, outcomes `allow` and `deny` only
- deny-by-default: no matching rule means `deny`
- explicit `deny` overrides `allow`; higher `priority` wins between allows
- the policy bundle is a versioned YAML file, GitOps-managed like every other config

## Requirements

### R-1: Policy contract in shared-contracts

The rule schema, decision object, and default policy bundle are defined as shared contracts.

Acceptance criteria:

- `policy-rule.schema.json` defines the rule shape: `id`, `domain` (fixed: `action_authz`), `description`, `priority`, `enabled`, `match` (`roles_any`, `actions_any`), `decision` (`allow` | `deny`) — a strict subset of the Tier-1 rule schema, forward-compatible with `require_approval` and conditions
- `policy-decision.schema.json` defines the decision object: `decision`, `matched_rule_ids`, `reason` (required); `action`, `subject` (optional) — matching the Tier-1 minimum decision response
- a default policy bundle `policy-default.yaml` ships in `shared/shared-contracts/policies/` covering the current gateway surface with actions: `chat`, `session:create`, `session:read`
- the default bundle grants: `platform-admin`, `approver`, `operator`, `developer`, `read-only-observer` → all three actions (`chat`, `session:create`, `session:read`); chat is conversational today (a read surface), so observer is allowed per the authorization matrix; when chat gains a mutating capability, that capability gets its own action name and observer is denied it by default
- `shared/shared-contracts/README.md` documents the policy contract and the action naming convention (`<resource>:<verb>`, bare `chat` for the chat action)

### R-2: Gateway policy decision module

A small evaluation module produces decisions from the loaded policy bundle.

Acceptance criteria:

- the gateway loads the policy bundle at startup from `GATEWAY_POLICY_PATH`; when unset, it falls back to a copy of the default bundle packaged with the gateway (kept in sync with shared-contracts by a test)
- an invalid or unreadable bundle at a configured path fails startup readiness — no silent fallback to defaults when a path was explicitly set
- `evaluate(roles, action) -> PolicyDecision` implements: deny-by-default, explicit deny overrides allow, higher priority wins, disabled rules ignored
- evaluation is a pure in-memory operation — no network calls, no policy-center dependency
- the decision object serializes to the `policy-decision.schema.json` shape

### R-3: Deny-by-default enforcement on business routes

Every business route names its action and enforces the decision.

Acceptance criteria:

- route→action mapping: `POST /api/v1/chat` and `GET /api/v1/chat/stream` → `chat`; `POST /api/v1/sessions` → `session:create`; `GET /api/v1/sessions/{id}` → `session:read`
- enforcement runs after identity resolution (SPEC-003) and before any downstream call; the verified (or synthetic) identity's `roles` are the only policy input
- a `deny` decision returns `403` with a structured error body containing `detail`, `action`, and `reason` — never a bare 403
- health, runtime metadata, and auth routes (`/health/*`, `/api/v1/runtime`, `/api/v1/auth/*`, `/api/v1/identity/normalize`) are explicitly exempt — they are platform plumbing, not operator actions
- enforcement applies identically whether the identity is verified or synthetic dev — the `developer` role is granted access by policy, not by bypass

### R-4: Decision audit logging

Every policy decision is observable.

Acceptance criteria:

- every evaluation emits a structured log record with: `subject`, `roles`, `action`, `decision`, `matched_rule_ids`, `x-request-id`
- denials log at `WARNING`; allows log at `INFO`
- no separate audit store yet — structured stdout logs are the audit channel for this phase (consistent with the current observability posture)

### R-5: Contract and CI enforcement

Acceptance criteria:

- gateway tests validate: allow path per role (including `read-only-observer` → `chat` → 200), deny path (a role with no matching grant → 403 with structured body), deny-by-default for an unknown action/role, explicit-deny-overrides-allow, disabled-rule skip, invalid-bundle startup failure
- a contract test binds the gateway's packaged default bundle and decision serialization to the shared-contracts schemas
- SPEC-001/002/003 regression tests continue passing; CI green for all three Python products
- both dev Kustomize overlay bases continue to render (overlays mount the default policy via ConfigMap and set `GATEWAY_POLICY_PATH`)

## Non-Goals

- `require_approval` and `allow_with_conditions` outcomes, approval tiers, ticket/change-window conditions — future spec when execution actions exist
- `feature_access`, `approval`, and `execution_gate` policy domains
- policy-center as a running service — it stays a stub; this spec defines the contract it will later serve
- environment targeting (`environments_any`) — the platform has no multi-environment action surface yet
- resource-level / per-session ownership policies (session user-scoping already handles ownership)
- OPA or any external policy engine
- portal UI for policy management — policy changes go through Git review

## Impact

- products touched: `products/tool-gateway` (policy module, route enforcement, config knob)
- contracts touched: new `policy-rule.schema.json`, `policy-decision.schema.json`, `policies/policy-default.yaml` in `shared/shared-contracts`
- dependencies added: `PyYAML` (tool-gateway) for bundle loading
- deployment impact: dev overlays gain a policy ConfigMap and `GATEWAY_POLICY_PATH`
- living state docs to update on delivery: root `README.md`, `products/tool-gateway/README.md`, `products/policy-center/README.md` (contract pointer), `shared/shared-contracts/README.md`, `CHANGELOG.md`

## Open Questions

None — all resolved (see Changelog).

## Changelog

- 2026-07-28: created as `draft` addressing risk B2
- 2026-07-28: resolved open questions — (1) `read-only-observer` is allowed `chat`, `session:create`, and `session:read`: the authorization matrix explicitly grants observer "chat and service query", and chat is conversational (a read surface) today; when chat gains a mutating capability it gets its own action name and observer is denied it by default — deny-by-default stays meaningful at action granularity rather than punishing the read surface; (2) a denied `GET /api/v1/chat/stream` returns a plain `403` JSON response before the stream starts — normal HTTP semantics, no SSE error event; status → `approved`
- 2026-07-28: implementation started; status → `in-progress`
- 2026-07-28: all requirements implemented and verified (115 tests passing: gateway 48, identity-broker 18, agent-platform 49; both overlay bases render); status → `delivered`
