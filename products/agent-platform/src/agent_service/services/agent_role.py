"""Role-scoped agent authority (SPEC-073 substrate, bound live in-process by SPEC-076 phase 5).

A closed, platform-owned **agent-role** vocabulary that narrows a sub-agent's
toolkit authority while every role rides the **same** gateway-forwarded
delegated token (ADR-0004). A role is an authority-narrowing label on the one
token — never a new credential, a per-role broker identity, a second identity
edge, or a new principal (ADR-0017 Decision 4).

The role is **process-local context** beside ``DELEGATED_TOKEN``: it is set by
the kernel around a role-scoped turn and read at toolkit-build time, is never
part of the SPEC-017 resumable snapshot, and never becomes a JWT claim, a
forwarded header, or any wire field in phase 2 (R-3, OQ-2). Like SPEC-070's
``VerifiedHuman`` it is deliberately ephemeral and re-derived per turn.

SPEC-073 (phase 2) shipped this **inert**; SPEC-076 (phase 5) binds it live
**in-process** — the bounded read-only orchestration loop brackets its
orchestrator/diagnostician/executor turns in :func:`agent_role_scope`, while the
deployed **unscoped** single-agent turn still binds no role and stays
byte-identical (R-5). The bound role still never crosses the wire: SPEC-073 R-3
keeps it off every JWT claim, forwarded header, and wire field, so it becomes a
wire contract only in phase 6.

No agentscope type appears anywhere in this module (SPEC-018 gate point 4).
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from enum import Enum
from collections.abc import Iterator


class AgentRole(str, Enum):
    """The closed, platform-owned agent-role vocabulary (SPEC-073 R-1).

    Exactly three values. ``ORCHESTRATOR`` collapses ADR-0017 Decision 4's
    "`planner`/`orchestrator`" into one role (OQ-1): at the toolkit layer the
    two are indistinguishable — both hold no mutation authority and no direct
    tools. A closed enum grows additively if phase 5's bounded loop ever needs
    to separate planning from delegation.

    There is deliberately **no ``approver`` role**: ADR-0017 Decision 2 fixes
    the approver as a *distinct human, never an agent*, so an approver-facing
    agent role would contradict the diagnose-before-act autonomy ceiling.

    The values are plain lowercase platform strings; a role reduces to its
    ``.value`` on any serialized surface with no agentscope import (R-1).
    """

    DIAGNOSTICIAN = "diagnostician"
    ORCHESTRATOR = "orchestrator"
    EXECUTOR = "executor"


class AgentRoleError(ValueError):
    """Raised when a role outside the closed set is bound.

    Fail-closed (R-1/R-5): an unknown or malformed role is rejected, never
    coerced to a wider posture. The message is a stable code so it can be
    matched in tests without asserting on human prose.
    """

    def __init__(self) -> None:
        super().__init__("agent_role_invalid")


# Process-local role context (OQ-2): set by the kernel around a role-scoped
# turn, read at toolkit-build time. Default ``None`` means an unscoped turn —
# today's single-agent path — which is never narrowed and stays byte-identical.
AGENT_ROLE: ContextVar[AgentRole | None] = ContextVar("AGENT_ROLE", default=None)


def coerce_agent_role(value: object) -> AgentRole:
    """Resolve ``value`` to an :class:`AgentRole`, failing closed (R-1/R-5).

    Accepts an :class:`AgentRole` or its exact string value. Anything else —
    ``None``, an unknown string, a non-string, or a model/tool-supplied value
    outside the closed set — raises :class:`AgentRoleError` rather than
    defaulting to a wider posture.
    """
    if isinstance(value, AgentRole):
        return value
    if isinstance(value, str):
        try:
            return AgentRole(value)
        except ValueError:
            raise AgentRoleError() from None
    raise AgentRoleError()


def current_agent_role() -> AgentRole | None:
    """The role bound to the current turn, or ``None`` when unscoped."""
    return AGENT_ROLE.get()


def current_agent_role_value() -> str | None:
    """The bound role's plain platform string, or ``None`` when unscoped.

    The serialized form used for kernel-internal provenance (R-4); never an
    agentscope type and never a wire field (SPEC-073 R-3 — the wire contract is
    phase 6).
    """
    role = AGENT_ROLE.get()
    return role.value if role is not None else None


@contextmanager
def agent_role_scope(value: object) -> Iterator[AgentRole]:
    """Bind a role for the enclosed turn, then restore the prior context.

    The bracket mirrors the kernel's ``DELEGATED_TOKEN`` set/reset: it touches
    **only** ``AGENT_ROLE`` — never the delegated token and never the SPEC-070
    ``REQUESTER_IDENTITY``/``DECIDER_IDENTITY`` — so a member agent acts *as the
    same human* with a narrowed toolkit, never as a distinct principal (R-3).
    The role is fixed for the whole scope and cannot be widened from inside it
    (R-1); an out-of-set value fails closed before the scope opens.
    """
    resolved = coerce_agent_role(value)
    token = AGENT_ROLE.set(resolved)
    try:
        yield resolved
    finally:
        AGENT_ROLE.reset(token)
