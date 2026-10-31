---
kind: error_handling
name: Error Handling — Structured Domain Exceptions, HTTPException Mapping, and Upstream Posture Normalization
category: error_handling
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/app.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/services/delegated_identity.py
    - products/agent-platform/src/agent_service/services/execution_worker_client.py
    - products/agent-platform/src/agent_service/services/execution_protocol.py
---

## Overview

The Luban AIOps platform is a multi-service Python/FastAPI monorepo. Error handling follows three consistent layers:

1. **Domain exceptions** — per-product `Exception` subclasses raised inside services to represent business failures (configuration errors, transport failures, protocol violations).
2. **HTTP boundary mapping** — route handlers translate domain exceptions into `fastapi.HTTPException(status_code=..., detail=...)`, which FastAPI serializes as JSON `{"detail": ...}` responses.
3. **Upstream posture normalization** — the platform-gateway and agent-service proxy layers catch `httpx` exceptions and normalize upstream status codes so callers never see raw 500s from downstream outages.

There are no global `@app.exception_handler` registrations anywhere in the codebase; error presentation relies entirely on FastAPI's built-in `HTTPException` serializer and on explicit `raise HTTPException(...)` at every API boundary.

## Key Files and Packages

- `products/platform-gateway/src/platform_gateway/app.py` — single HTTP middleware that wraps every request, logs structured events, and for the secret authorization edge catches all exceptions to return either a redirect or a `JSONResponse({"detail": "Target authorization unavailable"}, 503)` instead of leaking stack traces.
- `products/platform-gateway/src/platform_gateway/services/gateway_service.py` — canonical upstream-proxy pattern: `except httpx.HTTPStatusError` → pass through 4xx with `_upstream_detail(exc, ...)`; map 5xx + transport `httpx.HTTPError` → `HTTPException(502, ...)`. Also defines `PolicyLoadError` and uses `TokenVerificationError`.
- `products/platform-gateway/src/platform_gateway/services/token_verifier.py` — defines `TokenVerificationError(Exception)` used by JWT verification.
- `products/platform-gateway/src/platform_gateway/services/policy_engine.py` — defines `PolicyLoadError(Exception)`, `ApprovalSpec`, `PolicyRule`, `PolicyDecision` dataclasses; policy denials raise `HTTPException(403, {"detail": "action denied by policy", "action": ..., "reason": ...})` via `enforce_policy()`.
- `products/agent-platform/src/agent_service/api/v2/routes.py` — the main v2 HTTP surface; raises `HTTPException` directly for auth/validation errors and maps client-layer exceptions (`SkillsDependencyNotConfigured`, `SkillsServiceUnavailable`, `SkillsClientRejected`, `IncidentDependencyNotConfigured`, `IncidentServiceUnavailable`, `IncidentNotFound`, `NoValidatedTriageReport`) to 503/502/404/409/422.
- `products/agent-platform/src/agent_service/providers/base.py` — defines `ProviderConfigurationError(ValueError)` used uniformly across OpenAI/Dashscope/DeepSeek/Luban providers.
- `products/agent-platform/src/agent_service/services/delegated_identity.py` — defines `DelegatedIdentityError(ValueError)` for identity-flow failures.
- `products/agent-platform/src/agent_service/services/execution_worker_client.py` — defines `WorkerHandoffError(Exception)` (with `.reason`) and `WorkerHandoffTimeout(Exception)`; the `handoff()` function documents the contract: "Raises `WorkerHandoffError` ... or `WorkerHandoffTimeout`; never returns an error dict."
- `products/agent-platform/src/agent_service/services/execution_protocol.py` — defines `ProtocolError(ValueError)` used for signed-envelope validation failures.
- Per-product service packages follow the same shape: `audit_store.StoreError`, `ingest_auth.IngestAuthError`, `exchange_service.ExchangeError`, `incident_store.StoreError`, `normalization.NormalizationError`, `query_auth.QueryAuthError`, `triage.TriageError`, `connector.ConnectorConfigError`, `config.SettingsError`, `skill_store.StoreError`, `skills_hub.query_auth.QueryAuthError`.

## Architecture and Conventions

### Domain exceptions carry semantic meaning, not messages alone

Domain exceptions are defined close to the layer they belong to and subclass either `Exception` or `ValueError`:

- Configuration / setup failures → `*ConfigurationError(ValueError)` (e.g. `ProviderConfigurationError`, `ConnectorConfigError`, `SettingsError`).
- Client transport failures → `*ClientError(Exception)` (e.g. `SkillsClientError`, `IncidentClientError`, `WorkerHandoffError`).
- Protocol / wire-format failures → `ProtocolError(ValueError)`.
- Store / persistence failures → `StoreError(Exception)`.

