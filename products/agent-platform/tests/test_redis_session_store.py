"""Tests for RedisSessionStore and the build_session_store factory (SPEC-006)."""

from __future__ import annotations

import time

import fakeredis
import pytest

from agent_service.schemas.api import SessionRecord
from agent_service.services.session_store import (
    InMemorySessionStore,
    RedisSessionStore,
    build_session_store,
)


@pytest.fixture()
def redis_client():
    """Return a fakeredis client for testing."""
    return fakeredis.FakeRedis(decode_responses=False)


@pytest.fixture()
def redis_store(redis_client):
    """Return a RedisSessionStore backed by fakeredis."""
    return RedisSessionStore(client=redis_client, ttl_seconds=60)


# ---------------------------------------------------------------------------
# RedisSessionStore CRUD
# ---------------------------------------------------------------------------


class TestRedisSessionStoreCRUD:
    def test_create_and_get(self, redis_store):
        record = redis_store.create_session("alice")

        assert record.session_id.startswith("ses-")
        assert record.user_id == "alice"

        fetched = redis_store.get_session(record.session_id)
        assert fetched is not None
        assert fetched.session_id == record.session_id
        assert fetched.user_id == "alice"

    def test_get_missing_returns_none(self, redis_store):
        assert redis_store.get_session("ses-nonexistent") is None

    def test_delete_session(self, redis_store):
        record = redis_store.create_session("alice")
        assert redis_store.delete_session(record.session_id) is True
        assert redis_store.get_session(record.session_id) is None

    def test_delete_missing_returns_false(self, redis_store):
        assert redis_store.delete_session("ses-nonexistent") is False

    def test_create_session_without_user(self, redis_store):
        record = redis_store.create_session(None)
        assert record.user_id is None
        fetched = redis_store.get_session(record.session_id)
        assert fetched is not None
        assert fetched.user_id is None

    def test_len_counts_active_sessions(self, redis_store):
        assert len(redis_store) == 0
        redis_store.create_session("alice")
        redis_store.create_session("bob")
        assert len(redis_store) == 2


# ---------------------------------------------------------------------------
# User-scoped listing
# ---------------------------------------------------------------------------


class TestRedisUserListing:
    def test_list_sessions_by_user(self, redis_store):
        redis_store.create_session("alice")
        redis_store.create_session("alice")
        redis_store.create_session("bob")

        alice_sessions = redis_store.list_sessions_by_user("alice")
        assert len(alice_sessions) == 2
        assert all(s.user_id == "alice" for s in alice_sessions)

    def test_list_sessions_empty_user(self, redis_store):
        redis_store.create_session("alice")
        assert redis_store.list_sessions_by_user("nobody") == []

    def test_delete_removes_from_user_index(self, redis_store):
        record = redis_store.create_session("alice")
        redis_store.delete_session(record.session_id)
        assert redis_store.list_sessions_by_user("alice") == []


# ---------------------------------------------------------------------------
# Workspace bookkeeping (SPEC-022 R-1): touch + set-once title
# ---------------------------------------------------------------------------


class TestRedisWorkspaceBookkeeping:
    def test_touch_updates_last_active_at(self, redis_store):
        record = redis_store.create_session("alice")
        before = record.last_active_at
        redis_store.touch_session(record.session_id)
        fetched = redis_store.get_session(record.session_id)
        assert fetched is not None
        assert fetched.last_active_at >= before

    def test_touch_missing_session_is_noop(self, redis_store):
        redis_store.touch_session("ses-nonexistent")  # no error

    def test_set_title_mints_and_get_overlays(self, redis_store):
        record = redis_store.create_session("alice")
        redis_store.set_session_title(record.session_id, "check the pods")
        fetched = redis_store.get_session(record.session_id)
        assert fetched is not None
        assert fetched.title == "check the pods"

    def test_title_overlay_flows_into_user_listing(self, redis_store):
        record = redis_store.create_session("alice")
        redis_store.set_session_title(record.session_id, "check the pods")
        listed = redis_store.list_sessions_by_user("alice")
        assert [s.title for s in listed] == ["check the pods"]

    def test_set_title_is_set_once(self, redis_store):
        # The NX-minted title key must never be overwritten.
        record = redis_store.create_session("alice")
        redis_store.set_session_title(record.session_id, "first turn")
        redis_store.set_session_title(record.session_id, "second turn")
        fetched = redis_store.get_session(record.session_id)
        assert fetched is not None
        assert fetched.title == "first turn"

    def test_touch_never_clobbers_a_minted_title(self, redis_store):
        # Regression for the read-modify-write clobber: the blob carries
        # no title, so a touch rewrite cannot erase the NX-minted one.
        record = redis_store.create_session("alice")
        redis_store.set_session_title(record.session_id, "first turn")
        redis_store.touch_session(record.session_id)
        redis_store.touch_session(record.session_id)
        fetched = redis_store.get_session(record.session_id)
        assert fetched is not None
        assert fetched.title == "first turn"

    def test_set_title_missing_session_is_noop(self, redis_client, redis_store):
        redis_store.set_session_title("ses-nonexistent", "orphan")
        assert redis_client.get("session:title:ses-nonexistent") is None

    def test_delete_removes_title_key(self, redis_client, redis_store):
        record = redis_store.create_session("alice")
        redis_store.set_session_title(record.session_id, "first turn")
        redis_store.delete_session(record.session_id)
        assert redis_client.get(f"session:title:{record.session_id}") is None

    def test_len_excludes_title_keys(self, redis_store):
        record = redis_store.create_session("alice")
        redis_store.set_session_title(record.session_id, "first turn")
        assert len(redis_store) == 1


