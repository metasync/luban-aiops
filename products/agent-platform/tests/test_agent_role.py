"""SPEC-073 phase-2 tests: role-scoped agent identity & authority.

Phase 2 ships an **inert substrate**: these tests prove the role-narrowing and
identity-preservation seams over unit/contract assertions with **no
orchestration caller** and **no change to the deployed single-agent path**.
"""

import asyncio
import inspect
import json
from pathlib import Path

import pytest

from agent_service.runtime_kernel import AgentKernel
from agent_service.runtime_settings import RuntimeSettings
from agent_service.schemas.v2 import EvidenceAgentRole, EvidenceTurn
from agent_service.services.agent_role import (
    AGENT_ROLE,
    AgentRole,
    AgentRoleError,
    agent_role_scope,
    coerce_agent_role,
    current_agent_role,
    current_agent_role_value,
)
from agent_service.services.confirmation_records import make_record
from agent_service.services.delegated_identity import (
    DECIDER_IDENTITY,
    REQUESTER_IDENTITY,
)
from agent_service.services.hitl_confirmations import PendingConfirmation
from agent_service.tools.gateway_tools import DELEGATED_TOKEN

# repo root: tests -> agent-platform -> products -> <repo>
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCHEMA_DIR = _REPO_ROOT / "shared" / "shared-contracts" / "schemas"

_READ_TOOL = {
    "name": "k8s.list_pods",
    "description": "x",
    "risk_level": "read",
    "parameters_schema": {"type": "object"},
}
_WRITE_TOOL = {
    "name": "k8s.delete_pod",
    "description": "x",
    "risk_level": "write",
    "parameters_schema": {"type": "object"},
}


def _kernel() -> AgentKernel:
    return AgentKernel(
        settings=RuntimeSettings(
            api_key="test-key",
            tool_gateway_url="http://gw:8080",
        )
    )


def _names(definitions: list[dict]) -> set[str]:
    return {d["name"] for d in definitions}


# ---------------------------------------------------------------------------
# R-1: a closed, platform-owned agent-role vocabulary
# ---------------------------------------------------------------------------
class TestRoleVocabulary:
    def test_exactly_three_closed_values(self):
        assert {r.value for r in AgentRole} == {
            "diagnostician",
            "orchestrator",
            "executor",
        }

    def test_role_reduces_to_plain_platform_string(self):
        # A role serializes to a plain str with no agentscope involvement.
        assert isinstance(AgentRole.EXECUTOR.value, str)
        assert AgentRole.DIAGNOSTICIAN.value == "diagnostician"

    def test_module_imports_no_agentscope(self):
        import agent_service.services.agent_role as mod

        source = Path(inspect.getsourcefile(mod)).read_text()
        # No agentscope *import* (gate point 4). The docstring may name the word
        # in prose; only an actual import would leak an agentscope type.
        assert "import agentscope" not in source
        assert "from agentscope" not in source
        assert not any(
            name.startswith("agentscope") for name in vars(mod)
        )

    @pytest.mark.parametrize(
        "bad", ["admin", "EXECUTOR", "", "approver", "planner", 123, object(), None]
    )
    def test_out_of_set_construction_fails_closed(self, bad):
        # Rejected, never coerced to a wider posture (R-1/R-5). "planner" and
        # "approver" are explicitly not roles (OQ-1).
        with pytest.raises(AgentRoleError):
            coerce_agent_role(bad)

    def test_coerce_accepts_enum_and_exact_value(self):
        assert coerce_agent_role(AgentRole.EXECUTOR) is AgentRole.EXECUTOR
        assert coerce_agent_role("executor") is AgentRole.EXECUTOR

    def test_bound_role_is_immutable_for_the_scope_and_restores(self):
        # Default is unscoped; the bracket fixes the role, cannot be widened
        # from inside, and restores the prior context on exit (R-1).
        assert current_agent_role() is None
        with agent_role_scope(AgentRole.DIAGNOSTICIAN) as role:
            assert role is AgentRole.DIAGNOSTICIAN
            assert current_agent_role() is AgentRole.DIAGNOSTICIAN
            # A nested scope for a different role does not leak outward.
            with agent_role_scope(AgentRole.EXECUTOR):
                assert current_agent_role() is AgentRole.EXECUTOR
            assert current_agent_role() is AgentRole.DIAGNOSTICIAN
        assert current_agent_role() is None

    def test_scope_fails_closed_before_opening_on_bad_role(self):
        with pytest.raises(AgentRoleError):
            with agent_role_scope("admin"):
                pass  # pragma: no cover - never entered
        assert current_agent_role() is None


