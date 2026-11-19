"""SPEC-078 R-1/R-2: the conversational diagnose → propose → stage composition.

These pin the *composition* (``run_conversational_remediation`` calls the delivered
SPEC-076 ``run_bounded_diagnosis`` then the delivered SPEC-077 ``stage_remediation``
**verbatim**) and the *route wiring* on both chat surfaces (``POST /api/v2/chat`` +
``GET /api/v2/chat/stream``). The two delivered halves are exercised in depth by
``test_orchestration.py``; here the fake kernel reproduces only what the composition
depends on — read-only turns return text and the single ``read_only=False`` executor
turn parks a ``PendingConfirmation`` labelled ``staged_by_role`` from the bound role,
never dispatching. The route tests patch ``run_conversational_remediation`` so the
branch is proven deterministically without a live model fan-out.

Invariants asserted throughout: the route binds **no** role and carries none on the
wire (SPEC-073 R-3); a diagnosis-only or unknown profile **fails closed before the
fan-out** and opens no executor turn (mirrors SPEC-077 R-2); the staged proposal only
**parks** for a distinct human (nothing dispatches); and a turn without the intent
flag never touches the composition (the unscoped path stays byte-identical).
"""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from agent_service.app import create_app
from agent_service.runtime_kernel import BlockingReply
from agent_service.runtime_settings import RuntimeSettings
from agent_service.schemas.v2 import EvidenceTurn
from agent_service.services.agent_role import AgentRole, current_agent_role_value
from agent_service.services.audit_emitter import build_audit_event
from agent_service.services.hitl_confirmations import PendingConfirmation
from agent_service.services.orchestration import (
    ConversationalRemediationResult,
    DiagnosisResult,
    run_conversational_remediation,
)
from agent_service.services.runbooks import get_profile


def _settings(**kwargs) -> RuntimeSettings:
    return RuntimeSettings(
        api_key="test-key", tool_gateway_url="http://gw:8080", **kwargs
    )


def _run(coro):
    return asyncio.run(coro)


class _ConvCall:
    def __init__(self, role, session_id, read_only, message, bearer_token, pending):
        self.role = role
        self.session_id = session_id
        self.read_only = read_only
        self.message = message
        self.bearer_token = bearer_token
        self.pending = pending


class ConversationalFakeKernel:
    """One kernel that both diagnoses (read-only) and parks the staging turn.

    Mirrors the real ``AgentKernel``: ``read_only=True`` turns (the diagnostician
    fan-out + the orchestrator synthesis) simply return text; the single
    ``read_only=False`` executor turn registers a ``PendingConfirmation`` labelled
    ``staged_by_role`` from the bound ``AGENT_ROLE`` (runtime_kernel ~L1899) and
    never dispatches — a distinct human approves and the signed at-most-one-dispatch
    worker executes. ``dispatch`` is the seam the composition must never touch.
    """

    def __init__(self, settings):
        self.settings = settings
        self.calls: list[_ConvCall] = []
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
        role = current_agent_role_value()
        pending = None
        if not read_only:
            pending = PendingConfirmation(
                confirm_id=f"cf::{session_id}",
                session_id=session_id,
                user_id=user_name,
                reply_id="r1",
            )
            pending.staged_by_role = role
        self.calls.append(
            _ConvCall(role, session_id, read_only, message, bearer_token, pending)
        )
        verb = "parked" if pending is not None else "observed"
        return BlockingReply(f"{verb}::{session_id}")

    async def dispatch(self, pending):  # pragma: no cover - staging never calls it
        self.dispatches.append(pending)

    @property
    def member_calls(self):
        return [c for c in self.calls if c.role == AgentRole.DIAGNOSTICIAN.value]

    @property
    def synthesis_calls(self):
        return [c for c in self.calls if c.role == AgentRole.ORCHESTRATOR.value]

    @property
    def staging_calls(self):
        return [c for c in self.calls if c.role == AgentRole.EXECUTOR.value]


