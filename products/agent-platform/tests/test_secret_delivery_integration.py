"""SPEC-062 cross-product roundtrip; no provider, cluster, SMTP, or live secrets.

Run the shipped gateway connector through the real kernel evidence/prose and
snapshot paths, then the redemption route. Only model/identity/transport I/O is
replaced. Gateway JWT and platform proxy contracts have their own route suites.
"""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import jsonschema
from agentscope.event import RequireUserConfirmEvent
from agentscope.message import ToolCallBlock
from agentscope.permission import PermissionBehavior
from agentscope.tool import ToolResponse
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_service import runtime_kernel
from agent_service.api.v2.routes import _normalize_stream_event
from agent_service.runtime_kernel import AgentKernel
from agent_service.runtime_settings import RuntimeSettings
from agent_service.services import session_service, session_transcript
from agent_service.services.agent_state_store import InMemoryAgentStateStore
from agent_service.services.evidence_store import InMemoryEvidenceStore
from agent_service.services.hitl_confirmations import CONFIRMATION_REGISTRY
from agent_service.services.kernel_middleware import GatewayPermissionMiddleware, ToolEvidenceMiddleware
from agent_service.services.session_store import InMemorySessionStore
from test_kernel_middleware import _StubAgent, _StubTool
from test_prose_redaction import FakeUserMsg


def test_generation_projection_and_redeem_roundtrip(monkeypatch, caplog):
    root = Path(__file__).resolve().parents[3]
    # Test-only source dependency; products retain independent runtime packages.
    monkeypatch.syspath_prepend(str(root / "products/tool-gateway/src"))
    # Services normally own separate metric registries in separate processes.
    from functools import partial
    import prometheus_client
    with monkeypatch.context() as metrics:
        isolated = prometheus_client.CollectorRegistry()
        for name in ("Counter", "Gauge", "Histogram", "Summary"):
            metrics.setattr(prometheus_client, name, partial(getattr(prometheus_client, name), registry=isolated))
        from tool_gateway.api.routes import secrets as redemption
        from tool_gateway.core.config import GatewaySettings, get_settings
        from tool_gateway.tools.registry import ToolRegistry
        from tool_gateway.tools.secrets_connector import SecretsConnector
        from tool_gateway.tools.redaction import redact_result

    connector = SecretsConnector()
    registry = ToolRegistry()
    connector.register_tools(registry)
    states, evidence, sessions = InMemoryAgentStateStore(), InMemoryEvidenceStore(), InMemorySessionStore()
    monkeypatch.setattr(runtime_kernel, "AGENT_STATE_STORE", states)
    monkeypatch.setattr(runtime_kernel, "EVIDENCE_STORE", evidence)
    monkeypatch.setattr(session_transcript, "AGENT_STATE_STORE", states)
    monkeypatch.setattr(session_service, "SESSION_STORE", sessions)
    session = sessions.create_session("alice")
    prompt = "Generate a strong password and let me copy it."
    session_service.mark_session_turn(session.session_id, prompt)
    raw_results = []

    class Agent(_StubAgent):
        def __init__(self):
            super().__init__([_StubTool("secrets_generate_password", "secrets.generate_password")])
            self.snapshot = {"context": []}
            self.state = SimpleNamespace(model_dump_json=lambda: json.dumps(self.snapshot), context=[])

        async def reply_stream(self, inputs):
            call = ToolCallBlock(id="generate-1", name="secrets_generate_password", input="{}")
            tool = self.toolkit.tool_groups[0].tools[0]
            decision = await GatewayPermissionMiddleware().on_check_permission(
                self, {"tool": tool, "tool_call": call}, None,
            )
            assert decision.behavior == PermissionBehavior.ALLOW

            async def execute(**kwargs):
                result = await registry.invoke("secrets.generate_password", {}, {
                    "sub": "owner-sub", "chat_session_id": session.session_id,
                })
                assert result.status == "success"
                raw = redact_result(result)[0].to_dict()
                raw_results.append(raw)
                yield ToolResponse(metadata={"gateway_result": raw})

            async for _ in ToolEvidenceMiddleware().on_acting(self, {"tool_call": call}, execute):
                pass
            value = raw_results[0]["data"]["generated_password"]
            text = f"Created {value}; encoded {quote(value, safe='')}."
            self.snapshot = {"context": [
                {"role": "user", "content": prompt},
                {"role": "tool", "content": [{"type": "text", "text": json.dumps(raw_results[0])}]},
                {"role": "assistant", "content": text},
            ]}
            for char in text:
                yield {"type": "TEXT_BLOCK_DELTA", "delta": char}
            yield {"type": "message_end"}

    agent = Agent()
    kernel = AgentKernel(settings=RuntimeSettings(api_key="fixture"))

    async def ensure(*args, **kwargs):
        return agent, FakeUserMsg, kernel.settings.provider

    monkeypatch.setattr(kernel, "ensure_agent", ensure)

    async def run():
        return [frame async for frame in kernel.stream_events(prompt, "req-demo", session.session_id, "alice")]

    frames = asyncio.run(run())
    assert len(raw_results) == 1
    data = raw_results[0]["data"]
    value = data["generated_password"]
    deliveries = [f for f in frames if f.get("type") == "secret_delivery"]
    assert len(deliveries) == 1
    assert not any(f.get("type") == "confirmation_request" for f in frames)
    replay = evidence.load_turns(session.session_id)
    assert any(f["type"] == "secret_delivery" for turn in replay for f in turn["frames"])
    available, transcript = session_transcript.extract_transcript(session.session_id)
    assert available and transcript[-1]["content"] == "Created ***; encoded ***."
    schema = json.loads((root / "shared/shared-contracts/schemas/agent-stream-event.schema.json").read_text())
    for frame in frames:
        wire = _normalize_stream_event(frame, session.session_id, "req-demo").model_dump(exclude_none=True)
        jsonschema.validate(wire, schema)

    audit = []
    app = FastAPI()
    app.state.secret_delivery_buffer = connector.buffer
    app.include_router(redemption.router)
    app.dependency_overrides[get_settings] = lambda: GatewaySettings(secrets_enabled=True)

    async def identity(*args):
        return SimpleNamespace(subject="owner-sub", username="alice", actor=None, roles=["operator"])

    monkeypatch.setattr(redemption, "resolve_request_identity", identity)
    monkeypatch.setattr(redemption, "emit_audit_event", lambda settings, event: audit.append(event))
    assert not audit
    with TestClient(app) as client:
        url = "/api/v2/secrets/delivery/" + data["delivery_id"]
        first = client.get(url)
        assert first.status_code == 200 and first.json() == {"value": value}
        assert first.headers["cache-control"] == "no-store"
        assert client.get(url).status_code == 404
    assert len(audit) == 1 and audit[0]["event_type"] == "secret_delivered"
    assert audit[0]["details"]["delivery_id"] == data["delivery_id"]
    projections = json.dumps([frames, replay, transcript, audit, session.title]) + states.load_state(session.session_id) + caplog.text
    assert value not in projections
    assert quote(value, safe="") not in projections
    assert raw_results[0]["data"]["generated_password"] == value


