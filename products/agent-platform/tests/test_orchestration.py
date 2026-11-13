"""SPEC-076 phase-5 tests: the bounded read-only orchestration loop (R-1, R-2).

These prove the platform-owned loop is **bounded** (it terminates at
``AGENT_ORCHESTRATION_MAX_STEPS`` and fails closed to a budget-limited partial
diagnosis), **read-only** (every member turn rides ``read_only=True``), binds the
correct **agent-role** per participant (``diagnostician`` members, an
``orchestrator`` synthesizer) as **process-local** context, shows the leader
**only** member summaries (memo §3.1), and constructs **no** agentscope
orchestration/pipeline type (ADR-0017 Decision 5).
"""

import asyncio
from pathlib import Path

import pytest

from agent_service.runtime_kernel import BlockingReply
from agent_service.runtime_settings import RuntimeSettings
from agent_service.schemas.v2 import EvidenceTurn
from agent_service.services.agent_role import (
    AgentRole,
    current_agent_role,
    current_agent_role_value,
)
from agent_service.services.audit_emitter import build_audit_event
from agent_service.services.delegated_identity import REQUESTER_IDENTITY
from agent_service.services.hitl_confirmations import PendingConfirmation
from agent_service.services.orchestration import (
    DiagnosisProfile,
    MemberStep,
    run_bounded_diagnosis,
    stage_remediation,
)
from agent_service.services.runbooks import (
    K8S_POD_DEGRADATION,
    OBSERVABILITY_ALERT,
    POST_DEPLOY_VERIFY,
    SERVICENOW_INCIDENT,
    all_profiles,
    diagnostician_read_families,
    get_profile,
    profile_names,
)

_ORCH_SRC = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "agent_service"
    / "services"
    / "orchestration.py"
)
_RUNBOOKS_SRC = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "agent_service"
    / "services"
    / "runbooks.py"
)
_SCHEMA_DIR = (
    Path(__file__).resolve().parents[3]
    / "shared"
    / "shared-contracts"
    / "schemas"
)


class _Call:
    def __init__(self, role, session_id, read_only, message, bearer_token):
        self.role = role
        self.session_id = session_id
        self.read_only = read_only
        self.message = message
        self.bearer_token = bearer_token


class FakeKernel:
    """Stands in for AgentKernel: records each turn and the role bound to it."""

    def __init__(self, settings):
        self.settings = settings
        self.calls: list[_Call] = []

    async def reply_text(
        self,
        *,
        message,
        session_id,
        user_name,
        bearer_token=None,
        response_schema=None,
        model_id=None,
        read_only=False,
        routing_allowed=False,
    ):
        self.calls.append(
            _Call(
                role=current_agent_role_value(),
                session_id=session_id,
                read_only=read_only,
                message=message,
                bearer_token=bearer_token,
            )
        )
        return BlockingReply(f"observed::{session_id}")

    # --- helpers -----------------------------------------------------------
    @property
    def member_calls(self):
        return [c for c in self.calls if c.role == AgentRole.DIAGNOSTICIAN.value]

    @property
    def synthesis_calls(self):
        return [c for c in self.calls if c.role == AgentRole.ORCHESTRATOR.value]


def _profile(n_steps: int) -> DiagnosisProfile:
    return DiagnosisProfile(
        name="test-profile",
        trigger="operator-invoked",
        read_families=("k8s", "observability"),
        steps=tuple(
            MemberStep(task_id=f"m{i}", prompt=f"read family {i}")
            for i in range(n_steps)
        ),
        remediation_shape=None,
    )


def _settings(**kwargs) -> RuntimeSettings:
    return RuntimeSettings(api_key="test-key", tool_gateway_url="http://gw:8080", **kwargs)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# R-1: the loop is bounded and fails closed