# ---------------------------------------------------------------------------
# R-2: the composition reuses the delivered machinery verbatim
# ---------------------------------------------------------------------------
class TestConversationalComposition:
    def test_composes_diagnose_then_stage_and_parks_one_executor_proposal(self):
        profile = get_profile("k8s-pod-degradation")  # 4 read steps + a shape
        kernel = ConversationalFakeKernel(_settings())
        result = _run(
            run_conversational_remediation(
                kernel,
                profile=profile,
                goal="pod checkout-7d9 is crash-looping",
                session_id="ses-conv",
                user_name="alice",
                bearer_token="the-one-token",
            )
        )
        # The delivered read-only fan-out ran first: 4 diagnostician members + one
        # orchestrator synthesis, every one read-only.
        assert len(kernel.member_calls) == 4
        assert all(c.read_only for c in kernel.member_calls)
        assert len(kernel.synthesis_calls) == 1
        assert kernel.synthesis_calls[0].read_only is True
        # Then exactly one executor staging turn parked one proposal.
        assert len(kernel.staging_calls) == 1
        staging = kernel.staging_calls[0]
        assert staging.read_only is False
        assert staging.session_id == "ses-conv::orch::staging"
        assert staging.pending is not None
        assert staging.pending.staged_by_role == "executor"
        # R-2: the team proposes, a human disposes — nothing dispatched.
        assert kernel.dispatches == []
        # The diagnosis rode to completion (not budget-limited) and the narrative
        # projects the diagnosis then the staged proposal as one voice (R-5).
        assert result.diagnosis.profile == "k8s-pod-degradation"
        assert result.diagnosis.budget_limited is False
        assert result.narrative == (
            "observed::ses-conv::orch::synthesis\n\n"
            "parked::ses-conv::orch::staging"
        )
        # The composition binds no role itself and leaves none bound afterwards.
        assert current_agent_role_value() is None

    def test_diagnosis_only_profile_fails_closed_before_any_fanout(self):
        profile = get_profile("servicenow-incident")  # remediation_shape is None
        assert profile.remediation_shape is None
        kernel = ConversationalFakeKernel(_settings())
        with pytest.raises(ValueError, match="remediation_shape"):
            _run(
                run_conversational_remediation(
                    kernel,
                    profile=profile,
                    goal="why is INC-1234 breaching its SLA",
                    session_id="ses-conv",
                    user_name="alice",
                    bearer_token="the-one-token",
                )
            )
        # Fail closed *before* the billable fan-out: no member, no synthesis, no
        # executor turn, no dispatch (mirrors SPEC-077 R-2).
        assert kernel.calls == []
        assert kernel.dispatches == []
        assert current_agent_role_value() is None

    def test_budget_still_bounds_the_conversational_fanout(self):
        profile = get_profile("k8s-pod-degradation")  # 4 declared steps
        kernel = ConversationalFakeKernel(_settings(orchestration_max_steps=2))
        result = _run(
            run_conversational_remediation(
                kernel,
                profile=profile,
                goal="pod is crash-looping",
                session_id="ses-conv",
                user_name="alice",
                bearer_token="the-one-token",
            )
        )
        # AGENT_ORCHESTRATION_MAX_STEPS still bounds the fan-out and fails closed
        # to a partial diagnosis — the composition never widens the budget.
        assert len(kernel.member_calls) == 2
        assert result.diagnosis.budget_limited is True
        assert result.diagnosis.steps_used == 2
        # A budget-limited partial still stages exactly one proposal, no dispatch.
        assert len(kernel.staging_calls) == 1
        assert kernel.dispatches == []

    def test_same_delegated_token_and_in_process_roles_across_every_hop(self):
        profile = get_profile("post-deploy-verify")  # 3 steps + a shape
        kernel = ConversationalFakeKernel(_settings())
        _run(
            run_conversational_remediation(
                kernel,
                profile=profile,
                goal="verify then roll back the bad deploy",
                session_id="ses-conv",
                user_name="alice",
                bearer_token="the-one-token",
            )
        )
        # R-3: every hop — members, synthesis, staging — rode the same one token.
        assert kernel.calls
        assert all(c.bearer_token == "the-one-token" for c in kernel.calls)
        # Roles are bound in-process only, one per seam, never on a wire field.
        assert {c.role for c in kernel.member_calls} == {"diagnostician"}
        assert {c.role for c in kernel.synthesis_calls} == {"orchestrator"}
        assert {c.role for c in kernel.staging_calls} == {"executor"}

    def test_composition_constructs_no_agentscope_orchestration_surface(self):
        # R-2 / ADR-0017 Decision 5: the composition is platform-owned — it only
        # calls the two delivered functions. AST-based so the docstring (which
        # *names* agentscope as a thing kept out) does not trip the guard: only
        # real imports and code references count. test_orchestration.py's
        # whole-file guard already covers this; here it is tied to the function.
        import ast

        tree = ast.parse(inspect.getsource(run_conversational_remediation))
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
        assert not any(
            module.split(".")[0] == "agentscope" for module in imported_modules
        )
        assert not (referenced_names & forbidden_types)


