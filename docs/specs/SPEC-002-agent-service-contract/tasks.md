# SPEC-002 Tasks: Platform-Owned Agent-Service Contract

Task states: `[ ]` pending, `[x]` done. Implementation starts when the spec is `approved`.

## R-1: Agent-service contract definition

- [x] create `agent-chat-request.schema.json` in `shared/shared-contracts/schemas/`
- [x] create `agent-chat-response.schema.json` (simplified envelope: `content` replaces `response`)
- [x] create `agent-stream-event.schema.json` (simplified: `type | session_id | request_id | delta`; no freeform `payload`)
- [x] create `agent-session.schema.json` (adds `status` enum to existing session shape)
- [x] create `agent-runtime-metadata.schema.json`
- [x] create `agent-health.schema.json`
- [x] document header conventions (`X-User-ID`, `x-request-id`) in `shared/shared-contracts/README.md`

## R-2: AgentScope adapter in agent-platform

- [x] add pydantic request/response models in `agent_service/schemas/` bound to R-1 schemas
- [x] create `agent_service/services/contract_adapter.py` (delegation to `AgentKernel` + response shaping)
- [x] create `agent_service/api/v2/` route package: `POST /api/v2/chat`, `GET /api/v2/chat/stream`, `POST /api/v2/sessions`, `GET /api/v2/sessions/{id}`, `GET /api/v2/runtime`, `GET /health/ready`
- [x] wire v2 router into the FastAPI app alongside v1 (coexist during migration)
- [x] streaming adapter: consume `AgentKernel.stream_events()`, emit only `agent-stream-event` conformant SSE frames
- [x] verify session semantics (ownership, TTL, per-session isolation) carry through the adapter

## R-3: Gateway consumer migration

- [x] create `api_gateway/services/agent_client.py` (single httpx-based client targeting `/api/v2/`)
- [x] update gateway routes to use `AgentServiceClient` instead of backend resolution
- [x] update gateway pydantic models to v2 contract (`content` field, simplified stream events)
- [x] remove `api_gateway/services/agent_backends.py` (dual-backend classes, resolution cache, probe logic)
- [x] remove `api_gateway/core/backend_context.py`
- [x] remove `agent_backend_mode` and `backend_resolution_ttl_seconds` from `GatewaySettings`
- [x] remove `AGENT_BACKEND_MODE` and `BACKEND_RESOLUTION_TTL_SECONDS` from overlay `runtime-config.env` files
- [x] update gateway contract tests to bind to v2 schemas

## R-4: Transitional surface retirement

- [x] remove v1 routes (`agent_service/api/routes/`) and v1 router registration
- [x] remove or reduce `entrypoints/transitional.py`
- [x] update `main.py` / `app.py` to bootstrap the v2 app as the default entrypoint
- [x] update Dockerfile default entrypoint if it references the transitional app
- [x] update `agent-platform` README: document `/api/v2/` as the sole external interface

## R-5: Contract enforcement and CI

- [x] add `test_contract_adapter.py` in agent-platform: validate route responses against JSON Schema files
- [x] update `test_contracts.py` in tool-gateway: bind gateway models to v2 schemas
- [x] verify `ci.yml` passes for both products (no workflow changes expected)
- [x] confirm all SPEC-001 regression tests still pass (auth, roles, sessions)

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified
- [x] living state docs updated (root README, agent-platform README, tool-gateway README, CHANGELOG)
- [x] `CHANGELOG.md` entry added referencing `SPEC-002`
- [x] spec index in `docs/specs/README.md` updated
- [x] spec status set to `delivered`
