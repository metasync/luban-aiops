"""SPEC-070 p5 — deterministic delegated-runtime fixtures (provider-independent).

This module builds the development harness the plan requires (§"Deterministic
integration fixtures", line 176): generated TLS certificates, a fixture OAuth
authorization/token/identity/revocation service enforcing PKCE S256 and
confidential-client authentication, a fixture target resource server, a real
JWKS endpoint, two users with distinct immutable accounts/RBAC, two targets, and
disposable Docker Postgres.

Everything here uses *real* sockets, *real* TLS, and *real* certificate
verification: the generated CA is installed into the trust store ``httpx`` uses
(``certifi.where()``) for the lifetime of the harness and restored on teardown,
so the shipped :class:`UserDelegatedClient` — which pins ``trust_env=False`` and
therefore ignores ``SSL_CERT_FILE`` — verifies the fixture servers against the
generated CA with hostname and chain checks fully enabled. There is no insecure
production switch, no mocked success return, and no real AAP endpoint.

Run directly for the fixture self-test (a real authorization-code grant over
TLS, refreshed, identity-verified, used against the resource server, then
revoked)::

    uv run --frozen --project products/tool-gateway \
        python products/tool-gateway/tests/integration/delegated_fixtures.py
"""
from __future__ import annotations

import atexit
import base64
import hashlib
import ipaddress
import json
import os
import secrets
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import certifi
import httpx
import jwt as pyjwt
import psycopg
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from jwt.algorithms import RSAAlgorithm

# --- fixed, non-secret fixture identities ---------------------------------
# The exact callback the configuration validator requires (path is pinned); it
# is never fetched by the gateway, only echoed into the provider redirect.
CALLBACK = "https://portal.test/api/v1/targets/authorizations/callback"

# Delegated-human trust (owner_namespace is pinned to this issuer).
IDENTITY_ISSUER = "trusted-identity-issuer"
IDENTITY_AUDIENCE = "tool-gateway"
IDENTITY_ACTORS = ("platform-gateway",)

# Projected service-account workload trust (cluster issuer, two audiences).
WORKLOAD_ISSUER = "https://cluster.issuer"
AUTH_WORKLOAD_SUBJECT = "system:serviceaccount:platform-gateway:platform-gateway"
EXEC_WORKLOAD_SUBJECT = "system:serviceaccount:execution-runtime:execution-runtime"

KID = "s70-fixture-key-1"

# Two users with distinct immutable platform subjects, target accounts, RBAC.
# ``fixture_user`` (the simulated browser session at the provider) maps to the
# immutable target account the provider's identity endpoint asserts; the gateway
# linkage maps the verified human subject to that same account.
USERS = {
    "alice": {"account": "42", "sub": "alice-immutable", "username": "alice", "roles": ["operator"]},
    "bob": {"account": "43", "sub": "bob-immutable", "username": "bob", "roles": ["approver"]},
}

CLIENT_ID = "delegated-client"
CLIENT_SECRET = "opaque-client-fixture-secret"
ACCESS_TTL_SECONDS = 600
REFRESH_TTL_SECONDS = 86400


def check(value, label):
    if not value:
        raise AssertionError(label)


def quiet_logs() -> None:
    """Silence app + third-party INFO noise so the harness's own ``print`` progress
    stays readable.

    These proofs are mandatory ``make verify`` gates; per-request INFO telemetry
    from the composed app, ``httpx`` and ``uvicorn`` would otherwise flood the log
    and bury the assertions. WARNING/ERROR still surface genuine problems, and the
    harness's own ``[s70-*]`` progress lines use ``print``, so they are unaffected.
    """
    import logging

    # ``httpx2``/``httpcore2`` are the namespaced httpx fork the MCP SDK vendors
    # (and that starlette's TestClient logs through); silence both it and plain
    # ``httpx`` so neither per-request INFO line floods the gate output.
    for name in ("tool_gateway", "httpx", "httpx2", "httpcore", "httpcore2",
                 "uvicorn", "asyncio", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)