# ---------------------------------------------------------------------------
class TestBoundedLoop:
    def test_budget_bounds_total_member_steps_and_fails_closed(self):
        kernel = FakeKernel(_settings(orchestration_max_steps=20))
        result = _run(
            run_bounded_diagnosis(
                kernel,
                profile=_profile(5),
                goal="why is checkout slow",
                session_id="ses-1",
                user_name="alice",
                bearer_token="tok",
                max_steps=3,
            )
        )
        # Only 3 of the 5 declared member steps ran; the loop stopped at the
        # bound and marked the result budget-limited (never unbounded).
        assert result.steps_used == 3
        assert result.budget == 3
        assert result.budget_limited is True
        assert len(result.member_summaries) == 3
        assert len(kernel.member_calls) == 3
        # The synthesis still ran (best-effort partial diagnosis).
        assert len(kernel.synthesis_calls) == 1
        assert result.diagnosis.startswith("observed::")

    def test_full_fanout_within_budget_is_not_limited(self):
        kernel = FakeKernel(_settings())
        result = _run(
            run_bounded_diagnosis(
                kernel,
                profile=_profile(2),
                goal="g",
                session_id="ses-2",
                user_name="alice",
                bearer_token="tok",
            )
        )
        assert result.steps_used == 2
        assert result.budget_limited is False
        assert len(kernel.member_calls) == 2

    def test_default_budget_comes_from_settings(self):
        kernel = FakeKernel(_settings(orchestration_max_steps=1))
        result = _run(
            run_bounded_diagnosis(
                kernel,
                profile=_profile(4),
                goal="g",
                session_id="ses-3",
                user_name="alice",
                bearer_token="tok",
            )
        )
        assert result.budget == 1
        assert result.steps_used == 1
        assert result.budget_limited is True

    def test_zero_budget_fails_closed_with_error(self):
        kernel = FakeKernel(_settings())
        with pytest.raises(ValueError, match="AGENT_ORCHESTRATION_MAX_STEPS"):
            _run(
                run_bounded_diagnosis(
                    kernel,
                    profile=_profile(2),
                    goal="g",
                    session_id="ses-4",
                    user_name="alice",
                    bearer_token="tok",
                    max_steps=0,
                )
            )
        # Nothing ran: the budget is validated before any member turn.
        assert kernel.calls == []

    def test_every_member_turn_is_read_only(self):
        kernel = FakeKernel(_settings())
        _run(
            run_bounded_diagnosis(
                kernel,
                profile=_profile(3),
                goal="g",
                session_id="ses-5",
                user_name="alice",
                bearer_token="tok",
            )
        )
        # The read-only admission is structural: no member (nor the synthesizer)
        # ever runs a mutating-capable turn.
        assert all(c.read_only for c in kernel.calls)

    def test_budget_limited_synthesis_is_marked_partial(self):
        kernel = FakeKernel(_settings())
        _run(
            run_bounded_diagnosis(
                kernel,
                profile=_profile(4),
                goal="g",
                session_id="ses-6",
                user_name="alice",
                bearer_token="tok",
                max_steps=2,
            )
        )
        synthesis = kernel.synthesis_calls[0]
        assert "budget was exhausted" in synthesis.message
        assert "PARTIAL" in synthesis.message


# ---------------------------------------------------------------------------
# R-2: role binding via the orchestration frame (process-local)
# ---------------------------------------------------------------------------
class TestRoleBinding:
    def test_members_bind_diagnostician_and_synthesis_binds_orchestrator(self):
        kernel = FakeKernel(_settings())
        _run(
            run_bounded_diagnosis(
                kernel,
                profile=_profile(3),
                goal="g",
                session_id="ses-7",
                user_name="alice",
                bearer_token="tok",
            )
        )
        assert len(kernel.member_calls) == 3
        assert len(kernel.synthesis_calls) == 1
        # No turn ran unscoped: the orchestration frame binds every participant.
        assert all(c.role is not None for c in kernel.calls)

    def test_role_is_process_local_and_restored_after_the_loop(self):
        kernel = FakeKernel(_settings())
        assert current_agent_role() is None
        _run(
            run_bounded_diagnosis(
                kernel,
                profile=_profile(2),
                goal="g",
                session_id="ses-8",
                user_name="alice",
                bearer_token="tok",
            )
        )
        # The bracket restores the prior (unscoped) context on exit.
        assert current_agent_role() is None
        assert current_agent_role_value() is None

    def test_each_participant_runs_on_an_isolated_session(self):
        kernel = FakeKernel(_settings())
        _run(
            run_bounded_diagnosis(
                kernel,
                profile=_profile(3),
                goal="g",
                session_id="ses-9",
                user_name="alice",
                bearer_token="tok",
            )
        )
        sessions = [c.session_id for c in kernel.calls]
        # Distinct derived session ids keep member memory isolated and stop the
        # per-session agent cache from reusing a diagnostician toolkit for the
        # orchestrator turn.
        assert len(set(sessions)) == len(sessions)
        assert all(s.startswith("ses-9::orch::") for s in sessions)
        assert "ses-9::orch::synthesis" in sessions


# ---------------------------------------------------------------------------
# R-1/R-2: the orchestrator sees only member summaries (memo §3.1)
# ---------------------------------------------------------------------------
class TestLeaderSeesOnlySummaries:
    def test_synthesis_prompt_carries_summaries_not_intermediate_steps(self):
        kernel = FakeKernel(_settings())
        _run(
            run_bounded_diagnosis(
                kernel,
                profile=_profile(2),
                goal="the-goal",
                session_id="ses-10",
                user_name="alice",
                bearer_token="tok",
            )
        )
        synthesis = kernel.synthesis_calls[0].message
        # Each member's summary (its task id + returned content) reaches the
        # leader; the member *instruction* prompts do not.
        for call in kernel.member_calls:
            assert call.session_id.split("::")[-1] in synthesis
            assert f"observed::{call.session_id}" in synthesis
        assert "the-goal" in synthesis
        # The member read-only instruction never leaks into the synthesis.
        assert "Autonomous read-only diagnosis step" not in synthesis


