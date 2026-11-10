"""Bounded read-only orchestration loop (SPEC-076 phase 5).

The **producer** that first *binds* the agent-roles SPEC-073 (v0.54.0),
SPEC-074 (v0.55.0), and SPEC-075 (v0.56.0) each landed **inert**. A
platform-owned ``orchestrator`` decomposes a diagnosis goal into a **bounded**
fan-out of read-only ``diagnostician`` member turns over the *existing*
``reply_text(..., read_only=True)`` seam (SPEC-015) and the *same* delegated
token (ADR-0004 — exactly one broker exchange per user), then synthesizes a
diagnosis from the member **summaries** alone (memo §3.1).

This is the **controlled relaxation of ADR-0011 Decision 3** and it is admitted
**only** where every step is read-only:

- the loop is **bounded** by ``AGENT_ORCHESTRATION_MAX_STEPS`` — a deliberate
  twin of the tool-gateway's ``GATEWAY_BROWSER_FLOW_MAX_STEPS`` (default ``20``,
  validated ``>= 1``) — counting **total member read steps per orchestration**
  (not per member), so the fan-out cannot grow unbounded regardless of member
  count (OQ-2);
- on exhaustion the loop **fails closed** to a budget-limited *partial*
  diagnosis: it stops, synthesizes best-effort from the summaries gathered, and
  never widens to a mutating step to "finish" (R-1);
- each member rides the **same** gateway-forwarded delegated token the
  orchestrator holds — no per-role broker mint, no second identity edge, and the
  role stays process-local (never a JWT claim, forwarded header, or wire field,
  R-3);
- the loop is **read-only**: a ``diagnostician`` toolkit carries no mutating tool
  (SPEC-073 R-2 ``_narrow_for_role``), so a member step that would mutate is
  structurally impossible inside the loop. Any remediation the diagnosis
  proposes is *staged* separately by an ``executor`` onto the existing HITL +
  signed-dispatch path (R-4) — never dispatched from inside the loop.

**No agentscope orchestration/pipeline type is imported or constructed here**
(``TeamPipeline`` / ``GoalPipeline`` / ``A2AAgent`` are kept out by ADR-0017
Decision 5); a guard test asserts the loop is platform-owned (gate point 4).

The deployed **unscoped** single-agent chat path is untouched: this module is the
*only* caller that opens an ``agent_role_scope()``, so the SPEC-073 (in-process
binding) and SPEC-075 (audit attribution) R-5 reachability guards now read "only the
orchestration frame binds a role". The SPEC-074 gateway-axis R-5 guard is unchanged
and still passes: the bound role never crosses the wire (R-3), so no deployed gateway
``evaluate()`` threads a non-``None`` role and the canonical ``agent_roles_any`` rules
stay ready-but-inert — the live read-only control is ``_narrow_for_role`` plus the
loop's ``read_only=True`` admission (R-8 point 3 / OQ-4).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from agent_service.services.agent_role import AgentRole, agent_role_scope

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MemberStep:
    """One declared read-only diagnostic sub-goal in a profile's fan-out.

    A member step is a single bounded ``diagnostician`` turn: the loop counts it
    as **one** step against ``AGENT_ORCHESTRATION_MAX_STEPS``, while the turn's
    own tool calls stay bounded by the per-turn ``AGENTSCOPE_MAX_ITERS`` (the
    two-level bound, OQ-2). ``prompt`` is the read-only instruction; the loop
    composes it with the diagnosis goal — it never names a mutating action.
    """

    task_id: str
    prompt: str


@dataclass(frozen=True)
class DiagnosisProfile:
    """A runbook-agnostic declaration of one detect→troubleshoot→propose flow.

    The bounded-diagnosis **capability** is built once (OQ-7); each of the four
    operator-named runbooks (memo §8 Q5) is expressed as a profile — its trigger,
    its read-only ``diagnostician`` toolkit families, the ordered member steps of
    its fan-out, and the *shape* of the remediation it may propose. The
    ``diagnostician`` toolkit itself is narrowed by risk tier + token ``roles``
    (SPEC-073 R-2), **not** by runbook family; ``read_families`` is declarative
    documentation of the families a runbook intends to read — it shapes neither
    the member prompt (composed from ``step.prompt`` alone) nor the toolkit.
    """

    name: str
    trigger: str
    read_families: tuple[str, ...]
    steps: tuple[MemberStep, ...]
    remediation_shape: str | None = None


@dataclass(frozen=True)
class MemberSummary:
    """What the orchestrator is allowed to see from one member (memo §3.1).

    Only the member's synthesized ``summary`` crosses back to the leader — never
    its intermediate tool steps. Member activity is nonetheless reconstructable
    from the durable evidence/audit record with role attribution (R-6).
    """

    task_id: str
    summary: str


@dataclass(frozen=True)
class DiagnosisResult:
    """The bounded loop's outcome: a synthesized diagnosis + its provenance.

    ``budget_limited`` is ``True`` when the step budget was exhausted before every
    declared member step ran, so the diagnosis is a best-effort **partial** result
    (R-1 fail-closed). ``steps_used`` counts member read steps only; the
    orchestrator's synthesis turn holds no gateway tools and is not a read step.
    """

    profile: str
    goal: str
    diagnosis: str
    member_summaries: tuple[MemberSummary, ...]
    steps_used: int
    budget: int
    budget_limited: bool


def _member_prompt(goal: str, step: MemberStep) -> str:
    """Compose one ``diagnostician`` member turn's read-only instruction."""
    return (
        "Autonomous read-only diagnosis step (no human approves any read; you "
        "may not mutate anything).\n"
        f"Diagnosis goal: {goal}\n"
        f"Your task: {step.prompt}\n"
        "Use only read-level tools. Report concisely what you observed and what "
        "it implies for the goal. Do not propose or attempt any mutation."
    )


