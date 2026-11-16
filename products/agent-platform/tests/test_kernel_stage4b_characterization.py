"""Stage-4b characterization gate: the ConfirmationCoordinator seam.

These pins snapshot the *HITL park / resume / expire* seam as it behaves
today, driven entirely through the public ``AgentKernel`` surface, so the
Stage-4b extraction of ``ConfirmationCoordinator`` (``_build_confirmation_frame``
/ ``_extract_browser_element_map`` / ``_record_resolution`` /
``_confirmation_message`` / ``_tool_names_have_browser_write`` /
``_batch_has_browser_write`` / ``_record_flow_approval`` /
``resume_confirmation`` / ``_resume_confirmation`` / ``expire_confirmation``)
into ``services/kernel_confirmations.py`` is provably byte-identical.

Every pin holds *before and after* the move and patches only a "move-safe"
seam:

* instance-level ``monkeypatch.setattr(kernel, "resume_confirmation" /
  "expire_confirmation" / "_resume_identities", ...)`` — the entry points the
  confirm route calls and the identity helper the resume path consults. After
  the move the collaborator must route every sibling call back through the
  kernel, so an instance patch stays authoritative (the invariant
  ``test_hitl_confirmations`` / ``test_kernel_middleware`` rely on).
* ``agent_service.runtime_kernel.flush_prose_frames`` — an ``runtime_kernel``-
  defined stream primitive read inside ``_resume_confirmation``. After the move
  the coordinator must keep resolving it through the ``runtime_kernel``
  namespace at call time (the same hazard class Stage 2 hit with
  ``AGENT_STATE_STORE``, Stage 3 with ``emit_audit_event``, Stage 4a with
  ``MODEL_CATALOG``). ``test_resume_consults_runtime_kernel_flush_prose_frames``
  is the discriminating pin: a module-level import in the collaborator would
  capture the original and ignore the patch.
* the async-generator delegator shape — ``resume_confirmation`` must return the
  collaborator's generator *directly* (no wrapper frame), so an early
  ``aclose()`` propagates into the inner ``finally`` that resets the ~15
  contextvars and clears the parked entry.
  ``test_resume_early_close_runs_finally_spine`` is the discriminating pin: a
  ``async def ... async for ... yield`` wrapper would strand the inner
  generator and leak the contextvar / token cleanup.

The rich end-to-end park / resume / expire behavior is already covered by
``test_hitl_confirmations`` (incl. ``test_stream_events_parks_and_emits_
confirmation_request``, which exercises the cross-collaborator
``stream_events`` -> ``_build_confirmation_frame`` call). This file adds the
wiring-focused net that guards the relocation itself.
"""

import asyncio
import time

import pytest
from agentscope.event import RequireUserConfirmEvent, UserInterruptEvent
from agentscope.message import ToolCallBlock

import agent_service.runtime_kernel as runtime_kernel
from agent_service.runtime_kernel import AgentKernel
from agent_service.runtime_settings import RuntimeSettings
from agent_service.services.confirmation_records import CONFIRMATION_RECORD_STORE
from agent_service.services.hitl_confirmations import CONFIRMATION_REGISTRY
from agent_service.tools.gateway_tools import GENERATION_OWNER_TOKEN

TOOL_CALL = ToolCallBlock(
    id="call-1", name="k8s.restart_service", input='{"namespace": "ops"}'
)


@pytest.fixture(autouse=True)
def _clean_registry():
    CONFIRMATION_REGISTRY._by_session.clear()
    records = getattr(CONFIRMATION_RECORD_STORE, "_by_confirm_id", None)
    if records is not None:
        records.clear()
    yield
    CONFIRMATION_REGISTRY._by_session.clear()
    if records is not None:
        records.clear()


def _kernel(**overrides) -> AgentKernel:
    kwargs = dict(api_key="test-key")
    kwargs.update(overrides)
    return AgentKernel(settings=RuntimeSettings(**kwargs))


class FakeUserMsg:
    def __init__(self, name, content):
        self.name = name
        self.content = content


class FakeAgent:
    """Records reply_stream inputs and yields scripted events."""

    def __init__(self, events=None):
        self.events = events if events is not None else []
        self.inputs = []
        self.toolkit = None

    async def reply_stream(self, inputs):
        self.inputs.append(inputs)
        for event in self.events:
            yield event


