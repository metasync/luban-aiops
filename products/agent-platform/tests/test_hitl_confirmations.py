"""SPEC-020 R-2: HITL confirmation bridging — registry, kernel, routes."""

from __future__ import annotations

import asyncio
import time

import pytest
from agentscope.event import (
    RequireUserConfirmEvent,
    UserConfirmResultEvent,
    UserInterruptEvent,
)
from agentscope.message import ToolCallBlock
from fastapi.testclient import TestClient

from agent_service.app import create_app
from agent_service.runtime_kernel import AgentKernel
from agent_service.runtime_settings import RuntimeSettings
from agent_service.services.hitl_confirmations import (
    CONFIRMATION_REGISTRY,
    ConfirmationExpired,
    ConfirmationNotFound,
    ConfirmationOwnerMismatch,
    ConfirmationRegistry,
)
from agent_service.services.runtime_dependencies import get_runtime_kernel

TOOL_CALL = ToolCallBlock(
    id="call-1", name="k8s.restart_service", input='{"namespace": "ops"}'
)


def _park_event() -> RequireUserConfirmEvent:
    return RequireUserConfirmEvent(reply_id="reply-1", tool_calls=[TOOL_CALL])


@pytest.fixture(autouse=True)
def _clean_registry():
    CONFIRMATION_REGISTRY._by_session.clear()
    yield
    CONFIRMATION_REGISTRY._by_session.clear()


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
    async def fake_ensure_agent(session_id, bearer_token=None):
        return agent, FakeUserMsg

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


class _FakeToolkitTool:
    """Minimal toolkit tool exposing the gateway risk tier attribute."""

    def __init__(self, name: str, risk_level: str) -> None:
        self.name = name
        self.gateway_risk_level = risk_level


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


def test_resume_confirmation_rejects_foreign_confirmer(monkeypatch) -> None:
    kernel = _configured_kernel()
    agent = FakeAgent()
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    claimed = CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)
    with pytest.raises(ConfirmationOwnerMismatch):
        _drain(
            kernel.resume_confirmation(
                "s1", claimed, "approve", "mallory", "req-x"
            )
        )


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


def test_confirm_foreign_session_returns_404() -> None:
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    response = client.post(
        "/api/v2/chat/confirm",
        json={
            "session_id": session_id,
            "confirm_id": "whatever",
            "decision": "approve",
        },
        headers={"X-User-ID": "mallory"},
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
