# Execution Cutover, Downgrade, and Restore Runbook

Operational procedure for changing the **execution-runtime** binary version and for
recovering from a **database restore** of the execution ledger. This is the operator-facing
companion to SPEC-063 R-7b ("Compatibility through a gated cutover") and ADR-0013
(durable single-use execution claims).

> **Read this first.** The durable ledger guarantees *at most one worker-to-gateway dispatch
> per approved call*. It does **not** guarantee exactly-once business effects, and it cannot
> make an arbitrary out-of-band restore or a direct old-binary deployment safe by itself.
> Nothing in the cutover tooling ever re-enables admission: enabling is a separate, explicit,
> separately authorized step.

## Why a gated cutover exists

Admission authority lives in a single `execution_protocol_state` row carrying an
**external admission epoch** (a UUID) and an `admission_enabled` flag. Two properties drive
every rule below:

1. **Old binaries cannot be trusted to honor a new flag.** A downgrade to a pre-SPEC-063
   worker would silently return execution to the process-local, best-effort path. The gate
   therefore refuses any mutation-enabled downgrade unless the operator explicitly selects
   `disabled-recovery` and first disables mutations and stops the worker.
2. **A same-era snapshot cannot be detected by a flag stored inside it.** If you restore a
   database snapshot, the restored row's `admission_enabled`/`admission_epoch` are whatever
   they were at snapshot time — they cannot tell you that a restore happened. The interlock
   is therefore **external**: keep mutations disabled, choose a fresh epoch outside the
   restored database, and configure it on both consumers. A consumer configured with that
   new epoch refuses the old catalog with `epoch_mismatch`. Restoring the catalog while
   retaining the old consumer epoch does **not** produce this protection automatically.

The decision logic is versioned in
`products/execution-runtime/src/execution_runtime/services/execution_cutover.py` and is the
same code the failure harness exercises at **F-33**. The cutover wrapper adds bounded
`kubectl` stop/inventory checks for disabled recovery; the rotation wrapper operates
only on the DSN-selected database. Both propagate refusal from the decision core.

## Tools

| Tool | Purpose |
|---|---|
| `shared/platform-ops/gitops/execution-cutover.sh` | Refuses downgrade/unknown in normal mode. Disabled-recovery requires operator confirmation that mutations are disabled, scales the worker to zero, waits for deletion, and refuses failed/nonempty worker or agent inventory. It does not itself disable the gateway, stop agents, inspect off-cluster senders, or replace images. |
| `shared/platform-ops/gitops/rotate-execution-epoch.sh` | Writes the supplied external epoch into the DSN-selected catalog with admission **still disabled**. Refuses an enabled catalog or invalid schema; idempotent. It does not update consumer configuration; its namespace argument does not select the database. |
| `python -m execution_runtime.services.execution_cutover plan-cutover` | The versioned decision core (JSON out; non-zero exit on refusal). |
| `python -m execution_runtime.services.execution_cutover rotate-epoch` | The versioned rotation core. |

## Initial SPEC-063 protocol cutover

The first 0.42.x → 0.43.0 protocol transition is **coordinated and mutation-disabled**,
even though its semantic version is an upgrade. The version classifier is not a migration
or compatibility verifier. Stock `make deploy` does not invoke this guard, migrate the
ledger, provision its epoch, or perform this procedure; do not use it as an initial cutover
shortcut. It also waits for worker readiness, which is deliberately 503 while disabled.

1. Record the authorized context/namespace, image versions, operator, target scope, and
   evidence destination. Disable writes at the gateway gate, new agent admission, and new
   worker handoffs. For new consumers, both `AGENT_EXECUTION_ADMISSION_ENABLED` and
   `EXECUTION_ADMISSION_ENABLED` stay false; clear the catalog flag if it already exists.
2. Inventory in-flight attempts and held deliveries. Drain within the bounded budget,
   preserve old receipts, and classify ambiguous work as unresolved. Stop every old
   execution-capable agent/worker and separately inventory any off-cluster senders.
   Verify termination rather than treating a failed wait as success. Keep governed
   investigative reads available; termination is not downstream cancellation.
