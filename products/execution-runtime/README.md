# Execution Runtime

Isolated execution worker for approved bounded actions (SPEC-038).

## Purpose

`execution-runtime` receives signed execution requests handed off by
agent-platform after HITL approval, executes the approved bounded
action through the tool-gateway, and returns a signed receipt with the
result. It is the only platform component that performs approved
mutating tool invocations (SPEC-037 envelope contract, inherited
verbatim).

Responsibilities:

- authenticating the internal handoff (`POST /api/v1/executions/handoff`)
  with the static handoff token and verifying the signed execution
  request envelope plus the invocation-boundary argument digest
  (fail-closed)
- executing approved bounded actions via the tool-gateway using the
  forwarded confirmer token
- authoring signed receipts and closing rows in the shared
  `execution_records` table (first write wins)
- emitting `execution_completed` / `execution_rejected` audit events

## Lifecycle and idempotency

The deployment is a single long-running pod (`replicas: 1`) with a
synchronous blocking handoff — there is no task queue and no worker
pool. Single-flight idempotency keyed by `execution_id` guarantees the
gateway call happens exactly once per signed request; the registry is
in-process and authoritative precisely because there is one replica.

Scaling beyond `replicas: 1` requires a durable flight registry first,
and the queue/pool shape (async execution queue) is parked until
concurrent-operator workload makes the single pod a queueing
bottleneck — the re-evaluation trigger is recorded in the SPEC-038
Non-Goals and the delivery roadmap.

## Configuration

| Variable | Meaning | Default |
| --- | --- | --- |
| `EXECUTION_SIGNING_KEY` | HMAC key verifying envelopes / signing receipts (shared with agent-service) | unset ⇒ all handoffs rejected |
| `EXECUTION_HANDOFF_TOKEN` | static handoff credential | unset ⇒ all handoffs rejected |
| `TOOL_GATEWAY_URL` | tool-gateway endpoint | unset ⇒ executions fail |
| `EXECUTION_GATEWAY_TIMEOUT_SECONDS` | gateway invocation budget | `30` |
| `EXECUTION_STATE_STORE_BACKEND` | `memory` / `postgres` | `memory` |
| `EXECUTION_STATE_DB_URL` | sessions-database URL (postgres backend) | — |
| `EXECUTION_AUDIT_SERVICE_URL` | audit-service endpoint (log-only when unset) | unset |
| `EXECUTION_AUDIT_CLIENT_ID` / `EXECUTION_AUDIT_CLIENT_SECRET` | audit ingest credential | `execution-runtime` / unset |
| `EXECUTION_FLIGHT_RETENTION_SECONDS` | completed-flight cache retention | `900` |

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