def _synthesis_prompt(
    goal: str,
    profile: DiagnosisProfile,
    summaries: Sequence[MemberSummary],
    budget_limited: bool,
) -> str:
    """Compose the ``orchestrator`` synthesis turn from member summaries only.

    The orchestrator sees **only** the summaries (memo §3.1), never member
    intermediate steps, and holds no gateway tools (SPEC-073 R-2). When the
    budget was exhausted the prompt asks for an explicitly budget-limited partial
    diagnosis rather than pretending the fan-out completed.
    """
    lines = [
        "You are the orchestrator synthesizing a bounded read-only diagnosis.",
        f"Diagnosis goal: {goal}",
        f"Runbook profile: {profile.name}",
    ]
    if budget_limited:
        lines.append(
            "NOTE: the orchestration step budget was exhausted before every "
            "declared member step ran. Produce a best-effort PARTIAL diagnosis "
            "and state clearly that it is budget-limited. Do not request or "
            "assume any further (mutating) step to finish."
        )
    lines.append(
        "Member summaries (you see only these summaries, not member intermediate "
        "steps):"
    )
    if summaries:
        for summary in summaries:
            lines.append(f"- [{summary.task_id}] {summary.summary}")
    else:
        lines.append("- (no member summaries were gathered)")
    lines.append(
        "Synthesize a single coherent diagnosis. If a remediation is warranted, "
        "describe it strictly as a PROPOSAL — you cannot and must not execute any "
        "mutation; a distinct human approves any staged remediation."
    )
    return "\n".join(lines)


