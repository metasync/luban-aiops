---
kind: error_handling
name: FastAPI HTTP Exceptions, Domain-Specific Error Types, and Defensive Fallbacks
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/tool-gateway/src/api_gateway/services/policy_engine.py
    - products/tool-gateway/src/api_gateway/api/routes/auth.py
    - products/identity-broker/src/identity_service/app.py
    - products/agent-platform/src/agent_service/app.py
    - products/tool-gateway/src/api_gateway/app.py
---

The Luban AIOps platform uses a layered error-handling approach across its FastAPI-based services (agent-platform, identity-broker, tool-gateway). Errors are handled through three complementary mechanisms: HTTP-level exceptions for client-facing failures, domain-specific exception classes for internal service errors, and defensive try/except blocks that fall back to safe responses rather than crashing.

**HTTP-Level Errors (FastAPI)**
All services use FastAPI's built-in `HTTPException` for client-facing error responses. The agent-platform routes raise `HTTPException(status_code=401)` when required headers like `X-User-ID` are missing. Each service registers a consistent HTTP middleware that logs request lifecycle events (method, path, status_code, duration_ms) via a structured `log_event` call, ensuring all errors pass through uniform observability instrumentation.

**Domain-Specific Exception Classes**
Services define typed exception classes for internal failure modes:
- `ProviderConfigurationError(ValueError)` in agent-platform providers signals invalid or incomplete provider configuration (missing API keys, wrong provider name).
- `PolicyLoadError(Exception)` in the tool-gateway policy engine indicates malformed or missing policy bundles.
- `TokenVerificationError` in the tool-gateway token verifier handles JWT validation failures.
These exceptions propagate up through the service layers and are caught by route handlers or middleware, never leaking implementation details to clients.

**Defensive Fallback Patterns**
The agent-platform's `AgentKernel` implements robust fallback behavior. When AgentScope runtime is not configured, it returns placeholder text messages instead of raising errors. Provider failures are captured via `remember_error()` and surfaced through `runtime_metadata().last_error`, while streaming operations fall back to a `fallback_stream()` that yields safe SSE events with error context. This pattern ensures the service remains responsive even when downstream dependencies fail.

**Error Propagation Strategy**
Errors follow a clear propagation pattern: route handlers catch domain exceptions and convert them to appropriate HTTP responses, while unexpected exceptions are logged with full stack traces via `LOGGER.exception()` and converted to generic server errors. The identity-broker's auth routes demonstrate graceful handling by returning `{"authenticated": False}` on token verification failures rather than propagating exceptions.

**No Centralized Error Middleware**
The codebase does not implement custom exception handlers or centralized error transformation middleware. Instead, each service relies on FastAPI's default exception handling combined with explicit `try/except` blocks at critical boundaries (provider calls, policy evaluation, token verification). This keeps error handling localized and predictable.