import asyncio
from types import SimpleNamespace

from agent_service.runtime_kernel import AgentKernel
from agent_service.runtime_settings import RuntimeSettings


def test_placeholder_reply_without_credentials():
    kernel = AgentKernel(settings=RuntimeSettings(api_key=None))

    result = asyncio.run(
        kernel.reply_text(
            message="hello",
            session_id="ses-123",
            user_name="alice",
        )
    )

    assert "placeholder response" in result
    assert "ses-123" in result


def test_placeholder_stream_without_credentials():
    kernel = AgentKernel(settings=RuntimeSettings(api_key=None))

    async def collect_events():
        return [
            event
            async for event in kernel.stream_events(
                message="hello",
                request_id="req-123",
                session_id="ses-123",
                user_name="alice",
            )
        ]

    events = asyncio.run(collect_events())

    assert [event["event"] for event in events] == [
        "message_start",
        "message_delta",
        "message_end",
    ]
    assert events[1]["request_id"] == "req-123"
    assert "placeholder response" in events[1]["delta"]


def test_configuration_hint_mentions_provider_when_configured():
    kernel = AgentKernel(
        settings=RuntimeSettings(
            provider="deepseek",
            model_name="deepseek-v4-flash",
            api_key="test-key",
            base_url="https://api.deepseek.com",
        )
    )

    assert kernel.configuration_hint() == (
        "AgentScope runtime ready through deepseek provider using model "
        "deepseek-v4-flash at https://api.deepseek.com."
    )


def test_runtime_metadata_exposes_provider_state():
    kernel = AgentKernel(
        settings=RuntimeSettings(
            profile="deepseek",
            provider="deepseek",
            model_name="deepseek-v4-flash",
            api_key="test-key",
            base_url="https://api.deepseek.com",
        )
    )

    metadata = kernel.runtime_metadata()

    assert metadata["runtime_state"] == "ready"
    assert metadata["profile"] == "deepseek"
    assert metadata["provider"] == "deepseek"
    assert metadata["model_name"] == "deepseek-v4-flash"
    assert metadata["provider_options"] == {
        "max_tokens": None,
        "temperature": None,
        "top_p": None,
        "thinking_enable": False,
        "reasoning_effort": None,
    }
    assert metadata["last_error"] is None


def test_runtime_metadata_uses_provider_defaults_when_unset():
    kernel = AgentKernel(
        settings=RuntimeSettings(
            provider="dashscope",
            api_key="test-key",
        )
    )

    metadata = kernel.runtime_metadata()

    assert metadata["model_name"] == "qwen-plus"
    assert metadata["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"


def test_configuration_hint_mentions_provider_error():
    kernel = AgentKernel(
        settings=RuntimeSettings(
            provider="deepseek",
            model_name="deepseek-v4-flash",
            api_key="test-key",
        )
    )
    kernel._last_error = "model rejected request"

    assert kernel.runtime_state() == "provider_error"
    assert kernel.configuration_hint() == (
        "AgentScope runtime is configured through the deepseek provider, "
        "but the last provider call failed: model rejected request"
    )


def test_normalize_event_omits_delta_for_non_text_control_events():
    kernel = AgentKernel(settings=RuntimeSettings(api_key="test-key"))

    event = SimpleNamespace(type="REPLY_START", reply_id="reply-1")

    payload = kernel.normalize_event(
        event,
        request_id="req-123",
        session_id="ses-123",
    )

    assert payload["event"] == "reply_start"
    assert "delta" not in payload


def test_normalize_event_omits_delta_for_text_block_start_without_text():
    kernel = AgentKernel(settings=RuntimeSettings(api_key="test-key"))

    event = SimpleNamespace(
        type="TEXT_BLOCK_START",
        id="block-1",
        reply_id="reply-1",
        metadata={},
    )

    payload = kernel.normalize_event(
        event,
        request_id="req-123",
        session_id="ses-123",
    )

    assert payload["event"] == "text_block_start"
    assert "delta" not in payload


def test_normalize_event_keeps_delta_for_text_block_events():
    kernel = AgentKernel(settings=RuntimeSettings(api_key="test-key"))

    event = SimpleNamespace(type="TEXT_BLOCK_DELTA", delta="STREAM OK")

    payload = kernel.normalize_event(
        event,
        request_id="req-123",
        session_id="ses-123",
    )

    assert payload["event"] == "text_block_delta"
    assert payload["delta"] == "STREAM OK"


class FakeUserMsg:
    def __init__(self, name, content):
        self.name = name
        self.content = content


class FakeMemoryAgent:
    def __init__(self):
        self.history = []

    async def reply(self, msg):
        self.history.append(msg.content)
        return SimpleNamespace(content=f"turn {len(self.history)}")


def test_agent_conversation_state_never_crosses_sessions(monkeypatch):
    kernel = AgentKernel(settings=RuntimeSettings(api_key="test-key"))
    monkeypatch.setattr(kernel, "_build_agent", lambda: (FakeMemoryAgent(), FakeUserMsg))

    reply_a1 = asyncio.run(kernel.reply_text("first", "ses-a", "alice"))
    reply_b1 = asyncio.run(kernel.reply_text("hello", "ses-b", "bob"))
    reply_a2 = asyncio.run(kernel.reply_text("second", "ses-a", "alice"))

    # ses-b starts with fresh memory; ses-a keeps its own history
    assert reply_a1 == "turn 1"
    assert reply_b1 == "turn 1"
    assert reply_a2 == "turn 2"


def test_ensure_agent_reuses_instance_per_session(monkeypatch):
    kernel = AgentKernel(settings=RuntimeSettings(api_key="test-key"))
    monkeypatch.setattr(kernel, "_build_agent", lambda: (FakeMemoryAgent(), FakeUserMsg))

    agent_a, _ = kernel.ensure_agent("ses-a")
    agent_b, _ = kernel.ensure_agent("ses-b")

    assert agent_a is not agent_b
    assert kernel.ensure_agent("ses-a")[0] is agent_a


def test_ensure_agent_cache_is_bounded(monkeypatch):
    kernel = AgentKernel(
        settings=RuntimeSettings(api_key="test-key"),
        max_cached_agents=1,
    )
    monkeypatch.setattr(kernel, "_build_agent", lambda: (FakeMemoryAgent(), FakeUserMsg))

    agent_a, _ = kernel.ensure_agent("ses-a")
    kernel.ensure_agent("ses-b")

    assert kernel.ensure_agent("ses-a")[0] is not agent_a