def test_live_demo_with_mocked_io(monkeypatch, capsys):
    """Compile/run the shipped heredoc; never contact a cluster or redeem live."""
    import subprocess
    import urllib.request
    from urllib.error import HTTPError
    from urllib.parse import parse_qs, urlsplit

    import pytest

    root = Path(__file__).resolve().parents[3]
    script = root / "shared/platform-ops/e2e/secret-delivery-demo.sh"
    source = script.read_text().split("python3 - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    compiled = compile(source, str(script), "exec")
    value = "fixture-only-Generated!&+Demo"
    handle = "51b1935c-60ed-4eec-926b-8bff529df501"
    delivery = {"type": "secret_delivery", "delivery_id": handle,
                "channel": "portal_copy", "expires_at": "2099-01-01T00:00:00+00:00"}

    class Response:
        def __init__(self, body, status=200, headers=None):
            self.body, self.status, self.headers = body, status, headers or {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return (self.body if isinstance(self.body, str) else json.dumps(self.body)).encode()

    for scenario in ("success", "stream-leak", "title-leak", "log-leak", "missing-audit", "replay", "http-error", "bad-origin"):
        requests, log_reads, redemptions = [], [], []

        def open_request(request, timeout):
            requests.append(request)
            path = urlsplit(request.full_url).path
            if scenario == "http-error":
                raise HTTPError(request.full_url, 502, value, {}, None)
            if path == "/api/v1/tools":
                return Response([{"name": "secrets.generate_password", "risk_level": "read"}])
            if path == "/api/v1/sessions":
                assert request.get_method() == "POST" and json.loads(request.data) == {}
                return Response({"session_id": "ses-demo"})
            if path == "/api/v1/chat/stream":
                frames = [delivery, {"type": "message_delta", "delta": value if scenario == "stream-leak" else "Created ***."}]
                return Response("\n\n".join("data: " + json.dumps(frame) for frame in frames) + "\n\ndata: [DONE]\n")
            if path == "/api/v1/secrets/delivery/" + handle:
                redemptions.append(request)
                if len(redemptions) == 1 or scenario == "replay":
                    return Response({"value": value}, headers={"Cache-Control": "no-store"})
                raise HTTPError(request.full_url, 404, "unavailable", {}, None)
            if path == "/api/v1/sessions/ses-demo":
                return Response({"transcript_available": True, "transcript": [],
                                 "title": quote(value, safe="") if scenario == "title-leak" else "Generate a password",
                                 "evidence_turns": [{"frames": [delivery]}]})
            if path == "/api/v1/audit/events":
                query = parse_qs(urlsplit(request.full_url).query)
                assert query["request_id"] == [redemptions[0].get_header("X-request-id")]
                assert query["event_type"] == ["secret_delivered"]
                assert request.get_header("Authorization") == "Bearer fixture-audit-token"
                return Response({"events": [] if scenario == "missing-audit" else [
                    {"event_type": "secret_delivered", "details": {"delivery_id": handle, "channel": "portal_copy"}},
                ]})
            raise AssertionError("unexpected demo request")

        def logs(command, **kwargs):
            log_reads.append(command)
            assert command[0] == "kubectl" and "logs" in command
            return SimpleNamespace(returncode=0, stdout=value if scenario == "log-leak" else "metadata only")

        with monkeypatch.context() as io:
            io.setenv("GATEWAY_URL", "https://demo.invalid/path" if scenario == "bad-origin" else "https://demo.invalid")
            io.setenv("SECRET_DEMO_TOKEN", "fixture-operator-token")
            io.setenv("SECRET_DEMO_AUDIT_TOKEN", "fixture-audit-token")
            io.setattr(urllib.request, "build_opener", lambda handler: SimpleNamespace(open=open_request))
            io.setattr(subprocess, "run", logs)
            import time
            io.setattr(time, "sleep", lambda seconds: None)
            if scenario == "success":
                exec(compiled, {"__name__": "__main__"})
                assert len(redemptions) == 2 and len(log_reads) == 3
            else:
                with pytest.raises(SystemExit) as stopped:
                    exec(compiled, {"__name__": "__main__"})
                assert stopped.value.code == 1
            if scenario == "bad-origin":
                assert not requests
        output = capsys.readouterr()
        assert value not in output.out + output.err
        assert "fixture-operator-token" not in output.out + output.err
        assert ("SECRET_DELIVERY_OK" in output.out) == (scenario == "success")
        assert ("SECRET_DELIVERY_FAILED" in output.err) == (scenario != "success")


# --- SPEC-062 R-3 reveal-on-commit: the gated reset flow -------------------

GATED_CALL_ID = "gated-reset-1"


async def _collect(async_iter):
    return [frame async for frame in async_iter]


class _ResetFlowGenerateAgent(_StubAgent):
    """Generates a portal_copy password (buffered, not emitted), then parks on
    the gated reset write — the ResetAcmePassword shape the deferral targets."""

    def __init__(self, env):
        super().__init__([_StubTool("secrets_generate_password", "secrets.generate_password")])
        self._env = env
        self.snapshot = {"context": []}
        self.state = SimpleNamespace(
            model_dump_json=lambda: json.dumps(self.snapshot), context=[]
        )

    async def reply_stream(self, inputs):
        env = self._env
        call = ToolCallBlock(id="generate-1", name="secrets_generate_password", input="{}")

        async def execute(**kwargs):
            result = await env.registry.invoke("secrets.generate_password", {}, {
                "sub": "owner-sub", "chat_session_id": env.session.session_id,
            })
            assert result.status == "success"
            raw = env.redact_result(result)[0].to_dict()
            env.raw_results.append(raw)
            yield ToolResponse(metadata={"gateway_result": raw})

        async for _ in ToolEvidenceMiddleware().on_acting(self, {"tool_call": call}, execute):
            pass
        # Park on the gated mutation that commits the reset.
        yield RequireUserConfirmEvent(
            reply_id="reply-1",
            tool_calls=[ToolCallBlock(id=GATED_CALL_ID, name="web_click", input='{"ref": 7}')],
        )


class _ResetFlowCommitAgent(_StubAgent):
    """Resumes the parked turn: runs the gated reset write, then ends the turn.

    ``gated_status`` drives the release outcome — ``success`` reveals the held
    delivery (the commit); anything else withholds it (the silent burn).
    """

    def __init__(self, gated_status="success"):
        super().__init__([_StubTool("web_click", "web.click")])
        self._gated_status = gated_status
        self.snapshot = {"context": []}
        self.state = SimpleNamespace(
            model_dump_json=lambda: json.dumps(self.snapshot), context=[]
        )

    async def reply_stream(self, inputs):
        gated = {"tool_name": "web.click", "status": self._gated_status,
                 "data": {"ok": self._gated_status == "success"}}
        if self._gated_status != "success":
            gated["error"] = {"code": "UPSTREAM_ERROR", "message": "reset failed"}

        async def execute(**kwargs):
            yield ToolResponse(metadata={"gateway_result": gated})

        call = ToolCallBlock(id=GATED_CALL_ID, name="web_click", input='{"ref": 7}')
        async for _ in ToolEvidenceMiddleware().on_acting(self, {"tool_call": call}, execute):
            pass
        yield {"type": "message_end"}


def _run_reset_flow(monkeypatch, decision, gated_status="success"):
    """Drive generate -> park -> resume for one reset-flow scenario.

    Returns ``(park_frames, resume_frames, env)``. The signing machinery is
    stubbed so the test isolates delivery TIMING: an approval arms exactly the
    gated call_id in EXECUTION_REQUESTS, a denial arms nothing.
    """
    root = Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(root / "products/tool-gateway/src"))
    from functools import partial
    import prometheus_client
    with monkeypatch.context() as metrics:
        isolated = prometheus_client.CollectorRegistry()
        for name in ("Counter", "Gauge", "Histogram", "Summary"):
            metrics.setattr(prometheus_client, name,
                            partial(getattr(prometheus_client, name), registry=isolated))
        from tool_gateway.tools.registry import ToolRegistry
        from tool_gateway.tools.secrets_connector import SecretsConnector
        from tool_gateway.tools.redaction import redact_result

    connector = SecretsConnector()
    registry = ToolRegistry()
    connector.register_tools(registry)
    states, evidence, sessions = (
        InMemoryAgentStateStore(), InMemoryEvidenceStore(), InMemorySessionStore()
    )
    monkeypatch.setattr(runtime_kernel, "AGENT_STATE_STORE", states)
    monkeypatch.setattr(runtime_kernel, "EVIDENCE_STORE", evidence)
    monkeypatch.setattr(session_transcript, "AGENT_STATE_STORE", states)
    monkeypatch.setattr(session_service, "SESSION_STORE", sessions)
    session = sessions.create_session("alice")
    prompt = "Reset alice's acme-admin password."
    session_service.mark_session_turn(session.session_id, prompt)

    env = SimpleNamespace(
        root=root, connector=connector, registry=registry, session=session,
        prompt=prompt, evidence=evidence, states=states,
        redact_result=redact_result, raw_results=[],
    )
    kernel = AgentKernel(settings=RuntimeSettings(api_key="fixture"))
    holder = {"agent": _ResetFlowGenerateAgent(env)}

    async def fake_ensure(*args, **kwargs):
        return holder["agent"], FakeUserMsg, kernel.settings.provider

    monkeypatch.setattr(kernel, "ensure_agent", fake_ensure)
    monkeypatch.setattr(kernel, "_snapshot_state",
                        lambda session_id, agent, turn_literals=(): None)

    def fake_prepare_executions(pending, decider_user_id, confirmed, request_id, session_id):
        if not confirmed:
            return {}, None
        return {GATED_CALL_ID: {"call_id": GATED_CALL_ID,
                                "confirm_id": pending.confirm_id}}, None

    monkeypatch.setattr(kernel, "_prepare_executions", fake_prepare_executions)

    park_frames = asyncio.run(_collect(kernel.stream_events(
        prompt, "req-park", session.session_id, "alice")))
    parked = CONFIRMATION_REGISTRY.peek_parked(session.session_id)
    assert parked is not None, "the reset flow must park on the gated write"
    claimed = CONFIRMATION_REGISTRY.claim(
        session.session_id, parked.confirm_id, kernel.settings.hitl_confirm_timeout)
    holder["agent"] = _ResetFlowCommitAgent(gated_status)
    resume_frames = asyncio.run(_collect(kernel.resume_confirmation(
        session.session_id, claimed, decision, "alice", "req-resume",
        bearer_token="tok-alice")))
    return park_frames, resume_frames, env


def test_reset_flow_defers_reveal_until_gated_commit(monkeypatch, caplog):
    """Generate -> park -> approve -> gated success emits exactly one
    secret_delivery, under the committed turn, redeemable once, with the value
    absent from every projection. The button is NOT live while the card pends."""
    park_frames, resume_frames, env = _run_reset_flow(monkeypatch, "approve")
    value = env.raw_results[0]["data"]["generated_password"]
    delivery_id = env.raw_results[0]["data"]["delivery_id"]

    # No reveal while the card is pending; the park frame is present.
    assert not any(f.get("type") == "secret_delivery" for f in park_frames)
    assert any(f.get("type") == "confirmation_request" for f in park_frames)

    # Exactly one reveal, on the committed turn, carrying only metadata.
    released = [f for f in resume_frames if f.get("type") == "secret_delivery"]
    assert len(released) == 1
    assert released[0]["delivery_id"] == delivery_id
    assert released[0]["channel"] == "portal_copy"

    # Schema-valid on the wire.
    schema = json.loads(
        (env.root / "shared/shared-contracts/schemas/agent-stream-event.schema.json").read_text()
    )
    wire = _normalize_stream_event(released[0], env.session.session_id, "req-resume").model_dump(exclude_none=True)
    jsonschema.validate(wire, schema)

    # Persisted under the parking turn ordinal and replayed from evidence, so an
    # operator who did not watch the live resumed stream still gets the button.
    replay = env.evidence.load_turns(env.session.session_id)
    replayed = [f for turn in replay for f in turn["frames"] if f["type"] == "secret_delivery"]
    assert len(replayed) == 1 and replayed[0]["delivery_id"] == delivery_id

    # Redeemable exactly once by the owner, then burned.
    assert env.connector.buffer.redeem(delivery_id, "owner-sub") == value
    assert env.connector.buffer.redeem(delivery_id, "owner-sub") is None

    # The plaintext never rides any projection.
    projections = (
        json.dumps([park_frames, resume_frames, replay])
        + (env.states.load_state(env.session.session_id) or "") + caplog.text
    )
    assert value not in projections
    assert quote(value, safe="") not in projections


def test_reset_flow_deny_burns_delivery(monkeypatch):
    """A denial reveals nothing — the held delivery is never emitted, live or
    replayed (silent burn; it expires unredeemed)."""
    park_frames, resume_frames, env = _run_reset_flow(monkeypatch, "deny")
    assert not any(f.get("type") == "secret_delivery" for f in park_frames)
    assert not any(f.get("type") == "secret_delivery" for f in resume_frames)
    replay = env.evidence.load_turns(env.session.session_id)
    assert not any(f["type"] == "secret_delivery" for turn in replay for f in turn["frames"])


def test_reset_flow_gated_failure_burns_delivery(monkeypatch):
    """An approved gate whose mutation FAILS reveals nothing (silent burn) — the
    release trigger is a SUCCESSFUL gated tool_result, not the approval alone."""
    park_frames, resume_frames, env = _run_reset_flow(
        monkeypatch, "approve", gated_status="error")
    assert not any(f.get("type") == "secret_delivery" for f in park_frames)
    assert not any(f.get("type") == "secret_delivery" for f in resume_frames)
    replay = env.evidence.load_turns(env.session.session_id)
    assert not any(f["type"] == "secret_delivery" for turn in replay for f in turn["frames"])
