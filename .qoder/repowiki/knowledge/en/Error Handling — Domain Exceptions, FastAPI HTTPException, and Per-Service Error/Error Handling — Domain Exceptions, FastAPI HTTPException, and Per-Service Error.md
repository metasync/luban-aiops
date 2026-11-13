---
kind: error_handling
name: Error Handling — Domain Exceptions, FastAPI HTTPException, and Per-Service Error Boundaries
category: error_handling
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/services/agent_role.py
    - products/agent-platform/src/agent_service/services/execution_protocol.py
    - products/agent-platform/src/agent_service/services/execution_worker_client.py
    - products/agent-platform/src/agent_service/services/incident_client.py
    - products/agent-platform/src/agent_service/services/shift_summary.py
    - products/agent-platform/src/agent_service/services/skills_client.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/audit-service/src/audit_service/services/ingest_auth.py
    - products/incident-service/src/incident_service/services/connectors.py
    - products/incident-service/src/incident_service/services/incident_store.py
    - products/incident-service/src/incident_service/services/normalization.py
    - products/incident-service/src/incident_service/services/query_auth.py
    - products/incident-service/src/incident_service/services/triage.py
---

## Approach

The Luban platform is a multi-product Python/Node workspace (agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway, operator-portal). Each product is an independent FastAPI service that owns its own error model; there is no shared `errors` package or cross-product exception hierarchy. Errors are handled through three complementary layers:

1. **Domain-level custom exceptions** raised inside services/providers.
2. **FastAPI `HTTPException`** raised at route/service boundaries to produce HTTP responses.
3. **Per-service middleware / app wiring** that catches top-level exceptions and turns them into structured JSON or redirects.

There is no use of `try/except ... finally` as a general error-handling pattern, no `panic`/`recover` equivalent, and no global exception handler registered via `@app.exception_handler` in any of the production products (only `samples/acme-admin/app/src/acme_admin/main.py` registers one for its sample app).

## Key Files and Packages

### Custom domain exceptions (per product)

| Product | File | Exception(s) | Meaning |
|---|---|---|---|
| agent-platform | `src/agent_service/providers/base.py` | `ProviderConfigurationError(ValueError)` | Missing/invalid provider settings |
| agent-platform | `src/agent_service/runtime_kernel.py` | `UnknownModelError(ValueError)` | Model not found in catalog |
| agent-platform | `src/agent_service/services/agent_role.py` | `AgentRoleError(ValueError)` | Invalid agent role |
| agent-platform | `src/agent_service/services/delegated_identity.py` | `DelegatedIdentityError(ValueError)` | Delegated identity validation failure |
| agent-platform | `src/agent_service/services/execution_protocol.py` | `ProtocolError(ValueError)` | Execution protocol violation |
| agent-platform | `src/agent_service/services/execution_worker_client.py` | `WorkerHandoffError(Exception)` | Worker handoff failure |
| agent-platform | `src/agent_service/services/incident_client.py` | `IncidentClientError(Exception)` | Incident client call failure |
| agent-platform | `src/agent_service/services/shift_summary.py` | `DigestInputError`, `UnknownSessionError` | Shift summary inputs |
| agent-platform | `src/agent_service/services/skills_client.py` | `SkillsClientError(Exception)` | Skills hub call failure |
| audit-service | `src/audit_service/services/audit_store.py` | `StoreError(Exception)` | Store I/O failure |
| audit-service | `src/audit_service/services/ingest_auth.py` | `IngestAuthError(Exception)` | Audit ingest auth failure |
| execution-runtime | `src/execution_runtime/services/execution_protocol.py` | `ProtocolError(ValueError)` | Execution protocol violation |
| identity-broker | `src/identity_service/services/exchange_service.py` | `ExchangeError(Exception)` | Token exchange failure |
| incident-service | `src/incident_service/core/config.py` | `SettingsError(Exception)` | Configuration error |
| incident-service | `src/incident_service/services/connectors.py` | `ConnectorConfigError(Exception)` | Connector configuration error |
| incident-service | `src/incident_service/services/incident_store.py` | `StoreError(Exception)` | Store I/O failure |
| incident-service | `src/incident_service/services/normalization.py` | `NormalizationError(Exception)` | Normalization failure |
| incident-service | `src/incident_service/services/query_auth.py` | `QueryAuthError(Exception)` | Query authorization failure |
| incident-service | `src/incident_service/services/triage.py` | `TriageError(Exception)` | Triage failure |
| platform-gateway | `src/platform_gateway/services/policy_engine.py` | `PolicyLoadError(Exception)` | Policy bundle load/validation failure |
| platform-gateway | `src/platform_gateway/services/token_verifier.py` | `TokenVerificationError(Exception)`, `HumanIdentityRequired(TokenVerificationError)` | JWT verification failure |
| tool-gateway | `src/tool_gateway/services/gateway_service.py` | `DelegatedInvokeError` (imported from `delegated_invoke`) | Delegated invocation failure |

### HTTP boundary mapping

FastAPI routes raise `HTTPException` directly with explicit status codes:

