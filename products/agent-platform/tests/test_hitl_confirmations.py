"""SPEC-020 R-2: HITL confirmation bridging — registry, kernel, routes."""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

import pytest
from agentscope.event import (
    RequireUserConfirmEvent,
    UserConfirmResultEvent,
    UserInterruptEvent,
)
from agentscope.message import ToolCallBlock
from fastapi.testclient import TestClient

from agent_service.api.v2 import routes as v2_routes
from agent_service.app import create_app
from agent_service.runtime_kernel import AgentKernel
from agent_service.runtime_settings import RuntimeSettings
from agent_service.services import session_service
from agent_service.services.authoring_trace import AUTHORING_TRACE_STORE
from agent_service.services.confirmation_records import (
    CONFIRMATION_RECORD_STORE,
    make_record,
)
from agent_service.services.execution_records import EXECUTION_RECORD_STORE
from agent_service.services.execution_signing import (
    canonical_digest,
    verify_envelope,
)
from agent_service.services.hitl_confirmations import (
    CONFIRMATION_REGISTRY,
    ConfirmationExpired,
    ConfirmationNotFound,
    ConfirmationRegistry,
    build_change_request,
    curated_effect_sentence,
    redact_pending_calls,
)
from agent_service.services.kernel_middleware import TOOL_EVIDENCE_SINK
from agent_service.services.runtime_dependencies import get_runtime_kernel
from agent_service.services.secret_params import TRACE_CREDENTIAL_PLACEHOLDER
from agent_service.tools.gateway_tools import (
    EXECUTION_REJECTION,
    EXECUTION_REQUESTS,
)

TOOL_CALL = ToolCallBlock(
    id="call-1", name="k8s.restart_service", input='{"namespace": "ops"}'
)

# Parked tool calls carry the model-visible sanitized name (dots become
# underscores); the gateway canonical name must be restored in payloads.
SANITIZED_TOOL_CALL = ToolCallBlock(
    id="call-2", name="k8s_delete_pod", input='{"name": "web-1"}'
)

# SPEC-055 R-7: an uncurated action call whose input carries a literal secret.
# ``password`` is a vocabulary name; ``name`` is its off-allow-list sibling (only
# the curated ``k8s.delete_pod`` name/namespace are KNOWN_SAFE_FIELDS). The
# plaintext value is the fixture's whole point — every R-7 absence assertion
# below parks it first, so "never leaked" is not vacuous (the SPEC-045 lesson: an
# absence assertion proves nothing unless the fixture proves the secret was
# present to begin with).
SECRET_TOOL_CALL = ToolCallBlock(
    id="call-secret",
    name="k8s.rotate_secret",
    input='{"name": "db", "password": "s3cret-PASSWORD-xyz"}',
)

# SPEC-055 R-2: a credential entering a flow as a *reference* to a named
# credential set rather than as a literal — the structural fix this stage
# exists to protect. Here it stands in for a read-tier parked call, pinning
# the capture gate's exclusion of one; the projection-level guarantee that
# this reference survives ``parameterize_for_trace`` verbatim (which is what
# makes ``is_known_safe``'s precedence over the name vocabulary load-bearing,
# since ``is_secret_param`` matches "credential" as a substring) is pinned
# against the projection itself in test_secret_params.py.
CREDENTIAL_TOOL_CALL = ToolCallBlock(
    id="call-cred",
    name="web.fill_credential",
    input='{"credential_set": "admin-portal", "field": "password"}',
)


def _park_event() -> RequireUserConfirmEvent:
    return RequireUserConfirmEvent(reply_id="reply-1", tool_calls=[TOOL_CALL])


def _secret_park_event() -> RequireUserConfirmEvent:
    return RequireUserConfirmEvent(
        reply_id="reply-1", tool_calls=[SECRET_TOOL_CALL]
    )


@pytest.fixture(autouse=True)
def _clean_registry():
    CONFIRMATION_REGISTRY._by_session.clear()
    records = getattr(CONFIRMATION_RECORD_STORE, "_by_confirm_id", None)
    if records is not None:
        records.clear()
    executions = getattr(EXECUTION_RECORD_STORE, "_by_key", None)
    if executions is not None:
        executions.clear()
    # SPEC-055 R-2: the approval seam also appends to the authoring trace, so
    # the same isolation applies to it.
    traces = getattr(AUTHORING_TRACE_STORE, "_by_session", None)
    if traces is not None:
        traces.clear()
    yield
    CONFIRMATION_REGISTRY._by_session.clear()
    if records is not None:
        records.clear()
    if executions is not None:
        executions.clear()
    if traces is not None:
        traces.clear()


def _configured_kernel(**overrides) -> AgentKernel:
    settings = RuntimeSettings(api_key="test-key", **overrides)
    return AgentKernel(settings=settings)


def _drain(async_iter) -> list:
    async def _collect():
        return [frame async for frame in async_iter]

    return asyncio.run(_collect())


class FakeUserMsg:
    def __init__(self, name: str, content: str) -> None:
        self.name = name
        self.content = content


class FakeAgent:
    """Records reply_stream inputs and yields scripted events."""

    def __init__(self, events: list | None = None, raise_on_stream: bool = False):
        self.events = events if events is not None else []
        self.raise_on_stream = raise_on_stream
        self.inputs: list = []
        # SPEC-021 R-3: parked confirmations snapshot risk tiers from the
        # toolkit; tests default to no toolkit (no risk_level on frames).
        self.toolkit = None

    async def reply_stream(self, inputs):
        self.inputs.append(inputs)
        if self.raise_on_stream:
            raise RuntimeError("boom")
        for event in self.events:
            yield event


def _patch_agent(monkeypatch, kernel: AgentKernel, agent: FakeAgent) -> None:
    async def fake_ensure_agent(session_id, bearer_token=None, model_id=None):
        return agent, FakeUserMsg, model_id or kernel.settings.provider

    monkeypatch.setattr(kernel, "ensure_agent", fake_ensure_agent)
    monkeypatch.setattr(kernel, "_snapshot_state", lambda session_id, agent: None)


# --- Registry semantics ---


def test_registry_register_get_resolve_roundtrip() -> None:
    registry = ConfirmationRegistry()
    pending = registry.register("s1", "alice", "r1", [TOOL_CALL], timeout=600)
    assert registry.is_parked("s1", 600)
    assert registry.get("s1", pending.confirm_id, 600) is pending
    registry.resolve("s1", pending.confirm_id)
    assert not registry.is_parked("s1", 600)
    with pytest.raises(ConfirmationNotFound):
        registry.get("s1", pending.confirm_id, 600)


def test_registry_get_rejects_unknown_resolved_and_foreign_ids() -> None:
    registry = ConfirmationRegistry()
    pending = registry.register("s1", "alice", "r1", [TOOL_CALL], timeout=600)
    with pytest.raises(ConfirmationNotFound):
        registry.get("s1", "other-id", 600)
    with pytest.raises(ConfirmationNotFound):
        registry.get("s2", pending.confirm_id, 600)


def test_registry_expired_entry_stays_observable_until_closed() -> None:
    registry = ConfirmationRegistry()
    pending = registry.register("s1", "alice", "r1", [TOOL_CALL], timeout=600)
    pending.created_at = time.monotonic() - 601
    with pytest.raises(ConfirmationExpired):
        registry.get("s1", pending.confirm_id, 600)
    # Expiry never silently evicts: the entry stays parked until
    # expire_confirmation interrupts the parked reply and resolves it.
    assert registry.is_parked("s1", 600)
    assert registry.peek_parked("s1") is pending


def test_registry_expiry_unlocks_session_for_new_parking() -> None:
    registry = ConfirmationRegistry()
    stale = registry.register("s1", "alice", "r1", [TOOL_CALL], timeout=600)
    stale.created_at = time.monotonic() - 601
    fresh = registry.register("s1", "alice", "r2", [TOOL_CALL], timeout=600)
    assert registry.get("s1", fresh.confirm_id, 600) is fresh


def test_registry_claim_makes_decisions_single_flight() -> None:
    registry = ConfirmationRegistry()
    pending = registry.register("s1", "alice", "r1", [TOOL_CALL], timeout=600)
    claimed = registry.claim("s1", pending.confirm_id, 600)
    assert claimed is pending
    # A duplicate confirm sees NotFound, while the session stays parked
    # (409 for new turns) until the resumed stream resolves the entry.
    with pytest.raises(ConfirmationNotFound):
        registry.claim("s1", pending.confirm_id, 600)
    with pytest.raises(ConfirmationNotFound):
        registry.get("s1", pending.confirm_id, 600)
    assert registry.is_parked("s1", 600)
    registry.resolve("s1", pending.confirm_id)
    assert not registry.is_parked("s1", 600)