# ---------------------------------------------------------------------------
# R-2: per-role toolkit narrowing at the existing seam
# ---------------------------------------------------------------------------
class TestRoleToolkitNarrowing:
    def test_narrow_diagnostician_is_read_only(self):
        kept = _kernel()._narrow_for_role([_READ_TOOL, _WRITE_TOOL], AgentRole.DIAGNOSTICIAN)
        assert _names(kept) == {"k8s.list_pods"}

    def test_narrow_executor_sees_full_set(self):
        kept = _kernel()._narrow_for_role([_READ_TOOL, _WRITE_TOOL], AgentRole.EXECUTOR)
        assert _names(kept) == {"k8s.list_pods", "k8s.delete_pod"}

    def test_narrow_orchestrator_has_no_gateway_tools(self):
        kept = _kernel()._narrow_for_role([_READ_TOOL, _WRITE_TOOL], AgentRole.ORCHESTRATOR)
        assert kept == []

    def test_narrowing_is_subtractive_only_subset_of_unscoped(self):
        kernel = _kernel()
        universe = [_READ_TOOL, _WRITE_TOOL]
        for role in AgentRole:
            assert _names(kernel._narrow_for_role(universe, role)) <= _names(universe)

    def test_ensure_toolkit_splits_cache_per_role(self, monkeypatch):
        kernel = _kernel()

        async def fake_discover(gateway_url, bearer_token=None):
            return [dict(_READ_TOOL), dict(_WRITE_TOOL)]

        monkeypatch.setattr(
            "agent_service.tools.gateway_tools.discover_tools", fake_discover
        )

        unscoped = asyncio.run(kernel._ensure_toolkit("token-a"))
        with agent_role_scope(AgentRole.DIAGNOSTICIAN):
            diagnostician = asyncio.run(kernel._ensure_toolkit("token-a"))
        with agent_role_scope(AgentRole.EXECUTOR):
            executor = asyncio.run(kernel._ensure_toolkit("token-a"))
        with agent_role_scope(AgentRole.ORCHESTRATOR):
            orchestrator = asyncio.run(kernel._ensure_toolkit("token-a"))

        assert kernel._count_gateway_tools(unscoped) == 2
        assert kernel._count_gateway_tools(diagnostician) == 1
        assert kernel._count_gateway_tools(executor) == 2
        assert kernel._count_gateway_tools(orchestrator) == 0
        # Distinct roles -> distinct cache entries, never shared.
        assert len({id(unscoped), id(diagnostician), id(executor), id(orchestrator)}) == 4

    def test_unscoped_turn_keeps_one_stable_cache_entry(self, monkeypatch):
        # The deployed single-agent path: no role bound -> today's exact key and
        # one reused toolkit object, byte-identical (R-5 inertness).
        kernel = _kernel()
        calls = []

        async def fake_discover(gateway_url, bearer_token=None):
            calls.append(bearer_token)
            return [dict(_READ_TOOL), dict(_WRITE_TOOL)]

        monkeypatch.setattr(
            "agent_service.tools.gateway_tools.discover_tools", fake_discover
        )

        assert current_agent_role() is None
        first = asyncio.run(kernel._ensure_toolkit("token-a"))
        second = asyncio.run(kernel._ensure_toolkit("token-a"))
        assert first is second
        assert calls == ["token-a"]
        assert kernel._count_gateway_tools(first) == 2


# ---------------------------------------------------------------------------
# R-3: same-token identity preservation ("on whose behalf")
# ---------------------------------------------------------------------------
class TestSameTokenIdentityPreservation:
    def test_scope_touches_only_agent_role(self):
        # The bracket must never mint/alter a second identity edge: the delegated
        # token and the SPEC-070 requester/decider identities are untouched.
        token = object()
        requester = object()
        decider = object()
        t_tok = DELEGATED_TOKEN.set(token)
        t_req = REQUESTER_IDENTITY.set(requester)
        t_dec = DECIDER_IDENTITY.set(decider)
        try:
            with agent_role_scope(AgentRole.EXECUTOR):
                assert DELEGATED_TOKEN.get() is token
                assert REQUESTER_IDENTITY.get() is requester
                assert DECIDER_IDENTITY.get() is decider
                assert current_agent_role() is AgentRole.EXECUTOR
            # unchanged after the hop too
            assert DELEGATED_TOKEN.get() is token
            assert REQUESTER_IDENTITY.get() is requester
            assert DECIDER_IDENTITY.get() is decider
        finally:
            DELEGATED_TOKEN.reset(t_tok)
            REQUESTER_IDENTITY.reset(t_req)
            DECIDER_IDENTITY.reset(t_dec)

    def test_role_value_is_plain_string_never_a_wire_type(self):
        assert current_agent_role_value() is None
        with agent_role_scope(AgentRole.DIAGNOSTICIAN):
            value = current_agent_role_value()
        assert value == "diagnostician"
        assert type(value) is str


