---
kind: error_handling
name: Structured Domain Exceptions and HTTP Error Mapping Across Product Services
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/services/skills_client.py
    - products/agent-platform/src/agent_service/services/incident_client.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/audit-service/src/audit_service/services/ingest_auth.py
    - products/execution-runtime/src/execution_runtime/services/execution_protocol.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
    - products/incident-service/src/incident_service/core/config.py
    - products/incident-service/src/incident_service/services/connectors.py
    - products/incident-service/src/incident_service/services/incident_store.py
    - products/incident-service/src/incident_service/services/normalization.py
    - products/incident-service/src/incident_service/services/query_auth.py
    - products/incident-service/src/incident_service/services/triage.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/skills-hub/src/skills_hub/services/query_auth.py
    - products/skills-hub/src/skills_hub/services/skill_store.py
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
---

## Approach

The Luban platform uses a layered error model across its nine Python product services:

1. **Domain exceptions** — per-service custom `Exception` subclasses (sometimes `ValueError`-derived) represent business-level failures.
2. **Client-layer structured hierarchies** — outbound calls to sibling services wrap `httpx.HTTPError` into small, named exception trees that encode the intended HTTP posture (configured / unavailable / rejected).
3. **FastAPI `HTTPException`** — route handlers translate domain/client exceptions into HTTP responses; no global `exception_handler` is registered, so FastAPI's default JSON error response shape is used.
4. **No `try/except` at the API boundary for unhandled exceptions** — only explicitly caught exceptions are mapped; unexpected tracebacks surface via FastAPI's default handler.

There is no shared base error class across products. Each service defines its own hierarchy independently.

## Key Files and Packages