def test_registry_take_for_expiry_is_single_flight() -> None:
    registry = ConfirmationRegistry()
    pending = registry.register("s1", "alice", "r1", [TOOL_CALL], timeout=600)
    pending.created_at = time.monotonic() - 601
    taken = registry.take_for_expiry("s1", pending.confirm_id)
    assert taken is pending
    assert pending.claimed
    # A concurrent expiry (or a decision claim) cannot take it twice.
    with pytest.raises(ConfirmationNotFound):
        registry.take_for_expiry("s1", pending.confirm_id)
    registry.resolve("s1", pending.confirm_id)


def test_registry_take_for_expiry_rejects_claimed_entry() -> None:
    registry = ConfirmationRegistry()
    pending = registry.register("s1", "alice", "r1", [TOOL_CALL], timeout=600)
    # A decision resume claimed while fresh; the resumed stream then
    # outlives the TTL. Expiry must not reach the claimed entry.
    registry.claim("s1", pending.confirm_id, 600)
    pending.created_at = time.monotonic() - 601
    with pytest.raises(ConfirmationNotFound):
        registry.take_for_expiry("s1", pending.confirm_id)
    assert registry.is_parked("s1", 600)


def test_pending_calls_payload_parses_tool_call_input() -> None:
    registry = ConfirmationRegistry()
    pending = registry.register("s1", "alice", "r1", [TOOL_CALL], timeout=600)
    payload = pending.pending_calls_payload()
    assert payload == [
        {
            "call_id": "call-1",
            "tool_name": "k8s.restart_service",
            "parameters": {"namespace": "ops"},
        }
    ]
    assert pending.tool_names() == ["k8s.restart_service"]


def test_pending_calls_payload_carries_known_risk_level() -> None:
    """SPEC-021 R-3: risk tiers snapshotted at park time ride the frames."""
    registry = ConfirmationRegistry()
    pending = registry.register(
        "s1", "alice", "r1", [TOOL_CALL], timeout=600,
        risk_levels={"k8s.restart_service": "write"},
    )
    payload = pending.pending_calls_payload()
    assert payload[0]["risk_level"] == "write"


def test_pending_calls_payload_omits_unknown_risk_level() -> None:
    registry = ConfirmationRegistry()
    pending = registry.register("s1", "alice", "r1", [TOOL_CALL], timeout=600)
    assert "risk_level" not in pending.pending_calls_payload()[0]


def test_pending_calls_payload_emits_gateway_canonical_name() -> None:
    """The parked call carries the sanitized model name; the payload must
    emit the dotted gateway canonical name so the signed execution
    envelope resolves at the gateway registry (TOOL_NOT_FOUND regression)."""
    registry = ConfirmationRegistry()
    pending = registry.register(
        "s1", "alice", "r1", [SANITIZED_TOOL_CALL], timeout=600,
        risk_levels={"k8s_delete_pod": "write"},
        gateway_names={"k8s_delete_pod": "k8s.delete_pod"},
    )
    payload = pending.pending_calls_payload()
    assert payload[0]["tool_name"] == "k8s.delete_pod"
    # The risk snapshot stays keyed by the sanitized model name.
    assert payload[0]["risk_level"] == "write"
    assert payload[0]["action"] == "tools:mutate"


def test_pending_calls_payload_keeps_unmapped_name() -> None:
    """Without a canonical mapping the parked name flows through as-is."""
    registry = ConfirmationRegistry()
    pending = registry.register(
        "s1", "alice", "r1", [SANITIZED_TOOL_CALL], timeout=600,
    )
    assert pending.pending_calls_payload()[0]["tool_name"] == "k8s_delete_pod"


def test_pending_calls_payload_carries_bridged_action() -> None:
    """SPEC-030 R-3: risk tiers map to the policy action the confirm
    bridge evaluates; calls without a gateway tier carry no action."""
    registry = ConfirmationRegistry()
    pending = registry.register(
        "s1", "alice", "r1", [TOOL_CALL], timeout=600,
        risk_levels={"k8s.restart_service": "write"},
    )
    assert pending.pending_calls_payload()[0]["action"] == "tools:mutate"


def test_highest_action_prefers_tools_mutate() -> None:
    registry = ConfirmationRegistry()
    pending = registry.register(
        "s1", "alice", "r1", [TOOL_CALL], timeout=600,
        risk_levels={"a.read": "read", "b.write": "write", "c.admin": "admin"},
    )
    assert pending.highest_action() == "tools:mutate"


def test_highest_action_none_without_risk_tiers() -> None:
    registry = ConfirmationRegistry()
    pending = registry.register("s1", "alice", "r1", [TOOL_CALL], timeout=600)
    assert pending.highest_action() is None


# --- SPEC-054 R-3: the change-request projection ---


def test_change_request_curated_k8s_delete_pod_summary() -> None:
    """A curated tool gets its effect sentence as the summary (no fields)."""
    cr = build_change_request(
        "k8s.delete_pod", {"name": "scratch-restart-demo", "namespace": "ops"}
    )
    assert cr == {
        "summary": 'Delete pod "scratch-restart-demo" in namespace "ops"'
    }


def test_change_request_curated_web_click_uses_element_label() -> None:
    """A write-tier ``web.*`` gets a curated sentence; the element label comes
    from the display_hint when known, else the raw snapshot ref."""
    assert build_change_request("web.click", {"ref": 12}, "Reset password button") == {
        "summary": 'Click "Reset password button"'
    }
    assert build_change_request("web.click", {"ref": 12}) == {
        "summary": 'Click "ref 12"'
    }


def test_change_request_generic_fallback_for_uncurated_tool() -> None:
    """Every other tool gets a generic lead + label->value fields, so no action
    card regresses for want of a curated formatter (R-3). SPEC-055 R-7: the
    generic fallback now masks **fail-closed** — ``k8s.restart_service.namespace``
    is not on the KNOWN_SAFE_FIELDS allow-list, so it masks rather than rendering
    verbatim (the SPEC-054 mask-if-known-secret posture failed open here)."""
    cr = build_change_request("k8s.restart_service", {"namespace": "ops"})
    assert cr["summary"] == "Confirm k8s.restart_service"
    assert cr["fields"] == [
        {"label": "namespace", "value": "***", "masked": True}
    ]


def test_change_request_fill_credential_never_emits_a_value() -> None:
    """``web.fill_credential`` is reference-only: it names the credential set
    and the field but NEVER a secret value — even if a literal ``value`` sneaks
    into the parameters, the projection ignores it (R-2/R-3)."""
    cr = build_change_request(
        "web.fill_credential",
        {"credential_set": "admin-portal", "field": "password", "ref": 7},
        "Password input",
    )
    assert cr["summary"] == (
        'Fill the "password" of credential set "admin-portal" into '
        '"Password input"'
    )
    assert {f["label"] for f in cr["fields"]} == {"credential_set", "field"}
    assert all(f["masked"] is False for f in cr["fields"])
    # A stray literal value in the parameters never reaches the projection.
    leaked = build_change_request(
        "web.fill_credential",
        {"credential_set": "admin-portal", "field": "password", "value": "s3cret"},
    )
    assert "s3cret" not in json.dumps(leaked)


def test_change_request_masks_secret_named_parameter() -> None:
    """A secret-bearing parameter name masks its value to ``***`` while keeping
    the label, so the approver sees a secret is involved without seeing it.
    SPEC-055 R-7: ``k8s.rotate_secret`` is uncurated, so BOTH fields mask
    fail-closed — ``name`` is not on the allow-list either (only the curated
    ``k8s.delete_pod`` name/namespace are KNOWN_SAFE_FIELDS)."""
    cr = build_change_request(
        "k8s.rotate_secret", {"name": "db", "password": "s3cret-PASSWORD-xyz"}
    )
    by_label = {f["label"]: f for f in cr["fields"]}
    assert by_label["name"] == {"label": "name", "value": "***", "masked": True}
    assert by_label["password"]["value"] == "***"
    assert by_label["password"]["masked"] is True
    assert "s3cret-PASSWORD-xyz" not in json.dumps(cr)


def test_change_request_masks_web_type_text_opaque_value() -> None:
    """``web.type.text`` sits on the per-tool opaque-value list — masked
    wholesale regardless of the generic field name (R-3)."""
    cr = build_change_request("web.type", {"ref": 3, "text": "hunter2"})
    assert cr["summary"] == 'Type into "ref 3"'
    assert cr["fields"] == [{"label": "text", "value": "***", "masked": True}]
    assert "hunter2" not in json.dumps(cr)


def test_change_request_masks_off_vocabulary_secret_fail_closed() -> None:
    """SPEC-055 R-7a: the generic projection masks **fail-closed** — a secret
    under an off-vocabulary, generically-named key (``data`` matches no
    ``SECRET_PARAM_SUBSTRINGS`` entry) still masks, closing SPEC-054's fail-open
    path where it projected as plaintext. The fixture carries a realistic
    literal secret so the absence assertion is not vacuous."""
    cr = build_change_request(
        "k8s.apply_config", {"data": "AKIAIOSFODNN7EXAMPLE"}
    )
    assert cr["summary"] == "Confirm k8s.apply_config"
    assert cr["fields"] == [
        {"label": "data", "value": "***", "masked": True}
    ]
    assert "AKIAIOSFODNN7EXAMPLE" not in json.dumps(cr)