# ---------------------------------------------------------------------------
# R-4: authority-provenance labeling on a role-staged mutation
# ---------------------------------------------------------------------------
class TestStagedByRoleProvenance:
    def _pending(self) -> PendingConfirmation:
        return PendingConfirmation(
            confirm_id="c1", session_id="s1", user_id="u1", reply_id="r1"
        )

    def test_staged_by_role_defaults_none_and_is_settable(self):
        pending = self._pending()
        assert pending.staged_by_role is None
        with agent_role_scope(AgentRole.EXECUTOR):
            pending.staged_by_role = current_agent_role_value()
        assert pending.staged_by_role == "executor"

    def test_unscoped_park_leaves_staged_by_role_none(self):
        pending = self._pending()
        pending.staged_by_role = current_agent_role_value()
        assert pending.staged_by_role is None

    def test_durable_record_never_carries_role_provenance(self):
        # R-4: provenance stays kernel-internal in phase 2 — make_record has no
        # role parameter and emits no role field.
        assert "staged_by_role" not in inspect.signature(make_record).parameters
        record = make_record(
            confirm_id="c1",
            session_id="s1",
            owner_user_id="u1",
            pending_calls=[],
            action="write",
        )
        assert "staged_by_role" not in record
        assert "staged_by_role" not in json.dumps(record)

    def test_contract_schemas_unchanged_no_role_field(self):
        for name in ("execution-request.schema.json", "agent-stream-event.schema.json"):
            text = (_SCHEMA_DIR / name).read_text()
            assert "staged_by_role" not in text
            assert "agent_role" not in text


# ---------------------------------------------------------------------------
# R-5: fail-closed invariants and four-point-gate parity
# ---------------------------------------------------------------------------
class TestFailClosedAndInertness:
    def test_unrecognized_role_fails_closed_to_no_tools(self):
        # Defensive branch: a non-enum value never widens authority.
        kept = _kernel()._narrow_for_role([_READ_TOOL, _WRITE_TOOL], "bogus")  # type: ignore[arg-type]
        assert kept == []

    def test_default_context_is_unscoped(self):
        assert AGENT_ROLE.get() is None
        assert current_agent_role() is None

    def test_only_the_orchestration_frame_binds_a_role(self):
        # Reachability guard (SPEC-073 R-5, updated by SPEC-076 R-2): phase 2
        # asserted *no* caller binds a role; phase 5 wires exactly one producer.
        # The only sources that may open a role scope are agent_role.py (which
        # *defines* the bracket) and services/orchestration.py (the bounded
        # read-only orchestration frame). No other deployed path — chat, triage,
        # documents, skills, the kernel turn runner — may bind a role, so the
        # unscoped single-agent turn stays byte-identical and current_agent_role()
        # is None everywhere off the orchestration path.
        src_root = Path(__file__).resolve().parents[1] / "src" / "agent_service"
        allowed = {"agent_role.py", str(Path("services") / "orchestration.py")}
        offenders = []
        binders = []
        for path in src_root.rglob("*.py"):
            rel = str(path.relative_to(src_root))
            if path.name in allowed or rel in allowed:
                if path.name != "agent_role.py":
                    binders.append(rel)
                continue
            text = path.read_text()
            if "agent_role_scope(" in text or "AGENT_ROLE.set(" in text:
                offenders.append(rel)
        assert offenders == []
        # The orchestration frame is wired (phase 5 is live), and it is the only
        # non-definition binder.
        assert binders == [str(Path("services") / "orchestration.py")]


