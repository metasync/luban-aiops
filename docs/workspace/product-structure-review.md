# Product Structure Review

This note captures the current implementation structure of each product in the workspace and recommends where structural normalization should happen next.

## Snapshot

### `products/agent-platform`

Current shape:

- `src/agent_service/app.py`
- `src/agent_service/main.py`
- `src/agent_service/api/`
- `src/agent_service/core/`
- `src/agent_service/entrypoints/`
- `src/agent_service/schemas/`
- `src/agent_service/services/`
- `src/agent_service/runtime_settings.py`
- `src/agent_service/runtime_kernel.py`
- `src/agent_service/providers/`
- `src/agent_service/agent_app.py`
- `src/agent_service/native_service.py`
- `tests/`

Assessment:

- most mature backend product so far
- now split into clear transitional HTTP adapter, runtime kernel, provider, and native entrypoint modules
- the transitional `FastAPI` surface now follows the same responsibility-oriented layering used by the other backend services
- cached runtime configuration and kernel wiring are now explicit instead of hidden behind module-global construction
- still intentionally dual-surface because it exposes both the current workspace HTTP contract and more native `AgentScope` entrypoints

Recommendation:

- keep the current structure
- preserve the distinction between:
  - `app.py`
    - transitional `FastAPI` adapter for the current gateway and portal contract
  - `entrypoints/transitional.py`
    - transitional runtime bootstrap
  - `entrypoints/runtime.py`
    - native `AgentScope` `AgentApp` entrypoint
  - `entrypoints/native.py`
    - native `AgentScope 2.0` service-factory entrypoint built with `create_app`
- keep `main.py`, `agent_app.py`, and `native_service.py` as compatibility wrappers so script targets and imports remain stable

### `products/tool-gateway`

Current shape:

- `src/tool_gateway/app.py`
- `src/tool_gateway/api/routes/`
- `src/tool_gateway/core/`
- `src/tool_gateway/services/`
- `src/tool_gateway/tools/`
- `tests/`

Assessment:

- now follows a pragmatic `FastAPI` service layout
- route modules are separated from config and backend orchestration
- structurally cleaner than the earlier single-file `main.py` form
- since SPEC-010 (ADR-0005) this product is the tool service only; the portal-facing edge moved to `platform-gateway`

Recommendation:

- use this package shape as the baseline for future `FastAPI`-oriented backend services
- split `services/agent_backends.py` further only when native and transitional integration logic becomes materially larger

### `products/platform-gateway`

Current shape:

- `src/platform_gateway/app.py`
- `src/platform_gateway/api/routes/`
- `src/platform_gateway/core/`
- `src/platform_gateway/services/`
- `tests/`

Assessment:

- extracted from the former combined `api_gateway` package by SPEC-010 (ADR-0005)
- keeps the same `FastAPI` service layout for the portal-facing edge: token verification, action policy, chat/session proxying, and the delegation client

Recommendation:

- keep it aligned with the `tool-gateway` layout so the two gateway products stay structurally parallel

### `products/identity-broker`

Current shape:

- `src/identity_service/app.py`
- `src/identity_service/api/routes/`
- `src/identity_service/core/`
- `src/identity_service/schemas/`
- `src/identity_service/services/`
- `tests/`

Assessment:

- now aligned with the same `FastAPI` service pattern as `tool-gateway`
- good fit because the service owns a narrow HTTP surface and simple normalization logic
- the new shape is still lightweight enough for the current implementation size

Recommendation:

- keep this as the standard small-service pattern
- only add downstream client packages if the service begins calling external identity systems directly rather than returning placeholder compositions

### `products/operator-portal`

Current shape:

- `web-ui/`
- `nginx.conf`
- `Dockerfile`

Assessment:

- intentionally different from backend products
- currently a static UI shell with an `nginx` reverse proxy boundary

Recommendation:

- do not force the backend layout convention onto this product
- document UI-specific structure separately if the portal evolves into a richer frontend application

### `products/policy-center`

Current shape:

- `README.md`

Assessment:

- still a placeholder boundary

Recommendation:

- when implementation starts, use the same backend layout convention as `identity-broker` unless policy evaluation requires a materially different engine-oriented package split

### `products/skills-hub`

Current shape:

- `README.md`

Assessment:

- still a placeholder boundary

Recommendation:

- start with the same backend layout convention, then carve out specialized retrieval, catalog, or indexing modules as needed

### `products/execution-runtime`

Current shape:

- `README.md`

Assessment:

- still a placeholder boundary

Recommendation:

- likely needs the same backend layout at the HTTP/control edge, plus a separate execution adapter package once bounded-action runners are introduced

## Cross-Product Observations

- backend products are converging into two practical categories:
  - runtime-centric services with specialized internal modules, such as `agent-platform`
  - request/response services with clear `FastAPI` layering, such as `platform-gateway`, `tool-gateway`, and `identity-broker`
- `agent-platform` is now cleaner because its transitional HTTP adapter follows the same layering discipline without flattening its native runtime concerns into a generic service layout
- `operator-portal` should remain separate from backend layout conventions because its implementation style is inherently frontend-oriented
- placeholder products should not be over-structured until they acquire real runtime behavior

## Recommended Structural Baseline

Use these defaults going forward:

- `agent-platform`
  - keep its current runtime-first structure with a layered transitional HTTP adapter
- `tool-gateway`
  - treat as the reference pattern for `FastAPI` service organization
- `platform-gateway`
  - keep structurally parallel to `tool-gateway` (same layout, edge-scoped routes/services)
- `identity-broker`
  - mirror the same pattern at smaller scale
- future backend products
  - start from the `tool-gateway` and `identity-broker` layout unless they have a runtime or engine boundary that justifies a different split
