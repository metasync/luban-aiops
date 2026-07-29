# SPEC-004 Plan: Deny-By-Default Policy Enforcement

> Finalized 2026-07-28 alongside spec approval; open questions resolved in the spec changelog.

## Approach

Work contract-first: define the rule/decision schemas and the default policy bundle in shared-contracts (R-1), then build the gateway's pure evaluation module against them (R-2), wire enforcement into the business routes (R-3) with audit logging (R-4), and land tests plus overlay updates alongside each step (R-5).

## Design Per Requirement

### R-1: Policy contract in shared-contracts

- affected: `shared/shared-contracts/`
- new schemas in `schemas/`:
  - `policy-rule.schema.json` — rule shape: `id`, `domain` (const `action_authz`), `description`, `priority` (integer), `enabled` (boolean), `match` (`roles_any`, `actions_any` — string arrays), `decision.outcome` (`allow` | `deny`); `additionalProperties: false` so future fields (conditions, approval tiers) arrive via schema revision, not silent drift
  - `policy-decision.schema.json` — decision object: `decision` (`allow` | `deny`), `matched_rule_ids` (string array), `reason` (string) required; `action`, `subject` optional
- new directory `policies/` with `policy-default.yaml`:
  - `version: 1`, `rules:` list
  - allow rules: `platform-admin`/`approver`/`operator`/`developer`/`read-only-observer` → `chat`, `session:create`, `session:read` (observer allowed per the authorization matrix's "chat and service query" grant; chat is conversational today — a future mutating capability gets its own action name and observer is denied it by default)
  - no explicit deny rules in the default bundle — deny-by-default covers everything else
- README documents the contract, the action naming convention (`<resource>:<verb>`, bare `chat`), and that policy-center will later serve this same contract

### R-2: Gateway policy decision module

- affected: `products/tool-gateway/src/api_gateway/`
- new module: `services/policy_engine.py` — bundle loading, rule validation, evaluation
- bundle loading:
  - `GATEWAY_POLICY_PATH` set + file valid → load it
  - path set + file missing/invalid → raise at startup; `/health/ready` fails (no silent fallback when explicitly configured)
  - path not set → load the packaged default bundle (`api_gateway/policies/policy-default.yaml`, a copy of the shared-contracts bundle; a test asserts byte-for-byte sync)
- module-level singleton bundle with `reset_policy_state()` for tests (same pattern as `token_verifier`)
- `evaluate(roles, action) -> PolicyDecision`:
  1. collect enabled rules whose `match.roles_any` intersects `roles` and `actions_any` contains `action`
  2. any matched `deny` → deny (explicit deny overrides allow)
  3. otherwise highest-priority matched `allow` → allow
  4. no match → deny with reason `"no matching policy rule"` and empty `matched_rule_ids`
- `PolicyDecision` is a small dataclass/pydantic model serializing to the `policy-decision.schema.json` shape
- config additions: `GATEWAY_POLICY_PATH` (default: unset → packaged bundle)
- dependency: `PyYAML>=6.0,<7.0` added to gateway `pyproject.toml`
- alternatives: JSON bundle instead of YAML — rejected; the Tier-1 policy specification and GitOps config conventions use YAML, and PyYAML is a trivial dependency

### R-3: Deny-by-default enforcement on business routes

- affected: `api_gateway/api/routes/chat.py`, `api_gateway/api/routes/sessions.py`, `api_gateway/services/gateway_service.py`
- new helper in `gateway_service.py`: `enforce_policy(settings, identity, action, request_id)` — calls `evaluate(identity.roles, action)`, logs the decision (R-4), raises `HTTPException(403)` on deny with body `{detail, action, reason}`
- route→action wiring: `chat_route` and `chat_stream_route` → `chat`; `create_session_route` → `session:create`; `get_session_route` → `session:read`
- enforcement runs immediately after `resolve_request_identity` in each handler — verified and synthetic identities take the identical path
- a denied `chat/stream` returns plain `403` JSON before any SSE response starts (per resolved question 2)
- exempt routes (`/health/*`, `/api/v1/runtime`, `/api/v1/auth/*`, `/api/v1/identity/normalize`) simply never call `enforce_policy` — exemption is the absence of an action mapping, kept visible by a test asserting the protected-route list

### R-4: Decision audit logging

- affected: `services/gateway_service.py` (inside `enforce_policy`)
- one structured record per evaluation: `subject`, `roles`, `action`, `decision`, `matched_rule_ids`, `x-request-id`
- `LOGGER.warning` for deny, `LOGGER.info` for allow — stdout structured logs are the audit channel for this phase

### R-5: Contract and CI enforcement

- affected: `products/tool-gateway/tests/`, overlay bases
- new test module `tests/test_policy_engine.py`: deny-by-default, explicit-deny-overrides-allow, priority ordering, disabled-rule skip, invalid-bundle startup failure, packaged-bundle-matches-shared-contracts sync check, decision serialization validates against `policy-decision.schema.json`
- route tests in `tests/test_gateway_auth.py` (or a new `test_policy_enforcement.py`): observer → `chat` → 200; operator → `chat` → 200; developer (synthetic) → all actions → 200; a role with no matching grant → 403 with structured body; exempt routes unaffected
- overlays: both `dev-k8s-*` tool-gateway bases gain a `policy.yaml` ConfigMap entry (copy of the default bundle), a volume mount, and `GATEWAY_POLICY_PATH` in `runtime-config.env`; `kustomize build` must render for both bases
- regression: SPEC-001/002/003 suites pass; identity-broker and agent-platform untouched

## Sequencing And Dependencies

1. R-1 (contract) — no dependencies; schemas and bundle are pure artifacts
2. R-2 (evaluation module) — depends on 1 for the bundle/decision shapes
3. R-3 + R-4 (enforcement + audit) — depend on 2; implemented together (enforcement without logging is unauditable)
4. R-5 (tests + overlays) — lands alongside 2 and 3

## Test Strategy

- unit tests: bundle loading paths (valid/missing/invalid/unset), evaluation precedence semantics, decision serialization
- integration tests: TestClient hitting protected routes with identities carrying each role (via mocked `verify_token`, same fixture pattern as SPEC-003 tests)
- contract tests: packaged bundle ≡ shared-contracts bundle; bundle rules validate against `policy-rule.schema.json`; decisions validate against `policy-decision.schema.json`
- regression: full gateway suite plus overlay render checks

## Rollout And Migration

- the default bundle preserves current behavior for every existing role; `read-only-observer` keeps `chat`, `session:create`, and `session:read` per the authorization matrix, so no existing capability is revoked in this slice
- dev overlays pin the bundle explicitly via ConfigMap, so dev behavior is declared, not implied
- rollback: reverting the gateway to SPEC-003 code removes enforcement; the shared-contracts artifacts are inert without a consumer
- future: when policy-center becomes a service, `policy_engine.py` moves behind a `POST /policy/evaluate` endpoint returning the same decision object — gateway callers swap a function call for an HTTP call without contract changes
