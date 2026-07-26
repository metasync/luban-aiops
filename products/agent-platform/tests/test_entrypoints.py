import asyncio
from types import SimpleNamespace

from agent_service.entrypoints import native, runtime, transitional


def test_transitional_service_settings_reads_env(monkeypatch):
    monkeypatch.setenv("AGENT_TRANSITIONAL_HOST", "127.0.0.1")
    monkeypatch.setenv("AGENT_TRANSITIONAL_PORT", "9000")

    settings = transitional.TransitionalServiceSettings.from_env()

    assert settings.host == "127.0.0.1"
    assert settings.port == 9000


def test_transitional_service_settings_default_values(monkeypatch):
    monkeypatch.delenv("AGENT_TRANSITIONAL_HOST", raising=False)
    monkeypatch.delenv("AGENT_TRANSITIONAL_PORT", raising=False)

    settings = transitional.TransitionalServiceSettings.from_env()

    assert settings.host == transitional.DEFAULT_HTTP_HOST
    assert settings.port == transitional.DEFAULT_HTTP_PORT


def test_native_service_settings_read_surface_specific_env(monkeypatch):
    monkeypatch.setenv("AGENT_NATIVE_HOST", "0.0.0.0")
    monkeypatch.setenv("AGENT_NATIVE_PORT", "8181")
    monkeypatch.setenv("AGENT_NATIVE_TITLE", "Native AgentScope Service")
    monkeypatch.setenv("AGENT_NATIVE_VERSION", "0.2.0")

    settings = native.NativeServiceSettings.from_env()

    assert settings.host == "0.0.0.0"
    assert settings.port == 8181
    assert settings.title == "Native AgentScope Service"
    assert settings.version == "0.2.0"


def test_native_service_settings_default_values(monkeypatch):
    monkeypatch.delenv("AGENT_NATIVE_HOST", raising=False)
    monkeypatch.delenv("AGENT_NATIVE_PORT", raising=False)
    monkeypatch.delenv("AGENT_NATIVE_TITLE", raising=False)
    monkeypatch.delenv("AGENT_NATIVE_VERSION", raising=False)

    settings = native.NativeServiceSettings.from_env()

    assert settings.host == native.DEFAULT_HTTP_HOST
    assert settings.port == native.DEFAULT_NATIVE_HTTP_PORT
    assert settings.title == native.NATIVE_SERVICE_TITLE
    assert settings.version == native.SERVICE_VERSION


def test_build_agent_app_returns_placeholder_message_when_unconfigured(monkeypatch):
    class FakeMsg:
        def __init__(self, name: str, content, role: str, id: str | None = None) -> None:
            self.name = name
            self.content = content
            self.role = role
            self.id = id or "msg-1"
            self.metadata = {}
            self.usage = None

    class FakeAgentApp:
        def __init__(self, app_name: str, app_description: str, lifespan) -> None:
            self.app_name = app_name
            self.app_description = app_description
            self.lifespan = lifespan
            self.state = SimpleNamespace(session=None)
            self.handler = None

        def query(self, framework: str):
            assert framework == "agentscope"

            def decorator(func):
                self.handler = func
                return func

            return decorator

    class FakeKernel:
        def __init__(self) -> None:
            self.settings = SimpleNamespace(agent_name="LubanOpsRuntime")

        def is_configured(self) -> bool:
            return False

        def build_unconfigured_message(self, message: str, session_id: str) -> str:
            return f"placeholder for {session_id}: {message}"

    monkeypatch.setattr(runtime, "Msg", FakeMsg)
    monkeypatch.setattr(runtime, "AgentApp", FakeAgentApp)
    monkeypatch.setattr(runtime, "get_runtime_kernel", FakeKernel)

    agent_app = runtime.build_agent_app()

    async def collect():
        return [
            event
            async for event in agent_app.handler(
                None,
                "hello",
                request=SimpleNamespace(session_id="ses-123", user_id="alice"),
            )
        ]

    events = asyncio.run(collect())

    assert len(events) == 1
    reply_msg, completed = events[0]
    assert completed is True
    assert reply_msg.name == "LubanOpsRuntime"
    assert reply_msg.role == "assistant"
    assert reply_msg.content == [{"type": "text", "text": "placeholder for ses-123: hello"}]