# ---------------------------------------------------------------------------
# SPEC-075 (phase 4): audit & attribution — the inert ``agent_role`` dimension
# ---------------------------------------------------------------------------
class TestSpec075AuditAttribution:
    """Phase-4 guards for the additive ``agent_role`` attribution dimension.

    A deliberate clone of SPEC-070's ``delegation_mode``: one closed vocabulary
    shared by the audit-event and session-evidence contracts and the SPEC-073
    seed, wired into the emitter seam yet **inert** — no deployed caller binds a
    role until phase 5, so every unscoped event/turn audits byte-identically.

    Four-point-gate mapping (plan R-5): **point 1 (audit) strengthened** — the
    trail gains a which-role-acted dimension; **point 2 (identity) unchanged** —
    the role is a label beside the one delegated token, never a new
    principal/claim/identity edge; **point 3 (read-only posture) unchanged** —
    attribution narrows no authority (the prescriptive axis is SPEC-074);
    **point 4 (no agentscope types) unchanged** — a plain string enum on the v2
    contract.
    """

    def test_agent_role_enum_lockstep_across_contracts(self):
        # The attribution dimension cannot drift from the identity/policy
        # vocabulary: the SPEC-073 enum, the evidence-turn Literal, and every
        # contract schema carrying agent_role enumerate exactly one closed set.
        expected = {r.value for r in AgentRole}
        assert expected == {"diagnostician", "orchestrator", "executor"}
        assert (
            set(getattr(EvidenceAgentRole, "__args__", EvidenceAgentRole)) == expected
        )

        audit_event = json.loads((_SCHEMA_DIR / "audit-event.schema.json").read_text())
        assert set(audit_event["properties"]["agent_role"]["enum"]) == expected

        session_evidence = json.loads(
            (_SCHEMA_DIR / "session-evidence.schema.json").read_text()
        )
        assert set(session_evidence["properties"]["agent_role"]["enum"]) == expected

        agent_session = json.loads(
            (_SCHEMA_DIR / "agent-session.schema.json").read_text()
        )
        turn_item = agent_session["properties"]["evidence_turns"]["items"]
        assert set(turn_item["properties"]["agent_role"]["enum"]) == expected

    def test_agent_role_enum_lockstep_guard_fires_on_drift(self):
        # Sensitivity: prove the lockstep assertion is not vacuously true. A
        # contract that grew a value the vocabulary lacks ("planner"/"approver"
        # are explicitly not roles — OQ-1) or dropped one is the drift it catches.
        expected = {r.value for r in AgentRole}
        audit_event = json.loads((_SCHEMA_DIR / "audit-event.schema.json").read_text())
        contract = set(audit_event["properties"]["agent_role"]["enum"])
        assert contract == expected
        assert contract | {"planner"} != expected
        assert contract - {"executor"} != expected

    def test_evidence_turn_omits_agent_role_when_unscoped(self):
        # The evidence-turn serializer mirrors AuditEvent._omit_unknown_delegation:
        # an unscoped turn drops the key entirely (never null), so a legacy turn
        # replays byte-identically; a scoped turn projects the role verbatim.
        unscoped = EvidenceTurn(turn_index=0, request_id="req-1", frames=[])
        assert unscoped.agent_role is None
        assert "agent_role" not in unscoped.model_dump()
        assert "agent_role" not in json.loads(unscoped.model_dump_json())

        scoped = EvidenceTurn(
            turn_index=0, request_id="req-1", agent_role="executor", frames=[]
        )
        assert scoped.model_dump()["agent_role"] == "executor"
        assert json.loads(scoped.model_dump_json())["agent_role"] == "executor"

    def test_emitter_seam_threads_the_inert_seed(self):
        # R-5 seam (OQ-2): the deployed agent-platform audit call sites thread
        # current_agent_role_value() into the envelope. Composed with
        # test_only_the_orchestration_frame_binds_a_role, the seed is None on
        # every path except the SPEC-076 orchestration frame — the reachability
        # guarantee, audit-side (SPEC-075 goes live in phase 5, not before).
        src_root = Path(__file__).resolve().parents[1] / "src" / "agent_service"
        wired = [
            str(path.relative_to(src_root))
            for path in src_root.rglob("*.py")
            if "agent_role=current_agent_role_value()" in path.read_text()
        ]
        assert wired, "expected the emitter seam to thread current_agent_role_value()"

    def test_unscoped_emitter_event_is_byte_identical(self):
        # No-diff (plan L154): fed the unscoped seed, build_audit_event yields
        # exactly the historical envelope — no agent_role key — while a scoped role
        # would project, proving the seam is live yet never bound today.
        from agent_service.services import audit_emitter

        assert current_agent_role_value() is None
        event = audit_emitter.build_audit_event(
            "execution_requested",
            "req-1",
            "success",
            agent_role=current_agent_role_value(),
        )
        assert "agent_role" not in event
        assert set(event) == {
            "event_id",
            "occurred_at",
            "event_type",
            "service",
            "request_id",
            "outcome",
            "details",
        }
        with agent_role_scope(AgentRole.EXECUTOR):
            scoped = audit_emitter.build_audit_event(
                "execution_requested",
                "req-1",
                "success",
                agent_role=current_agent_role_value(),
            )
        assert scoped["agent_role"] == "executor"
