# Execution Runtime

<cite>
**Referenced Files in This Document**
- [app.py](file://products/execution-runtime/src/execution_runtime/app.py)
- [main.py](file://products/execution-runtime/src/execution_runtime/main.py)
- [router.py](file://products/execution-runtime/src/execution_runtime/api/router.py)
- [handoff.py](file://products/execution-runtime/src/execution_runtime/api/routes/handoff.py)
- [executor.py](file://products/execution-runtime/src/execution_runtime/services/executor.py)
- [single_flight.py](file://products/execution-runtime/src/execution_runtime/services/single_flight.py)
- [execution_signing.py](file://products/execution-runtime/src/execution_runtime/services/execution_signing.py)
- [execution_records.py](file://products/execution-runtime/src/execution_runtime/services/execution_records.py)
- [audit_emitter.py](file://products/execution-runtime/src/execution_runtime/services/audit_emitter.py)
- [config.py](file://products/execution-runtime/src/execution_runtime/core/config.py)
- [execution_ledger.py](file://products/execution-runtime/src/execution_runtime/services/execution_ledger.py)
- [execution_protocol.py](file://products/execution-runtime/src/execution_runtime/services/execution_protocol.py)
- [execution_io.py](file://products/execution-runtime/src/execution_runtime/services/execution_io.py)
- [execution_cutover.py](file://products/execution-runtime/src/execution_runtime/services/execution_cutover.py)
- [SPEC-038-isolated-execution-worker/spec.md](file://docs/specs/SPEC-038-isolated-execution-worker/spec.md)
- [SPEC-037-signed-execution-requests/spec.md](file://docs/specs/SPEC-037-signed-execution-requests/spec.md)
- [SPEC-063-crash-safe-execution/spec.md](file://docs/specs/SPEC-063-crash-safe-execution/spec.md)
</cite>

## Update Summary
**Changes Made**
- Updated core architecture to reflect SPEC-063 crash-safe execution infrastructure with durable Postgres-backed dispatch claims and at-most-one worker-to-gateway guarantees.
- Added new sections for Execution Ledger, Run Guard mechanism, v3 signed contracts, and enhanced handoff protocol with fail-closed persistence.
- Updated executor component to handle GatewayUncertain exceptions and typed outcomes handling.
- Enhanced troubleshooting guide with new failure scenarios and recovery procedures.
- Updated security considerations to cover durable claim protection and cutover safety.

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
10. [Appendices](#appendices)

## Introduction
The Execution Runtime is an isolated, single-replica worker that executes approved mutating actions safely and audibly. It receives signed execution envelopes from the agent platform over a secure internal handoff endpoint, verifies signatures and argument digests, runs exactly one tool invocation per request through the tool gateway using the confirmer's delegated token, records signed receipts, and emits audit events. 

**Updated** The service now provides crash-safe execution through SPEC-063: durable Postgres-backed dispatch claims ensure at-most-one worker-to-gateway dispatch guarantees even after process crashes or database failures. A run guard mechanism prevents duplicate mutations, while v3 signed contracts with HMAC-over-canonical-JSON signatures provide tamper-evident execution chains. The enhanced handoff protocol includes fail-closed persistence, typed outcomes handling, and comprehensive failure testing framework.

Key design goals:
- Isolation: separate process boundary for mutating workloads.
- Security: authenticated handoff, envelope signature verification, argument digest checks.
- Idempotency: durable single-flight registry keyed by execution_id with burn-on-claim semantics.
- Auditability: durable receipt storage and fire-and-forget audit emission.
- Resilience: timeouts, transport error handling, best-effort durability for records.
- Crash Safety: durable dispatch claims prevent duplicate mutations across process restarts.

**Section sources**
- [SPEC-038-isolated-execution-worker/spec.md:11-25](file://docs/specs/SPEC-038-isolated-execution-worker/spec.md#L11-L25)
- [SPEC-037-signed-execution-requests/spec.md:11-22](file://docs/specs/SPEC-037-signed-execution-requests/spec.md#L11-L22)
- [SPEC-063-crash-safe-execution/spec.md:29-45](file://docs/specs/SPEC-063-crash-safe-execution/spec.md#L29-L45)

## Project Structure
The Execution Runtime product is organized into FastAPI application layers, services, and core modules:
- Application entrypoints: app factory, lifespan, middleware, router wiring.
- API routes: health and handoff endpoints with v3 protocol support.
- Services: executor (tool-gateway call), single-flight registry, signing utilities, execution record store, audit emitter, execution ledger, protocol validation, I/O bounds, and cutover management.
- Core: frozen settings loaded from environment, metrics, observability, telemetry, runtime settings.

```mermaid
graph TB
A["FastAPI App<br/>lifespan + middleware"] --> B["Router<br/>health + handoff"]
B --> C["Handoff Route<br/>v3 auth + verify + ledger claim"]
C --> D["Executor<br/>tool-gateway call with uncertainty"]
C --> E["ExecutionLedger<br/>durable claims + observations"]
C --> F["SingleFlightRegistry<br/>in-process idempotency"]
C --> G["ExecutionRecordStore<br/>receipt close"]
C --> H["Audit Emitter<br/>fire-and-forget"]
A --> I["Config<br/>frozen settings"]
A --> J["Metrics + Telemetry"]
E --> K["Postgres<br/>dispatch claims + observations"]
```

**Diagram sources**
- [app.py:19-67](file://products/execution-runtime/src/execution_runtime/app.py#L19-L67)
- [router.py:1-8](file://products/execution-runtime/src/execution_runtime/api/router.py#L1-L8)
- [handoff.py:144-235](file://products/execution-runtime/src/execution_runtime/api/routes/handoff.py#L144-L235)
- [executor.py:17-71](file://products/execution-runtime/src/execution_runtime/services/executor.py#L17-L71)
- [execution_ledger.py:77-491](file://products/execution-runtime/src/execution_runtime/services/execution_ledger.py#L77-L491)
- [single_flight.py:34-107](file://products/execution-runtime/src/execution_runtime/services/single_flight.py#L34-L107)
- [execution_records.py:310-333](file://products/execution-runtime/src/execution_runtime/services/execution_records.py#L310-L333)
- [audit_emitter.py:30-99](file://products/execution-runtime/src/execution_runtime/services/audit_emitter.py#L30-L99)
- [config.py:20-84](file://products/execution-runtime/src/execution_runtime/core/config.py#L20-L84)

**Section sources**
- [app.py:19-67](file://products/execution-runtime/src/execution_runtime/app.py#L19-L67)
- [main.py:6-9](file://products/execution-runtime/src/execution_runtime/main.py#L6-L9)
- [router.py:1-8](file://products/execution-runtime/src/execution_runtime/api/router.py#L1-L8)

## Core Components
- Handoff route: authenticates caller via static bearer token, validates v3 envelope shape, verifies HMAC signature and argument digest, enforces durable single-flight idempotency through execution ledger, then executes and closes records.
- Executor: performs a single HTTP POST to the tool gateway with the forwarded delegated token; maps timeouts and transport errors to structured `GatewayUncertain` results; never logs or persists tokens.
- Execution Ledger: durable Postgres-backed dispatch authority with burn-on-claim semantics; manages dispatch claims, observations, and recovery state; ensures at-most-one dispatch guarantee.
- Single-flight registry: in-process async registry joining concurrent duplicates on one future; bounded completion cache with retention and cap; fails closed on misconfiguration.
- Signing utilities: canonical JSON, SHA-256 digest, HMAC-SHA256 signing and constant-time verification; builds signed receipts with outcome digests; supports v3 protocol.
- Execution record store: memory and Postgres backends; first-write-wins closing; late arrivals return existing receipt; retention sweep; best-effort durability.
- Audit emitter: fire-and-forget delivery to audit service; non-blocking thread; failures logged and counted without impacting execution path.
- Configuration: frozen settings with startup validation; supports memory/postgres backend selection; requires positive timeout and valid backend URL when postgres selected.

**Section sources**
- [handoff.py:144-235](file://products/execution-runtime/src/execution_runtime/api/routes/handoff.py#L144-L235)
- [executor.py:17-71](file://products/execution-runtime/src/execution_runtime/services/executor.py#L17-L71)
- [execution_ledger.py:77-491](file://products/execution-runtime/src/execution_runtime/services/execution_ledger.py#L77-L491)
- [single_flight.py:34-107](file://products/execution-runtime/src/execution_runtime/services/single_flight.py#L34-L107)
- [execution_signing.py:40-93](file://products/execution-runtime/src/execution_runtime/services/execution_signing.py#L40-L93)
- [execution_records.py:78-119](file://products/execution-runtime/src/execution_runtime/services/execution_records.py#L78-L119)
- [execution_records.py:196-303](file://products/execution-runtime/src/execution_runtime/services/execution_records.py#L196-L303)
- [audit_emitter.py:30-99](file://products/execution-runtime/src/execution_runtime/services/audit_emitter.py#L30-L99)
- [config.py:20-84](file://products/execution-runtime/src/execution_runtime/core/config.py#L20-L84)

## Architecture Overview
The end-to-end flow starts with the agent platform sending a v3 signed execution envelope plus parked arguments and a delegated token to the worker's handoff endpoint. The worker authenticates the caller, verifies the envelope signature and argument digest, atomically consumes a durable dispatch claim through the execution ledger, invokes the tool gateway, signs and stores the receipt, emits audit events, and returns the result and receipt to the caller.

```mermaid
sequenceDiagram
participant Client as "Agent Platform"
participant Worker as "Execution Runtime"
participant Ledger as "ExecutionLedger"
participant Registry as "SingleFlightRegistry"
participant Executor as "Executor"
participant Gateway as "Tool Gateway"
participant Store as "ExecutionRecordStore"
participant Audit as "Audit Service"
Client->>Worker : POST /api/v1/executions/handoff (v3)
Worker->>Worker : Verify handoff token + v3 envelope
Worker->>Ledger : claim(envelope, request_id)
alt First owner
Ledger-->>Worker : DispatchPermit + observation
Worker->>Registry : run(execution_id, execute_and_close)
Registry-->>Worker : (outcome, owner=True)
Worker->>Executor : execute_tool(tool_name, arguments, delegated_token)
Executor->>Gateway : POST tools/invoke (Bearer token)
Gateway-->>Executor : result dict or GatewayUncertain
Executor-->>Worker : result dict
Worker->>Ledger : finish(conn, envelope, fact)
Worker->>Store : close_execution(record, receipt, digest_match)
Store-->>Worker : existing_receipt?
Worker->>Audit : emit execution_completed
Worker-->>Client : {receipt, result}
else Replay/join
Registry-->>Worker : (cached_outcome, owner=False)
Worker-->>Client : {receipt, result}
end
```

**Diagram sources**
- [handoff.py:144-235](file://products/execution-runtime/src/execution_runtime/api/routes/handoff.py#L144-L235)
- [executor.py:17-71](file://products/execution-runtime/src/execution_runtime/services/executor.py#L17-L71)
- [execution_ledger.py:158-221](file://products/execution-runtime/src/execution_runtime/services/execution_ledger.py#L158-L221)
- [single_flight.py:42-84](file://products/execution-runtime/src/execution_runtime/services/single_flight.py#L42-L84)
- [execution_records.py:239-293](file://products/execution-runtime/src/execution_runtime/services/execution_records.py#L239-L293)
- [audit_emitter.py:68-99](file://products/execution-runtime/src/execution_runtime/services/audit_emitter.py#L68-L99)

## Detailed Component Analysis

### Handoff Endpoint: Authentication, Verification, and Durable Claim Management
The handoff endpoint is the only execution surface. It:
- Extracts and compares the bearer token against the configured handoff secret using constant-time comparison.
- Parses the body into envelope, arguments, and optional delegated token; rejects malformed payloads.
- Validates required envelope fields and enforces ASCII-only signatures before verification.
- Verifies the envelope signature using HMAC-SHA256 and recomputes the argument digest to ensure integrity.
- Atomically consumes a durable dispatch claim through the execution ledger; concurrent duplicates await the same future.
- Executes the action and closes the execution record; emits audit events; returns receipt and result.

**Updated** The endpoint now uses v3 protocol validation, durable claim management, and enhanced error handling with structured refusal responses.

```mermaid
flowchart TD
Start(["Request Received"]) --> Auth["Extract Bearer Token<br/>Compare with Configured Secret"]
Auth --> |Invalid| RejectAuth["Reject 401<br/>Emit execution_rejected"]
Auth --> Parse["Parse Body<br/>Envelope + Arguments + Delegated Token"]
Parse --> |Invalid| RejectBad["Reject 400<br/>Emit execution_rejected"]
Parse --> Validate["Validate Required Fields<br/>Signature ASCII Check"]
Validate --> |Missing/Invalid| RejectSig["Reject 400<br/>Emit execution_rejected"]
Validate --> Verify["Verify Envelope Signature<br/>Recompute Args Digest"]
Verify --> |Mismatch| RejectDigest["Reject 400<br/>Emit execution_rejected"]
Verify --> Claim["ExecutionLedger.claim()"]
Claim --> |No Permit| Refuse["Refuse with reason"]
Claim --> |Permit| SingleFlight["SingleFlightRegistry.run(execution_id)"]
SingleFlight --> Execute["Execute Tool Invocation"]
Execute --> Close["Close Execution Record<br/>Sign Receipt"]
Close --> Emit["Emit Audit Events"]
Emit --> Return["Return {receipt, result}"]
```

**Diagram sources**
- [handoff.py:144-235](file://products/execution-runtime/src/execution_runtime/api/routes/handoff.py#L144-L235)
- [execution_protocol.py:81-92](file://products/execution-runtime/src/execution_runtime/services/execution_protocol.py#L81-L92)
- [execution_ledger.py:158-221](file://products/execution-runtime/src/execution_runtime/services/execution_ledger.py#L158-L221)
- [single_flight.py:42-84](file://products/execution-runtime/src/execution_runtime/services/single_flight.py#L42-L84)

**Section sources**
- [handoff.py:144-235](file://products/execution-runtime/src/execution_runtime/api/routes/handoff.py#L144-L235)

### Executor: Safe Tool Invocation Through the Tool Gateway
The executor performs a single HTTP POST to the tool gateway with the forwarded delegated token as bearer. It:
- Validates configuration presence (gateway URL and delegated token).
- Builds payload including tool name, parameters, request correlation, optional session_id, and approval_kind provenance.
- Uses httpx with a configured timeout; maps TimeoutException and HTTPError to structured `GatewayUncertain` results.
- Parses response JSON; on failure, logs warning and returns structured error.
- Maps gateway result status to receipt vocabulary: success → succeeded, TIMEOUT → timeout, other → failed.

**Updated** The executor now raises `GatewayUncertain` exceptions for transport errors and validates response schema strictly.

```mermaid
flowchart TD
Entry(["execute_tool(settings, tool_name, arguments, delegated_token, request_id, ...)"]) --> CheckCfg{"Gateway URL & Token Present?"}
CheckCfg --> |No| ErrCfg["Raise GatewayUncertain<br/>NO_GATEWAY / NO_CREDENTIAL"]
CheckCfg --> Build["Build Payload<br/>tool_name, parameters, request_id,<br/>session_id?, approval_kind?"]
Build --> Call["POST /api/v2/tools/invoke<br/>Authorization: Bearer <token>"]
Call --> Resp{"Response OK?"}
Resp --> |Timeout| ErrTimeout["Raise GatewayUncertain<br/>transport_error"]
Resp --> |Transport Error| ErrTransport["Raise GatewayUncertain<br/>transport_error"]
Resp --> |JSON Parse Fail| ErrBad["Raise GatewayUncertain<br/>response_invalid"]
Resp --> |Success| Map["map_result_status(result)"]
Map --> Exit(["Return result dict"])
```

**Diagram sources**
- [executor.py:17-71](file://products/execution-runtime/src/execution_runtime/services/executor.py#L17-L71)

**Section sources**
- [executor.py:17-71](file://products/execution-runtime/src/execution_runtime/services/executor.py#L17-L71)

### Execution Ledger: Durable Dispatch Authority and Run Guard
The execution ledger provides crash-safe dispatch authority through durable Postgres-backed claims:
- Burn-on-claim semantics: atomically commits unique dispatch claims before gateway requests can be sent.
- Identity conflict detection: prevents reminted execution IDs from rerunning approved calls.
- Observation tracking: immutable, attributed observations rather than letting caller timeouts permanently close results.
- Recovery projection: distinguishes between not_dispatched, dispatch_claimed, outcome_unknown, and result_recorded states.
- Retention management: bounded cleanup of expired claims and observations after 30 days post-expiry.
- Health monitoring: operational gauges for unresolved claims and admission availability.

**New Section** This component implements SPEC-063 requirements for durable single-use dispatch authority with no leases, takeover, or memory fallback.

```mermaid
classDiagram
class ExecutionLedger {
+connection() contextmanager
+health() dict
+metrics_snapshot() dict
+claim(envelope, current_request_id) ClaimDecision
+open_send(permit, envelope) Connection
+finish(conn, envelope, fact) str
+stop(envelope, fact, reason) str
+append(execution_id, fact, source) str
+retention_sweep(batch) dict
+lookup(execution_id, replay) dict
}
class DispatchPermit {
+execution_id str
+run_id str
+request_digest str
+owner_id str
+consume(envelope) void
}
class ClaimDecision {
+permit DispatchPermit
+reason str
+observation dict
}
ExecutionLedger --> DispatchPermit : "manages"
ExecutionLedger --> ClaimDecision : "returns"
```

**Diagram sources**
- [execution_ledger.py:44-75](file://products/execution-runtime/src/execution_runtime/services/execution_ledger.py#L44-L75)
- [execution_ledger.py:77-491](file://products/execution-runtime/src/execution_runtime/services/execution_ledger.py#L77-L491)

**Section sources**
- [execution_ledger.py:77-491](file://products/execution-runtime/src/execution_runtime/services/execution_ledger.py#L77-L491)

### Protocol Validation: v3 Signed Contracts and Typed Outcomes
Protocol validation provides closed, local-only v3 execution contracts:
- Schema validation: validates execution-request, execution-receipt, execution-observation, execution-recovery, execution-handoff-response, and tool-result schemas.
- Metadata limits: enforces 8KB metadata size limits to prevent abuse.
- Request validation: validates protocol version, signature, lifetime bounds (900 seconds max), and timestamp formats.
- Observation validation: validates signed observations with identity conflict detection and receipt verification.
- Timestamp handling: ISO format conversion with timezone awareness.

**New Section** This component implements the v3 protocol specification with strict contract enforcement.

**Section sources**
- [execution_protocol.py:1-123](file://products/execution-runtime/src/execution_runtime/services/execution_protocol.py#L1-L123)

### I/O Bounds: Database Wait Management and Ownership Preservation
I/O bounds provide bound database wire waits and retain ownership across coroutine cancellation:
- Database budget context manager: tracks remaining time budgets across nested operations.
- BoundedConnection: wraps psycopg connections with deadline enforcement to prevent unbounded waits.
- Owned thread execution: shields tasks from cancellation while preserving resource disposal semantics.

**New Section** This component ensures database operations respect time budgets and don't leak resources during cancellation.

**Section sources**
- [execution_io.py:1-81](file://products/execution-runtime/src/execution_runtime/services/execution_io.py#L1-L81)

### Single-Flight Registry: Idempotency and Deduplication
The single-flight registry ensures each execution_id runs at most once:
- Creates a future for the first caller; subsequent callers await the same future.
- On completion, caches outcome and timestamp; evicts completed entries after retention window.
- Caps completed entries to prevent unbounded growth under replay storms.
- Drops failed flights so poison outcomes do not pin keys indefinitely.

```mermaid
classDiagram
class SingleFlightRegistry {
+int retention_seconds
-dict _flights
-asyncio.Lock _lock
+run(key, factory) tuple
-_evict(now) void
}
class _Flight {
+asyncio.Future future
+float completed_at
+Any outcome
}
SingleFlightRegistry --> _Flight : "manages"
```

**Diagram sources**
- [single_flight.py:27-107](file://products/execution-runtime/src/execution_runtime/services/single_flight.py#L27-L107)

**Section sources**
- [single_flight.py:34-107](file://products/execution-runtime/src/execution_runtime/services/single_flight.py#L34-L107)

### Signing Utilities: Canonicalization, Digests, and Receipts
Signing utilities implement the shared contract for execution requests and receipts:
- Canonical JSON: sorted keys, compact separators.
- Canonical digest: SHA-256 hex of canonical JSON.
- Sign envelope: HMAC-SHA256 over canonical envelope excluding signature field.
- Verify envelope: constant-time comparison of expected vs provided signature.
- Build receipt: includes execution_id, status, outcome_digest, request_id, completed_at, and signature.

```mermaid
flowchart TD
Input["Envelope + Key"] --> Canonical["canonical_json(obj)"]
Canonical --> Digest["canonical_digest(obj)"]
Digest --> Sign["sign_envelope(envelope, key)"]
Sign --> Verify["verify_envelope(envelope, signature, key)"]
Verify --> Result{"Valid?"}
Result --> |Yes| Receipt["build_receipt(request, status, outcome, request_id, key)"]
Result --> |No| Reject["Reject execution"]
```

**Diagram sources**
- [execution_signing.py:40-93](file://products/execution-runtime/src/execution_runtime/services/execution_signing.py#L40-L93)

**Section sources**
- [execution_signing.py:40-93](file://products/execution-runtime/src/execution_runtime/services/execution_signing.py#L40-L93)

### Execution Records: Best-Effort Durable Closing
The record store closes execution rows opened by the agent platform:
- In-memory backend: simple dict keyed by confirm_id + call_id; first write wins; late arrival returns existing receipt.
- Postgres backend: shares sessions database table; insert-if-absent request row; update only if status='requested'; late arrival loads existing receipt; retention sweep bounded per run.
- Factory selects backend based on settings; falls back to memory if Postgres unavailable.

```mermaid
flowchart TD
Start(["close_execution(record, receipt, digest_match)"]) --> Backend{"Backend Type"}
Backend --> |Memory| Mem["Insert or Update Row<br/>First Write Wins"]
Backend --> |Postgres| Pg["INSERT ... ON CONFLICT DO NOTHING<br/>UPDATE WHERE status='requested'"]
Mem --> Late{"Row Already Closed?"}
Pg --> Late
Late --> |Yes| ReturnExisting["Return Existing Receipt"]
Late --> |No| Sweep["Retention Sweep (Bounded)"]
Sweep --> End(["Done"])
```

**Diagram sources**
- [execution_records.py:78-119](file://products/execution-runtime/src/execution_runtime/services/execution_records.py#L78-L119)
- [execution_records.py:196-303](file://products/execution-runtime/src/execution_runtime/services/execution_records.py#L196-L303)
- [execution_records.py:310-333](file://products/execution-runtime/src/execution_runtime/services/execution_records.py#L310-L333)

**Section sources**
- [execution_records.py:78-119](file://products/execution-runtime/src/execution_runtime/services/execution_records.py#L78-L119)
- [execution_records.py:196-303](file://products/execution-runtime/src/execution_runtime/services/execution_records.py#L196-L303)
- [execution_records.py:310-333](file://products/execution-runtime/src/execution_runtime/services/execution_records.py#L310-L333)

### Audit Emission: Fire-and-Forget Delivery
Audit events are emitted asynchronously:
- Non-blocking daemon thread per event with short timeout.
- No impact on execution path if audit service is unreachable.
- Metrics recorded for emit success/failure.
- Event schema matches shared contracts; optional identity fields omitted when absent.

**Section sources**
- [audit_emitter.py:30-99](file://products/execution-runtime/src/execution_runtime/services/audit_emitter.py#L30-L99)

### Configuration: Frozen Settings and Startup Validation
Configuration is loaded from environment variables and validated at startup:
- Supports memory/postgres backend selection.
- Requires positive gateway timeout and valid DB URL when postgres selected.
- Provides audit service URL and credentials for fire-and-forget emission.
- Flight retention seconds bound single-flight registry lifetime.

**Section sources**
- [config.py:20-84](file://products/execution-runtime/src/execution_runtime/core/config.py#L20-L84)

## Dependency Analysis
The Execution Runtime depends on:
- Tool Gateway: outbound HTTP calls for tool invocations; uses delegated token as bearer; timeouts and transport errors handled gracefully with `GatewayUncertain` exceptions.
- Postgres (required for mutation): durable execution ledger for dispatch claims and observations; fail-closed admission without memory fallback.
- Audit Service (optional): fire-and-forget emission; failures do not degrade execution path.
- Agent Platform: sends signed envelopes and delegated tokens via authenticated handoff; relies on worker's fail-closed posture.

**Updated** Postgres is now required for mutation admission, not optional. The execution ledger provides durable dispatch claims instead of relying solely on in-process single-flight semantics.

```mermaid
graph TB
Agent["Agent Platform"] --> |Authenticated Handoff| Worker["Execution Runtime"]
Worker --> |HTTP POST| Gateway["Tool Gateway"]
Worker --> |Required| Postgres["Postgres (Execution Ledger)"]
Worker --> |Fire-and-Forget| Audit["Audit Service"]
```

**Diagram sources**
- [executor.py:27-59](file://products/execution-runtime/src/execution_runtime/services/executor.py#L27-L59)
- [execution_ledger.py:78-101](file://products/execution-runtime/src/execution_runtime/services/execution_ledger.py#L78-L101)
- [audit_emitter.py:68-99](file://products/execution-runtime/src/execution_runtime/services/audit_emitter.py#L68-L99)

**Section sources**
- [executor.py:27-59](file://products/execution-runtime/src/execution_runtime/services/executor.py#L27-L59)
- [execution_ledger.py:78-101](file://products/execution-runtime/src/execution_runtime/services/execution_ledger.py#L78-L101)
- [audit_emitter.py:68-99](file://products/execution-runtime/src/execution_runtime/services/audit_emitter.py#L68-L99)

## Performance Considerations
- Single-flight deduplication reduces redundant gateway calls under concurrency and replay scenarios.
- Bounded completion cache prevents unbounded memory growth; eviction occurs post-completion and on every run.
- Timeouts on gateway calls protect worker resources; mapped to structured errors for consistent handling upstream.
- Fire-and-forget audit emission avoids blocking the critical path; failures are logged and counted.
- Best-effort record store ensures availability even if Postgres is down; audit completeness may degrade but execution continues.
- **Updated** Durable dispatch claims add Postgres overhead but provide crash safety; claim operations are atomic and bounded.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and diagnostics:
- Unauthorized handoff: check EXECUTION_HANDOFF_TOKEN configuration and bearer header; inspect rejection reason unauthorized.
- Invalid signature: verify EXECUTION_SIGNING_KEY provisioning and envelope integrity; inspect rejection reason signature_invalid.
- Argument digest mismatch: ensure arguments sent match the signed args_digest; inspect rejection reason args_digest_mismatch.
- Gateway timeout: adjust EXECUTION_GATEWAY_TIMEOUT_SECONDS; inspect executor timeout mapping to timeout status.
- Transport error: verify tool gateway reachability; inspect TRANSPORT_ERROR mapping and logs.
- Late completion: indicates a racing close (e.g., resumed stream timeout); check record store behavior and late completion metrics.
- Audit emission failures: check EXECUTION_AUDIT_SERVICE_URL and credentials; review audit emit metrics and warnings.
- **Updated** Durable claim failures: check Postgres connectivity and schema; inspect claim_commit_unconfirmed and store_unavailable reasons.
- **Updated** Protocol errors: verify v3 envelope format, signature validity, and lifetime bounds; check protocol_unsupported and lifetime_invalid reasons.
- **Updated** Recovery state: use execution ledger lookup to determine if execution is not_dispatched, dispatch_claimed, outcome_unknown, or result_recorded.

**Section sources**
- [handoff.py:144-235](file://products/execution-runtime/src/execution_runtime/api/routes/handoff.py#L144-L235)
- [executor.py:27-59](file://products/execution-runtime/src/execution_runtime/services/executor.py#L27-L59)
- [execution_records.py:239-293](file://products/execution-runtime/src/execution_runtime/services/execution_records.py#L239-L293)
- [audit_emitter.py:77-99](file://products/execution-runtime/src/execution_runtime/services/audit_emitter.py#L77-L99)
- [execution_ledger.py:416-491](file://products/execution-runtime/src/execution_runtime/services/execution_ledger.py#L416-L491)

## Conclusion
The Execution Runtime provides a secure, isolated, and auditable execution layer for approved mutating actions. It enforces authentication, cryptographic verification, idempotency, and resilient error handling while maintaining strong separation from the agent process. 

**Updated** With SPEC-063 crash-safe execution infrastructure, the service now provides durable dispatch claims that prevent duplicate mutations even after process crashes or database failures. The execution ledger ensures at-most-one worker-to-gateway dispatch guarantees, while the run guard mechanism and v3 signed contracts provide tamper-evident execution chains. The enhanced handoff protocol includes fail-closed persistence, typed outcomes handling, and comprehensive failure testing framework.

The design ensures that no unauthorized mutations can occur, all actions are traceable via signed receipts and audit events, and the system remains robust under failures and retries. Scaling considerations emphasize single-replica deployment with durable claim management; future scaling would require distributed claim coordination.

[No sources needed since this section summarizes without analyzing specific files]

## Appendices

### Creating Bounded Actions and Signing Execution Requests
- Define a bounded action as a tool invocation with explicit intent and parameters.
- At resume, construct a signed execution request envelope containing tool name, parked arguments' digest, identifiers, and timestamps.
- Sign the envelope using HMAC-SHA256 with the platform signing key; compute canonical digest of arguments.
- Forward the envelope, arguments, and delegated token to the worker's handoff endpoint.

**Section sources**
- [SPEC-037-signed-execution-requests/spec.md:50-81](file://docs/specs/SPEC-037-signed-execution-requests/spec.md#L50-L81)
- [execution_signing.py:40-93](file://products/execution-runtime/src/execution_runtime/services/execution_signing.py#L40-L93)

### Handling Action Failures
- Gateway timeouts map to receipt status timeout; transport errors map to failed; successful responses map to succeeded.
- Record store handles late arrivals by preserving the first-written receipt; late completions are logged and counted.
- Audit events capture execution_completed with status and duration; rejections emit execution_rejected with reason.
- **Updated** `GatewayUncertain` exceptions indicate transport uncertainty where the target may still have acted; these should not be treated as definitive failures.

**Section sources**
- [executor.py:13-71](file://products/execution-runtime/src/execution_runtime/services/executor.py#L13-L71)
- [execution_records.py:239-293](file://products/execution-runtime/src/execution_runtime/services/execution_records.py#L239-L293)
- [handoff.py:266-304](file://products/execution-runtime/src/execution_runtime/api/routes/handoff.py#L266-L304)

### Debugging Execution Issues
- Inspect handoff rejections for unauthorized, signature_invalid, or args_digest_mismatch reasons.
- Review executor logs for gateway timeouts and transport errors; validate tool gateway URL and connectivity.
- Check record store readiness and Postgres availability; verify fallback to in-memory store.
- Monitor audit emit metrics and warnings for delivery failures.
- **Updated** Use execution ledger lookup to diagnose durable claim state and recovery information.
- **Updated** Check protocol validation errors for v3 envelope format, signature, and lifetime issues.

**Section sources**
- [handoff.py:306-356](file://products/execution-runtime/src/execution_runtime/api/routes/handoff.py#L306-L356)
- [executor.py:27-59](file://products/execution-runtime/src/execution_runtime/services/executor.py#L27-L59)
- [execution_records.py:295-303](file://products/execution-runtime/src/execution_runtime/services/execution_records.py#L295-L303)
- [audit_emitter.py:77-99](file://products/execution-runtime/src/execution_runtime/services/audit_emitter.py#L77-L99)
- [execution_ledger.py:416-491](file://products/execution-runtime/src/execution_runtime/services/execution_ledger.py#L416-L491)

### Security Considerations
- Isolation: separate deployment, ClusterIP-only access, no external routes; enforced at infrastructure layer.
- Credential management: static handoff token and signing key provisioned via deploy chain; missing secrets fail closed.
- Authorization: delegated token carries approver identity; worker never holds user authority; tool gateway evaluates policy.
- Prevention of unauthorized mutations: fail-closed verification, signature and digest checks, single-flight enforcement.
- **Updated** Durable dispatch claims prevent duplicate mutations across process restarts; burn-on-claim semantics ensure at-most-one dispatch.
- **Updated** v3 protocol validation enforces strict contract compliance and prevents legacy envelope bypass.
- **Updated** Execution ledger provides tamper-evident observation history with integrity conflict detection.

**Section sources**
- [SPEC-038-isolated-execution-worker/spec.md:79-117](file://docs/specs/SPEC-038-isolated-execution-worker/spec.md#L79-L117)
- [config.py:20-84](file://products/execution-runtime/src/execution_runtime/core/config.py#L20-L84)
- [executor.py:27-59](file://products/execution-runtime/src/execution_runtime/services/executor.py#L27-L59)
- [execution_ledger.py:77-491](file://products/execution-runtime/src/execution_runtime/services/execution_ledger.py#L77-L491)
- [execution_protocol.py:81-123](file://products/execution-runtime/src/execution_runtime/services/execution_protocol.py#L81-L123)

### Crash-Safe Execution Infrastructure
The SPEC-063 implementation provides crash-safe execution through several key mechanisms:

- **Durable Dispatch Claims**: Postgres-backed claims prevent duplicate mutations even after process crashes. Each claim is uniquely owned and never reclaimed.
- **Run Guard Mechanism**: Atomic claim consumption before gateway invocation ensures only one process can dispatch per approved call.
- **Typed Outcomes Handling**: Clear distinction between not_dispatched, dispatch_claimed, outcome_unknown, and result_recorded states.
- **V3 Signed Contracts**: Enhanced protocol with HMAC-over-canonical-JSON signatures and strict schema validation.
- **Enhanced Handoff Protocol**: Fail-closed persistence with structured refusal responses and recovery information.
- **Comprehensive Failure Testing**: Deterministic barrier-based testing framework covering 36 failure scenarios.

**New Section** This infrastructure ensures at-most-one worker-to-gateway dispatch guarantees even after process crashes or database failures, while maintaining backward compatibility with existing execution flows.

**Section sources**
- [SPEC-063-crash-safe-execution/spec.md:29-45](file://docs/specs/SPEC-063-crash-safe-execution/spec.md#L29-L45)
- [execution_ledger.py:77-491](file://products/execution-runtime/src/execution_runtime/services/execution_ledger.py#L77-L491)
- [execution_protocol.py:1-123](file://products/execution-runtime/src/execution_runtime/services/execution_protocol.py#L1-L123)
- [handoff.py:144-235](file://products/execution-runtime/src/execution_runtime/api/routes/handoff.py#L144-L235)