"""Stage-4a characterization gate: the TurnStreamer seam.

These pins snapshot the *turn-streaming / reply* seam as it behaves today,
driven entirely through the public ``AgentKernel`` surface, so the Stage-4a
extraction of ``TurnStreamer`` (``stream_events`` / ``normalize_event`` /
``reply_text`` / ``fallback_stream`` / ``build_unconfigured_message`` /
``build_provider_error_message`` / ``_finish_authorization_stream`` /
``_flush_pending_deliveries`` / ``_discard_burned_deliveries`` /
``_drain_held_deliveries`` / ``_drain_trace_queue``) into
``services/kernel_streaming.py`` is provably byte-identical.

Every pin holds *before and after* the move and patches only a "move-safe"
seam:

* ``agent_service.runtime_kernel.MODEL_CATALOG`` — the model catalog is read
  inside ``stream_events`` (unknown-model fail-closed) and
  ``build_provider_error_message`` (provider attribution). After the move the
  streamer must keep resolving it through the ``runtime_kernel`` namespace at
  call time, so a test that patches it still intercepts — the exact hazard
  class Stage 2 hit with ``AGENT_STATE_STORE`` and Stage 3 with
  ``emit_audit_event``. ``test_stream_events_consults_runtime_kernel_model_catalog``
  is the discriminating pin: a module-level import in the collaborator would
  read the *real* catalog and fail the unknown-model guard.
* instance-level ``monkeypatch.setattr(kernel, "_snapshot_state"/"_observe_*"/...)``
  — proves the moved methods route their sibling calls back through the kernel,
  so an instance patch stays authoritative (the invariant ``test_delegated_identity``
  relies on).
* the ``agent-stream-event`` frame contract (``normalize_event`` /
  ``fallback_stream``) — pinned byte-for-byte; the rich end-to-end behavior is
  already covered by ``test_runtime_kernel`` / ``test_contract_adapter`` /
  ``test_model_switching`` / ``test_secret_delivery_integration``. This file
  adds the wiring-focused net that guards the relocation itself.
"""

import asyncio
from types import SimpleNamespace

from agent_service.runtime_kernel import AgentKernel
from agent_service.runtime_settings import RuntimeSettings
from agent_service.services.kernel_middleware import (
    PENDING_RELEASE_DELIVERIES,
    STREAM_PENDING_DELIVERIES,
)


def _kernel(**overrides) -> AgentKernel:
    kwargs = dict(api_key="test-key")
    kwargs.update(overrides)
    return AgentKernel(settings=RuntimeSettings(**kwargs))


class FakeUserMsg:
    def __init__(self, name, content):
        self.name = name
        self.content = content


class FakeAgentState:
    def model_dump_json(self):
        return "{}"


class FakeMemoryAgent:
    def __init__(self):
        self.history = []
        self.state = FakeAgentState()

    async def reply(self, msg, structured_schema=None):
        self.history.append(msg.content)
        return SimpleNamespace(content=f"turn {len(self.history)}")


def _collect(aiter):
    async def run():
        return [event async for event in aiter]

    return asyncio.run(run())


# --- the agent-stream-event byte-contract: normalize_event ---


def test_normalize_event_control_frame_has_no_delta():
    kernel = _kernel()

    frame = kernel.normalize_event(
        SimpleNamespace(type="REPLY_START", reply_id="reply-1"),
        request_id="req-1",
        session_id="ses-1",
    )

    assert frame["event"] == "reply_start"
    assert frame["request_id"] == "req-1"
    assert frame["session_id"] == "ses-1"
    assert "delta" not in frame


def test_normalize_event_text_delta_carries_text():
    kernel = _kernel()

    frame = kernel.normalize_event(
        SimpleNamespace(type="TEXT_BLOCK_DELTA", delta="STREAM OK"),
        request_id="req-1",
        session_id="ses-1",
    )

    assert frame["event"] == "text_block_delta"
    assert frame["delta"] == "STREAM OK"


