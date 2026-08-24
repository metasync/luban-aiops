# Agent Platform Service

<cite>
**Referenced Files in This Document**
- [main.py](file://products/agent-platform/src/agent_service/main.py)
- [app.py](file://products/agent-platform/src/agent_service/app.py)
- [agent_app.py](file://products/agent-platform/src/agent_service/agent_app.py)
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [runtime_settings.py](file://products/agent-platform/src/agent_service/runtime_settings.py)
- [config.py](file://products/agent-platform/src/agent_service/core/config.py)
- [env.py](file://products/agent-platform/src/agent_service/core/env.py)
- [metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [observability.py](file://products/agent-platform/src/agent_service/core/observability.py)
- [telemetry.py](file://products/agent-platform/src/agent_service/core/telemetry.py)
- [request_context.py](file://products/agent-platform/src/agent_service/core/request_context.py)
- [routes.py](file://products/agent-platform/src/agent_service/api/v2/routes.py)
- [api.py](file://products/agent-platform/src/agent_service/schemas/api.py)
- [v2.py](file://products/agent-platform/src/agent_service/schemas/v2.py)
- [base.py](file://products/agent-platform/src/agent_service/providers/base.py)
- [openai.py](file://products/agent-platform/src/agent_service/providers/openai.py)
- [dashscope.py](file://products/agent-platform/src/agent_service/providers/dashscope.py)
- [deepseek.py](file://products/agent-platform/src/agent_service/providers/deepseek.py)
- [luban.py](file://products/agent-platform/src/agent_service/providers/luban.py)
- [registry.py](file://products/agent-platform/src/agent_service/providers/registry.py)
- [session_service.py](file://products/agent-platform/src/agent_service/services/session_service.py)
- [session_store.py](file://products/agent-platform/src/agent_service/services/session_store.py)
- [session_transcript.py](file://products/agent-platform/src/agent_service/services/session_transcript.py)
- [hitl_confirmations.py](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py)
- [evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [model_catalog.py](file://products/agent-platform/src/agent_service/services/model_catalog.py)
- [model_discovery.py](file://products/agent-platform/src/agent_service/services/model_discovery.py)
- [runtime_service.py](file://products/agent-platform/src/agent_service/services/runtime_service.py)
- [runtime_dependencies.py](file://products/agent-platform/src/agent_service/services/runtime_dependencies.py)
- [gateway_tools.py](file://products/agent-platform/src/agent_service/tools/gateway_tools.py)
- [models.py](file://products/platform-gateway/src/platform_gateway/api/routes/models.py)
- [gateway_service.py](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py)
- [ModelSelect.tsx](file://products/operator-portal/web-ui/app/src/chat/ModelSelect.tsx)
- [models.ts](file://products/operator-portal/web-ui/app/src/api/models.ts)
- [chat.py](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py)
- [test_chat_stream_modality.py](file://products/agent-platform/tests/test_chat_stream_modality.py)
- [test_evidence_store.py](file://products/agent-platform/tests/test_evidence_store.py)
- [test_model_catalog.py](file://products/agent-platform/tests/test_model_catalog.py)
- [test_model_discovery.py](file://products/agent-platform/tests/test_model_discovery.py)
- [test_model_switching.py](file://products/agent-platform/tests/test_model_switching.py)
- [session-evidence.schema.json](file://shared/shared-contracts/schemas/session-evidence.schema.json)
- [model-catalog.schema.json](file://shared/shared-contracts/schemas/model-catalog.schema.json)
- [pyproject.toml](file://products/agent-platform/pyproject.toml)
- [Dockerfile](file://products/agent-platform/Dockerfile)
- [README.md](file://products/agent-platform/README.md)
</cite>

## Update Summary
**Changes Made**
- Added comprehensive multi-model runtime capability with per-turn model selection and session-based model pinning
- Implemented new `/api/v2/models` endpoint for credential-safe model catalog enumeration
- Enhanced model resolution with fallback ladder system (request > pinned > default)
- Integrated live model discovery service with background task management and fail-soft caching
- Added persistent model pinning storage across all session store backends (memory, Redis, Postgres)
- Enhanced error handling for model resolution failures with proper 422 status codes
- Updated API endpoints to support per-turn model selection with validation and normalization
- Added support for the new luban provider with OpenAI-compatible self-hosted endpoints

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Multi-Session Operator Workspace](#multi-session-operator-workspace)
7. [Session Store Enhancements](#session-store-enhancements)
8. [Transcript Extraction Service](#transcript-extraction-service)
9. [HITL Confirmation Registry Integration](#hitl-confirmation-registry-integration)
10. [Enhanced Streaming Architecture](#enhanced-streaming-architecture)
11. [Voice Readiness Support](#voice-readiness-support)
12. [Per-Request Trace Queues](#per-request-trace-queues)
13. [Delegated Token Management](#delegated-token-management)
14. [Evidence Store Service](#evidence-store-service)
15. [Model Catalog Service](#model-catalog-service)
16. [Live Model Discovery Service](#live-model-discovery-service)
17. [Multi-Model Runtime Capability](#multi-model-runtime-capability)
18. [Dependency Analysis](#dependency-analysis)
19. [Performance Considerations](#performance-considerations)
20. [Troubleshooting Guide](#troubleshooting-guide)
21. [Conclusion](#conclusion)
22. [Appendices](#appendices)

## Introduction
The Agent Platform Service is the core orchestration engine of the Luban AIOps Platform. It provides a runtime kernel for agent execution, a provider registry for multi-model backends (OpenAI, DashScope, DeepSeek, and Luban), and robust session management with durable storage. The service exposes REST APIs for agent interactions, streaming responses, and configuration management, enabling scalable and observable AI operations across diverse model providers.

**Updated** The service now includes comprehensive multi-model runtime capability with per-turn model selection, session-based model pinning, and credential-gated model catalogs. The enhanced architecture supports dynamic model switching at runtime through a sophisticated resolution system that prioritizes explicit requests over pinned sessions, falling back to defaults when needed. Live model discovery runs as background tasks with fail-soft caching to ensure continuous availability even during provider outages. The addition of the Luban provider enables self-hosted OpenAI-compatible endpoints such as Ollama, vLLM, and llama.cpp servers.

## Project Structure
The Agent Platform Service is implemented as a Python FastAPI application organized by feature layers:
- Entrypoints and application bootstrapping with lifespan management
- API routes and request/response schemas
- Runtime kernel and settings with model discovery integration
- Provider implementations and registry with filtering capabilities
- Session services and stores with model pinning support
- Evidence store service with dual backend support
- Model catalog service with live discovery capabilities
- Background task management for model discovery
- Tools and integrations
- Core cross-cutting concerns (configuration, observability, metrics, telemetry, request context)

```mermaid
graph TB
subgraph "Entrypoints"
main["main.py"]
app["app.py"]
agent_app["agent_app.py"]
end
subgraph "API"
routes_v2["api/v2/routes.py"]
schema_api["schemas/api.py"]
schema_v2["schemas/v2.py"]
end
subgraph "Runtime"
kernel["runtime_kernel.py"]
settings["runtime_settings.py"]
config["core/config.py"]
env["core/env.py"]
end
subgraph "Providers"
base_prov["providers/base.py"]
openai["providers/openai.py"]
dashscope["providers/dashscope.py"]
deepseek["providers/deepseek.py"]
luban["providers/luban.py"]
reg["providers/registry.py"]
end
subgraph "Sessions"
sess_svc["services/session_service.py"]
sess_store["services/session_store.py"]
sess_transcript["services/session_transcript.py"]
hitl_reg["services/hitl_confirmations.py"]
end
subgraph "Evidence Store"
ev_store["services/evidence_store.py"]
ev_schema["schemas/session-evidence.schema.json"]
end
subgraph "Model Catalog"
model_cat["services/model_catalog.py"]
model_disc["services/model_discovery.py"]
model_schema["schemas/model-catalog.schema.json"]
end
subgraph "Background Tasks"
lifespan["FastAPI Lifespan"]
task_mgr["Task Manager"]
end
subgraph "Tools"
gw_tools["tools/gateway_tools.py"]
end
subgraph "Cross-Cutting"
metrics["core/metrics.py"]
obs["core/observability.py"]
tel["core/telemetry.py"]
ctx["core/request_context.py"]
end
main --> app --> agent_app
app --> lifespan
lifespan --> task_mgr
task_mgr --> model_disc
agent_app --> routes_v2
routes_v2 --> kernel
kernel --> reg
reg --> base_prov
reg --> openai
reg --> dashscope
reg --> deepseek
reg --> luban
kernel --> sess_svc
sess_svc --> sess_store
sess_svc --> sess_transcript
routes_v2 --> hitl_reg
kernel --> gw_tools
kernel --> ev_store
kernel --> model_cat
model_disc --> model_cat
ev_store --> metrics
model_cat --> metrics
model_disc --> metrics
app --> metrics
app --> obs
app --> tel
app --> ctx
kernel --> config
kernel --> settings
settings --> env
```

**Diagram sources**
- [main.py](file://products/agent-platform/src/agent_service/main.py)
- [app.py](file://products/agent-platform/src/agent_service/app.py)
- [agent_app.py](file://products/agent-platform/src/agent_service/agent_app.py)
- [routes.py](file://products/agent-platform/src/agent_service/api/v2/routes.py)
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [runtime_settings.py](file://products/agent-platform/src/agent_service/runtime_settings.py)
- [config.py](file://products/agent-platform/src/agent_service/core/config.py)
- [env.py](file://products/agent-platform/src/agent_service/core/env.py)
- [base.py](file://products/agent-platform/src/agent_service/providers/base.py)
- [openai.py](file://products/agent-platform/src/agent_service/providers/openai.py)
- [dashscope.py](file://products/agent-platform/src/agent_service/providers/dashscope.py)
- [deepseek.py](file://products/agent-platform/src/agent_service/providers/deepseek.py)
- [luban.py](file://products/agent-platform/src/agent_service/providers/luban.py)
- [registry.py](file://products/agent-platform/src/agent_service/providers/registry.py)
- [session_service.py](file://products/agent-platform/src/agent_service/services/session_service.py)
- [session_store.py](file://products/agent-platform/src/agent_service/services/session_store.py)
- [session_transcript.py](file://products/agent-platform/src/agent_service/services/session_transcript.py)
- [hitl_confirmations.py](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py)
- [evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [model_catalog.py](file://products/agent-platform/src/agent_service/services/model_catalog.py)
- [model_discovery.py](file://products/agent-platform/src/agent_service/services/model_discovery.py)
- [gateway_tools.py](file://products/agent-platform/src/agent_service/tools/gateway_tools.py)
- [metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [observability.py](file://products/agent-platform/src/agent_service/core/observability.py)
- [telemetry.py](file://products/agent-platform/src/agent_service/core/telemetry.py)
- [request_context.py](file://products/agent-platform/src/agent_service/core/request_context.py)

**Section sources**
- [README.md](file://products/agent-platform/README.md)
- [pyproject.toml](file://products/agent-platform/pyproject.toml)
- [Dockerfile](file://products/agent-platform/Dockerfile)

## Core Components
- Runtime Kernel: Orchestrates agent lifecycle, conversation state, tool invocation, and provider dispatch with enhanced AgentScope 2.x toolkit registration, anti-hallucination guards, and model normalization support.
- Provider Registry: Discovers and manages model providers (OpenAI, DashScope, DeepSeek, Luban) with pluggable interfaces using new AgentScope 2.x model construction patterns.
- Session Management: Persists and restores conversations with durable storage, multi-session workspace support, and concurrency-safe access with model pinning.
- Evidence Store: Provides persistent storage for tool execution evidence with dual backend support and size-capped retention policies.
- Model Catalog: Manages credential-gated model discovery with multi-provider support, legacy alias resolution, and public schema compliance.
- Live Model Discovery: Implements background task management with periodic refresh cycles, provider filtering, and atomic catalog updates.
- **Multi-Model Runtime**: Provides per-turn model selection with session-based pinning and sophisticated resolution hierarchy.
- API Layer: Exposes REST endpoints for chat, sessions, streaming events, model discovery, and health checks with v3 streaming protocol support.
- Cross-Cutting: Configuration, environment, metrics, observability, telemetry, and request-scoped context.

Key responsibilities:
- Lifecycle: Initialize, start, run, and shutdown agents safely with AgentScope 2.x compatibility.
- Conversation: Maintain message history, context, and state per session with workspace organization.
- Evidence Capture: Persist tool_call and tool_result frames with size caps and automatic eviction.
- Model Resolution: Normalize model IDs including legacy provider name aliases to concrete model entries.
- **Multi-Model Selection**: Resolve models through priority hierarchy (explicit request > pinned session > default).
- **Session Pinning**: Persist model selections per session with TTL-aware storage across all backends.
- **Live Discovery**: Periodically discover available models from providers with fail-soft fallback ladder and provider-specific filtering.
- **Background Tasks**: Manage model discovery lifecycle through FastAPI lifespan context with proper startup/shutdown handling.
- **Atomic Updates**: Swap catalog contents atomically to prevent partial updates during refresh cycles.
- Streaming: Emit incremental events to clients over HTTP streaming with v3 tool_call/tool_result frames.
- Security: Manage per-user toolkit closures bound to delegated tokens for secure tool execution.
- Anti-Hallucination: Prevent model fabrication through systematic NO_TOOLS_NOTICE injection.
- Auto-Approval: Pre-approve vetted read-only tools to prevent headless stream stalls while maintaining security.
- Voice Readiness: Support both text and voice input modalities with consistent policy enforcement and HITL workflows.
- Workspace Management: Provide multi-session operator workspace with session listing, detail views, and owner-only deletion.
- Transcript Reconstruction: Extract conversation history from kernel state snapshots for workspace UIs.
- HITL Integration: Support human-in-the-loop workflows with parked confirmation management.
- Observability: Emit structured logs, metrics, and traces for each operation with per-request audit trails.

**Updated** The service now includes comprehensive multi-model runtime capability with per-turn model selection, session-based model pinning, credential-gated model catalogs, live model discovery with background task management, sophisticated error handling for model resolution failures, and enhanced operational visibility through detailed logging and metrics collection. The addition of the Luban provider enables self-hosted OpenAI-compatible endpoints with bearer token authentication.

**Section sources**
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [registry.py](file://products/agent-platform/src/agent_service/providers/registry.py)
- [session_service.py](file://products/agent-platform/src/agent_service/services/session_service.py)
- [routes.py](file://products/agent-platform/src/agent_service/api/v2/routes.py)
- [evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [model_catalog.py](file://products/agent-platform/src/agent_service/services/model_catalog.py)
- [model_discovery.py](file://products/agent-platform/src/agent_service/services/model_discovery.py)
- [app.py](file://products/agent-platform/src/agent_service/app.py)
- [metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [observability.py](file://products/agent-platform/src/agent_service/core/observability.py)
- [telemetry.py](file://products/agent-platform/src/agent_service/core/telemetry.py)
- [request_context.py](file://products/agent-platform/src/agent_service/core/request_context.py)

## Architecture Overview
The service follows a layered architecture with enhanced security and anti-hallucination features:
- API layer receives requests, validates payloads, and delegates to the runtime kernel with v3 streaming support, session workspace operations, and voice-readiness parity.
- Runtime kernel coordinates sessions, tools, and provider selection via the registry with AgentScope 2.x toolkit registration, evidence capture, and model normalization.
- Providers implement standardized interfaces to communicate with external model APIs using new model construction patterns.
- Session service persists state using a configurable store with workspace bookkeeping and transcript extraction.
- Evidence store provides persistent storage for tool execution evidence with dual backend support and size-capped retention.
- Model catalog provides credential-gated discovery of available models with legacy alias resolution.
- **Multi-model runtime resolves per-turn model selection through priority hierarchy with session-based pinning.**
- **Live discovery service runs background tasks to periodically refresh model catalogs with fail-soft fallback ladder.**
- **FastAPI lifespan manages discovery task lifecycle with proper startup and shutdown handling.**
- Cross-cutting modules provide configuration, metrics, observability, and telemetry with per-request audit trails.

```mermaid
sequenceDiagram
participant Client as "Client"
participant Gateway as "Platform Gateway"
participant API as "FastAPI Routes"
participant Kernel as "RuntimeKernel"
participant Sess as "SessionService"
participant Store as "SessionStore"
participant EvStore as "EvidenceStore"
participant ModelCat as "ModelCatalog"
participant Disc as "ModelDiscovery"
participant Reg as "ProviderRegistry"
participant Prov as "ModelProvider"
participant Tools as "GatewayTools"
participant Transcript as "TranscriptExtractor"
participant HITL as "ConfirmationRegistry"
participant Trace as "TraceQueue"
Note over Client,HITL : Multi-Model Chat with Per-Turn Selection
Client->>Gateway : POST /api/v1/chat {message, model, input_modality}
Gateway->>API : Forward with model and input_modality metadata
API->>Sess : ensure_session(sessionId, user_id)
API->>API : _resolve_model(requested, pinned)
alt Explicit model requested
API->>ModelCat : validate model_id exists
ModelCat-->>API : model entry or 422 error
else Pinned model valid
API->>ModelCat : get(pinned)
ModelCat-->>API : pinned model or None
else Fallback to default
API->>ModelCat : default_entry()
ModelCat-->>API : default model
end
API->>Sess : pin_session_model(sessionId, resolved)
API->>Sess : mark_session_turn(sessionId, message)
Sess->>Store : set_session_title + touch_session + set_model
Sess-->>API : session updated
API->>Kernel : execute(message, sessionId, bearerToken, model_id)
Kernel->>Kernel : normalize_model_id(model_id)
Kernel->>Reg : resolveProvider(providerName)
Reg-->>Kernel : Provider instance
Kernel->>Tools : build_gateway_toolkit(definitions, bearerToken, traceQueue)
Tools-->>Kernel : toolkit with v3 tool_call/tool_result support
Kernel->>Prov : streamChat(messages, options, toolkit)
Prov-->>Kernel : StreamEvent* + tool_call/tool_result frames
Kernel->>EvStore : save_turn(frames, session_max_bytes)
EvStore-->>Kernel : evidence persisted
Kernel->>Trace : emit trace events
Trace-->>Kernel : audit trail data
Kernel-->>API : StreamEvent* with v3 frames
API-->>Client : SSE/Streaming Response with tool_call/tool_result
Kernel->>Sess : save(sessionId, updatedState)
Sess->>Store : set(sessionId, updatedState)
Note over Disc : Background Task Management
Disc->>Disc : refresh_once() every N seconds
Disc->>ModelCat : refresh_catalog(series_map)
ModelCat-->>Disc : atomic catalog swap
```

**Updated** The sequence diagram now shows the complete multi-model runtime capability with per-turn model selection, session-based model pinning, credential-gated validation, and the full model resolution hierarchy (request > pinned > default).

**Diagram sources**
- [routes.py](file://products/agent-platform/src/agent_service/api/v2/routes.py)
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [session_service.py](file://products/agent-platform/src/agent_service/services/session_service.py)
- [session_store.py](file://products/agent-platform/src/agent_service/services/session_store.py)
- [session_transcript.py](file://products/agent-platform/src/agent_service/services/session_transcript.py)
- [evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [model_catalog.py](file://products/agent-platform/src/agent_service/services/model_catalog.py)
- [model_discovery.py](file://products/agent-platform/src/agent_service/services/model_discovery.py)
- [app.py](file://products/agent-platform/src/agent_service/app.py)
- [hitl_confirmations.py](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py)
- [registry.py](file://products/agent-platform/src/agent_service/providers/registry.py)
- [base.py](file://products/agent-platform/src/agent_service/providers/base.py)
- [gateway_tools.py](file://products/agent-platform/src/agent_service/tools/gateway_tools.py)
- [chat.py](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py)

## Detailed Component Analysis

### Runtime Kernel
The runtime kernel is the central orchestrator for agent execution with enhanced AgentScope 2.x compatibility, anti-hallucination features, and model normalization support. It manages:
- Agent lifecycle initialization and shutdown with AgentScope 2.x toolkit registration
- Conversation state transitions with per-request toolkit rebuilding
- Tool invocation and result aggregation with v3 streaming support
- Provider selection and streaming event handling with trace queue integration
- Evidence capture and persistence for tool_call and tool_result frames
- Model normalization for legacy provider name aliases and concrete model ID resolution
- Anti-hallucination guard system with NO_TOOLS_NOTICE injection
- Auto-approval mechanism for vetted read-only tools to prevent headless stream stalls
- Voice readiness support through input_modality parameter passthrough

```mermaid
classDiagram
class AgentKernel {
+initialize()
+start()
+execute(message, sessionId, bearerToken)
+streamChat(message, sessionId, bearerToken)
+invokeTool(toolName, params, bearerToken)
+_ensure_toolkit(bearerToken)
+_build_request_toolkit(bearerToken, traceQueue)
+_count_function_tools(toolkit)
+shutdown()
+reply_text(message, session_id, user_name, bearer_token, response_schema)
+stream_events(message, request_id, session_id, user_name, bearer_token)
+resume_confirmation(session_id, pending, decision, user_name, request_id, bearer_token)
+expire_confirmation(session_id, confirm_id)
+runtime_metadata()
+mode()
+provider_name()
+is_configured()
+runtime_state()
+_persist_evidence(session_id, request_id, turn_index, frames)
+_normalize_model_id(model_id)
+_build_model(model_id)
}
class SessionService {
+load(sessionId)
+save(sessionId, state)
+delete(sessionId)
+create_named_session(session_id, user_id)
+ensure_session(session_id, user_id)
+get_session(session_id, user_id)
+list_sessions(user_id)
+mark_session_turn(session_id, message)
+pin_session_model(session_id, model)
}
class EvidenceStore {
<<interface>>
+backend_name : str
+save_turn(session_id, request_id, turn_index, frames, session_max_bytes)
+load_turns(session_id)
+delete_session(session_id)
+is_ready()
}
class ModelCatalog {
+entries : tuple
+get(model_id)
+default_entry()
+public_models()
}
class ModelDiscovery {
+refresh_once()
+run_loop()
+build_discovery_service(settings, credentials)
}
class ProviderRegistry {
+register(name, provider)
+resolve(name)
+list()
}
class ModelProvider {
<<interface>>
+streamChat(messages, options)
+healthCheck()
}
class GatewayTools {
+discover_tools(gateway_url, bearer_token)
+build_gateway_toolkit(definitions, gateway_url, bearer_token, trace_queue)
+invoke_gateway_tool(gateway_url, tool_name, parameters, bearer_token)
}
AgentKernel --> SessionService : "uses"
AgentKernel --> EvidenceStore : "persists evidence"
AgentKernel --> ModelCatalog : "resolves models"
AgentKernel --> ProviderRegistry : "uses"
AgentKernel --> GatewayTools : "manages"
ModelDiscovery --> ModelCatalog : "updates"
ProviderRegistry --> ModelProvider : "manages"
GatewayTools --> ModelProvider : "secure invocation"
```

**Updated** The runtime kernel now includes AgentScope 2.x toolkit registration, per-request toolkit rebuilding with trace queues, anti-hallucination guard system, auto-approval mechanism for preventing headless stream stalls, enhanced session management methods for multi-session workspace operations and model pinning, evidence capture and persistence for tool execution frames, model normalization for legacy provider name aliases, and voice readiness support through input_modality parameter passthrough.

**Diagram sources**
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [session_service.py](file://products/agent-platform/src/agent_service/services/session_service.py)
- [evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [model_catalog.py](file://products/agent-platform/src/agent_service/services/model_catalog.py)
- [model_discovery.py](file://products/agent-platform/src/agent_service/services/model_discovery.py)
- [registry.py](file://products/agent-platform/src/agent_service/providers/registry.py)
- [base.py](file://products/agent-platform/src/agent_service/providers/base.py)
- [gateway_tools.py](file://products/agent-platform/src/agent_service/tools/gateway_tools.py)

**Section sources**
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)

### Provider Registry and Implementations
The provider registry supports multiple model backends through a common interface. Implementations include OpenAI, DashScope, DeepSeek, and Luban, all updated to use AgentScope 2.x model construction patterns with enhanced parameter support.

```mermaid
classDiagram
class BaseProvider {
<<abstract>>
+streamChat(messages, options)
+healthCheck()
+build_model(settings)
+discover_filter(model_id)
+discover_family_prefixes
+discover_exclude_markers
}
class OpenAIProvider {
+build_model(settings)
+provider_name = "openai"
+default_model = "gpt-4o-mini"
+discover_family_prefixes = ("gpt-", "o1", "o3", "o4", "chatgpt-")
}
class DashScopeProvider {
+build_model(settings)
+provider_name = "dashscope"
+default_model = "qwen-plus"
+discover_family_prefixes = ("qwen",)
+discover_exclude_markers = _NON_CHAT_MARKERS + ("-vl", "-mt", "-ocr", "omni")
}
class DeepSeekProvider {
+build_model(settings)
+provider_name = "deepseek"
+default_model = "deepseek-v4-flash"
+discover_family_prefixes = ("deepseek",)
}
class LubanProvider {
+build_model(settings)
+provider_name = "luban"
+default_model = "qwen3-8b"
+discover_family_prefixes = ()
+validate(settings)
}
class ProviderRegistry {
+register(name, provider)
+resolve(name)
+list()
}
BaseProvider <|-- OpenAIProvider
BaseProvider <|-- DashScopeProvider
BaseProvider <|-- DeepSeekProvider
BaseProvider <|-- LubanProvider
ProviderRegistry --> BaseProvider : "manages"
```

Configuration examples:
- OpenAI: Configure API key, model name, organization, and reasoning effort via environment variables or runtime settings.
- DashScope: Set endpoint URL, credentials, thinking budget, and parallel tool calls; select model variant.
- DeepSeek: Provide authentication token, target model identifier, and reasoning effort level.
- **Luban**: Configure LUBAN_API_KEY and mandatory LUBAN_BASE_URL for self-hosted OpenAI-compatible endpoints; supports bearer token authentication with no default endpoint.

**Updated** All provider implementations now use AgentScope 2.x model construction patterns with enhanced parameter support including reasoning effort, thinking enable flags, and parallel tool calls. Voice readiness is supported through consistent parameter passing across all modalities. Provider implementations include sophisticated filtering mechanisms for live model discovery, with family prefix restrictions and non-chat modality exclusion markers to ensure only chat-capable models are discovered. The new Luban provider enables self-hosted OpenAI-compatible endpoints with strict bearer token requirements and no default base URL.

**Section sources**
- [base.py](file://products/agent-platform/src/agent_service/providers/base.py)
- [openai.py](file://products/agent-platform/src/agent_service/providers/openai.py)
- [dashscope.py](file://products/agent-platform/src/agent_service/providers/dashscope.py)
- [deepseek.py](file://products/agent-platform/src/agent_service/providers/deepseek.py)
- [luban.py](file://products/agent-platform/src/agent_service/providers/luban.py)
- [registry.py](file://products/agent-platform/src/agent_service/providers/registry.py)
- [runtime_settings.py](file://products/agent-platform/src/agent_service/runtime_settings.py)
- [config.py](file://products/agent-platform/src/agent_service/core/config.py)
- [env.py](file://products/agent-platform/src/agent_service/core/env.py)

### Multi-Model Runtime Capability

#### Overview
The multi-model runtime capability enables dynamic model selection at runtime through a sophisticated resolution hierarchy that prioritizes explicit requests over pinned sessions, falling back to defaults when needed. This provides flexibility for operators to switch between different models without restarting sessions or affecting other users.

#### Model Resolution Hierarchy
```mermaid
flowchart TD
A["Chat Request"] --> B{"Explicit model requested?"}
B --> |Yes| C{"Model exists in catalog?"}
C --> |No| D["Return 422 Unknown Model Error"]
C --> |Yes| E["Use explicit model"]
B --> |No| F{"Pinned model exists?"}
F --> |Yes| G{"Pinned model still valid?"}
G --> |Yes| H["Use pinned model"]
G --> |No| I["Fallback to default"]
F --> |No| J["Use default model"]
E --> K["Pin model to session"]
H --> L["Continue processing"]
I --> M["Continue processing"]
J --> N["Continue processing"]
K --> L
```

**Diagram sources**
- [routes.py:112-137](file://products/agent-platform/src/agent_service/api/v2/routes.py#L112-L137)
- [session_service.py:105-120](file://products/agent-platform/src/agent_service/services/session_service.py#L105-L120)

#### Key Features
- **Priority-Based Resolution**: Explicit requests take precedence over pinned sessions, which override defaults
- **Credential-Gated Validation**: All model selections must exist in the credential-gated catalog
- **Session Persistence**: Model selections persist across turns within a session with TTL-aware storage
- **Graceful Degradation**: Invalid pinned models automatically fall back to defaults without errors
- **Error Handling**: Unknown models return 422 status codes with descriptive error messages
- **Audit Trail**: Model resolution decisions are logged with request and session context

#### Implementation Details
```mermaid
sequenceDiagram
participant Client as "Client"
participant API as "API Route"
participant Session as "Session"
participant Catalog as "ModelCatalog"
participant Store as "SessionStore"
Note over Client,Store : Model Resolution Flow
Client->>API : POST /api/v2/chat {model : "qwen-plus"}
API->>Session : ensure_session(session_id, user_id)
Session-->>API : SessionRecord with model field
API->>API : _resolve_model("qwen-plus", session.model)
alt Explicit model provided
API->>Catalog : get("qwen-plus")
Catalog-->>API : ModelCatalogEntry or None
alt Model exists
API->>Store : set_session_model(session_id, "qwen-plus")
Store-->>API : success
API-->>Client : Process with qwen-plus
else Model missing
API-->>Client : 422 Unknown Model Error
end
else No explicit model
API->>Catalog : get(session.model)
Catalog-->>API : Pinned model or None
alt Pinned model valid
API-->>Client : Process with pinned model
else Pinned invalid
API->>Catalog : default_entry()
Catalog-->>API : Default model
API-->>Client : Process with default model
end
end
```

**Diagram sources**
- [routes.py:142-182](file://products/agent-platform/src/agent_service/api/v2/routes.py#L142-L182)
- [routes.py:185-230](file://products/agent-platform/src/agent_service/api/v2/routes.py#L185-L230)
- [session_store.py:349-364](file://products/agent-platform/src/agent_service/services/session_store.py#L349-L364)

#### Session-Based Model Pinning
Model pinning persists the selected model for each session with TTL-aware storage across all backend types:

- **Memory Backend**: In-memory dictionary with TTL expiration
- **Redis Backend**: JSON serialization with key expiration
- **Postgres Backend**: Native SQL UPDATE statements with TTL conditions

**Section sources**
- [routes.py:112-137](file://products/agent-platform/src/agent_service/api/v2/routes.py#L112-L137)
- [session_service.py:105-120](file://products/agent-platform/src/agent_service/services/session_service.py#L105-L120)
- [session_store.py:349-364](file://products/agent-platform/src/agent_service/services/session_store.py#L349-L364)
- [session_store.py:471-477](file://products/agent-platform/src/agent_service/services/session_store.py#L471-L477)

### Multi-Session Operator Workspace
The multi-session operator workspace provides comprehensive session lifecycle management for operators to organize and manage conversation workspaces.

```mermaid
flowchart TD
Start(["Operator Request"]) --> List["GET /api/v2/sessions"]
List --> Fetch["Fetch User Sessions"]
Fetch --> Sort["Sort by last_active_at DESC"]
Sort --> Cap["Cap at 50 sessions"]
Cap --> CheckHITL["Check HITL Status"]
CheckHITL --> AddFlags["Add pending_confirmation flags"]
AddFlags --> ReturnList["Return Session List"]
Detail["GET /api/v2/sessions/{id}"] --> GetSession["Get Session Detail"]
GetSession --> ExtractTranscript["Extract Transcript"]
GetSession --> LoadEvidence["Load Evidence Turns"]
ExtractTranscript --> BuildResponse["Build Response with Title, Timestamps, Transcript, Evidence"]
LoadEvidence --> BuildResponse
BuildResponse --> ReturnDetail["Return Session Detail"]
Delete["DELETE /api/v2/sessions/{id}"] --> ValidateOwner["Validate Session Owner"]
ValidateOwner --> CheckParked["Check for Parked Confirmations"]
CheckParked --> |Has Pending| Reject["409 Conflict - Resolve First"]
CheckParked --> |No Pending| DeleteSession["Delete Session + State + Evidence"]
DeleteSession --> Audit["Emit session_deleted Audit Event"]
Audit --> Success["200 Deleted"]
```

**Diagram sources**
- [routes.py:334-419](file://products/agent-platform/src/agent_service/api/v2/routes.py#L334-L419)
- [session_service.py:72-123](file://products/agent-platform/src/agent_service/services/session_service.py#L72-L123)
- [session_store.py:72-73](file://products/agent-platform/src/agent_service/services/session_store.py#L72-L73)

Key features:
- **Session Listing**: Most-recently-active first, capped at 50 sessions per user
- **Workspace Ordering**: Uses `last_active_at` timestamps for chronological organization
- **Server-Minted Titles**: First user turn creates immutable session titles (80-char cap)
- **Owner-Only Access**: Foreign session IDs return 404 (anti-enumeration pattern)
- **HITL Integration**: Sessions with parked confirmations block deletion with 409
- **Transcript Extraction**: Best-effort conversation history from kernel state snapshots
- **Evidence Retrieval**: Load persisted tool execution evidence for session details
- **Audit Trail**: All delete operations emit durable `session_deleted` audit events

**Section sources**
- [routes.py:334-419](file://products/agent-platform/src/agent_service/api/v2/routes.py#L334-L419)
- [session_service.py:72-123](file://products/agent-platform/src/agent_service/services/session_service.py#L72-L123)

### Session Store Enhancements
The session store has been enhanced with workspace bookkeeping capabilities including last_active_at timestamps and server-minted titles, plus model pinning support.

```mermaid
classDiagram
class SessionStore {
<<interface>>
+backend_name : str
+create_session(user_id, session_id) : SessionRecord
+get_session(session_id) : SessionRecord?
+list_sessions_by_user(user_id) : list[SessionRecord]
+delete_session(session_id) : bool
+touch_session(session_id) : None
+set_session_title(session_id, title) : None
+set_session_model(session_id, model) : None
+is_ready() : bool
+__len__() : int
}
class InMemorySessionStore {
+backend_name = "memory"
+ttl_seconds : float
+max_entries : int
+_sessions : dict[str, SessionRecord]
+_last_accessed : dict[str, float]
}
class RedisSessionStore {
+backend_name = "redis"
+ttl_seconds : int
+_client : redis.Redis
}
class PostgresSessionStore {
+backend_name = "postgres"
+ttl_seconds : float
+_db_url : str
+_connect : SyncConnectFactory
}
SessionStore <|.. InMemorySessionStore
SessionStore <|.. RedisSessionStore
SessionStore <|.. PostgresSessionStore
```

Enhanced capabilities:
- **Last Active Tracking**: `last_active_at` timestamps for workspace ordering and activity monitoring
- **Server-Minted Titles**: Immutable titles created from first user turn (80-character cap)
- **Model Pinning**: Persistent model selection per session with TTL-aware storage
- **Backend-Specific Optimization**: Postgres uses native SQL ordering, memory/Redis sort client-side
- **TTL-Aware Operations**: All workspace operations respect session TTL and idle expiration
- **Fail-Open Design**: Workspace bookkeeping failures don't block chat operations
- **Idempotent DDL**: Postgres schema migration handles pre-existing deployments gracefully

**Section sources**
- [session_store.py:46-73](file://products/agent-platform/src/agent_service/services/session_store.py#L46-L73)
- [session_store.py:81-169](file://products/agent-platform/src/agent_service/services/session_store.py#L81-L169)
- [session_store.py:176-320](file://products/agent-platform/src/agent_service/services/session_store.py#L176-L320)
- [session_store.py:420-612](file://products/agent-platform/src/agent_service/services/session_store.py#L420-L612)

### Transcript Extraction Service
The transcript extraction service provides best-effort conversation history reconstruction from kernel state snapshots for workspace UIs.

```mermaid
sequenceDiagram
participant Client as "Client"
participant API as "Session Detail Route"
participant Transcript as "TranscriptExtractor"
participant StateStore as "AgentStateStore"
participant Parser as "ContentParser"
Client->>API : GET /sessions/{sessionId}
API->>Transcript : extract_transcript(sessionId)
Transcript->>StateStore : load_state(sessionId)
alt State Available
StateStore-->>Transcript : JSON snapshot
Transcript->>Parser : parse context messages
Parser->>Parser : filter user/assistant roles only
Parser->>Parser : extract text content from blocks
Parser-->>Transcript : clean conversation turns
Transcript-->>API : transcript_available=true, turns[]
else State Missing/Corrupt
StateStore-->>Transcript : null/error
Transcript-->>API : transcript_available=false, []
end
API-->>Client : Session detail with transcript
```

**Diagram sources**
- [session_transcript.py:30-64](file://products/agent-platform/src/agent_service/services/session_transcript.py#L30-L64)
- [routes.py:375-395](file://products/agent-platform/src/agent_service/api/v2/routes.py#L375-L395)

Key characteristics:
- **Best-Effort Design**: Missing snapshots degrade gracefully without errors
- **Role Filtering**: Only extracts user and assistant messages (excludes system/tool frames)
- **Content Flattening**: Converts block-structured content to plain text
- **Timestamp Preservation**: Maintains original message creation times when available
- **Error Resilience**: Corrupt JSON or unknown shapes return empty transcripts
- **Security Boundary**: Never fabricates conversation history

**Section sources**
- [session_transcript.py:1-83](file://products/agent-platform/src/agent_service/services/session_transcript.py#L1-L83)

### HITL Confirmation Registry Integration
The HITL (Human-In-The-Loop) confirmation registry manages parked tool confirmations for interactive workflows.

```mermaid
stateDiagram-v2
[*] --> Unparked
Unparked --> Parked : RequireUserConfirmEvent
Parked --> Claimed : claim(confirm_id)
Claimed --> Resolved : resolve(confirm_id)
Parked --> Expired : TTL exceeded
Expired --> Resolved : expire_confirmation(confirm_id)
Resolved --> [*]
note right of Parked
Single-flight guard prevents
double-resumption of parked
tool confirmations
end note
note right of Claimed
Ownership transfer ensures
only session owner can
answer confirmation
end note
```

**Diagram sources**
- [hitl_confirmations.py:93-229](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L93-L229)
- [routes.py:71-100](file://products/agent-platform/src/agent_service/api/v2/routes.py#L71-L100)

Core functionality:
- **Parked Confirmation Management**: Tracks tool calls awaiting user approval
- **Single-Flight Guarantees**: Prevents duplicate confirmation processing
- **TTL-Based Expiration**: Automatic cleanup of expired confirmations
- **Owner Validation**: Ensures only session owners can answer confirmations
- **Risk Level Tracking**: Captures mutating tool risk levels for UI flagging
- **Integration Points**: Bridges AgentScope kernel events with platform workflows

**Section sources**
- [hitl_confirmations.py:1-229](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L1-L229)
- [routes.py:71-100](file://products/agent-platform/src/agent_service/api/v2/routes.py#L71-L100)

### API Endpoints
The API layer exposes REST endpoints for agent interactions, session management, model discovery, and health checks. Requests are validated against schemas and routed to the runtime kernel with v3 streaming protocol support.

Typical endpoints:
- Chat: POST /chat with message, optional session ID, and delegated token
- Sessions: GET/POST/DELETE /sessions for lifecycle management with evidence retrieval
- Models: GET /models for credential-safe model discovery
- Health: GET /health for readiness and liveness probes
- Streaming: Server-sent events for incremental responses with v3 tool_call/tool_result frames

Request/response validation uses Pydantic models defined in schemas with enhanced v3 streaming event types.

**Updated** Chat endpoints now accept delegated tokens for secure tool execution and support v3 streaming protocol with tool_call/tool_result frames for comprehensive audit trails. Both POST /chat and GET /chat/stream endpoints accept input_modality parameters for voice-readiness parity. Session endpoints provide multi-session workspace operations with proper authorization, audit trails, and evidence turn retrieval. Model endpoints provide credential-safe enumeration of available models with public schema compliance.

**Section sources**
- [routes.py:106-235](file://products/agent-platform/src/agent_service/api/v2/routes.py#L106-L235)
- [routes.py:334-419](file://products/agent-platform/src/agent_service/api/v2/routes.py#L334-L419)
- [routes.py:534-544](file://products/agent-platform/src/agent_service/api/v2/routes.py#L534-L544)
- [api.py:8-18](file://products/agent-platform/src/agent_service/schemas/api.py#L8-L18)
- [v2.py](file://products/agent-platform/src/agent_service/schemas/v2.py)

### Tools Integration
The service integrates with external tools through a gateway abstraction. Tools can be invoked during agent execution to perform actions like Kubernetes operations or data retrieval with enhanced AgentScope 2.x compatibility.

```mermaid
sequenceDiagram
participant Kernel as "RuntimeKernel"
participant GatewayTools as "GatewayTools"
participant External as "External Tool"
participant Trace as "TraceQueue"
participant HITL as "ConfirmationRegistry"
participant EvStore as "EvidenceStore"
Kernel->>GatewayTools : build_gateway_toolkit(definitions, bearerToken, traceQueue)
GatewayTools->>External : discover_tools(bearerToken)
External-->>GatewayTools : availableTools
GatewayTools->>Trace : emit tool_call trace event
GatewayTools->>HITL : check_auto_approval(tool_name)
alt Tool requires confirmation
HITL-->>GatewayTools : ASK decision
GatewayTools->>Kernel : stall until user confirms
else Tool auto-approved
HITL-->>GatewayTools : ALLOW decision
GatewayTools->>External : invoke("k8s_connector", action, params, bearerToken)
External-->>GatewayTools : result
GatewayTools->>Trace : emit tool_result trace event
Trace-->>Kernel : audit trail data
Kernel->>EvStore : persist evidence frames
EvStore-->>Kernel : evidence stored
GatewayTools-->>Kernel : toolResult
end
```

**Updated** The tools integration now includes AgentScope 2.x toolkit registration pattern, per-request trace queues for audit trails, v3 streaming support with tool_call/tool_result frames, auto-approval mechanism for vetted read-only tools, HITL confirmation registry integration for interactive workflows, and evidence store integration for persistent tool execution records. Voice readiness is maintained throughout the tool execution pipeline.

**Diagram sources**
- [gateway_tools.py](file://products/agent-platform/src/agent_service/tools/gateway_tools.py)
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [hitl_confirmations.py](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py)
- [evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)

**Section sources**
- [gateway_tools.py](file://products/agent-platform/src/agent_service/tools/gateway_tools.py)

## Multi-Session Operator Workspace

### Overview
The multi-session operator workspace provides comprehensive session lifecycle management for operators to organize, monitor, and manage conversation workspaces. This foundation enables operators to handle multiple concurrent incidents, track conversation progress, and maintain workspace organization without direct database access.

### Key Features
- **Session Listing**: Browse user's sessions ordered by most recent activity
- **Workspace Organization**: Server-minted titles from first user turns for easy identification
- **Activity Tracking**: Last active timestamps for workspace sorting and monitoring
- **Owner-Only Access**: Anti-enumeration pattern prevents session enumeration attacks
- **HITL Integration**: Sessions with pending confirmations are properly flagged and protected
- **Transcript Access**: Best-effort conversation history reconstruction for workspace UIs
- **Evidence Retrieval**: Load persisted tool execution evidence for session details
- **Audit Trail**: All workspace operations are logged for compliance and debugging

### Implementation Details
```mermaid
flowchart TD
A["Operator Request"] --> B{"Operation Type"}
B --> |List| C["GET /api/v2/sessions"]
B --> |Detail| D["GET /api/v2/sessions/{id}"]
B --> |Delete| E["DELETE /api/v2/sessions/{id}"]
C --> F["Fetch user sessions"]
F --> G["Sort by last_active_at DESC"]
G --> H["Cap at 50 sessions"]
H --> I["Check HITL status"]
I --> J["Add pending_confirmation flags"]
J --> K["Return session list"]
D --> L["Get session by ID"]
L --> M["Validate owner"]
M --> N["Extract transcript"]
M --> O["Load evidence turns"]
N --> P["Build response with transcript"]
O --> P
P --> Q["Return with title, timestamps, transcript, evidence"]
E --> R["Validate owner"]
R --> S["Check for parked confirmations"]
S --> |Has pending| T["409 Conflict"]
S --> |Clear| U["Delete session + state + evidence"]
U --> V["Emit audit event"]
V --> W["200 Deleted"]
```

**Diagram sources**
- [routes.py:334-419](file://products/agent-platform/src/agent_service/api/v2/routes.py#L334-L419)
- [session_service.py:72-123](file://products/agent-platform/src/agent_service/services/session_service.py#L72-L123)

### Security Considerations
- **Anti-Enumeration**: Foreign session IDs return 404, indistinguishable from unknown IDs
- **Owner Validation**: All operations validate session ownership before processing
- **HITL Protection**: Sessions with parked confirmations cannot be deleted (409 conflict)
- **Audit Logging**: All workspace operations generate audit events for compliance
- **Role-Based Access**: Platform gateway enforces policy rules for session operations

**Section sources**
- [routes.py:334-419](file://products/agent-platform/src/agent_service/api/v2/routes.py#L334-L419)
- [session_service.py:72-123](file://products/agent-platform/src/agent_service/services/session_service.py#L72-L123)

## Session Store Enhancements

### Overview
The session store has been enhanced with workspace bookkeeping capabilities to support multi-session operator workspace functionality. These enhancements include last_active_at timestamps for activity tracking and server-minted titles for session identification, plus model pinning support.

### Enhanced Schema
```mermaid
erDiagram
SESSIONS {
TEXT session_id PK
TEXT user_id
TIMESTAMPTZ created_at
TIMESTAMPTZ last_accessed_at
TEXT title
TIMESTAMPTZ last_active_at
TEXT model
}
INDEXES {
idx_sessions_user ON user_id
idx_sessions_accessed ON last_accessed_at
}
```

**Diagram sources**
- [session_store.py:327-344](file://products/agent-platform/src/agent_service/services/session_store.py#L327-L344)

### Backend Implementations
All three backend implementations support the enhanced workspace features:

- **In-Memory Store**: Supports TTL-based eviction with workspace metadata
- **Redis Store**: Uses JSON serialization with sorted sets for user-scoped listing
- **Postgres Store**: Native SQL queries with optimized indexing for workspace operations

### Workspace Bookkeeping
```mermaid
sequenceDiagram
participant Chat as "Chat Operation"
participant Service as "SessionService"
participant Store as "SessionStore"
participant DB as "Database"
Chat->>Service : mark_session_turn(session_id, message)
Service->>Service : extract title from message (80-char cap)
Service->>Store : set_session_title(session_id, title)
Store->>DB : UPDATE sessions SET title WHERE title IS NULL
Store->>Store : touch_session(session_id)
Store->>DB : UPDATE sessions SET last_active_at = now()
DB-->>Store : success
Store-->>Service : workspace updated
Service-->>Chat : continue processing
```

**Diagram sources**
- [session_service.py:86-102](file://products/agent-platform/src/agent_service/services/session_service.py#L86-L102)
- [session_store.py:386-398](file://products/agent-platform/src/agent_service/services/session_store.py#L386-L398)

### Performance Optimizations
- **Server-Side Sorting**: Postgres backend uses native SQL ORDER BY for efficient workspace listing
- **Indexed Queries**: Proper indexing on user_id, last_accessed_at, and last_active_at columns
- **TTL-Aware Operations**: All workspace operations respect session TTL and idle expiration
- **Fail-Open Design**: Workspace bookkeeping failures don't block core chat operations
- **Idempotent Migration**: Postgres DDL handles pre-existing deployments gracefully

**Section sources**
- [session_store.py:46-73](file://products/agent-platform/src/agent_service/services/session_store.py#L46-L73)
- [session_store.py:81-169](file://products/agent-platform/src/agent_service/services/session_store.py#L81-L169)
- [session_store.py:176-320](file://products/agent-platform/src/agent_service/services/session_store.py#L176-L320)
- [session_store.py:420-612](file://products/agent-platform/src/agent_service/services/session_store.py#L420-L612)

## Transcript Extraction Service

### Overview
The transcript extraction service provides best-effort conversation history reconstruction from kernel state snapshots. This enables workspace UIs to display conversation context without requiring live stream replay or direct database access.

### Extraction Process
```mermaid
flowchart TD
A["Load Kernel State Snapshot"] --> B{"Snapshot Valid?"}
B --> |No| C["Return transcript_available=false, []"]
B --> |Yes| D["Parse JSON Context Array"]
D --> E{"Context is Array?"}
E --> |No| C
E --> |Yes| F["Filter Messages"]
F --> G{"Message Has Role?"}
G --> |No| H["Skip Message"]
G --> |Yes| I{"Role is user/assistant?"}
I --> |No| H
I --> |Yes| J["Extract Text Content"]
J --> K{"Content is String or Blocks?"}
K --> |String| L["Use Direct Text"]
K --> |Blocks| M["Flatten Text Blocks"]
M --> N["Join Block Text"]
L --> O["Create Turn Object"]
N --> O
O --> P["Add Created At (if present)"]
P --> Q["Add to Turns Array"]
Q --> R["Continue Processing"]
R --> S{"More Messages?"}
S --> |Yes| F
S --> |No| T["Return transcript_available=true, turns[]"]
```

**Diagram sources**
- [session_transcript.py:30-64](file://products/agent-platform/src/agent_service/services/session_transcript.py#L30-L64)

### Key Characteristics
- **Best-Effort Design**: Missing or corrupt snapshots degrade gracefully without errors
- **Role Filtering**: Only extracts user and assistant messages (excludes system/tool frames)
- **Content Flattening**: Converts block-structured content to plain text
- **Timestamp Preservation**: Maintains original message creation times when available
- **Security Boundary**: Never fabricates conversation history
- **Error Resilience**: Handles various content formats and edge cases gracefully

### Integration Points
- **Session Detail Endpoint**: Provides transcript data alongside session metadata
- **Workspace UI**: Enables conversation context display in operator interfaces
- **Audit Trail**: Transcript availability status aids in debugging and monitoring
- **Fallback Handling**: Graceful degradation when snapshots are unavailable

**Section sources**
- [session_transcript.py:1-83](file://products/agent-platform/src/agent_service/services/session_transcript.py#L1-L83)

## HITL Confirmation Registry Integration

### Overview
The HITL (Human-In-The-Loop) confirmation registry manages parked tool confirmations for interactive workflows. When AgentScope kernel encounters tools requiring user approval, it parks the reply and waits for operator confirmation before proceeding.

### Confirmation Lifecycle
```mermaid
stateDiagram-v2
[*] --> Unparked : Initial State
Unparked --> Parked : RequireUserConfirmEvent
Parked --> Claimed : claim(confirm_id)
Claimed --> Resolved : resolve(confirm_id)
Parked --> Expired : TTL exceeded
Expired --> Resolved : expire_confirmation(confirm_id)
Resolved --> [*] : Cleanup Complete
note right of Parked
Single-flight guard prevents
double-resumption of parked
tool confirmations
end note
note right of Claimed
Ownership transfer ensures
only session owner can
answer confirmation
end note
note right of Expired
TTL-based cleanup prevents
stale confirmations from
blocking sessions indefinitely
end note
```

**Diagram sources**
- [hitl_confirmations.py:93-229](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L93-L229)

### Core Components
- **PendingConfirmation**: Data structure holding parked tool call information
- **ConfirmationRegistry**: In-memory registry managing confirmation lifecycle
- **Risk Level Tracking**: Captures mutating tool risk levels for UI flagging
- **TTL Management**: Automatic expiration of stale confirmations
- **Owner Validation**: Ensures only session owners can answer confirmations

### Integration Patterns
- **Chat Routes**: Check for parked confirmations before processing new messages
- **Stream Events**: Surface confirmation requests to clients via SSE
- **Confirmation Endpoint**: Handle operator decisions to resume parked workflows
- **Session Protection**: Block deletion of sessions with pending confirmations

**Section sources**
- [hitl_confirmations.py:1-229](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L1-L229)
- [routes.py:71-100](file://products/agent-platform/src/agent_service/api/v2/routes.py#L71-L100)

## Enhanced Streaming Architecture

### Overview
The streaming architecture has been enhanced with v3 protocol support, including dedicated tool_call and tool_result frames for comprehensive audit trails and evidence panel rendering.

### V3 Protocol Features
- **Tool Call Frames**: Capture tool invocation details including parameters and call IDs
- **Tool Result Frames**: Record execution outcomes with evidence and data summaries
- **Evidence Panel Support**: Structured data for UI components to display tool usage
- **Audit Trail Integration**: Seamless integration with per-request trace queues
- **Evidence Persistence**: Automatic persistence of tool execution evidence for session replay

### Stream Event Types
```mermaid
stateDiagram-v2
[*] --> message_start
message_start --> message_delta
message_delta --> message_end
message_delta --> tool_call
tool_call --> tool_result
tool_result --> message_delta
message_end --> [*]
note right of tool_call
Captures :
- tool_name
- call_id
- parameters
end note
note right of tool_result
Captures :
- status
- evidence
- data_summary
- error
end note
```

**Diagram sources**
- [v2.py:42-68](file://products/agent-platform/src/agent_service/schemas/v2.py#L42-L68)
- [routes.py:105-150](file://products/agent-platform/src/agent_service/api/v2/routes.py#L105-L150)

### Evidence Panel Data
The v3 protocol supports rich evidence data including:
- **Execution Context**: Tool names, parameters, and call identifiers
- **Results and Errors**: Status codes, error messages, and failure details
- **Data Summaries**: Truncated previews of large tool outputs
- **Audit Information**: Request IDs, session IDs, and timestamps

**Section sources**
- [v2.py:42-68](file://products/agent-platform/src/agent_service/schemas/v2.py#L42-L68)
- [routes.py:105-150](file://products/agent-platform/src/agent_service/api/v2/routes.py#L105-L150)
- [gateway_tools.py:212-251](file://products/agent-platform/src/agent_service/tools/gateway_tools.py#L212-L251)

## Voice Readiness Support

### Overview
The Agent Platform Service now provides comprehensive voice-readiness support through the addition of input_modality parameters to both POST /chat and GET /chat/stream endpoints. This enhancement ensures parity between synchronous and asynchronous chat interfaces while maintaining consistent policy enforcement and HITL workflows.

### Input Modality Implementation
```mermaid
sequenceDiagram
participant Client as "Client"
participant Gateway as "Platform Gateway"
participant API as "Agent Platform API"
participant Kernel as "RuntimeKernel"
participant Policy as "Policy Engine"
participant HITL as "ConfirmationRegistry"
Note over Client,HITL : Voice-Ready Chat Flow
Client->>Gateway : POST /api/v1/chat {message, input_modality="voice"}
Gateway->>API : Forward with input_modality metadata
API->>Policy : Enforce policy (modality ignored)
Policy-->>API : Policy decision unchanged
API->>HITL : Check parked confirmations
HITL-->>API : No parked confirmations
API->>Kernel : Execute with input_modality passthrough
Kernel-->>API : Response with consistent behavior
API-->>Client : Response (same as text modality)
Note over Client,HITL : Voice-Ready Streaming
Client->>API : GET /api/v2/chat/stream?message=...&input_modality=voice
API->>Policy : Enforce policy (modality ignored)
Policy-->>API : Policy decision unchanged
API->>Kernel : Stream events with input_modality passthrough
Kernel-->>API : StreamEvent* with v3 frames
API-->>Client : SSE/Streaming Response
```

**Diagram sources**
- [routes.py:135-165](file://products/agent-platform/src/agent_service/api/v2/routes.py#L135-L165)
- [v2.py:31-48](file://products/agent-platform/src/agent_service/schemas/v2.py#L31-L48)
- [chat.py:90-143](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L90-L143)

### Key Features
- **Literal Type Validation**: Strict validation of input_modality to 'text' or 'voice' values
- **Default Behavior**: Defaults to 'text' modality for backward compatibility
- **Metadata-Only**: Input modality is metadata only and never changes policy or HITL outcomes
- **Consistent Enforcement**: Same policy enforcement regardless of input modality
- **Audit Trail Integration**: Input modality is recorded in audit events for tracking
- **Test Coverage**: Comprehensive tests validate acceptance, validation, and default behavior

### API Changes
- **POST /api/v2/chat**: Accepts input_modality in request body with Literal["text", "voice"] validation
- **GET /api/v2/chat/stream**: Accepts input_modality as query parameter with Literal["text", "voice"] validation
- **Schema Validation**: Pydantic models enforce strict type checking for input_modality
- **Backward Compatibility**: Default value of 'text' ensures existing clients continue to work

### Testing and Validation
The implementation includes comprehensive test coverage:
- **Acceptance Testing**: Validates that both 'text' and 'voice' modalities are accepted
- **Validation Testing**: Ensures invalid modality values are rejected with 422 status
- **Default Behavior Testing**: Confirms default 'text' modality when not specified
- **Parity Testing**: Verifies consistent behavior across POST and GET endpoints

**Section sources**
- [routes.py:135-165](file://products/agent-platform/src/agent_service/api/v2/routes.py#L135-L165)
- [v2.py:31-48](file://products/agent-platform/src/agent_service/schemas/v2.py#L31-L48)
- [test_chat_stream_modality.py:1-63](file://products/agent-platform/tests/test_chat_stream_modality.py#L1-L63)
- [chat.py:90-143](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L90-L143)

## Per-Request Trace Queues

### Overview
Per-request trace queues provide comprehensive audit trails for tool execution, enabling evidence panel rendering and detailed monitoring of tool usage patterns.

### Queue Architecture
```mermaid
sequenceDiagram
participant Client as "Client"
participant Kernel as "RuntimeKernel"
participant Queue as "TraceQueue"
participant Tools as "GatewayTools"
participant External as "External Tool"
Client->>Kernel : stream_events(message, bearerToken)
Kernel->>Kernel : create asyncio.Queue()
Kernel->>Tools : build_gateway_toolkit(..., traceQueue)
Tools->>Queue : put(tool_call event)
Tools->>External : invoke tool
External-->>Tools : result
Tools->>Queue : put(tool_result event)
Kernel->>Queue : drain queue events
Queue-->>Kernel : trace events
Kernel-->>Client : stream with trace events
```

**Diagram sources**
- [runtime_kernel.py:404-447](file://products/agent-platform/src/agent_service/runtime_kernel.py#L404-447)
- [gateway_tools.py:212-251](file://products/agent-platform/src/agent_service/tools/gateway_tools.py#L212-L251)

### Key Features
- **Isolation**: Each request gets its own trace queue for clean separation
- **Non-blocking**: Async queue operations don't block tool execution
- **Complete Coverage**: Captures both tool invocations and results
- **Structured Data**: Rich metadata including parameters, evidence, and summaries

### Trace Event Structure
Each trace event includes:
- **Event Type**: `tool_call` or `tool_result`
- **Identification**: Tool name, call ID, request ID, session ID
- **Execution Context**: Parameters, status, errors
- **Evidence Data**: Tool-specific evidence and data summaries

**Section sources**
- [runtime_kernel.py:404-447](file://products/agent-platform/src/agent_service/runtime_kernel.py#L404-447)
- [gateway_tools.py:212-251](file://products/agent-platform/src/agent_service/tools/gateway_tools.py#L212-L251)

## Delegated Token Management

### Overview
The Agent Platform Service implements comprehensive delegated token management to ensure secure tool discovery and invocation. The runtime kernel manages per-user toolkit closures that are bound to delegated tokens, providing a secure execution context for all tool operations.

### Token Flow Architecture
```mermaid
sequenceDiagram
participant Client as "Client"
participant API as "API Layer"
participant Kernel as "RuntimeKernel"
participant Closure as "ToolkitClosure"
participant Tools as "GatewayTools"
participant External as "External Services"
Client->>API : Request with Authorization : Bearer token
API->>Kernel : Forward request + bearer token
Kernel->>Closure : createToolkitClosure(bearerToken)
Closure->>Tools : discover_tools(bearerToken)
Tools->>External : List available tools
External-->>Tools : Tool definitions
Tools-->>Closure : Available tools with auth requirements
Closure->>Tools : invoke(toolName, params, bearerToken)
Tools->>External : Execute tool with bearerToken
External-->>Tools : Tool result
Tools-->>Closure : Execution result
Closure-->>Kernel : Secure tool result
Kernel-->>API : Final response
API-->>Client : Response with results
```

**Diagram sources**
- [runtime_kernel.py:178-223](file://products/agent-platform/src/agent_service/runtime_kernel.py#L178-223)
- [gateway_tools.py:99-126](file://products/agent-platform/src/agent_service/tools/gateway_tools.py#L99-L126)
- [routes.py:40-47](file://products/agent-platform/src/agent_service/api/v2/routes.py#L40-L47)

### Key Features
- **Per-User Isolation**: Each user's toolkit closure is isolated and bound to their specific delegated token
- **Bearer Token Relay**: Delegated tokens are automatically converted to bearer tokens for downstream tool calls
- **Secure Discovery**: Tool discovery happens within the context of the user's delegated token
- **Context Propagation**: Authentication context flows through the entire execution pipeline
- **Lifecycle Management**: Toolkit closures are created per-request and cleaned up after execution

### Security Benefits
- Prevents token leakage between users
- Ensures tools execute with appropriate user permissions
- Provides audit trail for tool access patterns
- Maintains separation of concerns between identity and execution contexts

**Section sources**
- [runtime_kernel.py:178-223](file://products/agent-platform/src/agent_service/runtime_kernel.py#L178-223)
- [gateway_tools.py:99-126](file://products/agent-platform/src/agent_service/tools/gateway_tools.py#L99-L126)
- [routes.py:40-47](file://products/agent-platform/src/agent_service/api/v2/routes.py#L40-L47)

## Evidence Store Service

### Overview
The evidence store service provides persistent storage for tool execution evidence with dual backend support (in-memory and Postgres). It captures tool_call and tool_result frames from streaming operations, applies size-capped retention policies, and provides evidence retrieval for session replay and audit purposes.

### Architecture
```mermaid
classDiagram
class EvidenceStore {
<<interface>>
+backend_name : str
+save_turn(session_id, request_id, turn_index, frames, session_max_bytes)
+load_turns(session_id)
+delete_session(session_id)
+is_ready()
}
class _BaseEvidenceStore {
+save_turn(session_id, request_id, turn_index, frames, session_max_bytes)
+_enforce_budget(session_id, session_max_bytes)
+load_turns(session_id)
+_next_frame_index(session_id, turn_index)
+_insert_rows(rows)
+_session_bytes(session_id)
+_evict_oldest_result_payload(session_id)
+_load_rows(session_id)
+_delete_rows(session_id)
}
class InMemoryEvidenceStore {
+backend_name = "memory"
-_rows : dict[str, list[dict]]
+_next_frame_index(session_id, turn_index)
+_insert_rows(rows)
+_session_bytes(session_id)
+_evict_oldest_result_payload(session_id)
+_load_rows(session_id)
+_delete_rows(session_id)
}
class PostgresEvidenceStore {
+backend_name = "postgres"
+_db_url : str
+ttl_seconds : float
+_connect : SyncConnectFactory
+initialize()
+_next_frame_index(session_id, turn_index)
+_insert_rows(rows)
+_session_bytes(session_id)
+_evict_oldest_result_payload(session_id)
+_load_rows(session_id)
+_delete_rows(session_id)
}
EvidenceStore <|.. _BaseEvidenceStore
_BaseEvidenceStore <|.. InMemoryEvidenceStore
_BaseEvidenceStore <|.. PostgresEvidenceStore
```

**Diagram sources**
- [evidence_store.py:86-204](file://products/agent-platform/src/agent_service/services/evidence_store.py#L86-L204)
- [evidence_store.py:211-273](file://products/agent-platform/src/agent_service/services/evidence_store.py#L211-L273)
- [evidence_store.py:362-497](file://products/agent-platform/src/agent_service/services/evidence_store.py#L362-L497)

### Key Features
- **Dual Backend Support**: In-memory for development/testing, Postgres for production with failover
- **Size-Capped Storage**: Per-entry character limits and per-session byte budgets with automatic eviction
- **Evidence Grouping**: Frames grouped by turn index with request correlation and timestamps
- **Automatic Eviction**: Oldest result payloads evicted when session exceeds budget, preserving metadata
- **TTL Management**: Opportunistic sweep of expired evidence rows in Postgres backend
- **Metrics Integration**: Comprehensive observability for evidence persistence operations
- **Redaction Inheritance**: Inherits redaction from tool-gateway choke point for security

### Evidence Persistence Flow
```mermaid
sequenceDiagram
participant Kernel as "RuntimeKernel"
participant Prepare as "prepare_frames"
participant Store as "EvidenceStore"
participant Budget as "_enforce_budget"
participant Metrics as "Metrics"
Kernel->>Prepare : prepare_frames(frames, entry_max_chars)
Prepare-->>Kernel : prepared frames with truncation markers
Kernel->>Store : save_turn(session_id, request_id, turn_index, prepared, session_max_bytes)
Store->>Store : _insert_rows(rows)
Store->>Budget : _enforce_budget(session_id, session_max_bytes)
Budget->>Budget : _session_bytes(session_id)
Budget->>Budget : _evict_oldest_result_payload(session_id)
Budget-->>Store : freed bytes
Store->>Metrics : record_evidence_frames_persisted(count)
Store-->>Kernel : evidence persisted
```

**Diagram sources**
- [evidence_store.py:118-164](file://products/agent-platform/src/agent_service/services/evidence_store.py#L118-L164)
- [runtime_kernel.py:450-473](file://products/agent-platform/src/agent_service/runtime_kernel.py#L450-L473)

### Configuration and Environment Variables
- **AGENT_STATE_STORE_BACKEND**: Selects backend ("memory" or "postgres")
- **AGENT_STATE_DB_URL**: Database connection string for Postgres backend
- **AGENT_STATE_TTL_SECONDS**: Time-to-live for evidence rows (opportunistic sweep)
- **AGENT_EVIDENCE_ENTRY_MAX_CHARS**: Per-entry data payload character limit (default: 131072)
- **AGENT_EVIDENCE_SESSION_MAX_BYTES**: Per-session storage budget in bytes (default: 4194304)

### Evidence Schema
The evidence store follows the session-evidence schema with structured turn groups containing tool_call and tool_result frames, supporting truncation markers for size-capped storage.

**Section sources**
- [evidence_store.py:1-551](file://products/agent-platform/src/agent_service/services/evidence_store.py#L1-L551)
- [session-evidence.schema.json:1-58](file://shared/shared-contracts/schemas/session-evidence.schema.json#L1-L58)
- [runtime_kernel.py:450-473](file://products/agent-platform/src/agent_service/runtime_kernel.py#L450-L473)
- [metrics.py:158-186](file://products/agent-platform/src/agent_service/core/metrics.py#L158-L186)
- [runtime_settings.py:145-150](file://products/agent-platform/src/agent_service/runtime_settings.py#L145-L150)

## Model Catalog Service

### Overview
The model catalog service provides credential-gated discovery of available LLM models across multiple providers (OpenAI, DashScope, DeepSeek, and Luban). It derives the set of selectable models from per-provider environment configuration at startup, ensuring that only configured providers with resolvable API keys contribute to the catalog.

### Architecture
```mermaid
classDiagram
class ModelCatalogEntry {
+id : str
+label : str
+provider : RuntimeProvider
+api_key : str
+model_name : str
+base_url : str | None
+default : bool
+to_public_dict()
}
class ModelCatalog {
+_entries : tuple
+_by_id : dict
+_aliases : dict
+entries : tuple
+get(model_id)
+default_entry()
+public_models()
+_swap(entries, aliases)
}
class ProviderCredentials {
+provider : RuntimeProvider
+api_key : str
+base_url : str | None
+default_model : str
+models_override : tuple[str, ...] | None
}
class RuntimeSettings {
+provider : RuntimeProvider
+api_key : str
+model_name : str
+base_url : str
+profile : str
+from_env()
}
ModelCatalog --> ModelCatalogEntry : "manages"
ModelCatalog --> ProviderCredentials : "uses for defaults"
ModelCatalog --> RuntimeSettings : "uses for defaults"
```

**Diagram sources**
- [model_catalog.py:42-61](file://products/agent-platform/src/agent_service/services/model_catalog.py#L42-L61)
- [model_catalog.py:149-185](file://products/agent-platform/src/agent_service/services/model_catalog.py#L149-L185)
- [model_catalog.py:223-280](file://products/agent-platform/src/agent_service/services/model_catalog.py#L223-L280)

### Key Features
- **Credential-Gated Discovery**: Only providers with resolvable API keys contribute to the catalog
- **Multi-Provider Support**: OpenAI, DashScope, DeepSeek, and Luban with full model series enumeration
- **Legacy Alias Resolution**: Bare provider names alias to provider's default model for backward compatibility
- **Public Schema Compliance**: Discovery payload contains only id, label, provider, and default fields
- **Environment Variable Configuration**: Supports `<PROVIDER>_API_KEY`, `<PROVIDER>_MODEL_NAME`, `<PROVIDER>_BASE_URL`, and `<PROVIDER>_MODELS`
- **Active Profile Fallback**: Active profile maintains existing AGENTSCOPE_* environment variable compatibility
- **Duplicate Detection**: Prevents model ID conflicts across different providers
- **Atomic Updates**: Thread-safe catalog swapping with lock protection for concurrent access

### Model Resolution Flow
```mermaid
sequenceDiagram
participant Client as "Client"
participant Gateway as "Platform Gateway"
participant API as "Agent Platform API"
participant Catalog as "ModelCatalog"
participant Kernel as "RuntimeKernel"
Note over Client,Kernel : Model Selection Flow
Client->>Gateway : GET /api/v1/models
Gateway->>API : GET /api/v2/models
API->>Catalog : public_models()
Catalog-->>API : {models : [...], default : string}
API-->>Gateway : Public model catalog
Gateway-->>Client : Credential-safe model list
Client->>Gateway : POST /api/v1/chat {message, model : "qwen-plus"}
Gateway->>API : Forward with model selection
API->>Catalog : get("qwen-plus")
Catalog-->>API : ModelCatalogEntry
API->>Kernel : execute(..., model_id="qwen-plus")
Kernel->>Kernel : normalize_model_id("qwen-plus")
Kernel-->>API : Normalized model ID
API-->>Client : Response with selected model
```

**Diagram sources**
- [routes.py:534-544](file://products/agent-platform/src/agent_service/api/v2/routes.py#L534-L544)
- [model_catalog.py:168-174](file://products/agent-platform/src/agent_service/services/model_catalog.py#L168-L174)
- [runtime_kernel.py:248-261](file://products/agent-platform/src/agent_service/runtime_kernel.py#L248-261)

### Configuration Examples
- **OpenAI**: Set `OPENAI_API_KEY`, optionally `OPENAI_MODEL_NAME`, `OPENAI_BASE_URL`, `OPENAI_MODELS`
- **DashScope**: Set `DASHSCOPE_API_KEY`, optionally `DASHSCOPE_MODEL_NAME`, `DASHSCOPE_BASE_URL`, `DASHSCOPE_MODELS`
- **DeepSeek**: Set `DEEPSEEK_API_KEY`, optionally `DEEPSEEK_MODEL_NAME`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODELS`
- **Luban**: Set `LUBAN_API_KEY` and mandatory `LUBAN_BASE_URL` for self-hosted OpenAI-compatible endpoints
- **Active Profile**: Existing `AGENTSCOPE_API_KEY`, `AGENTSCOPE_MODEL_NAME`, `AGENTSCOPE_BASE_URL` remain compatible

### Operator Portal Integration
The operator portal UI displays models grouped by provider with credential-gated discovery:
- **Grouped Display**: Models organized under provider labels (OpenAI, DashScope, DeepSeek, Luban)
- **Default Selection**: Deploy-time default model pre-selected when multiple models available
- **Single Model Mode**: Fixed label display when only one model is configured
- **Graceful Degradation**: Selector hides when catalog fetch fails, chat continues working
- **Test Coverage**: Comprehensive tests for grouping, fallback behavior, and single model scenarios

**Section sources**
- [model_catalog.py:1-331](file://products/agent-platform/src/agent_service/services/model_catalog.py#L1-L331)
- [routes.py:534-544](file://products/agent-platform/src/agent_service/api/v2/routes.py#L534-L544)
- [models.py:19-45](file://products/platform-gateway/src/platform_gateway/api/routes/models.py#L19-L45)
- [ModelSelect.tsx:20-71](file://products/operator-portal/web-ui/app/src/chat/ModelSelect.tsx#L20-L71)
- [models.ts:1-30](file://products/operator-portal/web-ui/app/src/api/models.ts#L1-L30)
- [test_model_catalog.py:196-244](file://products/agent-platform/tests/test_model_catalog.py#L196-L244)

## Live Model Discovery Service

### Overview
The live model discovery service implements background task management for automatic model discovery from configured providers. It provides a fail-soft ladder system that falls back through multiple tiers (live fetch → in-memory cache → Postgres cache → curated series) to ensure continuous model availability even when providers are temporarily unavailable.

### Architecture
```mermaid
classDiagram
class ModelDiscoveryService {
+_settings : RuntimeSettings
+_credentials : tuple[ProviderCredentials, ...]
+_cache : PostgresDiscoveryCache
+_last_good : dict[RuntimeProvider, tuple[str, ...]]
+refresh_once()
+run_loop()
+_resolve_series(credentials)
+_apply_filter(credentials, models)
}
class PostgresDiscoveryCache {
+_db_url : str
+_bootstrapped : bool
+read(provider) : tuple[str, ...] | None
+write(provider, models) : None
+_connect() : Any
}
class ModelCatalog {
+refresh_catalog(series_map, settings) : bool
+entries : tuple
+public_models() : dict
}
class ProviderCredentials {
+provider : RuntimeProvider
+api_key : str
+base_url : str | None
+default_model : str
+models_override : tuple[str, ...] | None
}
ModelDiscoveryService --> PostgresDiscoveryCache : "uses"
ModelDiscoveryService --> ModelCatalog : "updates"
ModelDiscoveryService --> ProviderCredentials : "processes"
```

**Diagram sources**
- [model_discovery.py:196-283](file://products/agent-platform/src/agent_service/services/model_discovery.py#L196-L283)
- [model_discovery.py:69-153](file://products/agent-platform/src/agent_service/services/model_discovery.py#L69-L153)
- [model_catalog.py:283-303](file://products/agent-platform/src/agent_service/services/model_catalog.py#L283-L303)

### Key Features
- **Background Task Management**: Runs as an asyncio task managed by FastAPI lifespan context
- **Periodic Refresh**: Configurable refresh intervals with exponential backoff on failures
- **Fail-Soft Ladder**: Multiple fallback tiers ensure model availability even during provider outages
- **Provider Filtering**: Chat-only model filtering with family prefix restrictions and non-chat modality exclusion
- **Persistent Caching**: Postgres-backed cache for model discovery results across process restarts
- **Atomic Catalog Updates**: Thread-safe catalog swapping with lock protection
- **Metrics Collection**: Comprehensive observability for discovery operations and refresh cycles
- **Graceful Degradation**: Discovery failures don't impact core chat functionality

### Discovery Ladder Flow
```mermaid
sequenceDiagram
participant Disc as "ModelDiscoveryService"
participant Live as "Live Fetch"
participant Memory as "In-Memory Cache"
participant Postgres as "Postgres Cache"
participant Curated as "Curated Series"
Note over Disc,Curated : Discovery Ladder Process
Disc->>Disc : _resolve_series(credentials)
alt Models Override Enabled
Disc->>Curated : force_include_default(models_override, default)
else Discovery Disabled
Disc->>Curated : curated_series(credentials)
else Discovery Enabled
Disc->>Live : fetch_provider_models(credentials)
alt Live Fetch Success
Live-->>Disc : filtered_models
Disc->>Disc : _apply_filter(credentials, models)
Disc->>Disc : update _last_good[provider]
Disc->>Postgres : write(provider, models)
Disc->>Disc : return filtered_models
else Live Fetch Failed
Disc->>Memory : get _last_good[provider]
alt Memory Cache Hit
Memory-->>Disc : cached_models
Disc->>Disc : return cached_models
else Memory Cache Miss
Disc->>Postgres : read(provider)
alt Postgres Cache Hit
Postgres-->>Disc : cached_models
Disc->>Disc : force_include_default(cached, default)
Disc->>Disc : return cached_models
else Postgres Cache Miss
Disc->>Curated : curated_series(credentials)
Curated-->>Disc : curated_models
Disc->>Disc : return curated_models
end
end
end
end
```

**Diagram sources**
- [model_discovery.py:227-264](file://products/agent-platform/src/agent_service/services/model_discovery.py#L227-L264)
- [model_discovery.py:155-193](file://products/agent-platform/src/agent_service/services/model_discovery.py#L155-L193)
- [model_discovery.py:69-153](file://products/agent-platform/src/agent_service/services/model_discovery.py#L69-L153)

### FastAPI Lifespan Integration
The discovery service integrates seamlessly with FastAPI's lifespan management:
- **Startup**: Creates background task and performs initial model discovery
- **Runtime**: Continuously refreshes model catalogs at configured intervals
- **Shutdown**: Gracefully cancels background tasks and cleans up resources
- **Error Handling**: Logs exceptions but never crashes the application

### Provider Filtering Mechanisms
Each provider implements sophisticated filtering to ensure only chat-capable models are discovered:
- **Family Prefix Restrictions**: Models must match provider-specific prefixes (e.g., "gpt-", "qwen", "deepseek")
- **Non-Chat Modality Exclusion**: Filters out embedding, rerank, TTS, audio, image, moderation, transcription, and other non-chat modalities
- **Dated Snapshot Detection**: Automatically excludes dated model snapshots (e.g., "model-2024-01-01")
- **Custom Exclusion Markers**: Provider-specific exclusions for vision, translation, OCR, and other specialized modalities

### Configuration and Environment Variables
- **AGENT_MODEL_DISCOVERY_ENABLED**: Enable/disable discovery (default: true)
- **AGENT_MODEL_DISCOVERY_REFRESH_SECONDS**: Refresh interval in seconds (default: 1800)
- **AGENT_MODEL_DISCOVERY_TIMEOUT_SECONDS**: HTTP timeout for provider /models calls (default: 5.0)
- **SESSION_DB_URL**: Database connection for persistent cache (optional)
- **AGENT_STATE_DB_URL**: Alternative database connection for persistent cache

### Metrics and Observability
The discovery service provides comprehensive metrics:
- **Refresh Counters**: Track refresh attempts and outcomes (override, disabled, live, memory, cache, curated)
- **Model Count Gauges**: Monitor current number of models per provider
- **Error Logging**: Detailed logging for network failures, parsing errors, and database issues
- **Performance Monitoring**: Track refresh cycle duration and cache hit rates

**Section sources**
- [model_discovery.py:1-300](file://products/agent-platform/src/agent_service/services/model_discovery.py#L1-L300)
- [app.py:19-47](file://products/agent-platform/src/agent_service/app.py#L19-L47)
- [metrics.py:188-210](file://products/agent-platform/src/agent_service/core/metrics.py#L188-L210)
- [runtime_settings.py:152-157](file://products/agent-platform/src/agent_service/runtime_settings.py#L152-L157)
- [test_model_discovery.py:1-421](file://products/agent-platform/tests/test_model_discovery.py#L1-L421)

## Dependency Analysis
The service has clear separation of concerns with minimal coupling between layers:
- API depends on schemas and kernel
- Kernel depends on session service, provider registry, evidence store, model catalog, and tools
- Providers are independent implementations registered at runtime
- Session service abstracts storage backend
- Evidence store provides independent persistence layer with dual backend support
- Model catalog provides credential-gated discovery with legacy alias resolution
- **Live discovery service depends on model catalog, provider registry, and runtime settings**
- **FastAPI lifespan manages discovery task lifecycle independently**
- Cross-cutting concerns are injected into the application lifecycle

```mermaid
graph LR
API["API Routes"] --> Kernel["RuntimeKernel"]
Kernel --> Session["SessionService"]
Kernel --> Evidence["EvidenceStore"]
Kernel --> ModelCat["ModelCatalog"]
Kernel --> Registry["ProviderRegistry"]
Kernel --> Tools["GatewayTools"]
Kernel --> Closure["ToolkitClosure"]
Registry --> Base["BaseProvider"]
Base --> OpenAI["OpenAIProvider"]
Base --> DashScope["DashScopeProvider"]
Base --> DeepSeek["DeepSeekProvider"]
Base --> Luban["LubanProvider"]
Session --> Store["SessionStore"]
Session --> Transcript["TranscriptExtractor"]
API --> HITL["ConfirmationRegistry"]
API --> Metrics["Metrics"]
API --> Obs["Observability"]
API --> Tel["Telemetry"]
Closure --> Tools
Evidence --> Metrics
Evidence --> Store
ModelCat --> Metrics
ModelCat --> Registry
ModelDisc["ModelDiscovery"] --> ModelCat
ModelDisc --> Registry
ModelDisc --> Metrics
Lifespan["FastAPI Lifespan"] --> ModelDisc
```

**Updated** The dependency graph now shows the enhanced toolkit registration pattern with per-request trace queues, auto-approval mechanism, v3 streaming support, multi-session workspace foundations, evidence store integration with dual backend support, model catalog service with credential-gated discovery and legacy alias resolution, live model discovery service with background task management, voice-readiness support through input_modality parameter passthrough, and the new Luban provider for self-hosted OpenAI-compatible endpoints.

**Diagram sources**
- [routes.py](file://products/agent-platform/src/agent_service/api/v2/routes.py)
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [session_service.py](file://products/agent-platform/src/agent_service/services/session_service.py)
- [evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [model_catalog.py](file://products/agent-platform/src/agent_service/services/model_catalog.py)
- [model_discovery.py](file://products/agent-platform/src/agent_service/services/model_discovery.py)
- [app.py](file://products/agent-platform/src/agent_service/app.py)
- [registry.py](file://products/agent-platform/src/agent_service/providers/registry.py)
- [base.py](file://products/agent-platform/src/agent_service/providers/base.py)
- [openai.py](file://products/agent-platform/src/agent_service/providers/openai.py)
- [dashscope.py](file://products/agent-platform/src/agent_service/providers/dashscope.py)
- [deepseek.py](file://products/agent-platform/src/agent_service/providers/deepseek.py)
- [luban.py](file://products/agent-platform/src/agent_service/providers/luban.py)
- [session_store.py](file://products/agent-platform/src/agent_service/services/session_store.py)
- [session_transcript.py](file://products/agent-platform/src/agent_service/services/session_transcript.py)
- [hitl_confirmations.py](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py)
- [metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [observability.py](file://products/agent-platform/src/agent_service/core/observability.py)
- [telemetry.py](file://products/agent-platform/src/agent_service/core/telemetry.py)
- [gateway_tools.py](file://products/agent-platform/src/agent_service/tools/gateway_tools.py)

**Section sources**
- [runtime_dependencies.py](file://products/agent-platform/src/agent_service/services/runtime_dependencies.py)

## Performance Considerations
- Streaming responses reduce latency by emitting events incrementally with v3 protocol support
- Connection pooling for provider HTTP clients improves throughput
- Session store caching minimizes I/O overhead
- Async processing for long-running operations prevents blocking
- Metrics collection enables performance monitoring and bottleneck identification
- Request context propagation ensures efficient tracing across components
- Toolkit closure caching reduces overhead for repeated tool invocations within the same request
- Per-request trace queues minimize memory footprint through efficient queue management
- Anti-hallucination guards prevent unnecessary tool discovery when tools are unavailable
- Auto-approval mechanism eliminates permission prompt overhead for vetted read-only tools
- **Workspace Optimization**: Server-side sorting in Postgres backend for efficient session listing
- **TTL-Aware Operations**: All workspace operations respect session TTL to prevent resource leaks
- **Fail-Open Design**: Workspace bookkeeping failures don't impact core chat performance
- **Transcript Extraction**: Best-effort design ensures degraded performance without errors
- **Voice Readiness**: Input modality parameter adds minimal overhead as metadata-only processing
- **Evidence Store Optimization**: Size-capped storage with automatic eviction prevents memory bloat
- **Dual Backend Failover**: Postgres unavailability falls back to in-memory for resilience
- **Evidence Metrics**: Comprehensive monitoring of evidence persistence operations and truncation events
- **Model Catalog Optimization**: Startup-derived catalog with in-memory lookup for fast model resolution
- **Legacy Alias Resolution**: Efficient provider name to concrete model mapping for backward compatibility
- **Credential-Gated Discovery**: Minimal overhead for model enumeration without exposing sensitive configuration
- **Live Discovery Optimization**: Background task with configurable refresh intervals and exponential backoff
- **Cache Tier Performance**: Multi-tier caching (memory, Postgres) reduces provider API calls
- **Atomic Updates**: Lock-protected catalog swaps prevent partial updates during refresh cycles
- **Provider Filtering Efficiency**: Family prefix matching and marker-based filtering minimize false positives
- **Multi-Model Runtime**: Priority-based model resolution with minimal overhead through session caching
- **Model Pinning**: TTL-aware storage prevents excessive writes while maintaining session affinity
- **Error Handling**: Fast-fail model validation prevents unnecessary processing of invalid requests
- **Luban Provider Optimization**: Self-hosted endpoints with strict bearer token requirements and no default base URL

**Updated** Performance considerations now include multi-session workspace optimizations, server-side sorting capabilities, TTL-aware operations, fail-open workspace bookkeeping that doesn't impact core chat performance, evidence store optimization with size-capped storage and automatic eviction, dual backend failover for resilience, voice-readiness support with minimal overhead through metadata-only processing, model catalog optimization with startup-derived catalog and efficient legacy alias resolution, live model discovery optimization with background task management, multi-tier caching strategies, atomic catalog updates with lock protection, multi-model runtime optimization with priority-based resolution and session-based caching, and Luban provider optimization for self-hosted OpenAI-compatible endpoints with strict security requirements.

## Troubleshooting Guide
Common issues and resolutions:
- Provider connection failures: Verify API keys, endpoints, and network connectivity
- Session persistence errors: Check storage backend availability and permissions
- Streaming interruptions: Monitor network stability and timeout configurations
- Performance degradation: Analyze metrics for slow providers or storage bottlenecks
- Configuration errors: Validate environment variables and runtime settings
- Delegated token issues: Verify token validity, expiration, and permission scope
- Tool invocation failures: Check bearer token relay and tool-specific authentication
- Empty toolkit issues: Ensure AgentScope 2.x toolkit registration is working correctly
- Hallucination problems: Verify NO_TOOLS_NOTICE injection when tools are unavailable
- Trace queue issues: Check per-request queue creation and event emission
- Headless stream stalls: Verify auto-approval configuration for vetted read-only tools
- Permission prompt issues: Check if tools are properly configured as read-only and on allow-list
- **Workspace Issues**: Verify session store backend connectivity and workspace bookkeeping operations
- **Transcript Problems**: Check kernel state snapshot availability and transcript extraction logs
- **HITL Issues**: Verify confirmation registry state and TTL configuration
- **Session Listing**: Check user session filtering and workspace ordering logic
- **Voice Readiness Issues**: Validate input_modality parameter acceptance and Literal type validation
- **Modality Validation**: Ensure 'text' and 'voice' values are accepted, invalid values return 422
- **Parity Issues**: Verify consistent behavior between POST /chat and GET /chat/stream endpoints
- **Evidence Store Issues**: Check backend availability, size limits, and evidence persistence metrics
- **Evidence Retrieval**: Verify evidence store connectivity and session evidence availability
- **Evidence Eviction**: Monitor evidence truncation metrics and adjust size limits as needed
- **Postgres Evidence**: Validate database connectivity and table schema for evidence storage
- **Model Catalog Issues**: Verify provider API key configuration and model series enumeration
- **Model Selection Errors**: Check model ID validation and legacy alias resolution
- **Portal Model Display**: Verify grouped model display and provider categorization
- **Discovery Failures**: Check platform gateway proxy configuration and upstream model endpoint
- **Live Discovery Issues**: Verify discovery service background task status and refresh intervals
- **Provider Filtering**: Check family prefix configurations and exclusion markers for chat-only models
- **Cache Tier Problems**: Validate Postgres connectivity and cache persistence operations
- **Network Timeouts**: Adjust discovery timeout settings for slow or unreliable providers
- **Metrics Monitoring**: Check discovery refresh counters and model count gauges for operational insights
- **Multi-Model Runtime Issues**: Verify model resolution hierarchy and session pinning functionality
- **Model Pinning Problems**: Check session store backend connectivity and model persistence
- **Resolution Failures**: Validate explicit model requests against credential-gated catalog
- **Fallback Behavior**: Test graceful degradation from invalid pinned models to defaults
- **Error Responses**: Verify 422 status codes for unknown models and proper error messages
- **Luban Provider Issues**: Verify LUBAN_BASE_URL configuration and bearer token authentication
- **Self-Hosted Endpoint Problems**: Check network connectivity to self-hosted OpenAI-compatible servers
- **Luban Model Discovery**: Validate family prefix filtering and non-chat modality exclusion

Debugging utilities:
- Health check endpoints for service status
- Structured logging with correlation IDs
- Metrics endpoints for operational insights
- Telemetry traces for request flow analysis
- Token validation endpoints for debugging delegated token flow
- Tool schema inspection for verifying toolkit registration
- Trace event monitoring for audit trail analysis
- Environment variable inspection for auto-allow-list configuration
- **Workspace Monitoring**: Check session store backend status and workspace operation metrics
- **Transcript Debugging**: Verify kernel state snapshot availability and transcript extraction logs
- **HITL Debugging**: Monitor confirmation registry state and parked confirmation lifecycle
- **Session Audit**: Review audit trail for session workspace operations
- **Voice Readiness Debugging**: Validate input_modality parameter handling and modality-specific behaviors
- **Evidence Store Debugging**: Check evidence store backend status, size limits, and persistence metrics
- **Evidence Panel Debugging**: Verify evidence turn retrieval and evidence schema compliance
- **Model Catalog Debugging**: Verify provider configuration, model enumeration, and legacy alias resolution
- **Portal Model Debugging**: Check model selector grouping, default selection, and catalog fetch behavior
- **Live Discovery Debugging**: Monitor background task status, refresh cycles, and cache tier performance
- **Provider Filter Debugging**: Validate family prefix matching and non-chat modality exclusion logic
- **Cache Tier Debugging**: Check Postgres connectivity, cache persistence, and fallback behavior
- **Multi-Model Runtime Debugging**: Monitor model resolution decisions and session pinning operations
- **Model Resolution Debugging**: Verify priority hierarchy execution and fallback behavior
- **Error Handling Debugging**: Check 422 status codes and error message formatting for model validation
- **Luban Provider Debugging**: Validate LUBAN_BASE_URL configuration and bearer token authentication flow
- **Self-Hosted Endpoint Debugging**: Check network connectivity and OpenAI-compatible API responses

**Updated** Troubleshooting guide now includes multi-session workspace troubleshooting, transcript extraction debugging strategies, HITL confirmation registry diagnostics, workspace operation monitoring, evidence store troubleshooting with dual backend support, voice-readiness debugging with input_modality parameter validation and parity testing, comprehensive evidence persistence monitoring and debugging, model catalog troubleshooting with provider configuration validation, model selection debugging, and operator portal model display verification, plus live model discovery troubleshooting with background task monitoring, provider filtering validation, cache tier diagnostics, and discovery performance optimization, and multi-model runtime troubleshooting with model resolution debugging and session pinning diagnostics, and Luban provider troubleshooting with self-hosted endpoint configuration and bearer token authentication.

**Section sources**
- [metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [observability.py](file://products/agent-platform/src/agent_service/core/observability.py)
- [telemetry.py](file://products/agent-platform/src/agent_service/core/telemetry.py)
- [request_context.py](file://products/agent-platform/src/agent_service/core/request_context.py)

## Conclusion
The Agent Platform Service provides a robust foundation for AI agent orchestration with multi-provider support, durable session management, and comprehensive observability. Its modular architecture enables easy customization and scaling while maintaining high performance and reliability.

**Updated** The service now includes comprehensive multi-model runtime capability with per-turn model selection, session-based model pinning, credential-gated model catalogs, live model discovery with background task management, sophisticated error handling for model resolution failures, and enhanced operational visibility through detailed logging and metrics collection. The addition of the Luban provider enables self-hosted OpenAI-compatible endpoints with strict security requirements. These enhancements strengthen the platform's flexibility, enable dynamic model management, provide detailed operational visibility, and maintain the performance characteristics that make it suitable for production AI operations.

## Appendices

### Practical Examples

#### Agent Development
- Define agent behavior through conversation templates and tool integrations
- Use the runtime kernel to manage agent lifecycle and state with AgentScope 2.x compatibility
- Implement custom tools for domain-specific operations with proper toolkit registration
- Leverage delegated tokens for secure tool execution with per-request isolation

#### Provider Customization
- Extend the base provider interface for new model backends using AgentScope 2.x patterns
- Register custom providers in the registry with proper model construction
- Configure provider-specific settings through environment variables with enhanced parameter support

#### Integration Patterns
- Use the API gateway for unified access to multiple agents with v3 streaming support
- Implement policy enforcement for security and compliance with audit trail integration
- Leverage streaming responses for real-time interactions with tool_call/tool_result frames
- Utilize per-request toolkit closures for secure multi-tenant scenarios with comprehensive audit trails

#### Anti-Hallucination Strategies
- Configure NO_TOOLS_NOTICE thresholds based on operational requirements
- Monitor tool discovery success rates and adjust accordingly
- Implement fallback mechanisms when tools are unavailable
- Use evidence panels to visualize tool usage and prevent fabrication

#### Auto-Approval Configuration
- Customize the allow-list via `AGENT_GATEWAY_TOOL_AUTO_ALLOW` environment variable
- Ensure tools are properly marked as read-only in tool definitions
- Monitor tool execution logs to verify auto-approval is working correctly
- Regularly review and update the allow-list based on security policies

#### Multi-Session Workspace Operations
- **Session Management**: Create, list, and delete sessions with proper authorization
- **Workspace Organization**: Use server-minted titles and last_active_at timestamps for organization
- **Transcript Access**: Retrieve conversation history from kernel state snapshots
- **Evidence Retrieval**: Load persisted tool execution evidence for session details
- **HITL Integration**: Handle parked confirmations and interactive workflows
- **Audit Compliance**: Monitor workspace operations through audit trails

#### Voice Readiness Implementation
- **Input Modality**: Use input_modality parameter for voice-based interactions
- **Consistent Behavior**: Ensure same policy enforcement regardless of input modality
- **Testing**: Validate both 'text' and 'voice' modalities work consistently
- **Backward Compatibility**: Default to 'text' modality for existing clients
- **Audit Trail**: Track input modality in audit events for monitoring and analysis

#### Evidence Store Configuration
- **Backend Selection**: Configure AGENT_STATE_STORE_BACKEND for memory or postgres
- **Database Setup**: Set AGENT_STATE_DB_URL for Postgres evidence persistence
- **Size Limits**: Adjust AGENT_EVIDENCE_ENTRY_MAX_CHARS and AGENT_EVIDENCE_SESSION_MAX_BYTES
- **TTL Configuration**: Set AGENT_STATE_TTL_SECONDS for evidence row expiration
- **Monitoring**: Track evidence persistence metrics and truncation events
- **Failover**: Verify graceful fallback to in-memory when Postgres is unavailable

#### Model Catalog Configuration
- **Provider Setup**: Configure `<PROVIDER>_API_KEY` for each enabled provider
- **Model Series**: Set `<PROVIDER>_MODELS` to override curated model lists
- **Active Profile**: Existing `AGENTSCOPE_*` variables remain compatible for single-provider deployments
- **Portal Integration**: Verify grouped model display and default selection in operator portal
- **Legacy Compatibility**: Test bare provider name aliases for backward compatibility
- **Discovery Testing**: Validate credential-gated model enumeration through platform gateway

#### Live Model Discovery Configuration
- **Enable Discovery**: Set `AGENT_MODEL_DISCOVERY_ENABLED=true` to activate background discovery
- **Refresh Interval**: Configure `AGENT_MODEL_DISCOVERY_REFRESH_SECONDS` for optimal refresh frequency
- **Timeout Settings**: Adjust `AGENT_MODEL_DISCOVERY_TIMEOUT_SECONDS` for slow providers
- **Database Cache**: Set `SESSION_DB_URL` or `AGENT_STATE_DB_URL` for persistent model caching
- **Provider Filtering**: Verify family prefix configurations and exclusion markers for chat-only models
- **Monitoring**: Check discovery metrics and refresh logs for operational insights
- **Fallback Testing**: Validate cache tier behavior during provider outages

#### Multi-Model Runtime Configuration
- **Per-Turn Selection**: Include `model` parameter in chat requests for explicit model selection
- **Session Pinning**: Model selections automatically persist across turns within a session
- **Fallback Behavior**: Invalid pinned models gracefully degrade to default models
- **Error Handling**: Unknown models return 422 status with descriptive error messages
- **Validation**: All model selections must exist in credential-gated catalog
- **Audit Trail**: Model resolution decisions logged with request and session context

#### Luban Provider Configuration
- **Self-Hosted Setup**: Configure `LUBAN_API_KEY` and mandatory `LUBAN_BASE_URL` for self-hosted OpenAI-compatible endpoints
- **Bearer Token Authentication**: Ensure proper bearer token setup for self-hosted model servers
- **Model Selection**: Use `LUBAN_MODEL_NAME` or `LUBAN_MODELS` to specify served model identifiers
- **Endpoint Validation**: Verify network connectivity to self-hosted endpoints
- **Security**: Confirm strict bearer token requirements are enforced
- **Integration**: Test with popular self-hosted solutions like Ollama, vLLM, and llama.cpp

**Updated** Practical examples now include guidance on leveraging AgentScope 2.x toolkit registration, anti-hallucination guards, auto-approval mechanism, v3 streaming protocols, per-request trace queues, comprehensive multi-session workspace operations, evidence store configuration and management, model catalog setup with multi-provider support, live model discovery configuration with background task management, provider filtering mechanisms, cache tier optimization, atomic catalog updates with lock protection, multi-model runtime configuration with per-turn selection and session-based pinning, and Luban provider configuration for self-hosted OpenAI-compatible endpoints with complete operator workflow management.

**Section sources**
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [registry.py](file://products/agent-platform/src/agent_service/providers/registry.py)
- [base.py](file://products/agent-platform/src/agent_service/providers/base.py)
- [routes.py](file://products/agent-platform/src/agent_service/api/v2/routes.py)
- [session_service.py](file://products/agent-platform/src/agent_service/services/session_service.py)
- [session_store.py](file://products/agent-platform/src/agent_service/services/session_store.py)
- [session_transcript.py](file://products/agent-platform/src/agent_service/services/session_transcript.py)
- [hitl_confirmations.py](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py)
- [evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [model_catalog.py](file://products/agent-platform/src/agent_service/services/model_catalog.py)
- [model_discovery.py](file://products/agent-platform/src/agent_service/services/model_discovery.py)
- [app.py](file://products/agent-platform/src/agent_service/app.py)
- [gateway_tools.py](file://products/agent-platform/src/agent_service/tools/gateway_tools.py)
- [v2.py](file://products/agent-platform/src/agent_service/schemas/v2.py)
- [test_chat_stream_modality.py](file://products/agent-platform/tests/test_chat_stream_modality.py)
- [test_evidence_store.py](file://products/agent-platform/tests/test_evidence_store.py)
- [test_model_catalog.py](file://products/agent-platform/tests/test_model_catalog.py)
- [test_model_discovery.py](file://products/agent-platform/tests/test_model_discovery.py)
- [test_model_switching.py](file://products/agent-platform/tests/test_model_switching.py)
- [session-evidence.schema.json](file://shared/shared-contracts/schemas/session-evidence.schema.json)
- [model-catalog.schema.json](file://shared/shared-contracts/schemas/model-catalog.schema.json)
- [luban.py](file://products/agent-platform/src/agent_service/providers/luban.py)