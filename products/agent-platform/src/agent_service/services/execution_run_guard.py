"""Synchronous run-stop latch, persistent run identity, and typed secret-release permits.

SPEC-063 R-4. The authoritative run stop is durable in Postgres
(:meth:`ExecutionRecovery.stop_run`), but a mutation check must fail closed
*synchronously* at the invocation boundary — before the kernel yields any result
or event — even when the durable stop write has not landed or the store is
unavailable. This module owns three things:

* the process-local **monotonic** stop latch. It is only ever set, never reset
  within a process; a restart clears it and the durable stop stays authoritative
  (re-read from the database), so a stopped run can never be laundered back into
  a clean one by an in-process gap.
* **persistent root-run identity** binding (run/session/owner). A new human root
  mints a run; a restore must rebind its existing UUID. This module never remints
  a restored identity.
* the **single-use, PID-bound, non-serializable** secret-release permit, minted
  only from a verified original durable success on a non-stopped run.

None of this is dispatch authority. The worker's committed claim remains the only
dispatch permit, and a permit here never reconstructs tool output — it authorizes
revealing an already-held delivery handle whose value lives in the gateway, not
here. A permit is not proof of a business effect.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
import os
import threading

from agent_service.services.execution_protocol import ProtocolError, VerifiedOriginal

# The guard bound to the in-flight turn, set by the runtime kernel around each
# streamed mutation (mirroring EXECUTION_REQUESTS). ``None`` for read-only turns
# and every non-execution path, so all enforcement points below stay inert and
# existing behavior is byte-identical until the kernel binds a guard.
CURRENT_RUN_GUARD: ContextVar["RunGuard | None"] = ContextVar(
    "CURRENT_RUN_GUARD", default=None,
)


def current_guard() -> "RunGuard | None":
    return CURRENT_RUN_GUARD.get()


class RunStopLatch:
    """Process-local, monotonic run-stop marks keyed by ``run_id``.

    Deliberately unbounded and never evicting: forgetting a stop would let a
    later synchronous check wrongly pass, which is the exact failure this latch
    exists to prevent. Growth is bounded by the number of distinct runs stopped
    in one process lifetime (a UUID plus a short closed-vocabulary reason each),
    which is small relative to the safety it buys. Durability across restarts is
    the database's job, not this latch's.
    """

    def __init__(self) -> None:
        self._marks: dict[str, str] = {}
        self._lock = threading.Lock()

    def mark(self, run_id, reason) -> None:
        """Record a stop. Monotonic: the first reason for a run is retained."""
        if not run_id:
            return
        with self._lock:
            self._marks.setdefault(str(run_id), reason or "run_stopped")

    def reason(self, run_id):
        with self._lock:
            return self._marks.get(str(run_id))

    def is_stopped(self, run_id) -> bool:
        with self._lock:
            return str(run_id) in self._marks


# One latch per process, shared by every RunGuard so a stop set on any stream is
# visible to every later mutation check in the same process. Injected in tests.
_PROCESS_LATCH = RunStopLatch()


def process_latch() -> RunStopLatch:
    return _PROCESS_LATCH


_PERMIT_AUTHORITY = object()


class SecretReleasePermit:
    """Single-use authority to reveal one already-held delivery for one execution.

    Minted only by :meth:`RunGuard.release_permit` from a verified original
    durable success on a non-stopped run. It carries no secret material and
    cannot reconstruct output. Consuming it twice, in another process, or after
    any serialization/copy attempt is impossible by construction — mirroring the
    worker's ``DispatchPermit`` and the agent's ``VerifiedOriginal``.
    """

    __slots__ = ("_run_id", "_execution_id", "_receipt_digest", "_consumed", "_pid")

    def __init__(self, authority, run_id, execution_id, receipt_digest) -> None:
        if authority is not _PERMIT_AUTHORITY:
            raise TypeError(
                "secret-release permits require a verified original durable success"
            )
        self._run_id, self._execution_id = str(run_id), str(execution_id)
        self._receipt_digest = receipt_digest
        self._consumed = False
        self._pid = os.getpid()

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def execution_id(self) -> str:
        return self._execution_id

    @property
    def receipt_digest(self):
        return self._receipt_digest

    @property
    def consumed(self) -> bool:
        return self._consumed

    def consume(self) -> None:
        """Burn the permit exactly once, in the minting process only."""
        if self._pid != os.getpid():
            raise TypeError("secret-release permit cannot cross a process boundary")
        if self._consumed:
            raise TypeError("secret-release permit is single-use")
        self._consumed = True

    def __reduce__(self):
        raise TypeError("secret-release permit cannot be serialized")

    def __copy__(self):
        raise TypeError("secret-release permit cannot be copied")

    def __deepcopy__(self, memo):
        raise TypeError("secret-release permit cannot be copied")


@dataclass(frozen=True)
class RunIdentity:
    """Persistent root-run identity that survives park/resume and restore."""

    run_id: str
    session_id: str
    owner_user_id: str


class RunGuard:
    """Binds a persistent run identity to the synchronous latch and durable stop.

    ``recovery`` is an :class:`ExecutionRecovery` (or ``None`` for a purely local
    guard). ``latch`` is injectable for tests and defaults to the process latch.
    The guard is the *agent-side* enforcement point described in R-4: it never
    dispatches, never returns raw output, and never mints a permit without a
    durable accepted original success.
    """

    def __init__(self, identity, *, recovery=None, latch=None) -> None:
        if not isinstance(identity, RunIdentity):
            raise TypeError("run guard requires a persistent RunIdentity")
        self._identity = identity
        self._recovery = recovery
        self._latch = latch if latch is not None else _PROCESS_LATCH

    @property
    def identity(self) -> RunIdentity:
        return self._identity

    @property
    def run_id(self) -> str:
        return self._identity.run_id

    @property
    def recovery(self):
        return self._recovery

    def stopped(self) -> bool:
        """Non-raising synchronous stop check for permission/evidence seams."""
        return self._latch.reason(self._identity.run_id) is not None

    def ensure_not_stopped(self) -> None:
        """Synchronous, DB-free fail-closed check for the invocation boundary.

        Consulted before the ``ALLOWED`` shortcut, before flow signing, in the
        mutating closure, and again immediately before a secret emission. The
        durable stop is separately re-checked by the worker at claim/final send;
        this latch is the in-process half that also covers a stop whose durable
        write has not landed.
        """
        if self.stopped():
            raise ProtocolError("run_stopped")

    def mark_stopped(self, reason) -> None:
        self._latch.mark(self._identity.run_id, reason)

    def durable_stop(self, reason, *, envelope=None, fact=None) -> bool:
        """Set the local latch first (fail closed), then attempt the durable stop.

        Returns ``True`` only when the durable monotonic stop is acknowledged. On
        store/lock failure the latch stays set and ``False`` is returned: the run
        is blocked in-process, and the durable stop is idempotently retried by a
        later call or re-read from database state after a restart. The local
        latch is set *before* the write so a crash mid-stop still fails closed.
        """
        self.mark_stopped(reason)
        if self._recovery is None:
            return False
        try:
            self._recovery.stop_run(
                self._identity.run_id,
                self._identity.session_id,
                self._identity.owner_user_id,
                reason=reason,
                envelope=envelope,
                fact=fact,
            )
            return True
        except ProtocolError:
            # Keep the latch set; the durable stop is unconfirmed, not undone.
            return False

    def release_permit(self, envelope, original, current_request_id) -> SecretReleasePermit:
        """Mint the single-use secret-release permit from a verified original success.

        Fails closed unless every one of these holds:

        1. the run is not locally stopped;
        2. a durable recovery store is present (no store, no durable acceptance,
           no permit — a local-only guard cannot authorize a reveal);
        3. ``original`` is a same-process :class:`VerifiedOriginal`, never a dict,
           recovery page, or ``status: success`` frame;
        4. durable agent acceptance of the exact recorded worker result succeeds
           on a non-stopped, non-conflicting run.

        The returned permit authorizes revealing an already-held handle only. It
        is not proof of a business effect and carries no output.
        """
        self.ensure_not_stopped()
        if self._recovery is None:
            raise ProtocolError("receipt_unconfirmed")
        if not isinstance(original, VerifiedOriginal):
            raise ProtocolError("response_invalid")
        # accept() revalidates the original, binds the exact receipt digest, and
        # re-checks the durable run stop and integrity; it raises before we mint
        # anything if the result is not a durably accepted original success.
        self._recovery.accept(envelope, original, current_request_id)
        receipt_digest = original.observation["receipt_digest"]
        return SecretReleasePermit(
            _PERMIT_AUTHORITY,
            self._identity.run_id,
            envelope["execution_id"],
            receipt_digest,
        )


def bind_run(recovery, session_id, owner_user_id, *, run_id=None) -> RunGuard:
    """Bind persistent run identity for a turn.

    A genuinely new human root passes ``run_id=None`` and mints a durable run.
    A restore/resume MUST pass its existing ``run_id``; this helper never
    remints a restored identity, and the caller is responsible for failing
    closed when a session's persisted run identity is missing.
    """
    if run_id is None:
        run_id = recovery.create_run(session_id, owner_user_id)
    return RunGuard(
        RunIdentity(str(run_id), session_id, owner_user_id), recovery=recovery
    )
