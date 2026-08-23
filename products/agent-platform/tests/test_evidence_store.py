"""Evidence store tests (SPEC-025 R-1).

Exercises the shared cap enforcement, InMemoryEvidenceStore,
PostgresEvidenceStore against a fake sync psycopg driver (SPEC-016/017
pattern), and the build_evidence_store factory's backend branches.
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import pytest
from prometheus_client import REGISTRY

from agent_service.services.evidence_store import (
    InMemoryEvidenceStore,
    PostgresEvidenceStore,
    build_evidence_store,
    prepare_frames,
)


def _truncated_count(reason: str) -> float:
    return (
        REGISTRY.get_sample_value(
            "evidence_frames_truncated_total", {"reason": reason}
        )
        or 0.0
    )


def _persisted_count() -> float:
    return REGISTRY.get_sample_value("evidence_frames_persisted_total") or 0.0


def _tool_call(call_id: str = "call-1") -> dict:
    return {
        "type": "tool_call",
        "tool_name": "k8s.list_pods",
        "call_id": call_id,
        "parameters": {"namespace": "ops"},
    }


def _tool_result(call_id: str = "call-1", data=None) -> dict:
    return {
        "type": "tool_result",
        "tool_name": "k8s.list_pods",
        "call_id": call_id,
        "status": "success",
        "data": data if data is not None else {"pods": []},
        "evidence": {"duration_ms": 42, "risk_level": "read"},
    }


def _fake_connect(calls: list[dict], rows=None, fail: bool = False):
    """Build a fake sync connect factory mirroring the SPEC-016 pattern."""

    class FakeCursor:
        def execute(self, sql, params=None):
            if fail:
                raise RuntimeError("connection refused")
            calls.append({"sql": sql, "params": params})

        def fetchone(self):
            return rows[0] if rows else None

        def fetchall(self):
            return rows or []

        @property
        def rowcount(self):
            return len(rows) if rows else 0

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

    @contextmanager
    def connect():
        yield FakeConn()

    return connect


# ---------------------------------------------------------------------------
# Shared entry-cap enforcement
# ---------------------------------------------------------------------------


class TestPrepareFrames:
    def test_within_cap_passes_through(self):
        frames = prepare_frames([_tool_call(), _tool_result()], 1000)
        assert frames[1]["data"] == {"pods": []}
        assert "truncated" not in frames[1]

    def test_oversized_data_truncated_with_marker(self):
        big = {"blob": "x" * 5000}
        before = _truncated_count("entry_cap")
        frames = prepare_frames([_tool_result(data=big)], 100)
        frame = frames[0]
        assert isinstance(frame["data"], str)
        assert len(frame["data"]) == 100
        assert frame["truncated"]["reason"] == "entry_cap"
        assert frame["truncated"]["original_chars"] > 100
        assert _truncated_count("entry_cap") == before + 1

    def test_boundary_value_not_truncated(self):
        payload = {"blob": "x"}
        exact = len(json.dumps(payload, default=str))
        frames = prepare_frames([_tool_result(data=payload)], exact)
        assert "truncated" not in frames[0]

    def test_none_data_and_tool_calls_untouched(self):
        result = _tool_result()
        result["data"] = None
        frames = prepare_frames([result, _tool_call()], 10)
        assert frames[0]["data"] is None
        assert "truncated" not in frames[0]


# ---------------------------------------------------------------------------
# InMemoryEvidenceStore
# ---------------------------------------------------------------------------


class TestInMemoryEvidenceStore:
    def test_save_load_round_trip_groups_by_turn(self):
        store = InMemoryEvidenceStore()
        store.save_turn("ses-1", "req-1", 0, [_tool_call(), _tool_result()], 1 << 30)
        store.save_turn("ses-1", "req-2", 1, [_tool_call("call-2")], 1 << 30)

        turns = store.load_turns("ses-1")
        assert [t["turn_index"] for t in turns] == [0, 1]
        assert turns[0]["request_id"] == "req-1"
        assert len(turns[0]["frames"]) == 2
        assert turns[0]["frames"][0]["type"] == "tool_call"
        assert turns[0]["created_at"]

    def test_frame_index_continues_across_park_and_resume(self):
        store = InMemoryEvidenceStore()
        store.save_turn("ses-1", "req-1", 0, [_tool_call()], 1 << 30)
        store.save_turn("ses-1", "req-2", 0, [_tool_result()], 1 << 30)

        turns = store.load_turns("ses-1")
        assert len(turns) == 1
        # One group, two frames, indices continued — never collided.
        assert len(turns[0]["frames"]) == 2

    def test_budget_evicts_oldest_result_payload_keeps_metadata(self):
        store = InMemoryEvidenceStore()
        big = {"blob": "y" * 900}
        store.save_turn(
            "ses-1", "req-1", 0, [_tool_call(), _tool_result(data=big)], 1 << 30
        )
        before = _truncated_count("session_budget")
        # A tiny budget forces eviction of the stored result payload.
        store.save_turn("ses-1", "req-2", 1, [_tool_result("call-2", {"blob": "z"})], 600)

        turns = store.load_turns("ses-1")
        evicted = turns[0]["frames"][1]
        assert evicted["data"] is None
        assert evicted["truncated"] == {"reason": "session_budget"}
        # Metadata survives eviction so card counts stay exact.
        assert evicted["evidence"]["duration_ms"] == 42
        assert _truncated_count("session_budget") > before

    def test_eviction_targets_oldest_turn_first(self):
        store = InMemoryEvidenceStore()
        store.save_turn("ses-1", "req-1", 0, [_tool_result("call-a", {"v": "a" * 200})], 1 << 30)
        store.save_turn("ses-1", "req-2", 1, [_tool_result("call-b", {"v": "b" * 200})], 1 << 30)
        store.save_turn("ses-1", "req-3", 2, [_tool_result("call-c", {"v": "c" * 200})], 1000)

        turns = store.load_turns("ses-1")
        assert turns[0]["frames"][0].get("truncated", {}).get("reason") == "session_budget"
        # Exactly one eviction: the middle turn keeps its payload too.
        assert "truncated" not in turns[1]["frames"][0]
        assert turns[2]["frames"][0]["data"] == {"v": "c" * 200}

    def test_empty_frames_noop(self):
        store = InMemoryEvidenceStore()
        store.save_turn("ses-1", "req-1", 0, [], 1 << 30)
        assert store.load_turns("ses-1") == []

    def test_delete_session_cascade(self):
        store = InMemoryEvidenceStore()
        store.save_turn("ses-1", "req-1", 0, [_tool_call()], 1 << 30)
        assert store.delete_session("ses-1") is True
        assert store.delete_session("ses-1") is False
        assert store.load_turns("ses-1") == []

    def test_frames_persisted_metric(self):
        store = InMemoryEvidenceStore()
        before = _persisted_count()
        store.save_turn("ses-1", "req-1", 0, [_tool_call(), _tool_result()], 1 << 30)
        assert _persisted_count() == before + 2


# ---------------------------------------------------------------------------
# Redaction regression (SPEC-009 choke point inherited by construction)
# ---------------------------------------------------------------------------


def test_redacted_frame_round_trips_byte_identical():
    """Credential-shaped values can never (re)enter a stored frame.

    Redaction runs upstream at the tool-gateway ``invoke_tool`` choke point
    (SPEC-009) before any frame reaches the agent; agent-platform cannot
    import the gateway to prove that here. This test pins the agent-side
    contract instead: a frame whose credential-shaped values are already
    replaced by the gateway's ``[REDACTED]`` marker must survive
    ``prepare_frames`` → ``save_turn`` → ``load_turns`` byte-identical, so
    the persistence path can neither strip markers nor reintroduce raw
    credentials.
    """
    # Shape of tool-gateway ``redact_result()`` output: sensitive keys keep
    # their names while values become the marker, and credential-shaped
    # spans inside free text are replaced by the marker.
    redacted = {
        "type": "tool_result",
        "tool_name": "db.query",
        "call_id": "call-red",
        "status": "success",
        "data": {
            "connection": {
                "host": "db.ops",
                "password": "[REDACTED]",
                "token": "[REDACTED]",
            },
            "log": "auth: Bearer [REDACTED] accepted; jwt=[REDACTED]",
        },
        "evidence": {"duration_ms": 12, "risk_level": "read"},
    }
    prepared = prepare_frames([redacted], 131_072)
    store = InMemoryEvidenceStore()
    store.save_turn("ses-red", "req-red", 0, prepared, 1 << 30)

    frames = store.load_turns("ses-red")[0]["frames"]
    stored = next(f for f in frames if f["type"] == "tool_result")
    # Byte-identical through JSON serialization — markers intact, nothing
    # stripped or rewritten, no truncation marker added at this size.
    assert json.loads(json.dumps(stored)) == redacted
    assert stored["data"]["connection"]["password"] == "[REDACTED]"
    assert "Bearer [REDACTED]" in stored["data"]["log"]
    assert "truncated" not in stored


# ---------------------------------------------------------------------------
# PostgresEvidenceStore SQL shape
# ---------------------------------------------------------------------------


class TestPostgresEvidenceStore:
    def _store(self, calls, rows=None, fail=False):
        return PostgresEvidenceStore(
            "postgresql://fake",
            ttl_seconds=600,
            connect=_fake_connect(calls, rows=rows, fail=fail),
        )

    def test_initialize_runs_ddl(self):
        calls: list[dict] = []
        self._store(calls).initialize()
        assert "CREATE TABLE IF NOT EXISTS session_evidence" in calls[0]["sql"]
        assert "idx_session_evidence_updated" in calls[0]["sql"]

    def test_save_turn_queries_index_inserts_and_sweeps(self):
        calls: list[dict] = []
        store = self._store(calls)
        store.save_turn("ses-1", "req-1", 0, [_tool_call()], 1 << 30)

        assert "COALESCE(MAX(frame_index)" in calls[0]["sql"]
        insert = calls[1]
        assert "INSERT INTO session_evidence" in insert["sql"]
        assert "ON CONFLICT (session_id, turn_index, frame_index)" in insert["sql"]
        assert insert["params"]["frame_index"] == 0
        assert json.loads(insert["params"]["frame"])["type"] == "tool_call"
        assert "DELETE FROM session_evidence" in calls[2]["sql"]
        assert calls[2]["params"]["ttl_seconds"] == 600
        # Budget lookup ran and saw an empty session.
        assert "SUM(payload_bytes)" in calls[3]["sql"]

    def test_evict_oldest_nulls_data_and_marks_budget(self):
        calls: list[dict] = []
        frame = _tool_result(data={"blob": "x" * 100})
        store = self._store(
            calls, rows=[("(1,1)", frame, len(json.dumps(frame)))]
        )
        freed = store._evict_oldest_result_payload("ses-1")
        assert freed > 0
        update = calls[-1]
        assert "UPDATE session_evidence" in update["sql"]
        evicted = json.loads(update["params"]["frame"])
        assert evicted["data"] is None
        assert evicted["truncated"] == {"reason": "session_budget"}

    def test_evict_returns_zero_when_nothing_evictable(self):
        calls: list[dict] = []
        assert self._store(calls)._evict_oldest_result_payload("ses-1") == 0

    def test_load_rows_refreshes_ttl_and_groups(self):
        calls: list[dict] = []
        rows = [
            (0, 0, "req-1", _tool_call(), "2026-08-23T10:00:00Z"),
            (0, 1, "req-1", _tool_result(), "2026-08-23T10:00:00Z"),
        ]
        store = self._store(calls, rows=rows)
        turns = store.load_turns("ses-1")
        sql = calls[0]["sql"]
        assert "UPDATE session_evidence" in sql
        assert "SET updated_at = now()" in sql
        assert len(turns) == 1
        assert [f["type"] for f in turns[0]["frames"]] == [
            "tool_call",
            "tool_result",
        ]

    def test_delete_session_reports_rowcount(self):
        calls: list[dict] = []
        assert self._store(calls, rows=[(1,)]).delete_session("ses-1") is True
        assert "DELETE FROM session_evidence" in calls[0]["sql"]

    def test_is_ready_false_when_connect_fails(self):
        calls: list[dict] = []
        assert self._store(calls, fail=True).is_ready() is False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestBuildEvidenceStore:
    def test_memory_backend_is_default(self, monkeypatch):
        monkeypatch.delenv("AGENT_STATE_STORE_BACKEND", raising=False)
        store = build_evidence_store()
        assert isinstance(store, InMemoryEvidenceStore)

    def test_postgres_backend_selected(self, monkeypatch):
        calls: list[dict] = []
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "postgres")
        monkeypatch.setenv("AGENT_STATE_DB_URL", "postgresql://fake/sessions")
        monkeypatch.setattr(
            PostgresEvidenceStore,
            "_default_connect",
            lambda self: _fake_connect(calls, rows=[(1,)])(),
        )
        store = build_evidence_store()
        assert isinstance(store, PostgresEvidenceStore)
        assert "CREATE TABLE IF NOT EXISTS session_evidence" in calls[0]["sql"]

    def test_postgres_without_dsn_fails_startup(self, monkeypatch):
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "postgres")
        monkeypatch.delenv("AGENT_STATE_DB_URL", raising=False)
        with pytest.raises(ValueError, match="AGENT_STATE_DB_URL"):
            build_evidence_store()

    def test_postgres_unreachable_falls_back_to_memory(self, monkeypatch):
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "postgres")
        monkeypatch.setenv("AGENT_STATE_DB_URL", "postgresql://fake/sessions")
        monkeypatch.setattr(
            PostgresEvidenceStore,
            "_default_connect",
            lambda self: _fake_connect([], fail=True)(),
        )
        store = build_evidence_store()
        assert isinstance(store, InMemoryEvidenceStore)

    def test_unknown_backend_fails_startup(self, monkeypatch):
        monkeypatch.setenv("AGENT_STATE_STORE_BACKEND", "redis")
        with pytest.raises(ValueError, match="Unknown AGENT_STATE_STORE_BACKEND"):
            build_evidence_store()