def test_build_agent_app_streams_messages_when_configured(monkeypatch):
    class FakeMsg:
        def __init__(self, name: str, content, role: str, id: str | None = None) -> None:
            self.name = name
            self.content = content
            self.role = role
            self.id = id or "reply-1"
            self.metadata = {}
            self.usage = None

    class FakeSessionManager:
        def __init__(self) -> None:
            self.loaded: list[tuple[str, str, object]] = []
            self.saved: list[tuple[str, str, object]] = []

        async def load_session_state(self, session_id: str, user_id: str, agent) -> None:
            self.loaded.append((session_id, user_id, agent))

        async def save_session_state(self, session_id: str, user_id: str, agent) -> None:
            self.saved.append((session_id, user_id, agent))

    session_manager = FakeSessionManager()

    class FakeAgentApp:
        def __init__(self, app_name: str, app_description: str, lifespan) -> None:
            self.app_name = app_name
            self.app_description = app_description
            self.lifespan = lifespan
            self.state = SimpleNamespace(session=session_manager)
            self.handler = None

        def query(self, framework: str):
            assert framework == "agentscope"

            def decorator(func):
                self.handler = func
                return func

            return decorator

    class FakeAgent:
        def __init__(self) -> None:
            self.console_output_enabled = True
            self.received = []

        def set_console_output_enabled(self, enabled: bool) -> None:
            self.console_output_enabled = enabled

        async def reply_stream(self, msgs):
            self.received.append(msgs)
            yield SimpleNamespace(type="TEXT_BLOCK_DELTA", reply_id="reply-1", block_id="blk-1", delta="hello")
            yield SimpleNamespace(type="TEXT_BLOCK_DELTA", reply_id="reply-1", block_id="blk-1", delta=" world")
            yield SimpleNamespace(type="REPLY_END", reply_id="reply-1")

    fake_agent = FakeAgent()

    class FakeKernel:
        def __init__(self) -> None:
            self.settings = SimpleNamespace(agent_name="LubanOpsRuntime")
            self.cleared = 0

        def is_configured(self) -> bool:
            return True

        def ensure_agent(self):
            return fake_agent, None

        def clear_error(self) -> None:
            self.cleared += 1

    monkeypatch.setattr(runtime, "Msg", FakeMsg)
    monkeypatch.setattr(runtime, "AgentApp", FakeAgentApp)
    monkeypatch.setattr(runtime, "get_runtime_kernel", FakeKernel)

    agent_app = runtime.build_agent_app()

    async def collect():
        return [
            event
            async for event in agent_app.handler(
                None,
                "hello",
                request=SimpleNamespace(session_id="ses-123", user_id="alice"),
            )
        ]

    events = asyncio.run(collect())

    assert [(msg.content, done) for msg, done in events] == [
        ([{"type": "text", "text": "hello"}], False),
        ([{"type": "text", "text": "hello world"}], False),
        ([{"type": "text", "text": "hello world"}], True),
    ]
    assert fake_agent.console_output_enabled is False
    assert fake_agent.received == ["hello"]
    assert session_manager.loaded == [("ses-123", "alice", fake_agent)]
    assert session_manager.saved == [("ses-123", "alice", fake_agent)]