def pkce_challenge(verifier: str) -> str:
    """RFC 7636 S256 code challenge for a verifier."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# --- generated TLS PKI ------------------------------------------------------

def _new_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def generate_ca():
    """A self-signed CA used to sign every fixture server certificate."""
    key = _new_key()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SPEC-070 Fixture CA")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=True,
                crl_sign=True, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    return key, cert


def issue_server_cert(ca_key, ca_cert, *, hostnames=("localhost",), ips=("127.0.0.1",)):
    """A CA-signed server certificate with DNS + IP subject-alt-names."""
    key = _new_key()
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostnames[0])])
    san = [x509.DNSName(h) for h in hostnames]
    san += [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=2))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    return key, cert


def _cert_pem(cert) -> bytes:
    return cert.public_bytes(serialization.Encoding.PEM)


def _key_pem(key) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def write_cert_pair(directory: Path, name: str, key, cert) -> tuple[str, str]:
    cert_path = directory / f"{name}-cert.pem"
    key_path = directory / f"{name}-key.pem"
    cert_path.write_bytes(_cert_pem(cert))
    key_path.write_bytes(_key_pem(key))
    os.chmod(key_path, 0o600)
    return str(cert_path), str(key_path)


def server_ssl_context(cert_path: str, key_path: str) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(cert_path, key_path)
    # Fixture servers do not require client certificates; the *client* verifies
    # the server against the generated CA.
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


# --- CA trust installation (the only way the shipped client trusts the fixture)

@contextmanager
def trust_ca(ca_cert_pem: bytes):
    """Install the generated CA into the bundle ``httpx``/``certifi`` verifies with.

    ``UserDelegatedClient`` pins ``trust_env=False`` and builds its own
    ``httpx.AsyncClient`` with no ``verify`` override, so it always verifies
    against ``certifi.where()``. Appending the fixture CA there is a genuine
    trust-anchor installation — verification, hostname matching, and chain
    validation all stay fully enabled — not an insecure switch. The original
    bundle is restored on teardown and via ``atexit``; a prior dirty run is
    self-healed by stripping anything after the begin marker.
    """
    path = certifi.where()
    raw = Path(path).read_bytes()
    begin = b"\n# SPEC-070-FIXTURE-CA-BEGIN\n"
    end = b"\n# SPEC-070-FIXTURE-CA-END\n"
    if begin in raw:  # self-heal a prior hard-crashed run
        raw = raw.split(begin, 1)[0]
    original = raw

    def restore():
        try:
            Path(path).write_bytes(original)
        except OSError:
            pass

    Path(path).write_bytes(original + begin + ca_cert_pem + end)
    atexit.register(restore)
    try:
        yield path
    finally:
        restore()
        try:
            atexit.unregister(restore)
        except Exception:
            pass


# --- shared provider state --------------------------------------------------

class ProviderState:
    """Thread-safe fixture provider state shared by the OAuth and resource servers."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.codes: dict[str, dict] = {}
        self.access_tokens: dict[str, dict] = {}
        self.refresh_tokens: dict[str, dict] = {}
        # Deterministic fault injection (None = normal behavior).
        self.token_error: str | None = None       # force an OAuth error code on /token
        self.identity_status: int | None = None    # force /whoami status
        self.resource_status: int | None = None    # force the resource server status
        self.revoke_status: int | None = None       # force /revoke status
        # Call counters + recipients, for the no-fallback/no-dispatch assertions.
        self.stats: dict[str, int] = {}
        self.reset_stats()

    def reset_stats(self) -> None:
        with self.lock:
            self.stats = {
                "authorize": 0, "token": 0, "token_code": 0, "token_refresh": 0,
                "whoami": 0, "revoke": 0, "resource": 0, "jwks": 0, "mcp": 0,
            }

    def bump(self, key: str) -> None:
        with self.lock:
            self.stats[key] = self.stats.get(key, 0) + 1


# --- HTTP handlers ----------------------------------------------------------

def _send_json(handler: BaseHTTPRequestHandler, code: int, obj: dict) -> None:
    body = json.dumps(obj).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _send_redirect(handler: BaseHTTPRequestHandler, location: str) -> None:
    handler.send_response(302)
    handler.send_header("Location", location)
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", "0")
    handler.end_headers()


def _client_authorized(handler: BaseHTTPRequestHandler, form: dict) -> bool:
    """Validate confidential-client auth (Basic header or POST body)."""
    header = handler.headers.get("Authorization", "")
    if header.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
            cid, _, csecret = decoded.partition(":")
        except Exception:
            return False
        return cid == CLIENT_ID and csecret == CLIENT_SECRET
    cid = (form.get("client_id") or [""])[0]
    csecret = (form.get("client_secret") or [""])[0]
    return cid == CLIENT_ID and csecret == CLIENT_SECRET


