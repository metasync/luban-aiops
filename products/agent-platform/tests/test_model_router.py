"""SPEC-071 R-2: opt-in per-turn model routing (AgentScope ``ModelRouterMiddleware``).

Covers the seven R-2 acceptance-test criteria (spec.md:150-154):

* **opt-in gating** — off ⇒ middleware absent and the composed stack is
  independent of the per-turn flag (byte-identical to v0.51.1); on + map ⇒
  present; on + no map ⇒ inert; an explicit turn ⇒ suppressed; an unknown
  candidate id ⇒ fail-closed at build.
* **precedence** — an explicit request model and a live pin both suppress
  routing; only a default-resolved turn arms it (``request > pinned > routed >
  default``), including the Path-A pin lifecycle.
* **fail-soft** — a classifier error and an unknown candidate each keep the
  agent's own model and never hard-fail the turn (drives the real middleware).
* **resume** — a routed ``reply_id`` reuses its stored choice without
  re-routing, and the router-armed agent rides a distinct cache key so a
  park/resume reuses it.
* **attribution** — ``_effective_model_id`` maps the routed candidate back to
  its catalog id (``None`` when routing did not fire); the response ``model``
  and the ``message_end`` frame carry the effective id; the two-value reply
  unpack contract is preserved.
* **contract boundary** — no agentscope type leaks; ``agent-stream-event.
  schema.json`` stays byte-unchanged and the routed id rides its existing
  ``model`` field.
* **token observation** — the Stage-0 refined disposition, asserted not
  instrumented: the routed model's reply tokens ride SPEC-065 while the
  classification call bypasses the ``on_model_call`` observation point.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import jsonschema
import pytest
from fastapi.testclient import TestClient

from agent_service import runtime_kernel
from agent_service.api.v2 import routes as v2_routes
from agent_service.app import create_app
from agent_service.runtime_kernel import AgentKernel, BlockingReply, UnknownModelError
from agent_service.runtime_settings import ModelRouterCandidateSpec, RuntimeSettings
from agent_service.services.kernel_middleware import TokenUsageMiddleware
from agent_service.services.runtime_dependencies import get_runtime_kernel

from agentscope.event import ReplyStartEvent
from agentscope.message import UserMsg
from agentscope.middleware import ChatModelCandidate, ModelRouterMiddleware

from test_contract_adapter import load_schema
from test_model_switching import (
    FakeCatalog,
    FakeEndAgent,
    FakeUserMsg,
    _configured_kernel,
    _drain,
)

# The stock middleware records its choice under its class name (Stage-0 S0-4);
# the kernel reads it back through the same key.
_ROUTER_KEY = "ModelRouterMiddleware"

_ROUTER_CANDIDATES = (
    ModelRouterCandidateSpec(
        name="fast", model_id="deepseek", description="quick, simple tasks"
    ),
    ModelRouterCandidateSpec(
        name="deep", model_id="openai", description="complex, multi-step reasoning"
    ),
)


def _router_kernel(**overrides) -> AgentKernel:
    """A kernel with the router knob on, a classifier model, and a candidate map."""
    return AgentKernel(
        settings=RuntimeSettings(
            api_key="test-key",
            model_router_enabled=True,
            model_router_model="openai",
            model_router_candidates=_ROUTER_CANDIDATES,
            **overrides,
        )
    )


def _stub_build_model(kernel, monkeypatch, built=None):
    """Replace real provider construction with a sentinel; optionally record ids."""

    def _fake(model_id=None):
        if built is not None:
            built.append(model_id)
        return SimpleNamespace(model_id=model_id)

    monkeypatch.setattr(kernel, "_build_model", _fake)


def _routers(kernel, routing_allowed) -> list:
    return [
        m
        for m in kernel._build_middlewares(routing_allowed)
        if isinstance(m, ModelRouterMiddleware)
    ]


# ---------------------------------------------------------------------------
# 1. Opt-in gating
# ---------------------------------------------------------------------------


class TestOptInGating:
    def test_absent_when_disabled_even_on_a_default_turn(self, monkeypatch):
        kernel = _configured_kernel()  # model_router_enabled defaults False
        _stub_build_model(kernel, monkeypatch)
        assert _routers(kernel, routing_allowed=True) == []

    def test_present_when_enabled_with_map_on_a_default_turn(self, monkeypatch):
        kernel = _router_kernel()
        built: list = []
        _stub_build_model(kernel, monkeypatch, built)

        routers = _routers(kernel, routing_allowed=True)

        assert len(routers) == 1
        # The classifier rides the configured router model and every candidate
        # is built from a credential-gated catalog id (never a new provider).
        assert "openai" in built and "deepseek" in built
        assert set(routers[0]._models) == {"fast", "deep"}

    def test_inert_when_enabled_without_a_map(self, monkeypatch):
        # enabled + no candidate map ⇒ inert, not an error (settings guard).
        kernel = AgentKernel(
            settings=RuntimeSettings(api_key="test-key", model_router_enabled=True)
        )
        _stub_build_model(kernel, monkeypatch)
        assert _routers(kernel, routing_allowed=True) == []

    def test_suppressed_on_an_explicit_turn(self, monkeypatch):
        # Precedence at the middleware seam: routing_allowed False ⇒ absent.
        kernel = _router_kernel()
        _stub_build_model(kernel, monkeypatch)
        assert _routers(kernel, routing_allowed=False) == []

    def test_disabled_stack_is_independent_of_the_flag(self, monkeypatch):
        # "byte-identical to v0.51.1 when off": with the knob off the composed
        # stack does not depend on ``routing_allowed`` and holds no router.
        kernel = _configured_kernel()
        _stub_build_model(kernel, monkeypatch)
        armed = [type(m).__name__ for m in kernel._build_middlewares(True)]
        disarmed = [type(m).__name__ for m in kernel._build_middlewares(False)]
        assert armed == disarmed
        assert "ModelRouterMiddleware" not in armed

    def test_unknown_candidate_id_fails_closed_at_build(self, monkeypatch):
        # A revoked catalog id in the map raises at build: a router is never
        # armed against a model the credential-gated catalog does not have.
        kernel = _router_kernel()

        def _fake(model_id=None):
            if model_id == "deepseek":
                raise UnknownModelError("deepseek")
            return SimpleNamespace(model_id=model_id)

        monkeypatch.setattr(kernel, "_build_model", _fake)
        with pytest.raises(UnknownModelError):
            kernel._build_middlewares(routing_allowed=True)


# ---------------------------------------------------------------------------
# 2. Precedence: request > pinned > routed > default
# ---------------------------------------------------------------------------


class TestPrecedence:
    @staticmethod
    def _arms_routing(requested, pinned) -> bool:
        _model_id, selected_by = v2_routes._resolve_model(requested, pinned)
        return selected_by == "default"

    def test_only_a_default_resolved_turn_arms_routing(self, monkeypatch):
        monkeypatch.setattr(
            v2_routes,
            "MODEL_CATALOG",
            FakeCatalog(ids=("deepseek", "openai"), default="openai"),
        )
        assert self._arms_routing("deepseek", "openai") is False  # explicit request
        assert self._arms_routing(None, "deepseek") is False  # live pin
        assert self._arms_routing(None, None) is True  # default-resolved

    def test_a_revoked_pin_degrades_to_default_and_re_arms(self, monkeypatch):
        # A pin whose key was revoked drops out of the catalog and degrades to
        # the default, so provenance reports ``default`` and routing re-arms.
        monkeypatch.setattr(
            v2_routes, "MODEL_CATALOG", FakeCatalog(ids=("openai",), default="openai")
        )
        assert self._arms_routing(None, "deepseek") is True

    def test_chat_threads_routing_allowed_and_path_a_pin(self, monkeypatch):
        # End-to-end: routes computes ``routing_allowed`` from provenance and
        # pins only an explicit request (Path A), so a later model-less turn on
        # the now-pinned session stays suppressed.
        monkeypatch.setattr(
            v2_routes,
            "MODEL_CATALOG",
            FakeCatalog(ids=("deepseek", "openai"), default="openai"),
        )
        kernel = get_runtime_kernel()
        seen: list = []

        async def fake_reply_text(**kwargs):
            seen.append(kwargs.get("routing_allowed"))
            return BlockingReply("ok")

        monkeypatch.setattr(kernel, "reply_text", fake_reply_text)
        client = TestClient(create_app())
        sid = client.post(
            "/api/v2/sessions", headers={"X-User-ID": "alice"}
        ).json()["session_id"]

        client.post(
            "/api/v2/chat",
            json={"message": "hi", "session_id": sid},
            headers={"X-User-ID": "alice"},
        )  # 1) default-resolved ⇒ armed
        client.post(
            "/api/v2/chat",
            json={"message": "hi", "session_id": sid, "model": "deepseek"},
            headers={"X-User-ID": "alice"},
        )  # 2) explicit request ⇒ suppressed and pins the session
        client.post(
            "/api/v2/chat",
            json={"message": "hi", "session_id": sid},
            headers={"X-User-ID": "alice"},
        )  # 3) now pinned ⇒ suppressed

        assert seen == [True, False, False]


# ---------------------------------------------------------------------------
# 3-4. Fail-soft + resume, driving the real ModelRouterMiddleware
# ---------------------------------------------------------------------------

_ORIG_MODEL = object()  # the agent's own model
_ROUTED_MODEL = object()  # the "fast" candidate's model


class _FakeClassifier:
    """A plain ``ChatModelBase``-style classifier: only ``generate_structured_output``
    is used (``_route`` falls to it when the model is not a ``ClassifierModelBase``)."""

    def __init__(self, choice):
        self._choice = choice
        self.calls = 0

    async def generate_structured_output(self, messages, structured_model):
        self.calls += 1
        if isinstance(self._choice, Exception):
            raise self._choice
        return SimpleNamespace(content={"choice": self._choice})


def _mk_router(choice):
    classifier = _FakeClassifier(choice)
    middleware = ModelRouterMiddleware(
        classifier_model=classifier,
        candidates=[
            ChatModelCandidate(
                name="fast", model=_ROUTED_MODEL, description="quick tasks"
            )
        ],
    )
    return classifier, middleware


def _fake_agent(reply_id=None, middle_context=None):
    return SimpleNamespace(
        model=_ORIG_MODEL,
        state=SimpleNamespace(
            middle_context={} if middle_context is None else middle_context,
            reply_id=reply_id,
        ),
    )


def _drive(middleware, agent, inputs, *, emit_reply_start=True, reply_id="r1"):
    """Run ``on_reply`` and record the model at the inner model-call point.

    ``next_handler`` models agentscope's ``_call_model``: it yields the
    ``ReplyStartEvent`` (where the router swaps ``agent.model``) and then reads
    ``agent.model`` — the serving model the token observer would attribute.
    """
    observed: list = []

    async def next_handler(**kwargs):
        if emit_reply_start:
            yield ReplyStartEvent(reply_id=reply_id, session_id="s1", name="assistant")
        observed.append(agent.model)

    async def run():
        async for _ in middleware.on_reply(agent, {"inputs": inputs}, next_handler):
            pass
        return observed

    return asyncio.run(run())


class TestFailSoft:
    def test_routes_to_the_selected_candidate(self):
        classifier, middleware = _mk_router("fast")
        agent = _fake_agent()
        observed = _drive(middleware, agent, UserMsg(name="user", content="quick"))
        assert observed == [_ROUTED_MODEL]  # the reply ran on the routed model
        assert agent.model is _ORIG_MODEL  # restored once the reply completes
        assert agent.state.middle_context[_ROUTER_KEY] == {"r1": "fast"}
        assert classifier.calls == 1

    def test_classifier_error_keeps_the_agents_model(self):
        classifier, middleware = _mk_router(RuntimeError("classifier down"))
        agent = _fake_agent()
        # Must not raise: a routing error never hard-fails the turn.
        observed = _drive(middleware, agent, UserMsg(name="user", content="quick"))
        assert observed == [_ORIG_MODEL]
        assert agent.state.middle_context[_ROUTER_KEY] == {"r1": None}
        assert classifier.calls == 1

    def test_unknown_candidate_keeps_the_agents_model(self):
        _classifier, middleware = _mk_router("ghost")
        agent = _fake_agent()
        observed = _drive(middleware, agent, UserMsg(name="user", content="quick"))
        assert observed == [_ORIG_MODEL]
        assert agent.state.middle_context[_ROUTER_KEY] == {"r1": None}


class TestResumeSafety:
    def test_a_routed_reply_id_reuses_its_choice_without_re_routing(self):
        classifier, middleware = _mk_router("fast")
        # A parked reply already recorded its choice under its reply_id.
        agent = _fake_agent(
            reply_id="r1", middle_context={_ROUTER_KEY: {"r1": "fast"}}
        )
        # Resume: ``inputs`` is not a fresh Msg/list and the reply does not
        # restart, so no new ReplyStartEvent and no re-route.
        observed = _drive(
            middleware, agent, object(), emit_reply_start=False, reply_id="r1"
        )
        assert observed == [_ROUTED_MODEL]  # the same model serves post-resume
        assert classifier.calls == 0  # the classifier was not re-invoked
        assert agent.model is _ORIG_MODEL  # restored

    def test_routed_agent_uses_a_distinct_cache_key(self, monkeypatch):
        # A resume with the same routing posture reuses the router-armed agent
        # (so the router replays its stored choice); a routed agent is never
        # reused for a disarmed turn, nor vice versa. The router must be armed
        # (knob on + candidate map) for the cache to split.
        kernel = _router_kernel()
        builds: list = []

        async def fake_build_agent(
            session_id,
            bearer_token=None,
            model_id=None,
            read_only=False,
            routing_allowed=False,
        ):
            builds.append(routing_allowed)
            return (FakeEndAgent(), FakeUserMsg, model_id or kernel.settings.provider)

        monkeypatch.setattr(kernel, "_build_agent", fake_build_agent)

        disarmed, _, _ = asyncio.run(kernel.ensure_agent("ses-r", model_id="openai"))
        armed, _, _ = asyncio.run(
            kernel.ensure_agent("ses-r", model_id="openai", routing_allowed=True)
        )
        resumed, _, _ = asyncio.run(
            kernel.ensure_agent("ses-r", model_id="openai", routing_allowed=True)
        )

        assert disarmed is not armed  # the ::routed suffix separates the cache
        assert armed is resumed  # the resumed turn reuses the armed agent
        assert builds == [False, True]  # only two builds; the resume reused

    def test_no_cache_split_when_the_router_is_inert(self, monkeypatch):
        # The ``::routed`` suffix is gated on the same ``_router_armed``
        # predicate that registers the middleware, so an inert (default-off)
        # router never wastes a cache slot: a default-resolved turn and an
        # explicit turn on the same model share one agent.
        kernel = _configured_kernel()  # router disabled
        builds: list = []

        async def fake_build_agent(
            session_id,
            bearer_token=None,
            model_id=None,
            read_only=False,
            routing_allowed=False,
        ):
            builds.append(routing_allowed)
            return (FakeEndAgent(), FakeUserMsg, model_id or kernel.settings.provider)

        monkeypatch.setattr(kernel, "_build_agent", fake_build_agent)

        first, _, _ = asyncio.run(kernel.ensure_agent("ses-d", model_id="openai"))
        second, _, _ = asyncio.run(
            kernel.ensure_agent("ses-d", model_id="openai", routing_allowed=True)
        )

        assert first is second  # no split while the router is inert
        assert builds == [False]  # a single build


# ---------------------------------------------------------------------------
# 5. Attribution: the effective model + model_selected_by
# ---------------------------------------------------------------------------


class _RoutedState:
    def __init__(self, name, reply_id):
        self.middle_context = {_ROUTER_KEY: {reply_id: name}}
        self.reply_id = reply_id

    def model_dump_json(self):
        return "{}"


class _RoutedEndAgent:
    """Yields one message_end; its state records the routed candidate."""

    def __init__(self, name, reply_id):
        self.toolkit = None
        self.state = _RoutedState(name, reply_id)

    async def reply_stream(self, inputs):
        yield SimpleNamespace(type="message_end", message="complete")


def _agent_routed_to(name, reply_id="r1"):
    return SimpleNamespace(
        state=SimpleNamespace(
            middle_context={_ROUTER_KEY: {reply_id: name}}, reply_id=reply_id
        )
    )


class TestAttribution:
    def test_effective_model_maps_the_routed_candidate(self):
        kernel = _router_kernel()
        assert kernel._effective_model_id(_agent_routed_to("fast")) == "deepseek"
        assert kernel._effective_model_id(_agent_routed_to("deep")) == "openai"

    def test_effective_model_none_when_routing_did_not_fire(self):
        kernel = _router_kernel()
        idle = SimpleNamespace(
            state=SimpleNamespace(middle_context={}, reply_id="r1")
        )
        assert kernel._effective_model_id(idle) is None

    def test_effective_model_none_on_a_fail_soft_record(self):
        kernel = _router_kernel()
        # ``_route`` stores None on error/unknown; attribution must fall back to
        # the resolved tier rather than invent a model.
        assert kernel._effective_model_id(_agent_routed_to(None)) is None
        assert kernel._effective_model_id(_agent_routed_to("ghost")) is None

    def test_attribution_never_raises_on_malformed_state(self):
        kernel = _router_kernel()
        assert kernel._effective_model_id(object()) is None
        assert kernel._effective_model_id(SimpleNamespace(state=None)) is None

    def test_blocking_reply_keeps_the_two_value_unpack_contract(self):
        reply = BlockingReply("content", {"s": 1}, None, "deepseek")
        content, structured = reply  # exactly two values, as before SPEC-071
        assert (content, structured) == ("content", {"s": 1})
        assert reply.effective_model == "deepseek"  # additive, never unpacked

    def test_chat_response_reports_the_effective_routed_model(self, monkeypatch):
        monkeypatch.setattr(
            v2_routes,
            "MODEL_CATALOG",
            FakeCatalog(ids=("deepseek", "openai"), default="openai"),
        )
        kernel = get_runtime_kernel()

        async def fake_reply_text(**kwargs):
            # The router served deepseek even though the turn resolved default.
            return BlockingReply("ok", None, None, "deepseek")

        monkeypatch.setattr(kernel, "reply_text", fake_reply_text)
        client = TestClient(create_app())
        sid = client.post(
            "/api/v2/sessions", headers={"X-User-ID": "alice"}
        ).json()["session_id"]

        resp = client.post(
            "/api/v2/chat",
            json={"message": "hi", "session_id": sid},
            headers={"X-User-ID": "alice"},
        )
        assert resp.status_code == 200
        assert resp.json()["model"] == "deepseek"  # effective, not the default openai

    def test_chat_response_falls_back_to_the_resolved_model(self, monkeypatch):
        monkeypatch.setattr(
            v2_routes,
            "MODEL_CATALOG",
            FakeCatalog(ids=("deepseek", "openai"), default="openai"),
        )
        kernel = get_runtime_kernel()

        async def fake_reply_text(**kwargs):
            return BlockingReply("ok")  # effective_model None ⇒ routing did not fire

        monkeypatch.setattr(kernel, "reply_text", fake_reply_text)
        client = TestClient(create_app())
        sid = client.post(
            "/api/v2/sessions", headers={"X-User-ID": "alice"}
        ).json()["session_id"]

        resp = client.post(
            "/api/v2/chat",
            json={"message": "hi", "session_id": sid},
            headers={"X-User-ID": "alice"},
        )
        assert resp.json()["model"] == "openai"  # the resolved default

    def test_stream_message_end_carries_the_routed_model(self, monkeypatch):
        kernel = _router_kernel()
        monkeypatch.setattr(
            runtime_kernel,
            "MODEL_CATALOG",
            FakeCatalog(ids=("deepseek", "openai"), default="openai"),
        )
        agent = _RoutedEndAgent("fast", "reply-x")

        async def fake_build_agent(
            session_id,
            bearer_token=None,
            model_id=None,
            read_only=False,
            routing_allowed=False,
        ):
            return (agent, FakeUserMsg, model_id or kernel.settings.provider)

        monkeypatch.setattr(kernel, "_build_agent", fake_build_agent)
        monkeypatch.setattr(
            kernel, "_snapshot_state", lambda session_id, agent, turn_literals=(): None
        )
        monkeypatch.setattr(kernel, "_persist_evidence", lambda *args: None)

        frames = _drain(
            kernel.stream_events(
                message="hi",
                request_id="req-1",
                session_id="ses-1",
                user_name="alice",
                model_id="openai",
                routing_allowed=True,
            )
        )
        end = [f for f in frames if f.get("event") == "message_end"]
        assert len(end) == 1
        assert end[0]["model"] == "deepseek"  # routed, not the resolved openai


# ---------------------------------------------------------------------------
# 6. Contract boundary: no type leak + schema byte-stability
# ---------------------------------------------------------------------------


class TestContractBoundary:
    def test_schema_is_unchanged_and_carries_the_model_field(self):
        # SPEC-071 adds no schema version and no routing event type; the routed
        # id rides the existing SPEC-024 ``model`` field. (test_contract_adapter
        # holds the full v13 byte-stability guard; this pins the SPEC-071 view.)
        schema = load_schema("agent-stream-event.schema.json")
        assert schema["title"] == "Agent Stream Event (v13)"
        assert "model" in schema["properties"]
        assert not any("rout" in t for t in schema["properties"]["type"]["enum"])

    def test_a_routed_message_end_frame_still_validates(self):
        schema = load_schema("agent-stream-event.schema.json")
        frame = v2_routes._normalize_stream_event(
            {"type": "message_end", "model": "deepseek"}, "ses-1", "req-1"
        ).model_dump(mode="json", exclude_none=True)
        assert frame["model"] == "deepseek"
        jsonschema.validate(frame, schema)  # the byte-unchanged schema accepts it


# ---------------------------------------------------------------------------
# 7. Token observation — the Stage-0 refined disposition (asserted, not instrumented)
# ---------------------------------------------------------------------------


class TestTokenObservationDisposition:
    def test_router_and_token_usage_never_share_a_hook_chain(self):
        # Stage-0 S0-1: the router is ``on_reply``-only and TokenUsage is
        # ``on_model_call``-only, so they never compete on wrap order and the
        # on_reply swap is active for the inner ``_call_model`` TokenUsage sees.
        assert "on_reply" in ModelRouterMiddleware.__dict__
        assert "on_model_call" not in ModelRouterMiddleware.__dict__
        assert "on_model_call" in TokenUsageMiddleware.__dict__
        assert "on_reply" not in TokenUsageMiddleware.__dict__

    def test_the_classification_call_bypasses_the_model_call_point(self):
        # Stage-0 S0-2: the routed model's reply tokens ride SPEC-065 (the inner
        # model call runs against the swapped model), while the classifier's
        # direct ``generate_structured_output`` never reaches the on_model_call
        # observation point — unobserved by design while default-off.
        classifier, middleware = _mk_router("fast")
        agent = _fake_agent()
        observed = _drive(middleware, agent, UserMsg(name="user", content="quick"))

        assert classifier.calls == 1  # the classification call happened
        assert observed == [_ROUTED_MODEL]  # only the routed reply model was observed
        assert classifier not in observed  # the classifier never rode the model call