def _patch_agent(monkeypatch, kernel, agent):
    async def fake_ensure_agent(
        session_id, bearer_token=None, model_id=None, read_only=False, routing_allowed=False
    ):
        return agent, FakeUserMsg, model_id or kernel.settings.provider

    monkeypatch.setattr(kernel, "ensure_agent", fake_ensure_agent)
    monkeypatch.setattr(kernel, "_snapshot_state", lambda session_id, agent, turn_literals=(): None)


def _drain(async_iter):
    async def _collect():
        return [frame async for frame in async_iter]

    return asyncio.run(_collect())


def _park_event():
    return RequireUserConfirmEvent(reply_id="reply-1", tool_calls=[TOOL_CALL])


# --- entry-point delegators: resume_confirmation / expire_confirmation ---


def test_resume_yields_confirmation_result_first(monkeypatch):
    """The delegator returns a working async generator whose first frame is the
    ``confirmation_result`` (SPEC-020 R-2 frame contract)."""
    kernel = _kernel()
    agent = FakeAgent(events=[])
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)

    frames = _drain(
        kernel.resume_confirmation("s1", pending, "approve", "alice", "req-1")
    )

    assert frames[0]["type"] == "confirmation_result"
    assert frames[0]["status"] == "approved"
    assert frames[0]["confirm_id"] == pending.confirm_id


def test_resume_confirmation_instance_patch_is_honored(monkeypatch):
    """The confirm route patches ``kernel.resume_confirmation`` on the instance;
    the delegator must not shadow-break that surface."""
    kernel = _kernel()
    calls = []

    async def fake_resume(*args, **kwargs):
        calls.append((args, kwargs))
        yield {"type": "sentinel"}

    monkeypatch.setattr(kernel, "resume_confirmation", fake_resume)

    frames = _drain(
        kernel.resume_confirmation("s1", None, "approve", "alice", "req-1")
    )

    assert frames == [{"type": "sentinel"}]
    assert len(calls) == 1