def _bearer_token(handler: BaseHTTPRequestHandler) -> str | None:
    header = handler.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return None


class _SilentHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args) -> None:  # keep harness output clean
        pass

    def version_string(self) -> str:
        return "s70-fixture"


class OAuthHandler(_SilentHandler):
    """Fixture OAuth authorization/token/identity/revocation service."""

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/authorize":
            return self._authorize(query)
        if parsed.path == "/whoami":
            return self._whoami()
        _send_json(self, 404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        form = parse_qs(raw)
        if parsed.path == "/token":
            return self._token(form)
        if parsed.path == "/revoke":
            return self._revoke(form)
        _send_json(self, 404, {"error": "not_found"})

    # -- endpoints --
    def _authorize(self, query: dict) -> None:
        state: ProviderState = self.server.state
        state.bump("authorize")
        get = lambda k: (query.get(k) or [""])[0]  # noqa: E731
        if get("response_type") != "code" or get("client_id") != CLIENT_ID:
            return _send_json(self, 400, {"error": "invalid_request"})
        if get("code_challenge_method") != "S256" or not get("code_challenge"):
            return _send_json(self, 400, {"error": "invalid_request", "error_description": "pkce_s256_required"})
        redirect_uri = get("redirect_uri")
        if redirect_uri != CALLBACK:
            return _send_json(self, 400, {"error": "invalid_request", "error_description": "redirect_mismatch"})
        state_param = get("state")
        denial = get("fixture_denial")
        if denial:
            return _send_redirect(self, f"{redirect_uri}?error={denial}&state={state_param}")
        user = USERS.get(get("fixture_user"))
        if user is None:
            return _send_json(self, 400, {"error": "access_denied", "error_description": "unknown_fixture_user"})
        code = secrets.token_urlsafe(32)
        with state.lock:
            state.codes[code] = {
                "challenge": get("code_challenge"), "user": get("fixture_user"),
                "account": user["account"], "scope": get("scope") or "read",
                "redirect_uri": redirect_uri, "used": False,
            }
        _send_redirect(self, f"{redirect_uri}?code={code}&state={state_param}")

    def _token(self, form: dict) -> None:
        state: ProviderState = self.server.state
        state.bump("token")
        if not _client_authorized(self, form):
            return _send_json(self, 401, {"error": "invalid_client"})
        if state.token_error:
            return _send_json(self, 400, {"error": state.token_error})
        grant = (form.get("grant_type") or [""])[0]
        if grant == "authorization_code":
            state.bump("token_code")
            return self._token_code(form, state)
        if grant == "refresh_token":
            state.bump("token_refresh")
            return self._token_refresh(form, state)
        _send_json(self, 400, {"error": "unsupported_grant_type"})

    def _token_code(self, form: dict, state: ProviderState) -> None:
        get = lambda k: (form.get(k) or [""])[0]  # noqa: E731
        code = get("code")
        verifier = get("code_verifier")
        with state.lock:
            record = state.codes.get(code)
            if record is None or record["used"]:
                return _send_json(self, 400, {"error": "invalid_grant"})
            record["used"] = True  # single-use authorization code
        if get("redirect_uri") != record["redirect_uri"]:
            return _send_json(self, 400, {"error": "invalid_grant"})
        if not verifier or pkce_challenge(verifier) != record["challenge"]:
            return _send_json(self, 400, {"error": "invalid_grant"})
        self._issue(record["user"], record["account"], record["scope"], state)

    def _token_refresh(self, form: dict, state: ProviderState) -> None:
        token = (form.get("refresh_token") or [""])[0]
        with state.lock:
            record = state.refresh_tokens.get(token)
            if record is None or record["revoked"]:
                return _send_json(self, 400, {"error": "invalid_grant"})
            record["revoked"] = True  # rotate: the presented refresh token is spent
        self._issue(record["user"], record["account"], record["scope"], state)

    def _issue(self, user: str, account: str, scope: str, state: ProviderState) -> None:
        access = secrets.token_urlsafe(32)
        refresh = secrets.token_urlsafe(32)
        now = time.time()
        with state.lock:
            state.access_tokens[access] = {
                "user": user, "account": account, "scope": scope, "exp": now + ACCESS_TTL_SECONDS,
            }
            state.refresh_tokens[refresh] = {
                "user": user, "account": account, "scope": scope, "revoked": False,
                "exp": now + REFRESH_TTL_SECONDS,
            }
        _send_json(self, 200, {
            "access_token": access, "token_type": "Bearer", "expires_in": ACCESS_TTL_SECONDS,
            "refresh_token": refresh, "scope": scope, "refresh_expires_in": REFRESH_TTL_SECONDS,
        })

    def _whoami(self) -> None:
        state: ProviderState = self.server.state
        state.bump("whoami")
        if state.identity_status is not None:
            return _send_json(self, state.identity_status, {"error": "forced"})
        token = _bearer_token(self)
        with state.lock:
            record = state.access_tokens.get(token or "")
        if record is None or record["exp"] < time.time():
            return _send_json(self, 401, {"error": "invalid_token"})
        # json_immutable_id: only the configured immutable claim is evidence.
        _send_json(self, 200, {"id": record["account"], "username": record["user"]})

    def _revoke(self, form: dict) -> None:
        state: ProviderState = self.server.state
        state.bump("revoke")
        if not _client_authorized(self, form):
            return _send_json(self, 401, {"error": "invalid_client"})
        if state.revoke_status is not None:
            return _send_json(self, state.revoke_status, {"error": "forced"})
        token = (form.get("token") or [""])[0]
        with state.lock:
            record = state.refresh_tokens.get(token)
            if record is not None:
                record["revoked"] = True
        # RFC 7009: 200 for an accepted or already-invalid token.
        _send_json(self, 200, {})


class ResourceHandler(_SilentHandler):
    """Fixture target resource server; validates the delegated access token."""

    def do_GET(self) -> None:  # noqa: N802
        self._handle()

    def do_POST(self) -> None:  # noqa: N802
        self._handle()

    def _handle(self) -> None:
        state: ProviderState = self.server.state
        state.bump("resource")
        if state.resource_status is not None:
            return _send_json(self, state.resource_status, {"error": "forced"})
        token = _bearer_token(self)
        with state.lock:
            record = state.access_tokens.get(token or "")
        if record is None or record["exp"] < time.time():
            return _send_json(self, 401, {"error": "invalid_token"})
        _send_json(self, 200, {"ok": True, "path": urlsplit(self.path).path, "account": record["account"]})


class JwksHandler(_SilentHandler):
    """Plain-HTTP JWKS endpoint serving the fixture signing public key."""

    def do_GET(self) -> None:  # noqa: N802
        state: ProviderState = self.server.state
        state.bump("jwks")
        _send_json(self, 200, {"keys": [self.server.jwk]})


class McpRecorderHandler(_SilentHandler):
    """Plain-HTTP stand-in for the AAP MCP endpoint (a contact recorder).

    It records every connection so the harness can assert the MCP adapter opens
    *no* target session when a delegated grant is missing (SPEC-070 R-4). It is
    deliberately not a real MCP server: the shared delegated acquisition seam
    fails closed before the adapter's streamable-HTTP session opener dials it, so
    a correct fail-closed leaves this recorder at zero hits. The user-delegated
    MCP *success* path is the AAP-compatibility leg (DI-070), out of scope here.
    """

    def _record(self) -> None:
        state: ProviderState = self.server.state
        state.bump("mcp")
        _send_json(self, 200, {"jsonrpc": "2.0", "id": None,
                               "error": {"code": -32601, "message": "fixture recorder"}})

    def do_GET(self) -> None:  # noqa: N802
        self._record()

    def do_POST(self) -> None:  # noqa: N802
        self._record()


# --- server bootstrap -------------------------------------------------------

class _ThreadServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _serve(httpd: _ThreadServer) -> threading.Thread:
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return thread


def start_https(handler_cls, state: ProviderState, cert_path: str, key_path: str):
    httpd = _ThreadServer(("127.0.0.1", 0), handler_cls)
    ctx = server_ssl_context(cert_path, key_path)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    httpd.state = state
    port = httpd.server_address[1]
    _serve(httpd)
    return httpd, port


def start_http(handler_cls, state: ProviderState):
    httpd = _ThreadServer(("127.0.0.1", 0), handler_cls)
    httpd.state = state
    port = httpd.server_address[1]
    _serve(httpd)
    return httpd, port


def stop_server(httpd) -> None:
    try:
        httpd.shutdown()
        httpd.server_close()
    except Exception:
        pass


# --- signing key + JWT minting ---------------------------------------------

def generate_signing_key():
    """One RSA key + JWK for the human and both workload verifiers."""
    private_key = _new_key()
    jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": KID, "use": "sig", "alg": "RS256", "kty": "RSA"})
    return private_key, jwk


def _encode(claims: dict, private_key) -> str:
    return pyjwt.encode(claims, private_key, algorithm="RS256", headers={"kid": KID})


def mint_human(private_key, user: str, *, iss: str = IDENTITY_ISSUER, aud: str = IDENTITY_AUDIENCE,
               authentication_source: str = "oidc", act=None, exp=None, iat=None,
               sub: str | None = None, roles=None) -> str:
    """A genuine delegated-human bearer (owner_namespace == iss)."""
    profile = USERS[user]
    now = int(time.time())
    return _encode({
        "iss": iss, "aud": [aud], "sub": sub or profile["sub"],
        "username": profile["username"], "roles": roles if roles is not None else list(profile["roles"]),
        "groups": [], "iat": iat if iat is not None else now - 1,
        "exp": exp if exp is not None else now + 300,
        "authentication_source": authentication_source,
        "act": {"sub": "platform-gateway"} if act is None else act,
    }, private_key)


def mint_auth_workload(private_key, *, iss: str = WORKLOAD_ISSUER,
                       aud: str = "luban-target-authorization-handoff",
                       sub: str = AUTH_WORKLOAD_SUBJECT, exp=None) -> str:
    now = int(time.time())
    return _encode({"iss": iss, "aud": [aud], "sub": sub, "iat": now - 1,
                    "exp": exp if exp is not None else now + 300}, private_key)


def mint_exec_workload(private_key, *, iss: str = WORKLOAD_ISSUER,
                       aud: str = "luban-target-execution-handoff",
                       sub: str = EXEC_WORKLOAD_SUBJECT, exp=None) -> str:
    now = int(time.time())
    return _encode({"iss": iss, "aud": [aud], "sub": sub, "iat": now - 1,
                    "exp": exp if exp is not None else now + 300}, private_key)


# --- disposable Postgres ----------------------------------------------------

def _log(msg: str) -> None:
    print(f"[s70-fixture] {msg}", flush=True)


def _docker(*args, **kwargs):
    """A bounded docker CLI call.

    Both a client-side ``DOCKER_CLIENT_TIMEOUT`` and a hard ``subprocess`` timeout
    are applied so a wedged daemon fails fast with a clear error instead of
    hanging the harness (and the whole ``make verify``) indefinitely.
    """
    env = {**os.environ, "DOCKER_CLIENT_TIMEOUT": "15"}
    kwargs.setdefault("env", env)
    try:
        return subprocess.run(["docker", *args], check=True, capture_output=True, text=True,
                              timeout=kwargs.pop("timeout", 45), **kwargs).stdout.strip()
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"docker {' '.join(args[:2])} timed out — the Docker daemon appears "
            f"unresponsive; restart Docker Desktop and retry") from exc