def test_curated_effect_sentence_none_for_uncurated_tool() -> None:
    """The card message sources from the curated sentence where one exists; an
    uncurated tool yields ``None`` so the message stays the generic constant and
    the middleware ASK reason is never wired through verbatim (R-3/R-4)."""
    assert (
        curated_effect_sentence("k8s.delete_pod", {"name": "web-1"})
        == 'Delete pod "web-1" in namespace "default"'
    )
    assert curated_effect_sentence("k8s.restart_service", {"namespace": "ops"}) is None


def test_pending_calls_payload_assembles_change_request_for_action_kind() -> None:
    """An ``action`` card carries the projection as a SIBLING of ``parameters``
    (never inside it), so ``canonical_digest(parameters)`` — the signed
    args_digest — is byte-identical with and without it (R-3)."""
    registry = ConfirmationRegistry()
    pending = registry.register(
        "s1", "alice", "r1", [SANITIZED_TOOL_CALL], timeout=600,
        gateway_names={"k8s_delete_pod": "k8s.delete_pod"},
        approval_kind="action",
    )
    entry = pending.pending_calls_payload()[0]
    assert entry["change_request"] == {
        "summary": 'Delete pod "web-1" in namespace "default"'
    }
    assert "change_request" not in entry["parameters"]
    assert canonical_digest(entry["parameters"]) == canonical_digest(
        {"name": "web-1"}
    )


def test_pending_calls_payload_omits_change_request_for_flow_and_legacy_kind() -> None:
    """A ``flow`` card renders the flow headline instead, and a legacy/None kind
    carries no projection — so the exact-shape payload assertions above (and
    pre-v11 clients) stay byte-for-byte unchanged (R-1/R-3)."""
    registry = ConfirmationRegistry()
    for kind in ("flow", None):
        pending = registry.register(
            "s1", "alice", "r1", [TOOL_CALL], timeout=600, approval_kind=kind,
        )
        assert "change_request" not in pending.pending_calls_payload()[0]


# --- SPEC-055 R-7: fail-closed raw-parameter redaction ---


def test_redact_pending_calls_masks_action_card_parameters_in_place() -> None:
    """R-7 finding #1: an action card's raw ``parameters`` redact in place (keys
    preserved, secret-bearing values -> ``***``) and the SAME list is returned
    for chaining. A freshly re-read payload — the copy ``build_requests`` digests
    at resume — stays raw, the R-7c invariant at unit scope: redaction never
    mutates ``self.tool_calls``."""
    registry = ConfirmationRegistry()
    pending = registry.register(
        "s1", "alice", "r1", [SECRET_TOOL_CALL], 600, approval_kind="action",
    )
    payload = pending.pending_calls_payload()
    returned = redact_pending_calls(pending, payload)
    assert returned is payload
    assert payload[0]["parameters"] == {"name": "***", "password": "***"}
    # The signing input is a fresh parse, untouched by the display redaction.
    assert pending.pending_calls_payload()[0]["parameters"] == {
        "name": "db", "password": "s3cret-PASSWORD-xyz",
    }


def test_redact_pending_calls_leaves_flow_and_legacy_payloads_raw() -> None:
    """R-7 no-regression: redaction gates on the action kind, so a ``flow`` or
    legacy/None card's payload is returned byte-for-byte unchanged — it renders
    the headline (flow) or predates the discriminator (legacy) and carries no
    ``change_request`` sibling (plan §1)."""
    registry = ConfirmationRegistry()
    for kind in ("flow", None):
        pending = registry.register(
            "s1", "alice", "r1", [SECRET_TOOL_CALL], 600, approval_kind=kind,
        )
        payload = pending.pending_calls_payload()
        snapshot = json.dumps(payload, sort_keys=True)
        redact_pending_calls(pending, payload)
        assert json.dumps(payload, sort_keys=True) == snapshot
        assert payload[0]["parameters"] == {
            "name": "db", "password": "s3cret-PASSWORD-xyz",
        }


# --- Kernel: park on RequireUserConfirmEvent ---


def test_stream_events_parks_and_emits_confirmation_request(monkeypatch):
    kernel = _configured_kernel()
    agent = FakeAgent(
        events=[{"type": "TEXT_BLOCK_DELTA", "delta": "checking"}, _park_event()]
    )
    _patch_agent(monkeypatch, kernel, agent)

    frames = _drain(
        kernel.stream_events(
            message="restart it",
            request_id="req-1",
            session_id="s1",
            user_name="alice",
        )
    )
    confirmation_frames = [
        f for f in frames if f.get("type") == "confirmation_request"
    ]
    assert len(confirmation_frames) == 1
    frame = confirmation_frames[0]
    assert frame["pending_calls"][0]["tool_name"] == "k8s.restart_service"
    assert frame["message"] == "Tool execution requires your confirmation."
    # The stream ends without message_end after parking.
    assert not any(f.get("event") == "message_end" for f in frames)
    assert CONFIRMATION_REGISTRY.is_parked("s1", 600)
    # SPEC-033 R-1: the durable record carries the parking turn ordinal
    # (0 here — the fake agent has no prior context).
    record = CONFIRMATION_RECORD_STORE.load_pending_for_session("s1")
    assert record is not None
    assert record["turn_index"] == 0


def test_action_card_redacts_secret_on_stream_frame_and_record(monkeypatch):
    """SPEC-055 R-7b (stream + persist legs): parking an action call whose input
    carries a literal secret emits a ``confirmation_request`` frame AND writes a
    durable record whose ``parameters`` mask it to ``***`` — the plaintext never
    rides the frame or lands at rest beside the masked ``change_request``. The
    fixture parks the real secret, so the absence assertions are not vacuous."""
    kernel = _configured_kernel()
    agent = FakeAgent(events=[_secret_park_event()])
    _patch_agent(monkeypatch, kernel, agent)

    frames = _drain(
        kernel.stream_events(
            message="rotate it",
            request_id="req-1",
            session_id="s1",
            user_name="alice",
        )
    )
    frame = next(
        f for f in frames if f.get("type") == "confirmation_request"
    )
    # k8s.rotate_secret is uncurated => an action card; both the off-allow-list
    # ``name`` and the secret-named ``password`` mask fail-closed.
    assert frame["approval_kind"] == "action"
    assert frame["pending_calls"][0]["parameters"] == {
        "name": "***", "password": "***",
    }
    assert "s3cret-PASSWORD-xyz" not in json.dumps(frame)

    # At-rest leg: the durable record is fed from the same redacted payload.
    record = CONFIRMATION_RECORD_STORE.load_pending_for_session("s1")
    assert record is not None
    assert record["pending_calls"][0]["parameters"] == {
        "name": "***", "password": "***",
    }
    assert "s3cret-PASSWORD-xyz" not in json.dumps(record)


def test_parked_record_carries_parking_turn_ordinal(monkeypatch):
    """SPEC-033 R-1: the record stores the same ordinal evidence uses."""
    kernel = _configured_kernel()
    agent = FakeAgent(events=[_park_event()])
    agent.state = SimpleNamespace(
        context=[
            SimpleNamespace(role="user"),
            SimpleNamespace(role="assistant"),
            SimpleNamespace(role="user"),
        ]
    )
    _patch_agent(monkeypatch, kernel, agent)

    _drain(
        kernel.stream_events(
            message="restart it",
            request_id="req-1",
            session_id="s1",
            user_name="alice",
        )
    )
    record = CONFIRMATION_RECORD_STORE.load_pending_for_session("s1")
    assert record["turn_index"] == 2


def test_parked_frame_and_durable_record_share_message_and_kind(monkeypatch):
    """SPEC-054 R-3/R-4: the card message and declared kind are computed ONCE
    at park time and fed to both the live frame and the durable record, so the
    operator card and the approver inbox / re-loaded transcript can never
    diverge. A curated action card carries its effect sentence as the message
    and the matching change-request projection beside its parameters."""
    kernel = _configured_kernel()
    delete_pod = ToolCallBlock(
        id="call-1",
        name="k8s_delete_pod",
        input='{"name": "scratch-restart-demo", "namespace": "default"}',
    )
    agent = FakeAgent(
        events=[
            RequireUserConfirmEvent(reply_id="reply-1", tool_calls=[delete_pod])
        ]
    )
    agent.toolkit = SimpleNamespace(
        tool_groups=[
            SimpleNamespace(
                tools=[_FakeToolkitTool("k8s_delete_pod", "write", "k8s.delete_pod")]
            )
        ]
    )
    _patch_agent(monkeypatch, kernel, agent)

    frames = _drain(
        kernel.stream_events(
            message="delete it",
            request_id="req-1",
            session_id="s1",
            user_name="alice",
        )
    )
    frame = [f for f in frames if f.get("type") == "confirmation_request"][0]
    record = CONFIRMATION_RECORD_STORE.load_pending_for_session("s1")
    sentence = 'Delete pod "scratch-restart-demo" in namespace "default"'
    # The curated effect sentence is the message on BOTH surfaces (R-4)...
    assert frame["message"] == sentence
    assert record["message"] == frame["message"]
    # ...the declared kind agrees (no bound flow, so this is an action)...
    assert frame["approval_kind"] == "action"
    assert record["approval_kind"] == frame["approval_kind"]
    # ...and the action card carries the projection beside its parameters.
    assert frame["pending_calls"][0]["change_request"] == {"summary": sentence}


