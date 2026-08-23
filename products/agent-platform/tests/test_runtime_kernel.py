import asyncio
from types import SimpleNamespace

from agent_service.runtime_kernel import AgentKernel
from agent_service.runtime_settings import RuntimeSettings


def test_placeholder_reply_without_credentials():
    kernel = AgentKernel(settings=RuntimeSettings(api_key=None))

    content, structured_output = asyncio.run(
        kernel.reply_text(
            message="hello",
            session_id="ses-123",
            user_name="alice",
        )
    )

    assert "placeholder response" in content
    assert "ses-123" in content
    assert structured_output is None


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


class FakeAgentState:
    """Minimal AgentState double for post-turn snapshotting."""

    def model_dump_json(self):
        return "{}"


class FakeMemoryAgent:
    def __init__(self):
        self.history = []
        self.state = FakeAgentState()

    async def reply(self, msg, structured_schema=None):
        self.history.append(msg.content)
        return SimpleNamespace(content=f"turn {len(self.history)}")


def test_agent_conversation_state_never_crosses_sessions(monkeypatch):
    kernel = AgentKernel(settings=RuntimeSettings(api_key="test-key"))

    async def fake_build_agent(session_id, bearer_token=None):
        return (FakeMemoryAgent(), FakeUserMsg)

    monkeypatch.setattr(kernel, "_build_agent", fake_build_agent)

    reply_a1, _ = asyncio.run(kernel.reply_text("first", "ses-a", "alice"))
    reply_b1, _ = asyncio.run(kernel.reply_text("hello", "ses-b", "bob"))
    reply_a2, _ = asyncio.run(kernel.reply_text("second", "ses-a", "alice"))

    # ses-b starts with fresh memory; ses-a keeps its own history
    assert reply_a1 == "turn 1"
    assert reply_b1 == "turn 1"
    assert reply_a2 == "turn 2"


def test_ensure_agent_reuses_instance_per_session(monkeypatch):
    kernel = AgentKernel(settings=RuntimeSettings(api_key="test-key"))

    async def fake_build_agent(session_id, bearer_token=None):
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

    async def fake_build_agent(session_id, bearer_token=None):
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

    async def fake_build_agent(session_id, bearer_token=None):
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

        async def fake_discover(gateway_url, bearer_token=None):
            calls.append((gateway_url, bearer_token))
            return [
                {
                    "name": "k8s.list_pods",
                    "description": "x",
                    "risk_level": "read",
                    "parameters_schema": {"type": "object"},
                }
            ]

        monkeypatch.setattr(
            "agent_service.tools.gateway_tools.discover_tools", fake_discover
        )

        first = asyncio.run(kernel._ensure_toolkit("token-a"))
        second = asyncio.run(kernel._ensure_toolkit("token-a"))

        assert first is second
        assert calls == [("http://gw:8080", "token-a")]

    def test_different_tokens_get_distinct_toolkits(self, monkeypatch):
        kernel = self._kernel()
        seen_tokens = []

        async def fake_discover(gateway_url, bearer_token=None):
            seen_tokens.append(bearer_token)
            return [
                {
                    "name": "k8s.list_pods",
                    "description": "x",
                    "risk_level": "read",
                    "parameters_schema": {"type": "object"},
                }
            ]

        monkeypatch.setattr(
            "agent_service.tools.gateway_tools.discover_tools", fake_discover
        )

        toolkit_a = asyncio.run(kernel._ensure_toolkit("token-a"))
        toolkit_b = asyncio.run(kernel._ensure_toolkit("token-b"))

        assert toolkit_a is not toolkit_b
        assert seen_tokens == ["token-a", "token-b"]

    def test_no_token_degrades_to_empty_toolkit_without_discovery(self, monkeypatch):
        kernel = self._kernel()
        calls = []

        async def fake_discover(gateway_url, bearer_token=None):
            # Without a token discovery short-circuits to an empty list.
            assert bearer_token is None
            calls.append(gateway_url)
            return []

        monkeypatch.setattr(
            "agent_service.tools.gateway_tools.discover_tools", fake_discover
        )

        toolkit = asyncio.run(kernel._ensure_toolkit(None))

        assert toolkit is not None
        # SPEC-018 R-2: an empty discovery is intentionally NOT cached, so a
        # later turn retries discovery instead of being stuck with no tools.
        assert asyncio.run(kernel._ensure_toolkit(None)) is not toolkit
        assert calls == ["http://gw:8080", "http://gw:8080"]


