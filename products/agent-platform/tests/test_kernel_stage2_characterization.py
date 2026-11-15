"""Stage-2 characterization gate for the AgentKernel decomposition.

These tests pin the *current* behavior of the two Stage-2 seams — model
resolution (``_build_model`` / ``_normalize_model_id`` / the router-attribution
trio / ``_router_armed``) and the agent build / cache / restore / snapshot
lifecycle (``_build_kernel_configs`` / ``_count_user_turns`` / ``_restore_state``
/ ``_snapshot_state`` / ``forget_session`` / ``ensure_agent``) — so they pass
identically *before* and *after* the collaborators move out of
``runtime_kernel.AgentKernel`` into ``services/kernel_models.ModelResolver`` and
``services/kernel_agents.AgentRegistry``.

They are deliberately written through the public ``AgentKernel`` surface and
patch only *move-safe* seams:

* singleton object methods (``MODEL_CATALOG.get``, ``AGENT_STATE_STORE.load_state``
  / ``save_state``) — the same object is referenced from whichever module hosts
  the code, so patching the instance survives the move;
* the kernel's own ``_provider`` attribute and ``_build_agent`` method — read
  live through the collaborator's kernel back-reference;
* never a module-level name that relocates (``runtime_kernel.MODEL_CATALOG``,
  ``runtime_kernel.get_provider``), which would silently stop reaching the moved
  code after extraction.

See docs/workspace/agent-kernel-decomposition-spike.md (Stage 2).
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from agent_service.runtime_kernel import AgentKernel, UnknownModelError
from agent_service.runtime_settings import (
    ModelRouterCandidateSpec,
    RuntimeSettings,
)
from agent_service.services.agent_state_store import AGENT_STATE_STORE
from agent_service.services.model_catalog import MODEL_CATALOG

# The stock ModelRouterMiddleware records its per-reply choice under its class
# name; ``_routed_candidate_name`` reads it back through the same literal key.
_ROUTER_KEY = "ModelRouterMiddleware"


def _configured(**overrides) -> AgentKernel:
    """A minimal configured kernel (router off) on the deepseek provider."""
    return AgentKernel(
        settings=RuntimeSettings(
            provider="deepseek", api_key="test-key", **overrides
        )
    )


def _router() -> AgentKernel:
    """A kernel with the router knob on, a classifier model, and a candidate map."""
    return AgentKernel(
        settings=RuntimeSettings(
            provider="deepseek",
            api_key="test-key",
            model_router_enabled=True,
            model_router_model="openai",
            model_router_candidates=(
                ModelRouterCandidateSpec(
                    name="fast", model_id="deepseek", description="quick"
                ),
                ModelRouterCandidateSpec(
                    name="deep", model_id="openai", description="complex"
                ),
            ),
        )
    )


class _FakeUserMsg:
    def __init__(self, name=None, content=None):
        self.name = name
        self.content = content


def _agent_with_router_record(reply_id, name):
    """An agent whose state carries a router attribution for ``reply_id``."""
    state = SimpleNamespace(
        middle_context={_ROUTER_KEY: {reply_id: name}}, reply_id=reply_id
    )
    return SimpleNamespace(state=state)


# ---------------------------------------------------------------------------
# ModelResolver seam — model selection + router attribution
# ---------------------------------------------------------------------------


def test_build_model_none_uses_active_provider_and_settings():
    # ``model_id=None`` keeps the deploy-time path: the kernel's own provider
    # builds against the live settings object (never a captured snapshot).
    kernel = _configured()
    seen: list = []
    kernel._provider = SimpleNamespace(
        build_model=lambda settings: seen.append(settings) or "MODEL"
    )
    assert kernel._build_model(None) == "MODEL"
    assert seen == [kernel.settings]


def test_build_model_unknown_id_raises_fail_closed():
    # An id absent from the credential-gated catalog fails closed (SPEC-024 R-1).
    kernel = _configured()
    with pytest.raises(UnknownModelError):
        kernel._build_model("definitely-not-a-real-catalog-id")


def test_normalize_model_id_falsy_is_active_provider():
    kernel = _configured()  # provider == "deepseek"
    assert kernel._normalize_model_id(None) == "deepseek"
    assert kernel._normalize_model_id("") == "deepseek"


def test_normalize_model_id_known_alias_and_unknown_passthrough(monkeypatch):
    # A known id resolves to its canonical catalog id; an unknown id passes
    # through verbatim (explicit-request paths reject it upstream). Patching the
    # singleton's ``get`` is move-safe: both the kernel and the collaborator
    # reference the same MODEL_CATALOG object.
    kernel = _configured()
    monkeypatch.setattr(
        MODEL_CATALOG,
        "get",
        lambda mid: SimpleNamespace(id=f"canonical::{mid}")
        if mid == "alias"
        else None,
    )
    assert kernel._normalize_model_id("alias") == "canonical::alias"
    assert kernel._normalize_model_id("unknown-id") == "unknown-id"


def test_routed_candidate_name_reads_router_middleware_record():
    kernel = _configured()
    # A string record for the current reply_id is returned verbatim.
    assert kernel._routed_candidate_name(_agent_with_router_record("r1", "fast")) == "fast"
    # No state / no middle_context / non-string / missing reply each yield None
    # (attribution never raises and never wedges a completed turn).
    assert kernel._routed_candidate_name(SimpleNamespace(state=None)) is None
    assert kernel._routed_candidate_name(object()) is None
    assert (
        kernel._routed_candidate_name(
            SimpleNamespace(
                state=SimpleNamespace(middle_context={}, reply_id="r1")
            )
        )
        is None
    )
    assert (
        kernel._routed_candidate_name(
            SimpleNamespace(
                state=SimpleNamespace(
                    middle_context={_ROUTER_KEY: {"r1": 123}}, reply_id="r1"
                )
            )
        )
        is None
    )


def test_candidate_model_id_maps_name_to_catalog_id():
    kernel = _router()  # fast -> deepseek, deep -> openai
    assert kernel._candidate_model_id("fast") == "deepseek"
    assert kernel._candidate_model_id("deep") == "openai"
    assert kernel._candidate_model_id("ghost") is None
    assert kernel._candidate_model_id(None) is None
    assert kernel._candidate_model_id("") is None


def test_effective_model_id_composes_routed_name_through_candidates():
    kernel = _router()
    assert kernel._effective_model_id(_agent_with_router_record("r1", "deep")) == "openai"
    # An idle agent (no router record) keeps its resolved tier: None.
    idle = SimpleNamespace(
        state=SimpleNamespace(middle_context={}, reply_id="r1")
    )
    assert kernel._effective_model_id(idle) is None


def test_router_armed_is_conjunction_of_turn_flag_and_deployment():
    armed = _router()
    assert armed._router_armed(routing_allowed=True) is True
    assert armed._router_armed(routing_allowed=False) is False
    inert = _configured()  # router knob off
    assert inert._router_armed(routing_allowed=True) is False
    assert inert._router_armed(routing_allowed=False) is False


# ---------------------------------------------------------------------------
# AgentRegistry seam — build / cache / restore / snapshot lifecycle
# ---------------------------------------------------------------------------


def test_build_kernel_configs_tracks_settings():
    kernel = _configured(
        max_iters=7,
        model_max_retries=4,
        context_trigger_ratio=0.5,
        tool_result_limit=123,
        compress_context_enabled=True,
        timezone="UTC",
    )
    cfg = kernel._build_kernel_configs()
    assert set(cfg) == {
        "model_config",
        "context_config",
        "react_config",
        "injection_config",
    }
    assert cfg["react_config"].max_iters == 7
    assert cfg["model_config"].max_retries == 4
    assert cfg["context_config"].trigger_ratio == 0.5
    assert cfg["context_config"].tool_result_limit == 123
    assert cfg["context_config"].compression_tool_enabled is True
    assert cfg["injection_config"].inject_runtime_state is True
    assert cfg["injection_config"].timezone == "UTC"


def test_count_user_turns_counts_only_user_role_messages():
    kernel = _configured()
    ctx = [
        SimpleNamespace(role="user"),
        SimpleNamespace(role="assistant"),
        SimpleNamespace(role="user"),
    ]
    assert (
        kernel._count_user_turns(
            SimpleNamespace(state=SimpleNamespace(context=ctx))
        )
        == 2
    )
    # No state / unreadable context degrades to 0 (defensive index fallback).
    assert kernel._count_user_turns(SimpleNamespace(state=None)) == 0
    assert kernel._count_user_turns(object()) == 0


def test_restore_state_returns_none_when_store_empty(monkeypatch):
    kernel = _configured()
    monkeypatch.setattr(AGENT_STATE_STORE, "load_state", lambda sid: None)
    assert kernel._restore_state("ses-x") is None


def test_restore_state_discards_corrupt_row(monkeypatch):
    # A poisoned snapshot is discarded (returns None) rather than wedging the
    # session; the corrupt row never reaches AgentState validation as truth.
    kernel = _configured()
    monkeypatch.setattr(
        AGENT_STATE_STORE, "load_state", lambda sid: "{not-valid-json"
    )
    assert kernel._restore_state("ses-x") is None


def test_snapshot_state_persists_serialized_projection(monkeypatch):
    kernel = _configured()
    saved: dict = {}
    monkeypatch.setattr(
        AGENT_STATE_STORE, "save_state", lambda sid, sj: saved.__setitem__(sid, sj)
    )
    agent = SimpleNamespace(
        state=SimpleNamespace(model_dump_json=lambda: '{"context": []}')
    )
    kernel._snapshot_state("ses-1", agent)
    assert "ses-1" in saved
    assert json.loads(saved["ses-1"]) == {"context": []}


def test_snapshot_state_never_raises_on_store_failure(monkeypatch):
    # A failed snapshot degrades durability, not the turn.
    kernel = _configured()

    def _boom(sid, sj):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(AGENT_STATE_STORE, "save_state", _boom)
    agent = SimpleNamespace(state=SimpleNamespace(model_dump_json=lambda: "{}"))
    kernel._snapshot_state("ses-1", agent)  # must not raise


def test_forget_session_drops_agent_family_and_literals():
    # forget_session drops the session, its ::read-only variant, and the whole
    # ::orch:: family from the agent cache, plus the matching literal knowledge,
    # while leaving unrelated sessions intact. Writing through ``kernel._agents``
    # must mutate the registry's live dict (read-through property).
    kernel = _configured()
    for key in (
        "ses-1",
        "ses-1::read-only",
        "ses-1::orch::t1",
        "ses-1::orch::t1::read-only",
        "other",
    ):
        kernel._agents[key] = (SimpleNamespace(), _FakeUserMsg, "deepseek")
    kernel._generated_literals["ses-1"] = {"x"}
    kernel._generated_literals["ses-1::orch::t1"] = {"y"}
    kernel._generated_literals["other"] = {"z"}

    kernel.forget_session("ses-1")

    for key in (
        "ses-1",
        "ses-1::read-only",
        "ses-1::orch::t1",
        "ses-1::orch::t1::read-only",
    ):
        assert key not in kernel._agents
    assert "other" in kernel._agents
    assert "ses-1" not in kernel._generated_literals
    assert "ses-1::orch::t1" not in kernel._generated_literals
    assert "other" in kernel._generated_literals


def test_ensure_agent_caches_by_session_and_separates_read_only(monkeypatch):
    # A repeat turn reuses the cached agent; a read_only turn rides a distinct
    # cache key so a restricted toolkit never leaks into an interactive turn.
    # Stubbing ``kernel._build_agent`` is move-safe: the registry's ensure_agent
    # calls it back through the kernel delegator.
    kernel = _configured()
    builds: list = []

    async def fake_build_agent(
        session_id,
        bearer_token=None,
        model_id=None,
        read_only=False,
        routing_allowed=False,
    ):
        builds.append((session_id, read_only))
        return (
            SimpleNamespace(toolkit=None, state=None),
            _FakeUserMsg,
            model_id or kernel.settings.provider,
        )

    monkeypatch.setattr(kernel, "_build_agent", fake_build_agent)

    a1, _, _ = asyncio.run(kernel.ensure_agent("ses-1"))
    a2, _, _ = asyncio.run(kernel.ensure_agent("ses-1"))
    ro, _, _ = asyncio.run(kernel.ensure_agent("ses-1", read_only=True))

    assert a1 is a2  # cache hit on the repeat
    assert ro is not a1  # ::read-only is a separate entry
    assert builds == [("ses-1", False), ("ses-1", True)]


def test_ensure_agent_lru_bound_evicts_oldest(monkeypatch):
    # The cache is LRU-bounded by max_cached_agents (which must flow into the
    # registry); building a second session at bound 1 evicts the first.
    kernel = AgentKernel(
        settings=RuntimeSettings(provider="deepseek", api_key="test-key"),
        max_cached_agents=1,
    )

    async def fake_build_agent(
        session_id,
        bearer_token=None,
        model_id=None,
        read_only=False,
        routing_allowed=False,
    ):
        return (
            SimpleNamespace(toolkit=None, state=None),
            _FakeUserMsg,
            model_id or kernel.settings.provider,
        )

    monkeypatch.setattr(kernel, "_build_agent", fake_build_agent)

    asyncio.run(kernel.ensure_agent("ses-A"))
    asyncio.run(kernel.ensure_agent("ses-B"))

    assert len(kernel._agents) == 1
    assert "ses-A" not in kernel._agents  # evicted (oldest)
    assert "ses-B" in kernel._agents