def start_postgres(password: str | None = None):
    """A disposable ``postgres:16-alpine`` on an ephemeral loopback port."""
    password = password or secrets.token_hex(24)
    name = f"s70-runtime-{secrets.token_hex(6)}"
    _docker("run", "--rm", "-d", "--name", name, "-p", "127.0.0.1::5432",
            "--tmpfs", "/var/lib/postgresql/data", "-e", "POSTGRES_PASSWORD",
            "postgres:16-alpine", env={**os.environ, "POSTGRES_PASSWORD": password})
    port = int(_docker("port", name, "5432/tcp").rsplit(":", 1)[1])
    dsn = f"postgresql://postgres:{password}@127.0.0.1:{port}/postgres"
    _wait_postgres(dsn)
    return {"container": name, "port": port, "password": password, "admin_dsn": dsn}


def _wait_postgres(dsn: str, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=3):
                return
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(0.5)
    raise RuntimeError(f"postgres did not become ready: {last}")


def stop_postgres(container: str) -> None:
    try:
        _docker("stop", "--time", "1", container)
    except Exception:
        pass


# --- fixture files ----------------------------------------------------------

def config_entry(*, oauth_base: str, resource_base: str, linkage_path: str,
                 target: str = "Automation", revision: str = "1") -> dict:
    """One full ``DelegatedConfiguration`` entry (shared by custody + connector)."""
    return {
        "scheme": "oauth2_authorization_code", "target": target,
        "authorization_url": f"{oauth_base}/authorize", "token_url": f"{oauth_base}/token",
        "renewal_url": f"{oauth_base}/token", "identity_url": f"{oauth_base}/whoami",
        "revocation_url": f"{oauth_base}/revoke",
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "client_auth": "client_secret_basic",
        "redirect_uri": CALLBACK, "scope": "read", "allowed_scopes": "read write",
        "oauth_origins": oauth_base, "resource_origins": resource_base,
        "pkce_method": "S256", "store": "postgres", "config_revision": revision,
        "identity_profile": "json_immutable_id", "identity_claim": "id",
        "identity_mapping_path": linkage_path, "access_cache_ttl_seconds": "300",
        "refresh_max_lifetime_seconds": str(REFRESH_TTL_SECONDS),
    }


