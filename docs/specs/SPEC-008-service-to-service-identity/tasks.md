# SPEC-008 Tasks: Service-to-Service Identity — Broker-Mediated Token Delegation

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Audience binding on platform JWTs

- [ ] add `audience` parameter to `issue_token` and emit `aud`; pass `aud=["tool-gateway"]` from login/callback (`products/identity-broker/src/identity_service/services/token_service.py`, `api/routes/auth.py`)
- [ ] add `GATEWAY_TOKEN_AUDIENCE` setting (default `tool-gateway`) (`products/tool-gateway/src/api_gateway/core/config.py`)
- [ ] enforce `aud` in `verify_token` (`audience=` + `require`), map `InvalidAudienceError` to 401 (`products/tool-gateway/src/api_gateway/services/token_verifier.py`)
- [ ] add `aud` (required) and `act` (optional) to the schema (`shared/shared-contracts/schemas/identity-token.schema.json`)
- [ ] tests: audience emission; valid aud → verified, wrong/missing aud → 401 (`products/identity-broker/tests/`, `products/tool-gateway/tests/`)

## R-2: Token exchange endpoint on identity-broker

- [ ] add `IDENTITY_DELEGATED_TOKEN_TTL_SECONDS` (default 300) and `IDENTITY_SERVICE_CLIENTS` registry config (`products/identity-broker/src/identity_service/core/config.py`)
- [ ] implement `exchange_service.py`: authenticate client, verify subject token, check audience allow-list, mint delegated token with `sub`/`username`/`roles` copied, `act`, `aud`, short TTL (`products/identity-broker/src/identity_service/services/exchange_service.py`)
- [ ] add `POST /api/v1/auth/exchange` route (`products/identity-broker/src/identity_service/api/routes/auth.py`)
- [ ] tests: exchange success; missing credential → 401; invalid/expired subject token → 401; disallowed audience → 400; roles never elevated (`products/identity-broker/tests/`)

## R-3: Service credential for the gateway

- [ ] add `GATEWAY_SERVICE_CLIENT_ID` / `GATEWAY_SERVICE_CLIENT_SECRET` settings (`products/tool-gateway/src/api_gateway/core/config.py`)
- [ ] broker validates the credential against the client registry; invalid → 401 (`products/identity-broker/src/identity_service/services/exchange_service.py`)
- [ ] provision the gateway service Secret in the overlay (not committed) (`shared/platform-ops/gitops/dev-k8s/`)

## R-4: Gateway performs delegation on the agent-service contract

- [ ] implement `delegation_client.exchange()` calling the broker exchange endpoint (`products/tool-gateway/src/api_gateway/services/delegation_client.py`)
- [ ] add a gateway-side TTL cache keyed by user subject with near-expiry re-exchange (in-memory per replica; no dependency on agent-platform's session store) (`products/tool-gateway/src/api_gateway/services/`)
- [ ] forward `Authorization: Bearer <delegated>` in `agent_client._headers`; keep `x-request-id`/`X-User-ID` (`products/tool-gateway/src/api_gateway/services/agent_client.py`)
- [ ] make exchange failure non-fatal (log + counter, proceed tool-less); route synthetic dev identity through the same path (`products/tool-gateway/src/api_gateway/services/`)
- [ ] tests: delegation forwarding; cache hit/miss/expiry; exchange-failure degradation; synthetic identity path (`products/tool-gateway/tests/`)

## R-5: agent-platform relays the delegated token

- [ ] send `Authorization: Bearer` in `discover_tools` and `invoke_gateway_tool` (`products/agent-platform/src/agent_service/tools/gateway_tools.py`)
- [ ] bind the owning user's delegated token into the toolkit closures (no cross-user sharing) (`products/agent-platform/src/agent_service/runtime_kernel.py`)
- [ ] remove `identity_context` from the invoke payload (`products/agent-platform/src/agent_service/tools/gateway_tools.py`)
- [ ] tests: bearer header sent on invoke + discovery; empty-Toolkit degradation without a token (`products/agent-platform/tests/`)

## R-6: Gateway tool routes derive identity from the token only

- [ ] remove `identity_context` from the invoke request contract; document body identity is never trusted (`products/tool-gateway/src/api_gateway/api/routes/tools.py`, `services/gateway_service.py`)
- [ ] authenticate `GET /api/v2/tools` and gate it behind a `tools:list` policy action (`products/tool-gateway/src/api_gateway/api/routes/tools.py`)
- [ ] add `tools:list` rule to the policy bundle; keep all four copies byte-identical (`shared/shared-contracts/policies/policy-default.yaml` + gateway copies)
- [ ] record `act` alongside `sub` in tool audit logs (`products/tool-gateway/src/api_gateway/services/gateway_service.py`)
- [ ] tests: `tools:list` allowed/denied by role; wrong-audience rejected before policy; re-point SPEC-007 invoke tests to a real delegated-token flow (`products/tool-gateway/tests/`)

## R-7: Contracts, tests, overlays, observability

- [ ] contract test binds gateway + identity-broker models to the updated schema (`products/tool-gateway/tests/`, `products/identity-broker/tests/`)
- [ ] add metrics: `token_exchange_total{result}` (broker); `delegation_exchange_total{result}`, `delegation_cache_total{result}` (gateway)
- [ ] set overlay env: `GATEWAY_TOKEN_AUDIENCE`, `GATEWAY_SERVICE_CLIENT_ID`, broker `IDENTITY_SERVICE_CLIENTS`, `IDENTITY_DELEGATED_TOKEN_TTL_SECONDS` (`shared/platform-ops/gitops/dev-k8s/`)
- [ ] `kustomize build` renders for all overlays

## Delivery Gate

- [ ] all acceptance criteria in `spec.md` verified
- [ ] SPEC-007 R-4/R-6 and open questions Q-1/Q-2 closed; SPEC-007 status advanced
- [ ] living state docs updated (see spec `Impact` section)
- [ ] `CHANGELOG.md` entry added referencing the spec ID
- [ ] spec index in `docs/specs/README.md` updated
- [ ] spec status set to `delivered`
