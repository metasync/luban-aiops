"""SPEC-078 Stage 4 (R-3 / FU-076-c / OQ-5): the in-process ``agent_roles_any`` axis.

The canonical bundle (``policy-default.yaml``, byte-unchanged here) already carries
the SPEC-074/076 agent-role axis — ``deny-diagnostician-tools-mutate`` and
``require-approval-executor-tools-mutate`` — but those rules stay **ready-but-inert**
on the deployed path because SPEC-073 R-3 keeps the bound role off every wire field,
so no gateway ``evaluate()`` ever threads a non-``None`` ``agent_role``. Stage 4 makes
the axis **fire in-process** at the executor-staging seam: ``_enforce_staging_role_axis``
reads the bound role from the process-local ``AGENT_ROLE`` contextvar (never a wire
field) and fails closed unless it is the canonical staging role.

These tests prove the four things R-3's acceptance names:

* the axis is **evaluated and enforced** — an ``executor`` may stage the mutating
  proposal; a ``diagnostician``/``orchestrator`` (or an unscoped ``None``) may not,
  failing closed rather than widening;
* the axis is genuinely **wired at the seam** — ``stage_remediation`` calls it inside
  the executor scope before any park, so a denial blocks staging before ``reply_text``;
* the role **never crosses a wire field** — the staging ``reply_text`` carries no
  ``agent_role`` kwarg and ``stage_remediation`` never forwards one (the schema
  byte-freeze + no-``agent_role``-on-wire guards live in ``test_contract_parity.py``);
* the in-process set **cannot drift** from the policy layer — ``_STAGING_AGENT_ROLES``
  is pinned to the canonical bundle's executor rule (and its diagnostician deny rule
  keeps ``diagnostician`` out), so the seam mirrors ``evaluate()`` rather than
  inventing a third, divergent engine.
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

import pytest
import yaml

from agent_service.runtime_kernel import BlockingReply
from agent_service.runtime_settings import RuntimeSettings
from agent_service.services import orchestration
from agent_service.services.agent_role import (
    AgentRole,
    agent_role_scope,
    current_agent_role_value,
)
from agent_service.services.hitl_confirmations import PendingConfirmation
from agent_service.services.orchestration import (
    _STAGING_AGENT_ROLES,
    AgentRoleAxisDenial,
    DiagnosisProfile,
    _enforce_staging_role_axis,
    stage_remediation,
)

_ROOT = Path(__file__).resolve().parents[3]
_POLICY_BUNDLE = (
    _ROOT / "shared" / "shared-contracts" / "policies" / "policy-default.yaml"
)


def _settings(**kwargs) -> RuntimeSettings:
    return RuntimeSettings(
        api_key="test-key", tool_gateway_url="http://gw:8080", **kwargs
    )


def _run(coro):
    return asyncio.run(coro)


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


class _AxisCall:
    def __init__(self, role, session_id, read_only, kwargs, pending):
        self.role = role
        self.session_id = session_id
        self.read_only = read_only
        self.kwargs = kwargs
        self.pending = pending


class AxisStagingFakeKernel:
    """Mimics the kernel's mutating-call park (runtime_kernel:1874/1899) **and**
    records every kwarg handed to ``reply_text``.

    The park labels the staging role from the bound ``AGENT_ROLE`` (line 1899) and
    never dispatches; the ``**kwargs`` capture lets the wire tests assert no
    ``agent_role`` crosses the seam. ``reply_text`` deliberately takes ``**kwargs``
    (not a fixed signature) so a smuggled ``agent_role=`` would be recorded, not
    swallowed by a TypeError — the test wants to *see* the wire surface.
    """

    def __init__(self, settings):
        self.settings = settings
        self.calls: list[_AxisCall] = []
        self.dispatches: list = []

    async def reply_text(self, **kwargs):
        pending = PendingConfirmation(
            confirm_id=f"cf::{kwargs['session_id']}",
            session_id=kwargs["session_id"],
            user_id=kwargs["user_name"],
            reply_id="r1",
        )
        pending.staged_by_role = current_agent_role_value()
        self.calls.append(
            _AxisCall(
                role=current_agent_role_value(),
                session_id=kwargs["session_id"],
                read_only=kwargs.get("read_only", False),
                kwargs=kwargs,
                pending=pending,
            )
        )
        return BlockingReply(f"parked::{kwargs['session_id']}")

    async def dispatch(self, pending):  # pragma: no cover - staging never calls it
        self.dispatches.append(pending)


# ---------------------------------------------------------------------------
# R-3: the axis is evaluated and enforced — executor may stage, others may not.
# ---------------------------------------------------------------------------
class TestStagingRoleAxisEnforcement:
    def test_executor_passes_the_axis(self):
        # The canonical staging role: an executor may propose the mutating tool.
        with agent_role_scope(AgentRole.EXECUTOR):
            assert _enforce_staging_role_axis() == "executor"

    def test_diagnostician_is_denied_fail_closed(self):
        # A read-only diagnostician can never stage a mutation (R-3 / R-4).
        with agent_role_scope(AgentRole.DIAGNOSTICIAN):
            with pytest.raises(AgentRoleAxisDenial) as exc:
                _enforce_staging_role_axis()
        assert exc.value.role == "diagnostician"

    def test_orchestrator_is_denied_fail_closed(self):
        # The orchestrator delegates and holds no tools, so it may not stage either.
        with agent_role_scope(AgentRole.ORCHESTRATOR):
            with pytest.raises(AgentRoleAxisDenial) as exc:
                _enforce_staging_role_axis()
        assert exc.value.role == "orchestrator"

    def test_unscoped_is_denied_fail_closed(self):
        # The critical default: an unscoped turn (agent_role None — today's single-
        # agent path) is NOT admitted to stage. Fail-closed means the axis never
        # widens to a more permissive posture when no role is bound.
        assert current_agent_role_value() is None
        with pytest.raises(AgentRoleAxisDenial) as exc:
            _enforce_staging_role_axis()
        assert exc.value.role is None

    def test_denial_carries_a_stable_code_not_prose(self):
        # The message is a stable code so tests/telemetry match it without
        # asserting on human prose (mirrors AgentRoleError's contract).
        with pytest.raises(AgentRoleAxisDenial, match="agent_role_axis_denied"):
            _enforce_staging_role_axis()


# ---------------------------------------------------------------------------
# R-3: the axis is genuinely wired at the executor-staging seam.
# ---------------------------------------------------------------------------
class TestAxisWiredAtStagingSeam:
    def test_executor_staging_fires_the_axis_and_parks(self):
        # On the live path stage_remediation binds the executor, so the axis fires
        # and passes: the proposal parks (never dispatches) with the SPEC-073 R-4
        # staged_by_role provenance.
        kernel = AxisStagingFakeKernel(_settings())
        reply = _run(
            stage_remediation(
                kernel,
                profile=_remediation_profile(),
                goal="g",
                diagnosis="pod is crash-looping",
                session_id="ses-60",
                user_name="alice",
                bearer_token="tok",
            )
        )
        content, _structured = reply
        assert content == "parked::ses-60::orch::staging"
        assert len(kernel.calls) == 1
        assert kernel.calls[0].role == "executor"
        assert kernel.calls[0].read_only is False
        assert kernel.calls[0].pending.staged_by_role == "executor"
        assert kernel.dispatches == []
        # The role is process-local and restored once the step unwinds.
        assert current_agent_role_value() is None

    def test_axis_denial_blocks_staging_before_any_park(self, monkeypatch):
        # Prove the seam actually calls the axis before reply_text: if the axis
        # denies, staging propagates the denial and parks nothing (no executor turn
        # is opened, no card is registered, nothing dispatches).
        def _boom() -> str:
            raise AgentRoleAxisDenial("diagnostician")

        monkeypatch.setattr(orchestration, "_enforce_staging_role_axis", _boom)
        kernel = AxisStagingFakeKernel(_settings())
        with pytest.raises(AgentRoleAxisDenial):
            _run(
                stage_remediation(
                    kernel,
                    profile=_remediation_profile(),
                    goal="g",
                    diagnosis="d",
                    session_id="ses-61",
                    user_name="alice",
                    bearer_token="tok",
                )
            )
        assert kernel.calls == []
        assert kernel.dispatches == []

    def test_stage_remediation_source_calls_the_axis(self):
        # Source-level complement to the runtime proof above: the axis call is
        # present in stage_remediation, so it cannot be silently removed without
        # this test failing.
        src = inspect.getsource(stage_remediation)
        assert "_enforce_staging_role_axis()" in src


# ---------------------------------------------------------------------------
# R-3: the bound role never crosses a wire field at the staging seam.
# ---------------------------------------------------------------------------
class TestRoleNeverCrossesTheWire:
    def test_staging_reply_text_carries_no_agent_role_kwarg(self):
        # The park turn forwards the delegated token + the prompt, never the role:
        # the axis reads the role from the process-local contextvar, so it is not a
        # reply_text argument and cannot leak onto the gateway wire.
        kernel = AxisStagingFakeKernel(_settings())
        _run(
            stage_remediation(
                kernel,
                profile=_remediation_profile(),
                goal="g",
                diagnosis="d",
                session_id="ses-62",
                user_name="alice",
                bearer_token="the-one-token",
            )
        )
        kwargs = kernel.calls[0].kwargs
        assert "agent_role" not in kwargs
        # Sanity: the seam did forward the token + read_only=False (belt-and-braces
        # that we inspected the real staging call, not an empty capture).
        assert kwargs["bearer_token"] == "the-one-token"
        assert kwargs["read_only"] is False

    def test_stage_remediation_source_never_forwards_a_role(self):
        # No ``agent_role=`` anywhere in the staging step: the role is bound via
        # agent_role_scope (process-local) and read via the contextvar, never
        # passed as a wire-facing argument (SPEC-073 R-3; the multi-agent wire
        # frame is phase 6).
        src = inspect.getsource(stage_remediation)
        assert "agent_role=" not in src


# ---------------------------------------------------------------------------
# R-3: the in-process staging set is pinned to the canonical bundle (no drift).
# ---------------------------------------------------------------------------
class TestStagingRolesPinnedToCanonicalBundle:
    @staticmethod
    def _rules_by_id() -> dict[str, dict]:
        doc = yaml.safe_load(_POLICY_BUNDLE.read_text())
        return {rule["id"]: rule for rule in doc["rules"]}

    def test_staging_roles_equal_the_bundle_executor_rule(self):
        # The in-process axis mirrors the canonical executor rule's agent_roles_any
        # exactly, so the seam cannot drift from the policy layer it complements.
        rules = self._rules_by_id()
        executor_rule = rules["require-approval-executor-tools-mutate"]
        bundle_roles = frozenset(executor_rule["match"]["agent_roles_any"])
        assert _STAGING_AGENT_ROLES == bundle_roles

    def test_staging_roles_are_exactly_the_closed_executor_value(self):
        # And that set is exactly the closed-vocabulary executor value — one role,
        # the AgentRole enum member, so the axis admits no synthetic/unknown role.
        assert _STAGING_AGENT_ROLES == frozenset({AgentRole.EXECUTOR.value})
        assert _STAGING_AGENT_ROLES == frozenset({"executor"})

    def test_diagnostician_deny_rule_keeps_diagnostician_out_of_staging(self):
        # The complementary deny rule pins diagnostician as the denied role; the
        # in-process set must exclude it, proving the seam enforces the same
        # executor-allowed / diagnostician-denied split the bundle declares.
        rules = self._rules_by_id()
        deny_rule = rules["deny-diagnostician-tools-mutate"]
        assert frozenset(deny_rule["match"]["agent_roles_any"]) == frozenset(
            {"diagnostician"}
        )
        assert "diagnostician" not in _STAGING_AGENT_ROLES
        # Every closed role the bundle denies or leaves inert is out; only the
        # executor staging role is in.
        for role in AgentRole:
            if role is AgentRole.EXECUTOR:
                assert role.value in _STAGING_AGENT_ROLES
            else:
                assert role.value not in _STAGING_AGENT_ROLES
