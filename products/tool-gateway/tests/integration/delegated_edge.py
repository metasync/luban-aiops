"""SPEC-070 p6 — the real browser edge, over real TLS, against a real backend.

Where :mod:`delegated_runtime` (p5b) drives the *tool-gateway's* internal
authorization routes in process, and :mod:`delegated_multiproc` (p5c) drives
independent tool-gateway processes, this module proves the layer that only the
**platform-gateway browser edge** (``/api/v1/targets/authorizations``) adds — the
secret-safe, cookie-bound, browser-facing surface the plan calls out (§"Browser
and edge proof", line 186):

* a **real ``uvicorn`` platform-gateway process composed from env** and served
  over **generated TLS** (its own CA + server certificate), pointed at a **real
  tool-gateway process** (p5c's ``GatewayProcess``) over the fixture OAuth /
  JWKS / disposable Postgres stack — no mocks, no ASGI in-process shortcut, no
  dependency overrides;
* the browser-binding invariants, driven with **real cookie jars over the wire**:
  Authorize navigation, authorized return, a *different browser without the
  cookie* fails closed (and does not even consume the single-use handle), *same-
  browser tabs* (one jar, several concurrent challenges) all resolve, and
  *cookie expiry / logout* invalidates pending work;
* the **canceled** (provider denial) and **failed/expired** (spent-state replay)
  outcomes are bounded, non-authorized redirects that never reflect the
  provider's ``error_description``;
* **callback/start response bodies and headers** are verified over real TLS
  (bare 302s, ``no-store`` family, ``Secure``/``Max-Age=0`` cookie clearing, and
  an empty navigation body so no provider material reaches the SPA-visible
  response); and
* the **actual edge process logs** are captured and scanned: the navigation path
  is templated (``/start/{start_token}``) and *no* code, state, cookie secret,
  handle, or provider URL ever appears.

The real-browser UI screenshot matrix (the portal SPA rendering Authorize /
canceled / failed / expired / authorized-return / Continue) is the conditional
"once available" half of line 186: the fixtures pin the provider redirect to
``https://portal.test/...`` and the callback to the same host, which a real
browser cannot resolve without a host-override that is out of scope here. This
module therefore proves every edge invariant deterministically over real TLS at
the HTTP boundary the browser actually drives; see the SPEC-070 task matrix for
the explicit browser-UI limitation, recorded alongside DI-070/AAP.

Run::

    uv run --frozen --project products/tool-gateway \
        python products/tool-gateway/tests/integration/delegated_edge.py
"""
from __future__ import annotations

import asyncio
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx

import delegated_fixtures as fx
import delegated_multiproc as mp
import delegated_runtime as rt
from delegated_fixtures import (
    CALLBACK,
    IDENTITY_ISSUER,
    FixtureStack,
    check,
    mint_auth_workload,
)

ROOT = Path(__file__).resolve().parents[4]
EDGE_BASE = "/api/v1/targets/authorizations"
INTERNAL_BASE = "/api/v2/targets/authorizations"
COOKIE_PREFIX = "__Host-luban-oauth-"
NO_STORE = {"cache-control": "no-store", "pragma": "no-cache", "referrer-policy": "no-referrer"}
DENY_CANARY = "SECRET-CANARY-DENY-DESCRIPTION"
READY_TIMEOUT = 120.0


def _log(msg: str) -> None:
    print(f"[s70-edge] {msg}", flush=True)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# --- the real platform-gateway edge, served over generated TLS ---------------

