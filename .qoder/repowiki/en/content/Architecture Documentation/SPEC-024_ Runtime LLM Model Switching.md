# SPEC-024: Runtime LLM Model Switching

<cite>
**Referenced Files in This Document**
- [spec.md](file://docs/specs/SPEC-024-runtime-llm-model-switching/spec.md)
- [plan.md](file://docs/specs/SPEC-024-runtime-llm-model-switching/plan.md)
- [tasks.md](file://docs/specs/SPEC-024-runtime-llm-model-switching/tasks.md)
- [model_catalog.py](file://products/agent-platform/src/agent_service/services/model_catalog.py)
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [api.py](file://products/agent-platform/src/agent_service/schemas/api.py)
- [runtime_settings.py](file://products/agent-platform/src/agent_service/runtime_settings.py)
- [registry.py](file://products/agent-platform/src/agent_service/providers/registry.py)
</cite>

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Dependency Analysis](#dependency-analysis)
7. [Performance Considerations](#performance-considerations)
8. [Troubleshooting Guide](#troubleshooting-guide)
9. [Conclusion](#conclusion)
10. [Appendices](#appendices)

## Introduction
SPEC-024 enables runtime selection of the LLM model per session through a portal dropdown, backed by a credential-gated model catalog and per-session affinity. The agent-platform exposes a discovery endpoint for available models, pins the chosen model on the session record, rebuilds the kernel agent when the model changes without losing conversation memory, and enriches audit events with the resolved model. The platform-gateway relays model discovery and chat requests with optional model fields, while the operator-portal renders a selector sourced from the catalog.

Key outcomes:
- Operators can compare models or recover from provider outages without redeploying.
- Selection is audited and gated by credentials; unknown models fail closed.
- Per-session affinity survives restarts and integrates with existing HITL and policy flows.

**Section sources**
- [spec.md:12-37](file://docs/specs/SPEC-024-runtime-llm-model-switching/spec.md#L12-L37)
- [plan.md:10-167](file://docs/specs/SPEC-024-runtime-llm-model-switching/plan.md#L10-L167)
- [tasks.md:6-35](file://docs/specs/SPEC-024-runtime-llm-model-switching/tasks.md#L6-L35)

## Project Structure
The implementation spans three layers:
- Agent-platform services and kernel: catalog construction, kernel model binding, session affinity, and stream enrichment.
- Platform-gateway: pass-through routes for model discovery and chat with optional model fields, plus policy enforcement.
- Operator-portal: UI selector driven by the catalog discovery endpoint.

```mermaid
graph TB
Portal["Operator Portal<br/>Model Selector"] --> Gateway["Platform Gateway<br/>/api/v1/models, /api/v1/chat"]
Gateway --> AgentService["Agent Platform<br/>/api/v2/models, /api/v2/chat"]
AgentService --> Catalog["Model Catalog<br/>Credential-gated entries"]
AgentService --> Kernel["RuntimeKernel<br/>ensure_agent + _build_model"]
Kernel --> Providers["Provider Registry<br/>dashscope/deepseek/openai"]
AgentService --> SessionStore["Session Store<br/>SessionRecord.model"]
AgentService --> Audit["Audit Tee<br/>chat_started/completed"]
```

**Diagram sources**
- [model_catalog.py:1-142](file://products/agent-platform/src/agent_service/services/model_catalog.py#L1-L142)
- [runtime_kernel.py:216-243](file://products/agent-platform/src/agent_service/runtime_kernel.py#L216-L243)
- [registry.py:1-28](file://products/agent-platform/src/agent_service/providers/registry.py#L1-L28)
- [api.py:8-21](file://products/agent-platform/src/agent_service/schemas/api.py#L8-L21)

**Section sources**
- [plan.md:77-127](file://docs/specs/SPEC-024-runtime-llm-model-switching/plan.md#L77-L127)
- [tasks.md:12-29](file://docs/specs/SPEC-024-runtime-llm-model-switching/tasks.md#L12-L29)

## Core Components
- Credential-gated model catalog: Builds a startup-time list of selectable models from environment variables per provider, dropping entries without API keys and flagging the deploy-time default.
- Runtime kernel model selection: Resolves the effective model per turn (request > pinned > default), rebuilds the agent on switch, and restores persisted agent state to preserve conversation history.
- Session affinity: Persists the selected model id on the session record so it survives restarts and is visible in session detail.
- Discovery contract: Exposes a read-only catalog via agent-platform and relays it through the gateway with policy gating.
- Audit enrichment: Records the resolved model in chat_started and chat_completed audit payloads without introducing new event types.

**Section sources**
- [model_catalog.py:38-142](file://products/agent-platform/src/agent_service/services/model_catalog.py#L38-L142)
- [runtime_kernel.py:216-243](file://products/agent-platform/src/agent_service/runtime_kernel.py#L216-L243)
- [runtime_kernel.py:511-614](file://products/agent-platform/src/agent_service/runtime_kernel.py#L511-L614)
- [api.py:8-21](file://products/agent-platform/src/agent_service/schemas/api.py#L8-L21)
- [plan.md:105-127](file://docs/specs/SPEC-024-runtime-llm-model-switching/plan.md#L105-L127)

## Architecture Overview
The runtime switching flow ensures safe, auditable, and persistent model selection per session.

```mermaid
sequenceDiagram
participant Client as "Portal"
participant Gateway as "Platform Gateway"
participant Agent as "Agent Platform"
participant Catalog as "Model Catalog"
participant Kernel as "RuntimeKernel"
participant Store as "Session Store"
participant Audit as "Audit Tee"
Client->>Gateway : GET /api/v1/models
Gateway->>Agent : GET /api/v2/models
Agent->>Catalog : public_models()
Catalog-->>Agent : {models, default}
Agent-->>Gateway : {models, default}
Gateway-->>Client : {models, default}
Client->>Gateway : POST /api/v1/chat {message, session_id, model?}
Gateway->>Agent : POST /api/v2/chat {message, session_id, model?}
Agent->>Store : pin model if changed
Agent->>Kernel : ensure_agent(session_id, bearer_token, model_id?)
Kernel->>Catalog : get(model_id?)
alt Unknown model
Catalog-->>Kernel : None
Kernel-->>Agent : UnknownModelError
Agent-->>Gateway : 4xx error
Gateway-->>Client : 4xx error
else Valid model
Catalog-->>Kernel : Entry
Kernel->>Kernel : _build_model(entry)
Kernel-->>Agent : Agent bound to model
Agent-->>Gateway : Streamed response
Gateway-->>Client : SSE frames
Agent->>Audit : chat_started/completed with model
end
```

**Diagram sources**
- [model_catalog.py:113-142](file://products/agent-platform/src/agent_service/services/model_catalog.py#L113-L142)
- [runtime_kernel.py:216-243](file://products/agent-platform/src/agent_service/runtime_kernel.py#L216-L243)
- [runtime_kernel.py:547-614](file://products/agent-platform/src/agent_service/runtime_kernel.py#L547-L614)
- [plan.md:92-117](file://docs/specs/SPEC-024-runtime-llm-model-switching/plan.md#L92-L117)

## Detailed Component Analysis

### Model Catalog
Responsibilities:
- Derive entries from per-provider environment variables, falling back to active profile settings for the current provider.
- Drop entries without an API key; mark the active profile’s entry as default.
- Provide a discovery-safe view that excludes credentials and base URLs.

Key behaviors:
- Entries are keyed by provider name; labels carry the resolved model name for display.
- A zero-entry catalog is allowed and degrades gracefully.

```mermaid
flowchart TD
Start(["Startup"]) --> ForEach["For each supported provider"]
ForEach --> Resolve["Resolve API key, model name, base URL"]
Resolve --> KeyPresent{"API key present?"}
KeyPresent --> |No| Skip["Skip entry"]
KeyPresent --> |Yes| Build["Build ModelCatalogEntry"]
Build --> DefaultCheck{"Is active profile provider?"}
DefaultCheck --> |Yes| MarkDefault["Mark default=True"]
DefaultCheck --> |No| Keep["Keep default=False"]
MarkDefault --> Collect["Collect entry"]
Keep --> Collect
Collect --> Next{"More providers?"}
Next --> |Yes| ForEach
Next --> |No| End(["Return tuple of entries"])
```

**Diagram sources**
- [model_catalog.py:68-110](file://products/agent-platform/src/agent_service/services/model_catalog.py#L68-L110)

**Section sources**
- [model_catalog.py:1-142](file://products/agent-platform/src/agent_service/services/model_catalog.py#L1-L142)
- [plan.md:12-41](file://docs/specs/SPEC-024-runtime-llm-model-switching/plan.md#L12-L41)

### Runtime Kernel Model Binding
Responsibilities:
- Resolve effective model per turn using request > pinned > default order.
- Rebuild the agent when the model changes, restoring persisted agent state to keep conversation history intact.
- Fail closed on unknown model ids with a structured error.

Key behaviors:
- Cache tracks the bound model id per session; mismatch triggers eviction and rebuild.
- Provider adapters remain unchanged; settings are replaced via dataclass replacement.

```mermaid
sequenceDiagram
participant Route as "Chat Route"
participant Kernel as "RuntimeKernel.ensure_agent"
participant Catalog as "Model Catalog"
participant Builder as "_build_model"
participant Provider as "Provider"
Route->>Kernel : ensure_agent(session_id, bearer_token, model_id?)
alt Cached agent exists
Kernel->>Kernel : Compare cached model_id vs bound model_id
alt Mismatch
Kernel->>Kernel : Evict cache
Kernel->>Builder : _build_model(model_id)
else Match
Kernel-->>Route : Return cached agent
end
else No cache or evicted
Kernel->>Builder : _build_model(model_id)
Builder->>Catalog : get(model_id)
alt Unknown
Catalog-->>Builder : None
Builder-->>Kernel : UnknownModelError
Kernel-->>Route : Error
else Known
Catalog-->>Builder : Entry
Builder->>Provider : build_model(replaced settings)
Provider-->>Builder : Model instance
Builder-->>Kernel : Model
Kernel-->>Route : New agent bound to model
end
end
```

**Diagram sources**
- [runtime_kernel.py:511-614](file://products/agent-platform/src/agent_service/runtime_kernel.py#L511-L614)
- [runtime_kernel.py:216-243](file://products/agent-platform/src/agent_service/runtime_kernel.py#L216-L243)
- [model_catalog.py:113-142](file://products/agent-platform/src/agent_service/services/model_catalog.py#L113-L142)

**Section sources**
- [runtime_kernel.py:216-243](file://products/agent-platform/src/agent_service/runtime_kernel.py#L216-L243)
- [runtime_kernel.py:547-614](file://products/agent-platform/src/agent_service/runtime_kernel.py#L547-L614)
- [plan.md:43-63](file://docs/specs/SPEC-024-runtime-llm-model-switching/plan.md#L43-L63)

### Session Affinity and Schema
Responsibilities:
- Persist the selected model id on the session record for durability across restarts.
- Expose the pinned model additively in session detail responses.

Key behaviors:
- Additive schema change; legacy records remain readable.
- Pinning occurs at turn start and is idempotent per value.

```mermaid
classDiagram
class SessionRecord {
+string session_id
+string user_id
+datetime created_at
+string status
+string title
+datetime last_active_at
+string model
}
```

**Diagram sources**
- [api.py:8-21](file://products/agent-platform/src/agent_service/schemas/api.py#L8-L21)

**Section sources**
- [api.py:8-21](file://products/agent-platform/src/agent_service/schemas/api.py#L8-L21)
- [plan.md:64-76](file://docs/specs/SPEC-024-runtime-llm-model-switching/plan.md#L64-L76)

### Provider Resolution and Settings
Responsibilities:
- Define supported providers and validate configuration at startup.
- Provide default provider options and resolve model names/base URLs.

Key behaviors:
- Strict validation of provider choices and related knobs.
- Fallback to AGENTSCOPE_* settings for the active profile provider.

**Section sources**
- [runtime_settings.py:32-35](file://products/agent-platform/src/agent_service/runtime_settings.py#L32-L35)
- [runtime_settings.py:113-158](file://products/agent-platform/src/agent_service/runtime_settings.py#L113-L158)
- [runtime_settings.py:279-349](file://products/agent-platform/src/agent_service/runtime_settings.py#L279-L349)
- [registry.py:1-28](file://products/agent-platform/src/agent_service/providers/registry.py#L1-L28)

## Dependency Analysis
The runtime switching feature introduces minimal coupling:
- Catalog depends on runtime settings and provider registry to construct entries.
- Kernel depends on catalog for validation and on provider registry to build models.
- Schemas extend session records additively; no breaking changes.
- Gateway routes relay model fields verbatim, preserving upstream error posture.

```mermaid
graph LR
Settings["RuntimeSettings"] --> Catalog["Model Catalog"]
Registry["Provider Registry"] --> Catalog
Catalog --> Kernel["RuntimeKernel"]
Kernel --> Registry
Kernel --> Store["Session Store"]
Store --> Schemas["SessionRecord.schema"]
```

**Diagram sources**
- [model_catalog.py:24-35](file://products/agent-platform/src/agent_service/services/model_catalog.py#L24-L35)
- [runtime_kernel.py:8-25](file://products/agent-platform/src/agent_service/runtime_kernel.py#L8-L25)
- [registry.py:1-28](file://products/agent-platform/src/agent_service/providers/registry.py#L1-L28)
- [api.py:8-21](file://products/agent-platform/src/agent_service/schemas/api.py#L8-L21)

**Section sources**
- [plan.md:77-117](file://docs/specs/SPEC-024-runtime-llm-model-switching/plan.md#L77-L117)
- [tasks.md:12-23](file://docs/specs/SPEC-024-runtime-llm-model-switching/tasks.md#L12-L23)

## Performance Considerations
- Model catalog is built once at startup; lookup is O(1) per id.
- Kernel agent cache is bounded; model switch triggers controlled rebuild with state restore.
- Stream tee captures message_end.model without additional passes over the stream.
- No per-turn parameter tuning surfaces; provider options remain deploy-time to avoid runtime overhead.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and resolutions:
- Unknown model id: The kernel rejects unknown ids early; routes map to 4xx errors. Verify the model id against the catalog discovery endpoint.
- Missing credentials: Entries without API keys are excluded from the catalog; ensure provider-specific keys are set.
- Session stuck with parked HITL confirmation: Model changes are refused with 409 until the confirmation resolves.
- Audit missing model: Ensure stream tee captures message_end.model and that chat_started includes the requested model.

Operational checks:
- Validate catalog exposure via GET /api/v2/models and gateway passthrough GET /api/v1/models.
- Confirm session detail includes the pinned model after a turn.
- Inspect audit events for chat_started and chat_completed to verify model attribution.

**Section sources**
- [runtime_kernel.py:31-37](file://products/agent-platform/src/agent_service/runtime_kernel.py#L31-L37)
- [runtime_kernel.py:735-761](file://products/agent-platform/src/agent_service/runtime_kernel.py#L735-L761)
- [plan.md:92-117](file://docs/specs/SPEC-024-runtime-llm-model-switching/plan.md#L92-L117)

## Conclusion
SPEC-024 delivers runtime LLM model switching with strong safety guarantees: credential gating, fail-closed validation, per-session affinity, and audited selection. The design leverages existing provider adapters, session stores, and audit infrastructure, minimizing risk while enabling operators to compare models and respond to provider issues without redeployment.

[No sources needed since this section summarizes without analyzing specific files]

## Appendices
- Contract updates:
  - New model catalog schema under shared contracts.
  - Additive model field on chat request/response and session detail.
  - Additive model field on stream message_end frames.
- Deployment notes:
  - Active deepseek profile remains the default via existing AGENTSCOPE_* knobs.
  - Additional providers enabled via per-provider environment variables.

**Section sources**
- [plan.md:77-141](file://docs/specs/SPEC-024-runtime-llm-model-switching/plan.md#L77-L141)
- [tasks.md:12-35](file://docs/specs/SPEC-024-runtime-llm-model-switching/tasks.md#L12-L35)