def test_confirmation_request_carries_risk_level(monkeypatch):
    """SPEC-021 R-3: parked mutating calls surface their risk tier."""
    from types import SimpleNamespace

    kernel = _configured_kernel()
    agent = FakeAgent(events=[_park_event()])
    agent.toolkit = SimpleNamespace(
        tool_groups=[
            SimpleNamespace(
                tools=[_FakeToolkitTool("k8s.restart_service", "write")]
            )
        ]
    )
    _patch_agent(monkeypatch, kernel, agent)

    frames = _drain(
        kernel.stream_events(
            message="restart it",
            request_id="req-1",
            session_id="s1",
            user_name="alice",
        )
    )
    frame = [f for f in frames if f.get("type") == "confirmation_request"][0]
    assert frame["pending_calls"][0]["risk_level"] == "write"


def test_confirmation_request_emits_gateway_canonical_name(monkeypatch):
    """The confirmation frame must emit the dotted canonical name the
    gateway registry resolves, not the sanitized model-visible name."""
    kernel = _configured_kernel()
    agent = FakeAgent(
        events=[
            RequireUserConfirmEvent(
                reply_id="reply-1", tool_calls=[SANITIZED_TOOL_CALL]
            )
        ]
    )
    agent.toolkit = SimpleNamespace(
        tool_groups=[
            SimpleNamespace(
                tools=[
                    _FakeToolkitTool(
                        "k8s_delete_pod", "write", "k8s.delete_pod"
                    )
                ]
            )
        ]
    )
    _patch_agent(monkeypatch, kernel, agent)

    frames = _drain(
        kernel.stream_events(
            message="restart it",
            request_id="req-1",
            session_id="s1",
            user_name="alice",
        )
    )
    frame = [f for f in frames if f.get("type") == "confirmation_request"][0]
    assert frame["pending_calls"][0]["tool_name"] == "k8s.delete_pod"
    assert frame["pending_calls"][0]["risk_level"] == "write"


class _FakeToolkitTool:
    """Minimal toolkit tool exposing the gateway risk tier attribute."""

    def __init__(
        self,
        name: str,
        risk_level: str,
        gateway_tool_name: str | None = None,
    ) -> None:
        self.name = name
        self.gateway_risk_level = risk_level
        if gateway_tool_name is not None:
            self.gateway_tool_name = gateway_tool_name


def test_filter_mutating_for_hitl_drops_non_read_when_disabled():
    """SPEC-021 R-3: HITL off -> mutating tools never reach the toolkit."""
    kernel = _configured_kernel(hitl_confirm_timeout=0)
    definitions = [
        {"name": "k8s.list_pods", "risk_level": "read"},
        {"name": "k8s.delete_pod", "risk_level": "write"},
    ]
    kept = kernel._filter_mutating_for_hitl(definitions)
    assert [d["name"] for d in kept] == ["k8s.list_pods"]
    assert kernel._mutating_tools_excluded


def test_filter_mutating_for_hitl_keeps_all_when_bridging_enabled():
    kernel = _configured_kernel(hitl_confirm_timeout=600)
    definitions = [
        {"name": "k8s.list_pods", "risk_level": "read"},
        {"name": "k8s.delete_pod", "risk_level": "write"},
    ]
    kept = kernel._filter_mutating_for_hitl(definitions)
    assert kept == definitions
    assert not kernel._mutating_tools_excluded


def test_filter_read_only_drops_non_read_definitions():
    """Read-only turns (incident triage) never see mutating tools."""
    kernel = _configured_kernel(hitl_confirm_timeout=600)
    definitions = [
        {"name": "k8s.list_pods", "risk_level": "read"},
        {"name": "skills.search"},
        {"name": "k8s.delete_pod", "risk_level": "write"},
    ]
    kept = kernel._filter_read_only(definitions)
    assert [d["name"] for d in kept] == ["k8s.list_pods", "skills.search"]


def test_filter_read_only_keeps_everything_when_all_read():
    kernel = _configured_kernel(hitl_confirm_timeout=600)
    definitions = [
        {"name": "k8s.list_pods", "risk_level": "read"},
        {"name": "incidents.list", "risk_level": "read"},
    ]
    assert kernel._filter_read_only(definitions) == definitions


def test_stream_events_disabled_mode_keeps_silent_park(monkeypatch):
    kernel = _configured_kernel(hitl_confirm_timeout=0)
    agent = FakeAgent(events=[_park_event()])
    _patch_agent(monkeypatch, kernel, agent)

    frames = _drain(
        kernel.stream_events(
            message="restart it",
            request_id="req-1",
            session_id="s1",
            user_name="alice",
        )
    )
    assert not any(f.get("type") == "confirmation_request" for f in frames)
    assert not CONFIRMATION_REGISTRY.is_parked("s1", 600)


# --- Kernel: resume ---


def test_resume_confirmation_approves_all_parked_calls(monkeypatch):
    kernel = _configured_kernel()
    agent = FakeAgent(events=[{"type": "REPLY_END"}])
    _patch_agent(monkeypatch, kernel, agent)
    CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    pending = CONFIRMATION_REGISTRY.peek_parked("s1")
    claimed = CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)

    frames = _drain(
        kernel.resume_confirmation(
            session_id="s1",
            pending=claimed,
            decision="approve",
            user_name="alice",
            request_id="req-2",
            bearer_token="tok-alice",
        )
    )
    assert frames[0]["type"] == "confirmation_result"
    assert frames[0]["status"] == "approved"
    assert frames[0]["confirm_id"] == pending.confirm_id
    fed = agent.inputs[0]
    assert isinstance(fed, UserConfirmResultEvent)
    assert fed.reply_id == "reply-1"
    assert [r.confirmed for r in fed.confirm_results] == [True]
    assert not CONFIRMATION_REGISTRY.is_parked("s1", 600)


def test_resume_confirmation_deny_feeds_refusal_back(monkeypatch):
    kernel = _configured_kernel()
    agent = FakeAgent(events=[{"type": "REPLY_END"}])
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    claimed = CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)

    frames = _drain(
        kernel.resume_confirmation(
            session_id="s1",
            pending=claimed,
            decision="deny",
            user_name="alice",
            request_id="req-2",
        )
    )
    assert frames[0]["status"] == "denied"
    fed = agent.inputs[0]
    assert [r.confirmed for r in fed.confirm_results] == [False]


def test_claim_rejects_unknown_and_expired_entries() -> None:
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    with pytest.raises(ConfirmationNotFound):
        CONFIRMATION_REGISTRY.claim("s1", "nope", 600)
    pending.created_at = time.monotonic() - 601
    with pytest.raises(ConfirmationExpired):
        CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)


def test_resume_confirmation_accepts_cross_user_confirmer(monkeypatch) -> None:
    """SPEC-030 R-3: tier_2 approvals resume under a confirmer other
    than the session owner; who may decide is enforced by the
    platform-gateway approval-tier bridge, not the kernel."""
    kernel = _configured_kernel()
    agent = FakeAgent(events=[{"type": "REPLY_END"}])
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    claimed = CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)
    frames = _drain(
        kernel.resume_confirmation(
            "s1", claimed, "approve", "bob-approver", "req-x"
        )
    )
    assert frames[0]["type"] == "confirmation_result"
    assert frames[0]["status"] == "approved"
    assert not CONFIRMATION_REGISTRY.is_parked("s1", 600)


def test_resume_confirmation_resolves_entry_on_stream_error(monkeypatch):
    kernel = _configured_kernel()
    agent = FakeAgent(raise_on_stream=True)
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    claimed = CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)

    with pytest.raises(RuntimeError):
        _drain(
            kernel.resume_confirmation(
                "s1", claimed, "approve", "alice", "req-x"
            )
        )
    assert not CONFIRMATION_REGISTRY.is_parked("s1", 600)