- `products/agent-platform/src/agent_service/providers/base.py` — `ProviderConfigurationError(ValueError)` raised when provider settings are incomplete or invalid.
- `products/agent-platform/src/agent_service/runtime_kernel.py` — `UnknownModelError(ValueError)` for unknown model identifiers.
- `products/agent-platform/src/agent_service/services/execution_protocol.py` — `ProtocolError(ValueError)` for protocol-level mismatches.
- `products/agent-platform/src/agent_service/services/skills_client.py` — `SkillsClientError` base with `SkillsDependencyNotConfigured`, `SkillsServiceUnavailable`, `SkillsClientRejected(status_code, message)`.
- `products/agent-platform/src/agent_service/services/incident_client.py` — `IncidentClientError` base with `IncidentDependencyNotConfigured`, `IncidentServiceUnavailable`, `IncidentNotFound(incident_id)`, `IncidentClientRejected(status_code, message)`.
- `products/agent-platform/src/agent_service/api/v2/routes.py` — central mapping of client exceptions to `HTTPException` status codes.
- `products/platform-gateway/src/platform_gateway/services/policy_engine.py` — `PolicyLoadError(Exception)` for invalid policy bundles.
- `products/platform-gateway/src/platform_gateway/services/token_verifier.py` — `TokenVerificationError(Exception)`.
- `products/audit-service/src/audit_service/services/audit_store.py` — `StoreError(Exception)`.
- `products/audit-service/src/audit_service/services/ingest_auth.py` — `IngestAuthError(Exception)`.
- `products/execution-runtime/src/execution_runtime/services/execution_protocol.py` — `ProtocolError(ValueError)` (mirrors agent-platform's type).
- `products/identity-broker/src/identity_service/services/exchange_service.py` — `ExchangeError(Exception)`.
- `products/incident-service/src/incident_service/core/config.py` — `SettingsError(Exception)`.
- `products/incident-service/src/incident_service/services/connectors.py` — `ConnectorConfigError(Exception)`.
- `products/incident-service/src/incident_service/services/incident_store.py` — `StoreError(Exception)`.
- `products/incident-service/src/incident_service/services/normalization.py` — `NormalizationError(Exception)`.
- `products/incident-service/src/incident_service/services/query_auth.py` — `QueryAuthError(Exception)`.
- `products/incident-service/src/incident_service/services/triage.py` — `TriageError(Exception)`.
- `products/skills-hub/src/skills_hub/core/config.py` — `SettingsError(Exception)`.
- `products/skills-hub/src/skills_hub/services/query_auth.py` — `QueryAuthError(Exception)`.
- `products/skills-hub/src/skills_hub/services/skill_store.py` — `StoreError(Exception)`.
- `products/tool-gateway/src/tool_gateway/services/policy_engine.py` — `PolicyLoadError(Exception)`.
- `products/tool-gateway/src/tool_gateway/services/token_verifier.py` — `TokenVerificationError(Exception)`.

## Architecture and Conventions

### Client-layer exception hierarchy

Outbound clients follow a consistent four-class pattern (see `skills_client.py` and `incident_client.py`):

```
BaseError(Exception)
├── DependencyNotConfigured   → dependency knobs missing → 503
├── ServiceUnavailable        → transport failure or upstream 5xx → 502
├── NotFound                  → known structural 404 case
└── Rejected                → any other upstream 4xx, carries status_code + message
```

The `*Rejected` variant stores `status_code` and `message` as attributes so the caller can re-emit them verbatim. The `_upstream_message` helper extracts `response.json()["error"]["message"]` when present, falling back to a generic string.

### Route-level mapping

`products/agent-platform/src/agent_service/api/v2/routes.py` contains the canonical mapping:

| Exception | HTTP status | Detail |
|---|---:|---|
| `XxxDependencyNotConfigured` | 503 | `str(exc)` |
| `XxxServiceUnavailable` | 502 | `str(exc)` |
| `XxxNotFound` | 404 | structural message |
| `XxxClientRejected` | `exc.status_code` | `exc.message` |
| Validation / auth failures | 400 / 401 / 409 / 410 / 422 | literal strings |

The docstring on `_validate_skill_markdown` documents the invariant: "not configured 503, unreachable or upstream 5xx 502, any other 4xx passed through — an unvalidated draft is never returned."

### Configuration validation

Per-service configuration errors use dedicated `SettingsError` classes (`incident-service/core/config.py`, `skills-hub/core/config.py`) plus domain-specific variants like `ConnectorConfigError`. Provider configuration uses `ProviderConfigurationError(ValueError)` from `providers/base.py`, raised by every concrete provider's `validate()` method.

### Policy bundle loading

`platform-gateway/services/policy_engine.py` raises `PolicyLoadError` for every malformed YAML rule, missing field, invalid outcome, or disallowed approval configuration. The same pattern is mirrored in `tool-gateway/services/policy_engine.py`.

### No centralized error framework

There is no shared base exception class, no global FastAPI `@app.exception_handler`, and no centralized error code registry. Each product owns its types. The closest cross-product convention is the naming pattern `<Domain>Error` and the client-layer `DependencyNotConfigured / ServiceUnavailable / Rejected` trio.

### Structured vs. raw exceptions

Some internal paths raise plain `ValueError` or `RuntimeError` directly (e.g. `runtime_settings.py` validates env vars with `raise ValueError(...)`, `document_prose.py` raises `RuntimeError("prose generation returned an empty reply")`). These are not wrapped before reaching the API layer.

## Conventions and Constraints

- **Observed convention**: Outbound HTTP clients wrap `httpx.HTTPError` into a small named hierarchy rather than propagating raw transport exceptions to callers.
- **Observed convention**: Routes map `DependencyNotConfigured → 503`, `ServiceUnavailable → 502`, `NotFound → 404`, and pass `Rejected.status_code` through unchanged.
- **Observed convention**: Client-layer exceptions carry `status_code` and `message` attributes so the route layer can forward the upstream response without leaking stack traces.
- **Observed convention**: Module-level policy-loading functions raise `PolicyLoadError` with human-readable messages that include the offending rule id and source path.
- **Constraint documented in code comments**: The skill-draft generation path guarantees "an unvalidated draft is never returned" — validation failures degrade to a facts-only skeleton, and a second skeleton validation failure returns 502.
- **Constraint documented in code comments**: Incident and skills client failures are "never a raw traceback" — they are translated to structured HTTP responses.
- **No enforced rule found**: There is no lint rule, shared base class, or CI check enforcing the exception hierarchy pattern; it is maintained by developer convention across products.