# ---------------------------------------------------------------------------
# R-1: the route branch on both chat surfaces
# ---------------------------------------------------------------------------
def _client() -> TestClient:
    return TestClient(create_app())


def _new_session(client: TestClient) -> str:
    response = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    assert response.status_code == 201, response.text
    return response.json()["session_id"]


def _conv_result(profile: str, *, budget_limited: bool = False):
    diagnosis = DiagnosisResult(
        profile=profile,
        goal="g",
        diagnosis=f"diagnosis::{profile}",
        member_summaries=(),
        steps_used=1,
        budget=20,
        budget_limited=budget_limited,
    )
    return ConversationalRemediationResult(
        diagnosis=diagnosis,
        staging_reply=BlockingReply(f"staged::{profile}"),
    )


class TestChatRouteBranch:
    def test_chat_drives_composition_and_projects_narrative(self):
        client = _client()
        session_id = _new_session(client)
        captured: dict = {}

        async def fake_conv(kernel, **kwargs):
            captured.update(kwargs)
            captured["role_at_entry"] = current_agent_role_value()
            return _conv_result(kwargs["profile"].name)

        with patch(
            "agent_service.api.v2.routes.run_conversational_remediation", fake_conv
        ):
            response = client.post(
                "/api/v2/chat",
                json={
                    "message": "pod checkout-7d9 is crash-looping, please remediate",
                    "session_id": session_id,
                    "remediation_intent": True,
                    "remediation_profile": "k8s-pod-degradation",
                },
                headers={"X-User-ID": "alice", "Authorization": "Bearer tok-123"},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        # The narrative is projected onto the existing AgentChatResponse frame and
        # no agent_role crosses the wire (SPEC-073 R-3).
        assert body["content"] == (
            "diagnosis::k8s-pod-degradation\n\nstaged::k8s-pod-degradation"
        )
        assert body["status"] == "ok"
        assert body["session_id"] == session_id
        assert "agent_role" not in body
        # The route resolved the declared profile and forwarded the chat message as
        # the goal, on the same delegated token, binding no role at the entry.
        assert captured["profile"] is get_profile("k8s-pod-degradation")
        assert captured["goal"] == (
            "pod checkout-7d9 is crash-looping, please remediate"
        )
        assert captured["session_id"] == session_id
        assert captured["user_name"] == "alice"
        assert captured["bearer_token"] == "tok-123"
        assert captured["role_at_entry"] is None

    def test_chat_budget_limited_composition_surfaces_as_partial(self):
        client = _client()
        session_id = _new_session(client)

        async def fake_conv(kernel, **kwargs):
            return _conv_result(kwargs["profile"].name, budget_limited=True)

        with patch(
            "agent_service.api.v2.routes.run_conversational_remediation", fake_conv
        ):
            response = client.post(
                "/api/v2/chat",
                json={
                    "message": "remediate the degraded pod",
                    "session_id": session_id,
                    "remediation_intent": True,
                    "remediation_profile": "k8s-pod-degradation",
                },
                headers={"X-User-ID": "alice"},
            )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "partial"

    def test_chat_without_intent_flag_never_touches_the_composition(self):
        client = _client()
        session_id = _new_session(client)

        async def bomb(kernel, **kwargs):  # pragma: no cover - must not run
            raise AssertionError(
                "run_conversational_remediation must not run without the intent flag"
            )

        with patch(
            "agent_service.api.v2.routes.run_conversational_remediation", bomb
        ):
            response = client.post(
                "/api/v2/chat",
                json={"message": "hello", "session_id": session_id},
                headers={"X-User-ID": "alice"},
            )

        # The unscoped single-agent path ran byte-identically (no composition).
        assert response.status_code == 200, response.text

    def test_chat_intent_unknown_profile_fails_closed_422(self):
        client = _client()
        session_id = _new_session(client)

        async def bomb(kernel, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("composition must not run for an unknown profile")

        with patch(
            "agent_service.api.v2.routes.run_conversational_remediation", bomb
        ):
            response = client.post(
                "/api/v2/chat",
                json={
                    "message": "remediate",
                    "session_id": session_id,
                    "remediation_intent": True,
                    "remediation_profile": "reboot-everything",
                },
                headers={"X-User-ID": "alice"},
            )

        assert response.status_code == 422
        assert "unknown diagnosis profile" in response.json()["detail"]

    def test_chat_intent_diagnosis_only_profile_fails_closed_422(self):
        client = _client()
        session_id = _new_session(client)

        async def bomb(kernel, **kwargs):  # pragma: no cover - must not run
            raise AssertionError(
                "composition must not run for a diagnosis-only profile"
            )

        with patch(
            "agent_service.api.v2.routes.run_conversational_remediation", bomb
        ):
            response = client.post(
                "/api/v2/chat",
                json={
                    "message": "remediate the incident",
                    "session_id": session_id,
                    "remediation_intent": True,
                    "remediation_profile": "servicenow-incident",
                },
                headers={"X-User-ID": "alice"},
            )

        assert response.status_code == 422
        assert "diagnosis-only" in response.json()["detail"]


class TestChatStreamRouteBranch:
    def test_chat_stream_drives_composition_and_streams_narrative(self):
        client = _client()
        session_id = _new_session(client)
        captured: dict = {}

        async def fake_conv(kernel, **kwargs):
            captured.update(kwargs)
            captured["role_at_entry"] = current_agent_role_value()
            return _conv_result(kwargs["profile"].name)

        with patch(
            "agent_service.api.v2.routes.run_conversational_remediation", fake_conv
        ):
            response = client.get(
                "/api/v2/chat/stream",
                params={
                    "message": "remediate the crash-looping pod",
                    "session_id": session_id,
                    "remediation_intent": True,
                    "remediation_profile": "k8s-pod-degradation",
                },
                headers={"X-User-ID": "alice"},
            )

        assert response.status_code == 200, response.text
        text = response.text
        # The narrative is projected through the existing TurnStreamer frames — no
        # new frame type — and carries both the diagnosis and the staged proposal.
        assert "message_start" in text
        assert "diagnosis::k8s-pod-degradation" in text
        assert "staged::k8s-pod-degradation" in text
        assert "message_end" in text
        assert captured["goal"] == "remediate the crash-looping pod"
        assert captured["role_at_entry"] is None

    def test_chat_stream_intent_diagnosis_only_fails_closed_422(self):
        client = _client()
        session_id = _new_session(client)

        async def bomb(kernel, **kwargs):  # pragma: no cover - must not run
            raise AssertionError(
                "composition must not run for a diagnosis-only profile"
            )

        with patch(
            "agent_service.api.v2.routes.run_conversational_remediation", bomb
        ):
            response = client.get(
                "/api/v2/chat/stream",
                params={
                    "message": "remediate the incident",
                    "session_id": session_id,
                    "remediation_intent": True,
                    "remediation_profile": "servicenow-incident",
                },
                headers={"X-User-ID": "alice"},
            )

        # Fail closed before headers go out: a 422, never a half-open stream.
        assert response.status_code == 422
        assert "diagnosis-only" in response.json()["detail"]


# ---------------------------------------------------------------------------
# R-4 (verify only, no new production code): the ONE-turn conversational
# composition audits the correct agent_role across its whole diagnose→propose
# span. SPEC-077's TestDiagnoseActBridgeAttribution proved the two halves when
# driven as separate triggers; these prove the composed entry reconstructs the
# same trail in a single human-requested turn — through the delivered SPEC-075
# emitter seam, with no new event_type and nothing dispatched.
# ---------------------------------------------------------------------------
class _AttrConvCall:
    def __init__(self, session_id, event, turn, pending, bearer_token, user_name):
        self.session_id = session_id
        self.event = event
        self.turn = turn
        self.pending = pending
        self.bearer_token = bearer_token
        self.user_name = user_name


class ConversationalAttributionFakeKernel:
    """Drives the *real* SPEC-075 attribution seams inside every conversational
    turn **and** parks the single executor staging proposal.

    Like the real kernel it threads ``current_agent_role_value()`` into
    ``audit_emitter.build_audit_event`` (runtime_kernel:2769) and the persisted
    ``EvidenceTurn`` (runtime_kernel:1006); on the one ``read_only=False``
    executor turn it also registers a ``PendingConfirmation`` labelled
    ``staged_by_role`` from the bound role (runtime_kernel:1899) and never
    dispatches. R-4: attribution flows *automatically* off the delivered seams —
    no schema change, no new ``event_type``, no ``agent_role`` on any wire field.
    """

    def __init__(self, settings):
        self.settings = settings
        self.calls: list[_AttrConvCall] = []
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
        role_value = current_agent_role_value()
        request_id = f"req::{session_id}"
        # An EXISTING event_type — no new type is minted for the conversational
        # bridge (the enum stays closed; the gateway reuses ``chat_completed``).
        event = build_audit_event(
            "execution_requested",
            request_id,
            "success",
            session_id=session_id,
            username=user_name,
            agent_role=role_value,
        )
        turn = EvidenceTurn(
            turn_index=len(self.calls),
            request_id=request_id,
            agent_role=role_value,
            frames=[{"observed": message}],
        )
        pending = None
        if not read_only:
            pending = PendingConfirmation(
                confirm_id=f"cf::{session_id}",
                session_id=session_id,
                user_id=user_name,
                reply_id="r1",
            )
            pending.staged_by_role = role_value
        self.calls.append(
            _AttrConvCall(
                session_id, event, turn, pending, bearer_token, user_name
            )
        )
        verb = "parked" if pending is not None else "observed"
        return BlockingReply(f"{verb}::{session_id}")

    async def dispatch(self, pending):  # pragma: no cover - staging never calls it
        self.dispatches.append(pending)


class TestConversationalAttribution:
    def test_conversational_span_emits_role_attributed_audit_events(self):
        profile = get_profile("k8s-pod-degradation")  # 4 read steps + a shape
        kernel = ConversationalAttributionFakeKernel(_settings())
        _run(
            run_conversational_remediation(
                kernel,
                profile=profile,
                goal="pod checkout-7d9 is crash-looping",
                session_id="ses-attr",
                user_name="alice",
                bearer_token="the-one-token",
            )
        )
        roles = [c.event["agent_role"] for c in kernel.calls]
        # 4 diagnostician member reads + 1 orchestrator synthesis + 1 executor
        # staging proposal — the whole conversational bridge in ONE turn.
        assert len(kernel.calls) == 6
        assert roles.count("diagnostician") == 4
        assert roles.count("orchestrator") == 1
        assert roles.count("executor") == 1
        # Each turn's persisted evidence turn carries the same role as its audit
        # event (the two SPEC-075/SPEC-025 seams agree off the one bound role).
        for call in kernel.calls:
            assert call.turn.model_dump()["agent_role"] == call.event["agent_role"]
        # The executor proposal is the final turn, on the derived staging session.
        final = kernel.calls[-1]
        assert final.event["agent_role"] == "executor"
        assert final.session_id == "ses-attr::orch::staging"

    def test_staged_proposal_parks_with_executor_provenance_and_never_dispatches(
        self,
    ):
        profile = get_profile("k8s-pod-degradation")
        kernel = ConversationalAttributionFakeKernel(_settings())
        _run(
            run_conversational_remediation(
                kernel,
                profile=profile,
                goal="g",
                session_id="ses-attr2",
                user_name="alice",
                bearer_token="the-one-token",
            )
        )
        # Only the executor turn parks; the card carries the SPEC-073 R-4
        # staged_by_role provenance and nothing dispatches (R-2: the team proposes,
        # a distinct human disposes through the existing signed worker).
        parked = [c for c in kernel.calls if c.pending is not None]
        assert len(parked) == 1
        assert parked[0].pending.staged_by_role == "executor"
        assert parked[0].event["agent_role"] == "executor"
        assert kernel.dispatches == []
        # The read-only fan-out (diagnostician members + orchestrator synthesis)
        # never parks a mutating call.
        assert all(
            c.pending is None
            for c in kernel.calls
            if c.event["agent_role"] != "executor"
        )

    def test_conversational_attribution_one_human_one_token_no_new_event_type(self):
        profile = get_profile("post-deploy-verify")  # 3 steps + a shape
        kernel = ConversationalAttributionFakeKernel(_settings())
        _run(
            run_conversational_remediation(
                kernel,
                profile=profile,
                goal="verify then roll back the bad deploy",
                session_id="ses-attr3",
                user_name="alice",
                bearer_token="the-one-token",
            )
        )
        assert kernel.calls
        # Attributable to the same human + the one delegated token across every
        # hop (R-4): no member mints a second identity edge or a second token.
        assert all(c.user_name == "alice" for c in kernel.calls)
        assert all(c.bearer_token == "the-one-token" for c in kernel.calls)
        # No unscoped (None) agent_role leaks on the live conversational path: the
        # dimension is present and populated on every turn of the run.
        assert all("agent_role" in c.event for c in kernel.calls)
        assert all(c.event["agent_role"] is not None for c in kernel.calls)
        # No new event_type is minted for the conversational bridge: the closed
        # enum is reused verbatim (here the existing execution_requested seam).
        assert {c.event["event_type"] for c in kernel.calls} == {
            "execution_requested"
        }
        # The role is process-local and restored once the composition unwinds.
        assert current_agent_role_value() is None

