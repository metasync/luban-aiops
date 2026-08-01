# SPEC-008 Tasks: Service-to-Service Identity — Broker-Mediated Token Delegation

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Audience binding on platform JWTs

- [x] add `audience` parameter to `issue_token` and emit `aud`; pass `aud=["tool-gateway"]` from login/callback (`products/identity-broker/src/identity_service/services/token_service.py`, `api/routes/auth.py`)
- [x] add `GATEWAY_TOKEN_AUDIENCE` setting (default `tool-gateway`) (`products/tool-gateway/src/api_gateway/core/config.py`)
- [x] enforce `aud` in `verify_token` (`audience=` + `require`), map `InvalidAudienceError` to 401 (`products/tool-gateway/src/api_gateway/services/token_verifier.py`)
- [x] add `aud` (required) and `act` (optional) to the schema (`shared/shared-contracts/schemas/identity-token.schema.json`)
- [x] tests: audience emission; valid aud → verified, wrong/missing aud → 401 (`products/identity-broker/tests/`, `products/tool-gateway/tests/`)

## R-2: Token exchange endpoint on identity-broker

- [x] add `IDENTITY_DELEGATED_TOKEN_TTL_SECONDS` (default 300) and `IDENTITY_SERVICE_CLIENTS` registry config (`products/identity-broker/src/identity_service/core/config.py`)
- [x] implement `exchange_service.py`: authenticate client, verify subject token, check audience allow-list, mint delegated token with `sub`/`username`/`roles` copied, `act`, `aud`, short TTL (`products/identity-broker/src/identity_service/services/exchange_service.py`)
- [x] add `POST /api/v1/auth/exchange` route (`products/identity-broker/src/identity_service/api/routes/auth.py`)
- [x] tests: exchange success; missing credential → 401; invalid/expired subject token → 401; disallowed audience → 400; roles never elevated (`products/identity-broker/tests/`)

## R-3: Service credential for the gateway

- [x] add `GATEWAY_SERVICE_CLIENT_ID` / `GATEWAY_SERVICE_CLIENT_SECRET` settings (`products/tool-gateway/src/api_gateway/core/config.py`)
- [x] broker validates the credential against the client registry; invalid → 401 (`products/identity-broker/src/identity_service/services/exchange_service.py`)
- [x] provision the gateway service Secret in the overlay (not committed) (`shared/platform-ops/gitops/dev-k8s/`)

## R-4: Gateway performs delegation on the agent-service contract

- [x] implement `delegation_client.exchange()` calling the broker exchange endpoint (`products/tool-gateway/src/api_gateway/services/delegation_client.py`)
- [x] add a gateway-side TTL cache keyed by user subject with near-expiry re-exchange (in-memory per replica; no dependency on agent-platform's session store) (`products/tool-gateway/src/api_gateway/services/`)
- [x] forward `Authorization: Bearer <delegated>` in `agent_client._headers`; keep `x-request-id`/`X-User-ID` (`products/tool-gateway/src/api_gateway/services/agent_client.py`)
- [x] make exchange failure non-fatal (log + counter, proceed tool-less); route synthetic dev identity through the same path (`products/tool-gateway/src/api_gateway/services/`)
- [x] tests: delegation forwarding; cache hit/miss/expiry; exchange-failure degradation; synthetic identity path (`products/tool-gateway/tests/`)

## R-5: agent-platform relays the delegated token

- [x] send `Authorization: Bearer` in `discover_tools` and `invoke_gateway_tool` (`products/agent-platform/src/agent_service/tools/gateway_tools.py`)
- [x] bind the owning user's delegated token into the toolkit closures (no cross-user sharing) (`products/agent-platform/src/agent_service/runtime_kernel.py`)
- [x] remove `identity_context` from the invoke payload (`products/agent-platform/src/agent_service/tools/gateway_tools.py`)
- [x] tests: bearer header sent on invoke + discovery; empty-Toolkit degradation without a token (`products/agent-platform/tests/`)

## R-6: Gateway tool routes derive identity from the token only

- [x] remove `identity_context` from the invoke request contract; document body identity is never trusted (`products/tool-gateway/src/api_gateway/api/routes/tools.py`, `services/gateway_service.py`)
- [x] authenticate `GET /api/v2/tools` and gate it behind a `tools:list` policy action (`products/tool-gateway/src/api_gateway/api/routes/tools.py`)
- [x] add `tools:list` rule to the policy bundle; keep all four copies byte-identical (`shared/shared-contracts/policies/policy-default.yaml` + gateway copies)
- [x] record `act` alongside `sub` in tool audit logs (`products/tool-gateway/src/api_gateway/services/gateway_service.py`)
- [x] tests: `tools:list` allowed/denied by role; wrong-audience rejected before policy; re-point SPEC-007 invoke tests to a real delegated-token flow (`products/tool-gateway/tests/`)

## R-7: Contracts, tests, overlays, observability

- [x] contract test binds gateway + identity-broker models to the updated schema (`products/tool-gateway/tests/`, `products/identity-broker/tests/`)
- [x] add metrics: `token_exchange_total{result}` (broker); `delegation_exchange_total{result}`, `delegation_cache_total{result}` (gateway)
- [x] set overlay env: `GATEWAY_TOKEN_AUDIENCE`, `GATEWAY_SERVICE_CLIENT_ID`, broker `IDENTITY_SERVICE_CLIENTS`, `IDENTITY_DELEGATED_TOKEN_TTL_SECONDS` (`shared/platform-ops/gitops/dev-k8s/`)
- [x] `kustomize build` renders for all overlays

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified
- [x] SPEC-007 R-4/R-6 and open questions Q-1/Q-2 closed; SPEC-007 status advanced
- [x] living state docs updated (see spec `Impact` section)
- [x] `CHANGELOG.md` entry added referencing the spec ID
- [x] spec index in `docs/specs/README.md` updated
- [x] spec status set to `delivered`