class EdgeProcess:
    """A real ``uvicorn`` platform-gateway composed from env over generated TLS.

    The edge is launched in its *own* product venv (``uv run --project
    products/platform-gateway``) because the two gateway products do not share an
    interpreter. It serves HTTPS with a freshly generated CA + server certificate
    (independent of the fixture provider CA), so the harness's browser client
    verifies it with hostname and chain checks fully enabled. The edge's only
    outbound hop is the plain-loopback tool-gateway; it never dials the fixture
    provider itself (the simulated browser does), so it needs no fixture CA.

    The uvicorn access log is deliberately left **on**: ``protect_http_records()``
    installs a global ``LogRecord`` factory that templates the authorization
    request path and omits httpx/httpcore diagnostics, so the captured process
    log is the genuine article this module scans for secret leakage.
    """

    def __init__(self, stack: FixtureStack, tg_base_url: str, workload_path: str):
        self.stack = stack
        self.tg_base_url = tg_base_url
        self.workload_path = workload_path
        self.proc: subprocess.Popen | None = None
        self.base_url = ""
        self.ca_path = ""
        self._logfh = None
        self._tmp = tempfile.TemporaryDirectory(prefix="s70-edge-")

    def start(self) -> "EdgeProcess":
        root = Path(self._tmp.name)
        ca_key, ca_cert = fx.generate_ca()
        self.ca_path = str(root / "edge-ca.pem")
        Path(self.ca_path).write_bytes(fx._cert_pem(ca_cert))
        srv_key, srv_cert = fx.issue_server_cert(
            ca_key, ca_cert, hostnames=("localhost", "127.0.0.1"), ips=("127.0.0.1",))
        cert_path, key_path = fx.write_cert_pair(root, "edge", srv_key, srv_cert)

        port = _free_port()
        env = {
            **os.environ,
            "OTEL_ENABLED": "false",
            "PLATFORM_GATEWAY_TARGET_AUTHORIZATION_ENABLED": "true",
            "PLATFORM_GATEWAY_REQUIRE_AUTH": "true",
            "PLATFORM_GATEWAY_DELEGATION_AUDIENCE": "tool-gateway",
            "PLATFORM_GATEWAY_TOOL_GATEWAY_URL": self.tg_base_url,
            "PLATFORM_GATEWAY_AUTHORIZATION_WORKLOAD_TOKEN_PATH": self.workload_path,
            "IDENTITY_JWKS_URL": self.stack.jwks_url,
            "IDENTITY_TOKEN_ISSUER": IDENTITY_ISSUER,
        }
        self._logfh = tempfile.NamedTemporaryFile(  # noqa: SIM115 — dumped on failure
            prefix="s70-edge-log-", suffix=".log", delete=False, mode="w+b")
        cmd = [
            "uv", "run", "--frozen", "--project", "products/platform-gateway",
            "python", "-m", "uvicorn", "--factory", "platform_gateway.app:create_app",
            "--host", "127.0.0.1", "--port", str(port),
            "--ssl-keyfile", key_path, "--ssl-certfile", cert_path,
            "--log-level", "info",
        ]
        self.proc = subprocess.Popen(cmd, env=env, cwd=str(ROOT),
                                     stdout=self._logfh, stderr=subprocess.STDOUT)
        self.base_url = f"https://127.0.0.1:{port}"
        self._wait_ready()
        _log(f"real platform-gateway edge up at {self.base_url} (pid {self.proc.pid}, TLS)")
        return self

    def _wait_ready(self) -> None:
        deadline = time.monotonic() + READY_TIMEOUT
        last = ""
        while time.monotonic() < deadline:
            if self.proc is not None and self.proc.poll() is not None:
                raise RuntimeError(f"edge exited early ({self.proc.returncode})\n{self._tail()}")
            try:
                r = httpx.get(self.base_url + "/health/live", verify=self.ca_path, timeout=3.0)
                if r.status_code == 200:
                    return
                last = f"status {r.status_code}"
            except Exception as exc:  # noqa: BLE001 — not listening yet
                last = exc.__class__.__name__
            time.sleep(0.5)
        raise RuntimeError(f"edge not ready within {READY_TIMEOUT}s ({last})\n{self._tail()}")

    def _tail(self) -> str:
        try:
            self._logfh.flush()
            return Path(self._logfh.name).read_text(errors="replace")[-6000:]
        except Exception:  # noqa: BLE001
            return "<no edge log>"

    def read_log(self) -> str:
        try:
            self._logfh.flush()
            return Path(self._logfh.name).read_text(errors="replace")
        except Exception:  # noqa: BLE001
            return ""

    def get(self, path: str, *, cookie: str | None = None) -> httpx.Response:
        """One browser navigation. A fresh client per call models a browser whose
        cookie jar is exactly ``cookie`` — httpx then never merges a persisted
        jar cookie into a *second* ``Cookie`` header, which the edge's
        duplicate-jar guard would (correctly) reject."""
        headers = {"Cookie": cookie} if cookie else {}
        with httpx.Client(base_url=self.base_url, verify=self.ca_path,
                          follow_redirects=False, timeout=20.0) as client:
            return client.get(path, headers=headers)

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
        self._tmp.cleanup()