def test_normalize_event_renames_terminal_frames_under_authorization():
    # ``target_authorization_enabled`` needs the full SPEC-070 trust config to
    # pass settings validation (a bare True is rejected).
    kernel = _kernel(
        target_authorization_enabled=True,
        delegated_identity_issuer="trusted-issuer",
        delegated_identity_audience="tool-gateway",
        delegated_identity_actors=("platform-gateway",),
        delegated_identity_jwks_url="https://identity.test/jwks",
    )

    end = kernel.normalize_event(
        SimpleNamespace(type="MESSAGE_END"), request_id="req-1", session_id="ses-1"
    )
    reply_end = kernel.normalize_event(
        SimpleNamespace(type="REPLY_END"), request_id="req-1", session_id="ses-1"
    )

    # An SDK model message end is not the wire turn end when authorization is
    # enabled; only reply_end settles the turn.
    assert end["event"] == "model_message_end"
    assert reply_end["event"] == "message_end"


def test_normalize_event_redactor_holdback_omits_delta():
    kernel = _kernel()
    held = SimpleNamespace(literals=frozenset(), feed=lambda text: "")

    frame = kernel.normalize_event(
        SimpleNamespace(type="TEXT_BLOCK_DELTA", delta="secret"),
        request_id="req-1",
        session_id="ses-1",
        redactor=held,
    )

    # A fully held-back chunk omits ``delta`` (never sends "") and rewrites the
    # payload duplicate with the masked text.
    assert "delta" not in frame
    assert frame["payload"] == {"type": "text_block_delta", "delta": ""}


# --- the MODEL_CATALOG patch-surface hazard (the AGENT_STATE_STORE class) ---


def test_build_provider_error_message_reads_runtime_kernel_model_catalog(monkeypatch):
    monkeypatch.setattr(
        "agent_service.runtime_kernel.MODEL_CATALOG",
        {"m1": SimpleNamespace(provider="acme", id="m1")},
    )
    kernel = _kernel()

    msg = kernel.build_provider_error_message("hi", "ses-1", model_id="m1")

    # Attribution names the catalog entry's own provider — proving the patched
    # catalog was consulted through the runtime_kernel namespace.
    assert "acme (model m1)" in msg
    assert "hi" in msg


def test_stream_events_unknown_model_fails_closed():
    kernel = _kernel()

    events = _collect(
        kernel.stream_events(
            message="hi",
            request_id="req-1",
            session_id="ses-1",
            user_name="alice",
            model_id="definitely-not-a-real-model",
        )
    )

    assert len(events) == 1
    assert events[0]["event"] == "error"
    assert events[0]["error"]["code"] == "unknown_model"


def test_stream_events_consults_runtime_kernel_model_catalog(monkeypatch):
    # The discriminating pin: a catalog patched to CONTAIN the id must let the
    # turn past the unknown-model guard. A collaborator that captured
    # MODEL_CATALOG at import time would read the real catalog, fail the guard,
    # and emit an unknown_model error instead of the fallback frames.
    monkeypatch.setattr(
        "agent_service.runtime_kernel.MODEL_CATALOG",
        {"fake-model": SimpleNamespace(provider="acme", id="fake-model")},
    )
    kernel = _kernel(api_key=None)  # unconfigured -> fallback stream

    events = _collect(
        kernel.stream_events(
            message="hi",
            request_id="req-1",
            session_id="ses-1",
            user_name="alice",
            model_id="fake-model",
        )
    )

    assert [event["event"] for event in events] == [
        "message_start",
        "message_delta",
        "message_end",
    ]


# --- fallback_stream byte-contract ---


def test_fallback_stream_frame_sequence():
    kernel = _kernel()

    events = _collect(
        kernel.fallback_stream(
            request_id="req-1", session_id="ses-1", delta="hello there"
        )
    )

    assert [event["event"] for event in events] == [
        "message_start",
        "message_delta",
        "message_end",
    ]
    assert events[1]["delta"] == "hello there"
    assert events[2]["message"] == "complete"
    assert all(
        event["request_id"] == "req-1" and event["session_id"] == "ses-1"
        for event in events
    )


# --- reply_text: unconfigured placeholder + route-back-through-kernel ---


def test_reply_text_unconfigured_returns_placeholder():
    kernel = _kernel(api_key=None)

    reply, structured = asyncio.run(kernel.reply_text("hi", "ses-1", "alice"))

    assert "placeholder response" in reply
    assert structured is None


def test_reply_text_routes_snapshot_through_kernel(monkeypatch):
    kernel = _kernel()

    async def fake_build_agent(
        session_id, bearer_token=None, model_id=None, read_only=False, routing_allowed=False
    ):
        return (FakeMemoryAgent(), FakeUserMsg, model_id or kernel.settings.provider)

    monkeypatch.setattr(kernel, "_build_agent", fake_build_agent)
    snapshots: list = []
    monkeypatch.setattr(
        kernel, "_snapshot_state", lambda *args, **kwargs: snapshots.append(args)
    )

    reply, structured = asyncio.run(kernel.reply_text("first", "ses-a", "alice"))

    assert reply == "turn 1"
    assert structured is None
    assert snapshots, "reply_text must route _snapshot_state back through the kernel"


