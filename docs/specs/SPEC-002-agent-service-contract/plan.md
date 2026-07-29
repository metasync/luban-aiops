# SPEC-002 Plan: Platform-Owned Agent-Service Contract

> Finalized 2026-07-28 alongside spec approval; open questions resolved in the spec changelog.

## Approach

Work inside-out: define the contract schemas first (R-1), implement the adapter against them (R-2), migrate the gateway consumer (R-3), then remove the transitional surface (R-4). Contract tests (R-5) land alongside R-2 and R-3 so enforcement is continuous.

## Design Per Requirement

### R-1: Agent-service contract definition

- affected: `shared/shared-contracts/schemas/`
- new schema files: `agent-chat-request.schema.json`, `agent-chat-response.schema.json`, `agent-stream-event.schema.json`, `agent-session.schema.json`, `agent-runtime-metadata.schema.json`, `agent-health.schema.json`
- envelope simplification: the v2 chat response uses `{session_id, request_id, content, status}` — renaming `response` → `content` for clarity and aligning with streaming delta terminology; `status` enum stays `ok | partial | error`
- stream event simplification: `{type, session_id, request_id, delta}` with `type` enum `message_start | message_delta | message_end | error`; drop the freeform `payload` field (it leaked AgentScope internals)
- session schema: `{session_id, user_id, created_at, status}` — compatible with existing `session.schema.json` but adds `status` enum (`active | expired`)
- header conventions documented in a `README` section alongside schemas: `X-User-ID`, `x-request-id` are required request headers
- alternatives: keep v1 shapes verbatim — rejected; the `response` field name and freeform `payload` are the exact leaks ADR-0003 eliminates

### R-2: AgentScope adapter

- affected: new `agent_service/api/v2/` route package, `agent_service/services/contract_adapter.py`
- the adapter module owns: request validation (pydantic models bound to R-1 schemas), delegation to `AgentKernel`, response shaping into contract-conformant dicts
- routes: `POST /api/v2/chat`, `GET /api/v2/chat/stream`, `POST /api/v2/sessions`, `GET /api/v2/sessions/{id}`, `GET /api/v2/runtime`, `GET /health/ready`
- session semantics reuse the existing `SessionStore` and `SessionService` from SPEC-001 (TTL, ownership, eviction)
- streaming: the adapter consumes `AgentKernel.stream_events()` and re-emits only `agent-stream-event` conformant frames (no raw AgentScope event types cross the boundary)
- the existing `api/routes/` package (v1 transitional) is untouched until R-4
- alternatives: wrap the native AgentScope HTTP endpoints with a reverse proxy — rejected; still leaks framework types and couples to AgentScope's URL structure

### R-3: Gateway consumer migration

- affected: `api_gateway/services/agent_backends.py` (removed), `api_gateway/services/gateway_service.py`, `api_gateway/core/config.py`, `api_gateway/core/backend_context.py` (removed), gateway routes, overlay env files
- the gateway gains a single `AgentServiceClient` (thin httpx wrapper) targeting `{AGENT_SERVICE_URL}/api/v2/...`
- `GatewaySettings` drops: `agent_backend_mode`, `backend_resolution_ttl_seconds`; keeps `agent_service_url`, `chat_response_timeout_seconds`, `require_auth`, identity settings
- gateway pydantic models updated to align with v2 schemas (notably `content` replaces `response` in chat response)
- the resolution cache and dual-backend probe code are deleted entirely
- alternatives: keep the backend abstraction with a single implementation — rejected; the abstraction existed only to bridge two protocols; with one contract it adds indirection without value

### R-4: Transitional surface retirement

- affected: `agent_service/api/routes/` (v1 routes removed), `agent_service/app.py` (transitional bootstrap), `agent_service/entrypoints/transitional.py`, Dockerfile entrypoint reference
- the FastAPI app's router switches to mount only `/api/v2/` routes and health
- `entrypoints/transitional.py` is removed; `main.py` bootstraps the v2 app directly
- native entrypoints (`entrypoints/runtime.py`, `entrypoints/native.py`) remain untouched for AgentScope-native consumers
- the Dockerfile default entrypoint changes from the transitional app to the v2 app
- overlay `dev-k8s-transitional` keeps its name (it describes the overlay's history) but its config drops `AGENT_BACKEND_MODE`

### R-5: Contract enforcement and CI

- affected: `products/agent-platform/tests/`, `products/tool-gateway/tests/`
- agent-platform: new `test_contract_adapter.py` validating route responses against the JSON Schema files (using `jsonschema.validate`)
- tool-gateway: existing `test_contracts.py` updated to bind gateway models to v2 schemas
- CI unchanged structurally (same `ci.yml` matrix); both products' test suites enforce the contract

## Sequencing And Dependencies

1. R-1 schemas — no dependencies; everything builds on these
2. R-2 adapter + R-5 agent-platform tests — depends on 1
3. R-3 gateway migration + R-5 gateway tests — depends on 2 (needs the adapter running to validate against)
4. R-4 transitional removal — depends on 3 (gateway must be migrated first)

## Test Strategy

- unit tests: adapter routes return schema-valid responses; gateway client calls the right URLs
- contract tests: bidirectional — agent-platform validates its outputs, gateway validates its models, both against the same JSON Schema files
- regression: all SPEC-001 behaviors (auth enforcement, role logging, session integrity) have existing tests that must continue passing

## Rollout And Migration

- the v2 adapter and v1 transitional routes coexist inside agent-platform during development; R-4 removes v1 only after R-3 lands
- overlay changes are Git-diffable: `AGENT_BACKEND_MODE` removal is a single-line delete per overlay
- rollback: reverting the gateway to SPEC-001 code restores dual-backend behavior; the v1 routes exist until R-4 removes them, giving a narrow but real rollback window during development
- after delivery: the contract is the sole boundary; no rollback to dual-surface is possible or desired