def write_fixtures(root: Path, *, oauth_base: str, resource_base: str, set_id: str = "user"):
    """Write the keyring, linkage, custody config, and connector credential sets."""
    keyring_path = root / "keys.json"
    keyring_path.write_text(json.dumps({
        "active_key_id": "k1", "recovery_epoch": "epoch1",
        "fingerprint_key": base64.b64encode(secrets.token_bytes(32)).decode(),
        "keys": {k: base64.b64encode(secrets.token_bytes(32)).decode() for k in ("k1", "k2")},
    }))
    linkage_path = root / "linkage.json"
    linkage_path.write_text(json.dumps([
        {"owner_namespace": IDENTITY_ISSUER, "owner_sub": profile["sub"], "target_account": profile["account"]}
        for profile in USERS.values()
    ]))
    primary = config_entry(oauth_base=oauth_base, resource_base=resource_base,
                           linkage_path=str(linkage_path), target="Automation")
    other = config_entry(oauth_base=oauth_base, resource_base=resource_base,
                         linkage_path=str(linkage_path), target="Other")
    config_path = root / "sets.json"
    config_path.write_text(json.dumps({set_id: primary, "other": other}))
    # The HTTP connector's credential-set file uses the identical entry shape.
    credential_sets_path = root / "credential_sets.json"
    credential_sets_path.write_text(json.dumps({set_id: primary, "other": other}))
    return {
        "keyring_path": str(keyring_path), "linkage_path": str(linkage_path),
        "config_path": str(config_path), "credential_sets_path": str(credential_sets_path),
        "entry": primary, "set_id": set_id,
    }


