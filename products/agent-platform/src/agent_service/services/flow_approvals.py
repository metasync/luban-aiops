"""Session-scoped browser-flow authority and context (SPEC-051 R-1/R-2/R-6).

Two per-process, session-scoped stores back the platform-enforced flow-unlock
that completes SPEC-049 R-4 — one HITL gate per mutating browser flow:

- ``FLOW_CONTEXTS`` is the kernel's *reflection* of the gateway-owned flow
  binding. The tool-gateway binds a flow on ``web.navigate`` and rides it back
  on ``data["flow"]``; the kernel records that dict here as running state
  (``FlowContext``). It is the single source for two consumers: the R-6 card
  headline and the R-1 flow *identity* (``skill_id`` + ``origin``) the unlock
  authority is scoped to. The gateway still owns and enforces the flow
  (deviation guard: origin allowlist, ``risk_class``, step budget); this is a
  reflection, not ownership (ADR-0007).

- ``FLOW_APPROVALS`` records the operator's approval of a mutating flow's
  first parked write. Subsequent ``web.*`` writes in the *same* flow are
  admitted and auto-signed under that authority — but only while
  ``FLOW_CONTEXTS`` still matches the approved identity. A rebind to a
  different flow overwrites the context, the identity no longer matches, and
  the next write re-parks: this is what eliminates the ADR-0007 cross-flow
  trade-off rather than merely bounding it. The authority is TTL-bounded
  (``AGENT_BROWSER_FLOW_APPROVAL_TTL``); ``0`` disables flow-unlock entirely
  (every write parks — the pre-fix posture).

Both stores are deliberately in-memory and per-process, mirroring
``CONFIRMATION_REGISTRY``: nothing survives a restart. A dropped context or
authority fails *safe* — the next browser write re-parks for a fresh operator
decision and the card re-renders tool-level. Neither store ever auto-runs a
write on its own; it only unlocks the kernel's own auto-signing path, and the
tool-gateway deviation guard still bounds every unlocked invocation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

# Browser tools that mutate (write tier) and therefore ride the flow-unlock
# path. Dotted gateway canonical names; the kernel matches a parked/asked
# tool's ``gateway_tool_name`` against this set. ``web.evaluate`` is included
# because arbitrary JS can mutate the DOM (SPEC-050) — it inherits the
# write-tier gate. Read-tier ``web.*`` probes are auto-allowed separately and
# never reach the flow-unlock branch.
BROWSER_WRITE_TOOLS = frozenset({
    "web.click",
    "web.type",
    "web.select",
    "web.press_key",
    "web.upload_file",
    "web.evaluate",
})


@dataclass
class FlowContext:
    """The kernel's reflection of the gateway-owned flow binding (R-1/R-6).

    Updated from each successful ``web.navigate`` result's ``data["flow"]``.
    ``skill_id`` + ``origin`` form the flow *identity* the unlock authority is
    scoped to; ``title``/``description``/``risk_class`` feed the R-6 card
    headline; ``steps_used``/``max_steps`` mirror the gateway step budget for
    observability (the gateway, not the kernel, enforces it).
    """

    session_id: str
    skill_id: str
    origin: str
    title: str = ""
    description: str = ""
    risk_class: str = "read"
    steps_used: int = 0
    max_steps: int = 0
    observed_at: float = field(default_factory=time.monotonic)

    def identity(self) -> tuple[str, str]:
        """The flow identity (``skill_id``, ``origin``) the authority keys on."""
        return (self.skill_id, self.origin)

    def summary(self) -> dict[str, object]:
        """The card-level flow headline payload (R-6).

        Carried on the confirmation-request frame as ``flow_summary`` and on
        the parked confirmation as ``browser_flow``; the portal renders it
        above the per-call tool detail. Empty title/description are kept as
        empty strings so the portal can fall back gracefully.
        """
        return {
            "skill_id": self.skill_id,
            "origin": self.origin,
            "title": self.title,
            "description": self.description,
            "risk_class": self.risk_class,
        }


class FlowContextStore:
    """Per-process map of ``session_id`` -> the live ``FlowContext``.

    At most one flow context per session: ``record`` overwrites unconditionally
    with the latest ``web.navigate`` flow dict, so a rebind to a different
    skill/origin replaces the identity — exactly how the R-1 identity guard
    detects a flow change and re-parks the next write.
    """

    def __init__(self) -> None:
        self._by_session: dict[str, FlowContext] = {}

    def record(self, session_id: str, flow: dict) -> FlowContext:
        """Record (overwrite) the session's flow context from a flow dict.

        ``flow`` is the gateway's ``data["flow"]`` (``FlowState.to_dict()``).
        Missing keys degrade to safe defaults rather than raising — a partial
        flow dict still yields a usable identity and an empty headline.
        """
        context = FlowContext(
            session_id=session_id,
            skill_id=str(flow.get("skill_id") or ""),
            origin=str(flow.get("origin") or ""),
            title=str(flow.get("title") or ""),
            description=str(flow.get("description") or ""),
            risk_class=str(flow.get("risk_class") or "read"),
            steps_used=_as_int(flow.get("steps_used")),
            max_steps=_as_int(flow.get("max_steps")),
        )
        self._by_session[session_id] = context
        return context

    def get(self, session_id: str) -> FlowContext | None:
        return self._by_session.get(session_id)

    def clear(self, session_id: str) -> None:
        self._by_session.pop(session_id, None)

    def clear_all(self) -> None:
        self._by_session.clear()


@dataclass
class FlowApproval:
    """A recorded operator approval of one mutating flow (R-1/R-2).

    ``confirm_id``/``owner_user_id``/``decider_user_id`` come from the parked
    card the operator approved, so every auto-signed write under this
    authority reuses the approving card's correlation and identity (ADR-0007).
    ``skill_id``/``origin`` are the *approved flow identity* captured from the
    card's ``browser_flow`` (R-6); the unlock only holds while they still match
    the live ``FlowContext``. ``ttl`` is captured at record time so ``get`` can
    honor expiry without the caller threading the setting through every lookup.
    """

    session_id: str
    confirm_id: str
    owner_user_id: str
    decider_user_id: str
    skill_id: str
    origin: str
    ttl: float
    approved_at: float = field(default_factory=time.monotonic)

    def is_expired(self) -> bool:
        """True when the authority no longer unlocks writes.

        ``ttl <= 0`` disables flow-unlock (every write parks — the pre-fix
        posture), so it is always expired. Otherwise the authority lapses
        ``ttl`` seconds after approval (monotonic).
        """
        if self.ttl <= 0:
            return True
        return (time.monotonic() - self.approved_at) > self.ttl

    def identity(self) -> tuple[str, str]:
        """The approved flow identity (``skill_id``, ``origin``)."""
        return (self.skill_id, self.origin)


class FlowApprovalStore:
    """Per-process map of ``session_id`` -> the live ``FlowApproval``.

    At most one flow authority per session. ``get`` honors the captured TTL and
    returns ``None`` for an expired authority, so a lapse fails safe (the next
    write re-parks). Expired entries are not eagerly evicted — a subsequent
    ``record`` overwrites them and ``clear``/``clear_all`` drop them.
    """

    def __init__(self) -> None:
        self._by_session: dict[str, FlowApproval] = {}

    def record(
        self,
        session_id: str,
        confirm_id: str,
        owner_user_id: str,
        decider_user_id: str,
        skill_id: str,
        origin: str,
        ttl: float,
    ) -> FlowApproval:
        approval = FlowApproval(
            session_id=session_id,
            confirm_id=confirm_id,
            owner_user_id=owner_user_id,
            decider_user_id=decider_user_id,
            skill_id=skill_id,
            origin=origin,
            ttl=ttl,
        )
        self._by_session[session_id] = approval
        return approval

    def get(self, session_id: str) -> FlowApproval | None:
        """Return the session's unexpired authority, or ``None``.

        ``None`` covers both "no approval recorded" and "approval expired"
        (TTL lapse or ``ttl <= 0`` disable) — either way the caller must
        fail safe and let the write park.
        """
        approval = self._by_session.get(session_id)
        if approval is None or approval.is_expired():
            return None
        return approval

    def has_approval(self, session_id: str) -> bool:
        """True when the session holds an unexpired flow authority (R-2)."""
        return self.get(session_id) is not None

    def clear(self, session_id: str) -> None:
        self._by_session.pop(session_id, None)

    def clear_all(self) -> None:
        self._by_session.clear()


def _as_int(value: object) -> int:
    """Coerce a flow-dict numeric field to ``int``, defaulting to ``0``."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


# Process-wide singletons shared by the runtime kernel and its middleware.
# Tests may clear them between cases; production code never replaces them.
FLOW_CONTEXTS = FlowContextStore()
FLOW_APPROVALS = FlowApprovalStore()