# ---------------------------------------------------------------------------
# R-1: no agentscope orchestration/pipeline type on the path (Decision 5)
# ---------------------------------------------------------------------------
class TestPlatformOwned:
    def test_no_agentscope_orchestration_type_is_constructed(self):
        # AST-based so the module docstring (which *names* the forbidden types
        # as things kept out by Decision 5) does not trip the guard: only real
        # imports and code references count.
        import ast

        tree = ast.parse(_ORCH_SRC.read_text())
        forbidden_types = {"TeamPipeline", "GoalPipeline", "A2AAgent"}
        imported_modules: set[str] = set()
        referenced_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_modules.add(node.module or "")
            elif isinstance(node, ast.Name):
                referenced_names.add(node.id)
            elif isinstance(node, ast.Attribute):
                referenced_names.add(node.attr)
        # No agentscope import anywhere on the orchestration path.
        assert not any(
            module.split(".")[0] == "agentscope" for module in imported_modules
        )
        # No agentscope orchestration/pipeline type is referenced (constructed).
        assert not (referenced_names & forbidden_types)


# ---------------------------------------------------------------------------
# R-1/OQ-2: the AGENT_ORCHESTRATION_MAX_STEPS knob
# ---------------------------------------------------------------------------
class TestBudgetKnob:
    def test_default_is_twenty(self):
        assert _settings().orchestration_max_steps == 20

    def test_below_one_fails_startup(self):
        with pytest.raises(ValueError, match="AGENT_ORCHESTRATION_MAX_STEPS"):
            _settings(orchestration_max_steps=0)

    def test_from_env_reads_the_knob(self, monkeypatch):
        monkeypatch.setenv("AGENT_ORCHESTRATION_MAX_STEPS", "7")
        assert RuntimeSettings.from_env().orchestration_max_steps == 7


# ---------------------------------------------------------------------------
# R-3: same-token identity preservation across the fan-out
# ---------------------------------------------------------------------------
class _IdCall:
    def __init__(self, role, bearer_token, requester):
        self.role = role
        self.bearer_token = bearer_token
        self.requester = requester


class IdentityFakeKernel:
    """Mimics the real per-turn ``REQUESTER_IDENTITY`` bracket (SPEC-070).

    The real ``reply_text`` derives the requester from the delegated token and
    sets ``REQUESTER_IDENTITY`` for the turn. This fake resolves the same human
    for the same token, so a fan-out that forwards one token must see one
    unchanged requester on every hop.
    """

    def __init__(self, settings, token_to_human):
        self.settings = settings
        self.calls: list[_IdCall] = []
        self._token_to_human = token_to_human

    async def reply_text(
        self,
        *,
        message,
        session_id,
        user_name,
        bearer_token=None,
        response_schema=None,
        model_id=None,
        read_only=False,
        routing_allowed=False,
    ):
        human = self._token_to_human.get(bearer_token)
        var = REQUESTER_IDENTITY.set(human)
        try:
            self.calls.append(
                _IdCall(
                    role=current_agent_role_value(),
                    bearer_token=bearer_token,
                    requester=REQUESTER_IDENTITY.get(),
                )
            )
        finally:
            REQUESTER_IDENTITY.reset(var)
        return BlockingReply(f"observed::{session_id}")


class TestSameTokenIdentity:
    def test_every_participant_rides_the_same_delegated_token(self):
        kernel = FakeKernel(_settings())
        _run(
            run_bounded_diagnosis(
                kernel,
                profile=_profile(4),
                goal="g",
                session_id="ses-20",
                user_name="alice",
                bearer_token="the-one-token",
                max_steps=2,
            )
        )
        # Members and the synthesizer all ride the orchestrator's own token; no
        # member turn was handed a different (per-role) credential.
        assert kernel.calls, "expected at least one turn"
        assert all(c.bearer_token == "the-one-token" for c in kernel.calls)

    def test_requester_identity_unchanged_across_every_hop(self):
        human = object()  # stands in for one VerifiedHuman
        kernel = IdentityFakeKernel(_settings(), {"tok": human})
        assert REQUESTER_IDENTITY.get() is None
        _run(
            run_bounded_diagnosis(
                kernel,
                profile=_profile(3),
                goal="g",
                session_id="ses-21",
                user_name="alice",
                bearer_token="tok",
            )
        )
        # Four hops (3 members + 1 synthesis) all resolve the same human.
        assert len(kernel.calls) == 4
        assert all(c.requester is human for c in kernel.calls)
        assert all(c.bearer_token == "tok" for c in kernel.calls)
        # The loop leaves no identity bound after it unwinds.
        assert REQUESTER_IDENTITY.get() is None

    def test_orchestration_path_mints_no_second_identity_edge(self):
        # R-3 by construction: the loop forwards the one token and adds zero
        # identity machinery. AST-scan the module imports — it may only reach the
        # process-local role bracket, never a broker/token/JWT/identity client.
        import ast

        tree = ast.parse(_ORCH_SRC.read_text())
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        forbidden_substrings = (
            "broker",
            "delegated_identity",
            "jwt",
            "httpx",
            "identity_broker",
        )
        for module in imported:
            lowered = module.lower()
            for forbidden in forbidden_substrings:
                assert forbidden not in lowered, f"orchestration imported {module}"

    def test_role_is_never_forwarded_as_a_wire_field(self):
        # The bound role stays process-local: run_bounded_diagnosis never passes
        # agent_role= into reply_text (which has no such parameter) and never
        # writes it to a header/claim. A source scan proves the only role use is
        # the process-local bracket.
        text = _ORCH_SRC.read_text()
        assert "agent_role=" not in text
        assert "agent_role_scope(" in text  # the only role mechanism