# --- _drain_trace_queue: decoration + observer route-back ---


def test_drain_trace_queue_decorates_and_routes_observers(monkeypatch):
    kernel = _kernel()
    queue: asyncio.Queue = asyncio.Queue()
    queue.put_nowait({"type": "tool_result", "call_id": "c1"})
    queue.put_nowait({"type": "reasoning", "text": "thinking"})
    evidence_frames: list = []
    seen = {"bind": 0, "inval": 0, "tool": 0}

    def bump(key):
        def _recorder(*args, **kwargs):
            seen[key] += 1

        return _recorder

    monkeypatch.setattr(kernel, "_observe_flow_binding", bump("bind"))
    monkeypatch.setattr(kernel, "_observe_flow_invalidation", bump("inval"))
    monkeypatch.setattr(kernel, "_observe_tool_result", bump("tool"))

    frames = kernel._drain_trace_queue(queue, "req-1", "ses-1", evidence_frames, {})

    assert len(frames) == 2
    assert all(
        frame["request_id"] == "req-1" and frame["session_id"] == "ses-1"
        for frame in frames
    )
    # tool_result is an evidence frame type; reasoning is not.
    assert [frame["type"] for frame in evidence_frames] == ["tool_result"]
    # Each drained frame fans out to all three observers, routed via the kernel.
    assert seen == {"bind": 2, "inval": 2, "tool": 2}


# --- reveal-on-commit delivery buffers ---


def test_flush_pending_deliveries_drains_stream_buffer_only():
    kernel = _kernel()
    queue: asyncio.Queue = asyncio.Queue()
    stream_token = STREAM_PENDING_DELIVERIES.set([{"delivery_id": "d1", "secret": "s"}])
    release_token = PENDING_RELEASE_DELIVERIES.set([{"delivery_id": "held"}])
    try:
        kernel._flush_pending_deliveries(queue)

        flushed = queue.get_nowait()
        assert flushed == {
            "type": "secret_delivery",
            "delivery_id": "d1",
            "secret": "s",
        }
        assert queue.empty()
        # PENDING_RELEASE is deliberately NOT flushed on an ungated turn end.
        assert PENDING_RELEASE_DELIVERIES.get() == [{"delivery_id": "held"}]
        assert STREAM_PENDING_DELIVERIES.get() == []
    finally:
        STREAM_PENDING_DELIVERIES.reset(stream_token)
        PENDING_RELEASE_DELIVERIES.reset(release_token)


def test_drain_held_deliveries_combines_and_clears_both_buffers():
    kernel = _kernel()
    stream_token = STREAM_PENDING_DELIVERIES.set([{"delivery_id": "d1"}])
    release_token = PENDING_RELEASE_DELIVERIES.set([{"delivery_id": "d2"}])
    try:
        held = kernel._drain_held_deliveries()

        assert held == ({"delivery_id": "d1"}, {"delivery_id": "d2"})
        assert STREAM_PENDING_DELIVERIES.get() == []
        assert PENDING_RELEASE_DELIVERIES.get() == []
    finally:
        STREAM_PENDING_DELIVERIES.reset(stream_token)
        PENDING_RELEASE_DELIVERIES.reset(release_token)


def test_discard_burned_deliveries_calls_gateway_with_owner_token(monkeypatch):
    kernel = _kernel(tool_gateway_url="http://gw:8080")
    calls: list = []

    async def fake_discard(url, delivery_ids, owner_token):
        calls.append((url, delivery_ids, owner_token))

    monkeypatch.setattr(
        "agent_service.tools.gateway_tools.discard_deliveries", fake_discard
    )

    asyncio.run(
        kernel._discard_burned_deliveries(
            [{"delivery_id": "d1"}, {"nope": 1}], "owner-tok"
        )
    )
    assert calls == [("http://gw:8080", ["d1"], "owner-tok")]

    # An empty batch never reaches the gateway.
    calls.clear()
    asyncio.run(kernel._discard_burned_deliveries([], "owner-tok"))
    assert calls == []
