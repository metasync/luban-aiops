# SPEC-004 Tasks: Deny-By-Default Policy Enforcement

Task states: `[ ]` pending, `[x]` done. Implementation starts when the spec is `approved`.

## R-1: Policy contract in shared-contracts

- [x] create `schemas/policy-rule.schema.json` (rule shape, `action_authz` only, `allow`/`deny` outcomes)
- [x] create `schemas/policy-decision.schema.json` (decision object, Tier-1 minimum response)
- [x] create `policies/policy-default.yaml` (role→action grants; all five roles get `chat`, `session:create`, `session:read`)
- [x] update `shared/shared-contracts/README.md`: policy contract, action naming convention

## R-2: Gateway policy decision module

- [x] add `PyYAML` dependency to `products/tool-gateway/pyproject.toml`
- [x] create `services/policy_engine.py`: bundle loading, validation, `evaluate()`, `reset_policy_state()`
- [x] package default bundle copy at `api_gateway/policies/policy-default.yaml`
- [x] add `GATEWAY_POLICY_PATH` setting; configured-but-invalid path fails `/health/ready`
- [x] implement precedence: deny-by-default, explicit deny wins, priority ordering, disabled rules skipped

## R-3: Deny-by-default enforcement on business routes

- [x] add `enforce_policy()` helper to `gateway_service.py` (evaluate → log → 403 on deny)
- [x] wire actions: chat routes → `chat`, sessions routes → `session:create` / `session:read`
- [x] structured `403` body: `detail`, `action`, `reason`
- [x] denied `chat/stream` returns plain 403 JSON before streaming starts
- [x] test asserting the protected-route list (exemptions stay visible)

## R-4: Decision audit logging

- [x] log every evaluation: `subject`, `roles`, `action`, `decision`, `matched_rule_ids`, `x-request-id`
- [x] denials at `WARNING`, allows at `INFO`

## R-5: Contract and CI enforcement

- [x] `tests/test_policy_engine.py`: loading paths, precedence semantics, decision serialization
- [x] route enforcement tests: observer allowed `chat` (200), operator allowed, synthetic developer allowed, ungranted role denied (403 + body)
- [x] contract sync test: packaged bundle ≡ shared-contracts bundle; rules/decisions validate against schemas
- [x] update both dev overlay tool-gateway bases: policy ConfigMap, volume mount, `GATEWAY_POLICY_PATH`
- [x] verify CI passes for all three products; overlay bases render

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified
- [x] living state docs updated (root README, tool-gateway README, policy-center README, shared-contracts README)
- [x] `CHANGELOG.md` entry added referencing `SPEC-004`
- [x] spec index in `docs/specs/README.md` updated
- [x] spec status set to `delivered`