# --- small browser/backend helpers ------------------------------------------

def _cookie_header(jar: dict[str, str]) -> str:
    return "; ".join(f"{COOKIE_PREFIX}{name}={value}" for name, value in jar.items())


def _assert_no_store(response: httpx.Response, label: str) -> None:
    for name, value in NO_STORE.items():
        check(response.headers.get(name) == value,
              f"{label}: {name}={value} present (got {response.headers.get(name)!r})")


def _assert_no_secret(response: httpx.Response, label: str, secrets_: list[str]) -> None:
    blob = response.text + "".join(f"{k}\n{v}\n" for k, v in response.headers.items())
    for canary in secrets_:
        check(canary not in blob, f"{label}: response reflects no secret material ({canary[:8]}…)")


def _start_challenge(tgc, stack, user, session, call, canaries):
    """A real durable challenge (the producer seam) plus a single-use start handle
    at the tool-gateway that records the browser binding. ``secret`` is 43 chars of
    the urlsafe alphabet — exactly the edge's ``__Host-`` cookie-secret format."""
    cid = rt.phase_producer(tgc, stack, user, session, call)
    secret = secrets.token_urlsafe(32)
    r = tgc.post(f"{INTERNAL_BASE}/{cid}/start", json={"browser_secret": secret},
                 headers=rt.human(stack, user))
    check(r.status_code == 200, f"start handle: {r.status_code} {r.text}")
    handle = r.json()["start_token"]
    canaries.extend([cid, handle, secret])
    return cid, handle, secret


def _provider_navigate(stack, provider_url, user, *, denial=None):
    """Simulate the initiating browser following the edge's redirect to the real
    fixture provider. Returns ``(code_or_None, state)``."""
    url = (provider_url + f"&fixture_denial={denial}" if denial
           else provider_url + f"&fixture_user={user}")
    with stack.client() as http:
        nav = http.get(url)
    check(nav.status_code == 302, f"provider navigation: {nav.status_code}")
    qs = parse_qs(urlsplit(nav.headers["location"]).query)
    return (qs.get("code") or [None])[0], qs["state"][0]


# --- the proof ---------------------------------------------------------------

