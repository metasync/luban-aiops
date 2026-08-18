# Runtime Kernel and Agent Lifecycle

<cite>
**Referenced Files in This Document**
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [gateway_tools.py](file://products/agent-platform/src/agent_service/tools/gateway_tools.py)
- [runtime_settings.py](file://products/agent-platform/src/agent_service/runtime_settings.py)
- [delegation_client.py](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py)
- [test_runtime_kernel.py](file://products/agent-platform/tests/test_runtime_kernel.py)
- [test_gateway_tools.py](file://products/agent-platform/tests/test_gateway_tools.py)
- [agent_state_store.py](file://products/agent-platform/src/agent_service/services/agent_state_store.py)
- [metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [routes.py](file://products/agent-platform/src/agent_service/api/v2/routes.py)
- [v2.py](file://products/agent-platform/src/agent_service/schemas/v2.py)
- [session_service.py](file://products/agent-platform/src/agent_service/services/session_service.py)
</cite>

## Update Summary
**Changes Made**
- Added comprehensive state persistence via AgentStateStore protocol with pluggable backends (memory and Postgres)
- Implemented TTL-based cleanup mechanism for stale agent states with automatic sweep operations
- Integrated metrics tracking for agent state store operations including errors, fallbacks, and backend selection
- Enhanced v2 chat endpoints with structured output support through response_schema parameter
- Added health check endpoints that report agent state store status and readiness
- Improved error handling and graceful degradation when state persistence fails

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

## Introduction
This document explains the runtime kernel and agent lifecycle management within the agent platform. It covers how the execution engine initializes, manages agent states, processes runtime settings and environment variables, supports dynamic configuration updates, and handles errors, resource cleanup, and graceful shutdown. The system now includes enhanced delegated token handling for secure tool execution, per-user toolkit closures, graceful degradation mechanisms, and comprehensive state persistence capabilities. **Updated**: The runtime kernel now implements sophisticated state persistence via the AgentStateStore protocol with TTL-based cleanup, metrics tracking, and structured output support for v2 chat endpoints, ensuring conversation durability across service restarts while maintaining robust operation even when authentication tokens are unavailable or state persistence fails.

## Project Structure
The runtime kernel and lifecycle are implemented primarily under the agent platform product. Key modules include:
- Runtime kernel: orchestrates agent lifecycle events and state transitions with enhanced token handling and state persistence
- State persistence layer: pluggable AgentStateStore protocol with memory and Postgres backends supporting TTL-based cleanup
- Tool gateway integration: provides token-aware tool discovery and execution with rotation support
- Runtime settings: loads and validates configuration from files and environment variables
- Services: runtime service for orchestration, session service for durable state, and session store for persistence
- Metrics and observability: comprehensive monitoring for agent state operations and system health
- V2 API endpoints: structured output support and enhanced health checks reporting state store status

```mermaid
graph TB
subgraph "Agent Platform"
A["app.py"] --> B["main.py"]
B --> C["entrypoints.runtime.py"]
C --> D["runtime_kernel.py"]
D --> E["runtime_service.py"]
E --> F["session_service.py"]
F --> G["session_store.py"]
D --> H["runtime_settings.py"]
H --> I["core/config.py"]
H --> J["core/env.py"]
D --> K["Token Handler"]
K --> L["Per-User Toolkits"]
L --> M["Graceful Degradation"]
D --> N["Gateway Tools"]
N --> O["Tool Discovery"]
O --> P["Token Rotation Support"]
D --> Q["AgentStateStore"]
Q --> R["InMemory Backend"]
Q --> S["Postgres Backend"]
S --> T["TTL Cleanup"]
D --> U["Metrics Tracking"]
U --> V["Error Counters"]
U --> W["Backend Gauges"]
D --> X["V2 Chat Endpoints"]
X --> Y["Structured Output"]
X --> Z["Health Checks"]
end
```

**Diagram sources**
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [agent_state_store.py](file://products/agent-platform/src/agent_service/services/agent_state_store.py)
- [metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [routes.py](file://products/agent-platform/src/agent_service/api/v2/routes.py)
- [session_service.py](file://products/agent-platform/src/agent_service/services/session_service.py)

**Section sources**
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [agent_state_store.py](file://products/agent-platform/src/agent_service/services/agent_state_store.py)
- [metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)

## Core Components
- Runtime Kernel: Central coordinator for agent lifecycle events (start, execute, pause, resume, terminate), maintaining per-agent state, coordinating with services, managing delegated token handling for secure tool execution, and implementing state persistence through the AgentStateStore protocol.
- AgentStateStore Protocol: Pluggable state persistence interface supporting multiple backends (in-memory and Postgres) with TTL-based cleanup and graceful degradation when backends fail.
- Gateway Tools Integration: Provides token-aware tool discovery and execution with support for dynamic token rotation during long-running sessions.
- Runtime Settings: Configuration loader that merges defaults, file-based settings, and environment variables; exposes typed accessors and supports reloads.
- Environment and Config Utilities: Provide strongly-typed access to runtime settings and environment variables, with validation and fallbacks.
- Runtime Service: Orchestrates high-level operations such as creating sessions, invoking agents, and managing long-running tasks.
- Session Service and Store: Manage durable session state, including persistence and retrieval, ensuring consistency across restarts and coordinating with agent state cleanup.
- Token Handler: Manages delegated token lifecycle and validation for secure tool execution with rotation support.
- Per-User Toolkits: Provides isolated tool execution contexts based on user identity and permissions with token rotation awareness.
- Graceful Degradation: Ensures system continues operating with limited functionality when authentication tokens are unavailable or state persistence fails.
- Metrics and Observability: Comprehensive monitoring for agent state operations, backend selection, error rates, and system health indicators.

Key responsibilities:
- Initialization: Load settings, validate environment, create dependencies, boot services, initialize token handlers, and configure state persistence backends.
- Lifecycle Management: Handle agent state transitions and event-driven execution with token-aware tool execution, rotation support, and persistent state management.
- Configuration: Support dynamic updates without restarting the process where feasible.
- Error Handling: Robust error propagation, retries, safe cleanup, graceful degradation when tokens are missing, rotated, or state persistence fails.
- Performance: Concurrency control, resource pooling, efficient memory usage, optimized token validation with rotation handling, and efficient state persistence with TTL cleanup.
- State Persistence: Save and restore agent conversation state across service restarts using pluggable backends with automatic TTL-based cleanup.

**Section sources**
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [agent_state_store.py](file://products/agent-platform/src/agent_service/services/agent_state_store.py)
- [metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)

## Architecture Overview
The runtime architecture centers around a kernel that coordinates lifecycle events through services and persists state via sessions with enhanced state persistence capabilities. Configuration is loaded at startup and can be refreshed dynamically. The enhanced architecture now includes token delegation for secure tool execution with rotation support, comprehensive state persistence through the AgentStateStore protocol, TTL-based cleanup mechanisms, and structured output support for v2 chat endpoints.

```mermaid
sequenceDiagram
participant Client as "Client"
participant API as "API Layer"
participant Kernel as "RuntimeKernel"
participant StateStore as "AgentStateStore"
participant TokenHandler as "Token Handler"
participant RSvc as "RuntimeService"
participant SSvc as "SessionService"
participant Store as "SessionStore"
participant Gateway as "Tool Gateway"
Client->>API : "POST /api/v2/chat"
API->>Kernel : "reply_text(message, response_schema)"
Kernel->>StateStore : "load_state(session_id)"
StateStore-->>Kernel : "persisted_state or None"
Kernel->>Kernel : "build_agent(state)"
Kernel->>TokenHandler : "validate_delegated_token()"
TokenHandler-->>Kernel : "token_valid or error"
Kernel->>Kernel : "transition to RUNNING"
Kernel->>Gateway : "discover_tools(bearer_token)"
Gateway-->>Kernel : "tool_definitions or []"
Kernel->>Kernel : "build_request_toolkit(token)"
Kernel->>RSvc : "run_agent(session_id)"
RSvc->>SSvc : "update_state(RUNNING)"
SSvc->>Store : "persist(session)"
Store-->>SSvc : "ok"
RSvc-->>Kernel : "result + structured_output"
Kernel->>StateStore : "save_state(session_id, state)"
StateStore-->>Kernel : "ok"
Kernel->>Kernel : "transition to COMPLETED or FAILED"
Kernel-->>API : "content + structured_output"
API-->>Client : "response"
```

**Diagram sources**
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [agent_state_store.py](file://products/agent-platform/src/agent_service/services/agent_state_store.py)
- [routes.py](file://products/agent-platform/src/agent_service/api/v2/routes.py)
- [session_service.py](file://products/agent-platform/src/agent_service/services/session_service.py)

## Detailed Component Analysis

### Runtime Kernel with State Persistence
The runtime kernel manages agent lifecycle events and enforces state transitions with comprehensive state persistence capabilities. It coordinates with the runtime service to perform work, uses the session service to persist state changes, integrates with the AgentStateStore protocol for conversation durability, and includes enhanced delegated token handling for secure tool execution with rotation support.

Lifecycle events and typical transitions:
- Start: Initialize resources, load settings, prepare context, set up token handlers, and configure state persistence backends.
- Execute: Transition to running, validate delegated tokens, restore persisted state, invoke agent logic with per-user toolkits, handle results or errors, and save state after completion.
- Pause: Suspend execution, save checkpoint, transition to paused.
- Resume: Restore checkpoint, re-validate tokens if needed, transition back to running.
- Terminate: Clean up resources, finalize state, revoke tokens, delete persisted state, transition to terminated.

Enhanced state persistence features:
- Pluggable AgentStateStore protocol supporting multiple backends (memory, Postgres)
- Automatic state restoration on agent construction for conversation continuity
- TTL-based cleanup of stale agent states with configurable expiration
- Graceful degradation when state persistence fails without affecting core functionality
- Structured output support through response_schema parameter in v2 chat endpoints
- Comprehensive metrics tracking for state operations, errors, and backend selection
- Health check endpoints reporting state store status and readiness

```mermaid
stateDiagram-v2
[*] --> Idle
Idle --> Starting : "start"
Starting --> Running : "execute"
Running --> Paused : "pause"
Paused --> Running : "resume"
Running --> Completed : "complete"
Running --> Failed : "error"
Completed --> Terminating : "terminate"
Failed --> Terminating : "terminate"
Paused --> Terminating : "terminate"
Terminating --> [*]
note right of Running : "Save state after each turn\nRestore state on next use"
note right of Completed : "Persist final state\nClean up resources"
```

Key behaviors:
- Event-driven transitions with guards to prevent invalid state changes.
- Integration with session persistence and agent state store for comprehensive durability.
- Error handling that captures exceptions, logs context, marks sessions appropriately, and implements graceful degradation when state persistence fails.
- Resource cleanup on termination to avoid leaks, including token revocation and state deletion.
- Token-aware execution that falls back to limited functionality when authentication fails.
- State restoration from persistent storage to maintain conversation continuity across service restarts.
- **Updated**: Structured output support through response_schema parameter enabling validated structured responses in v2 chat endpoints.
- **Updated**: TTL-based cleanup preventing accumulation of stale agent states with automatic sweep operations.

**Section sources**
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [test_runtime_kernel.py](file://products/agent-platform/tests/test_runtime_kernel.py)

### AgentStateStore Protocol and Backends
The AgentStateStore protocol provides a pluggable interface for agent state persistence with two built-in backends: in-memory for development/testing and Postgres for production deployments. The implementation includes comprehensive TTL-based cleanup, metrics tracking, and graceful degradation capabilities.

Key features:
- **Updated**: Pluggable protocol design supporting multiple storage backends
- **Updated**: In-memory backend for development and CI environments with simple key-value storage
- **Updated**: Postgres backend with production-grade durability, connection management, and SQL optimization
- **Updated**: TTL-based cleanup mechanism automatically removing stale agent states beyond configured expiration
- **Updated**: Comprehensive metrics tracking for state operations, errors, and backend selection
- **Updated**: Graceful degradation falling back to in-memory storage when Postgres is unavailable
- **Updated**: Health checking capabilities for monitoring backend availability

Implementation details:
- `save_state()`: Persists agent state JSON with automatic TTL refresh on writes
- `load_state()`: Restores agent state with TTL refresh on reads to keep active sessions alive
- `delete_state()`: Removes agent state when sessions are deleted
- `is_ready()`: Health check endpoint for monitoring backend availability
- TTL cleanup: Background sweep operations remove expired states efficiently
- Metrics integration: Tracks errors, fallbacks, and active backend selection

**Section sources**
- [agent_state_store.py](file://products/agent-platform/src/agent_service/services/agent_state_store.py)
- [test_agent_state_store.py](file://products/agent-platform/tests/test_agent_state_store.py)

### V2 Chat Endpoints with Structured Output
The v2 chat endpoints provide enhanced functionality including structured output support, comprehensive health checks, and improved error handling. These endpoints integrate with the state persistence layer and provide better observability into system health.

Key features:
- **Updated**: Structured output support through response_schema parameter enabling validated structured responses
- **Updated**: Enhanced health check endpoints reporting agent state store status and readiness
- **Updated**: Improved error handling with detailed status information
- **Updated**: Better integration with state persistence layer for conversation durability
- **Updated**: Comprehensive metrics tracking for chat requests and state operations

Implementation details:
- `chat()`: Handles blocking chat requests with optional structured output validation
- `chat_stream()`: Provides streaming responses with normalized event formats
- `health()`: Reports system health including agent state store backend status and readiness
- `create_session()` and `read_session()`: Session management with state persistence integration
- Structured output: Validates and returns structured data when response_schema is provided

**Section sources**
- [routes.py](file://products/agent-platform/src/agent_service/api/v2/routes.py)
- [v2.py](file://products/agent-platform/src/agent_service/schemas/v2.py)

### Metrics and Observability
Comprehensive metrics tracking provides visibility into agent state operations, backend selection, error rates, and system health. The metrics system follows established conventions and provides both counters and gauges for different types of observations.

Key features:
- **Updated**: Agent state store metrics including backend selection, operation errors, and fallback counts
- **Updated**: Session store metrics for cross-reference with agent state operations
- **Updated**: HTTP request metrics for API performance monitoring
- **Updated**: Chat request counting for usage analytics
- **Updated**: Prometheus-compatible metrics format for easy integration with monitoring systems

Implementation details:
- `record_agent_state_backend()`: Tracks active backend selection (memory vs postgres)
- `record_agent_state_error()`: Counts failed state operations by operation type
- `record_agent_state_fallback()`: Counts instances where system fell back to in-memory storage
- `record_chat_request()`: Counts chat requests for usage analytics
- `setup_metrics()`: Configures Prometheus middleware and /metrics endpoint

**Section sources**
- [metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)

### Session Service Integration
The session service coordinates between session management and agent state persistence, ensuring consistent cleanup when sessions are deleted and providing proper ownership validation.

Key features:
- **Updated**: Integration with AgentStateStore for coordinated state cleanup
- **Updated**: Proper error handling when state deletion fails without affecting session deletion
- **Updated**: Ownership validation ensuring users can only access their own sessions
- **Updated**: Idempotent session creation for dedicated sessions

Implementation details:
- `delete_session()`: Deletes both session and associated agent state with fail-open behavior
- `ensure_session()`: Creates or retrieves sessions with proper ownership validation
- `create_named_session()`: Supports dedicated sessions for incident triage scenarios
- State cleanup: Automatically removes agent state when sessions are deleted

**Section sources**
- [session_service.py](file://products/agent-platform/src/agent_service/services/session_service.py)

## Dependency Analysis
The runtime kernel depends on configuration, services, persistence layers, token handling components, and the new state persistence infrastructure. The following diagram shows key relationships including the enhanced state persistence architecture with TTL cleanup and metrics tracking:

```mermaid
classDiagram
class RuntimeKernel {
+start()
+execute(session_id)
+pause(session_id)
+resume(session_id)
+terminate(session_id)
+handle_delegated_token()
+get_per_user_toolkit()
+_build_request_toolkit()
+_restore_state()
-_snapshot_state()
}
class AgentStateStore {
<<interface>>
+backend_name
+save_state()
+load_state()
+delete_state()
+is_ready()
}
class InMemoryAgentStateStore {
+backend_name = "memory"
+save_state()
+load_state()
+delete_state()
+is_ready()
}
class PostgresAgentStateStore {
+backend_name = "postgres"
+ttl_seconds
+initialize()
+save_state()
+load_state()
+delete_state()
+is_ready()
}
class Metrics {
+record_agent_state_backend()
+record_agent_state_error()
+record_agent_state_fallback()
+record_chat_request()
}
class GatewayTools {
+discover_tools()
+build_gateway_toolkit()
+invoke_gateway_tool()
+_build_request_toolkit()
}
class DelegationClient {
+obtain_delegated_token()
+get_cached()
+put()
+exchange()
}
class RuntimeService {
+create_session()
+run_agent(session_id)
+get_status(session_id)
}
class SessionService {
+init_session()
+update_state(session_id, state)
+get_state(session_id)
+delete_session()
}
class SessionStore {
+save(session)
+load(session_id)
+delete(session_id)
}
class RuntimeSettings {
+get(key)
+reload()
}
RuntimeKernel --> AgentStateStore : "persists state"
RuntimeKernel --> Metrics : "tracks operations"
RuntimeKernel --> GatewayTools : "uses"
RuntimeKernel --> DelegationClient : "manages"
RuntimeKernel --> RuntimeService : "uses"
RuntimeKernel --> RuntimeSettings : "reads"
RuntimeService --> SessionService : "uses"
SessionService --> SessionStore : "persists"
SessionService --> AgentStateStore : "cleans up state"
AgentStateStore <|-- InMemoryAgentStateStore
AgentStateStore <|-- PostgresAgentStateStore
PostgresAgentStateStore --> Metrics : "records errors/fallbacks"
```

**Diagram sources**
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [agent_state_store.py](file://products/agent-platform/src/agent_service/services/agent_state_store.py)
- [metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [session_service.py](file://products/agent-platform/src/agent_service/services/session_service.py)

**Section sources**
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [agent_state_store.py](file://products/agent-platform/src/agent_service/services/agent_state_store.py)
- [metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [session_service.py](file://products/agent-platform/src/agent_service/services/session_service.py)

## Performance Considerations
- Concurrency Control: Use bounded worker pools for agent execution to prevent resource exhaustion.
- Memory Management: Avoid holding large payloads in memory; stream data where possible and release references promptly.
- Persistence Efficiency: Batch writes to session store and use optimistic locking to reduce contention.
- Configuration Reload: Perform atomic swaps of settings to minimize downtime and avoid partial reads.
- Token Validation Optimization: Cache validated tokens and implement efficient lookup mechanisms.
- **Updated**: State Persistence Optimization: Implement efficient state restoration and saving with minimal overhead, using TTL-based cleanup to prevent storage bloat.
- **Updated**: TTL-Based Cleanup: Automatic sweep operations remove stale agent states efficiently without impacting active sessions.
- **Updated**: Metrics Collection: Lightweight metrics recording with minimal performance impact for operational visibility.
- **Updated**: Structured Output Processing: Efficient schema validation and serialization for structured responses without blocking operations.
- Graceful Degradation: Minimize performance impact when falling back to empty Toolkit or in-memory state storage by using lazy initialization and caching.
- Observability: Emit metrics and traces for lifecycle events, latency, error rates, token validation performance, and state persistence operations.

## Troubleshooting Guide
Common issues and strategies:
- Invalid State Transitions: Ensure guards prevent illegal transitions; log detailed context when blocked.
- Configuration Errors: Validate required environment variables and config keys early; surface clear messages.
- Session Persistence Failures: Retry with backoff, mark sessions as failed, and alert operators.
- Graceful Shutdown: Drain in-flight requests, flush pending writes, and close connections cleanly.
- Resource Leaks: Track open handles and enforce timeouts; implement finalizers to guarantee cleanup.
- Token Validation Failures: Implement proper error handling, logging, and fallback mechanisms.
- **Updated**: State Persistence Issues: Monitor agent state store health, track error rates, and verify TTL cleanup operations are functioning correctly.
- **Updated**: Backend Selection Problems: Check environment variables for correct backend configuration and verify database connectivity for Postgres backend.
- **Updated**: TTL Cleanup Issues: Monitor sweep operations and verify stale states are being cleaned up according to configured TTL values.
- **Updated**: Structured Output Validation: Verify response schemas are valid and debug validation failures when structured output is requested.
- **Updated**: Metrics Collection: Monitor agent_state_errors_total, agent_state_fallbacks_total, and agent_state_backend metrics for operational insights.
- Graceful Degradation Issues: Monitor system behavior when tokens are unavailable or state persistence fails and ensure limited functionality continues.

Operational checks:
- Health endpoints to verify readiness and liveness including agent state store status.
- Metrics dashboards for throughput, latency, error rates, token validation success rates, and state persistence operations.
- Logs correlation using request IDs and session IDs.
- Token validation failure tracking and alerting.
- **Updated**: State persistence monitoring: Track agent state store backend selection, error rates, and fallback occurrences.
- **Updated**: TTL cleanup verification: Monitor sweep operations and verify storage growth is controlled by TTL expiration.
- **Updated**: Structured output debugging: Log schema validation errors and response formatting issues for troubleshooting.

**Section sources**
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [agent_state_store.py](file://products/agent-platform/src/agent_service/services/agent_state_store.py)
- [metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [routes.py](file://products/agent-platform/src/agent_service/api/v2/routes.py)

## Conclusion
The runtime kernel and agent lifecycle management provide a robust foundation for executing agents with durable state, configurable behavior, resilient operations, enhanced security through delegated token handling with rotation support, and comprehensive state persistence capabilities. By combining clear state transitions, strong configuration management, careful resource handling, sophisticated token management with graceful degradation, and advanced state persistence through the AgentStateStore protocol, the system supports scalable and maintainable agent execution in production environments. **Updated**: The enhanced state persistence system ensures conversation continuity across service restarts through pluggable backends with TTL-based cleanup, while structured output support in v2 chat endpoints enables validated structured responses. The comprehensive metrics and observability framework provides deep insights into system health and performance, ensuring reliable operation even when authentication tokens are unavailable, rotated during long-running sessions, or when state persistence backends experience failures.