# ---------------------------------------------------------------------------
# R-6: live attribution — the bound role flows into the audit/evidence record
# ---------------------------------------------------------------------------
class _AttrCall:
    def __init__(self, session_id, event, turn):
        self.session_id = session_id
        self.event = event
        self.turn = turn


class AttributionFakeKernel:
    """Drives the *real* attribution seams from inside each orchestrated turn.

    The real kernel threads ``current_agent_role_value()`` into
    ``audit_emitter.build_audit_event`` (runtime_kernel:2769, gateway_tools:338)
    and into the persisted ``EvidenceTurn`` (runtime_kernel:1006 -> evidence
    store). This fake calls those same serializers at the same point in the turn
    — inside the orchestration frame's ``agent_role_scope`` — so the recorded
    event/turn carry exactly the role the loop bound. SPEC-076 R-6: attribution
    flows *automatically* off the SPEC-075 seams, with no schema change.
    """

    def __init__(self, settings):
        self.settings = settings
        self.calls: list[_AttrCall] = []

    async def reply_text(
        self,
        *,
        message,
        session_id,
        user_name,
        bearer_token=None,
        response_schema=None,
        model_id=None,
        read_only=False,
        routing_allowed=False,
    ):
        role_value = current_agent_role_value()
        request_id = f"req::{session_id}"
        event = build_audit_event(
            "execution_requested",
            request_id,
            "success",
            session_id=session_id,
            agent_role=role_value,
        )
        turn = EvidenceTurn(
            turn_index=len(self.calls),
            request_id=request_id,
            agent_role=role_value,
            frames=[{"observed": message}],
        )
        self.calls.append(_AttrCall(session_id, event, turn))
        return BlockingReply(f"observed::{session_id}")


class TestLiveAttribution:
    def test_every_participant_emits_its_own_role_into_audit_and_evidence(self):
        kernel = AttributionFakeKernel(_settings())
        result = _run(
            run_bounded_diagnosis(
                kernel,
                profile=_profile(3),
                goal="g",
                session_id="ses-30",
                user_name="alice",
                bearer_token="tok",
            )
        )
        # Three diagnostician member turns + one orchestrator synthesis turn.
        assert len(kernel.calls) == 4
        member = [c for c in kernel.calls if not c.session_id.endswith("::synthesis")]
        synth = [c for c in kernel.calls if c.session_id.endswith("::synthesis")]
        assert len(member) == 3 and len(synth) == 1
        for call in member:
            # The audit event carries the bound role verbatim (SPEC-075 emitter
            # seam) and so does the persisted evidence turn (SPEC-025 field).
            assert call.event["agent_role"] == "diagnostician"
            assert call.turn.model_dump()["agent_role"] == "diagnostician"
        assert synth[0].event["agent_role"] == "orchestrator"
        assert synth[0].turn.model_dump()["agent_role"] == "orchestrator"
        assert result.steps_used == 3

    def test_agent_role_filter_returns_exactly_the_member_reads(self):
        # R-6: "?agent_role=diagnostician returns the member reads". The emitted
        # events partition by role exactly as the audit-service AuditQuery filter
        # (already proven in products/audit-service) narrows them, and each member
        # read stays reconstructable from its evidence turn with attribution.
        kernel = AttributionFakeKernel(_settings())
        _run(
            run_bounded_diagnosis(
                kernel,
                profile=_profile(4),
                goal="g",
                session_id="ses-31",
                user_name="alice",
                bearer_token="tok",
                max_steps=2,
            )
        )
        diagnostician = [
            c for c in kernel.calls if c.event.get("agent_role") == "diagnostician"
        ]
        orchestrator = [
            c for c in kernel.calls if c.event.get("agent_role") == "orchestrator"
        ]
        # Only the two member reads that ran under the budget carry diagnostician;
        # the synthesis is the sole orchestrator event.
        assert len(diagnostician) == 2
        assert len(orchestrator) == 1
        assert all("::synthesis" not in c.session_id for c in diagnostician)
        for call in diagnostician:
            assert call.turn.agent_role == "diagnostician"
            assert call.turn.frames
            assert (
                "Autonomous read-only diagnosis step"
                in call.turn.frames[0]["observed"]
            )

    def test_no_participant_emits_an_unscoped_event_during_a_run(self):
        # The dimension is populated only where a role is bound: every turn of an
        # orchestration run carries a non-None agent_role (no unscoped leak on the
        # live path — the reachability guarantee, audit-side).
        kernel = AttributionFakeKernel(_settings())
        _run(
            run_bounded_diagnosis(
                kernel,
                profile=_profile(2),
                goal="g",
                session_id="ses-32",
                user_name="alice",
                bearer_token="tok",
            )
        )
        assert kernel.calls
        assert all("agent_role" in c.event for c in kernel.calls)
        assert all(c.event["agent_role"] is not None for c in kernel.calls)
        assert all(c.turn.agent_role is not None for c in kernel.calls)

    def test_unscoped_control_turn_stays_byte_identical(self):
        # Contrast: off the orchestration path (no scope bound) the same seams
        # emit no agent_role dimension at all, so the deployed single-agent event
        # and a legacy evidence turn replay byte-identically (SPEC-075 R-5).
        assert current_agent_role_value() is None
        event = build_audit_event(
            "execution_requested",
            "req-ctl",
            "success",
            agent_role=current_agent_role_value(),
        )
        assert "agent_role" not in event
        turn = EvidenceTurn(
            turn_index=0,
            request_id="req-ctl",
            agent_role=current_agent_role_value(),
            frames=[],
        )
        assert "agent_role" not in turn.model_dump()


