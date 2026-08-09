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

    async def fake_build_agent(bearer_token=None):
        return (FakeMemoryAgent(), FakeUserMsg)

    monkeypatch.setattr(kernel, "_build_agent", fake_build_agent)

    reply_a1 = asyncio.run(kernel.reply_text("first", "ses-a", "alice"))
    reply_b1 = asyncio.run(kernel.reply_text("hello", "ses-b", "bob"))
    reply_a2 = asyncio.run(kernel.reply_text("second", "ses-a", "alice"))

    # ses-b starts with fresh memory; ses-a keeps its own history
    assert reply_a1 == "turn 1"
    assert reply_b1 == "turn 1"
    assert reply_a2 == "turn 2"


def test_ensure_agent_reuses_instance_per_session(monkeypatch):
    kernel = AgentKernel(settings=RuntimeSettings(api_key="test-key"))

    async def fake_build_agent(bearer_token=None):
        return (FakeMemoryAgent(), FakeUserMsg)

    monkeypatch.setattr(kernel, "_build_agent", fake_build_agent)

    agent_a, _ = asyncio.run(kernel.ensure_agent("ses-a"))
    agent_b, _ = asyncio.run(kernel.ensure_agent("ses-b"))

    assert agent_a is not agent_b
    assert asyncio.run(kernel.ensure_agent("ses-a"))[0] is agent_a


def test_ensure_agent_cache_is_bounded(monkeypatch):
    kernel = AgentKernel(
        settings=RuntimeSettings(api_key="test-key"),
        max_cached_agents=1,
    )

    async def fake_build_agent(bearer_token=None):
        return (FakeMemoryAgent(), FakeUserMsg)

    monkeypatch.setattr(kernel, "_build_agent", fake_build_agent)

    agent_a, _ = asyncio.run(kernel.ensure_agent("ses-a"))
    asyncio.run(kernel.ensure_agent("ses-b"))

    assert asyncio.run(kernel.ensure_agent("ses-a"))[0] is not agent_a


def test_concurrent_ensure_agent_builds_one_agent_per_session(monkeypatch):
    """Agent creation awaits, so concurrent turns must not each build an agent.

    Without serialisation the loser's agent — and its conversation memory —
    would be silently discarded.
    """
    kernel = AgentKernel(settings=RuntimeSettings(api_key="test-key"))
    build_calls = 0

    async def fake_build_agent(bearer_token=None):
        nonlocal build_calls
        build_calls += 1
        # Yield control so a concurrent caller can interleave here.
        await asyncio.sleep(0)
        return (FakeMemoryAgent(), FakeUserMsg)

    monkeypatch.setattr(kernel, "_build_agent", fake_build_agent)

    async def race():
        return await asyncio.gather(
            kernel.ensure_agent("ses-a"),
            kernel.ensure_agent("ses-a"),
            kernel.ensure_agent("ses-a"),
        )

    results = asyncio.run(race())

    assert build_calls == 1
    first_agent = results[0][0]
    assert all(agent is first_agent for agent, _ in results)


class TestPerTokenToolkitCache:
    """SPEC-008 R-5: toolkits are cached per delegated token, never shared."""

    def _kernel(self):
        return AgentKernel(
            settings=RuntimeSettings(
                api_key="test-key",
                tool_gateway_url="http://gw:8080",
            )
        )

    def test_same_token_reuses_cached_toolkit(self, monkeypatch):
        kernel = self._kernel()
        calls = []

        async def fake_build_toolkit(gateway_url, bearer_token=None):
            calls.append((gateway_url, bearer_token))
            return object()

        monkeypatch.setattr(
            "agent_service.tools.gateway_tools.build_toolkit", fake_build_toolkit
        )

        first = asyncio.run(kernel._ensure_toolkit("token-a"))
        second = asyncio.run(kernel._ensure_toolkit("token-a"))

        assert first is second
        assert calls == [("http://gw:8080", "token-a")]

    def test_different_tokens_get_distinct_toolkits(self, monkeypatch):
        kernel = self._kernel()
        seen_tokens = []

        async def fake_build_toolkit(gateway_url, bearer_token=None):
            seen_tokens.append(bearer_token)
            return object()

        monkeypatch.setattr(
            "agent_service.tools.gateway_tools.build_toolkit", fake_build_toolkit
        )

        toolkit_a = asyncio.run(kernel._ensure_toolkit("token-a"))
        toolkit_b = asyncio.run(kernel._ensure_toolkit("token-b"))

        assert toolkit_a is not toolkit_b
        assert seen_tokens == ["token-a", "token-b"]

    def test_no_token_degrades_to_empty_toolkit_without_discovery(self, monkeypatch):
        kernel = self._kernel()

        async def fake_build_toolkit(gateway_url, bearer_token=None):
            # build_toolkit is still invoked, but with no token discovery
            # short-circuits to an empty Toolkit inside gateway_tools.
            assert bearer_token is None
            from agentscope.tool import Toolkit

            return Toolkit()

        monkeypatch.setattr(
            "agent_service.tools.gateway_tools.build_toolkit", fake_build_toolkit
        )

        toolkit = asyncio.run(kernel._ensure_toolkit(None))

        assert toolkit is not None
        # Cached under the empty-key bucket.
        assert asyncio.run(kernel._ensure_toolkit(None)) is toolkit


class TestRequestToolkitRegistration:
    """Regression: per-request toolkits must actually register gateway tools.

    AgentScope 2.x removed ``Toolkit.add``; a toolkit built without tools is
    empty and the model can never invoke the gateway (root cause of the
    hallucinated health report). These tests assert the schemas are really
    present on the built toolkit.
    """

    DEFINITION = {
        "name": "k8s.list_pods",
        "description": "List pods in the cluster",
        "risk_level": "read",
        "parameters_schema": {
            "type": "object",
            "properties": {"namespace": {"type": "string"}},
        },
    }

    def _kernel(self):
        return AgentKernel(
            settings=RuntimeSettings(
                api_key="test-key",
                tool_gateway_url="http://gw:8080",
            )
        )

    def test_request_toolkit_registers_cached_definitions(self):
        kernel = self._kernel()
        kernel._tool_definitions["token-a"] = [self.DEFINITION]

        toolkit = asyncio.run(
            kernel._build_request_toolkit("token-a", asyncio.Queue())
        )

        schemas = asyncio.run(toolkit.get_tool_schemas())
        names = {schema["function"]["name"] for schema in schemas}
        assert names == {"k8s_list_pods"}

    def test_request_toolkit_empty_when_no_definitions_cached(self):
        kernel = self._kernel()

        toolkit = asyncio.run(
            kernel._build_request_toolkit("token-a", asyncio.Queue())
        )

        schemas = asyncio.run(toolkit.get_tool_schemas())
        assert not any(
            schema.get("type") == "function" for schema in schemas
        )

    def test_count_function_tools(self):
        from agentscope.tool import Toolkit

        from agent_service.tools.gateway_tools import build_gateway_toolkit

        kernel = self._kernel()

        assert asyncio.run(kernel._count_function_tools(Toolkit())) == 0

        populated = build_gateway_toolkit(
            [self.DEFINITION], "http://gw:8080", "token-a"
        )
        assert asyncio.run(kernel._count_function_tools(populated)) == 1