class TestToolkitRegistration:
    """Regression: the token-cached toolkit must really register gateway tools.

    AgentScope 2.x removed ``Toolkit.add``; a toolkit built without tools is
    empty and the model can never invoke the gateway (root cause of the
    hallucinated health report). After SPEC-018 removed the per-request
    toolkit rebuild, these tests assert the schemas are really present on the
    per-token cached toolkit.
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

    def _kernel(self, **overrides):
        return AgentKernel(
            settings=RuntimeSettings(
                api_key="test-key",
                tool_gateway_url="http://gw:8080",
                **overrides,
            )
        )

    def _patch_discover(self, monkeypatch, definitions):
        calls = []

        async def fake_discover(gateway_url, bearer_token=None):
            calls.append((gateway_url, bearer_token))
            return definitions

        monkeypatch.setattr(
            "agent_service.tools.gateway_tools.discover_tools", fake_discover
        )
        return calls

    def test_ensure_toolkit_registers_discovered_definitions(self, monkeypatch):
        kernel = self._kernel()
        calls = self._patch_discover(monkeypatch, [self.DEFINITION])

        toolkit = asyncio.run(kernel._ensure_toolkit("token-a"))

        schemas = asyncio.run(toolkit.get_tool_schemas())
        names = {schema["function"]["name"] for schema in schemas}
        assert names == {"k8s_list_pods"}
        assert calls == [("http://gw:8080", "token-a")]
        # Cached per token: a later turn reuses it without re-discovering.
        assert asyncio.run(kernel._ensure_toolkit("token-a")) is toolkit
        assert len(calls) == 1

    def test_rotated_token_discovers_on_cache_miss(self, monkeypatch):
        """Regression: delegated tokens rotate mid-session (portal token
        refresh). A token with no cached toolkit must run discovery instead
        of serving an empty toolkit (which injected the no-tools notice for
        every subsequent turn until browser refresh)."""
        kernel = self._kernel()
        calls = self._patch_discover(monkeypatch, [self.DEFINITION])

        asyncio.run(kernel._ensure_toolkit("token-old"))
        toolkit = asyncio.run(kernel._ensure_toolkit("token-new"))

        assert calls == [
            ("http://gw:8080", "token-old"),
            ("http://gw:8080", "token-new"),
        ]
        schemas = asyncio.run(toolkit.get_tool_schemas())
        names = {schema["function"]["name"] for schema in schemas}
        assert names == {"k8s_list_pods"}
        # The result is cached under the new token.
        assert asyncio.run(kernel._ensure_toolkit("token-new")) is toolkit

    def test_empty_discovery_result_is_not_cached(self, monkeypatch):
        """A failed/empty discovery must not poison the cache: the next turn
        retries discovery instead of being stuck with no tools."""
        kernel = self._kernel()
        results = [[], [self.DEFINITION]]

        async def fake_discover(gateway_url, bearer_token=None):
            return results.pop(0)

        monkeypatch.setattr(
            "agent_service.tools.gateway_tools.discover_tools", fake_discover
        )

        first = asyncio.run(kernel._ensure_toolkit("token-a"))
        assert asyncio.run(first.get_tool_schemas()) == []

        toolkit = asyncio.run(kernel._ensure_toolkit("token-a"))

        schemas = asyncio.run(toolkit.get_tool_schemas())
        names = {schema["function"]["name"] for schema in schemas}
        assert names == {"k8s_list_pods"}

    def test_task_tools_appended_and_excluded_from_gateway_count(self, monkeypatch):
        """R-5: opt-in task tools join the cached toolkit but never count as
        gateway tools, so the no-tools guard stays accurate."""
        kernel = self._kernel(task_tools_enabled=True)
        self._patch_discover(monkeypatch, [self.DEFINITION])

        toolkit = asyncio.run(kernel._ensure_toolkit("token-a"))

        schemas = asyncio.run(toolkit.get_tool_schemas())
        names = {schema["function"]["name"] for schema in schemas}
        assert names == {
            "k8s_list_pods",
            "TaskCreate",
            "TaskGet",
            "TaskList",
            "TaskUpdate",
        }
        assert kernel._count_gateway_tools(toolkit) == 1

    def test_task_tools_only_toolkit_when_gateway_empty(self, monkeypatch):
        kernel = self._kernel(task_tools_enabled=True)
        self._patch_discover(monkeypatch, [])

        toolkit = asyncio.run(kernel._ensure_toolkit("token-a"))

        schemas = asyncio.run(toolkit.get_tool_schemas())
        names = {schema["function"]["name"] for schema in schemas}
        assert names == {"TaskCreate", "TaskGet", "TaskList", "TaskUpdate"}
        assert kernel._count_gateway_tools(toolkit) == 0
        # Empty gateway discovery stays uncached even with task tools.
        assert asyncio.run(kernel._ensure_toolkit("token-a")) is not toolkit

    def test_count_gateway_tools(self):
        from agentscope.tool import Toolkit

        from agent_service.tools.gateway_tools import build_gateway_toolkit

        kernel = self._kernel()

        assert kernel._count_gateway_tools(Toolkit()) == 0

        populated = build_gateway_toolkit([self.DEFINITION], "http://gw:8080")
        assert kernel._count_gateway_tools(populated) == 1


class TestAgentRebuildOnToolRecovery:
    """SPEC-018 R-2: the agent is no longer rebuilt per request, so a cached
    agent that started with zero gateway tools must be rebuilt once discovery
    recovers — persisted state (SPEC-017 R-3) restores its memory."""

    def test_cached_agent_rebuilds_when_gateway_tools_recover(self, monkeypatch):
        kernel = AgentKernel(
            settings=RuntimeSettings(
                api_key="test-key",
                tool_gateway_url="http://gw:8080",
            )
        )
        results = [[], [TestToolkitRegistration.DEFINITION]]

        async def fake_discover(gateway_url, bearer_token=None):
            return results.pop(0)

        monkeypatch.setattr(
            "agent_service.tools.gateway_tools.discover_tools", fake_discover
        )

        builds = 0

        async def fake_build_agent(session_id, bearer_token=None):
            nonlocal builds
            builds += 1
            agent = FakeMemoryAgent()
            # Reflect the toolkit the real Agent would have received.
            agent.toolkit = await kernel._ensure_toolkit(bearer_token)
            return (agent, FakeUserMsg)

        monkeypatch.setattr(kernel, "_build_agent", fake_build_agent)

        agent_1, _ = asyncio.run(kernel.ensure_agent("ses-r", "token-a"))
        assert builds == 1
        assert kernel._count_gateway_tools(agent_1.toolkit) == 0

        # Discovery recovers: the stale agent is replaced, not reused.
        agent_2, _ = asyncio.run(kernel.ensure_agent("ses-r", "token-a"))
        assert builds == 2
        assert agent_2 is not agent_1
        assert kernel._count_gateway_tools(agent_2.toolkit) == 1

        # Steady state afterwards: no further rebuilds.
        agent_3, _ = asyncio.run(kernel.ensure_agent("ses-r", "token-a"))
        assert builds == 2
        assert agent_3 is agent_2

    def test_ensure_agent_survives_eviction_during_recovery_check(self, monkeypatch):
        """The await in the recovery check opens a preemption window: LRU
        eviction (or a concurrent rebuild) may remove the session entry while
        ``_ensure_toolkit`` is awaiting. The fast path must fall through to
        the locked rebuild instead of raising KeyError."""
        kernel = AgentKernel(settings=RuntimeSettings(api_key="test-key"))
        builds = 0

        async def fake_build_agent(session_id, bearer_token=None):
            nonlocal builds
            builds += 1
            return (FakeMemoryAgent(), FakeUserMsg)

        monkeypatch.setattr(kernel, "_build_agent", fake_build_agent)

        asyncio.run(kernel.ensure_agent("ses-e"))
        assert builds == 1

        # Simulate eviction happening inside the recovery-check await.
        async def evicting_ensure_toolkit(bearer_token=None):
            kernel._agents.pop("ses-e", None)
            from agentscope.tool import Toolkit

            return Toolkit()

        monkeypatch.setattr(kernel, "_ensure_toolkit", evicting_ensure_toolkit)

        agent, _ = asyncio.run(kernel.ensure_agent("ses-e"))

        assert builds == 2
        assert agent is not None


# ---------------------------------------------------------------------------
# SPEC-017 R-1: settings-driven kernel configs
# ---------------------------------------------------------------------------


class TestKernelConfigs:
    def test_configs_carry_settings_values(self):
        kernel = AgentKernel(
            settings=RuntimeSettings(
                api_key="test-key",
                max_iters=30,
                context_trigger_ratio=0.6,
                tool_result_limit=20000,
                timezone="Asia/Shanghai",
                model_max_retries=2,
            )
        )

        configs = kernel._build_kernel_configs()

        assert configs["react_config"].max_iters == 30
        assert configs["context_config"].trigger_ratio == 0.6
        assert configs["context_config"].tool_result_limit == 20000
        assert configs["injection_config"].timezone == "Asia/Shanghai"
        assert configs["injection_config"].inject_runtime_state is True
        assert configs["model_config"].max_retries == 2

    def test_configs_default_to_agentscope_values(self):
        kernel = AgentKernel(settings=RuntimeSettings(api_key="test-key"))

        configs = kernel._build_kernel_configs()

        assert configs["react_config"].max_iters == 20
        assert configs["context_config"].trigger_ratio == 0.8
        assert configs["context_config"].tool_result_limit == 50000
        assert configs["injection_config"].timezone == "UTC"
        assert configs["model_config"].max_retries == 0


# ---------------------------------------------------------------------------
# SPEC-017 R-2: structured output round trip
# ---------------------------------------------------------------------------


class FakeStructuredAgent:
    """Echoes the requested schema back as kernel-validated output."""

    def __init__(self):
        self.state = FakeAgentState()
        self.seen_schemas = []

    async def reply(self, msg, structured_schema=None):
        self.seen_schemas.append(structured_schema)
        structured = (
            {"summary": "validated", "schema_echo": structured_schema}
            if structured_schema is not None
            else None
        )
        return SimpleNamespace(
            content="structured turn", structured_output=structured
        )


SCHEMA = {"type": "object", "properties": {"summary": {"type": "string"}}}


def test_reply_text_passes_schema_and_returns_structured_output(monkeypatch):
    kernel = AgentKernel(settings=RuntimeSettings(api_key="test-key"))
    agent = FakeStructuredAgent()

    async def fake_build_agent(session_id, bearer_token=None):
        return (agent, FakeUserMsg)

    monkeypatch.setattr(kernel, "_build_agent", fake_build_agent)

    content, structured = asyncio.run(
        kernel.reply_text(
            "triage it", "ses-s", "alice", response_schema=SCHEMA
        )
    )

    assert content == "structured turn"
    assert structured["summary"] == "validated"
    assert structured["schema_echo"] == SCHEMA
    assert agent.seen_schemas == [SCHEMA]


def test_reply_text_without_schema_returns_none_structured(monkeypatch):
    kernel = AgentKernel(settings=RuntimeSettings(api_key="test-key"))
    agent = FakeStructuredAgent()

    async def fake_build_agent(session_id, bearer_token=None):
        return (agent, FakeUserMsg)

    monkeypatch.setattr(kernel, "_build_agent", fake_build_agent)

    content, structured = asyncio.run(
        kernel.reply_text("hello", "ses-s", "alice")
    )

    assert content == "structured turn"
    assert structured is None
    assert agent.seen_schemas == [None]


# ---------------------------------------------------------------------------
# SPEC-017 R-3: conversation state persistence
# ---------------------------------------------------------------------------


def test_reply_text_snapshots_state_after_turn(monkeypatch):
    from agent_service.services.agent_state_store import InMemoryAgentStateStore

    store = InMemoryAgentStateStore()
    monkeypatch.setattr(
        "agent_service.runtime_kernel.AGENT_STATE_STORE", store
    )
    kernel = AgentKernel(settings=RuntimeSettings(api_key="test-key"))

    async def fake_build_agent(session_id, bearer_token=None):
        return (FakeMemoryAgent(), FakeUserMsg)

    monkeypatch.setattr(kernel, "_build_agent", fake_build_agent)

    asyncio.run(kernel.reply_text("hello", "ses-durable", "alice"))

    assert store.load_state("ses-durable") == "{}"


def test_snapshot_failure_never_fails_the_turn(monkeypatch):
    class BrokenStore:
        def save_state(self, session_id, state_json):
            raise RuntimeError("state store down")

    monkeypatch.setattr(
        "agent_service.runtime_kernel.AGENT_STATE_STORE", BrokenStore()
    )
    kernel = AgentKernel(settings=RuntimeSettings(api_key="test-key"))

    async def fake_build_agent(session_id, bearer_token=None):
        return (FakeMemoryAgent(), FakeUserMsg)

    monkeypatch.setattr(kernel, "_build_agent", fake_build_agent)

    content, structured = asyncio.run(
        kernel.reply_text("hello", "ses-x", "alice")
    )
    assert content == "turn 1"
    assert structured is None


def test_restore_state_round_trips_real_agent_state(monkeypatch):
    from agentscope.state import AgentState

    from agent_service.services.agent_state_store import InMemoryAgentStateStore

    store = InMemoryAgentStateStore()
    monkeypatch.setattr(
        "agent_service.runtime_kernel.AGENT_STATE_STORE", store
    )
    kernel = AgentKernel(settings=RuntimeSettings(api_key="test-key"))

    store.save_state("ses-r", AgentState().model_dump_json())

    restored = kernel._restore_state("ses-r")
    assert isinstance(restored, AgentState)


def test_restore_state_missing_returns_none(monkeypatch):
    from agent_service.services.agent_state_store import InMemoryAgentStateStore

    monkeypatch.setattr(
        "agent_service.runtime_kernel.AGENT_STATE_STORE",
        InMemoryAgentStateStore(),
    )
    kernel = AgentKernel(settings=RuntimeSettings(api_key="test-key"))
    assert kernel._restore_state("ses-empty") is None


def test_restore_state_discards_corrupt_row(monkeypatch):
    from agent_service.services.agent_state_store import InMemoryAgentStateStore

    store = InMemoryAgentStateStore()
    monkeypatch.setattr(
        "agent_service.runtime_kernel.AGENT_STATE_STORE", store
    )
    kernel = AgentKernel(settings=RuntimeSettings(api_key="test-key"))

    store.save_state("ses-poison", "{not valid agent state")

    # A poisoned snapshot must never wedge the session: fresh agent instead.
    assert kernel._restore_state("ses-poison") is None


def test_task_state_round_trips_through_state_store(monkeypatch):
    """SPEC-018 R-5: task tools mutate only AgentState.tasks_context, so the
    SPEC-017 snapshot/restore path persists them with no extra machinery."""
    from agentscope.state import AgentState
    from agentscope.tool import TaskCreate

    from agent_service.services.agent_state_store import InMemoryAgentStateStore

    store = InMemoryAgentStateStore()
    monkeypatch.setattr(
        "agent_service.runtime_kernel.AGENT_STATE_STORE", store
    )
    kernel = AgentKernel(settings=RuntimeSettings(api_key="test-key"))

    state = AgentState()
    asyncio.run(
        TaskCreate().call(
            _agent_state=state,
            subject="diagnose crashloop",
            description="inspect pod restarts",
        )
    )

    # Post-turn snapshot, then restore as a freshly rebuilt agent would.
    kernel._snapshot_state("ses-task", SimpleNamespace(state=state))
    restored = kernel._restore_state("ses-task")

    assert restored is not None
    subjects = [task.subject for task in restored.tasks_context.tasks]
    assert subjects == ["diagnose crashloop"]


# ---------------------------------------------------------------------------
# SPEC-025 R-1: evidence persistence hook
# ---------------------------------------------------------------------------


class FakeEvidenceStore:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.saved: list[tuple] = []

    def save_turn(self, session_id, request_id, turn_index, frames, budget):
        if self.fail:
            raise RuntimeError("evidence store down")
        self.saved.append((session_id, request_id, turn_index, frames, budget))


def _evidence_frames():
    return [
        {
            "type": "tool_call",
            "tool_name": "k8s.list_pods",
            "call_id": "call-1",
            "parameters": {"namespace": "ops"},
        },
        {
            "type": "tool_result",
            "tool_name": "k8s.list_pods",
            "call_id": "call-1",
            "status": "success",
            "data": {"pods": []},
        },
    ]


class TestEvidencePersistenceHook:
    def test_count_user_turns_counts_user_messages(self):
        kernel = AgentKernel(settings=RuntimeSettings(api_key=None))
        agent = SimpleNamespace(
            state=SimpleNamespace(
                context=[
                    SimpleNamespace(role="system"),
                    SimpleNamespace(role="user"),
                    SimpleNamespace(role="assistant"),
                    SimpleNamespace(role="user"),
                ]
            )
        )
        assert kernel._count_user_turns(agent) == 2

    def test_count_user_turns_degrades_to_zero(self):
        kernel = AgentKernel(settings=RuntimeSettings(api_key=None))
        assert kernel._count_user_turns(SimpleNamespace()) == 0

    def test_persist_evidence_saves_prepared_frames(self, monkeypatch):
        import agent_service.runtime_kernel as rk

        store = FakeEvidenceStore()
        monkeypatch.setattr(rk, "EVIDENCE_STORE", store)
        kernel = AgentKernel(settings=RuntimeSettings(api_key=None))

        kernel._persist_evidence("ses-1", "req-1", 3, _evidence_frames())

        assert len(store.saved) == 1
        session_id, request_id, turn_index, frames, budget = store.saved[0]
        assert (session_id, request_id, turn_index) == ("ses-1", "req-1", 3)
        assert [frame["type"] for frame in frames] == [
            "tool_call",
            "tool_result",
        ]
        assert budget == kernel.settings.evidence_session_max_bytes

    def test_persist_evidence_applies_entry_cap(self, monkeypatch):
        import agent_service.runtime_kernel as rk

        store = FakeEvidenceStore()
        monkeypatch.setattr(rk, "EVIDENCE_STORE", store)
        kernel = AgentKernel(
            settings=RuntimeSettings(api_key=None, evidence_entry_max_chars=10)
        )
        frames = _evidence_frames()
        frames[1]["data"] = {"blob": "x" * 100}

        kernel._persist_evidence("ses-1", "req-1", 0, frames)

        saved_frame = store.saved[0][3][1]
        assert isinstance(saved_frame["data"], str)
        assert len(saved_frame["data"]) == 10
        assert saved_frame["truncated"]["reason"] == "entry_cap"

    def test_persist_evidence_failure_never_raises(self, monkeypatch):
        import agent_service.runtime_kernel as rk
        from prometheus_client import REGISTRY

        monkeypatch.setattr(rk, "EVIDENCE_STORE", FakeEvidenceStore(fail=True))
        kernel = AgentKernel(settings=RuntimeSettings(api_key=None))

        before = (
            REGISTRY.get_sample_value(
                "evidence_store_writes_total", {"result": "error"}
            )
            or 0.0
        )
        kernel._persist_evidence("ses-1", "req-1", 0, _evidence_frames())
        assert (
            REGISTRY.get_sample_value(
                "evidence_store_writes_total", {"result": "error"}
            )
            == before + 1
        )

    def test_persist_evidence_skips_empty_frame_list(self, monkeypatch):
        import agent_service.runtime_kernel as rk

        store = FakeEvidenceStore()
        monkeypatch.setattr(rk, "EVIDENCE_STORE", store)
        kernel = AgentKernel(settings=RuntimeSettings(api_key=None))

        kernel._persist_evidence("ses-1", "req-1", 0, [])
        assert store.saved == []
