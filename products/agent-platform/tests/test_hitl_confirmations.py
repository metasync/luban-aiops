"""SPEC-020 R-2: HITL confirmation bridging — registry, kernel, routes."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest
from agentscope.event import (
    RequireUserConfirmEvent,
    UserConfirmResultEvent,
    UserInterruptEvent,
)
from agentscope.message import ToolCallBlock
from fastapi.testclient import TestClient

from agent_service.api.v2 import routes as v2_routes
from agent_service.app import create_app
from agent_service.runtime_kernel import AgentKernel
from agent_service.runtime_settings import RuntimeSettings
from agent_service.services import session_service
from agent_service.services.confirmation_records import (
    CONFIRMATION_RECORD_STORE,
    make_record,
)
from agent_service.services.execution_records import EXECUTION_RECORD_STORE
from agent_service.services.execution_signing import (
    canonical_digest,
    verify_envelope,
)
from agent_service.services.hitl_confirmations import (
    CONFIRMATION_REGISTRY,
    ConfirmationExpired,
    ConfirmationNotFound,
    ConfirmationRegistry,
)
from agent_service.services.kernel_middleware import TOOL_EVIDENCE_SINK
from agent_service.services.runtime_dependencies import get_runtime_kernel
from agent_service.tools.gateway_tools import (
    EXECUTION_REJECTION,
    EXECUTION_REQUESTS,
)

TOOL_CALL = ToolCallBlock(
    id="call-1", name="k8s.restart_service", input='{"namespace": "ops"}'
)

# Parked tool calls carry the model-visible sanitized name (dots become
# underscores); the gateway canonical name must be restored in payloads.
SANITIZED_TOOL_CALL = ToolCallBlock(
    id="call-2", name="k8s_delete_pod", input='{"name": "web-1"}'
)


def _park_event() -> RequireUserConfirmEvent:
    return RequireUserConfirmEvent(reply_id="reply-1", tool_calls=[TOOL_CALL])


@pytest.fixture(autouse=True)
def _clean_registry():
    CONFIRMATION_REGISTRY._by_session.clear()
    records = getattr(CONFIRMATION_RECORD_STORE, "_by_confirm_id", None)
    if records is not None:
        records.clear()
    executions = getattr(EXECUTION_RECORD_STORE, "_by_key", None)
    if executions is not None:
        executions.clear()
    yield
    CONFIRMATION_REGISTRY._by_session.clear()
    if records is not None:
        records.clear()
    if executions is not None:
        executions.clear()


def _configured_kernel(**overrides) -> AgentKernel:
    settings = RuntimeSettings(api_key="test-key", **overrides)
    return AgentKernel(settings=settings)


def _drain(async_iter) -> list:
    async def _collect():
        return [frame async for frame in async_iter]

    return asyncio.run(_collect())


class FakeUserMsg:
    def __init__(self, name: str, content: str) -> None:
        self.name = name
        self.content = content


class FakeAgent:
    """Records reply_stream inputs and yields scripted events."""

    def __init__(self, events: list | None = None, raise_on_stream: bool = False):
        self.events = events if events is not None else []
        self.raise_on_stream = raise_on_stream
        self.inputs: list = []
        # SPEC-021 R-3: parked confirmations snapshot risk tiers from the
        # toolkit; tests default to no toolkit (no risk_level on frames).
        self.toolkit = None

    async def reply_stream(self, inputs):
        self.inputs.append(inputs)
        if self.raise_on_stream:
            raise RuntimeError("boom")
        for event in self.events:
            yield event


def _patch_agent(monkeypatch, kernel: AgentKernel, agent: FakeAgent) -> None:
    async def fake_ensure_agent(session_id, bearer_token=None, model_id=None):
        return agent, FakeUserMsg, model_id or kernel.settings.provider

    monkeypatch.setattr(kernel, "ensure_agent", fake_ensure_agent)
    monkeypatch.setattr(kernel, "_snapshot_state", lambda session_id, agent: None)


# --- Registry semantics ---


def test_registry_register_get_resolve_roundtrip() -> None:
    registry = ConfirmationRegistry()
    pending = registry.register("s1", "alice", "r1", [TOOL_CALL], timeout=600)
    assert registry.is_parked("s1", 600)
    assert registry.get("s1", pending.confirm_id, 600) is pending
    registry.resolve("s1", pending.confirm_id)
    assert not registry.is_parked("s1", 600)
    with pytest.raises(ConfirmationNotFound):
        registry.get("s1", pending.confirm_id, 600)


def test_registry_get_rejects_unknown_resolved_and_foreign_ids() -> None:
    registry = ConfirmationRegistry()
    pending = registry.register("s1", "alice", "r1", [TOOL_CALL], timeout=600)
    with pytest.raises(ConfirmationNotFound):
        registry.get("s1", "other-id", 600)
    with pytest.raises(ConfirmationNotFound):
        registry.get("s2", pending.confirm_id, 600)


def test_registry_expired_entry_stays_observable_until_closed() -> None:
    registry = ConfirmationRegistry()
    pending = registry.register("s1", "alice", "r1", [TOOL_CALL], timeout=600)
    pending.created_at = time.monotonic() - 601
    with pytest.raises(ConfirmationExpired):
        registry.get("s1", pending.confirm_id, 600)
    # Expiry never silently evicts: the entry stays parked until
    # expire_confirmation interrupts the parked reply and resolves it.
    assert registry.is_parked("s1", 600)
    assert registry.peek_parked("s1") is pending


def test_registry_expiry_unlocks_session_for_new_parking() -> None:
    registry = ConfirmationRegistry()
    stale = registry.register("s1", "alice", "r1", [TOOL_CALL], timeout=600)
    stale.created_at = time.monotonic() - 601
    fresh = registry.register("s1", "alice", "r2", [TOOL_CALL], timeout=600)
    assert registry.get("s1", fresh.confirm_id, 600) is fresh


def test_registry_claim_makes_decisions_single_flight() -> None:
    registry = ConfirmationRegistry()
    pending = registry.register("s1", "alice", "r1", [TOOL_CALL], timeout=600)
    claimed = registry.claim("s1", pending.confirm_id, 600)
    assert claimed is pending
    # A duplicate confirm sees NotFound, while the session stays parked
    # (409 for new turns) until the resumed stream resolves the entry.
    with pytest.raises(ConfirmationNotFound):
        registry.claim("s1", pending.confirm_id, 600)
    with pytest.raises(ConfirmationNotFound):
        registry.get("s1", pending.confirm_id, 600)
    assert registry.is_parked("s1", 600)
    registry.resolve("s1", pending.confirm_id)
    assert not registry.is_parked("s1", 600)


def test_registry_take_for_expiry_is_single_flight() -> None:
    registry = ConfirmationRegistry()
    pending = registry.register("s1", "alice", "r1", [TOOL_CALL], timeout=600)
    pending.created_at = time.monotonic() - 601
    taken = registry.take_for_expiry("s1", pending.confirm_id)
    assert taken is pending
    assert pending.claimed
    # A concurrent expiry (or a decision claim) cannot take it twice.
    with pytest.raises(ConfirmationNotFound):
        registry.take_for_expiry("s1", pending.confirm_id)
    registry.resolve("s1", pending.confirm_id)


def test_registry_take_for_expiry_rejects_claimed_entry() -> None:
    registry = ConfirmationRegistry()
    pending = registry.register("s1", "alice", "r1", [TOOL_CALL], timeout=600)
    # A decision resume claimed while fresh; the resumed stream then
    # outlives the TTL. Expiry must not reach the claimed entry.
    registry.claim("s1", pending.confirm_id, 600)
    pending.created_at = time.monotonic() - 601
    with pytest.raises(ConfirmationNotFound):
        registry.take_for_expiry("s1", pending.confirm_id)
    assert registry.is_parked("s1", 600)


def test_pending_calls_payload_parses_tool_call_input() -> None:
    registry = ConfirmationRegistry()
    pending = registry.register("s1", "alice", "r1", [TOOL_CALL], timeout=600)
    payload = pending.pending_calls_payload()
    assert payload == [
        {
            "call_id": "call-1",
            "tool_name": "k8s.restart_service",
            "parameters": {"namespace": "ops"},
        }
    ]
    assert pending.tool_names() == ["k8s.restart_service"]


def test_pending_calls_payload_carries_known_risk_level() -> None:
    """SPEC-021 R-3: risk tiers snapshotted at park time ride the frames."""
    registry = ConfirmationRegistry()
    pending = registry.register(
        "s1", "alice", "r1", [TOOL_CALL], timeout=600,
        risk_levels={"k8s.restart_service": "write"},
    )
    payload = pending.pending_calls_payload()
    assert payload[0]["risk_level"] == "write"


def test_pending_calls_payload_omits_unknown_risk_level() -> None:
    registry = ConfirmationRegistry()
    pending = registry.register("s1", "alice", "r1", [TOOL_CALL], timeout=600)
    assert "risk_level" not in pending.pending_calls_payload()[0]


def test_pending_calls_payload_emits_gateway_canonical_name() -> None:
    """The parked call carries the sanitized model name; the payload must
    emit the dotted gateway canonical name so the signed execution
    envelope resolves at the gateway registry (TOOL_NOT_FOUND regression)."""
    registry = ConfirmationRegistry()
    pending = registry.register(
        "s1", "alice", "r1", [SANITIZED_TOOL_CALL], timeout=600,
        risk_levels={"k8s_delete_pod": "write"},
        gateway_names={"k8s_delete_pod": "k8s.delete_pod"},
    )
    payload = pending.pending_calls_payload()
    assert payload[0]["tool_name"] == "k8s.delete_pod"
    # The risk snapshot stays keyed by the sanitized model name.
    assert payload[0]["risk_level"] == "write"
    assert payload[0]["action"] == "tools:mutate"


def test_pending_calls_payload_keeps_unmapped_name() -> None:
    """Without a canonical mapping the parked name flows through as-is."""
    registry = ConfirmationRegistry()
    pending = registry.register(
        "s1", "alice", "r1", [SANITIZED_TOOL_CALL], timeout=600,
    )
    assert pending.pending_calls_payload()[0]["tool_name"] == "k8s_delete_pod"


def test_pending_calls_payload_carries_bridged_action() -> None:
    """SPEC-030 R-3: risk tiers map to the policy action the confirm
    bridge evaluates; calls without a gateway tier carry no action."""
    registry = ConfirmationRegistry()
    pending = registry.register(
        "s1", "alice", "r1", [TOOL_CALL], timeout=600,
        risk_levels={"k8s.restart_service": "write"},
    )
    assert pending.pending_calls_payload()[0]["action"] == "tools:mutate"


def test_highest_action_prefers_tools_mutate() -> None:
    registry = ConfirmationRegistry()
    pending = registry.register(
        "s1", "alice", "r1", [TOOL_CALL], timeout=600,
        risk_levels={"a.read": "read", "b.write": "write", "c.admin": "admin"},
    )
    assert pending.highest_action() == "tools:mutate"


def test_highest_action_none_without_risk_tiers() -> None:
    registry = ConfirmationRegistry()
    pending = registry.register("s1", "alice", "r1", [TOOL_CALL], timeout=600)
    assert pending.highest_action() is None


# --- Kernel: park on RequireUserConfirmEvent ---


def test_stream_events_parks_and_emits_confirmation_request(monkeypatch):
    kernel = _configured_kernel()
    agent = FakeAgent(
        events=[{"type": "TEXT_BLOCK_DELTA", "delta": "checking"}, _park_event()]
    )
    _patch_agent(monkeypatch, kernel, agent)

    frames = _drain(
        kernel.stream_events(
            message="restart it",
            request_id="req-1",
            session_id="s1",
            user_name="alice",
        )
    )
    confirmation_frames = [
        f for f in frames if f.get("type") == "confirmation_request"
    ]
    assert len(confirmation_frames) == 1
    frame = confirmation_frames[0]
    assert frame["pending_calls"][0]["tool_name"] == "k8s.restart_service"
    assert frame["message"] == "Tool execution requires your confirmation."
    # The stream ends without message_end after parking.
    assert not any(f.get("event") == "message_end" for f in frames)
    assert CONFIRMATION_REGISTRY.is_parked("s1", 600)
    # SPEC-033 R-1: the durable record carries the parking turn ordinal
    # (0 here — the fake agent has no prior context).
    record = CONFIRMATION_RECORD_STORE.load_pending_for_session("s1")
    assert record is not None
    assert record["turn_index"] == 0


def test_parked_record_carries_parking_turn_ordinal(monkeypatch):
    """SPEC-033 R-1: the record stores the same ordinal evidence uses."""
    kernel = _configured_kernel()
    agent = FakeAgent(events=[_park_event()])
    agent.state = SimpleNamespace(
        context=[
            SimpleNamespace(role="user"),
            SimpleNamespace(role="assistant"),
            SimpleNamespace(role="user"),
        ]
    )
    _patch_agent(monkeypatch, kernel, agent)

    _drain(
        kernel.stream_events(
            message="restart it",
            request_id="req-1",
            session_id="s1",
            user_name="alice",
        )
    )
    record = CONFIRMATION_RECORD_STORE.load_pending_for_session("s1")
    assert record["turn_index"] == 2


def test_confirmation_request_carries_risk_level(monkeypatch):
    """SPEC-021 R-3: parked mutating calls surface their risk tier."""
    from types import SimpleNamespace

    kernel = _configured_kernel()
    agent = FakeAgent(events=[_park_event()])
    agent.toolkit = SimpleNamespace(
        tool_groups=[
            SimpleNamespace(
                tools=[_FakeToolkitTool("k8s.restart_service", "write")]
            )
        ]
    )
    _patch_agent(monkeypatch, kernel, agent)

    frames = _drain(
        kernel.stream_events(
            message="restart it",
            request_id="req-1",
            session_id="s1",
            user_name="alice",
        )
    )
    frame = [f for f in frames if f.get("type") == "confirmation_request"][0]
    assert frame["pending_calls"][0]["risk_level"] == "write"


def test_confirmation_request_emits_gateway_canonical_name(monkeypatch):
    """The confirmation frame must emit the dotted canonical name the
    gateway registry resolves, not the sanitized model-visible name."""
    kernel = _configured_kernel()
    agent = FakeAgent(
        events=[
            RequireUserConfirmEvent(
                reply_id="reply-1", tool_calls=[SANITIZED_TOOL_CALL]
            )
        ]
    )
    agent.toolkit = SimpleNamespace(
        tool_groups=[
            SimpleNamespace(
                tools=[
                    _FakeToolkitTool(
                        "k8s_delete_pod", "write", "k8s.delete_pod"
                    )
                ]
            )
        ]
    )
    _patch_agent(monkeypatch, kernel, agent)

    frames = _drain(
        kernel.stream_events(
            message="restart it",
            request_id="req-1",
            session_id="s1",
            user_name="alice",
        )
    )
    frame = [f for f in frames if f.get("type") == "confirmation_request"][0]
    assert frame["pending_calls"][0]["tool_name"] == "k8s.delete_pod"
    assert frame["pending_calls"][0]["risk_level"] == "write"


class _FakeToolkitTool:
    """Minimal toolkit tool exposing the gateway risk tier attribute."""

    def __init__(
        self,
        name: str,
        risk_level: str,
        gateway_tool_name: str | None = None,
    ) -> None:
        self.name = name
        self.gateway_risk_level = risk_level
        if gateway_tool_name is not None:
            self.gateway_tool_name = gateway_tool_name


def test_filter_mutating_for_hitl_drops_non_read_when_disabled():
    """SPEC-021 R-3: HITL off -> mutating tools never reach the toolkit."""
    kernel = _configured_kernel(hitl_confirm_timeout=0)
    definitions = [
        {"name": "k8s.list_pods", "risk_level": "read"},
        {"name": "k8s.delete_pod", "risk_level": "write"},
    ]
    kept = kernel._filter_mutating_for_hitl(definitions)
    assert [d["name"] for d in kept] == ["k8s.list_pods"]
    assert kernel._mutating_tools_excluded


def test_filter_mutating_for_hitl_keeps_all_when_bridging_enabled():
    kernel = _configured_kernel(hitl_confirm_timeout=600)
    definitions = [
        {"name": "k8s.list_pods", "risk_level": "read"},
        {"name": "k8s.delete_pod", "risk_level": "write"},
    ]
    kept = kernel._filter_mutating_for_hitl(definitions)
    assert kept == definitions
    assert not kernel._mutating_tools_excluded


def test_filter_read_only_drops_non_read_definitions():
    """Read-only turns (incident triage) never see mutating tools."""
    kernel = _configured_kernel(hitl_confirm_timeout=600)
    definitions = [
        {"name": "k8s.list_pods", "risk_level": "read"},
        {"name": "skills.search"},
        {"name": "k8s.delete_pod", "risk_level": "write"},
    ]
    kept = kernel._filter_read_only(definitions)
    assert [d["name"] for d in kept] == ["k8s.list_pods", "skills.search"]


def test_filter_read_only_keeps_everything_when_all_read():
    kernel = _configured_kernel(hitl_confirm_timeout=600)
    definitions = [
        {"name": "k8s.list_pods", "risk_level": "read"},
        {"name": "incidents.list", "risk_level": "read"},
    ]
    assert kernel._filter_read_only(definitions) == definitions


def test_stream_events_disabled_mode_keeps_silent_park(monkeypatch):
    kernel = _configured_kernel(hitl_confirm_timeout=0)
    agent = FakeAgent(events=[_park_event()])
    _patch_agent(monkeypatch, kernel, agent)

    frames = _drain(
        kernel.stream_events(
            message="restart it",
            request_id="req-1",
            session_id="s1",
            user_name="alice",
        )
    )
    assert not any(f.get("type") == "confirmation_request" for f in frames)
    assert not CONFIRMATION_REGISTRY.is_parked("s1", 600)


# --- Kernel: resume ---


def test_resume_confirmation_approves_all_parked_calls(monkeypatch):
    kernel = _configured_kernel()
    agent = FakeAgent(events=[{"type": "REPLY_END"}])
    _patch_agent(monkeypatch, kernel, agent)
    CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    pending = CONFIRMATION_REGISTRY.peek_parked("s1")
    claimed = CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)

    frames = _drain(
        kernel.resume_confirmation(
            session_id="s1",
            pending=claimed,
            decision="approve",
            user_name="alice",
            request_id="req-2",
            bearer_token="tok-alice",
        )
    )
    assert frames[0]["type"] == "confirmation_result"
    assert frames[0]["status"] == "approved"
    assert frames[0]["confirm_id"] == pending.confirm_id
    fed = agent.inputs[0]
    assert isinstance(fed, UserConfirmResultEvent)
    assert fed.reply_id == "reply-1"
    assert [r.confirmed for r in fed.confirm_results] == [True]
    assert not CONFIRMATION_REGISTRY.is_parked("s1", 600)


def test_resume_confirmation_deny_feeds_refusal_back(monkeypatch):
    kernel = _configured_kernel()
    agent = FakeAgent(events=[{"type": "REPLY_END"}])
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    claimed = CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)

    frames = _drain(
        kernel.resume_confirmation(
            session_id="s1",
            pending=claimed,
            decision="deny",
            user_name="alice",
            request_id="req-2",
        )
    )
    assert frames[0]["status"] == "denied"
    fed = agent.inputs[0]
    assert [r.confirmed for r in fed.confirm_results] == [False]


def test_claim_rejects_unknown_and_expired_entries() -> None:
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    with pytest.raises(ConfirmationNotFound):
        CONFIRMATION_REGISTRY.claim("s1", "nope", 600)
    pending.created_at = time.monotonic() - 601
    with pytest.raises(ConfirmationExpired):
        CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)


def test_resume_confirmation_accepts_cross_user_confirmer(monkeypatch) -> None:
    """SPEC-030 R-3: tier_2 approvals resume under a confirmer other
    than the session owner; who may decide is enforced by the
    platform-gateway approval-tier bridge, not the kernel."""
    kernel = _configured_kernel()
    agent = FakeAgent(events=[{"type": "REPLY_END"}])
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    claimed = CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)
    frames = _drain(
        kernel.resume_confirmation(
            "s1", claimed, "approve", "bob-approver", "req-x"
        )
    )
    assert frames[0]["type"] == "confirmation_result"
    assert frames[0]["status"] == "approved"
    assert not CONFIRMATION_REGISTRY.is_parked("s1", 600)


def test_resume_confirmation_resolves_entry_on_stream_error(monkeypatch):
    kernel = _configured_kernel()
    agent = FakeAgent(raise_on_stream=True)
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    claimed = CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)

    with pytest.raises(RuntimeError):
        _drain(
            kernel.resume_confirmation(
                "s1", claimed, "approve", "alice", "req-x"
            )
        )
    assert not CONFIRMATION_REGISTRY.is_parked("s1", 600)


# --- Kernel: expiry closes parked calls via UserInterruptEvent ---


def test_expire_confirmation_interrupts_expired_entry(monkeypatch):
    kernel = _configured_kernel()
    agent = FakeAgent(events=[])
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    pending.created_at = time.monotonic() - 601

    # Peek reaches the aged entry, so expiry closes the parked reply via
    # UserInterruptEvent instead of raising.
    asyncio.run(kernel.expire_confirmation("s1", pending.confirm_id))
    assert isinstance(agent.inputs[0], UserInterruptEvent)
    assert agent.inputs[0].reply_id == "reply-1"
    assert not CONFIRMATION_REGISTRY.is_parked("s1", 600)
    with pytest.raises(ConfirmationNotFound):
        asyncio.run(kernel.expire_confirmation("s1", pending.confirm_id))


def test_expire_confirmation_cleanup_survives_interrupt_failure(
    monkeypatch,
):
    kernel = _configured_kernel()
    agent = FakeAgent(raise_on_stream=True)
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    # A failed interrupt still resolves the entry so the session cannot wedge.
    asyncio.run(kernel.expire_confirmation("s1", pending.confirm_id))
    assert isinstance(agent.inputs[0], UserInterruptEvent)
    assert agent.inputs[0].reply_id == "reply-1"
    assert not CONFIRMATION_REGISTRY.is_parked("s1", 600)


def test_expire_confirmation_skips_claimed_entry(monkeypatch):
    """A racing expiry must never interrupt an in-flight resume."""
    kernel = _configured_kernel()
    agent = FakeAgent(events=[])
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    # The confirm route claimed the entry while fresh; the resume stream
    # then outlives the TTL. Expiry must back off.
    CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)
    pending.created_at = time.monotonic() - 601
    with pytest.raises(ConfirmationNotFound):
        asyncio.run(kernel.expire_confirmation("s1", pending.confirm_id))
    assert agent.inputs == []
    # The entry stays parked until the resume's finally resolves it.
    assert CONFIRMATION_REGISTRY.is_parked("s1", 600)


# --- Kernel: durable resolution records (SPEC-031 R-1) ---


def _seed_parked_record(session_id: str, confirm_id: str, owner: str = "alice"):
    CONFIRMATION_RECORD_STORE.save_parked(
        make_record(
            confirm_id,
            session_id,
            owner,
            [{"call_id": "call-1", "tool_name": "k8s.restart_service"}],
            "tools:mutate",
        )
    )


def test_resume_confirmation_persists_durable_resolution(monkeypatch):
    """The applied decision lands in the record store with attribution."""
    kernel = _configured_kernel()
    agent = FakeAgent(events=[])
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    _seed_parked_record("s1", pending.confirm_id)
    claimed = CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)

    _drain(
        kernel.resume_confirmation(
            "s1", claimed, "approve", "bob-approver", "req-x"
        )
    )
    record = CONFIRMATION_RECORD_STORE.load_record("s1", pending.confirm_id)
    assert record["status"] == "approved"
    assert record["decider_user_id"] == "bob-approver"
    assert record["decision"] == "approve"
    assert record["decided_at"] is not None


def test_resume_confirmation_persists_denial(monkeypatch):
    kernel = _configured_kernel()
    agent = FakeAgent(events=[])
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    _seed_parked_record("s1", pending.confirm_id)
    claimed = CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)

    _drain(kernel.resume_confirmation("s1", claimed, "deny", "alice", "req-x"))
    record = CONFIRMATION_RECORD_STORE.load_record("s1", pending.confirm_id)
    assert record["status"] == "denied"
    assert record["decider_user_id"] == "alice"
    assert record["decision"] == "deny"


def test_expire_confirmation_persists_expired_record(monkeypatch):
    kernel = _configured_kernel()
    agent = FakeAgent(events=[])
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    _seed_parked_record("s1", pending.confirm_id)
    pending.created_at = time.monotonic() - 601

    asyncio.run(kernel.expire_confirmation("s1", pending.confirm_id))
    record = CONFIRMATION_RECORD_STORE.load_record("s1", pending.confirm_id)
    assert record["status"] == "expired"
    assert record["decider_user_id"] is None
    assert record["decision"] is None


def test_resolution_write_failure_never_breaks_resume(monkeypatch):
    """A failing record store degrades history only, never the decision."""
    kernel = _configured_kernel()
    agent = FakeAgent(events=[])
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    claimed = CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)

    def broken_mark_resolved(*args, **kwargs):
        raise RuntimeError("store down")

    monkeypatch.setattr(
        CONFIRMATION_RECORD_STORE, "mark_resolved", broken_mark_resolved
    )
    frames = _drain(
        kernel.resume_confirmation("s1", claimed, "approve", "alice", "req-x")
    )
    assert frames[0]["status"] == "approved"
    assert not CONFIRMATION_REGISTRY.is_parked("s1", 600)


# --- Routes ---


def _client() -> TestClient:
    return TestClient(create_app())


def _park_registered(session_id: str, user_id: str = "alice", age: float = 0.0):
    pending = CONFIRMATION_REGISTRY.register(
        session_id, user_id, "reply-1", [TOOL_CALL], 600
    )
    if age:
        pending.created_at = time.monotonic() - age
    return pending


def test_confirm_unknown_confirmation_returns_404() -> None:
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    response = client.post(
        "/api/v2/chat/confirm",
        json={
            "session_id": session_id,
            "confirm_id": "nope",
            "decision": "approve",
        },
        headers={"X-User-ID": "alice"},
    )
    assert response.status_code == 404


def test_confirm_cross_user_confirmer_reaches_registry(monkeypatch) -> None:
    """SPEC-030 R-3: the route no longer asserts session ownership — a
    tier_2 approver confirms a session they do not own; approval
    authorization is enforced by the platform-gateway bridge."""
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    pending = _park_registered(session_id)

    kernel = get_runtime_kernel()

    async def fake_resume(**kwargs):
        yield {
            "type": "confirmation_result",
            "confirm_id": pending.confirm_id,
            "status": "approved",
        }

    monkeypatch.setattr(kernel, "resume_confirmation", fake_resume)
    response = client.post(
        "/api/v2/chat/confirm",
        json={
            "session_id": session_id,
            "confirm_id": pending.confirm_id,
            "decision": "approve",
        },
        headers={"X-User-ID": "bob-approver"},
    )
    assert response.status_code == 200


def test_pending_confirmation_endpoint_returns_parked_metadata() -> None:
    """SPEC-030 R-3: the confirm bridge reads the parked batch's policy
    action and owner username from this endpoint."""
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    pending = CONFIRMATION_REGISTRY.register(
        session_id, "alice", "reply-1", [TOOL_CALL], 600,
        risk_levels={"k8s.restart_service": "write"},
    )
    response = client.get(
        "/api/v2/chat/pending-confirmation",
        params={"session_id": session_id},
        headers={"X-User-ID": "bob-approver"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["confirm_id"] == pending.confirm_id
    assert body["owner_user_id"] == "alice"
    assert body["action"] == "tools:mutate"
    assert body["pending_calls"][0]["tool_name"] == "k8s.restart_service"


def test_pending_confirmation_endpoint_404_when_unparked() -> None:
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    response = client.get(
        "/api/v2/chat/pending-confirmation",
        params={"session_id": session_id},
        headers={"X-User-ID": "alice"},
    )
    assert response.status_code == 404


def test_pending_confirmation_endpoint_404_unknown_session() -> None:
    client = _client()
    response = client.get(
        "/api/v2/chat/pending-confirmation",
        params={"session_id": "no-such-session"},
        headers={"X-User-ID": "alice"},
    )
    assert response.status_code == 404


def test_confirm_expired_returns_410(monkeypatch) -> None:
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    pending = _park_registered(session_id, age=601)

    kernel = get_runtime_kernel()
    expired_calls: list = []

    async def fake_expire(session_id_arg, confirm_id_arg):
        expired_calls.append((session_id_arg, confirm_id_arg))
        CONFIRMATION_REGISTRY.resolve(session_id_arg, confirm_id_arg)

    monkeypatch.setattr(kernel, "expire_confirmation", fake_expire)
    response = client.post(
        "/api/v2/chat/confirm",
        json={
            "session_id": session_id,
            "confirm_id": pending.confirm_id,
            "decision": "approve",
        },
        headers={"X-User-ID": "alice"},
    )
    assert response.status_code == 410
    assert expired_calls == [(session_id, pending.confirm_id)]


def test_parked_session_rejects_new_turns_with_409() -> None:
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    _park_registered(session_id)

    blocked = client.post(
        "/api/v2/chat",
        json={"message": "hello", "session_id": session_id},
        headers={"X-User-ID": "alice"},
    )
    assert blocked.status_code == 409
    blocked_stream = client.get(
        "/api/v2/chat/stream",
        params={"message": "hello", "session_id": session_id},
        headers={"X-User-ID": "alice"},
    )
    assert blocked_stream.status_code == 409


def test_confirm_approve_streams_confirmation_result_first(monkeypatch) -> None:
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    pending = _park_registered(session_id)

    kernel = get_runtime_kernel()

    async def fake_resume(**kwargs):
        yield {
            "type": "confirmation_result",
            "confirm_id": kwargs["pending"].confirm_id,
            "status": "approved",
        }
        yield {
            "event": "message_end",
            "message": "complete",
        }

    monkeypatch.setattr(kernel, "resume_confirmation", fake_resume)
    response = client.post(
        "/api/v2/chat/confirm",
        json={
            "session_id": session_id,
            "confirm_id": pending.confirm_id,
            "decision": "approve",
        },
        headers={"X-User-ID": "alice", "x-request-id": "req-confirm"},
    )
    assert response.status_code == 200
    frames = [
        line.removeprefix("data: ")
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert '"confirmation_result"' in frames[0]
    assert '"approved"' in frames[0]
    assert '"message_end"' in frames[1]


def test_duplicate_confirm_fails_closed_with_404(monkeypatch) -> None:
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    pending = _park_registered(session_id)

    kernel = get_runtime_kernel()

    async def fake_resume(**kwargs):
        yield {
            "type": "confirmation_result",
            "confirm_id": kwargs["pending"].confirm_id,
            "status": "approved",
        }
        yield {"event": "message_end", "message": "complete"}

    monkeypatch.setattr(kernel, "resume_confirmation", fake_resume)
    payload = {
        "session_id": session_id,
        "confirm_id": pending.confirm_id,
        "decision": "approve",
    }
    first = client.post(
        "/api/v2/chat/confirm", json=payload, headers={"X-User-ID": "alice"}
    )
    assert first.status_code == 200
    # The claim is taken before headers go out: a duplicate (retry, second
    # tab, second operator) must fail closed with 404, never re-resume.
    second = client.post(
        "/api/v2/chat/confirm", json=payload, headers={"X-User-ID": "alice"}
    )
    assert second.status_code == 404


def test_confirm_with_evicted_model_pin_degrades_to_default(monkeypatch) -> None:
    """A stale session pin (evicted by a discovery refresh or a key
    revocation) must degrade to the catalog default on resume instead
    of raising UnknownModelError mid-stream — the registry entry is
    claimed before headers go out, so a raise would wedge the session.
    """
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    session_service.pin_session_model(session_id, "qwen-evicted")
    pending = _park_registered(session_id)

    class FakeCatalog:
        """Only the default survives; the pinned id was evicted."""

        def get(self, model_id):
            if model_id == "deepseek-v4-flash":
                return SimpleNamespace(id=model_id)
            return None

        def default_entry(self):
            return SimpleNamespace(id="deepseek-v4-flash")

    monkeypatch.setattr(v2_routes, "MODEL_CATALOG", FakeCatalog())
    kernel = get_runtime_kernel()
    captured: list = []

    async def fake_resume(**kwargs):
        captured.append(kwargs.get("model_id"))
        yield {"event": "message_end", "message": "complete"}

    monkeypatch.setattr(kernel, "resume_confirmation", fake_resume)
    response = client.post(
        "/api/v2/chat/confirm",
        json={
            "session_id": session_id,
            "confirm_id": pending.confirm_id,
            "decision": "approve",
        },
        headers={"X-User-ID": "alice"},
    )
    assert response.status_code == 200
    assert captured == ["deepseek-v4-flash"]


def test_expired_park_interrupts_before_new_turn(monkeypatch) -> None:
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    pending = _park_registered(session_id, age=601)

    kernel = get_runtime_kernel()
    expired_calls: list = []

    async def fake_expire(session_id_arg, confirm_id_arg):
        expired_calls.append((session_id_arg, confirm_id_arg))
        CONFIRMATION_REGISTRY.resolve(session_id_arg, confirm_id_arg)

    async def fake_reply_text(**kwargs):
        return "resumed", None

    monkeypatch.setattr(kernel, "expire_confirmation", fake_expire)
    monkeypatch.setattr(kernel, "reply_text", fake_reply_text)
    response = client.post(
        "/api/v2/chat",
        json={"message": "hello", "session_id": session_id},
        headers={"X-User-ID": "alice"},
    )
    # The TTL-expired park is closed via UserInterruptEvent and the new
    # turn proceeds instead of wedging on the parked reply.
    assert response.status_code == 200
    assert response.json()["content"] == "resumed"
    assert expired_calls == [(session_id, pending.confirm_id)]


def test_confirm_request_rejects_invalid_decision() -> None:
    client = _client()
    response = client.post(
        "/api/v2/chat/confirm",
        json={
            "session_id": "s1",
            "confirm_id": "c1",
            "decision": "maybe",
        },
        headers={"X-User-ID": "alice"},
    )
    assert response.status_code == 422


# --- Kernel: signed execution requests and receipts (SPEC-037 R-2/R-4/R-5) ---

SIGNING_KEY = "test-execution-key"


class ExecutionCapturingAgent(FakeAgent):
    """Records the execution context visible inside the resumed stream."""

    def __init__(self, events=None):
        super().__init__(events=events or [{"type": "REPLY_END"}])
        self.observed_requests = "unset"
        self.observed_rejection = "unset"

    async def reply_stream(self, inputs):
        self.observed_requests = EXECUTION_REQUESTS.get()
        self.observed_rejection = EXECUTION_REJECTION.get()
        async for event in super().reply_stream(inputs):
            yield event


class ToolResultAgent(FakeAgent):
    """Pushes scripted tool_result frames onto the evidence sink."""

    def __init__(self, tool_frames, events=None):
        super().__init__(events=events or [{"type": "REPLY_END"}])
        self.tool_frames = tool_frames

    async def reply_stream(self, inputs):
        sink = TOOL_EVIDENCE_SINK.get()
        for frame in self.tool_frames:
            sink.put_nowait(frame)
        async for event in super().reply_stream(inputs):
            yield event


def _capture_execution_audits(monkeypatch) -> list:
    events: list = []

    def fake_emit(settings, event):
        events.append(event)

    monkeypatch.setattr("agent_service.runtime_kernel.emit_audit_event", fake_emit)
    return events


def _approve_parked(monkeypatch, kernel, agent, request_id="req-2"):
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    claimed = CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)
    return _drain(
        kernel.resume_confirmation(
            session_id="s1",
            pending=claimed,
            decision="approve",
            user_name="alice",
            request_id=request_id,
            bearer_token="tok-alice",
        )
    )


def test_resume_approval_signs_and_persists_one_request_per_call(monkeypatch):
    """SPEC-037 R-2: one signed, persisted request per approved parked call."""
    kernel = _configured_kernel(execution_signing_key=SIGNING_KEY)
    agent = ExecutionCapturingAgent()
    audits = _capture_execution_audits(monkeypatch)

    frames = _approve_parked(monkeypatch, kernel, agent)
    assert frames[0]["status"] == "approved"

    requests = agent.observed_requests
    assert agent.observed_rejection is None
    assert set(requests) == {"call-1"}
    request = requests["call-1"]
    # The digest binds the parked arguments the approver saw.
    assert request["args_digest"] == canonical_digest({"namespace": "ops"})
    assert request["confirm_id"] == frames[0]["confirm_id"]
    assert request["owner_user_id"] == "alice"
    assert request["decider_user_id"] == "alice"
    assert verify_envelope(request, request["signature"], SIGNING_KEY)

    rows = EXECUTION_RECORD_STORE.load_for_session("s1")
    assert [row["status"] for row in rows] == ["requested"]
    assert rows[0]["execution_id"] == request["execution_id"]

    requested = [a for a in audits if a["event_type"] == "execution_requested"]
    assert len(requested) == 1
    assert requested[0]["outcome"] == "success"
    assert requested[0]["details"]["confirm_id"] == frames[0]["confirm_id"]
    assert requested[0]["details"]["call_id"] == "call-1"
    assert requested[0]["request_id"] == "req-2"
    assert requested[0]["session_id"] == "s1"


def test_resume_denial_constructs_no_execution_requests(monkeypatch):
    kernel = _configured_kernel(execution_signing_key=SIGNING_KEY)
    agent = ExecutionCapturingAgent()
    audits = _capture_execution_audits(monkeypatch)
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    claimed = CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)

    frames = _drain(
        kernel.resume_confirmation(
            "s1", claimed, "deny", "alice", "req-2"
        )
    )
    assert frames[0]["status"] == "denied"
    assert agent.observed_requests is None
    assert agent.observed_rejection is None
    assert EXECUTION_RECORD_STORE.load_for_session("s1") == []
    assert audits == []


def test_resume_missing_signing_key_rejects_fail_closed(monkeypatch):
    """SPEC-037 R-2: no key ⇒ batch rejected, audited signing_unavailable."""
    kernel = _configured_kernel()
    agent = ExecutionCapturingAgent()
    audits = _capture_execution_audits(monkeypatch)

    frames = _approve_parked(monkeypatch, kernel, agent)
    # The confirmation itself applied; the rejection rides the tool boundary.
    assert frames[0]["status"] == "approved"
    assert agent.observed_requests is None
    assert agent.observed_rejection == "signing_unavailable"
    assert EXECUTION_RECORD_STORE.load_for_session("s1") == []

    rejected = [a for a in audits if a["event_type"] == "execution_rejected"]
    assert len(rejected) == 1
    assert rejected[0]["outcome"] == "deny"
    assert rejected[0]["details"]["reason"] == "signing_unavailable"
    assert rejected[0]["details"]["call_id"] == "call-1"
    assert rejected[0]["request_id"] == "req-2"


def test_resume_receipt_closes_executed_call(monkeypatch):
    """SPEC-037 R-4/R-5: a landed tool result signs the closing receipt."""
    kernel = _configured_kernel(execution_signing_key=SIGNING_KEY)
    tool_frame = {
        "type": "tool_result",
        "call_id": "call-1",
        "tool_name": "k8s.restart_service",
        "status": "success",
        "output": {"restarted": True},
    }
    agent = ToolResultAgent([tool_frame])
    audits = _capture_execution_audits(monkeypatch)

    frames = _approve_parked(monkeypatch, kernel, agent)
    confirm_id = frames[0]["confirm_id"]
    assert any(f == {**tool_frame, "request_id": "req-2", "session_id": "s1"} for f in frames)

    rows = EXECUTION_RECORD_STORE.load_for_session("s1")
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "succeeded"
    assert row["digest_match"] is True
    receipt = row["receipt"]
    assert receipt["request_id"] == "req-2"
    assert receipt["outcome_digest"] == canonical_digest(
        {**tool_frame, "request_id": "req-2", "session_id": "s1"}
    )
    assert verify_envelope(receipt, receipt["signature"], SIGNING_KEY)

    completed = [a for a in audits if a["event_type"] == "execution_completed"]
    assert len(completed) == 1
    assert completed[0]["outcome"] == "success"
    assert completed[0]["details"]["status"] == "succeeded"
    assert completed[0]["details"]["confirm_id"] == confirm_id
    assert completed[0]["details"]["request_id"] == "req-2"
    assert isinstance(completed[0]["details"]["duration_ms"], int)


def test_resume_invocation_rejection_marks_record_without_receipt(monkeypatch):
    """SPEC-037 R-3/R-4: an EXECUTION_REJECTED frame closes the row as
    rejected; the audit already went out at the invocation boundary."""
    kernel = _configured_kernel(execution_signing_key=SIGNING_KEY)
    tool_frame = {
        "type": "tool_result",
        "call_id": "call-1",
        "tool_name": "k8s.restart_service",
        "status": "error",
        "error": {
            "code": "EXECUTION_REJECTED",
            "message": "execution rejected",
            "reason": "args_digest_mismatch",
        },
    }
    agent = ToolResultAgent([tool_frame])
    audits = _capture_execution_audits(monkeypatch)

    _approve_parked(monkeypatch, kernel, agent)
    rows = EXECUTION_RECORD_STORE.load_for_session("s1")
    assert [row["status"] for row in rows] == ["rejected"]
    assert rows[0]["reject_reason"] == "args_digest_mismatch"
    assert rows[0]["digest_match"] is False
    assert rows[0]["receipt"] is None
    # The kernel never re-audits a rejection owned by the tool boundary.
    assert not any(a["event_type"] == "execution_rejected" for a in audits)
    assert not any(a["event_type"] == "execution_completed" for a in audits)


def test_resume_timeout_result_signs_timeout_receipt(monkeypatch):
    kernel = _configured_kernel(execution_signing_key=SIGNING_KEY)
    tool_frame = {
        "type": "tool_result",
        "call_id": "call-1",
        "tool_name": "k8s.restart_service",
        "status": "error",
        "error": {"code": "TIMEOUT", "message": "gateway timed out"},
    }
    agent = ToolResultAgent([tool_frame])
    audits = _capture_execution_audits(monkeypatch)

    _approve_parked(monkeypatch, kernel, agent)
    rows = EXECUTION_RECORD_STORE.load_for_session("s1")
    assert rows[0]["status"] == "timeout"
    assert rows[0]["receipt"]["status"] == "timeout"
    completed = [a for a in audits if a["event_type"] == "execution_completed"]
    assert completed[0]["outcome"] == "error"
    assert completed[0]["details"]["status"] == "timeout"