def prove(edge: EdgeProcess, tg, stack: FixtureStack) -> None:
    canaries = [stack.oauth_base, CALLBACK, DENY_CANARY]
    tgc = tg.client()

    # ---- E1: Authorize navigation over real TLS (browser A, correct cookie) ----
    cid, handle, secret = _start_challenge(tgc, stack, "alice", "ses-edge-1", "call-edge-1", canaries)
    jar_a = _cookie_header({cid: secret})
    before = dict(stack.state.stats)
    r = edge.get(f"{EDGE_BASE}/start/{handle}", cookie=jar_a)
    check(r.status_code == 302, f"E1 authorize: 302, got {r.status_code}")
    provider_url = r.headers["location"]
    check(provider_url.startswith(stack.oauth_base + "/authorize?"),
          "E1 authorize: the edge redirects the browser to the real fixture provider over TLS")
    _assert_no_store(r, "E1 authorize")
    check(r.content == b"",
          "E1 authorize: navigation body is empty — provider material never reaches the SPA-visible body")
    check(stack.state.stats["authorize"] == before["authorize"],
          "E1 authorize: the edge only builds the provider URL; the browser contacts the provider")
    canaries.append(provider_url)
    _log("E1: Authorize navigation over real TLS -> 302 to the fixture provider, no-store, empty body")

    # The initiating browser follows the redirect; the provider issues a code.
    code, state = _provider_navigate(stack, provider_url, "alice")
    check(code and state, "E1: the provider returned a code + state to the exact callback")
    canaries.extend([code, state])
    check(stack.state.stats["authorize"] == before["authorize"] + 1, "E1: exactly one real provider authorize")

    # ---- E2: authorized return via the edge callback (browser A cookie) ----
    r = edge.get(f"{EDGE_BASE}/callback?code={code}&state={state}", cookie=jar_a)
    check(r.status_code == 302, f"E2 return: 302, got {r.status_code}")
    check(r.headers["location"] == f"/authorizations/return/{cid}",
          f"E2 return: server-chosen portal return path, got {r.headers['location']}")
    set_cookie = r.headers.get("set-cookie", "")
    check(f"{COOKIE_PREFIX}{cid}" in set_cookie and "Max-Age=0" in set_cookie and "Secure" in set_cookie,
          f"E2 return: the binding cookie is cleared (Secure, Max-Age=0), got {set_cookie!r}")
    _assert_no_store(r, "E2 return")
    check(r.content == b"", "E2 return: callback body empty")
    _assert_no_secret(r, "E2 return", [code, state, secret, handle])
    r = tgc.get(f"{INTERNAL_BASE}/{cid}", headers=rt.human(stack, "alice"))
    check(r.status_code == 200 and r.json().get("status") == "authorized",
          f"E2 return: backend status authorized, got {r.text[:160]}")
    _log("E2: authorized return over real TLS -> 302 to the portal path, cookie cleared, no secret reflected")

    # ---- E3: a different browser without the cookie fails, handle unconsumed ----
    # E1/E2 enrolled alice, so the binding/negative phases use bob — an owner who
    # is never enrolled here, so the producer still mints a fresh durable challenge.
    cid2, handle2, secret2 = _start_challenge(tgc, stack, "bob", "ses-edge-2", "call-edge-2", canaries)
    before = dict(stack.state.stats)
    r = edge.get(f"{EDGE_BASE}/start/{handle2}")  # browser B: NO cookie
    check(r.status_code == 302 and r.headers["location"] == "/",
          f"E3 no-cookie: a browser without the binding cookie is bare-redirected to '/', got {r.headers.get('location')}")
    check(r.content == b"", "E3 no-cookie: empty body")
    _assert_no_store(r, "E3 no-cookie")
    check(stack.state.stats["authorize"] == before["authorize"], "E3 no-cookie: no provider contact")
    # The handle was never consumed: the cookie-holding browser still authorizes.
    r = edge.get(f"{EDGE_BASE}/start/{handle2}", cookie=_cookie_header({cid2: secret2}))
    check(r.status_code == 302 and r.headers["location"].startswith(stack.oauth_base + "/authorize?"),
          "E3 no-cookie: the same handle still works for the cookie-holding browser — the cookie is the binding proof")
    _log("E3: a different browser without the cookie fails closed and does not consume the handle")

    # ---- E4: same-browser tabs work (one jar, two concurrent challenges) ----
    cid3, handle3, secret3 = _start_challenge(tgc, stack, "bob", "ses-edge-3", "call-edge-3", canaries)
    cid4, handle4, secret4 = _start_challenge(tgc, stack, "bob", "ses-edge-4", "call-edge-4", canaries)
    jar_tabs = _cookie_header({cid3: secret3, cid4: secret4})
    for label, tab_handle in (("tab-1", handle3), ("tab-2", handle4)):
        r = edge.get(f"{EDGE_BASE}/start/{tab_handle}", cookie=jar_tabs)
        check(r.status_code == 302 and r.headers["location"].startswith(stack.oauth_base + "/authorize?"),
              f"E4 same-browser {label}: one jar carries multiple concurrent tabs "
              f"({r.status_code} {r.headers.get('location')})")
    _log("E4: same-browser tabs (one cookie jar, two live challenges) both navigate")

    # ---- E5: cookie expiry / logout invalidates pending work ----
    cid5, handle5, secret5 = _start_challenge(tgc, stack, "bob", "ses-edge-5", "call-edge-5", canaries)
    before = dict(stack.state.stats)
    stale = secrets.token_urlsafe(32)
    canaries.append(stale)
    r = edge.get(f"{EDGE_BASE}/start/{handle5}", cookie=_cookie_header({cid5: stale}))
    check(r.status_code == 302 and r.headers["location"] == "/",
          f"E5 expired-cookie: a stale/cleared binding cannot resume pending work, got {r.headers.get('location')}")
    check(stack.state.stats["authorize"] == before["authorize"], "E5 expired-cookie: no provider contact")
    r = edge.get(f"{EDGE_BASE}/start/{handle5}")  # logged out: no cookie at all
    check(r.status_code == 302 and r.headers["location"] == "/",
          "E5 logout: a logged-out browser (no cookie) cannot resume pending work")
    _log("E5: cookie expiry/logout invalidates pending work (fail-closed, no provider contact)")

    # ---- E6: canceled state (provider denial) never reflects the description ----
    cid6, handle6, secret6 = _start_challenge(tgc, stack, "bob", "ses-edge-6", "call-edge-6", canaries)
    jar6 = _cookie_header({cid6: secret6})
    r = edge.get(f"{EDGE_BASE}/start/{handle6}", cookie=jar6)
    provider6 = r.headers["location"]
    canaries.append(provider6)
    _err, state6 = _provider_navigate(stack, provider6, "alice", denial="access_denied")
    canaries.append(state6)
    r = edge.get(f"{EDGE_BASE}/callback?error=access_denied&error_description={DENY_CANARY}&state={state6}",
                 cookie=jar6)
    check(r.status_code == 302, f"E6 canceled: 302, got {r.status_code}")
    check(r.headers["location"] in (f"/authorizations/return/{cid6}", "/"),
          f"E6 canceled: bounded non-authorized redirect, got {r.headers['location']}")
    check(r.content == b"", "E6 canceled: empty body")
    _assert_no_secret(r, "E6 canceled", [DENY_CANARY, "access_denied", state6])
    _assert_no_store(r, "E6 canceled")
    r = tgc.get(f"{INTERNAL_BASE}/{cid6}", headers=rt.human(stack, "bob"))
    check(r.json().get("status") != "authorized", f"E6 canceled: backend is not authorized, got {r.text[:160]}")
    _log("E6: canceled (provider denial) -> bounded redirect, error_description never reflected")

    # ---- E7: failed/expired — a spent callback state is a safe non-authorized '/' ----
    r = edge.get(f"{EDGE_BASE}/callback?code={code}&state={state}", cookie=jar_a)
    check(r.status_code == 302 and r.headers["location"] == "/",
          f"E7 replay: a spent/expired state is a safe '/' outcome, never re-authorizes, got {r.headers.get('location')}")
    check(r.content == b"", "E7 replay: empty body")
    _assert_no_secret(r, "E7 replay", [code, state])
    _assert_no_store(r, "E7 replay")
    _log("E7: failed/expired (spent-state replay) -> safe '/' outcome, no re-authorization")

    # ---- E8: inspect the real edge process logs ----
    log = edge.read_log()
    check(bool(log), "E8 logs: captured the real edge process log")
    check(f"{EDGE_BASE}/start/{{start_token}}" in log,
          "E8 logs: the edge logs the templated navigation path")
    leaked = [c for c in canaries if c and c in log]
    check(not leaked, f"E8 logs: real edge log leaks no provider/cookie/handle material ({[c[:8] for c in leaked]})")
    _log("E8: real edge process logs are secret-safe (templated paths, zero canary leakage)")