def test_resume_confirmation_reparks_new_card_under_session_owner(monkeypatch):
    """SPEC-054 R-2: an unbound resumed turn can park ANOTHER per-action
    card; that card must be owned by the SESSION OWNER (the requester), not
    the approver who resumed the turn. Otherwise the platform-gateway tier_2
    self-approval rule sees owner == approver and blocks that same approver
    from deciding the next card, breaking the N-card unbound guarantee."""
    kernel = _configured_kernel()
    # The resumed turn parks again on a second ASK-gated tool.
    agent = FakeAgent(events=[_park_event()])
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    claimed = CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)

    frames = _drain(
        kernel.resume_confirmation(
            "s1", claimed, "approve", "bob-approver", "req-x",
            owner_user_name="alice",
        )
    )
    # The resumed turn re-parked a fresh card and ended the stream.
    assert any(f.get("type") == "confirmation_request" for f in frames)
    reparked = CONFIRMATION_REGISTRY.peek_parked("s1")
    assert reparked is not None
    assert reparked.confirm_id != pending.confirm_id
    # Owned by the requester, NOT the approver who resumed the turn — so the
    # approval bridge's self-approval check compares alice != bob-approver.
    assert reparked.user_id == "alice"
    # The durable record (the bridge's fallback source) carries the same owner.
    record = CONFIRMATION_RECORD_STORE.load_record("s1", reparked.confirm_id)
    assert record["owner_user_id"] == "alice"


def test_resume_confirmation_repark_owner_defaults_to_decider(monkeypatch):
    """Without an explicit session owner (e.g. an ownerless session), the
    re-parked card falls back to the resuming identity — the pre-fix
    attribution — so the owner is never stranded as None."""
    kernel = _configured_kernel()
    agent = FakeAgent(events=[_park_event()])
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    claimed = CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)

    _drain(
        kernel.resume_confirmation("s1", claimed, "approve", "bob-approver", "req-x")
    )
    reparked = CONFIRMATION_REGISTRY.peek_parked("s1")
    assert reparked is not None
    assert reparked.user_id == "bob-approver"


# --- Kernel: expiry closes parked calls via UserInterruptEvent ---


def test_expire_confirmation_interrupts_expired_entry(monkeypatch):
    kernel = _configured_kernel()
    agent = FakeAgent(events=[])
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    pending.created_at = time.monotonic() - 601

    # Peek reaches the aged entry, so expiry closes the parked reply via
    # UserInterruptEvent instead of raising.
    asyncio.run(kernel.expire_confirmation("s1", pending.confirm_id))
    assert isinstance(agent.inputs[0], UserInterruptEvent)
    assert agent.inputs[0].reply_id == "reply-1"
    assert not CONFIRMATION_REGISTRY.is_parked("s1", 600)
    with pytest.raises(ConfirmationNotFound):
        asyncio.run(kernel.expire_confirmation("s1", pending.confirm_id))


def test_expire_confirmation_cleanup_survives_interrupt_failure(
    monkeypatch,
):
    kernel = _configured_kernel()
    agent = FakeAgent(raise_on_stream=True)
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    # A failed interrupt still resolves the entry so the session cannot wedge.
    asyncio.run(kernel.expire_confirmation("s1", pending.confirm_id))
    assert isinstance(agent.inputs[0], UserInterruptEvent)
    assert agent.inputs[0].reply_id == "reply-1"
    assert not CONFIRMATION_REGISTRY.is_parked("s1", 600)


def test_expire_confirmation_skips_claimed_entry(monkeypatch):
    """A racing expiry must never interrupt an in-flight resume."""
    kernel = _configured_kernel()
    agent = FakeAgent(events=[])
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    # The confirm route claimed the entry while fresh; the resume stream
    # then outlives the TTL. Expiry must back off.
    CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)
    pending.created_at = time.monotonic() - 601
    with pytest.raises(ConfirmationNotFound):
        asyncio.run(kernel.expire_confirmation("s1", pending.confirm_id))
    assert agent.inputs == []
    # The entry stays parked until the resume's finally resolves it.
    assert CONFIRMATION_REGISTRY.is_parked("s1", 600)


# --- Kernel: durable resolution records (SPEC-031 R-1) ---


def _seed_parked_record(session_id: str, confirm_id: str, owner: str = "alice"):
    CONFIRMATION_RECORD_STORE.save_parked(
        make_record(
            confirm_id,
            session_id,
            owner,
            [{"call_id": "call-1", "tool_name": "k8s.restart_service"}],
            "tools:mutate",
        )
    )


def test_resume_confirmation_persists_durable_resolution(monkeypatch):
    """The applied decision lands in the record store with attribution."""
    kernel = _configured_kernel()
    agent = FakeAgent(events=[])
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    _seed_parked_record("s1", pending.confirm_id)
    claimed = CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)

    _drain(
        kernel.resume_confirmation(
            "s1", claimed, "approve", "bob-approver", "req-x"
        )
    )
    record = CONFIRMATION_RECORD_STORE.load_record("s1", pending.confirm_id)
    assert record["status"] == "approved"
    assert record["decider_user_id"] == "bob-approver"
    assert record["decision"] == "approve"
    assert record["decided_at"] is not None


def test_resume_confirmation_persists_denial(monkeypatch):
    kernel = _configured_kernel()
    agent = FakeAgent(events=[])
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    _seed_parked_record("s1", pending.confirm_id)
    claimed = CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)

    _drain(kernel.resume_confirmation("s1", claimed, "deny", "alice", "req-x"))
    record = CONFIRMATION_RECORD_STORE.load_record("s1", pending.confirm_id)
    assert record["status"] == "denied"
    assert record["decider_user_id"] == "alice"
    assert record["decision"] == "deny"


def test_expire_confirmation_persists_expired_record(monkeypatch):
    kernel = _configured_kernel()
    agent = FakeAgent(events=[])
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    _seed_parked_record("s1", pending.confirm_id)
    pending.created_at = time.monotonic() - 601

    asyncio.run(kernel.expire_confirmation("s1", pending.confirm_id))
    record = CONFIRMATION_RECORD_STORE.load_record("s1", pending.confirm_id)
    assert record["status"] == "expired"
    assert record["decider_user_id"] is None
    assert record["decision"] is None


def test_resolution_write_failure_never_breaks_resume(monkeypatch):
    """A failing record store degrades history only, never the decision."""
    kernel = _configured_kernel()
    agent = FakeAgent(events=[])
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    claimed = CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)

    def broken_mark_resolved(*args, **kwargs):
        raise RuntimeError("store down")

    monkeypatch.setattr(
        CONFIRMATION_RECORD_STORE, "mark_resolved", broken_mark_resolved
    )
    frames = _drain(
        kernel.resume_confirmation("s1", claimed, "approve", "alice", "req-x")
    )
    assert frames[0]["status"] == "approved"
    assert not CONFIRMATION_REGISTRY.is_parked("s1", 600)


# --- Routes ---


def _client() -> TestClient:
    return TestClient(create_app())


def _park_registered(session_id: str, user_id: str = "alice", age: float = 0.0):
    pending = CONFIRMATION_REGISTRY.register(
        session_id, user_id, "reply-1", [TOOL_CALL], 600
    )
    if age:
        pending.created_at = time.monotonic() - age
    return pending


def test_confirm_unknown_confirmation_returns_404() -> None:
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    response = client.post(
        "/api/v2/chat/confirm",
        json={
            "session_id": session_id,
            "confirm_id": "nope",
            "decision": "approve",
        },
        headers={"X-User-ID": "alice"},
    )
    assert response.status_code == 404


def test_confirm_cross_user_confirmer_reaches_registry(monkeypatch) -> None:
    """SPEC-030 R-3: the route no longer asserts session ownership — a
    tier_2 approver confirms a session they do not own; approval
    authorization is enforced by the platform-gateway bridge."""
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    pending = _park_registered(session_id)

    kernel = get_runtime_kernel()

    async def fake_resume(**kwargs):
        yield {
            "type": "confirmation_result",
            "confirm_id": pending.confirm_id,
            "status": "approved",
        }

    monkeypatch.setattr(kernel, "resume_confirmation", fake_resume)
    response = client.post(
        "/api/v2/chat/confirm",
        json={
            "session_id": session_id,
            "confirm_id": pending.confirm_id,
            "decision": "approve",
        },
        headers={"X-User-ID": "bob-approver"},
    )
    assert response.status_code == 200


def test_confirm_route_threads_session_owner_into_resume(monkeypatch) -> None:
    """SPEC-054 R-2: the confirm route passes the SESSION OWNER (not the
    approver) as ``owner_user_name`` so a card the resumed turn re-parks is
    attributed to the requester, letting a tier_2 approver decide the next
    unbound per-action card instead of tripping the self-approval block."""
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    pending = _park_registered(session_id)  # owner alice

    kernel = get_runtime_kernel()
    captured: dict = {}

    async def fake_resume(**kwargs):
        captured.update(kwargs)
        yield {
            "type": "confirmation_result",
            "confirm_id": pending.confirm_id,
            "status": "approved",
        }

    monkeypatch.setattr(kernel, "resume_confirmation", fake_resume)
    response = client.post(
        "/api/v2/chat/confirm",
        json={
            "session_id": session_id,
            "confirm_id": pending.confirm_id,
            "decision": "approve",
        },
        headers={"X-User-ID": "bob-approver"},
    )
    assert response.status_code == 200
    # The approver is the decider; the session owner rides along for re-parks.
    assert captured["user_name"] == "bob-approver"
    assert captured["owner_user_name"] == "alice"