def test_build_agent_app_preserves_multiple_reply_blocks(monkeypatch):
    class FakeMsg:
        def __init__(self, name: str, content, role: str, id: str | None = None) -> None:
            self.name = name
            self.content = content
            self.role = role
            self.id = id or "reply-1"
            self.metadata = {}
            self.usage = None

    class FakeAgentApp:
        def __init__(self, app_name: str, app_description: str, lifespan) -> None:
            self.app_name = app_name
            self.app_description = app_description
            self.lifespan = lifespan
            self.state = SimpleNamespace(session=None)
            self.handler = None

        def query(self, framework: str):
            assert framework == "agentscope"

            def decorator(func):
                self.handler = func
                return func

            return decorator

    class FakeAgent:
        async def reply_stream(self, msgs):
            _ = msgs
            yield SimpleNamespace(
                type="TEXT_BLOCK_DELTA",
                reply_id="reply-1",
                block_id="text-1",
                delta="answer",
            )
            yield SimpleNamespace(
                type="THINKING_BLOCK_DELTA",
                reply_id="reply-1",
                block_id="thinking-1",
                delta="reasoning",
            )
            yield SimpleNamespace(type="REPLY_END", reply_id="reply-1")

    class FakeKernel:
        def __init__(self) -> None:
            self.settings = SimpleNamespace(agent_name="LubanOpsRuntime")

        def is_configured(self) -> bool:
            return True

        def ensure_agent(self):
            return FakeAgent(), None

        def clear_error(self) -> None:
            return None

    monkeypatch.setattr(runtime, "Msg", FakeMsg)
    monkeypatch.setattr(runtime, "AgentApp", FakeAgentApp)
    monkeypatch.setattr(runtime, "get_runtime_kernel", FakeKernel)

    agent_app = runtime.build_agent_app()

    async def collect():
        return [
            event
            async for event in agent_app.handler(
                None,
                "hello",
                request=SimpleNamespace(session_id="ses-123", user_id="alice"),
            )
        ]

    events = asyncio.run(collect())

    assert [(msg.content, done) for msg, done in events] == [
        (
            [{"type": "text", "text": "answer"}],
            False,
        ),
        (
            [
                {"type": "text", "text": "answer"},
                {"type": "thinking", "thinking": "reasoning"},
            ],
            False,
        ),
        (
            [
                {"type": "text", "text": "answer"},
                {"type": "thinking", "thinking": "reasoning"},
            ],
            True,
        ),
    ]


def test_build_agent_app_returns_provider_fallback_when_streaming_fails(monkeypatch):
    class FakeMsg:
        def __init__(self, name: str, content, role: str, id: str | None = None) -> None:
            self.name = name
            self.content = content
            self.role = role
            self.id = id or "msg-1"
            self.metadata = {}
            self.usage = None

    class FakeAgentApp:
        def __init__(self, app_name: str, app_description: str, lifespan) -> None:
            self.app_name = app_name
            self.app_description = app_description
            self.lifespan = lifespan
            self.state = SimpleNamespace(session=None)
            self.handler = None

        def query(self, framework: str):
            assert framework == "agentscope"

            def decorator(func):
                self.handler = func
                return func

            return decorator

    class FakeAgent:
        async def reply_stream(self, msgs):
            if msgs is None:  # pragma: no cover
                yield None
            raise RuntimeError("provider exploded")

    class FakeKernel:
        def __init__(self) -> None:
            self.settings = SimpleNamespace(agent_name="LubanOpsRuntime")
            self.remembered_error = None

        def is_configured(self) -> bool:
            return True

        def ensure_agent(self):
            return FakeAgent(), None

        def clear_error(self) -> None:
            return None

        def remember_error(self, exc: Exception) -> None:
            self.remembered_error = str(exc)

        def build_provider_error_message(self, message: str, session_id: str) -> str:
            return f"provider fallback for {session_id}: {message}"

    monkeypatch.setattr(runtime, "Msg", FakeMsg)
    monkeypatch.setattr(runtime, "AgentApp", FakeAgentApp)
    monkeypatch.setattr(runtime, "get_runtime_kernel", FakeKernel)

    agent_app = runtime.build_agent_app()

    async def collect():
        return [
            event
            async for event in agent_app.handler(
                None,
                "hello",
                request=SimpleNamespace(session_id="ses-123", user_id="alice"),
            )
        ]

    events = asyncio.run(collect())

    assert len(events) == 1
    reply_msg, completed = events[0]
    assert completed is True
    assert reply_msg.content == [{"type": "text", "text": "provider fallback for ses-123: hello"}]