# ---------------------------------------------------------------------------
# R-4: diagnose-before-act — the executor stages onto the existing HITL card
# ---------------------------------------------------------------------------
class _ParkCall:
    def __init__(self, role, session_id, read_only, message, bearer_token, pending):
        self.role = role
        self.session_id = session_id
        self.read_only = read_only
        self.message = message
        self.bearer_token = bearer_token
        self.pending = pending


class StagingFakeKernel:
    """Mimics the kernel's mutating-call park (runtime_kernel:1874/1899).

    When the executor proposes a remediation the real kernel registers a
    ``PendingConfirmation`` and labels it ``staged_by_role`` from the bound role;
    it never dispatches — a distinct human approves and the existing signed
    at-most-one-dispatch worker (SPEC-037/038/063) executes. This fake reproduces
    that park against the real ``PendingConfirmation`` type and exposes a
    ``dispatch`` seam the staging step must never touch.
    """

    def __init__(self, settings):
        self.settings = settings
        self.calls: list[_ParkCall] = []
        self.dispatches: list = []

    async def reply_text(
        self,
        *,
        message,
        session_id,
        user_name,
        bearer_token=None,
        response_schema=None,
        model_id=None,
        read_only=False,
        routing_allowed=False,
    ):
        pending = PendingConfirmation(
            confirm_id=f"cf::{session_id}",
            session_id=session_id,
            user_id=user_name,
            reply_id="r1",
        )
        # The park labels the staging role from the bound AGENT_ROLE (line 1899).
        pending.staged_by_role = current_agent_role_value()
        self.calls.append(
            _ParkCall(
                role=current_agent_role_value(),
                session_id=session_id,
                read_only=read_only,
                message=message,
                bearer_token=bearer_token,
                pending=pending,
            )
        )
        return BlockingReply(f"parked::{session_id}")

    async def dispatch(self, pending):  # pragma: no cover - staging never calls it
        self.dispatches.append(pending)


def _remediation_profile(
    name: str = "k8s-pod-degradation",
    shape: str = "restart the degraded pod",
) -> DiagnosisProfile:
    return DiagnosisProfile(
        name=name,
        trigger="operator-invoked",
        read_families=("k8s",),
        steps=(),
        remediation_shape=shape,
    )


class TestExecutorStaging:
    def test_executor_stages_onto_a_card_labelled_with_its_role(self):
        kernel = StagingFakeKernel(_settings())
        reply = _run(
            stage_remediation(
                kernel,
                profile=_remediation_profile(),
                goal="g",
                diagnosis="pod is crash-looping",
                session_id="ses-40",
                user_name="alice",
                bearer_token="tok",
            )
        )
        content, _structured = reply
        assert content == "parked::ses-40::orch::staging"
        assert len(kernel.calls) == 1
        call = kernel.calls[0]
        # The staging turn binds the executor and runs read_only=False so it can
        # *propose* the mutation, which the kernel parks (never dispatches).
        assert call.role == "executor"
        assert call.read_only is False
        # The parked card carries the SPEC-073 R-4 staged_by_role provenance.
        assert isinstance(call.pending, PendingConfirmation)
        assert call.pending.staged_by_role == "executor"

    def test_staging_parks_and_never_dispatches(self):
        # R-4: the staging step produces a parked card and zero dispatches; the
        # signed at-most-one-dispatch worker + SPEC-030 self-approval block are
        # the *existing* mutation path, reached only after a distinct human approves.
        kernel = StagingFakeKernel(_settings())
        _run(
            stage_remediation(
                kernel,
                profile=_remediation_profile(
                    "observability-alert", "scale the deployment"
                ),
                goal="g",
                diagnosis="d",
                session_id="ses-41",
                user_name="alice",
                bearer_token="tok",
            )
        )
        assert all(c.pending is not None for c in kernel.calls)
        assert kernel.dispatches == []

    def test_read_only_loop_never_binds_the_executor_role(self):
        # A diagnostician/orchestrator cannot stage a mutation at all: the bounded
        # diagnosis loop binds only those two roles, so no executor park is
        # reachable from inside the read-only fan-out (R-1/R-4).
        kernel = FakeKernel(_settings())
        _run(
            run_bounded_diagnosis(
                kernel,
                profile=_profile(3),
                goal="g",
                session_id="ses-42",
                user_name="alice",
                bearer_token="tok",
            )
        )
        roles = {c.role for c in kernel.calls}
        assert roles == {"diagnostician", "orchestrator"}
        assert "executor" not in roles

    def test_profile_without_remediation_shape_cannot_stage(self):
        # Fail closed: a read-only profile with no declared remediation shape has
        # nothing to propose, so staging refuses rather than opening an executor
        # turn (never widen to a mutation to "finish").
        kernel = StagingFakeKernel(_settings())
        with pytest.raises(ValueError, match="remediation_shape"):
            _run(
                stage_remediation(
                    kernel,
                    profile=_profile(1),  # remediation_shape is None
                    goal="g",
                    diagnosis="d",
                    session_id="ses-43",
                    user_name="alice",
                    bearer_token="tok",
                )
            )
        assert kernel.calls == []

    def test_staging_rides_the_same_token_and_leaves_no_role_bound(self):
        # R-3/R-4: the executor staging forwards the one delegated token and the
        # role stays process-local — restored to unscoped once the step unwinds.
        kernel = StagingFakeKernel(_settings())
        assert current_agent_role() is None
        _run(
            stage_remediation(
                kernel,
                profile=_remediation_profile(
                    "servicenow-incident", "reopen the incident"
                ),
                goal="g",
                diagnosis="d",
                session_id="ses-44",
                user_name="alice",
                bearer_token="the-one-token",
            )
        )
        assert kernel.calls[0].bearer_token == "the-one-token"
        assert current_agent_role() is None
        assert current_agent_role_value() is None

    def test_staging_adds_no_contract_wire_field(self):
        # R-4/OQ-5: staging reuses the existing HITL park and adds no contract
        # field — execution-request.schema.json stays byte-unchanged (no
        # staged_by_role, no agent_role), so the role provenance never crosses the
        # wire (the multi-agent frame is phase 6).
        schema = (_SCHEMA_DIR / "execution-request.schema.json").read_text()
        assert "staged_by_role" not in schema
        assert "agent_role" not in schema


