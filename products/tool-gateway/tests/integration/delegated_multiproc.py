"""SPEC-070 p5c — independently-started gateway processes against shared custody.

Where :mod:`delegated_runtime` (p5b) drives one real app *in process*, this
module launches **separate ``uvicorn`` gateway processes** — each composing the
real application from environment via ``create_app()``, with no overrides, no
fakes, and no JWKS patching — all pointed at the *same* disposable Postgres
custody and the *same* fixture OAuth/target servers over real generated TLS. It
then proves the runtime-observable cross-replica invariants the plan requires
(§"Deterministic integration fixtures", line 179):

* **cross-replica callback/refresh + cache miss** — an owner enrolls through
  replica A's authorization routes; replica B (which never saw the enrollment and
  whose process-local access cache is cold) performs the delegated send, so B must
  read the grant B's sibling published to shared custody and refresh it against the
  real provider (a real refresh + a real resource call, asserted by count);
* **restart durability** — a replica is terminated and a *fresh* process started;
  the published grant still authorizes a send (durability rides Postgres, never
  process memory);
* **revocation dominates warm replicas** — a shared-custody revocation is
  immediately visible to every replica *despite* their warm process-local access
  caches: the next send on each fails closed with zero refresh and zero dispatch
  (the acquisition seam rereads authoritative custody metadata before it will use
  any cached token);
* **configuration removal** — a freshly-started replica whose credential-set
  configuration no longer contains the set fails closed (``CREDENTIAL_SET_NOT_FOUND``)
  with zero dispatch, never falling back to another credential.

Division of coverage (no duplication): the *store-level* boundaries in the same
plan bullet — key rotation, wrong/removed keys, recovery epochs, account changes,
local expiry/delay bounds, and ambiguous/lost-commit boundaries — are proven
against shared Postgres by :mod:`delegated_custody` using independently started
processes, barriers, fake clocks, and a real COMMIT-acknowledgment wire proxy; both
modules run under the same ``make verify`` gate. This module adds the dimension
only a *running gateway* can exercise: cross-replica behavior through the real
HTTP routes and adapters.

Run::

    uv run --frozen --project products/tool-gateway \
        python products/tool-gateway/tests/integration/delegated_multiproc.py
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

import delegated_fixtures as fx
import delegated_runtime as rt
from delegated_fixtures import CALLBACK, IDENTITY_ISSUER, USERS, FixtureStack, check

ROOT = Path(__file__).resolve().parents[4]
SET_ID = "user"
READY_TIMEOUT = 45.0


def _log(msg: str) -> None:
    print(f"[s70-multiproc] {msg}", flush=True)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# --- one independently-started gateway process ------------------------------

class GatewayProcess:
    """A real ``uvicorn`` gateway composed from env against the shared fixtures.

    The generated CA is installed into the on-disk ``certifi`` bundle by the
    fixture stack, so this child process verifies the fixture OAuth/target servers
    over real TLS with hostname and chain checks fully enabled — the same trust
    anchor the in-process app uses, inherited across the process boundary.
    """

    def __init__(self, stack: FixtureStack, name: str, *, env_overrides: dict | None = None):
        self.stack = stack
        self.name = name
        self.env_overrides = env_overrides or {}
        self.proc: subprocess.Popen | None = None
        self.base_url = ""
        self._logfh = None

    def start(self) -> "GatewayProcess":
        port = _free_port()
        env = {**os.environ, **rt.runtime_env(self.stack), **self.env_overrides}
        env["OTEL_ENABLED"] = "false"
        self._logfh = tempfile.NamedTemporaryFile(  # noqa: SIM115 — dumped on failure
            prefix=f"s70-{self.name}-", suffix=".log", delete=False, mode="w+b")
        cmd = [
            sys.executable, "-m", "uvicorn", "--factory", "tool_gateway.app:create_app",
            "--host", "127.0.0.1", "--port", str(port),
            "--log-level", "warning", "--no-access-log",
        ]
        self.proc = subprocess.Popen(cmd, env=env, cwd=str(ROOT),
                                     stdout=self._logfh, stderr=subprocess.STDOUT)
        self.base_url = f"http://127.0.0.1:{port}"
        self._wait_ready()
        _log(f"{self.name}: real gateway process up at {self.base_url} (pid {self.proc.pid})")
        return self

    def _wait_ready(self) -> None:
        deadline = time.monotonic() + READY_TIMEOUT
        last = ""
        while time.monotonic() < deadline:
            if self.proc is not None and self.proc.poll() is not None:
                raise RuntimeError(f"{self.name}: gateway exited early "
                                   f"({self.proc.returncode})\n{self._tail()}")
            try:
                r = httpx.get(self.base_url + "/health/ready", timeout=3.0)
                if r.status_code == 200:
                    return
                last = f"status {r.status_code}"
            except Exception as exc:  # noqa: BLE001 — not listening yet
                last = exc.__class__.__name__
            time.sleep(0.4)
        raise RuntimeError(f"{self.name}: not ready within {READY_TIMEOUT}s ({last})\n{self._tail()}")

    def _tail(self) -> str:
        try:
            self._logfh.flush()
            return Path(self._logfh.name).read_text(errors="replace")[-4000:]
        except Exception:  # noqa: BLE001
            return "<no gateway log>"

    def client(self) -> httpx.Client:
        # The gateway routes are plain loopback HTTP; the *outbound* provider and
        # resource calls it makes are the real-TLS ones (verified via certifi).
        return httpx.Client(base_url=self.base_url, timeout=30.0)

    def stop(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        if self._logfh is not None:
            try:
                os.unlink(self._logfh.name)
            except OSError:
                pass
            self._logfh.close()


# --- a delegated send that returns the raw response (no built-in assertion) --

def _send(client: httpx.Client, stack: FixtureStack, user: str) -> httpx.Response:
    from tool_gateway.services.delegated_invoke import canonical_digest
    from delegated_fixtures import mint_human

    profile = USERS[user]
    parameters = {"url": rt.resource_url(stack), "credential_set": SET_ID}
    projection = {
        "tool_name": "http.get", "session_id": "ses-mp", "approval_kind": "action",
        "execution_id": f"exec-mp-{user}", "args_digest": canonical_digest(parameters),
        "requester_namespace": IDENTITY_ISSUER, "requester_sub": profile["sub"],
        "decider_namespace": IDENTITY_ISSUER, "decider_sub": profile["sub"],
        "owner_user_id": profile["username"], "decider_user_id": profile["username"],
    }
    return client.post("/api/v2/tools/invoke-delegated", json={
        "projection": projection, "parameters": parameters,
        "requester_token": mint_human(stack.signing_key, user),
        "decider_token": mint_human(stack.signing_key, user),
    }, headers=rt.exec_workload(stack))


def _revoke_owner(stack: FixtureStack, user: str) -> None:
    """A shared-custody local revocation, visible to every replica at once."""
    from tool_gateway.services.custody_crypto import Keyring
    from tool_gateway.services.delegated_custody import Owner, PostgresCustodyStore

    async def _run() -> None:
        store = PostgresCustodyStore(stack.admin_dsn, Keyring(stack.files["keyring_path"]),
                                     stack.files["config_path"], stack.files["set_id"], CALLBACK)
        await store.revoke(Owner(IDENTITY_ISSUER, USERS[user]["sub"]))
    asyncio.run(_run())


# --- the scenarios ----------------------------------------------------------

def _run(stack: FixtureStack) -> None:
    asyncio.run(rt._provision(stack))

    gateways: list[GatewayProcess] = []
    try:
        g1 = GatewayProcess(stack, "gw1").start()
        g2 = GatewayProcess(stack, "gw2").start()
        gateways += [g1, g2]

        # S1: enroll on replica A, send on replica B (cross-replica + cache miss).
        _log("S1: enroll via gw1, delegated send via gw2 (cold cache, shared custody)")
        with g1.client() as c1:
            cid = rt.phase_producer(c1, stack, "alice", "ses-mp", "call-mp-1")
            rt.phase_enroll(c1, stack, cid, "alice")
        stack.state.reset_stats()
        with g2.client() as c2:
            rt.phase_send(c2, stack, "alice")  # asserts a real refresh + one resource call
        s = stack.state.stats
        check(s["token_refresh"] >= 1 and s["resource"] == 1,
              f"S1: gw2 refreshed gw1's published grant from shared custody {s}")
        _log("S1: PASS — cross-replica refresh on a cold process-local cache")

        # S2: restart durability — kill gw2, start a fresh gw3, send again.
        _log("S2: terminate gw2, start a fresh gw3, delegated send (restart durability)")
        g2.stop()
        gateways.remove(g2)
        g3 = GatewayProcess(stack, "gw3").start()
        gateways.append(g3)
        stack.state.reset_stats()
        with g3.client() as c3:
            rt.phase_send(c3, stack, "alice")
        check(stack.state.stats["resource"] == 1, "S2: a restarted replica still sends")
        _log("S2: PASS — the published grant survives a replica restart")

        # S3: revocation dominates warm replicas (gw1 and gw3 both sent above).
        _log("S3: shared-custody revocation, then send on each warm replica")
        _revoke_owner(stack, "alice")
        for gw in (g1, g3):
            stack.state.reset_stats()
            with gw.client() as c:
                r = _send(c, stack, "alice")
            st = stack.state.stats
            # A revoked grant is a ``denied`` re-authorization posture (403). The
            # acquisition seam rereads authoritative custody metadata *before* it
            # will use any warm cached token, so the replica fails closed with
            # zero refresh and zero dispatch despite its process-local cache —
            # revocation in shared custody dominates every replica at once.
            check(r.status_code == 403, f"S3: {gw.name} denies after revocation ({r.status_code})")
            body = r.json()
            check(body.get("status") != "success",
                  f"S3: {gw.name} reports no success after revocation ({body.get('status')})")
            check(st["resource"] == 0 and st["token_refresh"] == 0,
                  f"S3: {gw.name} neither refreshes nor dispatches after revocation {st}")
        _log("S3: PASS — revocation is immediately visible to every warm replica")

        # S4: configuration removal on a freshly-started replica fails closed.
        _log("S4: start gw4 with the credential set removed from its configuration")
        removed = stack.root / "credential_sets_removed.json"
        removed.write_text(json.dumps({"other": json.loads(
            Path(stack.files["credential_sets_path"]).read_text())["other"]}))
        g4 = GatewayProcess(stack, "gw4",
                            env_overrides={"GATEWAY_HTTP_CREDENTIAL_SETS": str(removed)}).start()
        gateways.append(g4)
        # Re-enroll so the send reaches credential resolution (not a missing grant).
        with g1.client() as c1:
            cid2 = rt.phase_producer(c1, stack, "alice", "ses-mp4", "call-mp4-1")
            rt.phase_enroll(c1, stack, cid2, "alice")
        stack.state.reset_stats()
        with g4.client() as c4:
            r = _send(c4, stack, "alice")
        check(r.status_code != 200, f"S4: removed credential set fails closed ({r.status_code})")
        check("CREDENTIAL_SET_NOT_FOUND" in r.text,
              f"S4: names the missing set, never falls back ({r.text[:200]})")
        check(stack.state.stats["resource"] == 0, "S4: removed configuration dispatches nothing")
        _log("S4: PASS — configuration removal fails closed on a fresh replica")
    finally:
        for gw in gateways:
            gw.stop()


def main() -> int:
    if not __debug__:
        raise SystemExit("delegated-multiproc proof requires assertions enabled")
    fx.quiet_logs()
    try:
        fx._docker("ps")  # bounded liveness probe; fails fast on a wedged daemon
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None
    stack = FixtureStack()
    try:
        stack.start()
        _run(stack)
    except (AssertionError, RuntimeError) as exc:
        print(f"DELEGATED-MULTIPROC FAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        stack.stop()
    print("delegated-multiproc p5c: independent gateway processes against shared "
          "custody — cross-replica callback/refresh + cache miss, restart durability, "
          "revocation-dominates-warm-replicas, and configuration removal all passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