# ---------------------------------------------------------------------------
# TTL behaviour
# ---------------------------------------------------------------------------


class TestRedisTTL:
    def test_session_expires_after_ttl(self, redis_client):
        store = RedisSessionStore(client=redis_client, ttl_seconds=1)
        record = store.create_session("alice")

        # Still alive immediately.
        assert store.get_session(record.session_id) is not None

        # Force-expire by manipulating the key TTL.
        key = f"session:{record.session_id}"
        redis_client.expire(key, 0)
        # Redis processes expiry lazily; wait briefly.
        time.sleep(0.05)
        assert store.get_session(record.session_id) is None


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestRedisHealth:
    def test_is_ready_with_live_client(self, redis_store):
        assert redis_store.is_ready() is True

    def test_backend_name(self, redis_store):
        assert redis_store.backend_name == "redis"


# ---------------------------------------------------------------------------
# InMemorySessionStore (regression)
# ---------------------------------------------------------------------------


class TestInMemoryStore:
    def test_backend_name(self):
        assert InMemorySessionStore().backend_name == "memory"

    def test_is_ready(self):
        assert InMemorySessionStore().is_ready() is True

    def test_list_sessions_by_user(self):
        store = InMemorySessionStore()
        store.create_session("alice")
        store.create_session("bob")
        assert len(store.list_sessions_by_user("alice")) == 1

    def test_delete_session(self):
        store = InMemorySessionStore()
        record = store.create_session("alice")
        assert store.delete_session(record.session_id) is True
        assert store.get_session(record.session_id) is None
        assert store.delete_session(record.session_id) is False


# ---------------------------------------------------------------------------
# Factory: build_session_store
# ---------------------------------------------------------------------------


class TestBuildSessionStore:
    def test_memory_backend(self, monkeypatch):
        monkeypatch.setenv("SESSION_STORE_BACKEND", "memory")
        store = build_session_store()
        assert isinstance(store, InMemorySessionStore)
        assert store.backend_name == "memory"

    def test_redis_backend_with_fakeredis(self, monkeypatch):
        """Redis backend works when Redis is reachable."""
        monkeypatch.setenv("SESSION_STORE_BACKEND", "redis")
        monkeypatch.setenv("SESSION_REDIS_HOST", "localhost")
        monkeypatch.setenv("SESSION_REDIS_PORT", "6379")
        monkeypatch.setenv("SESSION_REDIS_DB", "15")  # isolated test DB

        # Patch redis.Redis to return fakeredis so we don't need a live server.
        import redis as redis_module

        original_redis = redis_module.Redis

        def _fake_redis(**kwargs):
            return fakeredis.FakeRedis(decode_responses=False)

        monkeypatch.setattr(redis_module, "Redis", _fake_redis)
        try:
            store = build_session_store()
            assert isinstance(store, RedisSessionStore)
            assert store.backend_name == "redis"
        finally:
            monkeypatch.setattr(redis_module, "Redis", original_redis)

    def test_fallback_to_memory_on_unreachable_redis(self, monkeypatch):
        """Unreachable Redis triggers fallback to InMemorySessionStore."""
        monkeypatch.setenv("SESSION_STORE_BACKEND", "redis")
        monkeypatch.setenv("SESSION_REDIS_HOST", "192.0.2.1")  # TEST-NET, unreachable
        monkeypatch.setenv("SESSION_REDIS_PORT", "6379")
        monkeypatch.setenv("SESSION_REDIS_DB", "1")

        store = build_session_store()
        assert isinstance(store, InMemorySessionStore)
        assert store.backend_name == "memory"

    def test_ttl_propagated_to_redis(self, monkeypatch):
        monkeypatch.setenv("SESSION_STORE_BACKEND", "memory")
        monkeypatch.setenv("SESSION_TTL_SECONDS", "300")
        store = build_session_store()
        assert store.ttl_seconds == 300.0