# ---------------------------------------------------------------------------
# SPEC-077 R-5 (OQ-5): the wired diagnose→act bridge audits by role
# ---------------------------------------------------------------------------
class TestDiagnoseActBridgeAttribution:
    """Stage 5 adds **no** production code — the attribution mechanism is the
    delivered SPEC-075 emitter seam (``build_audit_event(agent_role=
    current_agent_role_value())``) and the SPEC-073 ``staged_by_role`` park
    label, both already exercised off the diagnosis path (``TestLiveAttribution``
    and ``TestExecutorStaging`` above). These tests drive the *executor staging*
    turn — the half SPEC-077 wires to an explicit human trigger — through the
    same real seam and assert the audit trail reconstructs the bridge: diagnosis
    under ``diagnostician``/``orchestrator``, the staged proposal under
    ``executor``, one human + one delegated token throughout, and **no** new
    ``event_type`` (the enum stays closed).
    """

    def test_executor_staging_turn_emits_an_audit_event_attributed_to_executor(self):
        kernel = AttributionFakeKernel(_settings())
        _run(
            stage_remediation(
                kernel,
                profile=_remediation_profile(),
                goal="g",
                diagnosis="pod is crash-looping",
                session_id="ses-50",
                user_name="alice",
                bearer_token="the-one-token",
            )
        )
        # Exactly one executor turn, on the derived staging session.
        assert len(kernel.calls) == 1
        call = kernel.calls[0]
        assert call.session_id == "ses-50::orch::staging"
        # The delivered emitter seam threads the bound role verbatim: the audit
        # event and the persisted evidence turn both carry agent_role="executor"
        # (SPEC-075), with no new event_type minted for the bridge.
        assert call.event["agent_role"] == "executor"
        assert call.turn.model_dump()["agent_role"] == "executor"

    def test_diagnose_to_act_bridge_is_reconstructable_by_role(self):
        # The full bridge over ONE session/human/token: run_bounded_diagnosis
        # (diagnostician members + orchestrator synthesis) then stage_remediation
        # (the executor proposal). Every turn emits through the one seam, so the
        # audit trail partitions the diagnose→act story by role and the staged
        # proposal is attributable to the executor that parked it. The one
        # delegated token is threaded unchanged across both halves (proven by
        # test_staging_rides_the_same_token_and_leaves_no_role_bound above).
        kernel = AttributionFakeKernel(_settings())
        _run(
            run_bounded_diagnosis(
                kernel,
                profile=_profile(3),
                goal="g",
                session_id="ses-51",
                user_name="alice",
                bearer_token="the-one-token",
            )
        )
        _run(
            stage_remediation(
                kernel,
                profile=_remediation_profile(),
                goal="g",
                diagnosis="d",
                session_id="ses-51",
                user_name="alice",
                bearer_token="the-one-token",
            )
        )
        roles = [c.event["agent_role"] for c in kernel.calls]
        # 3 diagnostician member reads + 1 orchestrator synthesis + 1 executor
        # staging proposal — the whole bridge reconstructable from the trail.
        assert roles.count("diagnostician") == 3
        assert roles.count("orchestrator") == 1
        assert roles.count("executor") == 1
        # The executor proposal is the bridge's final turn, on the derived
        # staging session.
        final = kernel.calls[-1]
        assert final.event["agent_role"] == "executor"
        assert final.session_id == "ses-51::orch::staging"


