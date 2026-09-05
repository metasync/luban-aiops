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
- [confirmation_records.py](file://products/agent-platform/src/agent_service/services/confirmation_records.py)
- [evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [model_catalog.py](file://products/agent-platform/src/agent_service/services/model_catalog.py)
- [model_discovery.py](file://products/agent-platform/src/agent_service/services/model_discovery.py)
- [runtime_service.py](file://products/agent-platform/src/agent_service/services/runtime_service.py)
- [runtime_dependencies.py](file://products/agent-platform/src/agent_service/services/runtime_dependencies.py)
- [gateway_tools.py](file://products/agent-platform/src/agent_service/tools/gateway_tools.py)
- [execution_worker_client.py](file://products/agent-platform/src/agent_service/services/execution_worker_client.py)
- [execution_records.py](file://products/agent-platform/src/agent_service/services/execution_records.py)
- [operation_documents.py](file://products/agent-platform/src/agent_service/services/operation_documents.py)
- [shift_summary.py](file://products/agent-platform/src/agent_service/services/shift_summary.py)
- [document_prose.py](file://products/agent-platform/src/agent_service/services/document_prose.py)
- [incident_client.py](file://products/agent-platform/src/agent_service/services/incident_client.py)
- [incident_report.py](file://products/agent-platform/src/agent_service/services/incident_report.py)
- [flow_approvals.py](file://products/agent-platform/src/agent_service/services/flow_approvals.py)
- [handoff.py](file://products/execution-runtime/src/execution_runtime/api/routes/handoff.py)
- [models.py](file://products/platform-gateway/src/platform_gateway/api/routes/models.py)
- [gateway_service.py](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py)
- [documents.py](file://products/platform-gateway/src/platform_gateway/api/routes/documents.py)
- [incident_client.py](file://products/platform-gateway/src/platform_gateway/services/incident_client.py)
- [api.py](file://products/platform-gateway/src/platform_gateway/schemas/api.py)
- [ModelSelect.tsx](file://products/operator-portal/web-ui/app/src/chat/ModelSelect.tsx)
- [models.ts](file://products/operator-portal/web-ui/app/src/api/models.ts)
- [DocumentsView.tsx](file://products/operator-portal/web-ui/app/src/views/workspace/DocumentsView.tsx)
- [chat.py](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py)
- [usePendingDecisionPoll.ts](file://products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts)
- [decoder.ts](file://products/operator-portal/web-ui/app/src/stream/decoder.ts)
- [sessions.ts](file://products/operator-portal/web-ui/app/src/api/sessions.ts)
- [test_chat_stream_modality.py](file://products/agent-platform/tests/test_chat_stream_modality.py)
- [test_evidence_store.py](file://products/agent-platform/tests/test_evidence_store.py)
- [test_model_catalog.py](file://products/agent-platform/tests/test_model_catalog.py)
- [test_model_discovery.py](file://products/agent-platform/tests/test_model_discovery.py)
- [test_model_switching.py](file://products/agent-platform/tests/test_model_switching.py)
- [test_confirmation_records.py](file://products/agent-platform/tests/test_confirmation_records.py)
- [test_session_workspace.py](file://products/agent-platform/tests/test_session_workspace.py)
- [test_execution_worker_client.py](file://products/agent-platform/tests/test_execution_worker_client.py)
- [test_execution_records.py](file://products/agent-platform/tests/test_execution_records.py)
- [test_runtime_settings.py](file://products/agent-platform/tests/test_runtime_settings.py)
- [test_operation_documents.py](file://products/agent-platform/tests/test_operation_documents.py)
- [test_shift_summary.py](file://products/agent-platform/tests/test_shift_summary.py)
- [test_document_prose.py](file://products/agent-platform/tests/test_document_prose.py)
- [test_documents.py](file://products/agent-platform/tests/test_documents.py)
- [test_documents_repository.py](file://products/platform-gateway/tests/test_documents_repository.py)
- [test_flow_approvals.py](file://products/agent-platform/tests/test_flow_approvals.py)
- [spec.md](file://docs/specs/SPEC-035-decision-sync-arrival-polish/spec.md)
- [decision-sync-release-notes.md](file://docs/agentic-aiops-platform/release-notes/2026-08-26-decision-sync-arrival-polish.md)
- [SPEC-038-isolated-execution-worker/spec.md](file://docs/specs/SPEC-038-isolated-execution-worker/spec.md)
- [SPEC-039-operations-document-repository/spec.md](file://docs/specs/SPEC-039-operations-document-repository/spec.md)
- [SPEC-041-documents-readability-and-digest-reference/spec.md](file://docs/specs/SPEC-041-documents-readability-and-digest-reference/spec.md)
- [SPEC-043-incident-report-document-type/spec.md](file://docs/specs/SPEC-043-incident-report-document-type/spec.md)
- [SPEC-050-browser-tools-expansion-and-samples/spec.md](file://docs/specs/SPEC-050-browser-tools-expansion-and-samples/spec.md)
- [document-read-audit-integrity.md](file://docs/agentic-aiops-platform/release-notes/2026-08-27-document-read-audit-integrity.md)
- [documents-readability-release-notes.md](file://docs/agentic-aiops-platform/release-notes/2026-08-28-documents-readability-and-digest-reference.md)
- [incident-report-release-notes.md](file://docs/agentic-aiops-platform/release-notes/2026-08-29-incident-report-document-type.md)
- [session-evidence.schema.json](file://shared/shared-contracts/schemas/session-evidence.schema.json)
- [model-catalog.schema.json](file://shared/shared-contracts/schemas/model-catalog.schema.json)
- [operation-document.schema.json](file://shared/shared-contracts/schemas/operation-document.schema.json)
- [pyproject.toml](file://products/agent-platform/pyproject.toml)
- [Dockerfile](file://products/agent-platform/Dockerfile)
- [README.md](file://products/agent-platform/README.md)
</cite>

## Update Summary
**Changes Made**
- Added comprehensive flow authority management with 240+ lines of enhanced runtime kernel integration including build_flow_request function, flow approval system integration, and TTL-based flow authorities
- Integrated new flow_approvals.py service (244 lines) implementing session-scoped flow context and approval tracking with FlowContextStore and FlowApprovalStore
- Enhanced execution signing capabilities with flow request building for isolated tool execution workflows
- Added browser write tools classification and BROWSER_WRITE_TOOLS constant for proper risk assessment
- Updated middleware stack to include flow signing capability through GatewayPermissionMiddleware
- Implemented process-wide singletons for flow contexts and approvals with TTL-based expiration handling

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Document Repository Service](#document-repository-service)
7. [Incident Report Document Type](#incident-report-document-type)
8. [Shift Summary Digest Assembly](#shift-summary-digest-assembly)
9. [Optional Prose Generation](#optional-prose-generation)
10. [Document API Endpoints](#document-api-endpoints)
11. [Execution Worker Integration](#execution-worker-integration)
12. [Multi-Session Operator Workspace](#multi-session-operator-workspace)
13. [Session Store Enhancements](#session-store-enhancements)
14. [Enhanced Transcript Reconstruction](#enhanced-transcript-reconstruction)
15. [HITL Confirmation Registry Integration](#hitl-confirmation-registry-integration)
16. [Flow Authority Management](#flow-authority-management)
17. [Enhanced Streaming Architecture](#enhanced-streaming-architecture)
18. [Voice Readiness Support](#voice-readiness-support)
19. [Per-Request Trace Queues](#per-request-trace-queues)
20. [Delegated Token Management](#delegated-token-management)
21. [Evidence Store Service](#evidence-store-service)
22. [Model Catalog Service](#model-catalog-service)
23. [Live Model Discovery Service](#live-model-discovery-service)
24. [Multi-Model Runtime Capability](#multi-model-runtime-capability)
25. [Decision Sync Robustness](#decision-sync-robustness)
26. [Browser Tool Surface Expansion](#browser-tool-surface-expansion)
27. [Dependency Analysis](#dependency-analysis)
28. [Performance Considerations](#performance-considerations)
29. [Troubleshooting Guide](#troubleshooting-guide)
30. [Conclusion](#conclusion)
31. [Appendices](#appendices)

## Introduction
The Agent Platform Service is the core orchestration engine of the Luban AIOps Platform. It provides a runtime kernel for agent execution, a provider registry for multi-model backends (OpenAI, DashScope, DeepSeek, and Luban), and robust session management with durable storage. The service exposes REST APIs for agent interactions, streaming responses, and configuration management, enabling scalable and observable AI operations across diverse model providers.

**Updated** The service now includes comprehensive multi-model runtime capability with per-turn model selection, session-based model pinning, credential-gated model catalogs, live model discovery with background task management, sophisticated error handling for model resolution failures, and enhanced operational visibility through detailed logging and metrics collection. **Additionally, the service now features a complete document repository system that enables operators to create durable, typed operation documents with deterministic digests assembled from multiple data sources, optional AI-generated prose summaries with AI-generated one-line blurbs, role-based access controls, and deterministic counts-only summaries computed at creation time.** The addition of the Luban provider enables self-hosted OpenAI-compatible endpoints with strict bearer token requirements. **The enhanced confirmation record storage layer provides turn_index field support for precise confirmation card anchoring, idempotent resolution with SQL-level guards, improved startup sweep scoping to prevent sibling replica interference, and better error handling for concurrent approval attempts with structured 409 responses.** **Critical Security Fix v0.21.1**: Implemented envelope-only document listings for GET /documents endpoint, ensuring cross-owner reads are properly audited by stripping sensitive fields from list responses while maintaining full content access through single-document fetch endpoints. **SPEC-041 Enhancement**: Added deterministic counts-only document summaries computed from handover skeletons at creation time, stored in the operation documents table with PostgreSQL migration support, and surfaced in envelope-only list responses without breaking security posture. **v0.23.3 Enhancement**: Added AI-generated one-line blurbs extracted from prose responses using SUMMARY marker format, providing operator-friendly briefings with bounded character limits and robust parsing logic. **SPEC-043 Enhancement**: Added incident report document type support with dedicated incident service integration, dual-action authorization gates, and structured error handling for incident-specific workflows. **SPEC-050 Enhancement**: Enhanced browser tool surface with expanded write-tier operations, improved pending decision polling, and better transcript handling for browser interaction tools including web.click, web.type, web.select, web.press_key, and web.upload_file with human-readable element descriptions. **NEW FLOW AUTHORITY MANAGEMENT**: Added comprehensive flow authority management with 240+ lines of enhanced runtime kernel integration including build_flow_request function, flow approval system integration, and TTL-based flow authorities for secure isolated tool execution workflows.

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
- **Document repository service with persistent typed documents, role-based access controls, deterministic summary generation, and AI-generated blurbs**
- **Incident report service with incident service client, digest assembly, and dual-action authorization**
- **Shift summary digest assembly from multiple durable stores with handover skeleton computation**
- **Optional prose generation with fail-soft behavior, prompt safety, and AI-generated blurb extraction**
- **Flow authority management with session-scoped flow context and approval tracking**
- Execution worker client for isolated tool execution with fail-closed behavior
- Execution record persistence for signed execution lifecycle tracking
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
subgraph "Documents"
op_docs["services/operation_documents.py"]
shift_sum["services/shift_summary.py"]
doc_prose["services/document_prose.py"]
inc_client["services/incident_client.py"]
inc_report["services/incident_report.py"]
end
subgraph "Flow Authorities"
flow_approvals["services/flow_approvals.py"]
flow_contexts["FlowContextStore"]
flow_approvals_store["FlowApprovalStore"]
end
subgraph "Execution"
exec_worker["services/execution_worker_client.py"]
exec_records["services/execution_records.py"]
exec_runtime["execution_runtime/api/routes/handoff.py"]
end
subgraph "Confirmation Records"
confirm_store["services/confirmation_records.py"]
confirm_schema["schemas/confirmation.schema.json"]
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
routes_v2 --> confirm_store
routes_v2 --> op_docs
routes_v2 --> shift_sum
routes_v2 --> doc_prose
routes_v2 --> inc_client
routes_v2 --> inc_report
kernel --> gw_tools
kernel --> ev_store
kernel --> model_cat
kernel --> exec_worker
kernel --> exec_records
kernel --> flow_approvals
kernel --> flow_contexts
kernel --> flow_approvals_store
gw_tools --> exec_worker
exec_worker --> exec_runtime
model_disc --> model_cat
ev_store --> metrics
model_cat --> metrics
model_disc --> metrics
confirm_store --> metrics
exec_records --> metrics
op_docs --> metrics
shift_sum --> metrics
doc_prose --> metrics
inc_client --> metrics
inc_report --> metrics
flow_approvals --> metrics
flow_contexts --> metrics
flow_approvals_store --> metrics
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
- [confirmation_records.py](file://products/agent-platform/src/agent_service/services/confirmation_records.py)
- [evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [model_catalog.py](file://products/agent-platform/src/agent_service/services/model_catalog.py)
- [model_discovery.py](file://products/agent-platform/src/agent_service/services/model_discovery.py)
- [gateway_tools.py](file://products/agent-platform/src/agent_service/tools/gateway_tools.py)
- [execution_worker_client.py](file://products/agent-platform/src/agent_service/services/execution_worker_client.py)
- [execution_records.py](file://products/agent-platform/src/agent_service/services/execution_records.py)
- [operation_documents.py](file://products/agent-platform/src/agent_service/services/operation_documents.py)
- [shift_summary.py](file://products/agent-platform/src/agent_service/services/shift_summary.py)
- [document_prose.py](file://products/agent-platform/src/agent_service/services/document_prose.py)
- [incident_client.py](file://products/agent-platform/src/agent_service/services/incident_client.py)
- [incident_report.py](file://products/agent-platform/src/agent_service/services/incident_report.py)
- [flow_approvals.py](file://products/agent-platform/src/agent_service/services/flow_approvals.py)
- [handoff.py](file://products/execution-runtime/src/execution_runtime/api/routes/handoff.py)
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
- **Document Repository**: Provides persistent storage for typed operation documents with draft/published states, owner-only visibility, team-wide published access, envelope-only listings for security, deterministic counts-only summaries computed at creation time, and AI-generated one-line blurbs extracted from prose responses.
- **Incident Report Service**: Provides specialized document type for incident analysis with incident service integration, dual-action authorization gates, and structured error handling for incident-specific workflows.
- **Shift Summary Assembly**: Builds deterministic digests from multiple durable stores with role-based coverage, provenance tracking, and handover skeleton generation for summary computation.
- **Optional Prose Generation**: Generates AI-powered narratives from digests with fail-soft behavior, prompt safety guarantees, and AI-generated blurb extraction using SUMMARY marker format.
- **Flow Authority Management**: Implements session-scoped flow context and approval tracking with TTL-based authorities for secure isolated tool execution workflows.
- **Execution Worker Client**: Provides isolated execution of approved mutating tools through the execution-runtime service with fail-closed behavior, signature verification, and receipt tracking.
- **Execution Record Store**: Persists signed execution request/receipt lifecycle with durable storage and first-write-wins semantics for late arrivals.
- Enhanced Confirmation Records: Provides persistent storage for HITL confirmation lifecycle with turn_index field support, idempotent resolution, startup sweep scoping, and cross-replica consistency guarantees.
- Evidence Store: Provides persistent storage for tool execution evidence with dual backend support and size-capped retention policies.
- Model Catalog: Manages credential-gated model discovery with multi-provider support, legacy alias resolution, and public schema compliance.
- Live Model Discovery: Implements background task management with periodic refresh cycles, provider filtering, and atomic catalog updates.
- **Multi-Model Runtime**: Provides per-turn model selection with session-based pinning and sophisticated resolution hierarchy.
- API Layer: Exposes REST endpoints for chat, sessions, streaming events, model discovery, documents, and health checks with v3 streaming protocol support.
- Cross-Cutting: Configuration, environment, metrics, observability, telemetry, and request-scoped context.

Key responsibilities:
- Lifecycle: Initialize, start, run, and shutdown agents safely with AgentScope 2.x compatibility.
- Conversation: Maintain message history, context, and state per session with workspace organization.
- Evidence Capture: Persist tool_call and tool_result frames with size caps and automatic eviction.
- **Document Creation**: Generate typed operation documents with deterministic digests, optional prose summaries with AI-generated blurbs, deterministic counts-only summaries derived from handover skeletons, and role-based access controls.
- **Incident Report Creation**: Generate incident report documents with incident service integration, dual-action authorization, and structured error handling.
- **Flow Authority Management**: Manage session-scoped flow contexts and approvals with TTL-based expiration for secure isolated tool execution.
- **Role-Based Access**: Enforce owner-only draft visibility and team-wide published document access with envelope-only listings for security.
- **Isolated Execution**: Route approved mutating tool calls to execution-runtime service with signature verification and receipt tracking.
- **Enhanced Confirmation Record Management**: Persist parked confirmations with turn_index anchoring, idempotent resolution, startup sweep scoping, and cross-replica consistency.
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
- **Enhanced Transcript Reconstruction**: Extract conversation history from kernel state snapshots with proper markdown rendering and blank-line block joining.
- HITL Integration: Support human-in-the-loop workflows with parked confirmation management and durable state.
- Observability: Emit structured logs, metrics, and traces for each operation with per-request audit trails.

**Updated** The service now includes comprehensive multi-model runtime capability with per-turn model selection, session-based model pinning, credential-gated model catalogs, live model discovery with background task management, sophisticated error handling for model resolution failures, and enhanced operational visibility through detailed logging and metrics collection. **Additionally, the service now features a complete document repository system that enables operators to create durable, typed operation documents with deterministic digests assembled from multiple data sources, optional AI-generated prose summaries with AI-generated one-line blurbs using SUMMARY marker format, role-based access controls with draft/published states, envelope-only listings for security, and deterministic counts-only summaries computed from handover skeletons at creation time.** The addition of the Luban provider enables self-hosted OpenAI-compatible endpoints with strict bearer token requirements. **The enhanced confirmation record storage layer provides turn_index field support for precise confirmation card anchoring, idempotent resolution with SQL-level guards, improved startup sweep scoping to prevent sibling replica interference, and better error handling for concurrent approval attempts with structured 409 responses.** **Critical Security Fix v0.21.1**: Implemented envelope-only document listings for GET /documents endpoint to ensure cross-owner reads are properly audited by stripping sensitive fields from list responses while maintaining full content access through single-document fetch endpoints. **SPEC-041 Enhancement**: Added deterministic counts-only document summaries computed from handover skeletons at creation time, stored in the operation documents table with PostgreSQL migration support, and surfaced in envelope-only list responses without breaking security posture. **v0.23.3 Enhancement**: Added AI-generated one-line blurbs extracted from prose responses using SUMMARY marker format, providing operator-friendly briefings with bounded character limits and robust parsing logic. **SPEC-043 Enhancement**: Added incident report document type support with dedicated incident service client, dual-action authorization gates requiring both documents:create and incident:read permissions, structured error handling for incident service dependencies, and comprehensive test coverage for incident-specific workflows. **SPEC-050 Enhancement**: Enhanced browser tool surface with expanded write-tier operations including web.click, web.type, web.select, web.press_key, and web.upload_file, with improved pending decision polling and transcript handling for browser interaction tools featuring human-readable element descriptions and proper risk classification. **NEW FLOW AUTHORITY MANAGEMENT**: Added comprehensive flow authority management with 240+ lines of enhanced runtime kernel integration including build_flow_request function, flow approval system integration, and TTL-based flow authorities for secure isolated tool execution workflows with session-scoped flow context and approval tracking.

**Section sources**
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [registry.py](file://products/agent-platform/src/agent_service/providers/registry.py)
- [session_service.py](file://products/agent-platform/src/agent_service/services/session_service.py)
- [routes.py](file://products/agent-platform/src/agent_service/api/v2/routes.py)
- [operation_documents.py](file://products/agent-platform/src/agent_service/services/operation_documents.py)
- [incident_report.py](file://products/agent-platform/src/agent_service/services/incident_report.py)
- [incident_client.py](file://products/agent-platform/src/agent_service/services/incident_client.py)
- [shift_summary.py](file://products/agent-platform/src/agent_service/services/shift_summary.py)
- [document_prose.py](file://products/agent-platform/src/agent_service/services/document_prose.py)
- [flow_approvals.py](file://products/agent-platform/src/agent_service/services/flow_approvals.py)
- [execution_worker_client.py](file://products/agent-platform/src/agent_service/services/execution_worker_client.py)
- [execution_records.py](file://products/agent-platform/src/agent_service/services/execution_records.py)
- [confirmation_records.py](file://products/agent-platform/src/agent_service/services/confirmation_records.py)
- [evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [model_catalog.py](file://products/agent-platform/src/agent_service/services/model_catalog.py)
- [model_discovery.py](file://products/agent-platform/src/agent_service/services/model_discovery.py)
- [app.py](file://products/agent-platform/src/agent_service/app.py)
- [metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [observability.py](file://products/agent-platform/src/agent_service/core/observability.py)
- [telemetry.py](file://products/agent-platform/src/agent_service/core/telemetry.py)
- [request_context.py](file://products/agent-platform/src/agent_service/core/request.request_context.py)

## Architecture Overview
The service follows a layered architecture with enhanced security and anti-hallucination features:
- API layer receives requests, validates payloads, and delegates to the runtime kernel with v3 streaming support, session workspace operations, and voice-readiness parity.
- Runtime kernel coordinates sessions, tools, and provider selection via the registry with AgentScope 2.x toolkit registration, evidence capture, and model normalization.
- Providers implement standardized interfaces to communicate with external model APIs using new model construction patterns.
- Session service persists state using a configurable store with workspace bookkeeping and transcript extraction.
- Evidence store provides persistent storage for tool execution evidence with dual backend support and size-capped retention.
- **Document repository provides persistent storage for typed operation documents with role-based access controls, draft/published states, envelope-only listings for security, deterministic counts-only summaries computed from handover skeletons, and AI-generated one-line blurbs extracted from prose responses**.
- **Incident report service provides specialized document type with incident service integration, dual-action authorization gates, and structured error handling for incident-specific workflows**.
- **Shift summary assembly builds deterministic digests from multiple durable stores with provenance tracking, role-based coverage, and handover skeleton generation for summary computation**.
- **Optional prose generation creates AI-powered narratives from digests with fail-soft behavior, prompt safety guarantees, and AI-generated blurb extraction using SUMMARY marker format**.
- **Flow authority management implements session-scoped flow context and approval tracking with TTL-based authorities for secure isolated tool execution workflows**.
- **Execution worker client provides isolated execution of approved mutating tools through the execution-runtime service with fail-closed behavior and signature verification**.
- **Execution record store persists signed execution request/receipt lifecycle with durable storage and first-write-wins semantics**.
- Enhanced confirmation record store provides durable HITL confirmation lifecycle management with turn_index field support, idempotent resolution, and cross-replica consistency.
- Model catalog provides credential-gated discovery of available models with legacy alias resolution.
- **Multi-model runtime resolves per-turn model selection through priority hierarchy with session-based pinning**.
- **Live discovery service runs background tasks to periodically refresh model catalogs with fail-soft fallback ladder**.
- **FastAPI lifespan manages discovery task lifecycle with proper startup and shutdown handling**.
- Cross-cutting modules provide configuration, metrics, observability, and telemetry with per-request audit trails.

```mermaid
sequenceDiagram
participant Client as "Client"
participant Gateway as "Platform Gateway"
participant API as "FastAPI Routes"
participant Kernel as "RuntimeKernel"
participant Sess as "SessionService"
participant DocStore as "OperationDocumentStore"
participant ShiftSum as "ShiftSummary"
participant IncClient as "IncidentClient"
participant IncReport as "IncidentReport"
participant DocProse as "DocumentProse"
participant FlowAuth as "FlowAuthorityManager"
participant ExecWorker as "ExecutionWorkerClient"
participant ExecRuntime as "ExecutionRuntime"
participant ConfirmStore as "ConfirmationRecordStore"
participant EvStore as "EvidenceStore"
participant ModelCat as "ModelCatalog"
participant Disc as "ModelDiscovery"
participant Reg as "ProviderRegistry"
participant Prov as "ModelProvider"
participant Tools as "GatewayTools"
participant Transcript as "TranscriptExtractor"
participant HITL as "ConfirmationRegistry"
participant Trace as "TraceQueue"
Note over Client,HITL : Incident Report Document Creation with Dual-Action Gate
Client->>Gateway : POST /api/v2/documents {type : "incident_report", incident_id}
Gateway->>API : Forward with authorization headers
API->>API : Enforce documents : create AND incident : read
alt Authorization granted
API->>IncClient : fetch_incident_bundle(incident_id)
IncClient->>IncClient : Validate configuration & timeout
IncClient-->>API : incident bundle or error
API->>IncReport : build_digest(user_id, bundle, can_view_foreign)
IncReport-->>API : digest + provenance + handover skeleton
API->>API : document_summary(digest) - compute counts-only summary
alt include_prose = true
API->>DocProse : generate_prose(kernel, type, digest)
DocProse->>Kernel : _build_model(None)
Kernel-->>DocProse : model instance
DocProse-->>API : prose + blurb + status
else include_prose = false
API-->>API : prose_status = not_requested
end
API->>DocStore : create(document with digest, provenance, prose, summary, blurb)
DocStore-->>API : persisted document
API-->>Gateway : document response
Gateway-->>Client : 201 Created with document
else Authorization denied
API-->>Gateway : 403 Forbidden
Gateway-->>Client : 403 Forbidden
end
Note over ExecWorker : Isolated Execution Flow with Flow Authority
Client->>API : Chat with approved mutating tool
API->>Kernel : execute(message, sessionId, bearerToken)
Kernel->>FlowAuth : Check flow authority for session
FlowAuth-->>Kernel : Flow approval status
Kernel->>ExecWorker : handoff(envelope, arguments, delegated_token)
ExecWorker->>ExecRuntime : POST /api/v1/executions/handoff
ExecRuntime->>ExecRuntime : verify signature & digest
ExecRuntime->>ExecRuntime : execute tool call
ExecRuntime-->>ExecWorker : result + receipt
ExecWorker-->>Kernel : tool result
Kernel->>ExecRecords : save_receipt(receipt)
ExecRecords-->>Kernel : execution recorded
end
```

**Updated** The sequence diagram now shows the complete multi-model runtime capability with per-turn model selection, session-based model pinning, credential-gated validation, and the full model resolution hierarchy (request > pinned > default). **It also includes the incident report document creation flow with dual-action authorization gates requiring both documents:create and incident:read permissions, incident service client integration with structured error handling, and comprehensive degradation strategies for dependency failures.** **It also includes the document repository workflow with shift summary digest assembly, deterministic counts-only summary computation from handover skeletons, optional prose generation with AI-generated blurb extraction using SUMMARY marker format, persistent document storage with role-based access controls, envelope-only listings for security, and PostgreSQL migration support for the summary and blurb columns.** **It also includes the flow authority management with session-scoped flow context and approval tracking, TTL-based authorities for secure isolated tool execution, and comprehensive flow approval system integration.** **It also includes the execution worker integration for isolated tool execution with signature verification and receipt tracking, enhanced confirmation record storage layer with turn_index field support for precise confirmation card anchoring, idempotent resolution, startup sweep scoping to prevent sibling replica interference, and cross-replica consistency guarantees.** **SPEC-050 Enhancement**: Added browser tool surface expansion with improved pending decision polling and transcript handling for write-tier operations, supporting human-readable element descriptions for browser interaction tools.

**Diagram sources**
- [routes.py](file://products/agent-platform/src/agent_service/api/v2/routes.py)
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [session_service.py](file://products/agent-platform/src/agent_service/services/session_service.py)
- [session_store.py](file://products/agent-platform/src/agent_service/services/session_store.py)
- [session_transcript.py](file://products/agent-platform/src/agent_service/services/session_transcript.py)
- [operation_documents.py](file://products/agent-platform/src/agent_service/services/operation_documents.py)
- [incident_report.py](file://products/agent-platform/src/agent_service/services/incident_report.py)
- [incident_client.py](file://products/agent-platform/src/agent_service/services/incident_client.py)
- [shift_summary.py](file://products/agent-platform/src/agent_service/services/shift_summary.py)
- [document_prose.py](file://products/agent-platform/src/agent_service/services/document_prose.py)
- [flow_approvals.py](file://products/agent-platform/src/agent_service/services/flow_approvals.py)
- [execution_worker_client.py](file://products/agent-platform/src/agent_service/services/execution_worker_client.py)
- [execution_records.py](file://products/agent-platform/src/agent_service/services/execution_records.py)
- [handoff.py](file://products/execution-runtime/src/execution_runtime/api/routes/handoff.py)
- [confirmation_records.py](file://products/agent-platform/src/agent_service/services/confirmation_records.py)
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
- **Isolated execution routing for approved mutating tools through execution-runtime service with flow authority management**
- **Enhanced durable confirmation management with turn_index field support, idempotent resolution, and cross-replica consistency**
- **Flow authority management with session-scoped flow context and approval tracking using TTL-based authorities**

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
+_build_confirmation_frame(event, session_id, user_name, toolkit, turn_index)
+_prepare_executions(pending, user_name, confirmed, request_id, session_id)
+_sign_flow_execution(flow_request)
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
class OperationDocumentStore {
<<interface>>
+backend_name : str
+create(document)
+publish(owner_user_id, document_id)
+load(document_id)
+list_for_owner(owner_user_id)
+list_published()
+delete(owner_user_id, document_id)
+is_ready()
}
class IncidentClient {
<<interface>>
+fetch_incident_bundle(settings, request_id, incident_id)
+is_configured(settings)
}
class IncidentReport {
<<interface>>
+build_digest(requester_user_id, bundle, can_view_foreign)
+document_summary(digest)
}
class ShiftSummary {
+build_digest(requester_user_id, session_ids, can_view_foreign)
+validate_session_ids(session_ids)
+_owner_transcript_section(session_id)
+_owner_evidence_section(session_id)
+_confirmation_entry(record, metadata_only)
+_execution_entry(record)
+document_summary(digest)
}
class DocumentProse {
+generate_prose(kernel, document_type, digest)
+build_prose_prompt(document_type, digest)
+parse_blurb(text)
}
class FlowAuthorityManager {
<<interface>>
+check_flow_authorization(session_id)
+record_approval(session_id, confirm_id, owner_user_id, decider_user_id, skill_id, origin, ttl)
+has_approval(session_id)
+clear(session_id)
+clear_all()
}
class ExecutionWorkerClient {
<<interface>>
+backend_name : str
+handoff(request, arguments, delegated_token, settings, request_id)
}
class ExecutionRecordStore {
<<interface>>
+backend_name : str
+save_request(record)
+save_receipt(confirm_id, call_id, receipt, digest_match)
+mark_rejected(confirm_id, call_id, reason, digest_match)
+load_for_session(session_id)
+delete_session(session_id)
+is_ready()
}
class ConfirmationRecordStore {
<<interface>>
+backend_name : str
+save_parked(record)
+mark_resolved(session_id, confirm_id, status, decider_user_id, decision)
+load_for_session(session_id)
+load_record(session_id, confirm_id)
+load_pending_for_session(session_id)
+load_inbox()
+delete_session(session_id)
+is_ready()
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
AgentKernel --> OperationDocumentStore : "persists documents"
AgentKernel --> IncidentClient : "fetches incident bundles"
AgentKernel --> IncidentReport : "assembles incident digests"
AgentKernel --> ShiftSummary : "generates digests"
AgentKernel --> DocumentProse : "generates prose"
AgentKernel --> FlowAuthorityManager : "manages flow authorities"
AgentKernel --> ExecutionWorkerClient : "routes approved mutations"
AgentKernel --> ExecutionRecordStore : "persists execution records"
AgentKernel --> ConfirmationRecordStore : "persists confirmations"
AgentKernel --> EvidenceStore : "persists evidence"
AgentKernel --> ModelCatalog : "resolves models"
AgentKernel --> ProviderRegistry : "uses"
AgentKernel --> GatewayTools : "manages"
FlowAuthorityManager --> FlowContextStore : "manages contexts"
FlowAuthorityManager --> FlowApprovalStore : "manages approvals"
ModelDiscovery --> ModelCatalog : "updates"
ProviderRegistry --> ModelProvider : "manages"
GatewayTools --> ModelProvider : "secure invocation"
GatewayTools --> ExecutionWorkerClient : "isolated execution"
```

**Updated** The runtime kernel now includes AgentScope 2.x toolkit registration, per-request toolkit rebuilding with trace queues, anti-hallucination guard system, auto-approval mechanism for preventing headless stream stalls, enhanced session management methods for multi-session workspace operations and model pinning, evidence capture and persistence for tool execution frames, model normalization for legacy provider name aliases, voice readiness support through input_modality parameter passthrough, **isolated execution routing for approved mutating tools through the execution-runtime service with signature verification, receipt tracking, and comprehensive flow authority management, enhanced durable confirmation management with turn_index field support, idempotent resolution, and cross-replica consistency guarantees, and incident report document type support with dedicated incident service client integration and dual-action authorization enforcement.** **NEW FLOW AUTHORITY MANAGEMENT**: Added comprehensive flow authority management with 240+ lines of enhanced runtime kernel integration including build_flow_request function, flow approval system integration, and TTL-based flow authorities for secure isolated tool execution workflows with session-scoped flow context and approval tracking. **SPEC-050 Enhancement**: Enhanced browser tool surface with improved pending decision polling and transcript handling for write-tier operations, supporting human-readable element descriptions for browser interaction tools like web.click, web.type, web.select, web.press_key, and web.upload_file.

**Diagram sources**
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [session_service.py](file://products/agent-platform/src/agent_service/services/session_service.py)
- [operation_documents.py](file://products/agent-platform/src/agent_service/services/operation_documents.py)
- [incident_report.py](file://products/agent-platform/src/agent_service/services/incident_report.py)
- [incident_client.py](file://products/agent-platform/src/agent_service/services/incident_client.py)
- [shift_summary.py](file://products/agent-platform/src/agent_service/services/shift_summary.py)
- [document_prose.py](file://products/agent-platform/src/agent_service/services/document_prose.py)
- [flow_approvals.py](file://products/agent-platform/src/agent_service/services/flow_approvals.py)
- [execution_worker_client.py](file://products/agent-platform/src/agent_service/services/execution_worker_client.py)
- [execution_records.py](file://products/agent-platform/src/agent_service/services/execution_records.py)
- [confirmation_records.py](file://products/agent-platform/src/agent_service/services/confirmation_records.py)
- [evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [model_catalog.py](file://products/agent-platform/src/agent_service/services/model_catalog.py)
- [model_discovery.py](file://products/agent-platform/src/agent_service/services/model_discovery.py)
- [registry.py](file://products/agent-platform/src/agent_service/providers/registry.py)
- [base.py](file://products/agent-platform/src/agent_service/providers/base.py)
- [gateway_tools.py](file://products/agent-platform/src/agent_service/tools/gateway_tools.py)

**Section sources**
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)

### Flow Authority Management

#### Overview
The flow authority management system provides comprehensive session-scoped flow context and approval tracking with TTL-based authorities for secure isolated tool execution workflows. This enhancement addresses the need for granular control over tool execution flows within specific sessions, ensuring that only authorized operations can proceed within their designated time windows.

#### Key Features
- **Session-Scoped Flow Context**: Each session maintains its own flow context with isolated approval tracking
- **TTL-Based Authorities**: Flow approvals expire after configured time periods to prevent indefinite access
- **Process-Wide Singletons**: Flow contexts and approvals are managed through process-wide singletons for efficient sharing
- **BROWSER_WRITE_TOOLS Classification**: Proper classification of browser interaction tools as write-tier operations requiring confirmation
- **Build Flow Request Function**: Comprehensive flow request building for isolated tool execution workflows
- **Approval Tracking**: Complete tracking of flow approvals with owner and decider user identification
- **Expiration Handling**: Automatic expiration of flow authorities with safe failure modes

#### Flow Approval Architecture
```mermaid
flowchart TD
A["Tool Execution Request"] --> B{"Check Flow Authority"}
B --> C{"Session Has Active Approval?"}
C --> |Yes| D["Execute Tool Call"]
C --> |No| E{"Requires Confirmation?"}
E --> |Yes| F["Park for Human Approval"]
E --> |No| G["Execute Directly"]
F --> H["Await User Decision"]
H --> I{"Decision Received?"}
I --> |Approve| J["Record Flow Approval"]
I --> |Deny| K["Reject Execution"]
J --> L["Set TTL-Based Authority"]
L --> M["Execute Tool Call"]
D --> N["Complete Execution"]
G --> N
K --> O["Return Rejection"]
M --> N
```

**Diagram sources**
- [flow_approvals.py:176-244](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L176-L244)
- [runtime_kernel.py:40-44](file://products/agent-platform/src/agent_service/runtime_kernel.py#L40-L44)

#### Flow Context Store Implementation
The FlowContextStore manages session-scoped flow contexts with comprehensive approval tracking:

```mermaid
sequenceDiagram
participant Client as "Client"
participant Kernel as "RuntimeKernel"
participant FlowStore as "FlowContextStore"
participant ApprovalStore as "FlowApprovalStore"
Note over Client,ApprovalStore : Flow Authority Management
Client->>Kernel : Execute tool with session_id
Kernel->>FlowStore : get(session_id)
FlowStore-->>Kernel : FlowContext or None
alt No active approval
Kernel->>ApprovalStore : has_approval(session_id)
ApprovalStore-->>Kernel : False
Kernel->>Kernel : Park for human approval
Kernel->>ApprovalStore : record_approval(...)
ApprovalStore-->>Kernel : FlowApproval with TTL
Kernel->>Kernel : Set TTL-based authority
else Active approval exists
Kernel->>Kernel : Proceed with execution
end
Kernel-->>Client : Tool execution result
```

**Diagram sources**
- [flow_approvals.py:241-244](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L241-L244)
- [flow_approvals.py:188-208](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L188-L208)

#### TTL-Based Expiration Handling
Flow authorities use TTL-based expiration to ensure temporary access:

```mermaid
flowchart TD
A["Flow Approval Recorded"] --> B["Set approved_at timestamp"]
B --> C["Configure TTL period"]
C --> D{"Check if expired?"}
D --> |No| E["Allow execution"]
D --> |Yes| F["Reject execution"]
E --> G["Execute tool call"]
F --> H["Return unauthorized"]
G --> I["Complete execution"]
H --> J["Log rejection"]
```

**Diagram sources**
- [flow_approvals.py:188-208](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L188-L208)
- [test_flow_approvals.py:168-184](file://products/agent-platform/tests/test_flow_approvals.py#L168-L184)

#### Browser Write Tools Classification
The system includes proper classification for browser interaction tools as write-tier operations:

```mermaid
flowchart TD
A["Browser Tool Invocation"] --> B{"Tool Type?"}
B --> |web.click| C["Write-Tier Operation"]
B --> |web.type| D["Write-Tier Operation"]
B --> |web.select| E["Write-Tier Operation"]
B --> |web.press_key| F["Write-Tier Operation"]
B --> |web.upload_file| G["Write-Tier Operation"]
C --> H["Require Flow Authority"]
D --> H
E --> H
F --> H
G --> H
H --> I["Check Flow Approval"]
I --> J{"Has Active Approval?"}
J --> |Yes| K["Execute Tool"]
J --> |No| L["Park for Approval"]
```

**Diagram sources**
- [flow_approvals.py:40-44](file://products/agent-platform/src/agent_service/runtime_kernel.py#L40-L44)
- [flow_approvals.py:176-244](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L176-L244)

#### Test Coverage
The implementation includes comprehensive test coverage for flow authority scenarios:

- **TTL Expiration Testing**: Validates proper expiration behavior for various TTL values
- **Zero TTL Handling**: Tests that TTL <= 0 disables flow unlock for security
- **Negative TTL Support**: Handles negative TTL values as expired authorities
- **Stale Approval Detection**: Verifies detection of expired approvals based on timestamps
- **Store Operations**: Tests recording, retrieval, and clearing of flow approvals
- **Session Isolation**: Ensures proper isolation between different session contexts

**Section sources**
- [flow_approvals.py:1-244](file://products/agent-platform/src/agent_service/services/flow_approvals.py#L1-L244)
- [runtime_kernel.py:40-44](file://products/agent-platform/src/agent_service/runtime_kernel.py#L40-L44)
- [test_flow_approvals.py:168-201](file://products/agent-platform/tests/test_flow_approvals.py#L168-L201)

### Browser Tool Surface Expansion

#### Overview
The browser tool surface has been significantly expanded to support comprehensive web automation capabilities with enhanced HITL confirmation handling for write-tier operations. This enhancement addresses SPEC-050 by adding support for browser interaction tools including web.click, web.type, web.select, web.press_key, and web.upload_file, with improved pending decision polling and transcript handling for better user experience.

#### Key Features
- **Expanded Tool Surface**: Support for web.click, web.type, web.select, web.press_key, and web.upload_file operations
- **Human-Readable Element Descriptions**: Display hints for browser elements referenced in tool calls, improving operator understanding of pending actions
- **Write-Tier Risk Classification**: Proper classification of browser interaction tools as write-tier operations requiring confirmation
- **Improved Pending Decision Polling**: Enhanced polling mechanisms for browser tool confirmations with better timeout handling
- **Transcript Handling**: Better transcript reconstruction for browser tool operations with proper markdown rendering
- **Element Reference Mapping**: Support for snapshot element references in browser tool parameters with display hints

#### Browser Tool Risk Classification
```mermaid
flowchart TD
A["Browser Tool Invocation"] --> B{"Tool Type?"}
B --> |web.click| C["Write-Tier Operation"]
B --> |web.type| D["Write-Tier Operation"]
B --> |web.select| E["Write-Tier Operation"]
B --> |web.press_key| F["Write-Tier Operation"]
B --> |web.upload_file| G["Write-Tier Operation"]
C --> H["Require HITL Confirmation"]
D --> H
E --> H
F --> H
G --> H
H --> I["Generate Confirmation Request"]
I --> J["Include Display Hint"]
J --> K["Show Human-Readable Description"]
K --> L["Await User Approval"]
```

**Diagram sources**
- [hitl_confirmations.py:76-101](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L76-L101)
- [decoder.ts:78-103](file://products/operator-portal/web-ui/app/src/stream/decoder.ts#L78-L103)

#### Display Hint Implementation
The system now includes human-readable element descriptions for browser interaction tools that reference snapshot elements:

```mermaid
sequenceDiagram
participant Kernel as "Runtime Kernel"
participant HITL as "HITL Registry"
participant UI as "Operator Portal"
Note over Kernel,UI : Browser Tool Confirmation with Display Hint
Kernel->>HITL : Register pending confirmation
HITL->>HITL : Build confirmation payload
HITL->>HITL : Check if browser tool with element ref
alt Browser tool with element reference
HITL->>HITL : Lookup element description from snapshot
HITL->>HITL : Add display_hint to payload
else Regular tool
HITL->>HITL : Standard payload without display hint
end
HITL-->>UI : confirmation_request with display_hint
UI->>UI : Render human-readable description
UI-->>User : Show "Click button 'Submit'" instead of raw parameters
User->>UI : Approve/Deny action
UI-->>Kernel : Decision with confirmation_id
```

**Diagram sources**
- [hitl_confirmations.py:76-101](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L76-L101)
- [decoder.ts:78-103](file://products/operator-portal/web-ui/app/src/stream/decoder.ts#L78-L103)
- [sessions.ts:44-56](file://products/operator-portal/web-ui/app/src/api/sessions.ts#L44-L56)

#### Enhanced Pending Decision Polling
The pending decision polling has been enhanced to better handle browser tool confirmations with improved timeout management and better user feedback:

```mermaid
flowchart TD
A["Browser Tool Requires Confirmation"] --> B["Start Pending Decision Poll"]
B --> C{"Decision Received?"}
C --> |Yes| D["Process Decision"]
C --> |No| E{"Timeout Reached?"}
E --> |No| F["Continue Polling"]
F --> C
E --> |Yes| G["Handle Timeout"]
G --> H["Show Timeout Message"]
H --> I["Allow Retry"]
D --> J["Resume Tool Execution"]
J --> K["Update Transcript"]
K --> L["Complete Operation"]
```

**Diagram sources**
- [usePendingDecisionPoll.ts:56-169](file://products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts#L56-L169)
- [usePendingDecisionPoll.ts:171-201](file://products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts#L171-L201)

#### Test Coverage
The implementation includes comprehensive test coverage for browser tool scenarios:

- **Simple Expression Evaluation**: Tests basic JavaScript expression evaluation with write-tier classification
- **Mutation Blocking**: Validates that mutation attempts are properly blocked with appropriate error codes
- **Display Hint Rendering**: Ensures human-readable descriptions are properly included in confirmation requests
- **Risk Level Classification**: Verifies that browser tools are correctly classified as write-tier operations
- **Element Reference Handling**: Tests proper handling of snapshot element references in tool parameters

**Section sources**
- [hitl_confirmations.py:76-101](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L76-L101)
- [decoder.ts:78-103](file://products/operator-portal/web-ui/app/src/stream/decoder.ts#L78-L103)
- [sessions.ts:44-56](file://products/operator-portal/web-ui/app/src/api/sessions.ts#L44-L56)
- [usePendingDecisionPoll.ts:56-169](file://products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts#L56-L169)
- [test_browser_connector.py:1500-1530](file://products/tool-gateway/tests/test_browser_connector.py#L1500-L1530)

### Document Repository Service

#### Overview
The document repository service provides persistent storage for typed operation documents with role-based access controls, draft/published states, and comprehensive audit trails. It implements SPEC-039 R-1/R-2 with two-tier coverage (owner vs foreign sessions) and bounded retention policies. **Critical Security Enhancement v0.21.1**: Implements envelope-only document listings for GET /documents endpoint to ensure cross-owner reads are properly audited by stripping sensitive fields (digest and prose) from list responses while maintaining full content access through single-document fetch endpoints. **SPEC-041 Enhancement**: Adds deterministic counts-only document summaries computed from handover skeletons at creation time, stored in the operation documents table with PostgreSQL migration support, and surfaced in envelope-only list responses without breaking security posture. **v0.23.3 Enhancement**: Adds AI-generated one-line blurbs extracted from prose responses using SUMMARY marker format, providing operator-friendly briefings with bounded character limits and robust parsing logic.

#### Key Features
- **Typed Documents**: Supports `shift_summary` and `incident_report` document types with extensible discriminator pattern
- **Draft/Published States**: One-way transition from draft to published with owner-only actions
- **Role-Based Access**: Owner-only draft visibility, team-wide published document access
- **Bounded Storage**: PER_OWNER_CAP (20) limit per owner with oldest-first eviction
- **Retention Policy**: RETENTION_DAYS (30) automatic cleanup with opportunistic sweeping
- **Dual Backend Support**: In-memory for development/testing, Postgres for production with graceful fallback
- **Provenance Tracking**: Complete source record references for audit and traceability
- **Audit Trail Integration**: Fire-and-forget audit events for all document operations
- **Envelope-Only Listings**: Security enhancement that strips digest and prose from list responses to prevent unauthorized content access
- **Deterministic Summaries**: Counts-only summaries derived from handover skeletons at creation time, never containing titles, record ids, decision outcomes, or narrative text
- **AI-Generated Blurbs**: Bounded one-line stories extracted from prose responses using SUMMARY marker format, providing operator-friendly briefings

#### Document Lifecycle
```mermaid
flowchart TD
A["Create Document"] --> B{"Type: shift_summary or incident_report"}
B --> |shift_summary| C["Compute Summary from Handover"]
B --> |incident_report| D["Fetch Incident Bundle"]
C --> E{"Generate Prose with Blurb Extraction"}
D --> F{"Build Incident Digest"}
F --> G{"Generate Prose with Blurb Extraction"}
E --> H{"Owner Action Required"}
G --> H
H --> |Publish| I{"State: published"}
I --> J{"Team-Wide Access"}
J --> K{"Delete Allowed"}
K --> L["Document Removed"]
H --> |Delete| M["Document Removed"]
B --> N{"Non-Owner Access"}
N --> O{"404 Not Found"}
I --> P{"Read Access"}
P --> Q["Document Returned"]
```

**Diagram sources**
- [operation_documents.py:129-168](file://products/agent-platform/src/agent_service/services/operation_documents.py#L129-L168)
- [routes.py:910-956](file://products/agent-platform/src/agent_service/api/v2/routes.py#L910-L956)

#### Data Model
Each document contains:
- **Identity**: document_id, document_type, owner_user_id, label
- **Lifecycle**: created_at, published_at, state (draft/published)
- **Content**: provenance (source references), digest (assembled facts), prose (optional narrative)
- **Metadata**: prose_status (included/failed/not_requested), **summary (deterministic counts-only string)**, **blurb (AI-generated one-liner)**

#### Backend Implementations
Both in-memory and Postgres backends support the complete document repository functionality:

- **In-Memory Store**: Single-replica and non-persistent; suitable for development, CI, and as a fallback when Postgres is unreachable
- **Postgres Store**: Production-grade with SQL-level idempotency, bounded opportunistic sweep, startup sweep scoping, and **additive migrations for summary and blurb column support**

**Section sources**
- [operation_documents.py:1-573](file://products/agent-platform/src/agent_service/services/operation_documents.py#L1-L573)
- [routes.py:738-956](file://products/agent-platform/src/agent_service/api/v2/routes.py#L738-L956)

### Incident Report Document Type

#### Overview
The incident report document type provides specialized document creation for incident analysis with dedicated incident service integration, dual-action authorization gates, and structured error handling. It implements SPEC-043 with comprehensive coverage of incident envelopes, triage reports, connector dispatches, and linked session information.

#### Key Features
- **Incident Service Integration**: Dedicated client for fetching incident bundles with Basic authentication and bounded timeouts
- **Dual-Action Authorization**: Requires both `documents:create` and `incident:read` permissions for creation
- **Structured Error Handling**: Comprehensive error hierarchy mapping to HTTP postures (503, 502, 404, 4xx)
- **Two-Tier Coverage**: Full digest for owner sessions, metadata-only for foreign sessions with approvals:list capability
- **Deterministic Digests**: Mechanical fact copying from incident service with provenance anchors
- **Session Integration**: Links to triage sessions with appropriate coverage based on ownership and permissions
- **Provenance Tracking**: Complete source record references for audit and traceability
- **Graceful Degradation**: Unreadable secondary stores report unavailable without 500 errors

#### Incident Bundle Structure
```mermaid
flowchart TD
A["Incident Bundle"] --> B["Envelope"]
A --> C["Triage Report"]
A --> D["Dispatches"]
B --> E["Incident Section"]
C --> F["Triage Section"]
D --> G["Dispatch Section"]
E --> H["Session Section"]
F --> I["Provenance Tracking"]
G --> I
H --> I
I --> J["Final Digest"]
```

**Diagram sources**
- [incident_report.py:126-167](file://products/agent-platform/src/agent_service/services/incident_report.py#L126-L167)
- [incident_client.py:77-121](file://products/agent-platform/src/agent_service/services/incident_client.py#L77-L121)

#### Authorization Model
- **documents:create**: Required for all document creation (enforced by platform-gateway)
- **incident:read**: Additional requirement specifically for incident_report documents
- **X-Foreign-Coverage Header**: Trusted internal header for foreign session access control
- **Owner Validation**: Draft documents visible only to creators, published documents team-wide
- **Audit Trail**: All document operations emit audit events with correlation

#### Error Handling Strategy
- **503 Not Configured**: Missing incident service configuration
- **502 Service Unavailable**: Transport failure or upstream 5xx errors
- **404 Not Found**: Unknown incident ID
- **4xx Passed Through**: Other upstream client errors with original status codes
- **Never 500**: Structured error hierarchy prevents raw stack traces

#### Implementation Details
```mermaid
sequenceDiagram
participant Client as "Client"
participant Gateway as "Platform Gateway"
participant API as "Agent Platform API"
participant IncClient as "IncidentClient"
participant IncReport as "IncidentReport"
Note over Client,IncReport : Incident Report Creation Flow
Client->>Gateway : POST /api/v2/documents {type : "incident_report", incident_id}
Gateway->>API : Forward with authorization headers
API->>API : Enforce documents : create AND incident : read
alt Authorization granted
API->>IncClient : fetch_incident_bundle(incident_id)
IncClient->>IncClient : Validate configuration
IncClient->>IncClient : Make HTTP request with Basic auth
IncClient-->>API : Bundle or structured error
API->>IncReport : build_digest(user_id, bundle, can_view_foreign)
IncReport-->>API : digest + provenance
API->>API : document_summary(digest)
API-->>Client : 201 Created with document
else Authorization denied
API-->>Gateway : 403 Forbidden
Gateway-->>Client : 403 Forbidden
end
```

**Diagram sources**
- [routes.py:888-916](file://products/agent-platform/src/agent_service/api/v2/routes.py#L888-L916)
- [incident_client.py:77-121](file://products/agent-platform/src/agent_service/services/incident_client.py#L77-L121)
- [incident_report.py:126-167](file://products/agent-platform/src/agent_service/services/incident_report.py#L126-L167)

**Section sources**
- [incident_client.py:1-122](file://products/agent-platform/src/agent_service/services/incident_client.py#L1-L122)
- [incident_report.py:1-215](file://products/agent-platform/src/agent_service/services/incident_report.py#L1-L215)
- [routes.py:888-916](file://products/agent-platform/src/agent_service/api/v2/routes.py#L888-L916)
- [test_documents.py:552-742](file://products/agent-platform/tests/test_documents.py#L552-L742)

### Shift Summary Digest Assembly

#### Overview
The shift summary digest assembly builds deterministic digests from four durable stores: kernel state snapshot (turn counts only), evidence store, confirmation records, and execution records. Facts are copied verbatim with source record IDs for provenance anchors. **SPEC-041 Enhancement**: Now includes deterministic counts-only summary computation from the handover skeleton at creation time.

#### Coverage Tiers
- **Owner-Covered Sessions**: Full digest including title, turn counts, evidence counts per turn, confirmation decisions, execution receipts, and still-pending items
- **Foreign Sessions**: Metadata-level digest only (when requester holds approvals:list): confirmation decisions, execution receipts, and record counts — never titles, transcript excerpts, or evidence content

#### Key Features
- **Deterministic Assembly**: Mechanical fact copying from durable stores with no fabrication
- **Role-Based Filtering**: Foreign session access requires approvals:list capability
- **Graceful Degradation**: Unreadable secondary stores report unavailable without 500 errors
- **Input Validation**: Bounded session IDs (MAX_SESSION_IDS = 20) with deduplication
- **Provenance Tracking**: Complete source record references for audit and traceability
- **Handover Skeleton**: Deterministic handover section with covered-session counts, decision/execution details, open items, and quiet flag
- **Summary Computation**: Deterministic counts-only one-liner derived from handover skeleton for list surfaces

#### Digest Structure
```mermaid
flowchart TD
A["Session IDs Input"] --> B{"Validate & Deduplicate"}
B --> C{"Load Sessions"}
C --> D{"Coverage Type?"}
D --> |Owner| E["Full Digest Assembly"]
D --> |Foreign| F["Metadata-Only Digest"]
E --> G["Transcript Section"]
E --> H["Evidence Section"]
E --> I["Confirmation Entries"]
E --> J["Execution Entries"]
F --> K["Confirmation Decisions Only"]
F --> L["Execution Receipts Only"]
F --> M["Record Counts Only"]
G --> N["Open Items Summary"]
H --> N
I --> N
J --> N
K --> O["Provenance Tracking"]
L --> O
M --> O
N --> O
O --> P["Final Digest + Provenance + Handover"]
P --> Q["document_summary(handover)"]
Q --> R["Counts-Only Summary String"]
```

**Diagram sources**
- [shift_summary.py:77-90](file://products/agent-platform/src/agent_service/services/shift_summary.py#L77-L90)
- [shift_summary.py:182-263](file://products/agent-platform/src/agent_service/services/shift_summary.py#L182-L263)
- [shift_summary.py:266-322](file://products/agent-platform/src/agent_service/services/shift_summary.py#L266-322)
- [shift_summary.py:432-460](file://products/agent-platform/src/agent_service/services/shift_summary.py#L432-L460)

#### Error Handling
- **DigestInputError**: Structural input violations (empty session IDs, too many sessions)
- **UnknownSessionError**: Non-existent session IDs with offending IDs exposed
- **ForeignSessionDenied**: Foreign coverage requested without approvals:list capability

**Section sources**
- [shift_summary.py:1-323](file://products/agent-platform/src/agent_service/services/shift_summary.py#L1-L323)

### Optional Prose Generation

#### Overview
The optional prose generation service creates AI-powered narratives from digests with fail-soft behavior and strict prompt safety guarantees. It uses the runtime's default model with hard timeout protection. **v0.23.3 Enhancement**: Now includes AI-generated one-line blurbs extracted from prose responses using SUMMARY marker format, providing operator-friendly briefings with bounded character limits and robust parsing logic.

#### Safety Guarantees
- **Prompt Contract**: Model receives digest JSON only — never raw transcripts, evidence payloads, or argument bodies
- **Fail-Soft Behavior**: Any model error or timeout yields prose_status=failed and document ships digest-only
- **Hard Timeout**: PROSE_TIMEOUT_SECONDS (30.0) prevents hung model from blocking create route
- **No Fabrication**: Prompt explicitly instructs model to state only what facts contain, never invent details
- **Blurb Extraction**: Robust parsing logic extracts SUMMARY marker from first non-empty line with bounded character limits

#### Key Features
- **Digest-Only Input**: Strict separation between factual digest and generated narrative
- **Type Adaptation**: document_type parameter allows future prompt customization per document type
- **Streaming Support**: Handles both streaming and non-streaming model responses
- **Empty Response Handling**: Validates non-empty responses and treats empty replies as failures
- **Blurb Parsing**: Forgiving parser handles missing markers, case-insensitive matching, and character bounding
- **Operator-Friendly Blurbs**: Human handover voice with plain, direct, and concise one-liners

#### Implementation Details
```mermaid
flowchart TD
A["Generate Prose Request"] --> B["Build Prompt from Digest"]
B --> C["Create Model Instance"]
C --> D["Send Message with Prompt"]
D --> E{"Response Type?"}
E --> |Streaming| F["Drain Async Generator"]
E --> |Non-Streaming| G["Extract Content Directly"]
F --> H["Extract Text Content"]
G --> H
H --> I{"Text Empty?"}
I --> |Yes| J["Raise RuntimeError"]
I --> |No| K["Parse Blurb from SUMMARY Marker"]
K --> L["Extract Blurb and Prose"]
L --> M["Return Prose + Blurb + Status"]
J --> N["Catch Exception"]
N --> O["Log Warning + Return None + 'failed'"]
```

**Diagram sources**
- [document_prose.py:44-56](file://products/agent-platform/src/agent_service/services/document_prose.py#L44-L56)
- [document_prose.py:59-99](file://products/agent-platform/src/agent_service/services/document_prose.py#L59-L99)
- [document_prose.py:70-96](file://products/agent-platform/src/agent_service/services/document_prose.py#L70-L96)

**Section sources**
- [document_prose.py:1-158](file://products/agent-platform/src/agent_service/services/document_prose.py#L1-L158)

### Execution Worker Integration

#### Overview
The execution worker integration provides isolated execution of approved mutating tools through the execution-runtime service with fail-closed behavior, signature verification, and receipt tracking. This implementation addresses SPEC-038 R-4 by separating the execution boundary from the agent process, reducing blast radius and improving security posture.

#### Key Features
- **Fail-Closed Behavior**: Missing worker URL or handoff token rejects before any network call with `worker_unavailable` reason
- **Blocking Handoff**: Approved mutating calls block on worker response with bounded timeout (`AGENT_EXECUTION_WORKER_TIMEOUT_SECONDS`)
- **Signature Verification**: Execution-runtime service verifies signed execution request envelopes and argument digests
- **Receipt Tracking**: Durable execution records track request/receipt lifecycle with first-write-wins semantics
- **Structured Error Handling**: Timeout exceptions raise `WorkerHandoffTimeout`, transport errors raise `WorkerHandoffError` with `worker_unavailable`
- **Audit Trail Integration**: All rejections and completions are audited with correlation to resume requests
- **Single-Flight Idempotency**: Worker executes each `execution_id` at most once with concurrent duplicate joining

#### Execution Flow
```mermaid
flowchart TD
A["Approved Mutating Tool Call"] --> B{"Worker Configured?"}
B --> |No| C["Reject with worker_unavailable"]
B --> |Yes| D["Build Signed Envelope"]
D --> E["Handoff to Execution Runtime"]
E --> F{"Signature Valid?"}
F --> |No| G["Reject with signature_invalid"]
F --> |Yes| H{"Digest Match?"}
H --> |No| I["Reject with args_digest_mismatch"]
H --> |Yes| J["Execute Tool Call"]
J --> K["Write Receipt"]
K --> L["Return Result"]
C --> M["Structured Rejection Result"]
G --> M
I --> M
L --> N["Tool Result to Stream"]
```

**Diagram sources**
- [execution_worker_client.py:54-145](file://products/agent-platform/src/agent_service/services/execution_worker_client.py#L54-L145)
- [handoff.py:66-169](file://products/execution-runtime/src/execution_runtime/api/routes/handoff.py#L66-L169)
- [gateway_tools.py:247-302](file://products/agent-platform/src/agent_service/tools/gateway_tools.py#L247-L302)

#### Error Handling Strategy
The execution worker client implements comprehensive error handling with distinct exception types:

- **WorkerHandoffError**: Raised for missing configuration, transport failures, or malformed responses with `worker_unavailable` reason
- **WorkerHandoffTimeout**: Raised when worker doesn't respond within timeout budget, allowing resumed streams to surface structured timeout results
- **Structured Rejections**: Worker-side verification failures return specific reasons (signature_invalid, args_digest_mismatch, unauthorized)

#### Configuration Requirements
- **AGENT_EXECUTION_WORKER_URL**: URL of the execution-runtime service
- **AGENT_EXECUTION_HANDOFF_TOKEN**: Static handoff token for authentication
- **AGENT_EXECUTION_WORKER_TIMEOUT_SECONDS**: Bounded timeout for handoff calls (default: 60.0)

**Section sources**
- [execution_worker_client.py:1-145](file://products/agent-platform/src/agent_service/services/execution_worker_client.py#L1-L145)
- [handoff.py:1-344](file://products/execution-runtime/src/execution_runtime/api/routes/handoff.py#L1-L344)
- [gateway_tools.py:247-302](file://products/agent-platform/src/agent_service/tools/gateway_tools.py#L247-L302)
- [runtime_settings.py:166-173](file://products/agent-platform/src/agent_service/runtime_settings.py#L166-L173)

### Enhanced Confirmation Record Storage Layer with Turn Index Support

#### Overview
The enhanced confirmation record storage layer provides durable persistence for HITL (Human-In-The-Loop) confirmation lifecycle with turn_index field support for SPEC-033, idempotent resolution, improved startup sweep scoping to prevent sibling replica interference, and better error handling for concurrent approval attempts.

#### Key Features
- **Turn Index Field Support**: Each confirmation record now stores the ordinal of the user turn under which the park occurred, using the same convention as persisted evidence (`_count_user_turns`, 0-based over the seeded turn timeline)
- **Precise Card Anchoring**: Confirmation cards are anchored under their specific parking turn instead of stacking under the newest turn, improving operator experience
- **Idempotent Resolution**: SQL-level guards ensure confirmation outcomes are applied exactly once, preventing race conditions between concurrent approvers
- **Startup Sweep Scoping**: Scoped cleanup of stale pending confirmations based on HITL confirmation TTL to prevent sibling replica interference
- **Cross-Replica Consistency**: Durable records survive process restarts and replica boundaries while maintaining consistency guarantees
- **Claim-Time Persistence**: Outcomes are persisted immediately upon claim, providing structured 409 responses to racing approvers
- **TTL-Aware Cleanup**: Opportunistic sweep of old resolved records beyond inbox history window
- **Dual Backend Support**: In-memory for development/testing, Postgres for production with graceful fallback

#### Turn Index Implementation
```mermaid
flowchart TD
A["User Turn #N"] --> B["Agent executes tool calls"]
B --> C{"Tool requires confirmation?"}
C --> |Yes| D["Compute turn_index = _count_user_turns(agent)"]
D --> E["Create confirmation record with turn_index"]
E --> F["Persist to confirmation store"]
F --> G["Return confirmation_request frame"]
G --> H["Portal anchors card under turn #N"]
C --> |No| I["Continue processing"]
I --> J["Next turn"]
```

**Diagram sources**
- [runtime_kernel.py:869-924](file://products/agent-platform/src/agent_service/runtime_kernel.py#L869-L924)
- [runtime_kernel.py:1133-1177](file://products/agent-platform/src/agent_service/runtime_kernel.py#L1133-L1177)
- [confirmation_records.py:52-76](file://products/agent-platform/src/agent_service/services/confirmation_records.py#L52-L76)

#### Idempotent Resolution Implementation
```mermaid
flowchart TD
A["Concurrent Approval Request"] --> B{"SQL UPDATE with WHERE status = 'pending'"}
B --> |Success| C["Mark as approved/denied"]
B --> |No rows affected| D["Return structured 409 with winner's outcome"]
C --> E["Persist decider_user_id and decision"]
E --> F["Resume confirmation workflow"]
D --> G["Show winner's outcome to loser"]
```

**Diagram sources**
- [confirmation_records.py:262-274](file://products/agent-platform/src/agent_service/services/confirmation_records.py#L262-274)
- [routes.py:276-294](file://products/agent-platform/src/agent_service/api/v2/routes.py#L276-294)

#### Startup Sweep Scoping
The startup sweep is carefully scoped to only close pending confirmations that have exceeded the HITL confirmation TTL, ensuring that sibling replicas' live parks are never expired:

```mermaid
sequenceDiagram
participant App as "Application Startup"
participant Store as "ConfirmationRecordStore"
participant DB as "PostgreSQL"
Note over App,DB : Startup Sweep Process
App->>Store : initialize(stale_after_seconds=AGENT_HITL_CONFIRM_TIMEOUT)
Store->>DB : CREATE TABLE IF NOT EXISTS confirmation_records
Store->>DB : ALTER TABLE ADD COLUMN IF NOT EXISTS turn_index INTEGER
Store->>DB : UPDATE confirmation_records SET status='expired' WHERE status='pending' AND parked_at <= now() - make_interval(secs => stale_after_seconds)
Note right of DB : Only closes rows older than HITL TTL<br/>Younger rows stay pending for live replicas
DB-->>Store : Rows affected
Store-->>App : Initialization complete
```

**Diagram sources**
- [confirmation_records.py:415-431](file://products/agent-platform/src/agent_service/services/confirmation_records.py#L415-L431)
- [confirmation_records.py:330-341](file://products/agent-platform/src/agent_service/services/confirmation_records.py#L330-L341)

#### Error Handling for Concurrent Approvals
The system provides structured error responses for concurrent approval attempts:

```mermaid
stateDiagram-v2
[*] --> Pending : Parked Confirmation
Pending --> Approved : First Approver Claims
Pending --> Denied : First Approver Claims
Approved --> Resolved : Winner Streams Resume
Denied --> Resolved : Winner Streams Resume
Pending --> Expired : TTL Exceeded
Resolved --> [*] : Cleanup Complete
note right of Resolved
Racing approvers receive structured 409<br/>with winner's outcome instead of 404
end note
```

**Diagram sources**
- [routes.py:276-294](file://products/agent-platform/src/agent_service/api/v2/routes.py#L276-294)
- [test_confirmation_records.py:413-497](file://products/agent-platform/tests/test_confirmation_records.py#L413-L497)

#### Backend Implementations
Both in-memory and Postgres backends support the enhanced confirmation record functionality with turn_index field:

- **In-Memory Store**: Single-replica and non-persistent; suitable for development, CI, and as a fallback when Postgres is unreachable
- **Postgres Store**: Production-grade with SQL-level idempotency, turn_index column support, bounded opportunistic sweep, and startup sweep scoping

**Section sources**
- [confirmation_records.py:1-621](file://products/agent-platform/src/agent_service/services/confirmation_records.py#L1-L621)
- [routes.py:276-410](file://products/agent-platform/src/agent_service/api/v2/routes.py#L276-L410)
- [test_confirmation_records.py:1-695](file://products/agent-platform/tests/test_confirmation_records.py#L1-L695)

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
+discover_exclude_markers _NON_CHAT_MARKERS + ("-vl", "-mt", "-ocr", "omni")
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
- **Enhanced Transcript Extraction**: Best-effort conversation history from kernel state snapshots with proper markdown rendering
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
-_last_accessed : dict[str, float]
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
- [session_store.py:176-320](file://products/agent-platform/src/agent_service/services/session_store.py#L176-320)
- [session_store.py:420-612](file://products/agent-platform/src/agent_service/services/session_store.py#L420-L612)

### Enhanced Transcript Reconstruction

#### Overview
The enhanced transcript reconstruction service provides best-effort conversation history reconstruction from kernel state snapshots with proper markdown rendering through blank-line block joining. This addresses SPEC-035 R-1 where assistant messages persisted as separate text blocks were previously joined without paragraph breaks, causing block markdown (headings, lists, rules) to render as raw text instead of proper markdown.

#### Blank-Line Block Joining Implementation
```mermaid
flowchart TD
A["Assistant Message with Multiple Text Blocks"] --> B["Extract Text Blocks"]
B --> C{"Multiple Blocks?"}
C --> |Yes| D["Join with Blank Line (\\n\\n)"]
C --> |No| E["Use Single Block"]
D --> F["Preserve Markdown Formatting"]
E --> F
F --> G["Render Headings, Lists, Rules Properly"]
G --> H["Display in Workspace UI"]
```

**Diagram sources**
- [session_transcript.py:67-87](file://products/agent-platform/src/agent_service/services/session_transcript.py#L67-L87)
- [test_session_workspace.py:178-221](file://products/agent-platform/tests/test_session_workspace.py#L178-L221)

#### Key Improvements
- **Proper Paragraph Boundaries**: Text blocks separated by tool calls now join with `\n\n` instead of empty string
- **Markdown Rendering**: Segment-start headings like `## Pod Restart Summary` render as proper markdown instead of raw text
- **Block Content Preservation**: Lists, rules, and other block elements maintain proper formatting
- **Backward Compatibility**: Single-block messages remain unchanged
- **Best-Effort Design**: Missing or corrupt snapshots degrade gracefully without errors

#### Test Coverage
The implementation includes comprehensive test coverage validating:
- Multi-block assistant messages join with blank lines
- Single-block messages remain unchanged  
- Corrupt snapshots fall back gracefully
- Markdown formatting is preserved in rendered output

**Section sources**
- [session_transcript.py:1-87](file://products/agent-platform/src/agent_service/services/session_transcript.py#L1-L87)
- [test_session_workspace.py:178-221](file://products/agent-platform/tests/test_session_workspace.py#L178-L221)

### HITL Confirmation Registry Integration
The HITL (Human-In-The-Loop) confirmation registry manages parked tool confirmations for interactive workflows with enhanced durability and cross-replica consistency.

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
note right of Resolved
Durable record persists outcome
for cross-replica consistency
end note
```

**Diagram sources**
- [hitl_confirmations.py:93-229](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L93-229)
- [routes.py:71-100](file://products/agent-platform/src/agent_service/api/v2/routes.py#L71-100)

Core functionality:
- **Parked Confirmation Management**: Tracks tool calls awaiting user approval with durable persistence
- **Single-Flight Guarantees**: Prevents duplicate confirmation processing with SQL-level guards
- **TTL-Based Expiration**: Automatic cleanup of expired confirmations with startup sweep scoping
- **Owner Validation**: Ensures only session owners can answer confirmations
- **Risk Level Tracking**: Captures mutating tool risk levels for UI flagging
- **Integration Points**: Bridges AgentScope kernel events with platform workflows and durable storage
- **Cross-Replica Consistency**: Durable records survive process restarts and replica boundaries

**Section sources**
- [hitl_confirmations.py:1-256](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L1-L256)
- [routes.py:71-100](file://products/agent-platform/src/agent_service/api/v2/routes.py#L71-100)

### API Endpoints
The API layer exposes REST endpoints for agent interactions, session management, model discovery, documents, and health checks. Requests are validated against schemas and routed to the runtime kernel with v3 streaming protocol support.

Typical endpoints:
- Chat: POST /chat with message, optional session ID, and delegated token
- Sessions: GET/POST/DELETE /sessions for lifecycle management with evidence retrieval
- Models: GET /models for credential-safe model discovery
- **Documents**: POST /documents for creation, GET /documents for listing, GET /documents/{id} for reading, POST /documents/{id}/publish for publishing, DELETE /documents/{id} for deletion
- Health: GET /health for readiness and liveness probes
- Streaming: Server-sent events for incremental responses with v3 tool_call/tool_result frames
- **Confirmations**: POST /chat/confirm for approval workflows with structured error handling

Request/response validation uses Pydantic models defined in schemas with enhanced v3 streaming event types.

**Updated** Chat endpoints now accept delegated tokens for secure tool execution and support v3 streaming protocol with tool_call/tool_result frames for comprehensive audit trails. Both POST /chat and GET /chat/stream endpoints accept input_modality parameters for voice-readiness parity. Session endpoints provide multi-session workspace operations with proper authorization, audit trails, and evidence turn retrieval. Model endpoints provide credential-safe enumeration of available models with public schema compliance. **Document endpoints provide complete CRUD operations with role-based access controls, draft/published states, audit trail integration, envelope-only listings for security, deterministic counts-only summaries derived from handover skeletons, and AI-generated one-line blurbs extracted from prose responses. Confirmation endpoints provide structured 409 responses for racing approvers with winner attribution and durable outcome persistence, plus turn_index field support for precise confirmation card anchoring. Incident report document creation enforces dual-action authorization gates requiring both documents:create and incident:read permissions. Browser tool enhancements include improved pending decision polling and transcript handling for write-tier operations with human-readable element descriptions. Flow authority management integrates with execution workflows for secure isolated tool execution with session-scoped approvals and TTL-based authorities.**

**Section sources**
- [routes.py:106-235](file://products/agent-platform/src/agent_service/api/v2/routes.py#L106-L235)
- [routes.py:334-419](file://products/agent-platform/src/agent_service/api/v2/routes.py#L334-L419)
- [routes.py:738-956](file://products/agent-platform/src/agent_service/api/v2/routes.py#L738-L956)
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
participant ConfirmStore as "ConfirmationRecordStore"
participant ExecWorker as "ExecutionWorkerClient"
participant ExecRuntime as "ExecutionRuntime"
participant FlowAuth as "FlowAuthorityManager"
Kernel->>GatewayTools : build_gateway_toolkit(definitions, bearerToken, traceQueue)
GatewayTools->>External : discover_tools(bearerToken)
External-->>GatewayTools : availableTools
GatewayTools->>Trace : emit tool_call trace event
GatewayTools->>HITL : check_auto_approval(tool_name)
alt Tool requires confirmation
HITL->>ConfirmStore : save_parked(record with turn_index)
ConfirmStore-->>HITL : persisted confirmation with turn_index
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
else Approved mutating tool
GatewayTools->>FlowAuth : Check flow authority
FlowAuth-->>GatewayTools : Flow approval status
alt Has flow authority
GatewayTools->>ExecWorker : handoff(envelope, arguments, delegated_token)
ExecWorker->>ExecRuntime : POST /api/v1/executions/handoff
ExecRuntime-->>ExecWorker : result + receipt
ExecWorker-->>GatewayTools : tool result
GatewayTools->>Trace : emit tool_result trace event
Trace-->>Kernel : audit trail data
Kernel->>EvStore : persist evidence frames
EvStore-->>Kernel : evidence stored
GatewayTools-->>Kernel : toolResult
else No flow authority
GatewayTools-->>Kernel : Reject execution
end
end
```

**Updated** The tools integration now includes AgentScope 2.x toolkit registration pattern, per-request trace queues for audit trails, v3 streaming support with tool_call/tool_result frames, auto-approval mechanism for vetted read-only tools, HITL confirmation registry integration with durable storage for interactive workflows, evidence store integration for persistent tool execution records, **isolated execution routing for approved mutating tools through the execution-runtime service with signature verification, receipt tracking, and comprehensive flow authority management, enhanced confirmation record persistence with turn_index field support, idempotent resolution, and cross-replica consistency**. Voice readiness is maintained throughout the tool execution pipeline. **SPEC-050 Enhancement**: Enhanced browser tool surface with improved pending decision polling and transcript handling for write-tier operations, supporting human-readable element descriptions for browser interaction tools. **NEW FLOW AUTHORITY MANAGEMENT**: Added comprehensive flow authority management with session-scoped flow context and approval tracking for secure isolated tool execution workflows.

**Diagram sources**
- [gateway_tools.py](file://products/agent-platform/src/agent_service/tools/gateway_tools.py)
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [hitl_confirmations.py](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py)
- [confirmation_records.py](file://products/agent-platform/src/agent_service/services/confirmation_records.py)
- [evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [execution_worker_client.py](file://products/agent-platform/src/agent_service/services/execution_worker_client.py)
- [handoff.py](file://products/execution-runtime/src/execution_runtime/api/routes/handoff.py)
- [flow_approvals.py](file://products/agent-platform/src/agent_service/services/flow_approvals.py)

**Section sources**
- [gateway_tools.py](file://products/agent-platform/src/agent_service/tools/gateway_tools.py)

## Document Repository Service

### Overview
The document repository service provides persistent storage for typed operation documents with role-based access controls, draft/published states, and comprehensive audit trails. It implements SPEC-039 R-1/R-2 with two-tier coverage (owner vs foreign sessions) and bounded retention policies. **Critical Security Enhancement v0.21.1**: Implements envelope-only document listings for GET /documents endpoint to ensure cross-owner reads are properly audited by stripping sensitive fields (digest and prose) from list responses while maintaining full content access through single-document fetch endpoints. **SPEC-041 Enhancement**: Adds deterministic counts-only document summaries computed from handover skeletons at creation time, stored in the operation documents table with PostgreSQL migration support, and surfaced in envelope-only list responses without breaking security posture. **v0.23.3 Enhancement**: Adds AI-generated one-line blurbs extracted from prose responses using SUMMARY marker format, providing operator-friendly briefings with bounded character limits and robust parsing logic.

### Key Features
- **Typed Documents**: Supports `shift_summary` and `incident_report` document types with extensible discriminator pattern
- **Draft/Published States**: One-way transition from draft to published with owner-only actions
- **Role-Based Access**: Owner-only draft visibility, team-wide published document access
- **Bounded Storage**: PER_OWNER_CAP (20) limit per owner with oldest-first eviction
- **Retention Policy**: RETENTION_DAYS (30) automatic cleanup with opportunistic sweeping
- **Dual Backend Support**: In-memory for development/testing, Postgres for production with graceful fallback
- **Provenance Tracking**: Complete source record references for audit and traceability
- **Audit Trail Integration**: Fire-and-forget audit events for all document operations
- **Envelope-Only Listings**: Security enhancement that strips digest and prose from list responses to prevent unauthorized content access
- **Deterministic Summaries**: Counts-only summaries derived from handover skeletons at creation time, never containing titles, record ids, decision outcomes, or narrative text
- **AI-Generated Blurbs**: Bounded one-line stories extracted from prose responses using SUMMARY marker format, providing operator-friendly briefings

### Document Lifecycle
```mermaid
flowchart TD
A["Create Document"] --> B{"State: draft"}
B --> C{"Compute Summary from Handover"}
C --> D{"Generate Prose with Blurb Extraction"}
D --> E{"Owner Action Required"}
E --> |Publish| F{"State: published"}
F --> G{"Team-Wide Access"}
G --> H{"Delete Allowed"}
H --> I["Document Removed"]
E --> |Delete| J["Document Removed"]
B --> K{"Non-Owner Access"}
K --> L{"404 Not Found"}
F --> M{"Read Access"}
M --> N["Document Returned"]
```

**Diagram sources**
- [operation_documents.py:129-168](file://products/agent-platform/src/agent_service/services/operation_documents.py#L129-L168)
- [routes.py:910-956](file://products/agent-platform/src/agent_service/api/v2/routes.py#L910-L956)

### Data Model
Each document contains:
- **Identity**: document_id, document_type, owner_user_id, label
- **Lifecycle**: created_at, published_at, state (draft/published)
- **Content**: provenance (source references), digest (assembled facts), prose (optional narrative)
- **Metadata**: prose_status (included/failed/not_requested), **summary (deterministic counts-only string)**, **blurb (AI-generated one-liner)**

### Backend Implementations
Both in-memory and Postgres backends support the complete document repository functionality:

- **In-Memory Store**: Single-replica and non-persistent; suitable for development, CI, and as a fallback when Postgres is unreachable
- **Postgres Store**: Production-grade with SQL-level idempotency, bounded opportunistic sweep, startup sweep scoping, and **additive migrations for summary and blurb column support**

**Section sources**
- [operation_documents.py:1-573](file://products/agent-platform/src/agent_service/services/operation_documents.py#L1-L573)
- [routes.py:738-956](file://products/agent-platform/src/agent_service/api/v2/routes.py#L738-L956)

## Shift Summary Digest Assembly

### Overview
The shift summary digest assembly builds deterministic digests from four durable stores: kernel state snapshot (turn counts only), evidence store, confirmation records, and execution records. Facts are copied verbatim with source record IDs for provenance anchors. **SPEC-041 Enhancement**: Now includes deterministic counts-only summary computation from the handover skeleton at creation time.

### Coverage Tiers
- **Owner-Covered Sessions**: Full digest including title, turn counts, evidence counts per turn, confirmation decisions, execution receipts, and still-pending items
- **Foreign Sessions**: Metadata-level digest only (when requester holds approvals:list): confirmation decisions, execution receipts, and record counts — never titles, transcript excerpts, or evidence content

### Key Features
- **Deterministic Assembly**: Mechanical fact copying from durable stores with no fabrication
- **Role-Based Filtering**: Foreign session access requires approvals:list capability
- **Graceful Degradation**: Unreadable secondary stores report unavailable without 500 errors
- **Input Validation**: Bounded session IDs (MAX_SESSION_IDS = 20) with deduplication
- **Provenance Tracking**: Complete source record references for audit and traceability
- **Handover Skeleton**: Deterministic handover section with covered-session counts, decision/execution details, open items, and quiet flag
- **Summary Computation**: Deterministic counts-only one-liner derived from handover skeleton for list surfaces

### Digest Structure
```mermaid
flowchart TD
A["Session IDs Input"] --> B{"Validate & Deduplicate"}
B --> C{"Load Sessions"}
C --> D{"Coverage Type?"}
D --> |Owner| E["Full Digest Assembly"]
D --> |Foreign| F["Metadata-Only Digest"]
E --> G["Transcript Section"]
E --> H["Evidence Section"]
E --> I["Confirmation Entries"]
E --> J["Execution Entries"]
F --> K["Confirmation Decisions Only"]
F --> L["Execution Receipts Only"]
F --> M["Record Counts Only"]
G --> N["Open Items Summary"]
H --> N
I --> N
J --> N
K --> O["Provenance Tracking"]
L --> O
M --> O
N --> O
O --> P["Final Digest + Provenance + Handover"]
P --> Q["document_summary(handover)"]
Q --> R["Counts-Only Summary String"]
```

**Diagram sources**
- [shift_summary.py:77-90](file://products/agent-platform/src/agent_service/services/shift_summary.py#L77-L90)
- [shift_summary.py:182-263](file://products/agent-platform/src/agent_service/services/shift_summary.py#L182-L263)
- [shift_summary.py:266-322](file://products/agent-platform/src/agent_service/services/shift_summary.py#L266-322)
- [shift_summary.py:432-460](file://products/agent-platform/src/agent_service/services/shift_summary.py#L432-L460)

### Error Handling
- **DigestInputError**: Structural input violations (empty session IDs, too many sessions)
- **UnknownSessionError**: Non-existent session IDs with offending IDs exposed
- **ForeignSessionDenied**: Foreign coverage requested without approvals:list capability

**Section sources**
- [shift_summary.py:1-323](file://products/agent-platform/src/agent_service/services/shift_summary.py#L1-L323)

## Optional Prose Generation

### Overview
The optional prose generation service creates AI-powered narratives from digests with fail-soft behavior and strict prompt safety guarantees. It uses the runtime's default model with hard timeout protection. **v0.23.3 Enhancement**: Now includes AI-generated one-line blurbs extracted from prose responses using SUMMARY marker format, providing operator-friendly briefings with bounded character limits and robust parsing logic.

### Safety Guarantees
- **Prompt Contract**: Model receives digest JSON only — never raw transcripts, evidence payloads, or argument bodies
- **Fail-Soft Behavior**: Any model error or timeout yields prose_status=failed and document ships digest-only
- **Hard Timeout**: PROSE_TIMEOUT_SECONDS (30.0) prevents hung model from blocking create route
- **No Fabrication**: Prompt explicitly instructs model to state only what facts contain, never invent details
- **Blurb Extraction**: Robust parsing logic handles missing markers, case-insensitive matching, and character bounding

### Key Features
- **Digest-Only Input**: Strict separation between factual digest and generated narrative
- **Type Adaptation**: document_type parameter allows future prompt customization per document type
- **Streaming Support**: Handles both streaming and non-streaming model responses
- **Empty Response Handling**: Validates non-empty responses and treats empty replies as failures
- **Blurb Parsing**: Forgiving parser handles missing markers, case-insensitive matching, and character bounding
- **Operator-Friendly Blurbs**: Human handover voice with plain, direct, and concise one-liners

### Implementation Details
```mermaid
flowchart TD
A["Generate Prose Request"] --> B["Build Prompt from Digest"]
B --> C["Create Model Instance"]
C --> D["Send Message with Prompt"]
D --> E{"Response Type?"}
E --> |Streaming| F["Drain Async Generator"]
E --> |Non-Streaming| G["Extract Content Directly"]
F --> H["Extract Text Content"]
G --> H
H --> I{"Text Empty?"}
I --> |Yes| J["Raise RuntimeError"]
I --> |No| K["Parse Blurb from SUMMARY Marker"]
K --> L["Extract Blurb and Prose"]
L --> M["Return Prose + Blurb + Status"]
J --> N["Catch Exception"]
N --> O["Log Warning + Return None + 'failed'"]
```

**Diagram sources**
- [document_prose.py:44-56](file://products/agent-platform/src/agent_service/services/document_prose.py#L44-L56)
- [document_prose.py:59-99](file://products/agent-platform/src/agent_service/services/document_prose.py#L59-L99)
- [document_prose.py:70-96](file://products/agent-platform/src/agent_service/services/document_prose.py#L70-L96)

**Section sources**
- [document_prose.py:1-158](file://products/agent-platform/src/agent_service/services/document_prose.py#L1-L158)

## Document API Endpoints

### Overview
The document API endpoints provide complete CRUD operations for typed operation documents with role-based access controls and comprehensive audit trails. **Critical Security Enhancement v0.21.1**: Implements envelope-only document listings to prevent unauthorized content access while maintaining full content access through audited single-document fetch endpoints. **SPEC-041 Enhancement**: Adds deterministic counts-only summaries computed from handover skeletons at creation time, stored in the operation documents table with PostgreSQL migration support, and surfaced in envelope-only list responses without breaking security posture. **v0.23.3 Enhancement**: Adds AI-generated one-line blurbs extracted from prose responses using SUMMARY marker format, providing operator-friendly briefings with bounded character limits and robust parsing logic.

### Available Endpoints
- **POST /api/v2/documents**: Create a typed operation document with optional prose generation, automatic summary computation, and AI-generated blurb extraction
- **GET /api/v2/documents**: List document envelopes with scope filtering (mine/published) - **ENVELOPE-ONLY with summary and blurb fields**
- **GET /api/v2/documents/{document_id}**: Read a specific document with ownership validation - **AUDITED FETCH**
- **POST /api/v2/documents/{document_id}/publish**: Publish a draft document (owner-only)
- **DELETE /api/v2/documents/{document_id}**: Delete a document (owner-only)

### Authorization Model
- **documents:create**: Required for document creation (enforced by platform-gateway)
- **incident:read**: Additional requirement for incident_report documents (enforced by platform-gateway)
- **X-Foreign-Coverage Header**: Trusted internal header for foreign session access control
- **Owner Validation**: Draft documents visible only to creators, published documents team-wide
- **Audit Trail**: All document operations emit audit events with correlation IDs

### Security Enhancement: Envelope-Only Listings
The v0.21.1 security fix implements envelope-only document listings to address a critical vulnerability where list endpoints returned full document content (digest and prose) without proper audit trails. Now:

- **GET /documents**: Returns envelope-only rows with `digest` and `prose` fields stripped, but includes `summary` and `blurb` fields
- **GET /documents/{id}**: Returns full document content with proper audit trail for cross-owner reads
- **Portal Integration**: Documents view drawer now issues audited single fetch instead of rendering from list results

### Summary and Blurb Computation
**SPEC-041 R-4**: Deterministic counts-only summaries are computed from the document's handover skeleton at creation time:

- **Quiet Shifts**: "Quiet shift — no recorded decisions or executions."
- **Busy Shifts**: "N session · M decision · K execution · O open item" format
- **Counts Only**: Never contains session titles, record ids, decision outcomes, or narrative text
- **Creation Time**: Computed once during document creation, not recalculated on list renders
- **Legacy Support**: Documents created before SPEC-041 carry no summary field and degrade gracefully

**v0.23.3 Enhancement**: AI-generated one-line blurbs are extracted from prose responses using SUMMARY marker format:

- **Marker Format**: First line beginning with "SUMMARY:" followed by the one-liner
- **Character Limit**: Bounded to 240 characters maximum to prevent envelope bloat
- **Robust Parsing**: Case-insensitive marker detection with forgiving parsing logic
- **Fallback Behavior**: If no marker found, entire response becomes prose without blurb
- **Operator-Friendly**: Human handover voice with plain, direct, and concise language

### Request/Response Examples
```mermaid
sequenceDiagram
participant Client as "Client"
participant API as "Document API"
participant ShiftSum as "Shift Summary"
participant IncClient as "IncidentClient"
participant IncReport as "IncidentReport"
participant DocProse as "Document Prose"
participant DocStore as "Document Store"
Note over Client,DocStore : Document Creation Flow with Summary and Blurb
Client->>API : POST /api/v2/documents {type, sessions, label, include_prose}
alt shift_summary
API->>ShiftSum : build_digest(user_id, session_ids, can_view_foreign)
ShiftSum-->>API : digest + provenance + handover skeleton
else incident_report
API->>IncClient : fetch_incident_bundle(incident_id)
IncClient-->>API : incident bundle
API->>IncReport : build_digest(user_id, bundle, can_view_foreign)
IncReport-->>API : digest + provenance + handover skeleton
end
API->>API : document_summary(digest) - compute counts-only summary
alt include_prose = true
API->>DocProse : generate_prose(kernel, type, digest)
DocProse-->>API : prose + blurb + status
else include_prose = false
API-->>API : prose_status = not_requested
end
API->>DocStore : create(document with summary, blurb)
DocStore-->>API : persisted document
API-->>Client : 201 Created + document with summary and blurb
```

**Diagram sources**
- [routes.py:763-855](file://products/agent-platform/src/agent_service/api/v2/routes.py#L763-L855)
- [shift_summary.py:432-460](file://products/agent-platform/src/agent_service/services/shift_summary.py#L432-L460)
- [incident_report.py:126-167](file://products/agent-platform/src/agent_service/services/incident_report.py#L126-L167)
- [incident_client.py:77-121](file://products/agent-platform/src/agent_service/services/incident_client.py#L77-L121)
- [operation_documents.py:488-531](file://products/agent-platform/src/agent_service/services/operation_documents.py#L488-L531)
- [document_prose.py:114-158](file://products/agent-platform/src/agent_service/services/document_prose.py#L114-L158)

### Error Handling
- **400 Bad Request**: Invalid label length, unknown session IDs, digest input errors
- **403 Forbidden**: Foreign session coverage without approvals:list capability, missing incident:read permission for incident reports
- **404 Not Found**: Document not found or foreign draft access
- **409 Conflict**: Already published document
- **503 Not Configured**: Missing incident service configuration for incident reports
- **502 Service Unavailable**: Incident service transport failure or upstream 5xx errors
- **Audit Events**: All operations emit structured audit events with correlation

**Section sources**
- [routes.py:738-956](file://products/agent-platform/src/agent_service/api/v2/routes.py#L738-L956)
- [v2.py:335-367](file://products/agent-platform/src/agent_service/schemas/v2.py#L335-L367)

### Execution Worker Integration

#### Overview
The execution worker integration provides isolated execution of approved mutating tools through the execution-runtime service with fail-closed behavior, signature verification, and receipt tracking. This implementation addresses SPEC-038 R-4 by separating the execution boundary from the agent process, reducing blast radius and improving security posture.

#### Key Features
- **Fail-Closed Behavior**: Missing worker URL or handoff token rejects before any network call with `worker_unavailable` reason
- **Blocking Handoff**: Approved mutating calls block on worker response with bounded timeout (`AGENT_EXECUTION_WORKER_TIMEOUT_SECONDS`)
- **Signature Verification**: Execution-runtime service verifies signed execution request envelopes and argument digests
- **Receipt Tracking**: Durable execution records track request/receipt lifecycle with first-write-wins semantics
- **Structured Error Handling**: Timeout exceptions raise `WorkerHandoffTimeout`, transport errors raise `WorkerHandoffError` with `worker_unavailable`
- **Audit Trail Integration**: All rejections and completions are audited with correlation to resume requests
- **Single-Flight Idempotency**: Worker executes each `execution_id` at most once with concurrent duplicate joining

#### Execution Flow
```mermaid
flowchart TD
A["Approved Mutating Tool Call"] --> B{"Worker Configured?"}
B --> |No| C["Reject with worker_unavailable"]
B --> |Yes| D["Build Signed Envelope"]
D --> E["Handoff to Execution Runtime"]
E --> F{"Signature Valid?"}
F --> |No| G["Reject with signature_invalid"]
F --> |Yes| H{"Digest Match?"}
H --> |No| I["Reject with args_digest_mismatch"]
H --> |Yes| J["Execute Tool Call"]
J --> K["Write Receipt"]
K --> L["Return Result"]
C --> M["Structured Rejection Result"]
G --> M
I --> M
L --> N["Tool Result to Stream"]
```

**Diagram sources**
- [execution_worker_client.py:54-145](file://products/agent-platform/src/agent_service/services/execution_worker_client.py#L54-L145)
- [handoff.py:66-169](file://products/execution-runtime/src/execution_runtime/api/routes/handoff.py#L66-L169)
- [gateway_tools.py:247-302](file://products/agent-platform/src/agent_service/tools/gateway_tools.py#L247-L302)

#### Error Handling Strategy
The execution worker client implements comprehensive error handling with distinct exception types:

- **WorkerHandoffError**: Raised for missing configuration, transport failures, or malformed responses with `worker_unavailable` reason
- **WorkerHandoffTimeout**: Raised when worker doesn't respond within timeout budget, allowing resumed streams to surface structured timeout results
- **Structured Rejections**: Worker-side verification failures return specific reasons (signature_invalid, args_digest_mismatch, unauthorized)

#### Configuration Requirements
- **AGENT_EXECUTION_WORKER_URL**: URL of the execution-runtime service
- **AGENT_EXECUTION_HANDOFF_TOKEN**: Static handoff token for authentication
- **AGENT_EXECUTION_WORKER_TIMEOUT_SECONDS**: Bounded timeout for handoff calls (default: 60.0)

**Section sources**
- [execution_worker_client.py:1-145](file://products/agent-platform/src/agent_service/services/execution_worker_client.py#L1-L145)
- [handoff.py:1-344](file://products/execution-runtime/src/execution_runtime/api/routes/handoff.py#L1-L344)
- [gateway_tools.py:247-302](file://products/agent-platform/src/agent_service/tools/gateway_tools.py#L247-L302)
- [runtime_settings.py:166-173](file://products/agent-platform/src/agent_service/runtime_settings.py#L166-L173)

## Decision Sync Robustness

### Overview
The decision sync robustness improvements address critical issues exposed during live approval testing where resumed replies after external decisions could require manual browser refreshes to appear in the owner window. The enhancements include time-based settle windows, progressive arrival presentation, and improved markdown rendering for resumed content.

### Time-Based Settle Window (SPEC-035 R-3)
```mermaid
sequenceDiagram
participant Owner as "Owner Window"
participant Poll as "Pending Decision Poll"
participant Approver as "Approver Window"
participant Kernel as "Runtime Kernel"
Note over Owner,Poll : Decision Landing Process
Approver->>Kernel : Submit decision (approve/deny)
Kernel->>Kernel : Execute tool calls and generate summary
Note over Poll : Old : 12 ticks × 5s = 60s budget<br/>New : 5-minute deadline with resets
Poll->>Poll : Reset settle window on each change
Poll->>Owner : Apply changes with typewriter reveal
Note over Owner : Background tabs throttle timers,<br/>so deadline approach is more reliable
```

**Diagram sources**
- [usePendingDecisionPoll.ts:1-23](file://products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts#L1-L23)
- [spec.md:87-99](file://docs/specs/SPEC-035-decision-sync-arrival-polish/spec.md#L87-L99)

### Progressive Arrival Presentation (SPEC-035 R-4)
When a reseed delivers new content after an external decision, the system now reveals it progressively instead of appearing in one silent jump:

```mermaid
flowchart TD
A["External Decision Received"] --> B["Detect Changed Turns"]
B --> C["Calculate Previous Reply Length"]
C --> D["Start Typewriter Reveal"]
D --> E["Apply Flash Highlight"]
E --> F["Scroll Into View"]
F --> G["Complete Progressive Display"]
```

**Diagram sources**
- [spec.md:101-119](file://docs/specs/SPEC-035-decision-sync-arrival-polish/spec.md#L101-L119)

### Enhanced Markdown Rendering
The transcript reconstruction now properly joins text blocks with blank lines to preserve markdown formatting:

```mermaid
flowchart TD
A["Assistant Message with Tool Calls"] --> B["Text Block 1: 'Checking controller...'"]
A --> C["Tool Call Execution"]
A --> D["Text Block 2: '## Pod Restart Summary'"]
B --> E["Join with \\n\\n"]
D --> E
E --> F["Proper Markdown Rendering"]
F --> G["Heading Renders Correctly"]
```

**Diagram sources**
- [session_transcript.py:67-87](file://products/agent-platform/src/agent_service/services/session_transcript.py#L67-L87)
- [test_session_workspace.py:178-221](file://products/agent-platform/tests/test_session_workspace.py#L178-L221)

### Key Improvements
- **Reliable Content Delivery**: Resumed turns now reach owner window without manual refresh
- **Better Visual Feedback**: Progressive reveal makes arrived content noticeable
- **Proper Markdown Rendering**: Headings, lists, and other block elements render correctly
- **Robust Timing**: Time-based settle window works reliably even with background tab throttling
- **Improved User Experience**: Stronger flash effects and scroll-to-view behavior

**Section sources**
- [spec.md:1-183](file://docs/specs/SPEC-035-decision-sync-arrival-polish/spec.md#L1-L183)
- [decision-sync-release-notes.md:1-82](file://docs/agentic-aiops-platform/release-notes/2026-08-26-decision-sync-arrival-polish.md#L1-L82)
- [session_transcript.py:67-87](file://products/agent-platform/src/agent_service/services/session_transcript.py#L67-L87)
- [test_session_workspace.py:178-221](file://products/agent-platform/tests/test_session_workspace.py#L178-L221)

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
HITS-->>API : No parked confirmations
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
- [runtime_kernel.py:404-447](file://products/agent-platform/src/agent_service/runtime_kernel.py#L404-L447)
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
- [runtime_kernel.py:404-447](file://products/agent-platform/src/agent_service/runtime_kernel.py#L404-L447)
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
- [runtime_kernel.py:178-223](file://products/agent-platform/src/agent_service/runtime_kernel.py#L178-L223)
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
- [runtime_kernel.py:178-223](file://products/agent-platform/src/agent_service/runtime_kernel.py#L178-L223)
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
-_delete_rows(session_id)
}
class InMemoryEvidenceStore {
+backend_name = "memory"
-_rows : dict[str, list[dict]]
+_next_frame_index(session_id, turn_index)
+_insert_rows(rows)
+_session_bytes(session_id)
+_evict_oldest_result_payload(session_id)
+_load_rows(session_id)
-_delete_rows(session_id)
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
-_delete_rows(session_id)
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
- [model_catalog.py:223-280](file://products/agent-platform/src/agent_service/services/model_catalog.py#L223-280)

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
- [routes.py:534-544](file://products/agent-platform/src/agent_service/api/v2/routes.py#L534-544)
- [model_catalog.py:168-174](file://products/agent-platform/src/agent_service/services/model_catalog.py#L168-L174)
- [runtime_kernel.py:248-261](file://products/agent-platform/src/agent_service/runtime_kernel.py#L248-L261)

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
- [routes.py:534-544](file://products/agent-platform/src/agent_service/api/v2/routes.py#L534-544)
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

## Multi-Model Runtime Capability

### Overview
The multi-model runtime capability enables dynamic model selection at runtime through a sophisticated resolution hierarchy that prioritizes explicit requests over pinned sessions, falling back to defaults when needed. This provides flexibility for operators to switch between different models without restarting sessions or affecting other users.

### Model Resolution Hierarchy
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

### Key Features
- **Priority-Based Resolution**: Explicit requests take precedence over pinned sessions, which override defaults
- **Credential-Gated Validation**: All model selections must exist in the credential-gated catalog
- **Session Persistence**: Model selections persist across turns within a session with TTL-aware storage
- **Graceful Degradation**: Invalid pinned models automatically fall back to defaults without errors
- **Error Handling**: Unknown models return 422 status codes with descriptive error messages
- **Audit Trail**: Model resolution decisions are logged with request and session context

### Implementation Details
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

## Dependency Analysis
The service has clear separation of concerns with minimal coupling between layers:
- API depends on schemas and kernel
- Kernel depends on session service, provider registry, evidence store, model catalog, and tools
- Providers are independent implementations registered at runtime
- Session service abstracts storage backend
- Evidence store provides independent persistence layer with dual backend support
- Model catalog provides credential-gated discovery with legacy alias resolution
- **Document repository provides persistent storage for typed operation documents with role-based access controls, envelope-only listings, deterministic summary generation, and AI-generated blurb extraction**
- **Incident report service provides specialized document type with incident service integration, dual-action authorization gates, and structured error handling**
- **Shift summary assembly builds deterministic digests from multiple durable stores with provenance tracking and handover skeleton computation**
- **Optional prose generation creates AI-powered narratives from digests with fail-soft behavior and AI-generated blurb extraction**
- **Flow authority management implements session-scoped flow context and approval tracking with TTL-based authorities for secure isolated tool execution**
- **Execution worker client provides isolated execution through execution-runtime service with fail-closed behavior**
- **Execution record store provides durable persistence for signed execution lifecycle tracking**
- **Enhanced confirmation record store provides durable HITL confirmation lifecycle management with turn_index field support and idempotent resolution**
- **Live discovery service depends on model catalog, provider registry, and runtime settings**
- **FastAPI lifespan manages discovery task lifecycle independently**
- Cross-cutting concerns are injected into the application lifecycle

```mermaid
graph LR
API["API Routes"] --> Kernel["RuntimeKernel"]
Kernel --> Session["SessionService"]
Kernel --> Evidence["EvidenceStore"]
Kernel --> ExecWorker["ExecutionWorkerClient"]
Kernel --> ExecRecords["ExecutionRecordStore"]
Kernel --> ConfirmStore["ConfirmationRecordStore"]
Kernel --> ModelCat["ModelCatalog"]
Kernel --> Registry["ProviderRegistry"]
Kernel --> Tools["GatewayTools"]
Kernel --> Closure["ToolkitClosure"]
Kernel --> FlowAuth["FlowAuthorityManager"]
Registry --> Base["BaseProvider"]
Base --> OpenAI["OpenAIProvider"]
Base --> DashScope["DashScopeProvider"]
Base --> DeepSeek["DeepSeekProvider"]
Base --> Luban["LubanProvider"]
Session --> Store["SessionStore"]
Session --> Transcript["Enhanced TranscriptExtractor"]
API --> HITL["ConfirmationRegistry"]
API --> ConfirmStore
API --> DocStore["OperationDocumentStore"]
API --> ShiftSum["ShiftSummary"]
API --> DocProse["DocumentProse"]
API --> IncClient["IncidentClient"]
API --> IncReport["IncidentReport"]
API --> Metrics["Metrics"]
API --> Obs["Observability"]
API --> Tel["Telemetry"]
Closure --> Tools
Evidence --> Metrics
Evidence --> Store
ExecWorker --> ExecRuntime["ExecutionRuntime"]
ExecRecords --> Metrics
ConfirmStore --> Metrics
ModelCat --> Metrics
ModelCat --> Registry
ModelDisc["ModelDiscovery"] --> ModelCat
ModelDisc --> Registry
ModelDisc --> Metrics
Lifespan["FastAPI Lifespan"] --> ModelDisc
DocStore --> Metrics
ShiftSum --> Metrics
DocProse --> Metrics
IncClient --> Metrics
IncReport --> Metrics
FlowAuth --> FlowContexts["FlowContextStore"]
FlowAuth --> FlowApprovals["FlowApprovalStore"]
FlowContexts --> Metrics
FlowApprovals --> Metrics
```

**Updated** The dependency graph now shows the enhanced toolkit registration pattern with per-request trace queues, auto-approval mechanism, v3 streaming support, multi-session workspace foundations, evidence store integration with dual backend support, **document repository integration with persistent typed documents, role-based access controls, envelope-only listings, deterministic summary generation, and AI-generated blurb extraction using SUMMARY marker format, incident report service integration with incident service client, dual-action authorization gates, and structured error handling, shift summary assembly for deterministic digest generation with handover skeleton computation, optional prose generation with fail-soft behavior and AI-generated blurb extraction, flow authority management with session-scoped flow context and approval tracking for secure isolated tool execution, execution worker integration for isolated tool execution with fail-closed behavior and signature verification, execution record persistence for signed execution lifecycle tracking, enhanced confirmation record store with turn_index field support, idempotent resolution, and cross-replica consistency, model catalog service with credential-gated discovery and legacy alias resolution, live model discovery service with background task management, voice-readiness support through input_modality parameter passthrough, and the new Luban provider for self-hosted OpenAI-compatible endpoints.** **SPEC-050 Enhancement**: Added browser tool surface expansion with improved pending decision polling and transcript handling for write-tier operations, supporting human-readable element descriptions for browser interaction tools.

**Diagram sources**
- [routes.py](file://products/agent-platform/src/agent_service/api/v2/routes.py)
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [session_service.py](file://products/agent-platform/src/agent_service/services/session_service.py)
- [operation_documents.py](file://products/agent-platform/src/agent_service/services/operation_documents.py)
- [incident_report.py](file://products/agent-platform/src/agent_service/services/incident_report.py)
- [incident_client.py](file://products/agent-platform/src/agent_service/services/incident_client.py)
- [shift_summary.py](file://products/agent-platform/src/agent_service/services/shift_summary.py)
- [document_prose.py](file://products/agent-platform/src/agent_service/services/document_prose.py)
- [flow_approvals.py](file://products/agent-platform/src/agent_service/services/flow_approvals.py)
- [execution_worker_client.py](file://products/agent-platform/src/agent_service/services/execution_worker_client.py)
- [execution_records.py](file://products/agent-platform/src/agent_service/services/execution_records.py)
- [confirmation_records.py](file://products/agent-platform/src/agent_service/services/confirmation_records.py)
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
- [handoff.py](file://products/execution-runtime/src/execution_runtime/api/routes/handoff.py)

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
- **Enhanced Workspace Optimization**: Server-side sorting in Postgres backend for efficient session listing
- **TTL-Aware Operations**: All workspace operations respect session TTL to prevent resource leaks
- **Fail-Open Design**: Workspace bookkeeping failures don't block core chat performance
- **Enhanced Transcript Extraction**: Best-effort design ensures degraded performance without errors
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
- **Enhanced Confirmation Record Optimization**: SQL-level idempotency prevents race conditions and reduces database contention
- **Turn Index Optimization**: Efficient turn_index computation and storage for precise confirmation card anchoring
- **Startup Sweep Scoping**: Scoped cleanup prevents sibling replica interference and reduces unnecessary database operations
- **Cross-Replica Consistency**: Durable records ensure consistent state across process restarts and replica boundaries
- **Decision Sync Robustness**: Time-based settle windows provide reliable content delivery even with background tab throttling
- **Progressive Arrival Presentation**: Typewriter-style reveal improves user experience without significant performance impact
- **Blank-Line Block Joining**: Efficient markdown rendering preserves formatting without additional processing overhead
- **Execution Worker Optimization**: Fail-closed behavior prevents unnecessary network calls when worker is unavailable
- **Signature Verification**: Efficient HMAC verification with constant-time comparison prevents timing attacks
- **Receipt Tracking**: First-write-wins semantics prevent duplicate execution and reduce database contention
- **Single-Flight Idempotency**: Worker executes each execution_id at most once, preventing redundant tool calls
- **Timeout Handling**: Bounded timeouts prevent hung requests and resource exhaustion
- **Structured Error Responses**: Specific error reasons enable targeted troubleshooting and monitoring
- **Document Repository Optimization**: Bounded storage with PER_OWNER_CAP prevents unbounded growth and automatic cleanup
- **Shift Summary Assembly**: Deterministic digest generation with graceful degradation for unreadable stores
- **Prose Generation Timeout**: Hard timeout prevents hung model from blocking document creation
- **Role-Based Access Control**: Efficient ownership validation and draft/published state filtering
- **Audit Trail Integration**: Fire-and-forget audit events minimize performance impact
- **Dual Backend Fallback**: Postgres unavailability gracefully falls back to in-memory for document operations
- **Retention Policy Enforcement**: Opportunistic sweeping prevents excessive storage consumption
- **Provenance Tracking**: Efficient source record reference management for audit and traceability
- **Envelope-Only Listings**: Efficient field stripping from list responses to prevent unauthorized content access
- **Deterministic Summary Computation**: Lightweight counts-only summary derivation from handover skeleton at creation time
- **PostgreSQL Migration**: Additive summary column migration with graceful degradation for legacy records
- **Summary Field Efficiency**: Summary field included in envelope-only listings without breaking security posture
- **AI-Generated Blurb Optimization**: Bounded character limits and efficient parsing logic prevent performance bottlenecks
- **Blurb Extraction Efficiency**: Case-insensitive marker detection with early termination for optimal performance
- **Prose Generation Fail-Safety**: Quick failure on model errors prevents blocking document creation
- **Robust Parsing Logic**: Forgiving parser handles edge cases without impacting overall performance
- **Incident Report Optimization**: Structured error hierarchy prevents raw stack traces and provides efficient degradation
- **Incident Service Client**: Bounded timeouts and Basic authentication minimize overhead for incident bundle fetching
- **Dual-Action Authorization**: Efficient policy evaluation for incident reports without impacting shift summary performance
- **Incident Digest Assembly**: Mechanical fact copying with provenance anchors ensures deterministic performance
- **Session Coverage**: Two-tier coverage model optimizes foreign session access with metadata-only responses
- **Graceful Degradation**: Unreadable incident service returns structured errors without 500 responses
- **Browser Tool Surface Optimization**: Enhanced pending decision polling with improved timeout handling and better user feedback
- **Display Hint Efficiency**: Human-readable element descriptions are efficiently generated from snapshot references
- **Write-Tier Classification**: Proper risk classification for browser tools prevents unnecessary confirmation overhead
- **Transcript Handling**: Optimized transcript reconstruction for browser tool operations with proper markdown rendering
- **Element Reference Mapping**: Efficient lookup of snapshot element references for display hint generation
- **Confirmation Request Payload**: Optimized serialization of browser tool confirmation requests with display hints
- **Test Coverage**: Comprehensive testing for browser tool scenarios ensures performance and reliability
- **Flow Authority Optimization**: Session-scoped flow context management with efficient TTL-based expiration handling
- **Process-Wide Singletons**: Flow contexts and approvals managed through process-wide singletons for efficient sharing
- **Browser Write Tools Classification**: Efficient classification of browser interaction tools as write-tier operations
- **Build Flow Request Function**: Optimized flow request building for isolated tool execution workflows
- **Approval Tracking**: Efficient approval tracking with owner and decider user identification
- **Expiration Handling**: Automatic expiration of flow authorities with safe failure modes and minimal overhead

**Updated** Performance considerations now include enhanced multi-session workspace optimizations, server-side sorting capabilities, TTL-aware operations, fail-open workspace bookkeeping that doesn't impact core chat performance, evidence store optimization with size-capped storage and automatic eviction, dual backend failover for resilience, voice-readiness support with minimal overhead through metadata-only processing, model catalog optimization with startup-derived catalog and efficient legacy alias resolution, live model discovery optimization with background task management, multi-tier caching strategies, atomic catalog updates with lock protection, multi-model runtime optimization with priority-based resolution and session-based caching, enhanced confirmation record optimization with turn_index field support, SQL-level idempotency, startup sweep scoping, cross-replica consistency guarantees, Luban provider optimization for self-hosted OpenAI-compatible endpoints with strict security requirements, decision sync robustness with time-based settle windows, progressive arrival presentation for improved user experience, blank-line block joining for efficient markdown rendering, **document repository optimization with bounded storage, role-based access control efficiency, audit trail integration, dual backend fallback, retention policy enforcement, provenance tracking efficiency, envelope-only listings for security, deterministic summary computation with lightweight handover skeleton processing, and AI-generated blurb extraction with bounded character limits and efficient parsing logic, incident report optimization with structured error handling, dual-action authorization efficiency, incident service client performance tuning, and digest assembly optimization with mechanical fact copying, shift summary assembly optimization with deterministic digest generation and graceful degradation, optional prose generation optimization with hard timeout protection, fail-soft behavior, and AI-generated blurb extraction, flow authority management optimization with session-scoped flow context, efficient TTL-based expiration handling, process-wide singleton management, browser write tools classification, optimized flow request building, efficient approval tracking, and safe expiration handling, execution worker optimization with fail-closed behavior preventing unnecessary network calls, signature verification efficiency with constant-time comparison, receipt tracking with first-write-wins semantics, single-flight idempotency preventing redundant executions, timeout handling with bounded budgets, and structured error responses for targeted troubleshooting, browser tool surface optimization with enhanced pending decision polling, improved timeout handling, better user feedback, efficient display hint generation, proper risk classification for write-tier operations, optimized transcript handling for browser tools, and efficient element reference mapping for human-readable descriptions.**

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
- **Enhanced Workspace Issues**: Verify session store backend connectivity and workspace bookkeeping operations
- **Enhanced Transcript Problems**: Check kernel state snapshot availability and transcript extraction logs with blank-line joining
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
- **Enhanced Confirmation Record Issues**: Verify durable storage backend connectivity and idempotent resolution
- **Turn Index Problems**: Check turn_index field persistence and confirmation card anchoring
- **Startup Sweep Problems**: Check HITL confirmation TTL configuration and sweep scoping
- **Concurrent Approval Issues**: Verify structured 409 responses and winner attribution
- **Cross-Replica Consistency**: Validate durable record persistence and state synchronization
- **Race Condition Debugging**: Check SQL-level guards and claim-time outcome persistence
- **Decision Sync Issues**: Verify time-based settle window configuration and visibility kick behavior
- **Markdown Rendering Problems**: Check blank-line block joining and proper paragraph boundaries
- **Resumed Content Delivery**: Verify progressive arrival presentation and typewriter reveal functionality
- **Background Tab Throttling**: Test time-based settle window reliability with background tabs
- **Execution Worker Issues**: Verify worker URL configuration, handoff token setup, and network connectivity
- **Signature Verification Failures**: Check execution signing key configuration and envelope integrity
- **Handoff Timeouts**: Monitor worker timeout settings and adjust based on tool execution complexity
- **Receipt Tracking Problems**: Verify execution record store connectivity and first-write-wins semantics
- **Worker Rejections**: Check worker-side verification errors and structured rejection reasons
- **Late Completions**: Monitor late completion metrics and handle first-write-wins scenarios
- **Single-Flight Issues**: Verify execution_id uniqueness and concurrent duplicate handling
- **Document Repository Issues**: Verify backend connectivity, ownership validation, and draft/published state management
- **Shift Summary Problems**: Check session store connectivity, evidence store availability, and confirmation record access
- **Prose Generation Failures**: Verify model availability, timeout configuration, and prompt contract adherence
- **Document API Errors**: Validate authorization headers, label length constraints, and session ID existence
- **Role-Based Access Issues**: Check X-Foreign-Coverage header configuration and approvals:list capability
- **Audit Trail Problems**: Verify audit service connectivity and fire-and-forget event emission
- **Retention Policy Issues**: Check retention days configuration and opportunistic sweep effectiveness
- **Capacity Limit Problems**: Verify PER_OWNER_CAP enforcement and oldest-first eviction behavior
- **Provenance Tracking Issues**: Validate source record references and citation counting
- **Envelope-Only Listing Issues**: Verify GET /documents endpoint strips digest and prose fields, single fetch returns full content
- **Cross-Owner Read Audit Issues**: Check document_read audit events fire for cross-owner reads through single fetch endpoint
- **Portal Drawer Issues**: Verify Documents view drawer uses audited single fetch instead of rendering from list results
- **Summary Computation Issues**: Verify handover skeleton presence and deterministic summary generation
- **PostgreSQL Migration Issues**: Check summary column migration and additive schema changes
- **Legacy Record Degradation**: Verify documents created before SPEC-041 carry no summary field and degrade gracefully
- **List Endpoint Summary**: Ensure summary field appears in envelope-only listings without breaking security posture
- **Blurb Extraction Issues**: Verify SUMMARY marker detection, case-insensitive parsing, and character bounding
- **Prose Generation Timeout**: Check PROSE_TIMEOUT_SECONDS configuration and model response times
- **AI-Generated Blurb Problems**: Validate parse_blurb function behavior with various response formats
- **Document Creation Failures**: Verify include_prose flag handling and fallback to digest-only documents
- **Enveloped Listing Performance**: Monitor envelope-only field stripping efficiency and response sizes
- **Incident Report Issues**: Verify incident service configuration, dual-action authorization, and structured error handling
- **Incident Service Connectivity**: Check AGENT_INCIDENT_SERVICE_URL, AGENT_INCIDENT_CLIENT_ID, and AGENT_INCIDENT_CLIENT_SECRET
- **Authorization Failures**: Verify both documents:create and incident:read permissions for incident report creation
- **Bundle Fetching**: Validate incident service client timeout configuration and Basic authentication
- **Digest Assembly**: Check incident envelope structure, triage report availability, and session coverage
- **Error Mapping**: Verify 503/502/404/4xx status code mapping and structured error responses
- **Foreign Session Access**: Validate approvals:list capability for foreign session metadata access
- **Provenance Tracking**: Verify incident_id inclusion in audit events and session coverage documentation
- **Graceful Degradation**: Test incident service unavailability handling and fallback behaviors
- **Browser Tool Issues**: Verify browser tool configuration, element reference handling, and display hint generation
- **Pending Decision Polling**: Check browser tool confirmation polling intervals and timeout handling
- **Transcript Handling**: Verify browser tool transcript reconstruction with proper markdown rendering
- **Risk Classification**: Validate write-tier classification for browser interaction tools
- **Element Reference Mapping**: Check snapshot element reference lookup and display hint generation
- **Confirmation Request Payload**: Verify browser tool confirmation requests include proper display hints
- **Test Coverage**: Validate browser tool scenarios including simple expressions, mutation blocking, and risk classification
- **Flow Authority Issues**: Verify flow context store connectivity, approval tracking, and TTL-based expiration handling
- **Flow Context Problems**: Check session-scoped flow context management and process-wide singleton operations
- **Approval Tracking Issues**: Verify flow approval recording, owner/decider user identification, and TTL configuration
- **Expiration Handling**: Test flow authority expiration behavior and safe failure modes
- **Browser Write Tools**: Validate browser tool classification as write-tier operations and proper confirmation flow
- **Build Flow Request**: Check flow request building for isolated tool execution workflows and proper parameter handling
- **Process Singleton Issues**: Verify flow contexts and approvals singleton management and thread safety
- **TTL Configuration**: Check TTL-based authority expiration and proper timeout handling
- **Session Isolation**: Validate proper isolation between different session contexts for flow authorities

Debugging utilities:
- Health check endpoints for service status
- Structured logging with correlation IDs
- Metrics endpoints for operational insights
- Telemetry traces for request flow analysis
- Token validation endpoints for debugging delegated token flow
- Tool schema inspection for verifying toolkit registration
- Trace event monitoring for audit trail analysis
- Environment variable inspection for auto-allow-list configuration
- **Enhanced Workspace Monitoring**: Check session store backend status and workspace operation metrics
- **Enhanced Transcript Debugging**: Verify kernel state snapshot availability and transcript extraction logs with blank-line joining
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
- **Enhanced Confirmation Record Debugging**: Verify SQL-level idempotency, turn_index field support, startup sweep scoping, and cross-replica consistency
- **Turn Index Debugging**: Validate turn_index computation, persistence, and confirmation card anchoring behavior
- **Race Condition Debugging**: Check structured 409 responses and winner attribution in concurrent approval scenarios
- **Durable Storage Debugging**: Validate backend connectivity, idempotent resolution, and state synchronization
- **Decision Sync Debugging**: Verify time-based settle window configuration, visibility kick behavior, and progressive arrival presentation
- **Markdown Rendering Debugging**: Check blank-line block joining, paragraph boundaries, and proper markdown formatting in resumed content
- **Execution Worker Debugging**: Verify worker URL configuration, handoff token setup, signature verification, and receipt tracking
- **Handoff Debugging**: Check execution-runtime service connectivity, signature validation, and argument digest verification
- **Receipt Debugging**: Verify execution record store connectivity, first-write-wins semantics, and late completion handling
- **Timeout Debugging**: Monitor worker timeout settings, adjust based on tool execution complexity, and handle structured timeout results
- **Rejection Debugging**: Check worker-side verification errors, structured rejection reasons, and audit trail correlation
- **Document Repository Debugging**: Verify backend connectivity, ownership validation, draft/published state management, and role-based access controls
- **Shift Summary Debugging**: Check session store connectivity, evidence store availability, confirmation record access, and provenance tracking
- **Prose Generation Debugging**: Verify model availability, timeout configuration, prompt contract adherence, and fail-soft behavior
- **Document API Debugging**: Validate authorization headers, label length constraints, session ID existence, and audit trail integration
- **Role-Based Access Debugging**: Check X-Foreign-Coverage header configuration, approvals:list capability, and draft/published state filtering
- **Retention Policy Debugging**: Verify retention days configuration, opportunistic sweep effectiveness, and capacity limit enforcement
- **Provenance Tracking Debugging**: Validate source record references, citation counting, and audit trail completeness
- **Envelope-Only Listing Debugging**: Verify GET /documents endpoint strips digest and prose fields from both mine and published scopes, single fetch returns full content with proper audit trail
- **Summary Computation Debugging**: Verify handover skeleton presence, deterministic summary generation, and summary field inclusion in envelope-only listings
- **PostgreSQL Migration Debugging**: Check summary column migration execution, additive schema changes, and legacy record degradation behavior
- **Blurb Extraction Debugging**: Verify SUMMARY marker detection, case-insensitive parsing, character bounding, and fallback behavior
- **AI-Generated Blurb Debugging**: Check parse_blurb function behavior, response format handling, and operator-friendly briefing generation
- **Prose Generation Timeout Debugging**: Monitor PROSE_TIMEOUT_SECONDS configuration, model response times, and fail-soft degradation behavior
- **Document Creation Debugging**: Validate include_prose flag handling, fallback to digest-only documents, and AI-generated blurb extraction
- **Enveloped Listing Performance Debugging**: Monitor envelope-only field stripping efficiency and response sizes
- **Incident Report Debugging**: Verify incident service configuration, dual-action authorization enforcement, and structured error handling
- **Incident Client Debugging**: Check AGENT_INCIDENT_* environment variables, Basic authentication, and timeout configuration
- **Authorization Debugging**: Validate documents:create and incident:read permission enforcement for incident report creation
- **Bundle Fetching Debugging**: Verify incident service connectivity, incident ID validation, and error mapping to HTTP postures
- **Digest Assembly Debugging**: Check incident envelope structure, triage report availability, session coverage, and provenance tracking
- **Foreign Session Debugging**: Validate approvals:list capability for foreign session metadata access and coverage determination
- **Graceful Degradation Debugging**: Test incident service unavailability handling, 503/502/404/4xx error mapping, and structured error responses
- **Browser Tool Debugging**: Verify browser tool configuration, element reference handling, display hint generation, and pending decision polling
- **Pending Decision Polling Debugging**: Check browser tool confirmation polling intervals, timeout handling, and user feedback mechanisms
- **Transcript Handling Debugging**: Verify browser tool transcript reconstruction, markdown rendering, and proper paragraph boundaries
- **Risk Classification Debugging**: Validate write-tier classification for browser interaction tools and proper confirmation flow
- **Element Reference Mapping Debugging**: Check snapshot element reference lookup, display hint generation, and human-readable descriptions
- **Confirmation Request Payload Debugging**: Verify browser tool confirmation requests include proper display hints and element descriptions
- **Test Coverage Debugging**: Validate browser tool scenarios including simple expressions, mutation blocking, and risk classification
- **Flow Authority Debugging**: Verify flow context store connectivity, approval tracking functionality, and TTL-based expiration handling
- **Flow Context Debugging**: Check session-scoped flow context management, process-wide singleton operations, and thread safety
- **Approval Tracking Debugging**: Validate flow approval recording, owner/decider user identification, and TTL configuration
- **Expiration Handling Debugging**: Test flow authority expiration behavior, safe failure modes, and proper timeout handling
- **Browser Write Tools Debugging**: Validate browser tool classification as write-tier operations and proper confirmation flow
- **Build Flow Request Debugging**: Check flow request building for isolated tool execution workflows and proper parameter handling
- **Process Singleton Debugging**: Verify flow contexts and approvals singleton management, thread safety, and memory efficiency

**Updated** Troubleshooting guide now includes enhanced multi-session workspace troubleshooting, enhanced transcript extraction debugging strategies with blank-line block joining, HITL confirmation registry diagnostics, workspace operation monitoring, evidence store troubleshooting with dual backend support, voice-readiness debugging with input_modality parameter validation and parity testing, comprehensive evidence persistence monitoring and debugging, model catalog troubleshooting with provider configuration validation, model selection debugging, and operator portal model display verification, plus live model discovery troubleshooting with background task monitoring, provider filtering validation, cache tier diagnostics, and discovery performance optimization, and multi-model runtime troubleshooting with model resolution debugging and session pinning diagnostics, enhanced confirmation record troubleshooting with turn_index field support, SQL-level idempotency validation, startup sweep scoping verification, and cross-replica consistency testing, Luban provider troubleshooting with self-hosted endpoint configuration and bearer token authentication, decision sync robustness troubleshooting with time-based settle window validation, progressive arrival presentation debugging, and markdown rendering verification for resumed content, **document repository troubleshooting with backend connectivity validation, ownership verification, draft/published state management, role-based access control testing, envelope-only listing verification, summary computation debugging, PostgreSQL migration validation, legacy record degradation testing, AI-generated blurb extraction debugging, incident report troubleshooting with incident service client validation, dual-action authorization testing, structured error handling verification, and digest assembly verification, shift summary troubleshooting with deterministic digest generation and graceful degradation, optional prose generation troubleshooting with model availability checking, timeout configuration validation, prompt contract adherence verification, fail-soft behavior testing, and AI-generated blurb extraction debugging, flow authority management troubleshooting with flow context store validation, approval tracking verification, TTL-based expiration testing, session-scoped context management, process-wide singleton operations, browser write tools classification, flow request building validation, and safe expiration handling, execution worker troubleshooting with worker URL configuration validation, handoff token setup verification, signature verification debugging, receipt tracking diagnostics, timeout handling validation, and structured rejection reason analysis, browser tool troubleshooting with browser tool configuration validation, element reference handling verification, display hint generation testing, pending decision polling debugging, transcript handling validation, risk classification verification, and comprehensive test coverage for browser tool scenarios.**

**Section sources**
- [metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [observability.py](file://products/agent-platform/src/agent_service/core/observability.py)
- [telemetry.py](file://products/agent-platform/src/agent_service/core/telemetry.py)
- [request_context.py](file://products/agent-platform/src/agent_service/core/request_context.py)

## Conclusion
The Agent Platform Service provides a robust foundation for AI agent orchestration with multi-provider support, durable session management, and comprehensive observability. Its modular architecture enables easy customization and scaling while maintaining high performance and reliability.

**Updated** The service now includes comprehensive multi-model runtime capability with per-turn model selection, session-based model pinning, credential-gated model catalogs, live model discovery with background task management, sophisticated error handling for model resolution failures, and enhanced operational visibility through detailed logging and metrics collection. **Additionally, the service now features a complete document repository system that enables operators to create durable, typed operation documents with deterministic digests assembled from multiple data sources, optional AI-generated prose summaries with AI-generated one-line blurbs using SUMMARY marker format, role-based access controls with draft/published states, envelope-only listings for security, and deterministic counts-only summaries computed from handover skeletons at creation time.** The addition of the Luban provider enables self-hosted OpenAI-compatible endpoints with strict security requirements. **The enhanced confirmation record storage layer provides turn_index field support for precise confirmation card anchoring, idempotent resolution with SQL-level guards, improved startup sweep scoping to prevent sibling replica interference, and better error handling for concurrent approval attempts with structured 409 responses. The service also features enhanced decision sync robustness with time-based settle windows, improved session transcript reconstruction with blank-line block joining for proper markdown rendering, and progressive arrival presentation for resumed content.** **Critical Security Fix v0.21.1**: Implemented envelope-only document listings for GET /documents endpoint to prevent unauthorized content access while maintaining full content access through audited single-document fetch endpoints, ensuring cross-owner reads are properly audited. **SPEC-041 Enhancement**: Added deterministic counts-only document summaries computed from handover skeletons at creation time, stored in the operation documents table with PostgreSQL migration support, and surfaced in envelope-only list responses without breaking security posture. **v0.23.3 Enhancement**: Added AI-generated one-line blurbs extracted from prose responses using SUMMARY marker format, providing operator-friendly briefings with bounded character limits and robust parsing logic. **SPEC-043 Enhancement**: Added incident report document type support with dedicated incident service integration, dual-action authorization gates requiring both documents:create and incident:read permissions, structured error handling for incident service dependencies, and comprehensive test coverage for incident-specific workflows. **SPEC-050 Enhancement**: Enhanced browser tool surface with expanded write-tier operations including web.click, web.type, web.select, web.press_key, and web.upload_file, with improved pending decision polling and transcript handling for browser interaction tools featuring human-readable element descriptions and proper risk classification. **NEW FLOW AUTHORITY MANAGEMENT**: Added comprehensive flow authority management with 240+ lines of enhanced runtime kernel integration including build_flow_request function, flow approval system integration, and TTL-based flow authorities for secure isolated tool execution workflows with session-scoped flow context and approval tracking. These enhancements strengthen the platform's flexibility, enable dynamic model management, provide detailed operational visibility, ensure cross-replica consistency for HITL workflows, improve user experience with reliable content delivery, and maintain the performance characteristics that make it suitable for production AI operations.

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
- **Enhanced Transcript Access**: Retrieve conversation history from kernel state snapshots with proper markdown rendering
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

#### Enhanced Confirmation Record Store Configuration with Turn Index Support
- **Backend Selection**: Configure AGENT_STATE_STORE_BACKEND for memory or postgres
- **Database Setup**: Set AGENT_STATE_DB_URL for Postgres confirmation record persistence
- **TTL Configuration**: Set AGENT_HITL_CONFIRM_TIMEOUT for confirmation expiration (default: 600 seconds)
- **Turn Index Verification**: Validate turn_index field persistence and confirmation card anchoring
- **Startup Sweep**: Verify sweep scoping prevents sibling replica interference
- **Idempotent Resolution**: Test SQL-level guards prevent race conditions in concurrent approvals
- **Cross-Replica Consistency**: Validate durable record persistence across process restarts
- **Monitoring**: Track confirmation lifecycle metrics and sweep operations
- **Card Anchoring**: Verify confirmation cards anchor under their specific parking turns instead of stacking under newest turn

#### Execution Worker Configuration with Fail-Closed Behavior
- **Worker URL**: Configure `AGENT_EXECUTION_WORKER_URL` for execution-runtime service endpoint
- **Handoff Token**: Set `AGENT_EXECUTION_HANDOFF_TOKEN` for authenticated communication with worker
- **Timeout Settings**: Configure `AGENT_EXECUTION_WORKER_TIMEOUT_SECONDS` for bounded handoff calls (default: 60.0)
- **Fail-Closed Validation**: Verify missing worker configuration rejects with `worker_unavailable` reason
- **Signature Verification**: Ensure `AGENT_EXECUTION_SIGNING_KEY` is configured for envelope verification
- **Receipt Tracking**: Validate execution record store connectivity for request/receipt lifecycle
- **Error Handling**: Test timeout scenarios and structured error responses
- **Audit Trail**: Monitor execution audit events for approved mutating tool calls
- **Single-Flight Idempotency**: Verify concurrent duplicate handling and replay protection

#### Decision Sync Robustness Configuration
- **Settle Window**: Configure time-based settle window for reliable content delivery
- **Visibility Kick**: Ensure visibility/focus events trigger immediate polling
- **Progressive Presentation**: Verify typewriter-style reveal for arrived content
- **Markdown Rendering**: Test blank-line block joining for proper heading and list rendering
- **Background Tab Testing**: Validate settle window reliability with background tab throttling
- **Arrival Detection**: Verify detection of changed turns and previous reply length calculation
- **Flash Effects**: Test stronger visual feedback for arrived content
- **Scroll-to-View**: Verify automatic scrolling to first arrived group

#### Document Repository Configuration
- **Backend Selection**: Configure AGENT_STATE_STORE_BACKEND for memory or postgres
- **Database Setup**: Set AGENT_STATE_DB_URL for Postgres document persistence
- **Retention Policy**: Configure RETENTION_DAYS for automatic cleanup (default: 30 days)
- **Capacity Limits**: Adjust PER_OWNER_CAP for per-owner document limits (default: 20)
- **Authorization**: Configure documents:create permission for document creation
- **Foreign Coverage**: Set X-Foreign-Coverage header for approvals:list capability
- **Audit Trail**: Verify audit event emission for all document operations
- **Provenance Tracking**: Validate source record references and citation counting
- **Role-Based Access**: Test owner-only draft visibility and team-wide published access
- **Envelope-Only Listings**: Verify GET /documents endpoint strips digest and prose fields, single fetch returns full content with proper audit trail
- **Summary Computation**: Verify deterministic counts-only summaries computed from handover skeletons at creation time
- **PostgreSQL Migration**: Check summary column migration and additive schema changes
- **Legacy Record Support**: Validate documents created before SPEC-041 carry no summary field and degrade gracefully
- **AI-Generated Blurbs**: Verify SUMMARY marker detection, character bounding, and robust parsing logic
- **Prose Generation**: Test include_prose flag handling and fallback to digest-only documents
- **Blurb Extraction**: Validate parse_blurb function behavior with various response formats

#### Incident Report Configuration
- **Incident Service Setup**: Configure `AGENT_INCIDENT_SERVICE_URL`, `AGENT_INCIDENT_CLIENT_ID`, and `AGENT_INCIDENT_CLIENT_SECRET`
- **Dual-Action Authorization**: Ensure both documents:create and incident:read permissions for incident report creation
- **Timeout Configuration**: Set `AGENT_INCIDENT_CLIENT_TIMEOUT_SECONDS` for bounded incident service calls
- **Basic Authentication**: Verify incident service client credentials in INCIDENT_QUERY_CLIENTS registry
- **Error Handling**: Test 503/502/404/4xx status code mapping and structured error responses
- **Bundle Fetching**: Validate incident service connectivity and incident ID format validation
- **Session Coverage**: Test owner vs foreign session coverage with approvals:list capability
- **Provenance Tracking**: Verify incident_id inclusion in audit events and session coverage documentation
- **Graceful Degradation**: Test incident service unavailability handling and fallback behaviors
- **Digest Assembly**: Validate incident envelope structure, triage report availability, and dispatch outcomes
- **Prose Generation**: Test incident report prose generation with digest-only prompt contract
- **Portal Integration**: Verify incident picker in Documents dialog and incident report rendering

#### Shift Summary Configuration
- **Session Coverage**: Configure MAX_SESSION_IDS for bounded input (default: 20)
- **Label Length**: Set MAX_LABEL_LENGTH for document labeling (default: 120 characters)
- **Foreign Access**: Validate approvals:list capability requirement for foreign session coverage
- **Graceful Degradation**: Test unreadable store handling with unavailable status reporting
- **Provenance Integrity**: Verify source record references and cited record tracking
- **Coverage Tiers**: Test owner vs foreign session digest differences
- **Error Handling**: Validate DigestInputError, UnknownSessionError, and ForeignSessionDenied scenarios
- **Handover Skeleton**: Verify deterministic handover section with covered-session counts, decision/execution details, open items, and quiet flag
- **Summary Generation**: Test deterministic counts-only summary computation from handover skeleton

#### Optional Prose Generation Configuration
- **Timeout Settings**: Configure PROSE_TIMEOUT_SECONDS for model response timeout (default: 30.0)
- **Model Availability**: Verify runtime default model is accessible for prose generation
- **Fail-Soft Behavior**: Test model error handling with prose_status=failed fallback
- **Prompt Safety**: Validate digest-only input contract and no fabrication guarantee
- **Streaming Support**: Test both streaming and non-streaming model response handling
- **Empty Response Handling**: Verify empty reply detection and error treatment
- **Integration Testing**: Test prose generation with various digest structures and document types
- **AI-Generated Blurbs**: Verify SUMMARY marker extraction, character bounding, and operator-friendly briefing generation
- **Blurb Parsing**: Test parse_blurb function with various response formats and edge cases
- **Prose Status Handling**: Validate included/failed/not_requested status values and corresponding document states

#### Browser Tool Surface Configuration
- **Browser Tool Setup**: Configure browser tools with proper element reference handling and display hint generation
- **Pending Decision Polling**: Set appropriate polling intervals and timeout configurations for browser tool confirmations
- **Transcript Handling**: Verify browser tool transcript reconstruction with proper markdown rendering and paragraph boundaries
- **Risk Classification**: Validate write-tier classification for browser interaction tools and proper confirmation flow
- **Element Reference Mapping**: Configure snapshot element reference lookup and display hint generation
- **Confirmation Request Payload**: Ensure browser tool confirmation requests include proper display hints and element descriptions
- **Test Coverage**: Validate browser tool scenarios including simple expressions, mutation blocking, and risk classification
- **User Experience**: Test human-readable element descriptions and proper confirmation card anchoring
- **Performance Optimization**: Monitor browser tool performance and optimize pending decision polling intervals
- **Error Handling**: Test browser tool error scenarios and proper error messaging to users

#### Flow Authority Management Configuration
- **Backend Selection**: Configure AGENT_STATE_STORE_BACKEND for memory or postgres
- **Database Setup**: Set AGENT_STATE_DB_URL for Postgres flow approval persistence
- **TTL Configuration**: Set appropriate TTL values for flow authority expiration (default: 900 seconds)
- **Session Isolation**: Verify proper isolation between different session contexts for flow authorities
- **Approval Tracking**: Validate flow approval recording with owner and decider user identification
- **Expiration Handling**: Test TTL-based expiration behavior and safe failure modes
- **Browser Write Tools**: Configure proper classification of browser interaction tools as write-tier operations
- **Build Flow Request**: Validate flow request building for isolated tool execution workflows
- **Process Singletons**: Verify flow contexts and approvals singleton management and thread safety
- **Monitoring**: Track flow authority lifecycle metrics and expiration events
- **Security**: Ensure proper session-scoped flow context management and approval validation
- **Integration**: Test flow authority integration with execution worker and tool execution workflows

**Updated** Practical examples now include guidance on leveraging AgentScope 2.x toolkit registration, anti-hallucination guards, auto-approval mechanism, v3 streaming protocols, per-request trace queues, comprehensive multi-session workspace operations, evidence store configuration and management, model catalog setup with multi-provider support, live model discovery configuration with background task management, provider filtering mechanisms, cache tier optimization, atomic catalog updates with lock protection, multi-model runtime configuration with per-turn selection and session-based pinning, enhanced confirmation record store configuration with turn_index field support, idempotent resolution, startup sweep scoping, cross-replica consistency validation, Luban provider configuration for self-hosted OpenAI-compatible endpoints with complete operator workflow management, **document repository configuration with backend setup, retention policies, capacity limits, authorization configuration, foreign coverage handling, audit trail verification, provenance tracking, role-based access control, envelope-only listing verification, summary computation validation, PostgreSQL migration testing, legacy record degradation testing, AI-generated blurb extraction validation, and prose generation configuration with SUMMARY marker format, incident report configuration with incident service client setup, dual-action authorization testing, structured error handling verification, and digest assembly verification, shift summary configuration with session coverage limits, label length constraints, foreign access validation, graceful degradation testing, provenance integrity verification, coverage tier testing, error scenario validation, handover skeleton generation, and deterministic summary computation, optional prose generation configuration with timeout settings, model availability verification, fail-soft behavior testing, prompt safety validation, streaming support testing, empty response handling, integration testing, and AI-generated blurb extraction with robust parsing logic, flow authority management configuration with session-scoped flow context, approval tracking setup, TTL-based expiration handling, browser write tools classification, flow request building validation, process-wide singleton management, and safe expiration handling, execution worker configuration with fail-closed behavior, signature verification, receipt tracking, and isolated tool execution, browser tool surface configuration with browser tool setup, pending decision polling optimization, transcript handling validation, risk classification verification, element reference mapping, confirmation request payload validation, comprehensive test coverage, user experience testing, performance optimization, and error handling, decision sync robustness configuration with time-based settle windows, progressive arrival presentation, and blank-line block joining for proper markdown rendering.**

**Section sources**
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [registry.py](file://products/agent-platform/src/agent_service/providers/registry.py)
- [base.py](file://products/agent-platform/src/agent_service/providers/base.py)
- [routes.py](file://products/agent-platform/src/agent_service/api/v2/routes.py)
- [session_service.py](file://products/agent-platform/src/agent_service/services/session_service.py)
- [session_store.py](file://products/agent-platform/src/agent_service/services/session_store.py)
- [session_transcript.py](file://products/agent-platform/src/agent_service/services/session_transcript.py)
- [hitl_confirmations.py](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py)
- [confirmation_records.py](file://products/agent-platform/src/agent_service/services/confirmation_records.py)
- [evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [model_catalog.py](file://products/agent-platform/src/agent_service/services/model_catalog.py)
- [model_discovery.py](file://products/agent-platform/src/agent_service/services/model_discovery.py)
- [app.py](file://products/agent-platform/src/agent_service/app.py)
- [gateway_tools.py](file://products/agent-platform/src/agent_service/tools/gateway_tools.py)
- [execution_worker_client.py](file://products/agent-platform/src/agent_service/services/execution_worker_client.py)
- [execution_records.py](file://products/agent-platform/src/agent_service/services/execution_records.py)
- [operation_documents.py](file://products/agent-platform/src/agent_service/services/operation_documents.py)
- [incident_report.py](file://products/agent-platform/src/agent_service/services/incident_report.py)
- [incident_client.py](file://products/agent-platform/src/agent_service/services/incident_client.py)
- [shift_summary.py](file://products/agent-platform/src/agent_service/services/shift_summary.py)
- [document_prose.py](file://products/agent-platform/src/agent_service/services/document_prose.py)
- [flow_approvals.py](file://products/agent-platform/src/agent_service/services/flow_approvals.py)
- [handoff.py](file://products/execution-runtime/src/execution_runtime/api/routes/handoff.py)
- [v2.py](file://products/agent-platform/src/agent_service/schemas/v2.py)
- [test_chat_stream_modality.py](file://products/agent-platform/tests/test_chat_stream_modality.py)
- [test_evidence_store.py](file://products/agent-platform/tests/test_evidence_store.py)
- [test_model_catalog.py](file://products/agent-platform/tests/test_model_catalog.py)
- [test_model_discovery.py](file://products/agent-platform/tests/test_model_discovery.py)
- [test_model_switching.py](file://products/agent-platform/tests/test_model_switching.py)
- [test_confirmation_records.py](file://products/agent-platform/tests/test_confirmation_records.py)
- [test_session_workspace.py](file://products/agent-platform/tests/test_session_workspace.py)
- [test_execution_worker_client.py](file://products/agent-platform/tests/test_execution_worker_client.py)
- [test_execution_records.py](file://products/agent-platform/tests/test_execution_records.py)
- [test_runtime_settings.py](file://products/agent-platform/tests/test_runtime_settings.py)
- [test_operation_documents.py](file://products/agent-platform/tests/test_operation_documents.py)
- [test_shift_summary.py](file://products/agent-platform/tests/test_shift_summary.py)
- [test_document_prose.py](file://products/agent-platform/tests/test_document_prose.py)
- [test_documents.py](file://products/agent-platform/tests/test_documents.py)
- [test_documents_repository.py](file://products/platform-gateway/tests/test_documents_repository.py)
- [test_flow_approvals.py](file://products/agent-platform/tests/test_flow_approvals.py)
- [spec.md](file://docs/specs/SPEC-035-decision-sync-arrival-polish/spec.md)
- [decision-sync-release-notes.md](file://docs/agentic-aiops-platform/release-notes/2026-08-26-decision-sync-arrival-polish.md)
- [SPEC-038-isolated-execution-worker/spec.md](file://docs/specs/SPEC-038-isolated-execution-worker/spec.md)
- [SPEC-039-operations-document-repository/spec.md](file://docs/specs/SPEC-039-operations-document-repository/spec.md)
- [SPEC-041-documents-readability-and-digest-reference/spec.md](file://docs/specs/SPEC-041-documents-readability-and-digest-reference/spec.md)
- [SPEC-043-incident-report-document-type/spec.md](file://docs/specs/SPEC-043-incident-report-document-type/spec.md)
- [SPEC-050-browser-tools-expansion-and-samples/spec.md](file://docs/specs/SPEC-050-browser-tools-expansion-and-samples/spec.md)
- [document-read-audit-integrity.md](file://docs/agentic-aiops-platform/release-notes/2026-08-27-document-read-audit-integrity.md)
- [documents-readability-release-notes.md](file://docs/agentic-aiops-platform/release-notes/2026-08-28-documents-readability-and-digest-reference.md)
- [incident-report-release-notes.md](file://docs/agentic-aiops-platform/release-notes/2026-08-29-incident-report-document-type.md)
- [session-evidence.schema.json](file://shared/shared-contracts/schemas/session-evidence.schema.json)
- [model-catalog.schema.json](file://shared/shared-contracts/schemas/model-catalog.schema.json)
- [operation-document.schema.json](file://shared/shared-contracts/schemas/operation-document.schema.json)
- [luban.py](file://products/agent-platform/src/agent_service/providers/luban.py)
- [usePendingDecisionPoll.ts](file://products/operator-portal/web-ui/app/src/chat/usePendingDecisionPoll.ts)
- [decoder.ts](file://products/operator-portal/web-ui/app/src/stream/decoder.ts)
- [sessions.ts](file://products/operator-portal/web-ui/app/src/api/sessions.ts)
- [test_browser_connector.py](file://products/tool-gateway/tests/test_browser_connector.py)