- **401 Unauthorized**: missing/invalid bearer token, malformed header, expired token, missing human provenance (`products/agent-platform/src/agent_service/api/v2/routes.py`, `products/tool-gateway/src/tool_gateway/services/gateway_service.py`).
- **403 Forbidden**: policy deny, mutating-tool without `tools:mutate`, delegated execution disabled (`enforce_policy` in `tool_gateway/services/gateway_service.py` raises `HTTPException(status_code=403, detail={...})`).
- **422 Unprocessable Entity**: missing required HITL acknowledgment (`agent-platform v2 routes`).
- **502/503 Bad Gateway / Service Unavailable**: downstream service failures mapped from caught exceptions in `agent-platform v2 routes` (`status_code=503` for target unavailable, `502` for upstream error, `503` for recovery query errors).

### Middleware and app-level handling

`platform-gateway/app.py` installs a single `http` middleware that wraps every request in try/except:

```python
@app.middleware("http")
async def log_requests(request: Request, call_next):
    ...
    try:
        response = await call_next(request)
    except Exception:
        if not secret_edge:
            raise
        response = redirect() if browser_navigation else JSONResponse(
            {"detail": "Target authorization unavailable"}, status_code=503)
```

This is the only repository-wide exception boundary: it swallows all exceptions on the `/api/v1/targets/authorizations` secret edge and returns a generic 503, while re-raising on non-secret paths so FastAPI's default JSON error response applies. The middleware also attaches `Cache-Control: no-store` headers on secret-edge responses and emits a `http_request` event via `log_event`.

No other product registers a global `@app.exception_handler`; they rely on FastAPI's default exception-to-JSON conversion after their own service-layer `HTTPException` conversions.

## Architecture and Conventions

1. **Domain exceptions are narrow and typed.** Each product defines small exception classes close to the code that raises them. Many validation/configuration errors inherit from `ValueError` (e.g. `ProviderConfigurationError`, `UnknownModelError`, `AgentRoleError`, `ProtocolError`) rather than a shared base, keeping them lightweight and compatible with standard library expectations.

2. **Service-layer exceptions are translated to HTTP at the boundary.** `tool_gateway.services.gateway_service.resolve_request_identity` converts `TokenVerificationError` into `HTTPException(401, ...)`. `enforce_policy` converts a `PolicyDecision.decision == "deny"` into `HTTPException(403, detail={...})`. This keeps business logic free of HTTP concerns.

3. **Policy evaluation never raises; it returns a decision object.** `platform_gateway.services.policy_engine.evaluate` returns a frozen `PolicyDecision(dataclass)` with fields `decision`, `matched_rule_ids`, `reason`, `action`, `subject`, `approval`. Callers decide whether to map it to 403, 400, or continue. Load-time validation errors instead raise `PolicyLoadError`, which is caught by readiness endpoints and surfaced as `status: degraded`.

4. **Token verification normalizes library exceptions.** `token_verifier.verify_token` catches `jwt.ExpiredSignatureError`, `InvalidIssuerError`, `InvalidAudienceError`, `InvalidTokenError` and re-raises as `TokenVerificationError` with stable string messages (`"token expired"`, `"invalid token issuer"`, etc.), allowing callers to distinguish expired vs invalid tokens for metrics.

5. **Audit trail is decoupled from error propagation.** Both `tool-gateway` and `agent-platform` emit audit events (`emit_audit_event`) alongside error paths, ensuring denied invocations are recorded even when they become HTTP 403/400 responses.

6. **Redaction overflow is a controlled error envelope.** In `tool-gateway/_dispatch_invocation`, when redaction would drop too much data, the result is replaced with `make_error_result(tool_name, "REDACTION_OVERFLOW", ...)` carrying the original connector's risk tier and source system — fail-closed but traceable.

7. **Test harnesses define their own exceptions.** `products/agent-platform/harness/routing_accuracy.py` defines `HarnessPrerequisiteError(RuntimeError)` for test setup failures, isolated from production error types.

## Conventions and Constraints

- **Custom exceptions are defined next to the code that raises them**, not in a shared module. There is no central `exceptions.py` across products.
- **Validation/configuration errors subclass `ValueError`**; I/O/network failures subclass plain `Exception`. This is observed consistently across agent-platform providers and incident-service services.
- **HTTP status codes are explicit and documented per path.** Routes do not rely on implicit defaults; each `raise HTTPException(...)` carries a numeric `status_code` and a human-readable `detail`.
- **Policy denials are always 403 with a structured detail dict** containing `detail`, `action`, and `reason` — verified in `tool_gateway/services/gateway_service.enforce_policy`.
- **Token verification failures are always 401** with a message derived from the normalized `TokenVerificationError.detail`.
- **The platform-gateway secret edge swallows all exceptions** and returns 503; this is the only place in the repo where a broad `except Exception` is used to suppress errors at the HTTP layer.
- **No global exception handlers** are registered in production products; only `samples/acme-admin/app/src/acme_admin/main.py` uses `@app.exception_handler(AdminAuthRequired)` for its sample application.
- **`from None` chaining is used sparingly** to hide internal stack traces in user-facing errors (e.g. `raise AgentRoleError() from None`, `raise HTTPException(...) from None`), preventing implementation details from leaking into API responses.