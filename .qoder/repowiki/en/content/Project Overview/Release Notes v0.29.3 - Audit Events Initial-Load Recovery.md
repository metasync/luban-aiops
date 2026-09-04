# Release Notes v0.29.3 - Audit Events Initial-Load Recovery

<cite>
**Referenced Files in This Document**
- [2026-09-01-post-live-check-audit-events-initial-load-recovery.md](file://docs/agentic-aiops-platform/release-notes/2026-09-01-post-live-check-audit-events-initial-load-recovery.md)
- [AuditView.tsx](file://products/operator-portal/web-ui/app/src/views/audit/AuditView.tsx)
- [query.py](file://products/audit-service/src/audit_service/api/routes/query.py)
- [summary.py](file://products/audit-service/src/audit_service/api/routes/summary.py)
- [audit_store.py](file://products/audit-service/src/audit_service/services/audit_store.py)
- [gateway_service.py](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py)
- [browser_connector.py](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py)
- [browser_sessions.py](file://products/tool-gateway/src/tool_gateway/tools/browser_sessions.py)
- [credential_sets.py](file://products/tool-gateway/src/tool_gateway/tools/credential_sets.py)
- [test_browser_connector.py](file://products/tool-gateway/tests/test_browser_connector.py)
- [browser-sidecar-network-policy.yaml](file://shared/platform-ops/gitops/runtime-profiles/browser-dev/browser-sidecar-network-policy.yaml)
- [tool-gateway-browser-sidecar.yaml](file://shared/platform-ops/gitops/runtime-profiles/browser-dev/tool-gateway-browser-sidecar.yaml)
</cite>

## Update Summary
**Changes Made**
- Added comprehensive security hardening section for SPEC-049 browser connector
- Updated architecture diagrams to include browser connector components
- Added new sections covering origin re-checking, CDP port pinning, concurrent access fixes, and information disclosure prevention
- Enhanced troubleshooting guide with browser connector security considerations
- Updated conclusion to reflect both audit events recovery and browser connector hardening

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Security Hardening for Browser Connector (SPEC-049)](#security-hardening-for-browser-connector-spec-049)
7. [Dependency Analysis](#dependency-analysis)
8. [Performance Considerations](#performance-considerations)
9. [Troubleshooting Guide](#troubleshooting-guide)
10. [Conclusion](#conclusion)

## Introduction
This release addresses two critical areas: an intermittent initial-load issue in the Operator Portal's Audit Events tab and comprehensive security hardening for the SPEC-049 browser connector. The audit events fix resolves stale-session failures during initial load by adding identity-lifecycle awareness to retry logic. The browser connector hardening implements defense-in-depth security measures including read-tier origin re-checking, CDP port pinning to loopback with NetworkPolicy protection, concurrent access fixes, and information disclosure prevention.

## Project Structure
The changes span multiple components across the platform:

```mermaid
graph TB
subgraph "Operator Portal"
AV["AuditView.tsx"]
end
subgraph "Platform Gateway"
GW["gateway_service.py"]
end
subgraph "Audit Service"
QRY["query.py"]
SUM["summary.py"]
STORE["audit_store.py"]
end
subgraph "Tool Gateway - Browser Connector"
BC["browser_connector.py"]
BS["browser_sessions.py"]
CS["credential_sets.py"]
end
subgraph "Kubernetes Security"
NP["NetworkPolicy"]
SC["Sidecar Config"]
end
AV --> GW
GW --> QRY
GW --> SUM
QRY --> STORE
BC --> BS
BC --> CS
BC --> NP
BC --> SC
```

**Diagram sources**
- [AuditView.tsx:134-199](file://products/operator-portal/web-ui/app/src/views/audit/AuditView.tsx#L134-L199)
- [gateway_service.py:201-261](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L201-L261)
- [browser_connector.py:1-800](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L1-L800)
- [browser-sidecar-network-policy.yaml:1-30](file://shared/platform-ops/gitops/runtime-profiles/browser-dev/browser-sidecar-network-policy.yaml#L1-L30)

**Section sources**
- [2026-09-01-post-live-check-audit-events-initial-load-recovery.md:1-52](file://docs/agentic-aiops-platform/release-notes/2026-09-01-post-live-check-audit-events-initial-load-recovery.md#L1-L52)

## Core Components
- **AuditView (Portal)**: Owns filter state, loading/error/loaded flags, and the initial-load effect that fetches events and summary data. In v0.29.3, the effect is keyed on both role access and the session object to recover from stale-session failures.
- **BrowserConnector**: Implements bounded web-check tool surface with comprehensive security controls including origin allowlist enforcement, flow binding, deviation guards, and credential masking.
- **BrowserSessionPool**: Manages stateful browser sessions with concurrent access protection, TTL-based expiration, and memory-bounded eviction.
- **CredentialSetStore**: Provides secure named credential management with file-based configuration and automatic reload capabilities.

**Section sources**
- [AuditView.tsx:101-199](file://products/operator-portal/web-ui/app/src/views/audit/AuditView.tsx#L101-L199)
- [browser_connector.py:159-260](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L159-L260)
- [browser_sessions.py:120-289](file://products/tool-gateway/src/tool_gateway/tools/browser_sessions.py#L120-L289)
- [credential_sets.py:30-103](file://products/tool-gateway/src/tool_gateway/tools/credential_sets.py#L30-L103)

## Architecture Overview
The portal's Audit view triggers an initial load when the user has the required roles. If the browser boots with a stale expired session, the first request can receive 401 while the shell still appears signed-in due to cached identity fallback. The fix ensures that when the session changes (stale cleared, fresh sign-in, or silent refresh), the effect clears any latched error and retries once if not yet loaded.

```mermaid
sequenceDiagram
participant UI as "AuditView.tsx"
participant GW as "Platform Gateway"
participant ASQ as "Audit Service /events"
participant ASS as "Audit Service /summary"
participant ST as "Audit Store"
UI->>UI : "useEffect(allowed, session)"
alt First load and allowed
UI->>GW : "GET /api/v1/audit/events?limit=50"
GW-->>UI : "401 (stale session)"
UI->>UI : "setError(...), setLoaded=false"
else Session changes (fresh sign-in or silent refresh)
UI->>UI : "clear error, retry once if !loaded"
UI->>GW : "GET /api/v1/audit/events?limit=50"
GW->>ASQ : "authenticate_caller + query"
ASQ->>ST : "store.query(filters, cursor, limit)"
ST-->>ASQ : "page"
ASQ-->>GW : "200 {events,next_cursor}"
GW-->>UI : "200 {events,next_cursor}"
UI->>UI : "setEvents, setCursor, setLoaded=true"
end
```

**Diagram sources**
- [AuditView.tsx:185-199](file://products/operator-portal/web-ui/app/src/views/audit/AuditView.tsx#L185-L199)
- [query.py:35-94](file://products/audit-service/src/audit_service/api/routes/query.py#L35-L94)
- [audit_store.py:386-415](file://products/audit-service/src/audit_service/services/audit_store.py#L386-L415)

## Detailed Component Analysis

### AuditView Initial-Load Effect (v0.29.3)
- **Problem**: The initial-load effect was only keyed on role access; a 401 during the stale-session window left the view in a failed posture until a manual Refresh.
- **Fix**: Key the effect on both role access and the session object. On session transitions, clear any latched error and perform one retry if the view has not yet loaded.
- **Impact**: No API or policy changes; purely client-side lifecycle handling.

```mermaid
flowchart TD
Start(["Mount / Role check"]) --> Allowed{"Has audit:read?"}
Allowed --> |No| End(["Render gate"])
Allowed --> |Yes| CheckState{"loaded or loading?"}
CheckState --> |Yes| End
CheckState --> |No| Load["Call load(false)"]
Load --> Result{"Success?"}
Result --> |Yes| SetLoaded["Set events, cursor, loaded=true"]
Result --> |No| SetError["Set error message"]
SetError --> WaitSession["Wait for session change"]
WaitSession --> Retry{"Retry once if !loaded"}
Retry --> |Yes| Load
Retry --> |No| End
```

**Diagram sources**
- [AuditView.tsx:185-199](file://products/operator-portal/web-ui/app/src/views/audit/AuditView.tsx#L185-L199)

**Section sources**
- [AuditView.tsx:101-199](file://products/operator-portal/web-ui/app/src/views/audit/AuditView.tsx#L101-L199)
- [2026-09-01-post-live-check-audit-events-initial-load-recovery.md:11-41](file://docs/agentic-aiops-platform/release-notes/2026-09-01-post-live-check-audit-events-initial-load-recovery.md#L11-L41)

### Browser Connector Security Hardening
The browser connector implements comprehensive security measures:

#### Read-Tier Origin Re-Checking
Every read operation (snapshot, screenshot) re-validates the current page origin against both the allowlist and bound flow origin before capturing content. This prevents post-load client-side redirects from producing unauthorized captures.

#### CDP Port Pinning and NetworkPolicy Protection
The chromium-headless-shell sidecar binds CDP to loopback (127.0.0.1:9222) and a NetworkPolicy denies all ingress except the gateway HTTP port (8080), providing defense-in-depth protection even if the bind address is accidentally relaxed.

#### Concurrent Access Fixes
The session pool uses a create lock to prevent race conditions where concurrent callers for the same session key could each spawn separate browser contexts, which would orphan the first context and waste resources.

#### Information Disclosure Prevention
- Credential values are masked in snapshots (`value=***`) and screenshots
- Screenshot capture includes credential masking JavaScript injection
- Error messages never expose internal implementation details
- Unknown credential sets return structured errors without revealing available sets

**Section sources**
- [browser_connector.py:394-434](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L394-L434)
- [browser_sidecar_network_policy.yaml:1-30](file://shared/platform-ops/gitops/runtime-profiles/browser-dev/browser-sidecar-network-policy.yaml#L1-L30)
- [browser_sessions.py:144-147](file://products/tool-gateway/src/tool_gateway/tools/browser_sessions.py#L144-L147)
- [credential_sets.py:42-50](file://products/tool-gateway/src/tool_gateway/tools/credential_sets.py#L42-L50)

### Audit Service Query Endpoint
- Validates cursors and enforces service authentication before querying.
- Returns a page of events newest-first with a next_cursor for pagination.

```mermaid
sequenceDiagram
participant GW as "Gateway"
participant R as "query_events()"
participant S as "Store.query()"
GW->>R : "GET /api/v1/audit/events"
R->>R : "authenticate_caller()"
R->>R : "decode_cursor() if provided"
R->>S : "query(filters, cursor, limit)"
S-->>R : "AuditPage{events,next_cursor}"
R-->>GW : "200 JSON"
```

**Diagram sources**
- [query.py:35-94](file://products/audit-service/src/audit_service/api/routes/query.py#L35-L94)
- [audit_store.py:42-63](file://products/audit-service/src/audit_service/services/audit_store.py#L42-L63)

**Section sources**
- [query.py:35-94](file://products/audit-service/src/audit_service/api/routes/query.py#L35-L94)

### Audit Service Summary Endpoint
- Authenticates the caller and returns deterministic envelope-column aggregates.
- Used by the Summary tab; unaffected by the v0.29.3 fix but part of the same view.

**Section sources**
- [summary.py:34-78](file://products/audit-service/src/audit_service/api/routes/summary.py#L34-L78)

### Audit Store Abstraction
- Provides consistent query and summarize behavior across backends.
- In-memory store for tests/dev; PostgreSQL store for production with keyset pagination and bounded eviction.

**Section sources**
- [audit_store.py:42-63](file://products/audit-service/src/audit_service/services/audit_store.py#L42-L63)
- [audit_store.py:386-415](file://products/audit-service/src/audit_service/services/audit_store.py#L386-L415)

## Security Hardening for Browser Connector (SPEC-049)

### Multi-Layered Defense Strategy
The browser connector implements defense-in-depth security through multiple independent layers:

1. **Application-Level Controls**: Origin allowlist validation, flow binding, and deviation guards
2. **Network-Level Controls**: Loopback-only CDP binding and Kubernetes NetworkPolicy
3. **Process-Level Controls**: Sidecar isolation with resource limits and security contexts
4. **Data-Level Controls**: Credential masking and information disclosure prevention

### Origin Allowlist Enforcement
The system enforces strict origin control at multiple points:
- Pre-navigation validation against configured allowlist
- Post-navigation redirect landing verification
- Read-tier capture re-validation before snapshot/screenshot
- Flow origin deviation detection for interactions

### Concurrent Access Protection
The session pool implements robust concurrent access patterns:
- Create locks prevent duplicate context spawning for the same session key
- Double-check patterns ensure thread-safe session creation
- Proper cleanup of orphaned contexts during race conditions
- Memory-bounded session pools with oldest-idle eviction

### Credential Security
Named credential sets provide secure login automation:
- File-based configuration with automatic reload on changes
- Values never appear in logs, results, snapshots, or screenshots
- Masking applied to password fields and filled credential values
- Structured error responses for unknown credential sets

**Section sources**
- [browser_connector.py:10-38](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L10-L38)
- [browser_connector.py:218-222](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L218-L222)
- [browser_sessions.py:144-147](file://products/tool-gateway/src/tool_gateway/tools/browser_sessions.py#L144-L147)
- [credential_sets.py:1-17](file://products/tool-gateway/src/tool_gateway/tools/credential_sets.py#L1-L17)

## Dependency Analysis
- The portal's AuditView depends on:
  - Auth context for roles and session
  - Gateway endpoints for events and summary
- The gateway enforces policy and forwards authenticated requests to the audit service.
- The audit service depends on the configured store backend.
- The browser connector depends on:
  - Playwright library for browser automation
  - Chromium headless shell sidecar via CDP
  - Credential set configuration files
  - Skills hub for flow validation

```mermaid
graph LR
AV["AuditView.tsx"] --> GW["Platform Gateway"]
GW --> AS["Audit Service"]
AS --> STORE["Audit Store"]
BC["BrowserConnector"] --> BS["BrowserSessionPool"]
BC --> CS["CredentialSetStore"]
BS --> NP["NetworkPolicy"]
BS --> SC["Sidecar Config"]
```

**Diagram sources**
- [AuditView.tsx:134-199](file://products/operator-portal/web-ui/app/src/views/audit/AuditView.tsx#L134-L199)
- [gateway_service.py:201-261](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L201-L261)
- [browser_connector.py:159-260](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L159-L260)
- [browser-sidecar-network-policy.yaml:1-30](file://shared/platform-ops/gitops/runtime-profiles/browser-dev/browser-sidecar-network-policy.yaml#L1-L30)

**Section sources**
- [gateway_service.py:201-261](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L201-L261)

## Performance Considerations
- The audit events fix avoids repeated network calls by retrying only once on session transitions and only when the view has not yet loaded.
- The audit service uses keyset pagination and bounded limits to keep responses small and efficient.
- Summaries are computed over envelope columns only, avoiding payload excavation.
- The browser connector implements efficient session pooling with TTL-based expiration and memory-bounded eviction.
- Concurrent access patterns minimize resource contention while preventing race conditions.
- Credential set reloading uses file modification time checks to avoid unnecessary file reads.

## Troubleshooting Guide
- **Symptom**: Audit Events tab shows "No audit events match these filters" on first load, but Summary counts show events.
- **Root cause**: Initial auto-load fails with 401 during a stale-session window; the effect does not retry automatically.
- **Resolution**: After signing in again or allowing a silent refresh, the view will automatically retry once and populate the table.
- **Verification**:
  - Confirm the gateway logs show 401 followed by successful requests after session refresh.
  - Ensure the effect dependency includes the session object so it re-runs on identity lifecycle changes.
  - Confirm no manual Refresh is required post-sign-in.

### Browser Connector Troubleshooting
- **Symptom**: Browser tools unavailable or returning BROWSER_NOT_READY errors.
- **Root cause**: Browser sidecar not reachable or CDP endpoint misconfigured.
- **Resolution**: Verify `GATEWAY_BROWSER_CDP_ENDPOINT` points to reachable loopback:9222 and sidecar container is running.
- **Symptom**: Navigation denied with BROWSER_ORIGIN_NOT_ALLOWED.
- **Root cause**: Target origin not in configured allowlist.
- **Resolution**: Add target origin to `GATEWAY_BROWSER_ALLOW_ORIGINS` configuration.
- **Symptom**: Interactions denied with BROWSER_FLOW_ORIGIN_DEVIATED.
- **Root cause**: Current page origin differs from bound flow origin.
- **Resolution**: Navigate back to the flow's target origin before interacting.

**Section sources**
- [2026-09-01-post-live-check-audit-events-initial-load-recovery.md:11-41](file://docs/agentic-aiops-platform/release-notes/2026-09-01-post-live-check-audit-events-initial-load-recovery.md#L11-L41)
- [AuditView.tsx:185-199](file://products/operator-portal/web-ui/app/src/views/audit/AuditView.tsx#L185-L199)
- [test_browser_connector.py:440-483](file://products/tool-gateway/tests/test_browser_connector.py#L440-L483)

## Conclusion
Release v0.29.3 delivers two significant improvements: resolution of initial-load recovery issues in the Audit Events tab through identity-lifecycle-aware retry logic, and comprehensive security hardening for the SPEC-049 browser connector. The audit events fix is minimal, targeted, and validated with regression testing, preserving all existing server behaviors while improving resilience against transient authentication states. The browser connector hardening implements defense-in-depth security through multi-layered origin validation, CDP port pinning with NetworkPolicy protection, concurrent access safeguards, and robust information disclosure prevention. Together, these changes enhance both user experience and security posture across the platform.