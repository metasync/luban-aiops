"""Disabled cutover, downgrade, and restore interlock (SPEC-063 R-7b).

Decision logic for execution-runtime version cutover, downgrade, and
database-restore operations. It is kept separate from the deploy scripts so the
GitOps wrapper can call it and refuse on a denial, and so the failure harness
(F-33) can exercise it deterministically against real Postgres. Nothing here
ever enables admission: enabling remains an explicit, separately authorized
step ("do not automatically enable during deploy/startup").

Invariants (plan.md R-7b):

- A mutation-enabled version downgrade is refused unless the operator selects
  the explicit ``disabled-recovery`` mode. Old binaries cannot be trusted to
  honor a new flag, so in that mode the caller must disable gateway mutations
  and stop the worker before the binary is replaced.
- A DB restore is a disabled-recovery operation: retain evidence outside the
  restored snapshot, stop possible old senders, rotate the external
  epoch/handoff credential, and wait out every previously issued request's
  maximum lifetime (900s) measured from the last possible issuer shutdown, plus
  a bounded clock-disagreement margin.
- A same-era snapshot cannot be detected by a flag stored inside it, so the
  external epoch rotation is mandatory: a restored catalog whose stored epoch
  differs from the new external epoch fails closed (``epoch_mismatch``) until an
  explicit rotation records the new epoch with admission still disabled.
  Universal out-of-band rollback detection is never claimed.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from uuid import UUID

import psycopg

from execution_runtime.services.execution_migration import connect, verify_schema
from execution_runtime.services.execution_protocol import (
    MAX_LIFETIME_SECONDS, ProtocolError,
)

RECOVERY_MODES = ("normal", "disabled-recovery")
# Bounded margin for clock disagreement between the last possible issuer of a
# request and the operator rotating the epoch. Observation never resets a
# request deadline, so the wait is measured once from the last possible issuer
# shutdown and is not extended by later reads.
CLOCK_DISAGREEMENT_MARGIN_SECONDS = 60


@dataclass(frozen=True)
class CutoverDecision:
    """Outcome of a version-change plan. ``admission_after`` is never True unless
    it was already True and the change is a plain upgrade/same (this module never
    flips admission on)."""

    allowed: bool
    reason: str
    mode: str
    change: str
    admission_after: bool = False
    must_disable_mutations: bool = False
    must_stop_worker: bool = False
    requires_epoch_rotation: bool = False


@dataclass(frozen=True)
class RestoreDecision:
    """Outcome of a DB-restore interlock check. Admission is never enabled here."""

    allowed: bool
    blockers: tuple = ()
    epochs_reconciled: bool = False
    admission_after: bool = False
    required_wait_seconds: int = 0


def _version_tuple(value):
    """Comparable version tuple, or None when the version cannot be determined."""
    if isinstance(value, (tuple, list)):
        items = list(value)
    elif isinstance(value, str):
        items = [part for part in value.strip().split(".") if part != ""]
    else:
        return None
    try:
        return tuple(int(part) for part in items)
    except (TypeError, ValueError):
        return None


def plan_cutover(*, current_version, target_version, admission_enabled, mode):
    """Decide whether a version change may proceed, and under what interlock.

    A downgrade -- or any change whose version cannot be determined -- is refused
    unless ``mode`` is ``disabled-recovery``. In that mode the decision requires
    the caller to disable gateway mutations and stop the worker first; an unknown
    version additionally requires an external epoch rotation because the relative
    age of the binary cannot be established.
    """
    if mode not in RECOVERY_MODES:
        return CutoverDecision(False, "bad_recovery_mode", str(mode), "unknown")
    current, target = _version_tuple(current_version), _version_tuple(target_version)
    if current is None or target is None:
        change = "unknown"
    elif target < current:
        change = "downgrade"
    elif target > current:
        change = "upgrade"
    else:
        change = "same"
    if change in ("downgrade", "unknown"):
        if mode != "disabled-recovery":
            return CutoverDecision(False, "downgrade_requires_disabled_recovery", mode, change)
        return CutoverDecision(True, "disabled_recovery_required", mode, change,
                               admission_after=False, must_disable_mutations=True,
                               must_stop_worker=True,
                               requires_epoch_rotation=(change == "unknown"))
    # upgrade/same: no interlock; the admission state is reported unchanged and
    # is never turned on by this function.
    return CutoverDecision(True, "none", mode, change, admission_after=bool(admission_enabled))


def old_validity_wait_seconds(*, clock_disagreement_seconds=0, issuer_shutdown_skew_seconds=0):
    """Bounded wait before fresh, separately approved actions after a restore.

    Every previously issued request had at most ``MAX_LIFETIME_SECONDS`` of life
    measured from the last possible issuer shutdown; add a bounded
    clock-disagreement margin and any known issuer-shutdown skew. Negative inputs
    are clamped to zero so the wait can never shrink below one full lifetime.
    """
    skew = (max(0, int(clock_disagreement_seconds))
            + max(0, int(issuer_shutdown_skew_seconds)))
    return MAX_LIFETIME_SECONDS + CLOCK_DISAGREEMENT_MARGIN_SECONDS + skew


def restore_interlock(*, stored_epoch, external_epoch, evidence_retained_outside,
                      old_senders_stopped, wait_complete,
                      clock_disagreement_seconds=0, issuer_shutdown_skew_seconds=0):
    """Gate a DB restore. The restored catalog carries the OLD epoch; the operator
    must rotate the EXTERNAL epoch so the mismatch fails closed until an explicit
    rotation records it. Every blocker must clear before fresh actions; admission
    is never enabled here.
    """
    epochs_reconciled = bool(stored_epoch) and stored_epoch == external_epoch
    blockers = []
    if not evidence_retained_outside:
        blockers.append("evidence_not_retained_outside_snapshot")
    if not old_senders_stopped:
        blockers.append("old_senders_not_stopped")
    if not epochs_reconciled:
        blockers.append("external_epoch_not_rotated")
    if not wait_complete:
        blockers.append("old_validity_window_open")
    return RestoreDecision(allowed=not blockers, blockers=tuple(blockers),
                           epochs_reconciled=epochs_reconciled, admission_after=False,
                           required_wait_seconds=old_validity_wait_seconds(
                               clock_disagreement_seconds=clock_disagreement_seconds,
                               issuer_shutdown_skew_seconds=issuer_shutdown_skew_seconds))


def rotate_epoch(dsn, new_epoch, *, connection_factory=connect):
    """Explicit external epoch rotation for a restored/disabled catalog.

    Records ``new_epoch`` in ``execution_protocol_state`` with admission STILL
    disabled. Refuses an enabled catalog (disable it first) and an invalid
    schema, and is idempotent for the epoch already recorded. ``migrate()``
    deliberately never changes an existing epoch, so this is the only supported
    rotation path and the mandatory interlock for a same-era snapshot restore.
    """
    new_epoch = str(UUID(new_epoch))  # ValueError -> caller fails closed
    connection = connection_factory(dsn)
    try:
        # Same lock as migrate() so rotation and migration cannot interleave.
        connection.execute("SELECT pg_advisory_xact_lock(-630001)")
        state = verify_schema(connection)
        if state["admission_enabled"]:
            raise ProtocolError("epoch_rotation_refused_enabled")
        if state["admission_epoch"] == new_epoch:
            connection.commit()
            return {"rotated": False, "admission_epoch": new_epoch, "admission_enabled": False}
        rowcount = connection.execute(
            "UPDATE execution_protocol_state SET admission_epoch=%s "
            "WHERE singleton=true AND admission_enabled=false", (new_epoch,)).rowcount
        if rowcount != 1:
            raise ProtocolError("epoch_rotation_conflict")
        connection.commit()
        return {"rotated": True, "admission_epoch": new_epoch, "admission_enabled": False}
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(
        description="Execution cutover/downgrade/restore interlock; never auto-enables admission")
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan-cutover", help="decide a version change")
    plan.add_argument("--current-version", required=True)
    plan.add_argument("--target-version", required=True)
    plan.add_argument("--admission-enabled", action="store_true")
    plan.add_argument("--mode", default="normal")
    rotate = subparsers.add_parser(
        "rotate-epoch", help="record a new external epoch (admission stays disabled)")
    rotate.add_argument("--epoch", required=True)
    rotate.add_argument("--dsn-env", default="EXECUTION_STATE_DB_URL")
    args = parser.parse_args()
    if args.command == "plan-cutover":
        decision = plan_cutover(current_version=args.current_version,
                                target_version=args.target_version,
                                admission_enabled=args.admission_enabled, mode=args.mode)
        print(json.dumps(decision.__dict__))
        raise SystemExit(0 if decision.allowed else 1)
    try:
        result = rotate_epoch(os.environ.get(args.dsn_env, ""), args.epoch)
    except (ValueError, psycopg.Error, ProtocolError) as exc:
        reason = getattr(exc, "reason", None) or "invalid"
        raise SystemExit(f"epoch rotation refused; admission remains disabled: {reason}") from None
    print(json.dumps(result))


if __name__ == "__main__":
    main()
