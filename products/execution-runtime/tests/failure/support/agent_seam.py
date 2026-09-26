"""Parent-side launchers for the real agent invocation seam (cross-product legs).

The agent runs in its own product environment (``products/agent-platform/.venv``)
as a subprocess so no agent runtime import leaks into the execution-runtime test
process, mirroring ``test_agent_storage.agent``. Two shapes are provided:

* :func:`invoke_agent` — blocking; run the seam to completion and return facts.
* :class:`AgentProcess` — non-blocking and killable, for legs that must coordinate
  a worker barrier while the agent is mid-handoff (F-14 late result) or kill the
  agent OS process after the worker durably recorded a result (F-13 agent death).

Only bounded JSON facts cross the boundary; raw tool output, secret material, and
exception text never leave the probe.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from support.infrastructure import ROOT

_PROBE = Path(__file__).with_name("agent_invocation_probe.py")
_PERM_PROBE = Path(__file__).with_name("agent_permission_probe.py")
_AGENT_PYTHON = ROOT / "products/agent-platform/.venv/bin/python"


def _env():
    env = {k: v for k, v in os.environ.items() if k in {"PATH", "HOME", "TMPDIR"}}
    env.update(OTEL_SDK_DISABLED="true", OTEL_TRACES_EXPORTER="none",
               OTEL_METRICS_EXPORTER="none", OTEL_LOGS_EXPORTER="none")
    return env


def _payload(db, key, data):
    return json.dumps({"dsn": db.dsn, "key": key, "epoch": getattr(db, "epoch", ""), **data})


def decode_probe(returncode, output):
    # Do not let assertion rewriting print a CompletedProcess (including stderr),
    # or let JSONDecodeError include an untrusted response in failure artifacts.
    if returncode != 0:
        raise AssertionError("agent probe failed; no raw diagnostic retained")
    if len(output) > 1048576:
        raise AssertionError("agent probe facts exceeded the output bound")
    try:
        value = json.loads(output)
        if not isinstance(value, dict):
            raise ValueError
    except (ValueError, TypeError, RecursionError):
        raise AssertionError("agent probe returned invalid facts") from None
    return value


def run_probe(probe, payload, *, watchdog=40, env=None):
    try:
        process = subprocess.run(
            [str(_AGENT_PYTHON), str(probe)], input=payload,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            env=env or _env(), timeout=watchdog,
        )
    except subprocess.TimeoutExpired:
        raise AssertionError("agent probe exceeded its watchdog") from None
    return decode_probe(process.returncode, process.stdout)


def invoke_agent(db, key, *, watchdog=40, **data):
    """Blocking run of the real agent invocation seam; returns bounded facts."""
    return run_probe(_PROBE, _payload(db, key, data), watchdog=watchdog)


def decide_permission(db, key, *, watchdog=40, **data):
    """Blocking run of the real agent permission seam (on_check_permission +
    flow_signer); returns bounded decision/signing facts. The cross-product
    sibling of :func:`invoke_agent` for the gate upstream of dispatch."""
    return run_probe(_PERM_PROBE, _payload(db, key, data), watchdog=watchdog)


class AgentProcess:
    """A launched agent seam the parent can race against a barrier or kill."""

    def __init__(self, db, key, **data):
        self._process = subprocess.Popen(
            [str(_AGENT_PYTHON), str(_PROBE)], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=_env(),
        )
        self._process.stdin.write(_payload(db, key, data))
        self._process.stdin.close()
        # Drop the closed handle: communicate() would otherwise flush it and raise
        # ValueError, so collect() can only read stdout/stderr under its watchdog.
        self._process.stdin = None
        self.pid = self._process.pid

    @property
    def alive(self):
        return self._process.poll() is None

    def collect(self, *, watchdog=40):
        try:
            out, _ = self._process.communicate(timeout=watchdog)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=5)
            raise AssertionError("agent invocation probe exceeded its watchdog") from None
        return decode_probe(self._process.returncode, out)

    def kill(self):
        self._process.kill()
        self._process.wait(timeout=5)
        assert self._process.returncode != 0, "agent process did not die after kill"