async def run_bounded_diagnosis(
    kernel,
    *,
    profile: DiagnosisProfile,
    goal: str,
    session_id: str,
    user_name: str,
    bearer_token: str | None,
    model_id: str | None = None,
    max_steps: int | None = None,
) -> DiagnosisResult:
    """Run one bounded read-only orchestration and return its diagnosis.

    The loop fans out ``profile.steps`` as ``diagnostician`` read-only turns over
    the existing ``reply_text(..., read_only=True)`` seam, each wrapped in
    ``agent_role_scope(AgentRole.DIAGNOSTICIAN)``, then synthesizes the diagnosis
    as an ``orchestrator`` (no gateway tools). Every member rides the **same**
    ``bearer_token`` (R-3): no member mints or requests a second broker token.

    ``max_steps`` overrides the configured ``AGENT_ORCHESTRATION_MAX_STEPS``
    budget (tests); it defaults to the kernel's setting. The budget counts
    **total member read steps per orchestration**; on exhaustion the loop fails
    closed to a budget-limited partial diagnosis and never widens to a mutating
    step (R-1/OQ-2). Each member turn runs on its own derived session id so
    member memory never crosses and the leader sees only summaries (memo §3.1).

    No agentscope orchestration/pipeline type is constructed on this path
    (ADR-0017 Decision 5).
    """
    budget = (
        max_steps
        if max_steps is not None
        else kernel.settings.orchestration_max_steps
    )
    if budget < 1:
        # Fail closed: a non-positive budget is a misconfiguration, not a licence
        # to run unbounded. Mirrors the startup validation in runtime_settings.
        raise ValueError("AGENT_ORCHESTRATION_MAX_STEPS must be >= 1.")

    summaries: list[MemberSummary] = []
    steps_used = 0
    budget_limited = False

    for step in profile.steps:
        if steps_used >= budget:
            budget_limited = True
            LOGGER.info(
                "orchestration step budget exhausted; failing closed to a "
                "partial diagnosis",
                extra={
                    "session_id": session_id,
                    "profile": profile.name,
                    "budget": budget,
                    "steps_used": steps_used,
                    "remaining_steps": len(profile.steps) - steps_used,
                },
            )
            break
        member_session = f"{session_id}::orch::{step.task_id}"
        # SPEC-076 R-2: the orchestration frame binds the diagnostician role for
        # this member turn only; agent_role_scope touches just AGENT_ROLE and
        # restores it on exit, so the role stays process-local (SPEC-073 OQ-2) and
        # the same delegated token / requester identity is preserved (R-3).
        with agent_role_scope(AgentRole.DIAGNOSTICIAN):
            reply = await kernel.reply_text(
                message=_member_prompt(goal, step),
                session_id=member_session,
                user_name=user_name,
                bearer_token=bearer_token,
                model_id=model_id,
                read_only=True,
            )
        content, _structured = reply
        steps_used += 1
        summaries.append(MemberSummary(task_id=step.task_id, summary=content))

    diagnosis = await _synthesize(
        kernel,
        goal=goal,
        profile=profile,
        summaries=summaries,
        budget_limited=budget_limited,
        session_id=session_id,
        user_name=user_name,
        bearer_token=bearer_token,
        model_id=model_id,
    )
    return DiagnosisResult(
        profile=profile.name,
        goal=goal,
        diagnosis=diagnosis,
        member_summaries=tuple(summaries),
        steps_used=steps_used,
        budget=budget,
        budget_limited=budget_limited,
    )


async def _synthesize(
    kernel,
    *,
    goal: str,
    profile: DiagnosisProfile,
    summaries: Sequence[MemberSummary],
    budget_limited: bool,
    session_id: str,
    user_name: str,
    bearer_token: str | None,
    model_id: str | None,
) -> str:
    """Run the ``orchestrator`` synthesis turn over the member summaries."""
    prompt = _synthesis_prompt(goal, profile, summaries, budget_limited)
    # SPEC-076 R-2: the synthesizer binds the orchestrator role, whose gateway
    # toolkit is empty (it delegates, never invokes). read_only=True is belt-and-
    # braces: the orchestrator holds no tools regardless.
    with agent_role_scope(AgentRole.ORCHESTRATOR):
        reply = await kernel.reply_text(
            message=prompt,
            session_id=f"{session_id}::orch::synthesis",
            user_name=user_name,
            bearer_token=bearer_token,
            model_id=model_id,
            read_only=True,
        )
    content, _structured = reply
    return content