# ---------------------------------------------------------------------------
# R-7: the four declared runbook profiles + the trigger boundary
# ---------------------------------------------------------------------------
class TestRunbookProfiles:
    def test_exactly_four_profiles_declared_in_spec_order(self):
        # memo §8 Q5 = all four, in spec order (a, b, c, d).
        assert profile_names() == (
            "servicenow-incident",
            "observability-alert",
            "post-deploy-verify",
            "k8s-pod-degradation",
        )
        assert [p.name for p in all_profiles()] == list(profile_names())

    def test_get_profile_resolves_each_and_fails_closed_on_unknown(self):
        for name in profile_names():
            profile = get_profile(name)
            assert profile is not None
            assert profile.name == name
        # Fail closed: an unknown profile is never coerced to a wider runbook
        # (the operator-invoked trigger maps None to a 4xx).
        assert get_profile("reboot-everything") is None
        assert get_profile("") is None

    def test_declared_read_families_cover_the_spec_runbooks(self):
        # Data-integrity (M2): `diagnostician_read_families` is declarative
        # documentation of the read families the four runbooks intend to exercise
        # — it is NOT a toolkit filter (the live diagnostician toolkit is narrowed
        # by risk tier + token roles at `_narrow_for_role`, never by family) and
        # has no production caller. This asserts the declared profiles collectively
        # cover the spec-named families and that the union *derives* from them, so
        # adding a runbook widens it automatically (never hardcoded separately).
        union = diagnostician_read_families()
        expected: set[str] = set()
        for profile in all_profiles():
            expected.update(profile.read_families)
        assert set(union) == expected
        assert union == tuple(sorted(expected))  # deterministic order
        # Each read family the spec names for the four runbooks is declared.
        for family in (
            "servicenow",
            "observability",
            "kubernetes",
            "changes",
            "config",
        ):
            assert family in union

    def test_remediation_shapes_match_the_spec_split(self):
        # (a) ServiceNow-incident and (b) observability-alert are diagnosis-only
        # ("→ diagnosis"); (c) post-deploy-verify proposes a rollback and
        # (d) k8s-pod-degradation proposes a remediation.
        assert SERVICENOW_INCIDENT.remediation_shape is None
        assert OBSERVABILITY_ALERT.remediation_shape is None
        assert POST_DEPLOY_VERIFY.remediation_shape is not None
        assert "roll" in POST_DEPLOY_VERIFY.remediation_shape.lower()
        assert K8S_POD_DEGRADATION.remediation_shape is not None

    def test_every_profile_declares_an_operator_trigger_and_read_steps(self):
        for profile in all_profiles():
            # The phase-5 trigger is operator-invoked (OQ-3), declared per profile.
            assert "operator-invoked" in profile.trigger
            assert profile.read_families
            assert profile.steps  # a non-empty read fan-out
            ids = [step.task_id for step in profile.steps]
            assert len(set(ids)) == len(ids)  # unique, stable member task ids
            for step in profile.steps:
                assert step.prompt

    def test_each_runbook_runs_autonomous_read_only_with_no_human_approving_reads(
        self,
    ):
        # R-7 acceptance: "an autonomous read-only diagnosis runs with no human
        # approving any read". Drive each declared profile through the real loop
        # with a fixture-backed fake kernel: every member turn is read-only, only
        # diagnostician+orchestrator are bound, and no read parks on a human gate.
        for profile in all_profiles():
            kernel = FakeKernel(_settings())
            result = _run(
                run_bounded_diagnosis(
                    kernel,
                    profile=profile,
                    goal=f"diagnose {profile.name}",
                    session_id=f"ses-rb-{profile.name}",
                    user_name="alice",
                    bearer_token="tok",
                )
            )
            # All four profiles fit the default budget of 20, so every declared
            # member step ran and the result is not budget-limited.
            assert result.steps_used == len(profile.steps)
            assert result.budget_limited is False
            assert len(kernel.member_calls) == len(profile.steps)
            assert all(c.read_only for c in kernel.calls)
            assert {c.role for c in kernel.calls} == {
                "diagnostician",
                "orchestrator",
            }
            # No human approved any read: the member instruction states it and
            # the fake kernel parked nothing (no authorization_required).
            for call in kernel.member_calls:
                assert "no human approves any read" in call.message
            assert result.diagnosis

    def test_diagnosis_only_runbooks_cannot_stage_a_mutation(self):
        # (a) and (b) declare no remediation_shape, so the trigger cannot cause
        # a mutation at all: staging fails closed rather than opening an executor
        # turn (R-4/R-7 — "the trigger cannot cause a mutation without the R-4
        # gate"; here there is not even a proposal to gate).
        kernel = StagingFakeKernel(_settings())
        for profile in (SERVICENOW_INCIDENT, OBSERVABILITY_ALERT):
            with pytest.raises(ValueError, match="remediation_shape"):
                _run(
                    stage_remediation(
                        kernel,
                        profile=profile,
                        goal="g",
                        diagnosis="d",
                        session_id=f"ses-{profile.name}",
                        user_name="alice",
                        bearer_token="tok",
                    )
                )
        assert kernel.calls == []  # no executor turn was ever opened

    def test_remediation_runbooks_only_park_never_dispatch(self):
        # (c) and (d) declare a remediation shape: an executor may *stage* a
        # proposal, but it only parks on the existing HITL card and never
        # dispatches — a distinct human approver is required (R-4).
        for profile in (POST_DEPLOY_VERIFY, K8S_POD_DEGRADATION):
            kernel = StagingFakeKernel(_settings())
            _run(
                stage_remediation(
                    kernel,
                    profile=profile,
                    goal="g",
                    diagnosis="d",
                    session_id=f"ses-{profile.name}",
                    user_name="alice",
                    bearer_token="tok",
                )
            )
            assert len(kernel.calls) == 1
            assert kernel.calls[0].role == "executor"
            assert kernel.calls[0].pending.staged_by_role == "executor"
            assert kernel.dispatches == []  # never auto-dispatched

    def test_runbook_module_is_pure_data_and_binds_no_role(self):
        # A profile is pure data: the runbooks module constructs no agentscope
        # type (gate point 4) and is not a role-binder — the reachability guard
        # ("only the orchestration frame binds a role") must stay true, so this
        # module never opens an agent_role_scope or reads the bound role.
        import ast

        src = _RUNBOOKS_SRC.read_text()
        tree = ast.parse(src)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        assert not any(m.split(".")[0] == "agentscope" for m in imported)
        assert "agent_role_scope" not in src
        assert "current_agent_role" not in src


