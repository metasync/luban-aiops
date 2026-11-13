"""SPEC-077 R-8: mocked-I/O proof of the remediation-staging live-check pipeline.

The shipped ``remediation-livecheck.sh`` embeds its ``--live`` pipeline in a
``python3 - <<'PY'`` heredoc. This test extracts that heredoc, compiles it, and
executes it with ``subprocess.run`` (kubectl) and ``urllib.request.build_opener``
(HTTP) mocked, across a success/failure scenario matrix — so the script's
assertion logic (the two-tier route pre-flight, the R-3 deny-by-default 403 gate,
the R-2 diagnosis-only fail-closed, the point-1 chat_completed attribution, and
the point-3 mutation ceiling "a staged proposal parks with ZERO
execution_requested and no auto-approval") and its loud, secret-free failure path
are exercised in the ordinary suite with no cluster, no network and no paid model
call. The gated live leg itself (``LUBAN_REMEDIATION_DRIVE_PAID_TURN=1``) stays an
explicit operator step, mirroring ``test_diagnosis_livecheck.py`` (SPEC-076 R-8).
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
          / "shared/platform-ops/e2e/remediation-livecheck.sh")
TOKEN = "fixture-admin-token"
DENIED_TOKEN = "fixture-denied-token"

# The stageable profile the paid leg stages one proposal for, and the
# diagnosis-only profile that must fail closed at the trigger (R-2).
STAGEABLE = "k8s-pod-degradation"
DIAGNOSIS_ONLY = "servicenow-incident"
DENIED_ROLE = "auditor"

# Scenarios that set LUBAN_REMEDIATION_DRIVE_PAID_TURN=1 (the gated paid leg).
_DRIVE = {"live-drive", "mutation-detected", "policy-gate-open", "failclosed-open"}
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
    "live-preflight", "live-drive", "missing-agent-route", "missing-gateway-route",
    "mutation-detected", "policy-gate-open", "failclosed-open", "agent-pod-down",
])
def test_remediation_livecheck_pipeline(scenario, monkeypatch, capsys) -> None:
    compiled = compile(_pipeline_source(), str(SCRIPT), "exec")
    created: list[str] = []
    deleted: list[str] = []
    remediate_calls: list[dict] = []
    counter = [0]

    def open_request(request, timeout):
        parts = urlsplit(request.full_url)
        path, query = parts.path, parse_qs(parts.query)
        method = request.get_method()
        if path == "/api/v1/auth/token":
            # The drive leg mints a platform-admin (remediate:stage to trigger +
            # audit:read to prove the ceiling) and an auditor (no remediate:stage)
            # for the R-3 deny-by-default gate assertion.
            roles = json.loads(request.data)["roles"]
            if roles == ["platform-admin"]:
                return _Response({"access_token": TOKEN})
            if roles == [DENIED_ROLE]:
                return _Response({"access_token": DENIED_TOKEN})
            raise AssertionError("unexpected token mint roles: %r" % (roles,))
        if path == "/api/v1/sessions" and method == "POST":
            counter[0] += 1
            sid = "ses-rem-%d" % counter[0]
            created.append(sid)
            return _Response({"session_id": sid})
        if path.startswith("/api/v1/sessions/") and method == "DELETE":
            deleted.append(path.rsplit("/", 1)[-1])
            return _Response({})
        if path == "/api/v1/remediate" and method == "POST":
            payload = json.loads(request.data)
            auth = request.headers.get("Authorization", "")
            denied = auth == "Bearer " + DENIED_TOKEN
            prof = payload["profile"]
            remediate_calls.append({"profile": prof, "denied": denied,
                                    "session_id": payload.get("session_id")})
            if denied:
                # R-3 deny-by-default: no remediate:stage → 403 at the gateway,
                # before any proxy or model call (unless the gate is open).
                if scenario == "policy-gate-open":
                    return _Response({"session_id": payload.get("session_id"),
                                      "content": "staged::leak", "status": "ok"},
                                     status=200)
                return _Response({"detail": {"action": "remediate:stage"}}, status=403)
            if prof == DIAGNOSIS_ONLY:
                # R-2 fail-closed: a diagnosis-only profile is refused 4xx with no
                # executor turn (unless the guard is open).
                if scenario == "failclosed-open":
                    return _Response({"content": "staged::leak", "status": "ok"},
                                     status=200)
                return _Response({"detail": "profile %s is diagnosis-only" % prof},
                                 status=422)
            # Stageable + authorized → the one billable staging turn parks.
            return _Response({"session_id": payload.get("session_id"),
                              "request_id": "req-1",
                              "content": "staged::%s" % prof,
                              "status": "partial", "model": None}, status=200)
        if path == "/api/v1/audit/events" and method == "GET":
            sid = query.get("session_id", [""])[0]
            event_type = query.get("event_type", [""])[0]
            if event_type == "chat_completed":
                return _Response({"events": [{
                    "event_type": "chat_completed", "session_id": sid,
                }], "next_cursor": None})
            if event_type == "execution_requested":
                # POINT 3 sensitivity: the script queries this event type
                # cluster-wide (no session_id) and prefix-matches the session
                # family, because the staging turn audits under
                # "<session>::orch::staging", never the bare parent id. Fabricate
                # the mutation under the DERIVED staging id so the test proves the
                # prefix match catches it — an exact parent-scoped query would miss
                # this and pass vacuously.
                if scenario == "mutation-detected":
                    parent = next(c["session_id"] for c in remediate_calls
                                  if c["session_id"])
                    events = [{"event_type": "execution_requested",
                               "session_id": parent + "::orch::staging"}]
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
            if url.endswith("/api/v2/remediate"):
                code = "404" if scenario == "missing-agent-route" else "401"
            elif url.endswith("/api/v1/remediate"):
                code = "404" if scenario == "missing-gateway-route" else "401"
            else:
                raise AssertionError("unexpected probe url: %s" % url)
            return SimpleNamespace(returncode=0, stdout=code, stderr="")
        raise AssertionError("unexpected kubectl invocation: %r" % (command,))

    monkeypatch.setenv("NAMESPACE", "dev-luban-aiops")
    monkeypatch.setenv("GATEWAY_URL", "http://gw.invalid")
    monkeypatch.setenv("IDENTITY_URL", "http://id.invalid")
    if scenario in _DRIVE:
        monkeypatch.setenv("LUBAN_REMEDIATION_DRIVE_PAID_TURN", "1")
    else:
        monkeypatch.delenv("LUBAN_REMEDIATION_DRIVE_PAID_TURN", raising=False)
    monkeypatch.setattr(urllib.request, "build_opener",
                        lambda *a, **k: SimpleNamespace(open=open_request))
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)

    if scenario in _SUCCESS:
        exec(compiled, {"__name__": "__main__"})
        out = capsys.readouterr().out
        if scenario == "live-preflight":
            assert "REMEDIATION_LIVECHECK_LIVE_OK" in out
            # The pre-flight never mints a token, opens a session, or drives a
            # staging turn — it only probes the two routes (no model call).
            assert remediate_calls == [] and created == [] and deleted == []
        else:
            assert "REMEDIATION_LIVECHECK_TURN_OK" in out
            # Three remediate calls: (2a) the denied-role gate, (2b) the
            # diagnosis-only fail-closed, (2c) the one authorized paid park.
            assert len(remediate_calls) == 3
            assert remediate_calls[0]["denied"] is True
            assert (remediate_calls[1]["profile"] == DIAGNOSIS_ONLY
                    and remediate_calls[1]["denied"] is False)
            assert (remediate_calls[2]["profile"] == STAGEABLE
                    and remediate_calls[2]["session_id"])
            # Only the paid turn opens a session, and it is cleaned up.
            assert len(created) == 1 and deleted == created
    else:
        with pytest.raises(SystemExit) as excinfo:
            exec(compiled, {"__name__": "__main__"})
        assert excinfo.value.code == 1
        err = capsys.readouterr().err
        assert "REMEDIATION_LIVECHECK_FAILED" in err
        # Each sensitivity scenario must be named as the specific ceiling it broke.
        if scenario == "mutation-detected":
            assert "execution_requested" in err or "auto-dispatch" in err
        if scenario == "policy-gate-open":
            assert "403" in err or "deny-by-default" in err
        if scenario == "failclosed-open":
            assert "4xx" in err or "fail-closed" in err
        assert TOKEN not in err and DENIED_TOKEN not in err  # secret-free failure
