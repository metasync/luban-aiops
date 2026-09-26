# Execution Runtime

Isolated execution worker for approved bounded actions (SPEC-038).

## Purpose

`execution-runtime` receives signed execution requests handed off by
agent-platform after HITL approval, executes the approved bounded
action through the tool-gateway, and returns a signed receipt with the
result. It is the only platform component that performs approved
mutating tool invocations on Luban's approved worker path. SPEC-063 adds the
v3 signed envelope and durable dispatch ledger; legacy receipts remain readable,
but legacy envelopes are not executable.

Responsibilities:

- authenticating the internal handoff (`POST /api/v1/executions/handoff`)
  with the static handoff token and verifying the signed execution
  request envelope plus the invocation-boundary argument digest
  (fail-closed)
- executing approved bounded actions via the tool-gateway using the
  forwarded confirmer token
- consuming a committed single-use Postgres claim before dispatch, then persisting
  signed observations/receipts before returning an original result
- returning metadata-only status on duplicates; no raw-output or secret replay
- emitting `execution_completed` / `execution_rejected` audit events

## Lifecycle and idempotency

The deployment stays at one long-running replica with `Recreate`, synchronous
handoff, and no queue or worker pool. Postgres—not the old process-local flight
cache—owns dispatch authority across restarts and overlapping new-version workers.
Unique `execution_id` and `(confirm_id, call_id)` identities protect each approved
call. At most one worker dispatch attempt is allowed, **not exactly-once target
effects**. Claim acknowledgment loss authorizes no send; a consumed claim is never
reset, retried, or taken over, even if its owner dies before sending.

Requests expire within 900 seconds using database time. A claim lacking a validated
result becomes `outcome_unknown` by 120 seconds; this is not cancellation or a lease.
Late results remain evidence but cannot resume a stopped run. Claims/observations
are retained at least 30 days after expiry, independently of session deletion.
The bounded `ExecutionLedger.retention_sweep()` never removes run identities.

SIGTERM closes new admission and drains up to 35 seconds inside the 45-second pod
grace period. Neither graceful nor abrupt termination cancels remote work or releases
claims. Scaling and queueing remain deferred. Deployment/restore must follow the
[mutation-disabled cutover runbook](../../docs/guides/execution-cutover-restore.md).

## Configuration

| Variable | Meaning | Default |
| --- | --- | --- |
| `EXECUTION_SIGNING_KEY` | HMAC key verifying envelopes / signing receipts (shared with agent-service) | unset ⇒ all handoffs rejected |
| `EXECUTION_HANDOFF_TOKEN` | static handoff credential | unset ⇒ all handoffs rejected |
| `TOOL_GATEWAY_URL` | tool-gateway endpoint | unset ⇒ executions fail |
| `EXECUTION_GATEWAY_TIMEOUT_SECONDS` | gateway invocation budget, >0 and ≤30s | `30` |
| `EXECUTION_STATE_STORE_BACKEND` | legacy store choice; mutation admission requires actual Postgres | `memory` (cannot admit) |
| `EXECUTION_STATE_DB_URL` | Postgres ledger DSN; no admission fallback | unset |
| `EXECUTION_ADMISSION_ENABLED` | explicit worker admission gate, also requires enabled catalog | `false` |
| `EXECUTION_ADMISSION_EPOCH` | canonical UUID matching the external agent epoch and catalog | unset |
| `EXECUTION_AUDIT_SERVICE_URL` | audit-service endpoint (log-only when unset) | unset |
| `EXECUTION_AUDIT_CLIENT_ID` / `EXECUTION_AUDIT_CLIENT_SECRET` | audit ingest credential | `execution-runtime` / unset |
| `EXECUTION_FLIGHT_RETENTION_SECONDS` | legacy cache setting; never ledger retention or dispatch authority | `900` |

`/health/live` is process-local. `/health/ready` returns 503 while admission is
disabled or credentials, Postgres durability/schema, or epoch checks fail. Runtime
startup verifies but never creates/repairs the catalog. Fixed-cardinality metrics
report admission availability, duplicates/conflicts, persistence failures, drain,
and unresolved count/database age. Zero unresolved gauges during a store outage
are not proof of a clean ledger; check admission availability too.

## Development

```sh
make -C products/execution-runtime sync   # install dependencies
make -C products/execution-runtime test   # run the test suite
```

## Boundary

This service decides nothing: it never evaluates policy, never grants
approval, and never retries or re-executes. It exposes no portal or LLM
surface and no external route — the handoff endpoint is reachable only
inside the cluster. Isolation is enforced at the infrastructure layer:
its own Deployment/Service, its own secrets, and no gateway route.