def main() -> int:
    if not __debug__:
        raise SystemExit("delegated-edge proof requires assertions enabled")
    fx.quiet_logs()
    try:
        fx._docker("ps")  # bounded liveness probe; fails fast on a wedged daemon
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None
    stack = FixtureStack()
    tg = None
    edge = None
    try:
        stack.start()
        asyncio.run(rt._provision(stack))
        tg = mp.GatewayProcess(stack, "edge-backend").start()
        # The edge reads its authorization-handoff workload bearer from a mounted
        # file (never a command argument or env value); the tool-gateway verifies
        # it against the fixture JWKS exactly as it does the in-process harness's.
        workload = Path(stack.root) / "edge-workload.jwt"
        workload.write_text(mint_auth_workload(stack.signing_key, exp=int(time.time()) + 3600))
        edge = EdgeProcess(stack, tg.base_url, str(workload)).start()
        prove(edge, tg, stack)
    except (AssertionError, RuntimeError) as exc:
        print(f"DELEGATED-EDGE FAILED: {exc}", file=sys.stderr)
        if edge is not None and (tail := edge._tail()):
            print("--- edge log tail ---\n" + tail, file=sys.stderr)
        return 1
    finally:
        if edge is not None:
            edge.stop()
        if tg is not None:
            tg.stop()
        stack.stop()
    print("delegated-edge p6: the real platform-gateway browser edge over real TLS — "
          "Authorize navigation, authorized return, different-browser-without-cookie, "
          "same-browser tabs, cookie expiry/logout, canceled + failed/expired states, "
          "and secret-safe real edge logs all passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