Some exceptions carry extra fields beyond the message: `WorkerHandoffError.reason` encodes a machine-readable rejection reason separate from the human-facing message, and `PolicyDecision` is a frozen dataclass carrying `decision`, `matched_rule_ids`, `reason`, `action`, `subject`, and optional `approval`.

### HTTP boundaries always convert to `HTTPException`

Every FastAPI route handler converts domain exceptions into `HTTPException` before returning. The agent-service v2 routes use this pattern consistently:

```python
except SkillsDependencyNotConfigured as exc:
    raise HTTPException(status_code=503, detail=str(exc)) from None
except SkillsServiceUnavailable as exc:
    raise HTTPException(status_code=502, detail=str(exc)) from None
except SkillsClientRejected as exc:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
```

This gives callers a stable posture vocabulary: 503 = dependency not configured, 502 = upstream unreachable, 4xx = caller-side problem.

### Upstream posture normalization in the gateway

`gateway_service.py` centralizes the rule: upstream 4xx passes through unchanged (preserving anti-enumeration 404s and operator-actionable 409s), while upstream 5xx and transport failures become `HTTPException(502, ...)`. The helper `_upstream_detail(exc, fallback)` tries to extract the upstream response's `detail` field so the portal can render the original refusal verbatim when available.

The identity leg (`_identity_leg`) has a slightly different rule: 4xx passes through with a normalized detail string, and any 5xx becomes `HTTPException(502, "identity service unavailable — retry the sign-in")` so the sign-in surface never surfaces a raw 500 during rollout races.

### No global exception handlers

A search for `@app.exception_handler`, `@router.exception_handler`, and `exception_handlers=` across the entire repository returns zero matches. Error serialization is delegated to FastAPI's default `HTTPException` handler. The only place that catches `Exception` broadly is the platform-gateway's HTTP middleware, which rewrites unhandled exceptions on the secret authorization edge to a safe 503 JSON body rather than letting them propagate to FastAPI's default 500 handler.

### Structured logging accompanies errors

Errors are logged with structured `extra` dicts keyed by `request_id`, `service`, `method`, `path`, `status_code`, `duration_ms`, plus domain-specific fields like `session_id`, `user_id`, `action`, `decision`, `matched_rule_ids`. The gateway's `log_event` call in the HTTP middleware records every request/response pair, including failed ones, making error correlation possible end-to-end.

### Fail-closed handoff semantics

`WorkerHandoffError` and `WorkerHandoffTimeout` are deliberately separate: a timeout does not mean the worker did not act, so the caller must treat them differently (resume the stream and accept the durable receipt). Transport failures log only `exc.__class__.__name__` explicitly because transport messages can echo URLs or payloads and must never leak credentials.

## Conventions and Constraints

- **Observed convention**: Domain-layer functions raise typed `Exception`/`ValueError` subclasses; FastAPI route handlers convert them to `HTTPException(status_code, detail)`.
- **Observed convention**: Gateway proxy functions catch `httpx.HTTPStatusError` and branch on `400 <= status < 500` vs `>= 500`, passing 4xx through and collapsing 5xx to 502.
- **Observed convention**: Dependency-not-configured cases answer 503; unreachable/upstream failures answer 502; caller validation errors answer 4xx (400/401/404/409/422).
- **Observed convention**: Policy denials go through `enforce_policy()`, which emits an audit event and raises `HTTPException(403, {"detail": "action denied by policy", "action": ..., "reason": ...})`.
- **Observed constraint**: The secret authorization edge of the platform-gateway middleware catches all exceptions and returns either a redirect or `JSONResponse({"detail": "Target authorization unavailable"}, 503)` — unhandled exceptions on that path never reach FastAPI's default error handler.
- **Observed constraint**: The execution handoff contract documented in `execution_worker_client.handoff` states it "never returns an error dict" — errors leave the boundary exclusively as `WorkerHandoffError` or `WorkerHandoffTimeout`.
- **Observed constraint**: Skill-draft generation paths enforce that an unvalidated draft is never returned; second validation failure degrades to a facts-only skeleton, and if even that fails the route answers 502.
- **Observed constraint**: Token verification failures raise `TokenVerificationError` with a `detail` string that distinguishes "token expired" from other invalid-token cases, and the gateway records this distinction as a metric label.
- **Not enforced by tooling**: There is no linter rule, CI check, or framework-level enforcement visible in the repository that forces new code to follow these conventions; they are maintained by code review and the consistency of existing patterns.