class TestRunbookEndToEnd:
    """R-7/OQ-7: (a) ServiceNow-incident and (d) k8s-pod-degradation wired e2e."""

    def test_servicenow_incident_end_to_end_read_only_diagnosis(self):
        # (a) is diagnosis-only: the full four-member fan-out runs read-only and
        # synthesizes; there is no remediation to stage, so the flow ends at the
        # diagnosis (no executor, no park, no mutation).
        profile = get_profile("servicenow-incident")
        kernel = FakeKernel(_settings())
        result = _run(
            run_bounded_diagnosis(
                kernel,
                profile=profile,
                goal="why is INC-1234 breaching its SLA",
                session_id="ses-e2e-snow",
                user_name="alice",
                bearer_token="the-one-token",
            )
        )
        assert result.profile == "servicenow-incident"
        assert result.steps_used == 4
        assert result.budget_limited is False
        # The four declared read steps each drove one member turn.
        assert {c.session_id.split("::")[-1] for c in kernel.member_calls} == {
            "incident-record",
            "observability-signals",
            "kubernetes-state",
            "recent-changes",
        }
        # Same one token across the whole fan-out (R-3); read-only throughout.
        assert all(c.bearer_token == "the-one-token" for c in kernel.calls)
        assert all(c.read_only for c in kernel.calls)
        # Diagnosis-only: staging this profile fails closed (nothing to propose).
        staging = StagingFakeKernel(_settings())
        with pytest.raises(ValueError, match="remediation_shape"):
            _run(
                stage_remediation(
                    staging,
                    profile=profile,
                    goal="g",
                    diagnosis=result.diagnosis,
                    session_id="ses-e2e-snow",
                    user_name="alice",
                    bearer_token="the-one-token",
                )
            )
        assert staging.calls == []

    def test_k8s_pod_degradation_end_to_diagnose_then_stage(self):
        # (d) is the full detect→troubleshoot→propose: a read-only fan-out
        # diagnoses, then an executor stages the proposed remediation onto the
        # existing HITL card (parks, never dispatches).
        profile = get_profile("k8s-pod-degradation")
        kernel = FakeKernel(_settings())
        result = _run(
            run_bounded_diagnosis(
                kernel,
                profile=profile,
                goal="pod checkout-7d9 is crash-looping",
                session_id="ses-e2e-k8s",
                user_name="alice",
                bearer_token="the-one-token",
            )
        )
        assert result.steps_used == 4
        assert {c.session_id.split("::")[-1] for c in kernel.member_calls} == {
            "pod-events",
            "container-logs",
            "config-secret-diffs",
            "node-health",
        }
        # The read-only loop bound no executor and dispatched nothing.
        assert "executor" not in {c.role for c in kernel.calls}
        # Now stage the proposal: one executor turn parks a card, never dispatch.
        staging = StagingFakeKernel(_settings())
        _run(
            stage_remediation(
                staging,
                profile=profile,
                goal="pod checkout-7d9 is crash-looping",
                diagnosis=result.diagnosis,
                session_id="ses-e2e-k8s",
                user_name="alice",
                bearer_token="the-one-token",
            )
        )
        assert len(staging.calls) == 1
        assert staging.calls[0].role == "executor"
        assert staging.calls[0].read_only is False
        assert staging.calls[0].pending.staged_by_role == "executor"
        assert staging.dispatches == []
        # The staging rode the same one token (R-3).
        assert staging.calls[0].bearer_token == "the-one-token"