def test_pending_confirmation_endpoint_returns_parked_metadata() -> None:
    """SPEC-030 R-3: the confirm bridge reads the parked batch's policy
    action and owner username from this endpoint."""
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    pending = CONFIRMATION_REGISTRY.register(
        session_id, "alice", "reply-1", [TOOL_CALL], 600,
        risk_levels={"k8s.restart_service": "write"},
    )
    response = client.get(
        "/api/v2/chat/pending-confirmation",
        params={"session_id": session_id},
        headers={"X-User-ID": "bob-approver"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["confirm_id"] == pending.confirm_id
    assert body["owner_user_id"] == "alice"
    assert body["action"] == "tools:mutate"
    assert body["pending_calls"][0]["tool_name"] == "k8s.restart_service"


def test_pending_confirmation_endpoint_404_when_unparked() -> None:
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    response = client.get(
        "/api/v2/chat/pending-confirmation",
        params={"session_id": session_id},
        headers={"X-User-ID": "alice"},
    )
    assert response.status_code == 404


def test_pending_confirmation_endpoint_404_unknown_session() -> None:
    client = _client()
    response = client.get(
        "/api/v2/chat/pending-confirmation",
        params={"session_id": "no-such-session"},
        headers={"X-User-ID": "alice"},
    )
    assert response.status_code == 404


def test_confirm_expired_returns_410(monkeypatch) -> None:
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    pending = _park_registered(session_id, age=601)

    kernel = get_runtime_kernel()
    expired_calls: list = []

    async def fake_expire(session_id_arg, confirm_id_arg):
        expired_calls.append((session_id_arg, confirm_id_arg))
        CONFIRMATION_REGISTRY.resolve(session_id_arg, confirm_id_arg)

    monkeypatch.setattr(kernel, "expire_confirmation", fake_expire)
    response = client.post(
        "/api/v2/chat/confirm",
        json={
            "session_id": session_id,
            "confirm_id": pending.confirm_id,
            "decision": "approve",
        },
        headers={"X-User-ID": "alice"},
    )
    assert response.status_code == 410
    assert expired_calls == [(session_id, pending.confirm_id)]


def test_parked_session_rejects_new_turns_with_409() -> None:
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    _park_registered(session_id)

    blocked = client.post(
        "/api/v2/chat",
        json={"message": "hello", "session_id": session_id},
        headers={"X-User-ID": "alice"},
    )
    assert blocked.status_code == 409
    blocked_stream = client.get(
        "/api/v2/chat/stream",
        params={"message": "hello", "session_id": session_id},
        headers={"X-User-ID": "alice"},
    )
    assert blocked_stream.status_code == 409


def test_confirm_approve_streams_confirmation_result_first(monkeypatch) -> None:
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    pending = _park_registered(session_id)

    kernel = get_runtime_kernel()

    async def fake_resume(**kwargs):
        yield {
            "type": "confirmation_result",
            "confirm_id": kwargs["pending"].confirm_id,
            "status": "approved",
        }
        yield {
            "event": "message_end",
            "message": "complete",
        }

    monkeypatch.setattr(kernel, "resume_confirmation", fake_resume)
    response = client.post(
        "/api/v2/chat/confirm",
        json={
            "session_id": session_id,
            "confirm_id": pending.confirm_id,
            "decision": "approve",
        },
        headers={"X-User-ID": "alice", "x-request-id": "req-confirm"},
    )
    assert response.status_code == 200
    frames = [
        line.removeprefix("data: ")
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert '"confirmation_result"' in frames[0]
    assert '"approved"' in frames[0]
    assert '"message_end"' in frames[1]


def test_duplicate_confirm_fails_closed_with_404(monkeypatch) -> None:
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    pending = _park_registered(session_id)

    kernel = get_runtime_kernel()

    async def fake_resume(**kwargs):
        yield {
            "type": "confirmation_result",
            "confirm_id": kwargs["pending"].confirm_id,
            "status": "approved",
        }
        yield {"event": "message_end", "message": "complete"}

    monkeypatch.setattr(kernel, "resume_confirmation", fake_resume)
    payload = {
        "session_id": session_id,
        "confirm_id": pending.confirm_id,
        "decision": "approve",
    }
    first = client.post(
        "/api/v2/chat/confirm", json=payload, headers={"X-User-ID": "alice"}
    )
    assert first.status_code == 200
    # The claim is taken before headers go out: a duplicate (retry, second
    # tab, second operator) must fail closed with 404, never re-resume.
    second = client.post(
        "/api/v2/chat/confirm", json=payload, headers={"X-User-ID": "alice"}
    )
    assert second.status_code == 404


def test_confirm_with_evicted_model_pin_degrades_to_default(monkeypatch) -> None:
    """A stale session pin (evicted by a discovery refresh or a key
    revocation) must degrade to the catalog default on resume instead
    of raising UnknownModelError mid-stream — the registry entry is
    claimed before headers go out, so a raise would wedge the session.
    """
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    session_service.pin_session_model(session_id, "qwen-evicted")
    pending = _park_registered(session_id)

    class FakeCatalog:
        """Only the default survives; the pinned id was evicted."""

        def get(self, model_id):
            if model_id == "deepseek-v4-flash":
                return SimpleNamespace(id=model_id)
            return None

        def default_entry(self):
            return SimpleNamespace(id="deepseek-v4-flash")

    monkeypatch.setattr(v2_routes, "MODEL_CATALOG", FakeCatalog())
    kernel = get_runtime_kernel()
    captured: list = []

    async def fake_resume(**kwargs):
        captured.append(kwargs.get("model_id"))
        yield {"event": "message_end", "message": "complete"}

    monkeypatch.setattr(kernel, "resume_confirmation", fake_resume)
    response = client.post(
        "/api/v2/chat/confirm",
        json={
            "session_id": session_id,
            "confirm_id": pending.confirm_id,
            "decision": "approve",
        },
        headers={"X-User-ID": "alice"},
    )
    assert response.status_code == 200
    assert captured == ["deepseek-v4-flash"]


def test_expired_park_interrupts_before_new_turn(monkeypatch) -> None:
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]
    pending = _park_registered(session_id, age=601)

    kernel = get_runtime_kernel()
    expired_calls: list = []

    async def fake_expire(session_id_arg, confirm_id_arg):
        expired_calls.append((session_id_arg, confirm_id_arg))
        CONFIRMATION_REGISTRY.resolve(session_id_arg, confirm_id_arg)

    async def fake_reply_text(**kwargs):
        return "resumed", None

    monkeypatch.setattr(kernel, "expire_confirmation", fake_expire)
    monkeypatch.setattr(kernel, "reply_text", fake_reply_text)
    response = client.post(
        "/api/v2/chat",
        json={"message": "hello", "session_id": session_id},
        headers={"X-User-ID": "alice"},
    )
    # The TTL-expired park is closed via UserInterruptEvent and the new
    # turn proceeds instead of wedging on the parked reply.
    assert response.status_code == 200
    assert response.json()["content"] == "resumed"
    assert expired_calls == [(session_id, pending.confirm_id)]


def test_confirm_request_rejects_invalid_decision() -> None:
    client = _client()
    response = client.post(
        "/api/v2/chat/confirm",
        json={
            "session_id": "s1",
            "confirm_id": "c1",
            "decision": "maybe",
        },
        headers={"X-User-ID": "alice"},
    )
    assert response.status_code == 422


# --- Kernel: signed execution requests and receipts (SPEC-037 R-2/R-4/R-5) ---

SIGNING_KEY = "test-execution-key"


class ExecutionCapturingAgent(FakeAgent):
    """Records the execution context visible inside the resumed stream."""

    def __init__(self, events=None):
        super().__init__(events=events or [{"type": "REPLY_END"}])
        self.observed_requests = "unset"
        self.observed_rejection = "unset"

    async def reply_stream(self, inputs):
        self.observed_requests = EXECUTION_REQUESTS.get()
        self.observed_rejection = EXECUTION_REJECTION.get()
        async for event in super().reply_stream(inputs):
            yield event


class ToolResultAgent(FakeAgent):
    """Pushes scripted tool_result frames onto the evidence sink."""

    def __init__(self, tool_frames, events=None):
        super().__init__(events=events or [{"type": "REPLY_END"}])
        self.tool_frames = tool_frames

    async def reply_stream(self, inputs):
        sink = TOOL_EVIDENCE_SINK.get()
        for frame in self.tool_frames:
            sink.put_nowait(frame)
        async for event in super().reply_stream(inputs):
            yield event


def _capture_execution_audits(monkeypatch) -> list:
    events: list = []

    def fake_emit(settings, event):
        events.append(event)

    monkeypatch.setattr("agent_service.runtime_kernel.emit_audit_event", fake_emit)
    return events


def _approve_parked(
    monkeypatch, kernel, agent, request_id="req-2", risk_levels=None
):
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register(
        "s1", "alice", "reply-1", [TOOL_CALL], 600, risk_levels=risk_levels,
    )
    claimed = CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)
    return _drain(
        kernel.resume_confirmation(
            session_id="s1",
            pending=claimed,
            decision="approve",
            user_name="alice",
            request_id=request_id,
            bearer_token="tok-alice",
        )
    )


def test_resume_approval_signs_and_persists_one_request_per_call(monkeypatch):
    """SPEC-037 R-2: one signed, persisted request per approved parked call."""
    kernel = _configured_kernel(execution_signing_key=SIGNING_KEY)
    agent = ExecutionCapturingAgent()
    audits = _capture_execution_audits(monkeypatch)

    frames = _approve_parked(monkeypatch, kernel, agent)
    assert frames[0]["status"] == "approved"

    requests = agent.observed_requests
    assert agent.observed_rejection is None
    assert set(requests) == {"call-1"}
    request = requests["call-1"]
    # The digest binds the parked arguments the approver saw.
    assert request["args_digest"] == canonical_digest({"namespace": "ops"})
    assert request["confirm_id"] == frames[0]["confirm_id"]
    assert request["owner_user_id"] == "alice"
    assert request["decider_user_id"] == "alice"
    assert verify_envelope(request, request["signature"], SIGNING_KEY)

    rows = EXECUTION_RECORD_STORE.load_for_session("s1")
    assert [row["status"] for row in rows] == ["requested"]
    assert rows[0]["execution_id"] == request["execution_id"]

    requested = [a for a in audits if a["event_type"] == "execution_requested"]
    assert len(requested) == 1
    assert requested[0]["outcome"] == "success"
    assert requested[0]["details"]["confirm_id"] == frames[0]["confirm_id"]
    assert requested[0]["details"]["call_id"] == "call-1"
    assert requested[0]["request_id"] == "req-2"
    assert requested[0]["session_id"] == "s1"


def test_args_digest_is_invariant_under_action_card_redaction(monkeypatch):
    """SPEC-055 R-7c (invariant): redaction is a display/at-rest projection only.
    Approving an action card whose parameters redact on the streamed
    ``confirmation_result`` frame still signs ``args_digest =
    canonical_digest(RAW parameters)`` — plaintext secret included — because
    ``build_requests`` re-reads a fresh ``pending_calls_payload()`` at resume.
    Masking never mutates the signed copy the gateway verifies against."""
    kernel = _configured_kernel(execution_signing_key=SIGNING_KEY)
    agent = ExecutionCapturingAgent()
    _capture_execution_audits(monkeypatch)
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register(
        "s1", "alice", "reply-1", [SECRET_TOOL_CALL], 600,
        approval_kind="action",
    )
    claimed = CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)
    frames = _drain(
        kernel.resume_confirmation(
            session_id="s1",
            pending=claimed,
            decision="approve",
            user_name="alice",
            request_id="req-2",
            bearer_token="tok-alice",
        )
    )
    result = frames[0]
    assert result["status"] == "approved"
    # The echoed result frame is redacted (stream leg)...
    assert result["pending_calls"][0]["parameters"] == {
        "name": "***", "password": "***",
    }
    assert "s3cret-PASSWORD-xyz" not in json.dumps(result)
    # ...yet the signed digest binds the RAW arguments, byte-identical to the
    # pre-redaction value.
    request = agent.observed_requests["call-secret"]
    assert request["args_digest"] == canonical_digest(
        {"name": "db", "password": "s3cret-PASSWORD-xyz"}
    )
    assert verify_envelope(request, request["signature"], SIGNING_KEY)


