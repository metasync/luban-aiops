"""SPEC-080 R-8: mocked-I/O proof of the agent-initiated-clarification
live-check pipeline.

The shipped ``clarification-livecheck.sh`` embeds its ``--live`` pipeline in a
``python3 - <<'PY'`` heredoc. This test extracts that heredoc, compiles it, and
executes it with ``subprocess.run`` (kubectl) and ``urllib.request.build_opener``
(HTTP) mocked, across a success/failure scenario matrix — so the script's
assertion logic (the two-tier chat-route pre-flight, the answer-route deployment
probe, the ``AGENT_ASKUSER_ENABLED`` flag gate, the park → owner-answer →
same-turn resume drive, the point-1 ``chat_completed`` attribution, and the
point-3 ceiling "a read-only clarification requests ZERO execution and
auto-approves nothing") and its loud, secret-free failure path are exercised in
the ordinary suite with no cluster, no network and no paid model call. The gated
live leg itself (``LUBAN_CLARIFICATION_DRIVE_PAID_TURN=1``) stays an explicit
operator step, mirroring ``test_conversational_remediation_livecheck.py``
(SPEC-078 R-7).

The surface difference from the confirmation live-check: a clarification parks on
the v14 ``clarification_request`` frame (no ``message_end``, never a
``confirmation_request``) and is answered in-line by the OWNER over
``POST /api/v1/sessions/{id}/clarification/answer`` — no approver, no
distinct-human routing, no tier/self-approval gate (OQ-5).
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

SCRIPT = (Path(__file__).resolve().parents[3]
          / "shared/platform-ops/e2e/clarification-livecheck.sh")
TOKEN = "fixture-owner-token"
OWNER_ROLE = "operator"

# The one question the parked clarification carries, and the answer the owner
# gives in-line (its first option) — pinned so the drive leg's answer body is
# asserted, not merely sent.
QUESTION = "Which environment?"
FIRST_OPTION = "production"
CLARIFICATION_ID = "cl-1"

# Scenarios that set the gated paid leg (drive on).
_DRIVE = {
    "flag-off", "live-drive", "park-no-clarification", "park-is-confirmation",
    "park-completes", "resume-no-result", "resume-no-message-end",
    "no-completion", "mutation-detected", "auto-approval-detected",
    "durable-not-clarification",
}
_SUCCESS = {"live-preflight", "live-drive"}


def _pipeline_source() -> str:
    text = SCRIPT.read_text()
    return text.split("python3 - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]


def _sse(frames: list[dict]) -> str:
    return "".join("data: " + json.dumps(frame) + "\n\n" for frame in frames)


def _clarification_request(session_id: str) -> dict:
    return {
        "type": "clarification_request",
        "clarification_id": CLARIFICATION_ID,
        "questions": [{
            "question": QUESTION,
            "header": "Environment",
            "options": [
                {"label": FIRST_OPTION, "description": "Production"},
                {"label": "staging", "description": "Staging"},
            ],
        }],
        "session_id": session_id,
    }


def _park_frames(scenario: str, session_id: str) -> list[dict]:
    request = _clarification_request(session_id)
    if scenario == "park-no-clarification":
        # The model never asked — only a delta flowed, so nothing parked.
        return [{"type": "message_delta", "delta": "assuming prod", "session_id": session_id}]
    if scenario == "park-is-confirmation":
        return [request, {"type": "confirmation_request", "confirm_id": "cf-1",
                          "session_id": session_id}]
    if scenario == "park-completes":
        return [request, {"type": "message_end", "message": "complete",
                          "session_id": session_id}]
    return [request]


def _resume_frames(scenario: str, session_id: str) -> list[dict]:
    result = {"type": "clarification_result", "clarification_id": CLARIFICATION_ID,
              "status": "answered",
              "answers": [{"question": QUESTION, "selected": [FIRST_OPTION]}],
              "session_id": session_id}
    delta = {"type": "message_delta", "delta": "Thanks — checking.", "session_id": session_id}
    end = {"type": "message_end", "message": "complete", "model": "deepseek-v4-flash",
           "session_id": session_id}
    if scenario == "resume-no-result":
        return [delta, end]
    if scenario == "resume-no-message-end":
        return [result, delta]
    return [result, delta, end]


def _durable_card(scenario: str, session_id: str) -> dict:
    if scenario == "durable-not-clarification":
        return {"session_id": session_id, "confirm_id": "cf-1",
                "park_kind": "confirmation", "status": "approved",
                "pending_calls": [{"tool_name": "k8s.delete_pod", "risk_level": "write"}],
                "owner_user_id": "luban-operator"}
    return {"session_id": session_id, "confirm_id": CLARIFICATION_ID,
            "park_kind": "clarification", "status": "answered",
            "pending_calls": [],
            "questions": _clarification_request(session_id)["questions"],
            "owner_user_id": "luban-operator", "decider_user_id": "luban-operator"}


class _Response:
    def __init__(self, body, status: int = 200) -> None:
        self._body = body
        self.status = status
        self.headers: dict[str, str] = {}

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args) -> bool:
        return False

    def read(self) -> bytes:
        raw = self._body if isinstance(self._body, str) else json.dumps(self._body)
        return raw.encode()


@pytest.mark.parametrize("scenario", [
    "live-preflight", "missing-agent-route", "missing-gateway-route",
    "missing-answer-route", *sorted(_DRIVE),
])
def test_clarification_livecheck_pipeline(scenario, monkeypatch, capsys) -> None:
    compiled = compile(_pipeline_source(), str(SCRIPT), "exec")
    created: list[str] = []
    deleted: list[str] = []
    chat_stream_calls: list[str] = []
    answer_calls: list[dict] = []
    counter = [0]

    def open_request(request, timeout):
        parts = urlsplit(request.full_url)
        path, query = parts.path, parse_qs(parts.query)
        method = request.get_method()
        if path == "/api/v1/auth/token":
            # The drive leg mints exactly ONE owner token (the owner both parks
            # and answers in-line — no distinct approver identity, OQ-5).
            roles = json.loads(request.data)["roles"]
            assert roles == [OWNER_ROLE], roles
            return _Response({"access_token": TOKEN})
        if path == "/api/v1/sessions" and method == "POST":
            counter[0] += 1
            sid = "ses-clar-%d" % counter[0]
            created.append(sid)
            return _Response({"session_id": sid})
        if path == "/api/v1/chat/stream" and method == "GET":
            sid = query["session_id"][0]
            chat_stream_calls.append(sid)
            return _Response(_sse(_park_frames(scenario, sid)))
        if path.endswith("/clarification/answer") and method == "POST":
            payload = json.loads(request.data)
            answer_calls.append(payload)
            sid = path.split("/")[4]
            assert request.headers["Authorization"] == "Bearer " + TOKEN
            return _Response(_sse(_resume_frames(scenario, sid)))
        if path == "/api/v1/audit/events" and method == "GET":
            event_type = query.get("event_type", [""])[0]
            sid = query.get("session_id", [None])[0]
            if sid is not None and event_type == "chat_completed":
                events = ([] if scenario == "no-completion"
                          else [{"event_type": "chat_completed", "session_id": sid}])
                return _Response({"events": events, "next_cursor": None})
            if sid is None:
                # Family mutation query (no session_id): the point-3 ceiling.
                events = []
                if scenario == "mutation-detected" and event_type == "execution_requested":
                    events = [{"event_type": event_type, "session_id": created[0]}]
                if scenario == "auto-approval-detected" and event_type == "confirmation_decided":
                    events = [{"event_type": event_type, "session_id": created[0]}]
                return _Response({"events": events, "next_cursor": None})
            return _Response({"events": [], "next_cursor": None})
        if path.startswith("/api/v1/sessions/") and method == "GET":
            sid = path.rsplit("/", 1)[-1]
            return _Response({"confirmations": [_durable_card(scenario, sid)]})
        if path.startswith("/api/v1/sessions/") and method == "DELETE":
            deleted.append(path.rsplit("/", 1)[-1])
            return _Response({}, status=200)
        raise AssertionError(
            "unexpected livecheck request: %s %s" % (method, request.full_url))

    def fake_run(command, **kwargs):
        assert command[0] == "kubectl"
        if "exec" in command and "curl" in command:
            url = command[-1]  # the http_code -w prints is the probe's stdout
            if url.endswith("/api/v2/chat"):
                code = "404" if scenario == "missing-agent-route" else "401"
            elif url.endswith("/api/v1/chat"):
                code = "404" if scenario == "missing-gateway-route" else "401"
            elif url.endswith("/clarification/answer"):
                code = "404" if scenario == "missing-answer-route" else "401"
            else:
                raise AssertionError("unexpected probe url: %s" % url)
            return SimpleNamespace(returncode=0, stdout=code, stderr="")
        if "get" in command and "configmap" in command:
            flag = "false" if scenario == "flag-off" else "true"
            return SimpleNamespace(returncode=0, stdout=flag, stderr="")
        raise AssertionError("unexpected kubectl invocation: %r" % (command,))

    monkeypatch.setenv("NAMESPACE", "dev-luban-aiops")
    monkeypatch.setenv("GATEWAY_URL", "http://gw.invalid")
    monkeypatch.setenv("IDENTITY_URL", "http://id.invalid")
    if scenario in _DRIVE:
        monkeypatch.setenv("LUBAN_CLARIFICATION_DRIVE_PAID_TURN", "1")
    else:
        monkeypatch.delenv("LUBAN_CLARIFICATION_DRIVE_PAID_TURN", raising=False)
    monkeypatch.setattr(urllib.request, "build_opener",
                        lambda *a, **k: SimpleNamespace(open=open_request))
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)

    if scenario in _SUCCESS:
        exec(compiled, {"__name__": "__main__"})
        out = capsys.readouterr().out
        if scenario == "live-preflight":
            assert "CLARIFICATION_LIVECHECK_LIVE_OK" in out
            # The pre-flight never mints a token, opens a session, or drives a
            # turn — it only probes the two chat routes + the answer route.
            assert chat_stream_calls == [] and created == [] and deleted == []
            assert answer_calls == []
        else:
            assert "CLARIFICATION_LIVECHECK_TURN_OK" in out
            # Exactly one billable turn: it parks, the owner answers in-line, and
            # the same turn resumes. The throwaway session is cleaned up.
            assert len(chat_stream_calls) == 1 and len(created) == 1
            assert deleted == created
            assert len(answer_calls) == 1
            assert answer_calls[0]["clarification_id"] == CLARIFICATION_ID
            assert answer_calls[0]["answers"] == [
                {"question": QUESTION, "selected": [FIRST_OPTION]}]
            assert out.index("PARK_PROOF:") < out.index("RESUME_PROOF:")
            assert out.index("RESUME_PROOF:") < out.index("DURABLE_PROOF:")
            assert out.index("DURABLE_PROOF:") < out.index("CLEANUP_PROOF:")
    else:
        with pytest.raises(SystemExit) as excinfo:
            exec(compiled, {"__name__": "__main__"})
        assert excinfo.value.code == 1
        err = capsys.readouterr().err
        assert "CLARIFICATION_LIVECHECK_FAILED" in err
        # Each sensitivity scenario must be named as the specific invariant it
        # broke — a silent pass would mean the ceiling is not actually asserted.
        if scenario == "missing-agent-route":
            assert "/api/v2/chat" in err and "404" in err
        if scenario == "missing-gateway-route":
            assert "/api/v1/chat" in err
        if scenario == "missing-answer-route":
            assert "clarification/answer" in err
        if scenario == "flag-off":
            assert "AGENT_ASKUSER_ENABLED" in err
        if scenario == "park-no-clarification":
            assert "clarification_request" in err
        if scenario == "park-is-confirmation":
            assert "confirmation_request" in err
        if scenario == "park-completes":
            assert "message_end" in err
        if scenario == "resume-no-result":
            assert "clarification_result" in err
        if scenario == "resume-no-message-end":
            assert "message_end" in err
        if scenario == "no-completion":
            assert "chat_completed" in err
        if scenario == "mutation-detected":
            assert "execution_requested" in err
        if scenario == "auto-approval-detected":
            assert "confirmation_decided" in err
        if scenario == "durable-not-clarification":
            assert "clarification card" in err
        assert TOKEN not in err  # secret-free failure