# ---------------------------------------------------------------------------
# R-4: diagnose-before-act — an ``executor`` stages a proposal onto the existing
# HITL card. The read-only loop above never dispatches a mutation and never binds
# this role; staging is a separate, explicitly-triggered step.
# ---------------------------------------------------------------------------
def _staging_prompt(goal: str, profile: DiagnosisProfile, diagnosis: str) -> str:
    """Compose the ``executor`` turn that *proposes* one remediation.

    The executor proposes; it never dispatches. The kernel parks the proposed
    mutating call on the existing HITL confirmation card (SPEC-020/030/031) and a
    **distinct human** approver authorizes any execution through the signed
    at-most-one-dispatch worker (SPEC-037/038/063) — the SPEC-030 self-approval
    block fires unchanged. Autonomous resolve stays deferred (ADR-0017 Decision
    2), so the prompt frames the remediation strictly as a proposal.
    """
    return (
        "You are the executor staging a PROPOSED remediation for human approval.\n"
        f"Diagnosis goal: {goal}\n"
        f"Runbook profile: {profile.name}\n"
        f"Proposed remediation shape: {profile.remediation_shape}\n"
        f"Diagnosis:\n{diagnosis}\n"
        "Propose the single mutating action that would remediate this. You cannot "
        "and must not dispatch it yourself: the proposal parks on a human-approval "
        "card, and only a distinct human approver (never you, never the original "
        "requester) may authorize execution."
    )


async def stage_remediation(
    kernel,
    *,
    profile: DiagnosisProfile,
    goal: str,
    diagnosis: str,
    session_id: str,
    user_name: str,
    bearer_token: str | None,
    model_id: str | None = None,
):
    """Stage a proposed remediation as an ``executor`` onto the existing HITL card.

    R-4 (diagnose-before-act): ``run_bounded_diagnosis`` is read-only and never
    binds the executor role. When a remediation is warranted this **separate**
    step binds ``AgentRole.EXECUTOR`` and drives **one** turn over the *same*
    ``reply_text`` seam with ``read_only=False`` so the executor's full toolkit
    (SPEC-073 R-2 ``_narrow_for_role``) can *propose* the mutating call — which
    the kernel parks as the existing SPEC-020/030/031 confirmation card, labelled
    with the SPEC-073 R-4 ``staged_by_role="executor"`` provenance (the kernel
    reads it from the bound role at park time, ``runtime_kernel`` line ~1899).

    **Zero new mutation-path code**: no new gate, worker, claim type, or schema.
    Nothing here dispatches — the park requires a **distinct human** approver and
    rides the existing signed at-most-one-dispatch worker (SPEC-037/038/063); the
    SPEC-030 self-approval block fires unchanged. The same delegated token rides
    the staging turn (R-3) and the role stays process-local. A profile with no
    declared ``remediation_shape`` has nothing to propose and fails closed rather
    than widening an executor turn.
    """
    if profile.remediation_shape is None:
        # Fail closed: a read-only profile with no declared remediation shape has
        # nothing to stage — never open an executor turn without a proposal.
        raise ValueError(
            f"profile {profile.name!r} declares no remediation_shape; "
            "there is nothing to stage."
        )
    # SPEC-076 R-4: bind the executor role for this one staging turn. Unlike the
    # read-only loop, read_only is False so the executor's full toolkit can
    # propose the mutating call — which the kernel still parks on the existing
    # HITL confirmation (never auto-dispatched) with staged_by_role="executor".
    with agent_role_scope(AgentRole.EXECUTOR):
        reply = await kernel.reply_text(
            message=_staging_prompt(goal, profile, diagnosis),
            session_id=f"{session_id}::orch::staging",
            user_name=user_name,
            bearer_token=bearer_token,
            model_id=model_id,
            read_only=False,
        )
    return reply
