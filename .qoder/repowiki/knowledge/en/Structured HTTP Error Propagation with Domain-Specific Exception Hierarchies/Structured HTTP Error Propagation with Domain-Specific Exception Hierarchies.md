---
kind: error_handling
name: Structured HTTP Error Propagation with Domain-Specific Exception Hierarchies
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/services/skills_client.py
    - products/agent-platform/src/agent_service/services/incident_client.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/platform-gateway/src/platform_gateway/services/incident_client.py
    - products/platform-gateway/src/platform_gateway/services/agent_client.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/platform-gateway/src/platform_gateway/api/routes/audit.py
---

## Overview

The platform uses a consistent, layered error-handling strategy across all Python services (agent-platform, platform-gateway, audit-service, execution-runtime, identity-broker, incident-service, skills-hub, tool-gateway). Errors are expressed as small domain-specific exception hierarchies in client modules, then mapped to FastAPI `HTTPException` responses at the API boundary. There is no global exception handler; each route or service layer catches and translates exceptions explicitly.

## Framework and primitives

- **FastAPI** is the web framework for every service. Errors surface to callers via `fastapi.HTTPException(status_code=..., detail=...)` raised from routes or service functions.
- **httpx** is used for all inter-service HTTP calls. Transport failures raise `httpx.HTTPError`; non-2xx responses are inspected and translated into either domain exceptions or `HTTPException`.
- No `try/except` blocks catch `BaseException`, and there is no `panic`/`recover` equivalent — Python exceptions propagate up to the request handler.
- Structured logging (`logging.getLogger(__name__).warning(...)`) accompanies error paths but does not replace structured error objects.

## Domain-specific exception hierarchies

Each outbound client defines a small hierarchy of exceptions that encode the *semantic* failure mode rather than raw transport errors:

| Client | Base class | Exceptions | Meaning |
|---|---|---|---|
| `agent_service/services/skills_client.py` | `SkillsClientError` | `SkillsDependencyNotConfigured`, `SkillsServiceUnavailable`, `SkillsClientRejected` | Skills validation dependency missing / upstream 5xx / upstream 4xx |
| `agent_service/services/incident_client.py` | `IncidentClientError` | `IncidentDependencyNotConfigured`, `IncidentServiceUnavailable`, `IncidentNotFound`, `IncidentClientRejected` | Incident document assembly dependency missing / upstream 5xx / unknown id / other 4xx |
| `platform_gateway/services/incident_client.py` | N/A (direct `HTTPException`) | N/A | Same posture: raises `HTTPException(503)` when unconfigured, `HTTPException(502)` on transport/upstream 5xx, passes 4xx through |
| `platform_gateway/services/gateway_service.py` | N/A | Direct `HTTPException` | Auth failures (401), policy denials (403), upstream mapping |
| `agent_service/runtime_kernel.py` | `UnknownModelError(ValueError)` | `UnknownModelError` | Model id absent from credential-gated catalog; fail-closed |

These hierarchies are intentionally small and stable so callers can match on exact types rather than string matching status codes.

## Mapping rules (the "house posture")

A consistent mapping pattern is documented in docstrings and enforced by code:

1. **Dependency not configured** → `HTTPException(503, detail="...service not configured...")`. Used when a downstream service URL/secret is absent (skills-hub, incident-service).
2. **Transport failure or upstream 5xx** → `HTTPException(502, detail="...service unavailable/request failed")`. Wraps `httpx.HTTPError` and upstream 5xx responses.
3. **Upstream 4xx** → passed through verbatim with the upstream message extracted from `{"error": {"message": ...}}` payloads. This lets callers distinguish bad requests from outages.
4. **Domain-specific 4xx** (e.g. `IncidentNotFound`, `NoValidatedTriageReport`, confirmation expired) → mapped to their own semantic status codes (404, 409, 410) with human-readable messages.
5. **Kernel-level failures** (AgentScope provider errors) → caught in `reply_text` and `stream_events`, recorded via `remember_error`, and surfaced as a fallback response via `build_provider_error_message` rather than leaking stack traces.

This mapping is applied uniformly in:
- `agent_service/api/v2/routes.py` — catches `SkillsDependencyNotConfigured` → 503, `SkillsServiceUnavailable` → 502, `SkillsClientRejected` → pass-through status, `IncidentDependencyNotConfigured` → 503, `IncidentServiceUnavailable` → 502, `IncidentNotFound` → 404, `IncidentClientRejected` → pass-through.
- `platform_gateway/services/incident_client.py` — `_raise_upstream` helper centralizes the 4xx-pass-through vs 5xx→502 rule.
- `platform_gateway/api/routes/*.py` — direct `HTTPException` raises for auth (401), policy (403), and upstream proxying.

## Streaming and SSE error handling

Streaming endpoints (`open_chat_stream`, `open_chat_confirm_stream` in `platform_gateway/services/agent_client.py`) check the upstream status eagerly before yielding any frames. If the status is ≥ 400, they read the body to release the connection, close the response/client in a `finally` block, then call `response.raise_for_status()` so the caller sees the real error instead of an empty SSE stream. This prevents corrupting already-open streams with silent failures.

## Kernel-level resilience

The `AgentKernel` in `runtime_kernel.py` encapsulates long-lived state and applies best-effort durability:
- `_restore_state` and `_snapshot_state` wrap persistence in try/except blocks that log warnings and continue — a failed snapshot never breaks a turn.
- `_persist_evidence` similarly degrades gracefully on write failures.
- `reply_text` and `stream_events` catch any unexpected exception, record it via `remember_error`, and return a user-facing fallback message (`build_unconfigured_message` or `build_provider_error_message`) instead of raising.
- `UnknownModelError` enforces a fail-closed model selection policy: unknown model ids are rejected with a clear error rather than silently falling back to a default.

## Conventions observed

- **Never return unvalidated data**: skill-draft generation validates against skills-hub before returning; if validation fails twice (generation + skeleton), it answers 502 rather than returning malformed content.
- **Never leak raw tracebacks**: all clients extract a single-line `detail` message from upstream JSON or use a fixed string; stack traces are logged server-side only.
- **Distinguish configuration vs outage**: 503 means the service is not configured; 502 means it is configured but unreachable. Callers can act differently on these two signals.
- **Use typed exceptions for cross-layer contracts**: client modules define explicit exception classes so callers can `except SpecificError:` rather than inspecting strings.
- **SSE safety**: streaming paths always clean up httpx resources in `finally` blocks and guard against partial reads of error bodies.