def test_resume_denial_constructs_no_execution_requests(monkeypatch):
    kernel = _configured_kernel(execution_signing_key=SIGNING_KEY)
    agent = ExecutionCapturingAgent()
    audits = _capture_execution_audits(monkeypatch)
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register("s1", "alice", "reply-1", [TOOL_CALL], 600)
    claimed = CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)

    frames = _drain(
        kernel.resume_confirmation(
            "s1", claimed, "deny", "alice", "req-2"
        )
    )
    assert frames[0]["status"] == "denied"
    assert agent.observed_requests is None
    assert agent.observed_rejection is None
    assert EXECUTION_RECORD_STORE.load_for_session("s1") == []
    # SPEC-055 R-2: a trace is a by-product of an *approved* mutation, so a
    # denial appends nothing.
    assert AUTHORING_TRACE_STORE.load_for_session("s1") == []
    assert audits == []


def test_resume_missing_signing_key_rejects_fail_closed(monkeypatch):
    """SPEC-037 R-2: no key ⇒ batch rejected, audited signing_unavailable."""
    kernel = _configured_kernel()
    agent = ExecutionCapturingAgent()
    audits = _capture_execution_audits(monkeypatch)

    frames = _approve_parked(monkeypatch, kernel, agent)
    # The confirmation itself applied; the rejection rides the tool boundary.
    assert frames[0]["status"] == "approved"
    assert agent.observed_requests is None
    assert agent.observed_rejection == "signing_unavailable"
    assert EXECUTION_RECORD_STORE.load_for_session("s1") == []
    # SPEC-055 R-2: the fail-closed rejection happens before the capture
    # seam, so an *unsigned* mutation never enters an authoring trace.
    assert AUTHORING_TRACE_STORE.load_for_session("s1") == []

    rejected = [a for a in audits if a["event_type"] == "execution_rejected"]
    assert len(rejected) == 1
    assert rejected[0]["outcome"] == "deny"
    assert rejected[0]["details"]["reason"] == "signing_unavailable"
    assert rejected[0]["details"]["call_id"] == "call-1"
    assert rejected[0]["request_id"] == "req-2"


def test_resume_receipt_closes_executed_call(monkeypatch):
    """SPEC-037 R-4/R-5: a landed tool result signs the closing receipt."""
    kernel = _configured_kernel(execution_signing_key=SIGNING_KEY)
    tool_frame = {
        "type": "tool_result",
        "call_id": "call-1",
        "tool_name": "k8s.restart_service",
        "status": "success",
        "output": {"restarted": True},
    }
    agent = ToolResultAgent([tool_frame])
    audits = _capture_execution_audits(monkeypatch)

    frames = _approve_parked(monkeypatch, kernel, agent)
    confirm_id = frames[0]["confirm_id"]
    assert any(f == {**tool_frame, "request_id": "req-2", "session_id": "s1"} for f in frames)

    rows = EXECUTION_RECORD_STORE.load_for_session("s1")
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "succeeded"
    assert row["digest_match"] is True
    receipt = row["receipt"]
    assert receipt["request_id"] == "req-2"
    assert receipt["outcome_digest"] == canonical_digest(
        {**tool_frame, "request_id": "req-2", "session_id": "s1"}
    )
    assert verify_envelope(receipt, receipt["signature"], SIGNING_KEY)

    completed = [a for a in audits if a["event_type"] == "execution_completed"]
    assert len(completed) == 1
    assert completed[0]["outcome"] == "success"
    assert completed[0]["details"]["status"] == "succeeded"
    assert completed[0]["details"]["confirm_id"] == confirm_id
    assert completed[0]["details"]["request_id"] == "req-2"
    assert isinstance(completed[0]["details"]["duration_ms"], int)


def test_resume_invocation_rejection_marks_record_without_receipt(monkeypatch):
    """SPEC-037 R-3/R-4: an EXECUTION_REJECTED frame closes the row as
    rejected; the audit already went out at the invocation boundary."""
    kernel = _configured_kernel(execution_signing_key=SIGNING_KEY)
    tool_frame = {
        "type": "tool_result",
        "call_id": "call-1",
        "tool_name": "k8s.restart_service",
        "status": "error",
        "error": {
            "code": "EXECUTION_REJECTED",
            "message": "execution rejected",
            "reason": "args_digest_mismatch",
        },
    }
    agent = ToolResultAgent([tool_frame])
    audits = _capture_execution_audits(monkeypatch)

    _approve_parked(monkeypatch, kernel, agent)
    rows = EXECUTION_RECORD_STORE.load_for_session("s1")
    assert [row["status"] for row in rows] == ["rejected"]
    assert rows[0]["reject_reason"] == "args_digest_mismatch"
    assert rows[0]["digest_match"] is False
    assert rows[0]["receipt"] is None
    # The kernel never re-audits a rejection owned by the tool boundary.
    assert not any(a["event_type"] == "execution_rejected" for a in audits)
    assert not any(a["event_type"] == "execution_completed" for a in audits)