def test_expire_confirmation_instance_patch_is_honored(monkeypatch):
    """The expiry sweeper patches ``kernel.expire_confirmation`` on the
    instance; the delegator must forward to the patch."""
    kernel = _kernel()
    calls = []

    async def fake_expire(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(kernel, "expire_confirmation", fake_expire)
    asyncio.run(kernel.expire_confirmation("s1", "cid"))

    assert calls == [(("s1", "cid"), {})]


# --- async-generator delegator shape: aclose propagates into the finally ---


def test_resume_early_close_runs_finally_spine(monkeypatch):
    """DISCRIMINATING: closing the resume generator after its first frame must
    run the inner ``finally`` (contextvar resets + parked-entry cleanup). A
    wrapper delegator would strand the inner generator and leak it."""
    kernel = _kernel()
    agent = FakeAgent(events=[])
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    pending.requester_delegated_token = "owner-token"

    async def run():
        gen = kernel.resume_confirmation("s1", pending, "approve", "alice", "req-1")
        first = await gen.__anext__()
        during = GENERATION_OWNER_TOKEN.get()
        await gen.aclose()
        after = GENERATION_OWNER_TOKEN.get()
        return first, during, after

    first, during, after = asyncio.run(run())

    assert first["type"] == "confirmation_result"
    # The owner-token contextvar was armed while suspended at the first yield...
    assert during == ("owner-token",)
    # ...and the finally reset it on early close (aclose propagated inward).
    assert after is None
    assert pending.requester_delegated_token is None
    assert not CONFIRMATION_REGISTRY.is_parked("s1", 600)


# --- route-back-through-kernel: _resume_identities instance patch ---


def test_resume_routes_identities_back_through_kernel(monkeypatch):
    """``_resume_identities`` stays on the kernel and is patched on the instance
    (test_kernel_middleware); the moved resume path must consult it through the
    kernel, not a captured reference."""
    kernel = _kernel()
    agent = FakeAgent(events=[])
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    calls = []

    def fake_identities(pending_, session_id, user_id, bearer):
        calls.append((session_id, user_id))
        return None, None

    monkeypatch.setattr(kernel, "_resume_identities", fake_identities)

    _drain(kernel.resume_confirmation("s1", pending, "approve", "alice", "req-1"))

    assert calls and calls[0] == ("s1", "alice")


# --- _build_confirmation_frame: direct + cross-collaborator from stream_events ---


def test_build_confirmation_frame_registers_and_gates_on_timeout(monkeypatch):
    kernel = _kernel()
    agent = FakeAgent(events=[])

    frame = kernel._build_confirmation_frame(_park_event(), "s1", "alice", agent.toolkit)

    assert frame["type"] == "confirmation_request"
    assert frame["confirm_id"]
    assert frame["message"] == "Tool execution requires your confirmation."
    assert CONFIRMATION_REGISTRY.is_parked("s1", 600)

    # Bridging disabled (timeout 0) preserves the legacy silent-park posture.
    kernel0 = _kernel(hitl_confirm_timeout=0)
    assert kernel0._build_confirmation_frame(_park_event(), "s2", "alice", None) is None


def test_stream_events_parks_through_kernel_delegator(monkeypatch):
    """stream_events (TurnStreamer) calls ``_build_confirmation_frame`` through
    the kernel; after Stage 4b that resolves to the ConfirmationCoordinator
    delegator and still emits the park frame."""
    kernel = _kernel()
    agent = FakeAgent(events=[_park_event()])
    _patch_agent(monkeypatch, kernel, agent)

    frames = _drain(
        kernel.stream_events(
            message="restart it", request_id="req-1", session_id="s1", user_name="alice"
        )
    )

    assert any(f.get("type") == "confirmation_request" for f in frames)
    assert CONFIRMATION_REGISTRY.is_parked("s1", 600)


# --- class-qualified staticmethod: _batch_has_browser_write ---


def test_batch_has_browser_write_resolves_class_staticmethod():
    """``_batch_has_browser_write`` calls the browser-write predicate as a
    class-qualified staticmethod; the reference must resolve after the move."""
    kernel = _kernel()
    browser = CONFIRMATION_REGISTRY.register(
        "s1", "alice", "r1",
        [ToolCallBlock(id="b", name="web_click", input="{}")], 600,
        gateway_names={"web_click": "web.click"},
    )
    non_browser = CONFIRMATION_REGISTRY.register(
        "s1", "alice", "r2", [TOOL_CALL], 600,
        gateway_names={"k8s.restart_service": "k8s.restart_service"},
    )

    assert kernel._batch_has_browser_write(browser) is True
    assert kernel._batch_has_browser_write(non_browser) is False


# --- staticmethod delegator: _record_resolution ---


def test_record_resolution_forwards_to_store(monkeypatch):
    kernel = _kernel()
    calls = []
    monkeypatch.setattr(
        CONFIRMATION_RECORD_STORE, "mark_resolved", lambda *a: calls.append(a)
    )

    kernel._record_resolution("s1", "cid", "approved", "alice", "approve")

    assert calls == [("s1", "cid", "approved", "alice", "approve")]


# --- lazy-resolve through runtime_kernel: flush_prose_frames ---


def test_resume_consults_runtime_kernel_flush_prose_frames(monkeypatch):
    """DISCRIMINATING: ``flush_prose_frames`` is defined in ``runtime_kernel``
    and read inside ``_resume_confirmation``. Patching the ``runtime_kernel``
    namespace must intercept it after the move (call-time resolution), which a
    module-level import in the collaborator would miss."""
    kernel = _kernel()
    agent = FakeAgent(events=[{"type": "MESSAGE_END"}])
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    monkeypatch.setattr(
        runtime_kernel,
        "flush_prose_frames",
        lambda redactor, request_id, session_id: [{"event": "__flush_sentinel__"}],
    )

    frames = _drain(
        kernel.resume_confirmation("s1", pending, "approve", "alice", "req-1")
    )

    assert any(f.get("event") == "__flush_sentinel__" for f in frames)


# --- expire path ---


def test_expire_confirmation_interrupts_and_resolves(monkeypatch):
    kernel = _kernel()
    agent = FakeAgent(events=[])
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    pending.created_at = time.monotonic() - 601

    asyncio.run(kernel.expire_confirmation("s1", pending.confirm_id))

    assert agent.inputs and isinstance(agent.inputs[0], UserInterruptEvent)
    assert not CONFIRMATION_REGISTRY.is_parked("s1", 600)
    assert pending.requester_delegated_token is None