3. Select a fresh external UUID epoch and securely supply `EXECUTION_STATE_DB_URL` for
   the intended ledger. Run the additive migration from the matching worker distribution:

   ```sh
   uv run --frozen --project products/execution-runtime \
     python -m execution_runtime.services.execution_migration --epoch "$NEW_EXECUTION_EPOCH"
   ```

   Verify schema/constraints, DB permissions and durability, disabled catalog state, and
   epoch. Migration failure leaves admission disabled; startup never repairs the schema.
   Preserve historical receipt bytes and their signing verification material.
4. Deploy matching agent, worker, gateway, and portal versions with admission disabled.
   Configure agent `AGENT_EXECUTION_STATE_DB_URL`, worker `EXECUTION_STATE_DB_URL` and
   `EXECUTION_STATE_STORE_BACKEND=postgres`, and matching `AGENT_EXECUTION_ADMISSION_EPOCH`
   / `EXECUTION_ADMISSION_EPOCH`. Rotate the internal handoff credential on both consumers
   so old processes cannot enter the new worker; scope secret changes to the authorized
   environment. Do not rotate away the only key verifying historical receipts.
5. Verify image/process inventory, absence of old executable consumers, liveness, schema,
   owner recovery, read-only routing, and failure-test evidence. Disabled readiness is
   expected; do not wait for Ready or enable admission merely to complete deployment.
6. Only after unresolved-work accounting and explicit operational approval, enable the
   verified catalog and matching worker/agent configuration, check admission readiness,
   then restore the gateway mutation gate. Catalog enablement is an explicit operator
   database transaction; no shipped migration/rotation command performs it. Carry out only
   the separately authorized acceptance actions. Leave all mutation gates closed on any
   failed check; do not fall back to the old executor.

## Later same-protocol forward replacements

The version decision permits `upgrade`/`same` and leaves the reported admission state
unchanged. This does not prove protocol compatibility or authorize a rollout. Keep the
single-replica `Recreate` posture and apply the initial procedure again for any protocol
transition. A read-only classification example is:

```sh
EXECUTION_CUTOVER_PLAN_ONLY=true \
  shared/platform-ops/gitops/execution-cutover.sh --current 0.43.0 --target 0.43.0
```

## Downgrade (deliberate, rare)

A downgrade is refused in `normal` mode. To perform one you must run a **disabled recovery**:

1. **Disable mutations.** Apply and verify `GATEWAY_MUTATING_TOOLS_ENABLED=false`
   (removing the profile only changes desired configuration, not running processes).
   Clear both service admission flags and the catalog flag. Old binaries may ignore
   new flags: stop all agent issuers and inventory other possible senders explicitly.
2. **Confirm and stop the worker.** After verifying the disabled posture, run the guard
   in disabled-recovery mode with the authorized namespace. It scales the worker to zero,
   waits for pod deletion, and refuses failed inventory or any remaining worker/agent:

   ```sh
   EXECUTION_RECOVERY_MODE=disabled-recovery EXECUTION_MUTATIONS_DISABLED=true \
     shared/platform-ops/gitops/execution-cutover.sh --current 0.43.0 --target 0.42.0 "$NAMESPACE"
   ```

3. **Old-process inventory.** The wrapper's namespace label checks are only part of the
   inventory: confirm no other execution-capable process can send. Failed scale, wait,
   or inventory means stop, not permission to replace. **Pod termination does not prove
   downstream work stopped and does not release any durable claim** — classify anything
   ambiguous as *unresolved* and investigate the target system directly.
4. **Replace the binary** (deploy the older image).
5. Admission remains **disabled**. Do not re-enable it as part of a downgrade.

If the relative version cannot be determined (an unparseable tag), the guard treats it as
`unknown` and additionally **requires an external epoch rotation** before fresh actions,
because the age of the binary relative to the catalog cannot be established.

## Database restore

Restoring the ledger database is a disabled-recovery operation. Follow the order exactly.
The decision core can evaluate supplied blocker facts, but it does not independently
observe operator actions, elapsed wall time, or external snapshots.

1. **Retain evidence outside the snapshot.** Copy the receipts/claims/observations you may
   need for reconciliation to storage that the restore will not overwrite. Evidence lost from
   the restored snapshot cannot be reconstructed.
2. **Stop every possible old sender.** Scale execution-runtime to zero and disable mutations
   as above. Assume any process that held a pre-restore credential could still try to send.
