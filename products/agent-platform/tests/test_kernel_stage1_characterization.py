"""Stage-0 characterization gate for the AgentKernel decomposition (Stage 1).

These tests pin the *current* observable behavior of the two Stage-1 seams —
the runtime-status projections (``KernelStatus``) and the toolkit
assembly/narrowing methods (``ToolkitAssembler``) — through the ``AgentKernel``
public/delegated API only. They are written to pass identically **before and
after** the collaborators are extracted behind thin delegators, so a green run
is the byte-identical-behavior proof the decomposition memo
(``docs/workspace/agent-kernel-decomposition-spike.md``) requires at Stage 0.

Everything asserted here is a surface the wider suite already touches only
indirectly (via ``runtime_metadata`` / ``configuration_hint`` / the role
narrowing tests); this file makes the individual projections and filters
explicit so a refactor cannot silently shift one.
"""

import asyncio

from agent_service.runtime_kernel import AgentKernel
from agent_service.runtime_settings import RuntimeSettings
from agent_service.services.agent_role import AgentRole

_READ_TOOL = {
    "name": "k8s.list_pods",
    "description": "x",
    "risk_level": "read",
    "parameters_schema": {"type": "object"},
}
_WRITE_TOOL = {
    "name": "k8s.delete_pod",
    "description": "x",
    "risk_level": "write",
    "parameters_schema": {"type": "object"},
}

# The exact key set ``runtime_metadata()`` emits (SPEC-072 surface). Pinned so
# an extraction can neither drop nor add a key.
_METADATA_KEYS = {
    "runtime_mode",
    "runtime_state",
    "agentscope_enabled",
    "profile",
    "provider",
    "provider_description",
    "model_name",
    "base_url",
    "provider_options",
    "hint",
    "last_error",
}


def _configured() -> AgentKernel:
    return AgentKernel(
        settings=RuntimeSettings(
            provider="deepseek",
            model_name="deepseek-v4-flash",
            api_key="test-key",
            base_url="https://api.deepseek.com",
        )
    )


def _unconfigured() -> AgentKernel:
    return AgentKernel(settings=RuntimeSettings(api_key=None))


# ---------------------------------------------------------------------------
# KernelStatus seam — runtime-status projections
# ---------------------------------------------------------------------------
def test_mode_reflects_configuration():
    assert _configured().mode() == "agentscope"
    assert _unconfigured().mode() == "placeholder"


def test_is_configured_tracks_api_key():
    assert _configured().is_configured() is True
    assert _unconfigured().is_configured() is False


def test_runtime_state_covers_all_three_branches():
    assert _unconfigured().runtime_state() == "not_configured"

    ready = _configured()
    assert ready.runtime_state() == "ready"

    errored = _configured()
    errored.remember_error(Exception("boom"))
    assert errored.runtime_state() == "provider_error"


def test_configuration_hint_not_configured_branch():
    assert _unconfigured().configuration_hint() == (
        "AgentScope runtime is not configured. "
        "Set AGENTSCOPE_API_KEY to enable the runtime kernel."
    )


def test_provider_name_and_description_accessors():
    kernel = _configured()
    assert kernel.provider_name() == "deepseek"
    assert kernel.provider_description() == (
        "deepseek provider using model deepseek-v4-flash "
        "at https://api.deepseek.com"
    )


def test_last_error_accessor_round_trip():
    kernel = _configured()
    assert kernel.last_error() is None

    kernel.remember_error(Exception("plain failure"))
    assert kernel.last_error() == "plain failure"

    kernel.clear_error()
    assert kernel.last_error() is None
    # Cleared error returns the runtime to the ready state.
    assert kernel.runtime_state() == "ready"


def test_remember_error_masks_a_turn_literal():
    kernel = _configured()
    kernel.remember_error(Exception("leaked abc123secret"), ("abc123secret",))
    # The provided literal is masked, never echoed verbatim into last_error.
    assert "abc123secret" not in (kernel.last_error() or "")


def test_runtime_metadata_key_set_and_values():
    metadata = _configured().runtime_metadata()
    assert set(metadata) == _METADATA_KEYS
    assert metadata["runtime_mode"] == "agentscope"
    assert metadata["runtime_state"] == "ready"
    assert metadata["agentscope_enabled"] is True
    assert metadata["provider"] == "deepseek"
    assert metadata["provider_description"] == (
        "deepseek provider using model deepseek-v4-flash "
        "at https://api.deepseek.com"
    )
    assert metadata["model_name"] == "deepseek-v4-flash"
    assert metadata["base_url"] == "https://api.deepseek.com"
    assert metadata["provider_options"] == {
        "max_tokens": None,
        "temperature": None,
        "top_p": None,
        "thinking_enable": False,
        "reasoning_effort": None,
    }
    assert metadata["last_error"] is None
    assert metadata["hint"] == (
        "AgentScope runtime ready through deepseek provider using model "
        "deepseek-v4-flash at https://api.deepseek.com."
    )


# ---------------------------------------------------------------------------
# ToolkitAssembler seam — assembly + narrowing filters
# ---------------------------------------------------------------------------
def test_build_task_tools_returns_four_agentscope_tools():
    tools = _configured()._build_task_tools()
    assert len(tools) == 4
    assert {type(tool).__name__ for tool in tools} == {
        "TaskCreate",
        "TaskGet",
        "TaskList",
        "TaskUpdate",
    }


def test_filter_read_only_keeps_only_read_tools():
    kept = _configured()._filter_read_only([_READ_TOOL, _WRITE_TOOL])
    assert {d["name"] for d in kept} == {"k8s.list_pods"}


def test_filter_mutating_keeps_all_when_hitl_enabled():
    kernel = AgentKernel(
        settings=RuntimeSettings(api_key="test-key", hitl_confirm_timeout=600)
    )
    kept = kernel._filter_mutating_for_hitl([_READ_TOOL, _WRITE_TOOL])
    assert {d["name"] for d in kept} == {"k8s.list_pods", "k8s.delete_pod"}
    assert kernel._mutating_tools_excluded is False


def test_filter_mutating_drops_writes_when_hitl_disabled():
    kernel = AgentKernel(
        settings=RuntimeSettings(api_key="test-key", hitl_confirm_timeout=0)
    )
    kept = kernel._filter_mutating_for_hitl([_READ_TOOL, _WRITE_TOOL])
    assert {d["name"] for d in kept} == {"k8s.list_pods"}
    # The sticky posture flag flips once a mutating tool is excluded.
    assert kernel._mutating_tools_excluded is True


def test_narrow_for_role_matches_filter_read_only_for_diagnostician():
    kernel = _configured()
    narrowed = kernel._narrow_for_role(
        [_READ_TOOL, _WRITE_TOOL], AgentRole.DIAGNOSTICIAN
    )
    assert {d["name"] for d in narrowed} == {"k8s.list_pods"}


def test_ensure_toolkit_without_gateway_returns_task_tools_uncached(monkeypatch):
    # No tool_gateway_url configured: the toolkit is task-tools-only and is
    # NOT cached, so a later turn retries discovery (SPEC-018 R-2 posture).
    kernel = AgentKernel(
        settings=RuntimeSettings(api_key="test-key", task_tools_enabled=True)
    )
    first = asyncio.run(kernel._ensure_toolkit("token-a"))
    second = asyncio.run(kernel._ensure_toolkit("token-a"))
    assert first is not second
    assert kernel._count_gateway_tools(first) == 0
