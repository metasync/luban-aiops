"""SPEC-076 R-8: mocked-I/O proof of the bounded-diagnosis live-check pipeline.

The shipped ``diagnosis-livecheck.sh`` embeds its ``--live`` pipeline in a
``python3 - <<'PY'`` heredoc. This test extracts that heredoc, compiles it, and
executes it with ``subprocess.run`` (kubectl) and ``urllib.request.build_opener``
(HTTP) mocked, across a success/failure scenario matrix — so the script's
assertion logic (the two-tier route pre-flight, the bounded ok|partial synthesis,
the point-1 chat_completed attribution, and the point-3 read-only "no
execution_requested" proof) and its loud, secret-free failure path are exercised
in the ordinary suite with no cluster, no network and no paid model call. The
gated live leg itself (``LUBAN_DIAGNOSIS_DRIVE_PAID_TURN=1``) stays an explicit
operator step, mirroring ``test_observability_livecheck.py`` (SPEC-065 R-4).
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
          / "shared/platform-ops/e2e/diagnosis-livecheck.sh")
TOKEN = "fixture-admin-token"

# The three runbooks the live drive leg wires (OQ-6/OQ-7); post-deploy-verify is
# scenario-tested, not live-wired.
WIRED = {"k8s-pod-degradation", "observability-alert", "servicenow-incident"}

# Scenarios that set LUBAN_DIAGNOSIS_DRIVE_PAID_TURN=1 (the gated paid leg).
_DRIVE = {"live-drive", "mutation-detected"}
_SUCCESS = {"live-preflight", "live-drive"}


def _pipeline_source() -> str:
    text = SCRIPT.read_text()
    return text.split("python3 - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]


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
    "live-preflight", "live-drive", "missing-agent-route",
    "missing-gateway-route", "mutation-detected", "agent-pod-down",
])
def test_diagnosis_livecheck_pipeline(scenario, monkeypatch, capsys) -> None:
    compiled = compile(_pipeline_source(), str(SCRIPT), "exec")
    created: list[str] = []
    deleted: list[str] = []
    diagnose_calls: list[dict] = []
    session_profile: dict[str, str] = {}
    counter = [0]

    def open_request(request, timeout):
        parts = urlsplit(request.full_url)
        path, query = parts.path, parse_qs(parts.query)
        method = request.get_method()
        if path == "/api/v1/auth/token":
            # The drive leg needs chat (to trigger) + audit:read (to prove
            # read-only): only platform-admin carries both.
            assert json.loads(request.data)["roles"] == ["platform-admin"]
            return _Response({"access_token": TOKEN})
        if path == "/api/v1/sessions" and method == "POST":
            counter[0] += 1
            sid = "ses-diag-%d" % counter[0]
            created.append(sid)
            return _Response({"session_id": sid})
        if path.startswith("/api/v1/sessions/") and method == "DELETE":
            deleted.append(path.rsplit("/", 1)[-1])
            return _Response({})
        if path == "/api/v1/diagnose" and method == "POST":
            payload = json.loads(request.data)
            diagnose_calls.append(payload)
            sid = payload.get("session_id")
            session_profile[sid] = payload["profile"]
            return _Response({"session_id": sid, "request_id": "req-1",
                              "content": "diagnosis::%s" % payload["profile"],
                              "status": "ok", "model": None})
        if path == "/api/v1/audit/events" and method == "GET":
            sid = query.get("session_id", [""])[0]
            event_type = query.get("event_type", [""])[0]
            if event_type == "chat_completed":
                return _Response({"events": [{
                    "event_type": "chat_completed", "session_id": sid,
                    "details": {"profile": session_profile.get(sid)},
                }], "next_cursor": None})
            if event_type == "execution_requested":
                # POINT 3 sensitivity (M4): the script queries this event type
                # cluster-wide (no session_id) and prefix-matches the session
                # family, because a member mutation audits under
                # "<session>::orch::<task>", never the bare parent id. Fabricate
                # the mutation under a MEMBER id so the test proves the prefix
                # match catches it — an exact parent-scoped query would miss this
                # and pass vacuously.
                if scenario == "mutation-detected":
                    parent = diagnose_calls[-1]["session_id"]
                    events = [{"event_type": "execution_requested",
                               "session_id": parent + "::orch::collect-metrics"}]
                else:
                    events = []
                return _Response({"events": events, "next_cursor": None})
        raise AssertionError(
            "unexpected livecheck request: %s %s" % (method, request.full_url))

    def fake_run(command, **kwargs):
        assert command[0] == "kubectl" and "exec" in command
        joined = " ".join(command)
        if scenario == "agent-pod-down" and "deployment/agent-service" in joined:
            return SimpleNamespace(returncode=1, stdout="", stderr="pod not running")
        if "curl" in command:
            url = command[-1]  # the http_code -w prints is the probe's stdout
            if url.endswith("/api/v2/diagnose"):
                code = "404" if scenario == "missing-agent-route" else "401"
            elif url.endswith("/api/v1/diagnose"):
                code = "404" if scenario == "missing-gateway-route" else "401"
            else:
                raise AssertionError("unexpected probe url: %s" % url)
            return SimpleNamespace(returncode=0, stdout=code, stderr="")
        raise AssertionError("unexpected kubectl invocation: %r" % (command,))

    monkeypatch.setenv("NAMESPACE", "dev-luban-aiops")
    monkeypatch.setenv("GATEWAY_URL", "http://gw.invalid")
    monkeypatch.setenv("IDENTITY_URL", "http://id.invalid")
    if scenario in _DRIVE:
        monkeypatch.setenv("LUBAN_DIAGNOSIS_DRIVE_PAID_TURN", "1")
    else:
        monkeypatch.delenv("LUBAN_DIAGNOSIS_DRIVE_PAID_TURN", raising=False)
    monkeypatch.setattr(urllib.request, "build_opener",
                        lambda *a, **k: SimpleNamespace(open=open_request))
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)

    if scenario in _SUCCESS:
        exec(compiled, {"__name__": "__main__"})
        out = capsys.readouterr().out
        if scenario == "live-preflight":
            assert "DIAGNOSIS_LIVECHECK_LIVE_OK" in out
            # The pre-flight never mints a token, opens a session, or drives a
            # diagnosis — it only probes the two routes (no model call).
            assert diagnose_calls == [] and created == [] and deleted == []
        else:
            assert "DIAGNOSIS_LIVECHECK_TURN_OK" in out
            # All three wired runbooks driven, each in its own throwaway session,
            # and every session cleaned up.
            assert {call["profile"] for call in diagnose_calls} == WIRED
            assert len(diagnose_calls) == len(WIRED)
            assert len(created) == len(WIRED) and deleted == created
    else:
        with pytest.raises(SystemExit) as excinfo:
            exec(compiled, {"__name__": "__main__"})
        assert excinfo.value.code == 1
        err = capsys.readouterr().err
        assert "DIAGNOSIS_LIVECHECK_FAILED" in err
        # A mutation detected on the read-only loop must be named as such.
        if scenario == "mutation-detected":
            assert "execution_requested" in err or "must never mutate" in err
        assert TOKEN not in err  # secret-free failure path