3. **Restore while isolated; rotate the epoch and handoff credential.** Keep every sender
   stopped and the gateway disabled while restoring. A snapshot may restore an enabled
   catalog: explicitly clear that flag before rotation. Select and retain a fresh external
   UUID; configure it as both consumers' admission epoch, with their flags still false.
   Securely export `EXECUTION_STATE_DB_URL` for the intended database, then record that
   same UUID in the catalog (not a second newly generated UUID):

   ```sh
   shared/platform-ops/gitops/rotate-execution-epoch.sh --epoch "$NEW_EXECUTION_EPOCH"
   ```

   The script selects the database by DSN, not namespace, and changes only the catalog.
   Separately rotate both consumers' handoff credential using environment-scoped secret
   provisioning; never run a shared-environment sync script against an isolated scope.
   A new-epoch consumer refuses the old catalog with `epoch_mismatch`; after rotation,
   admission remains disabled. Neither step recovers lost claims or detects all restores.
4. **Wait out the old-validity window.** Every request issued before the restore had at most
   `MAX_LIFETIME_SECONDS = 900` of life, measured from the **last possible issuer shutdown**,
   plus a bounded clock-disagreement margin (`CLOCK_DISAGREEMENT_MARGIN_SECONDS = 60`). The
   base wait is therefore **960 seconds**, and it grows by any known issuer-shutdown skew or
   clock disagreement:

   ```
   required_wait = 900 + 60 + max(0, clock_disagreement) + max(0, issuer_shutdown_skew)
   ```

   Observation never resets this deadline — it is measured once from the last possible issuer
   shutdown and is not extended by later reads.
5. **Investigate downstream work.** Reconcile the target system's actual state against the
   retained receipts. A claim that was committed but whose send outcome is unknown stays
   *unknown*; never infer cancellation from a pod termination.
6. **Only then** consider fresh, separately approved actions with compatible consumers.
   Enabling the verified catalog and matching worker/agent configuration requires its own
   explicit operational approval, as in the initial cutover. `migrate()` only creates or
   verifies a disabled catalog; migration, startup, and restore tooling never enable it.

## Limits (state these honestly)

- **Lost evidence.** Anything not retained outside a restored snapshot is gone; the ledger
  cannot reconstruct claims, receipts, or observations that the snapshot predates or omits.
- **No universal rollback detection.** An arbitrary out-of-band restore, a direct
  old-binary `kubectl set image`, or a hand-edited catalog **cannot** be detected by this
  ledger alone. The gate only covers the *supported* wrapper path and the *external* epoch
  mismatch it can observe. F-33 tests the versioned CLI refusal and a catalog modeling
  restored state against a mismatched external epoch; the shell checks have separate
  local regression coverage described below.
- **No remote cancellation.** Stopping a worker or terminating a pod never claims to cancel
  work already dispatched downstream; such outcomes remain explicitly unknown.

## Verification

The failure harness exercises the decision core and real-Postgres epoch interlock at
**F-33** (`products/execution-runtime/tests/failure/test_cutover.py`); it models a restored
catalog's state, not a complete backup/restore system or a wall-clock 960-second drill:

- `downgrade` — the versioned CLI refuses downgrade in `normal` mode and returns mandatory
  disabled/stopped preconditions in `disabled-recovery`; upgrade never flips admission on.
- `restore` — a catalog carrying the old epoch under a new external epoch fails closed,
  `rotate_epoch` records the new epoch with admission still disabled, and the old-validity
  wait calculation includes the configured margins.
- `epoch_mismatch` — a ledger whose external epoch differs from the stored/envelope epoch
  mints no dispatch permit, while a correctly-epoched ledger does (control).

The shell's actual scale/wait/inventory behavior is covered locally by
`products/execution-runtime/tests/test_config.py::CutoverWrapperTests::test_disabled_recovery_requires_verified_empty_sender_inventory`
using the real decision CLI and fake kubectl: empty/drained inventories succeed;
failed scale/wait/read, remaining worker/issuer, or absent operator confirmation refuse.
No cluster is contacted by that test. F-32 independently exercises real worker process
overlap and bounded drain. The full required delivery gate is `make verify`, including
`make execution-failure-test`; failed runs remain retained.

Run F-33 alone in the development stage (never a delivery gate):

```sh
OTEL_SDK_DISABLED=true uv run --offline --frozen --project products/execution-runtime \
  python products/execution-runtime/tests/failure/run.py --stage development --select F-33
```