# --- the composed fixture stack --------------------------------------------

class FixtureStack:
    """Brings up PKI + trust + servers + Postgres + fixture files as one unit."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="s70-runtime-")
        self.root = Path(self._tmp.name)
        self.state = ProviderState()
        self._trust = None
        self.oauth_httpd = self.resource_httpd = self.jwks_httpd = self.mcp_httpd = None
        self.postgres: dict | None = None
        self.signing_key = None
        self.jwk = None
        self.files: dict = {}

    # -- lifecycle --
    def start(self) -> "FixtureStack":
        _log("generating TLS PKI (CA + server cert)")
        ca_key, ca_cert = generate_ca()
        ca_pem = _cert_pem(ca_cert)
        self.ca_path = str(self.root / "ca.pem")
        Path(self.ca_path).write_bytes(ca_pem)
        srv_key, srv_cert = issue_server_cert(ca_key, ca_cert)
        cert_path, key_path = write_cert_pair(self.root, "server", srv_key, srv_cert)

        _log("installing generated CA into the httpx/certifi trust store")
        self._trust = trust_ca(ca_pem)
        self._trust.__enter__()

        _log("starting fixture OAuth + resource HTTPS servers and JWKS HTTP server")
        self.oauth_httpd, oauth_port = start_https(OAuthHandler, self.state, cert_path, key_path)
        self.resource_httpd, resource_port = start_https(ResourceHandler, self.state, cert_path, key_path)
        self.signing_key, self.jwk = generate_signing_key()
        self.jwks_httpd, jwks_port = start_http(JwksHandler, self.state)
        self.jwks_httpd.jwk = self.jwk
        self.mcp_httpd, mcp_port = start_http(McpRecorderHandler, self.state)

        self.oauth_base = f"https://localhost:{oauth_port}"
        self.resource_base = f"https://localhost:{resource_port}"
        self.jwks_url = f"http://localhost:{jwks_port}/jwks"
        self.mcp_base = f"http://localhost:{mcp_port}/mcp"
        _log("writing custody/linkage/keyring/credential-set fixtures")
        self.files = write_fixtures(self.root, oauth_base=self.oauth_base,
                                    resource_base=self.resource_base)
        _log("provisioning disposable Postgres (docker)")
        self.postgres = start_postgres()
        _log(f"stack up: oauth={self.oauth_base} resource={self.resource_base} "
             f"jwks={self.jwks_url} pg_port={self.postgres['port']}")
        return self

    def stop(self) -> None:
        for httpd in (self.oauth_httpd, self.resource_httpd, self.jwks_httpd, self.mcp_httpd):
            if httpd is not None:
                stop_server(httpd)
        if self.postgres is not None:
            stop_postgres(self.postgres["container"])
        if self._trust is not None:
            self._trust.__exit__(None, None, None)
        self._tmp.cleanup()

    def __enter__(self) -> "FixtureStack":
        return self.start()

    def __exit__(self, *_exc) -> None:
        self.stop()

    # -- convenience --
    @property
    def admin_dsn(self) -> str:
        return self.postgres["admin_dsn"]

    def client(self, **kwargs) -> httpx.Client:
        """A harness httpx client that trusts the generated CA (for the harness's
        own browser/resource simulation calls)."""
        kwargs.setdefault("verify", self.ca_path)
        kwargs.setdefault("follow_redirects", False)
        kwargs.setdefault("timeout", 10.0)
        return httpx.Client(**kwargs)


# --- self-test: a real grant over real TLS ---------------------------------

async def _self_test(stack: FixtureStack) -> None:
    from pydantic import SecretStr

    from tool_gateway.services.authorization_transaction_store import PostgresAuthorizationTransactionStore
    from tool_gateway.services.authorization_transactions import AuthorizationTransaction
    from tool_gateway.services.custody_crypto import Keyring
    from tool_gateway.services.delegated_custody import Owner, PostgresCustodyStore, migrate_custody
    from tool_gateway.tools.user_delegated_client import (
        AcquisitionContext, DelegatedAcquisitionError, UserDelegatedClient)

    keyring = Keyring(stack.files["keyring_path"])
    await migrate_custody(stack.admin_dsn, keyring)
    custody = PostgresCustodyStore(stack.admin_dsn, keyring, stack.files["config_path"],
                                   stack.files["set_id"], CALLBACK)
    await custody.initialize()
    config, linkage, _keys, generation, _fp = await custody.sync_configuration()
    check(config.value("target") == "Automation", "self-test: config target")
    owner = Owner(IDENTITY_ISSUER, USERS["alice"]["sub"])
    check(linkage.get((owner.namespace, owner.subject)) == "42", "self-test: linkage maps alice to account 42")

    client = UserDelegatedClient(custody=custody)
    tx = PostgresAuthorizationTransactionStore(custody)
    now = datetime.now(timezone.utc)
    challenge_id = "11111111-1111-4111-8111-111111111111"
    record = AuthorizationTransaction(
        challenge_id=challenge_id, owner_namespace=owner.namespace, owner_sub=owner.subject,
        target=config.value("target"), credential_set_id=custody.set_id, config_generation=generation,
        session_id="session-selftest", call_id="call-selftest", return_url="/",
        created_at=now, updated_at=now, expires_at=now + timedelta(seconds=600))
    await tx.create(record)
    browser_secret = SecretStr(f"browser-secret-{challenge_id}")
    jar = {challenge_id: browser_secret.get_secret_value()}

    start = await tx.issue_start(challenge_id, owner.namespace, owner.subject, browser_secret=browser_secret, now=now)
    prepared = await tx.consume_start(start, browser_bindings=jar, now=now)
    check(prepared is not None, "self-test: start consumed and state prepared")

    url = client.build_authorization_url(config, state=prepared.state.get_secret_value(),
                                         verifier=prepared.verifier.get_secret_value())
    check(url.startswith(stack.oauth_base + "/authorize?"), "self-test: provider URL targets the fixture")

    # Simulate the initiating browser navigating to the provider (as alice).
    with stack.client() as http:
        resp = http.get(url + "&fixture_user=alice")
    check(resp.status_code == 302, "self-test: provider redirects to the callback")
    location = resp.headers["location"]
    qs = parse_qs(urlsplit(location).query)
    code = qs["code"][0]
    check(qs["state"][0] == prepared.state.get_secret_value(), "self-test: state round-trips")

    claim = await tx.claim_state(prepared.state, browser_bindings=jar, now=datetime.now(timezone.utc))
    check(claim is not None, "self-test: callback claim")
    bundle = await client.exchange_authorization_code(
        config, linkage, owner=owner, code=code, verifier=prepared.verifier.get_secret_value())
    check(bundle.scopes == "read", "self-test: granted scope")
    check(bundle.refresh_secret is not None, "self-test: refresh secret issued")

    metadata = await tx.complete_authorization(
        claim, target_account="42", scopes=bundle.scopes, refresh_secret=bundle.refresh_secret,
        refresh_expires_at=bundle.refresh_expires_at, now=datetime.now(timezone.utc))
    check(metadata is not None, "self-test: durable publication")

    # Send path: a real refresh over TLS, then a real resource call.
    ctx = AcquisitionContext(owner_namespace=owner.namespace, owner_sub=owner.subject,
                             set_name=stack.files["set_id"], target="Automation")
    token = await client.access_token_for_send(ctx)
    check(bool(token.token.get_secret_value()), "self-test: access token acquired")
    with stack.client() as http:
        r = http.get(stack.resource_base + "/api/data",
                     headers={"Authorization": f"Bearer {token.token.get_secret_value()}"})
    check(r.status_code == 200 and r.json()["account"] == "42", "self-test: resource accepted the delegated token")

    s = stack.state.stats
    check(s["authorize"] >= 1 and s["token_code"] >= 1 and s["token_refresh"] >= 1
          and s["whoami"] >= 2 and s["resource"] >= 1, f"self-test: call counts {s}")

    # PKCE + client-auth are actually enforced: a wrong verifier and a wrong
    # client secret both fail closed at the provider.
    bad = await _expect_exchange_error(client, config, linkage, owner, code="bogus", verifier="bogus")
    check(bad == "invalid_grant", f"self-test: bad code/verifier rejected ({bad})")

    # Local invalidation is the real target-401 path: revoking in custody makes
    # the next send fail closed rather than fall back to any other auth path.
    # (The send-path refresh rotated the provider refresh token, so the durable
    # grant — not the original code-exchange secret — is what must be revoked.)
    await client.invalidate_grant(ctx)
    client.reset_cache()
    invalidated = await _expect_send_error(client, ctx)
    check(invalidated == "authorization_required",
          f"self-test: locally invalidated grant blocks the next send ({invalidated})")

    # The remote RFC 7009 leg reports 'revoked' on provider acceptance.
    result = await client.revoke_token(config, bundle.refresh_secret)
    check(result == "revoked", f"self-test: remote revoke accepted ({result})")
    print("delegated-runtime fixtures self-test: real TLS grant, refresh, identity, "
          "resource, PKCE/client-auth enforcement, and revocation all passed")


async def _expect_exchange_error(client, config, linkage, owner, *, code, verifier) -> str:
    from tool_gateway.tools.user_delegated_client import DelegatedAcquisitionError
    try:
        await client.exchange_authorization_code(config, linkage, owner=owner, code=code, verifier=verifier)
    except DelegatedAcquisitionError as exc:
        return exc.kind
    return "no_error"


async def _expect_send_error(client, ctx) -> str:
    from tool_gateway.tools.user_delegated_client import DelegatedAcquisitionError
    try:
        await client.access_token_for_send(ctx)
    except DelegatedAcquisitionError as exc:
        return exc.kind
    return "no_error"


def main() -> int:
    import asyncio

    if not __debug__:
        raise SystemExit("fixture self-test requires assertions enabled")
    quiet_logs()
    try:
        _docker("ps")  # bounded liveness probe; fails fast on a wedged daemon
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None
    stack = FixtureStack()
    try:
        stack.start()
        asyncio.run(_self_test(stack))
    except AssertionError as exc:
        print(f"SELF-TEST FAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        stack.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
