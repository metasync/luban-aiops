"""SPEC-024 R-3: per-turn model selection, session pinning, kernel switching.

Covers the resolution order (request > pinned > default), fail-closed 422
for unknown ids, session-store affinity across the three backends, the
kernel's cached-agent rebuild on model switch, and the message_end model
attribution on streamed turns.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import fakeredis
import pytest
from fastapi.testclient import TestClient

from agent_service import runtime_kernel
from agent_service.api.v2 import routes as v2_routes
from agent_service.app import create_app
from agent_service.runtime_kernel import AgentKernel
from agent_service.runtime_settings import RuntimeSettings
from agent_service.services import session_service
from agent_service.services.session_service import pin_session_model
from agent_service.services.session_store import (
    InMemorySessionStore,
    PostgresSessionStore,
    RedisSessionStore,
)


class FakeCatalog:
    """Catalog double: ids are the known model ids, default may be absent."""

    def __init__(self, ids=(), default=None):
        self._ids = set(ids)
        self._default = default

    def get(self, model_id):
        # Routes/kernel consume ``entry.id`` (SPEC-026).
        return SimpleNamespace(id=model_id) if model_id in self._ids else None

    def default_entry(self):
        return SimpleNamespace(id=self._default) if self._default else None


# ---------------------------------------------------------------------------
# Resolution order: request > pinned > default, fail-closed on unknown
# ---------------------------------------------------------------------------


class TestResolveModel:
    def test_requested_known_wins_over_pinned_and_default(self, monkeypatch):
        monkeypatch.setattr(
            v2_routes, "MODEL_CATALOG",
            FakeCatalog(ids=("deepseek", "openai"), default="openai"),
        )
        assert v2_routes._resolve_model("deepseek", "openai") == "deepseek"

    def test_requested_unknown_fails_closed_with_422(self, monkeypatch):
        monkeypatch.setattr(
            v2_routes, "MODEL_CATALOG",
            FakeCatalog(ids=("deepseek",), default="deepseek"),
        )
        with pytest.raises(Exception) as exc_info:
            v2_routes._resolve_model("ghost", None)
        assert exc_info.value.status_code == 422

    def test_pinned_honored_when_request_absent(self, monkeypatch):
        monkeypatch.setattr(
            v2_routes, "MODEL_CATALOG",
            FakeCatalog(ids=("deepseek", "openai"), default="openai"),
        )
        assert v2_routes._resolve_model(None, "deepseek") == "deepseek"

    def test_pinned_absent_from_catalog_degrades_to_default(self, monkeypatch):
        # A revoked key drops the entry; the session must not 4xx.
        monkeypatch.setattr(
            v2_routes, "MODEL_CATALOG",
            FakeCatalog(ids=("openai",), default="openai"),
        )
        assert v2_routes._resolve_model(None, "deepseek") == "openai"

    def test_no_request_no_pin_resolves_default(self, monkeypatch):
        monkeypatch.setattr(
            v2_routes, "MODEL_CATALOG",
            FakeCatalog(ids=("openai",), default="openai"),
        )
        assert v2_routes._resolve_model(None, None) == "openai"

    def test_empty_catalog_resolves_none(self, monkeypatch):
        monkeypatch.setattr(v2_routes, "MODEL_CATALOG", FakeCatalog())
        assert v2_routes._resolve_model(None, "deepseek") is None


# ---------------------------------------------------------------------------
# Route wiring: 422 fail-closed, response attribution, session pinning
# ---------------------------------------------------------------------------


class TestChatRouteModelWiring:
    def _client_with_catalog(self, monkeypatch, ids, default):
        monkeypatch.setattr(
            v2_routes, "MODEL_CATALOG", FakeCatalog(ids=ids, default=default)
        )
        return TestClient(create_app())

    def test_chat_unknown_model_fails_closed(self, monkeypatch):
        client = self._client_with_catalog(monkeypatch, ("deepseek",), "deepseek")
        response = client.post(
            "/api/v2/chat",
            json={"message": "hello", "model": "ghost"},
            headers={"X-User-ID": "alice"},
        )
        assert response.status_code == 422
        assert "ghost" in response.json()["detail"]

    def test_chat_known_model_resolves_pins_and_echoes(self, monkeypatch):
        client = self._client_with_catalog(
            monkeypatch, ("deepseek", "openai"), "openai"
        )
        session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
        session_id = session.json()["session_id"]

        response = client.post(
            "/api/v2/chat",
            json={
                "message": "hello",
                "session_id": session_id,
                "model": "deepseek",
            },
            headers={"X-User-ID": "alice"},
        )
        assert response.status_code == 200
        assert response.json()["model"] == "deepseek"

        # The resolved model rides the session record (affinity, Q-4).
        detail = client.get(
            f"/api/v2/sessions/{session_id}", headers={"X-User-ID": "alice"}
        )
        assert detail.json()["model"] == "deepseek"

    def test_chat_stream_unknown_model_fails_closed_before_headers(
        self, monkeypatch
    ):
        client = self._client_with_catalog(monkeypatch, ("deepseek",), "deepseek")
        response = client.get(
            "/api/v2/chat/stream",
            params={"message": "hello", "model": "ghost"},
            headers={"X-User-ID": "alice"},
        )
        assert response.status_code == 422


def test_normalize_stream_event_passes_model_through():
    event = v2_routes._normalize_stream_event(
        {"event": "message_end", "model": "deepseek"}, "ses-1", "req-1"
    )
    assert event.model == "deepseek"

    event = v2_routes._normalize_stream_event(
        {"event": "message_end"}, "ses-1", "req-1"
    )
    assert event.model is None


# ---------------------------------------------------------------------------
# Session-store affinity across backends
# ---------------------------------------------------------------------------


class TestSessionModelPinning:
    def test_inmemory_store_round_trip(self):
        store = InMemorySessionStore()
        record = store.create_session("alice")
        store.set_session_model(record.session_id, "deepseek")
        assert store.get_session(record.session_id).model == "deepseek"
        # Newest wins: a later turn can re-pin.
        store.set_session_model(record.session_id, "openai")
        assert store.get_session(record.session_id).model == "openai"

    def test_redis_store_round_trip(self):
        store = RedisSessionStore(
            client=fakeredis.FakeRedis(decode_responses=False), ttl_seconds=600
        )
        record = store.create_session("alice")
        store.set_session_model(record.session_id, "deepseek")
        assert store.get_session(record.session_id).model == "deepseek"

    def test_postgres_store_updates_model(self):
        calls: list[dict] = []

        class FakeCursor:
            def execute(self, sql, params=None):
                calls.append({"sql": sql, "params": params})

            def fetchone(self):
                return None

            def fetchall(self):
                return []

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class FakeConn:
            def cursor(self):
                return FakeCursor()

            def commit(self):
                return None

            def close(self):
                return None

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        store = PostgresSessionStore(
            "postgresql://fake", connect=lambda **kwargs: FakeConn()
        )
        store.set_session_model("ses-1", "deepseek")
        assert any(
            "UPDATE sessions" in call["sql"]
            and "SET model = %(model)s" in call["sql"]
            and call["params"]["model"] == "deepseek"
            for call in calls
        )

    def test_pin_helper_fail_open(self, monkeypatch):
        class BrokenStore:
            def set_session_model(self, session_id, model):
                raise RuntimeError("store down")

        monkeypatch.setattr(session_service, "SESSION_STORE", BrokenStore())
        # Must never raise: bookkeeping never fails a turn.
        pin_session_model("ses-1", "deepseek")

    def test_pin_helper_skips_none(self, monkeypatch):
        called = []

        class RecordingStore:
            def set_session_model(self, session_id, model):
                called.append((session_id, model))

        monkeypatch.setattr(session_service, "SESSION_STORE", RecordingStore())
        pin_session_model("ses-1", None)
        assert called == []


# ---------------------------------------------------------------------------
# Kernel: fail-closed stream, model attribution, switch-on-demand rebuild
# ---------------------------------------------------------------------------


class FakeUserMsg:
    def __init__(self, name, content):
        self.name = name
        self.content = content


class FakeAgentState:
    def model_dump_json(self):
        return "{}"


class FakeEndAgent:
    """Yields a single message_end event."""

    def __init__(self):
        self.toolkit = None
        self.state = FakeAgentState()

    async def reply_stream(self, inputs):
        yield SimpleNamespace(type="message_end", message="complete")


def _drain(async_iter) -> list:
    async def _collect():
        return [frame async for frame in async_iter]

    return asyncio.run(_collect())


def _configured_kernel() -> AgentKernel:
    return AgentKernel(settings=RuntimeSettings(api_key="test-key"))


def test_stream_events_unknown_model_fails_closed(monkeypatch):
    kernel = _configured_kernel()
    monkeypatch.setattr(runtime_kernel, "MODEL_CATALOG", FakeCatalog())

    frames = _drain(
        kernel.stream_events(
            message="hello",
            request_id="req-1",
            session_id="ses-1",
            user_name="alice",
            model_id="ghost",
        )
    )

    assert len(frames) == 1
    assert frames[0]["event"] == "error"
    assert frames[0]["error"]["code"] == "unknown_model"
    assert "ghost" in frames[0]["error"]["message"]


def test_stream_message_end_carries_serving_model(monkeypatch):
    kernel = _configured_kernel()
    monkeypatch.setattr(
        runtime_kernel, "MODEL_CATALOG",
        FakeCatalog(ids=("deepseek",), default="deepseek"),
    )

    async def fake_build_agent(session_id, bearer_token=None, model_id=None, read_only=False):
        return (FakeEndAgent(), FakeUserMsg, model_id or kernel.settings.provider)

    monkeypatch.setattr(kernel, "_build_agent", fake_build_agent)
    monkeypatch.setattr(kernel, "_snapshot_state", lambda session_id, agent: None)
    monkeypatch.setattr(kernel, "_persist_evidence", lambda *args: None)

    frames = _drain(
        kernel.stream_events(
            message="hello",
            request_id="req-1",
            session_id="ses-1",
            user_name="alice",
            model_id="deepseek",
        )
    )

    end_frames = [f for f in frames if f.get("event") == "message_end"]
    assert len(end_frames) == 1
    assert end_frames[0]["model"] == "deepseek"


def test_fallback_message_attributes_serving_provider(monkeypatch):
    """A dashscope model failure must not blame the active profile's
    provider (deepseek here) in the fallback text."""
    from agent_service.services.model_catalog import (
        ModelCatalog,
        ModelCatalogEntry,
    )

    entry = ModelCatalogEntry(
        id="qwen3-8b",
        label="qwen3-8b",
        provider="dashscope",
        api_key="sk-x",
        model_name="qwen3-8b",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default=False,
    )
    kernel = AgentKernel(
        settings=RuntimeSettings(provider="deepseek", api_key="test-key")
    )
    kernel.remember_error(RuntimeError("403 accessdenied"))
    monkeypatch.setattr(
        runtime_kernel, "MODEL_CATALOG", ModelCatalog((entry,))
    )

    text = kernel.build_provider_error_message("hello", "ses-1", "qwen3-8b")
    assert "dashscope (model qwen3-8b)" in text
    assert "provider deepseek failed" not in text

    # Without model context the profile provider attribution is unchanged.
    text = kernel.build_provider_error_message("hello", "ses-1")
    assert "AgentScope provider deepseek failed" in text


def test_ensure_agent_rebuilds_on_model_switch(monkeypatch):
    kernel = _configured_kernel()
    builds: list[str | None] = []

    async def fake_build_agent(session_id, bearer_token=None, model_id=None, read_only=False):
        builds.append(model_id)
        return (
            FakeEndAgent(),
            FakeUserMsg,
            model_id or kernel.settings.provider,
        )

    monkeypatch.setattr(kernel, "_build_agent", fake_build_agent)

    agent_a, _, bound_a = asyncio.run(kernel.ensure_agent("ses-m"))
    agent_b, _, bound_b = asyncio.run(
        kernel.ensure_agent("ses-m", model_id="deepseek")
    )

    # First turn binds the deploy-time provider; the switch rebuilds.
    assert bound_a == kernel.settings.provider
    assert bound_b == "deepseek"
    assert len(builds) == 2
    assert agent_a is not agent_b

    # Steady state on the new model: no further rebuilds.
    agent_c, _, bound_c = asyncio.run(
        kernel.ensure_agent("ses-m", model_id="deepseek")
    )
    assert bound_c == "deepseek"
    assert agent_c is agent_b
    assert len(builds) == 2