def test_resume_timeout_result_signs_timeout_receipt(monkeypatch):
    kernel = _configured_kernel(execution_signing_key=SIGNING_KEY)
    tool_frame = {
        "type": "tool_result",
        "call_id": "call-1",
        "tool_name": "k8s.restart_service",
        "status": "error",
        "error": {"code": "TIMEOUT", "message": "gateway timed out"},
    }
    agent = ToolResultAgent([tool_frame])
    audits = _capture_execution_audits(monkeypatch)

    _approve_parked(monkeypatch, kernel, agent)
    rows = EXECUTION_RECORD_STORE.load_for_session("s1")
    assert rows[0]["status"] == "timeout"
    assert rows[0]["receipt"]["status"] == "timeout"
    completed = [a for a in audits if a["event_type"] == "execution_completed"]
    assert completed[0]["outcome"] == "error"
    assert completed[0]["details"]["status"] == "timeout"


# --- SPEC-055 R-2: authoring-trace capture at the approval seam --------------


def _approve_call(monkeypatch, kernel, agent, tool_call, **register_kwargs):
    """Approve one parked call through the real ``resume_confirmation`` seam."""
    _patch_agent(monkeypatch, kernel, agent)
    pending = CONFIRMATION_REGISTRY.register(
        "s1", "alice", "reply-1", [tool_call], 600, **register_kwargs
    )
    claimed = CONFIRMATION_REGISTRY.claim("s1", pending.confirm_id, 600)
    return _drain(
        kernel.resume_confirmation(
            session_id="s1",
            pending=claimed,
            decision="approve",
            user_name="alice",
            request_id="req-2",
            bearer_token="tok-alice",
        )
    )


def _risk_snapshot(*tool_calls, level="write"):
    """A park-time risk-tier snapshot, keyed the way the registry looks it up.

    ``pending_calls_payload`` reads ``risk_levels[tool_call.name]``, and in
    production that name is the sanitized gateway name while these fixtures
    use both forms — so keying off the call itself keeps the snapshot honest
    whichever form a fixture parks. Without it a parked call carries no tier
    at all, which the R-2 capture gate treats as "not a known mutation".
    """
    return {call.name: level for call in tool_calls}


def test_resume_approval_appends_a_trace_step_beside_the_record(monkeypatch):
    """SPEC-055 R-2: capture happens at the same resume seam that writes
    ``execution_records``, as a by-product of the already-signed mutation —
    so an approved per-action write yields exactly one replayable step next
    to exactly one durable record."""
    kernel = _configured_kernel(execution_signing_key=SIGNING_KEY)
    agent = ExecutionCapturingAgent()
    _capture_execution_audits(monkeypatch)

    frames = _approve_parked(
        monkeypatch, kernel, agent, risk_levels=_risk_snapshot(TOOL_CALL)
    )
    request = agent.observed_requests["call-1"]

    rows = AUTHORING_TRACE_STORE.load_for_session("s1")
    assert len(rows) == 1
    step = rows[0]
    assert step["session_id"] == "s1"
    assert step["position"] == 1
    assert step["tool_name"] == "k8s.restart_service"
    # The replayable argument the receipt only ever hashed.
    assert step["args"] == {"namespace": "ops"}
    assert step["execution_id"] == request["execution_id"]
    assert step["confirm_id"] == frames[0]["confirm_id"]
    assert step["captured_at"] == request["requested_at"]
    assert step["status"] == "draft"
    # One record, one step: the two stores stay 1:1 at this seam.
    records = EXECUTION_RECORD_STORE.load_for_session("s1")
    assert [row["execution_id"] for row in records] == [step["execution_id"]]


def test_resume_approval_parameterizes_a_literal_secret_at_capture(monkeypatch):
    """SPEC-055 R-2: a literal secret is parameterized *before* the trace
    write, so it never reaches a store that outlives the receipts which are
    otherwise its only copy — while the signed digest stays bound to the raw
    arguments the gateway verifies against."""
    kernel = _configured_kernel(execution_signing_key=SIGNING_KEY)
    agent = ExecutionCapturingAgent()
    _capture_execution_audits(monkeypatch)

    _approve_call(
        monkeypatch,
        kernel,
        agent,
        SECRET_TOOL_CALL,
        approval_kind="action",
        risk_levels=_risk_snapshot(SECRET_TOOL_CALL),
    )

    rows = AUTHORING_TRACE_STORE.load_for_session("s1")
    assert len(rows) == 1
    assert rows[0]["args"] == {
        # ``password`` is on the name vocabulary ⇒ a credential-reference
        # placeholder; ``name`` is off-vocabulary for this tool ⇒ it rides
        # verbatim so the trace stays replayable.
        "name": "db",
        "password": TRACE_CREDENTIAL_PLACEHOLDER,
    }
    assert "s3cret-PASSWORD-xyz" not in json.dumps(rows)
    # The signed copy is untouched: parameterization is a trace projection,
    # never a signing input (the R-7c invariant, from the other side).
    request = agent.observed_requests["call-secret"]
    assert request["args_digest"] == canonical_digest(
        {"name": "db", "password": "s3cret-PASSWORD-xyz"}
    )
    assert verify_envelope(request, request["signature"], SIGNING_KEY)


def test_a_read_tier_parked_call_is_never_captured(monkeypatch):
    """SPEC-055 R-2: a read-tier call is never captured, and being *signed*
    is not what makes a call a mutation. A read tool parks whenever it is off
    the middleware's curated auto-allow list, so it reaches this seam
    approved and signed — the park-time tier snapshot is what excludes it.

    ``web.fill_credential`` is the exemplar on purpose, and it carries a
    consequence stages 6 and 7 have to absorb: it is read-tier *and* on the
    default auto-allow list, so under the default configuration a
    credential-set reference step never enters a trace at all. A graduated
    flow therefore replays the mutations with no way to authenticate, and
    the credential reference is what the human completing the draft supplies
    at merge time (spec.md R-4: graduation produces a draft for human review
    and merge, never an auto-published skill). Recorded in tasks.md as an
    R-4/R-5 input.
    """
    kernel = _configured_kernel(execution_signing_key=SIGNING_KEY)
    agent = ExecutionCapturingAgent()
    _capture_execution_audits(monkeypatch)

    _approve_call(
        monkeypatch,
        kernel,
        agent,
        CREDENTIAL_TOOL_CALL,
        approval_kind="action",
        risk_levels=_risk_snapshot(CREDENTIAL_TOOL_CALL, level="read"),
    )

    # Approved, signed and durably recorded like any other call...
    request = agent.observed_requests["call-cred"]
    assert verify_envelope(request, request["signature"], SIGNING_KEY)
    assert len(EXECUTION_RECORD_STORE.load_for_session("s1")) == 1
    # ...but it is not a mutation, so it is not a replay step.
    assert AUTHORING_TRACE_STORE.load_for_session("s1") == []
    assert AUTHORING_TRACE_STORE.trace_status("s1") is None


def test_a_trace_store_failure_never_blocks_execution_or_the_receipt(
    monkeypatch,
):
    """SPEC-055 R-2: capture is best-effort and fail-safe. A trace store that
    raises degrades to "no graduation candidate" — the resumed stream still
    approves, the signed request still reaches the tool boundary, and the
    ``execution_records`` row still closes with a signed receipt."""
    class BrokenTraceStore:
        backend_name = "broken"

        def append_step(self, step):
            raise RuntimeError("trace store down")

    monkeypatch.setattr(
        "agent_service.runtime_kernel.AUTHORING_TRACE_STORE", BrokenTraceStore()
    )
    kernel = _configured_kernel(execution_signing_key=SIGNING_KEY)
    tool_frame = {
        "type": "tool_result",
        "call_id": "call-1",
        "tool_name": "k8s.restart_service",
        "status": "success",
        "output": {"restarted": True},
    }
    agent = ToolResultAgent([tool_frame])
    audits = _capture_execution_audits(monkeypatch)

    # The tier has to be a known mutation, or the gate never reaches the
    # broken store and this test would pass vacuously.
    frames = _approve_parked(
        monkeypatch, kernel, agent, risk_levels=_risk_snapshot(TOOL_CALL)
    )

    # The mutation still executed and was still receipted.
    assert frames[0]["status"] == "approved"
    assert any(
        f == {**tool_frame, "request_id": "req-2", "session_id": "s1"}
        for f in frames
    )
    rows = EXECUTION_RECORD_STORE.load_for_session("s1")
    assert [row["status"] for row in rows] == ["succeeded"]
    assert rows[0]["digest_match"] is True
    receipt = rows[0]["receipt"]
    assert verify_envelope(receipt, receipt["signature"], SIGNING_KEY)
    assert {a["event_type"] for a in audits} == {
        "execution_requested",
        "execution_completed",
    }

