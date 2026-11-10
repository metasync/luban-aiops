---
kind: error_handling
name: Domain Exception Classes with Structured Reason Codes and Route-Level HTTP Mapping
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/services/execution_protocol.py
    - products/agent-platform/src/agent_service/services/execution_worker_client.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/tool-gateway/src/tool_gateway/services/token_verifier.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
---

## Approach

Luban does not use a single shared base error type or a global FastAPI exception handler. Instead, each product defines its own small set of domain exception classes (typically named `<Domain>Error`) raised from service-layer functions, and the route handlers catch those exceptions to translate them into FastAPI `HTTPException`s with explicit status codes. There is no repository-wide `errors/` package; error types live next to the domain logic that raises them.

## Key files and packages

- `products/agent-platform/src/agent_service/services/execution_protocol.py` — `ProtocolError(ValueError)` carrying a `reason` string; used for signed-envelope validation, signature checks, lifetime bounds, and replay detection.
- `products/agent-platform/src/agent_service/services/execution_worker_client.py` — `WorkerHandoffError(Exception)` with a `reason` attribute (e.g. `worker_unavailable`) and `WorkerHandoffTimeout`; documents the fail-closed posture: missing config → reject before any network call, timeouts surface as a structured timeout result, transport errors degrade to `worker_unavailable`.
- `products/tool-gateway/src/tool_gateway/services/token_verifier.py` — `TokenVerificationError(Exception)` with a `detail` attribute, plus `HumanIdentityRequired(TokenVerificationError)` for the human-provenance gate.
- `products/platform-gateway/src/platform_gateway/services/policy_engine.py` — `PolicyLoadError(Exception)`.
- `products/platform-gateway/src/platform_gateway/services/token_verifier.py` — `TokenVerificationError(Exception)`.
- Other per-domain errors: `ProviderConfigurationError`, `UnknownModelError`, `AgentRoleError`, `DelegatedIdentityError`, `IncidentClientError`, `SkillsClientError`, `DigestInputError`, `UnknownSessionError` (agent-platform); `StoreError`, `IngestAuthError`, `SettingsError`, `ConnectorConfigError`, `NormalizationError`, `QueryAuthError`, `TriageError` (audit/incident); `AuthorizationError`, `CliError`, `CustodyError`, `DelegatedInvokeError`, `ConfigurationError`, `PasswordPolicyError`, `DelegatedAcquisitionError` (tool-gateway).
- `products/agent-platform/src/agent_service/api/v2/routes.py` — the main route file that maps service-layer exceptions to HTTP status codes.

## Architecture and conventions

1. **Per-domain exception classes.** Each product defines its own error classes close to the code that raises them. Most inherit directly from `Exception` or `ValueError`; there is no common base class shared across products.

2. **Structured payload on exceptions.** Two conventions coexist:
   - A `reason` attribute (e.g. `ProtocolError(reason)`, `WorkerHandoffError(reason, message)`), used when the caller needs to forward a semantic rejection code (often to an upstream worker or audit record).
   - A `detail` attribute (e.g. `TokenVerificationError(detail)`), used when the value is intended to become the HTTP response body.

3. **Route-level translation to HTTP.** The FastAPI routes do not rely on a global exception handler. In `agent_service/api/v2/routes.py`, service-layer exceptions are caught explicitly and re-raised as `fastapi.HTTPException(status_code=..., detail=...)`. Examples observed:
   - `SkillsDependencyNotConfigured` / `IncidentDependencyNotConfigured` → 503.
   - `SkillsServiceUnavailable` / `IncidentServiceUnavailable` → 502.
   - `IncidentNotFound` → 404.
   - `NoValidatedTriageReport` → 409.
   - `SkillsClientRejected` / `IncidentClientRejected` → forwarded `status_code` / `message` from the upstream client.
   - Missing headers (`X-User-ID`) → 401.
   - Upstream tool-gateway invocation errors → 503/502/404 depending on the caught exception.

4. **Fail-closed posture for external calls.** The execution handoff client documents this explicitly: missing worker URL or handoff token raises before any network call, timeouts raise a dedicated `WorkerHandoffTimeout`, and transport errors raise `WorkerHandoffError` with `worker_unavailable`. No in-process fallback exists.

5. **Credential-safe logging.** Transport failures log only the exception class name, never the exception text, because "transport messages can echo URLs or payloads and must never leak credentials" (`execution_worker_client.py`).

6. **No global exception handler at the gateway layer.** Neither `platform_gateway/api/router.py` nor `tool_gateway/api/router.py` registers an `@app.exception_handler`. Only one sample app under `samples/acme-admin/app/src/acme_admin/main.py` uses `@app.exception_handler(AdminAuthRequired)`, which is a sample, not a platform convention.

7. **Validation via schema + sentinel errors.** `execution_protocol.py` caches Draft202012 validators keyed by schema name and wraps any JSON-schema mismatch as `ProtocolError("bad_request")`, also enforcing canonical JSON serialization and metadata size limits.

## Conventions and constraints

- Domain errors are defined as small classes near the code that raises them rather than centralized in a shared package.
- Errors carry structured fields (`reason` or `detail`) instead of relying solely on the exception message, so callers can distinguish failure modes without parsing strings.
- Route handlers perform explicit try/except blocks mapping service-layer exceptions to HTTP status codes; there is no repository-wide automatic mapping from Python exceptions to HTTP responses.
- External-call failures follow a fail-closed pattern: configuration gaps are rejected before any outbound request, and transport failures degrade to a generic unavailable/rejection reason rather than leaking raw stack traces.
- Sensitive values (handoff tokens, delegated tokens, bearer tokens) are never included in log output; only exception class names are logged for transport failures.
- Protocol-level violations (signature, replay, identity conflict, unsupported version) are represented by `ProtocolError` with a machine-readable `reason` code rather than ad-hoc strings.