"""SPEC-063 v3 invocation coordinator: register -> dispatch -> durably accept.

This is the agent-side invocation boundary for one approved mutating call when
durable admission is enabled. It is deliberately narrow and never authoritative
about remote effects:

* It registers the immutable intent in-lane **before** any byte reaches the
  worker (R-4 enforcement order #6), so a crash between register and send leaves
  a bounded registered-but-unclaimed uncertainty rather than a silent no-op.
* Raw worker output leaves the boundary only as a ``VerifiedOriginal`` — the
  coordinator never reconstructs, caches, or re-derives a result.
* An exception is **never** proof the target did not act. A failure after a
  possible send is uncertainty; only a positively-evidenced pre-dispatch refusal
  is reported as blocked/not-dispatched.
* A secret-release permit is minted only from a durably accepted original
  successful response on a non-stopped run (R-4). ``status: success`` alone is
  insufficient, and the permit is single-use and never persisted here.

The coordinator is inert unless the caller passes a bound ``RunGuard``; the
legacy (admission-disabled) path never reaches it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_service.services.execution_protocol import ProtocolError, VerifiedOriginal, observation
from agent_service.services.execution_worker_client import handoff_original

# Reasons that can arise only before any byte reaches the worker: the target
# provably did not act, so the run stops with a positively-evidenced refusal and
# the recovery projection may scope ``not_dispatched`` to this submission.
_PRE_DISPATCH = frozenset({
    "gateway_not_configured", "credential_missing", "args_digest_mismatch",
    "bad_request", "signing_unavailable", "signature_invalid",
    "protocol_unsupported", "lifetime_invalid", "epoch_mismatch",
    "admission_disabled", "request_expired", "request_not_yet_valid",
    "identity_conflict", "request_missing", "predecessor_unresolved",
    "schema_invalid",
})
# Reasons that arise at or after a possible send, or from a failed durable
# completion: the outcome is unknown and must never be reported as no-effect.
_UNCERTAIN = frozenset({
    "transport_error", "response_invalid", "metadata_replay",
    "receipt_unconfirmed", "result_persistence_unconfirmed",
    "claim_commit_unconfirmed", "send_lock_unavailable", "store_unavailable",
    "shutdown", "integrity_conflict",
})


def agent_observation_kind(reason: str) -> str:
    """Map a closed reason_code to the agent observation kind for a stop.

    Only the four agent-authored stop kinds are producible here
    (``wait_expired``, ``transport_uncertain``, ``pre_dispatch_refused``,
    ``run_stopped``); ``response_accepted`` is minted inside ``accept``.
    """
    if reason == "wait_expired":
        return "wait_expired"
    if reason == "run_stopped":
        return "run_stopped"
    if reason in _UNCERTAIN:
        return "transport_uncertain"
    return "pre_dispatch_refused"


def is_uncertain(reason: str) -> bool:
    """True when the reason means the remote outcome is unknown."""
    return reason == "wait_expired" or reason in _UNCERTAIN


@dataclass(frozen=True)
class InvocationOutcome:
    """The coordinator's structured result for one mutating invocation."""

    # ``original`` (a validated durable worker result), ``uncertain`` (outcome
    # unknown after a possible send), or ``blocked`` (positively refused before
    # dispatch, or the run was already stopped).
    status: str
    # The validated original tool result; only set for ``original``.
    result: dict | None
    # A single-use secret-release permit; only set for an ``original`` success.
    permit: Any | None
    # The closed reason_code for ``uncertain``/``blocked``; ``None`` otherwise.
    reason: str | None
    # Whether the run latch/durable stop was set on this invocation.
    stopped: bool
    # Process-local original evidence; never placed in a tool frame or stored.
    original: VerifiedOriginal | None = field(default=None, repr=False)


async def coordinate_v3_invocation(
    *,
    guard,
    envelope: dict,
    arguments: dict,
    delegated_token: str | None,
    settings: Any,
    attempt_request_id: str,
    current_request_id: str,
) -> InvocationOutcome:
    """Register, dispatch, and durably accept one approved mutating call.

    ``guard`` is the turn's bound ``RunGuard`` (carrying the recovery store and
    the shared run latch). On success the validated original result is returned
    with a secret-release permit when the tool reported success. On any protocol
    failure the run latch is set first and the durable stop is attempted second
    (R-4 enforcement order #1/#2), an attributed agent observation is appended
    when one can be built, and a blocked/uncertain outcome is returned — never a
    claim that the target did not act when a send may have occurred.
    """
    key = getattr(settings, "execution_signing_key", None)
    try:
        # 1. Consult the stop before dispatch (R-4 enforcement order #3).
        guard.ensure_not_stopped()
        # 2. Register the immutable intent in-lane before any send.
        guard.recovery.register(envelope, attempt_request_id)
        # 3. Dispatch; raw output returns only as a VerifiedOriginal.
        original = await handoff_original(
            envelope, arguments, delegated_token, settings, attempt_request_id
        )
        # 4. Durably accept, then mint the single-use secret-release permit.
        permit = guard.release_permit(envelope, original, current_request_id)
    except ProtocolError as exc:
        return _stop_and_report(guard, envelope, exc.reason, key,
                                attempt_request_id, current_request_id)
    result = original.result
    # A permit authorizes secret release only for a successful gated write; a
    # validated tool failure is still durably accepted (above) but releases
    # nothing. The unused permit object is simply discarded.
    return InvocationOutcome(
        status="original",
        result=result,
        permit=permit if result.get("status") == "success" else None,
        reason=None,
        stopped=False,
        original=original,
    )


def _stop_and_report(
    guard, envelope, reason, key, attempt_request_id, current_request_id
) -> InvocationOutcome:
    """Set the latch, attempt the durable stop, and classify the outcome."""
    kind = agent_observation_kind(reason)
    fact = None
    if kind != "run_stopped":
        # An attributed observation binds the stop to this exact intent. If it
        # cannot be built (e.g. a non-v3 envelope), fall back to a bare stop so
        # the latch still fails closed rather than skipping the stop entirely.
        try:
            fact = observation(
                envelope, source="agent", kind=kind,
                attempt_request_id=attempt_request_id,
                current_request_id=current_request_id,
                key=key, reason=reason,
            )
        except ProtocolError:
            fact = None
    if fact is not None:
        guard.durable_stop(reason, envelope=envelope, fact=fact)
    else:
        guard.durable_stop(reason)
    return InvocationOutcome(
        status="uncertain" if is_uncertain(reason) else "blocked",
        result=None,
        permit=None,
        reason=reason,
        stopped=True,
    )
