"""SPEC-070 browser edge: failure-first HTTP tests with a controlled backend."""
import json
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from platform_gateway.app import create_app
from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.services import target_authorization as edge
from platform_gateway.services.policy_engine import reset_policy_state

CHALLENGE = "11111111-1111-4111-8111-111111111111"
HANDLE = "22222222-2222-4222-8222-222222222222"
BASE = "/api/v1/targets/authorizations"
SECRET = "b" * 43
COOKIE = f"__Host-luban-oauth-{CHALLENGE}={SECRET}"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def token(source="oidc", roles=None):
    return jwt.encode(dict(iss="issuer", sub="alice-sub", username="alice", aud=["platform-gateway"],
        roles=roles or ["operator"], groups=[], authentication_source=source,
        exp=int(time.time()) + 300), KEY, algorithm="RS256")


@pytest.fixture
def harness(tmp_path):
    reset_policy_state()
    mount = tmp_path / "workload.jwt"
    mount.write_text("projected-workload")
    settings = PlatformGatewaySettings(target_authorization_enabled=True,
        tool_gateway_url="http://tools.test", identity_token_issuer="issuer",
        authorization_workload_token_path=str(mount), service_client_secret="broker-fixture")
    calls = []
    expiry = (datetime.now(timezone.utc) + timedelta(seconds=300)).isoformat()
    status = dict(challenge_id=CHALLENGE, status="pending", target="Automation", session_id="ses-1",
        updated_at=datetime.now(timezone.utc).isoformat(), expires_at=expiry)
    reply = {"status": "authorized", "return_url": f"/authorizations/return/{CHALLENGE}"}

    def backend(request):
        calls.append(request)
        path = request.url.path
        if path.endswith("/provider-url"):
            return httpx.Response(200, json={"provider_url": "https://oauth.test/authorize?state=secret-state", "expires_at": expiry})
        if path.endswith("/callback"):
            return httpx.Response(200, json=reply)
        if path.endswith("/start"):
            return httpx.Response(200, json={"start_token": HANDLE,
                "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()})
        if path.endswith("/cancel"):
            return httpx.Response(204)
        if path.endswith("/browser-reset"):
            return httpx.Response(200, json={"canceled": 1})
        return httpx.Response(200, json=status)

    detail = dict(session_id="ses-1", user_id="alice", session_type="operation", evidence_turns=[
        {"frames": [{"type": "authorization_required", "auth_challenge_id": CHALLENGE, "target": "Automation"}]}])
    session = AsyncMock(return_value=detail)
    delegation = AsyncMock(return_value="delegated-human")
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    with patch.object(edge, "_http_client", side_effect=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(backend), trust_env=False, follow_redirects=False)), \
            patch("platform_gateway.services.token_verifier._get_jwks_client", return_value=SimpleNamespace(
                get_signing_key_from_jwt=lambda _: SimpleNamespace(key=KEY.public_key()))), \
            patch.object(edge, "obtain_delegated_token", delegation), \
            patch.object(edge, "get_session", session):
        with TestClient(app, base_url="https://portal.test", follow_redirects=False) as client:
            yield SimpleNamespace(client=client, calls=calls, status=status, reply=reply, mount=mount,
                session=session, delegation=delegation, settings=settings, app=app,
                headers={"Authorization": "Bearer " + token()})
    reset_policy_state()


def bare(response, location="/"):
    assert response.status_code == 302
    assert response.content == b""
    assert response.headers["location"] == location
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["referrer-policy"] == "no-referrer"


@pytest.mark.parametrize("query", ["", "code=x&state=s&state=t", "code=x&code=y&state=s",
    "code=x&error=access_denied&state=s", "state=s", "code=&state=s", "code=%ZZ&state=s",
    "code=%FF&state=s", "code=x&state=%0A", "code=x&state=s&owner_sub=mallory",
    "code=" + "x" * 17000 + "&state=s", "&".join(["error_description=x"] * 20)])
def test_malformed_callback_is_bare_and_never_forwarded(harness, query):
    bare(harness.client.get(BASE + "/callback?" + query, headers={"Cookie": COOKIE}))
    assert harness.calls == []
    harness.delegation.assert_not_called()
    harness.session.assert_not_called()


@pytest.mark.parametrize("cookie", ["", COOKIE + "; " + COOKIE, COOKIE.replace(SECRET, '"quoted"'),
    "__Host-luban-oauth-bad=abc", "; ".join(f"__Host-luban-oauth-{uuid4()}={SECRET}" for _ in range(9))])
def test_callback_rejects_missing_ambiguous_or_oversized_cookie_jar(harness, cookie):
    bare(harness.client.get(BASE + "/callback?code=code-canary&state=state-canary", headers={"Cookie": cookie}))
    assert harness.calls == []


@pytest.mark.parametrize("outcome", ["authorized", "canceled", "failed", "expired"])
def test_callback_uses_only_workload_and_cleans_matching_cookie(harness, outcome):
    harness.reply["status"] = outcome
    response = harness.client.get(BASE + "/callback?code=code-canary&state=state-canary", headers={"Cookie": COOKIE})
    bare(response, f"/authorizations/return/{CHALLENGE}")
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert "Secure" in response.headers["set-cookie"]
    assert harness.calls[0].headers["authorization"] == "Bearer projected-workload"
    assert json.loads(harness.calls[0].content) == dict(code="code-canary", state="state-canary",
        browser_bindings={CHALLENGE: SECRET})
    harness.delegation.assert_not_called()
    harness.session.assert_not_called()


@pytest.mark.parametrize("error, expected", [("access_denied", "access_denied"), ("unknown-provider-error", "server_error")])
def test_provider_denial_never_forwards_description(harness, error, expected):
    response = harness.client.get(BASE + f"/callback?state=s&error={error}&error_description=private-canary",
        headers={"Cookie": COOKIE})
    bare(response, f"/authorizations/return/{CHALLENGE}")
    body = json.loads(harness.calls[0].content)
    assert body == dict(state="s", denial=expected, browser_bindings={CHALLENGE: SECRET})


@pytest.mark.parametrize("url", ["https://evil.test", "//evil.test", "/authorizations/return/invalid", "/?code=leak",
    f"/authorizations/return/{HANDLE}"])
def test_untrusted_callback_destination_falls_back_without_cookie_clear(harness, url):
    harness.reply["return_url"] = url
    response = harness.client.get(BASE + "/callback?state=s&code=c", headers={"Cookie": COOKIE})
    bare(response)
    assert "set-cookie" not in response.headers


def test_missing_workload_mount_no_basic_fallback(harness):
    harness.mount.write_text("")
    bare(harness.client.get(BASE + "/callback?state=s&code=c", headers={"Cookie": COOKIE}))
    assert harness.calls == []


def test_workload_is_reread_per_callback(harness):
    for value in ("rotated-one", "rotated-two"):
        harness.mount.write_text(value)
        harness.client.get(BASE + "/callback?state=s&code=c", headers={"Cookie": COOKIE})
        assert harness.calls[-1].headers["authorization"] == "Bearer " + value


def test_start_requires_real_human_and_durable_owner_evidence(harness):
    for headers, expected in (({}, 401), ({"Authorization": "Bearer " + token("development")}, 403),
                              ({"Authorization": "Bearer " + token(roles=["auditor"])}, 403)):
        assert harness.client.post(f"{BASE}/{CHALLENGE}/start", headers=headers).status_code == expected
    assert harness.calls == []
    harness.session.return_value = {"session_id": "ses-1", "user_id": "alice", "evidence_turns": []}
    assert harness.client.post(f"{BASE}/{CHALLENGE}/start", headers=harness.headers).status_code == 404
    assert not any(c.url.path.endswith("/start") for c in harness.calls)


def test_start_cookie_bounds_and_only_backend_path_reaches_js(harness):
    response = harness.client.post(f"{BASE}/{CHALLENGE}/start", headers=harness.headers)
    assert response.status_code == 200
    assert set(response.json()) == {"start_url", "expires_at"}
    assert response.json()["start_url"] == f"{BASE}/start/{HANDLE}"
    cookie = response.headers["set-cookie"]
    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/" in cookie
    assert "Domain=" not in cookie
    assert 0 < int(cookie.split("Max-Age=")[1].split(";")[0]) <= 300
    body = json.loads(harness.calls[-1].content)
    assert len(body["browser_secret"]) == 43
    assert body["browser_secret"] not in response.text
    assert harness.calls[-1].headers["authorization"] == "Bearer delegated-human"


def test_start_cookie_limit_does_not_evict_other_challenge(harness):
    jar = "; ".join(f"__Host-luban-oauth-{uuid4()}={SECRET}" for _ in range(8))
    response = harness.client.post(f"{BASE}/{CHALLENGE}/start", headers={**harness.headers, "Cookie": jar})
    assert response.status_code == 409
    assert "set-cookie" not in response.headers
    assert harness.calls == []


def test_provider_navigation_is_bare_and_never_uses_human_delegation(harness):
    response = harness.client.get(f"{BASE}/start/{HANDLE}", headers={"Cookie": COOKIE})
    bare(response, "https://oauth.test/authorize?state=secret-state")
    assert json.loads(harness.calls[0].content) == {"start_token": HANDLE, "browser_bindings": {CHALLENGE: SECRET}}
    harness.delegation.assert_not_called()


def test_status_is_owned_evidence_checked_and_secret_free(harness):
    response = harness.client.get(f"{BASE}/{CHALLENGE}", headers=harness.headers)
    assert response.status_code == 200
    assert response.json() == harness.status
    harness.session.return_value["user_id"] = "mallory"
    assert harness.client.get(f"{BASE}/{CHALLENGE}", headers=harness.headers).status_code == 404


def test_cancel_and_reset_are_authenticated_and_clear_only_matching_cookies(harness):
    response = harness.client.post(f"{BASE}/{CHALLENGE}/cancel", headers={**harness.headers, "Cookie": COOKIE})
    assert response.status_code == 204 and response.content == b""
    assert "Max-Age=0" in response.headers["set-cookie"]
    response = harness.client.post(BASE + "/browser-reset", headers={**harness.headers, "Cookie": COOKIE})
    assert response.status_code == 204
    assert json.loads(harness.calls[-1].content) == {"browser_bindings": {CHALLENGE: SECRET}}


def test_authorization_logging_uses_templates_at_source(harness, caplog):
    import logging
    caplog.set_level(logging.DEBUG)
    with patch("platform_gateway.app.log_event") as event:
        harness.client.get(f"{BASE}/start/{HANDLE}", headers={"Cookie": COOKIE})
        assert event.call_args.kwargs["path"] == BASE + "/start/{start_token}"
    logger = logging.getLogger("uvicorn.access")
    record = logger.makeRecord(logger.name, logging.INFO, __file__, 1,
        '%s - "%s %s HTTP/%s" %d', ("client", "GET", BASE + "/callback?code=log-canary", "1.1", 302), None)
    assert "log-canary" not in record.getMessage()
    logger = logging.getLogger("httpcore.http11")
    record = logger.makeRecord(logger.name, logging.DEBUG, __file__, 1,
        "response headers %s", ({"location": "https://provider/?state=header-canary"},), None)
    assert "header-canary" not in record.getMessage()


def test_all_edge_failures_are_noncacheable(harness):
    for path, method in ((f"{BASE}/{CHALLENGE}", "get"), (f"{BASE}/{CHALLENGE}/start", "post"),
                         (BASE + "/missing", "get")):
        response = getattr(harness.client, method)(path)
        assert response.headers.get("cache-control") == "no-store"
        assert response.headers.get("referrer-policy") == "no-referrer"


def test_secret_spans_excluded_before_export(harness, monkeypatch):
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from platform_gateway.core import telemetry
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    # Isolated provider: exercise actual instrumentation/export without global SDK mutation.
    original = FastAPIInstrumentor.instrument_app
    def instrument(app, **kwargs):
        return original(app, tracer_provider=provider, **kwargs)
    monkeypatch.setattr(telemetry, "_providers_initialized", True)
    monkeypatch.setenv("OTEL_ENABLED", "true")
    monkeypatch.setattr(FastAPIInstrumentor, "instrument_app", instrument)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: harness.settings
    instrumentor = HTTPXClientInstrumentor()
    already_instrumented = instrumentor.is_instrumented_by_opentelemetry
    if not already_instrumented:
        instrumentor.instrument(tracer_provider=provider)
    try:
        with TestClient(app, base_url="https://portal.test", follow_redirects=False) as client:
            # The browser client is outside the server process in reality.
            from opentelemetry.instrumentation.utils import suppress_http_instrumentation
            with suppress_http_instrumentation():
                client.get(BASE + "/callback?code=span-canary&state=s", headers={"Cookie": COOKIE})
                client.get(f"{BASE}/start/{HANDLE}", headers={"Cookie": COOKIE})
            # Exclusion must hold without an inherited suppression context too.
            import asyncio
            import httpx
            async def direct():
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://portal.test") as c:
                    await c.get(BASE + "/callback?code=span-canary&state=s", headers={"Cookie": COOKIE})
                    await c.get("/health/live")
            asyncio.run(direct())
        server_spans = [s for s in exporter.get_finished_spans() if s.kind.name == "SERVER"]
        assert server_spans, "ordinary requests still export spans"
        assert all("authorizations" not in str(s.attributes) and "span-canary" not in str(s.attributes)
                   for s in server_spans)
        # Backend client spans are suppressed; only the test's external browser client may exist.
        assert not any("tools.test" in str(s.attributes) for s in exporter.get_finished_spans())
    finally:
        FastAPIInstrumentor.uninstrument_app(app)
        if not already_instrumented:
            instrumentor.uninstrument()
        provider.shutdown()


@pytest.mark.parametrize("query", ["code=x&state=%20", "code=%20&state=s", "code=x&state=%C3%A9",
    "code=%C3%A9&state=s", "code=x&state=s%20t", "code=c%20d&state=s"])
def test_nonopaque_callback_values_never_forward(harness, query):
    response = harness.client.get(BASE + "/callback?" + query, headers={"Cookie": COOKIE})
    bare(response)
    assert "set-cookie" not in response.headers
    assert harness.calls == []


def test_callback_body_and_trailing_slash_never_forward(harness):
    bare(harness.client.request("GET", BASE + "/callback?code=c&state=s", content="private-canary",
                                headers={"Cookie": COOKIE}))
    bare(harness.client.get(BASE + "/callback/?code=c&state=s", headers={"Cookie": COOKIE}))
    assert harness.calls == []


def test_failed_human_exchange_never_uses_workload_or_basic(harness):
    harness.delegation.return_value = None
    response = harness.client.post(f"{BASE}/{CHALLENGE}/start", headers=harness.headers)
    assert response.status_code == 503 and harness.calls == []


@pytest.mark.parametrize("body", [b'not-json', b'{"status":"authorized","status":"failed","return_url":"/"}', b'x' * 65537])
def test_backend_invalid_response_is_bare_without_retry_or_cookie_clear(harness, body):
    calls = []
    def backend(request):
        calls.append(request)
        return httpx.Response(200, content=body)
    with patch.object(edge, "_http_client", side_effect=lambda: httpx.AsyncClient(transport=httpx.MockTransport(backend))):
        response = harness.client.get(BASE + "/callback?state=s&code=c", headers={"Cookie": COOKIE})
    bare(response)
    assert "set-cookie" not in response.headers and len(calls) == 1


def test_lost_callback_ack_does_not_overwrite_authoritative_status(harness):
    calls = []
    def backend(request):
        calls.append(request)
        harness.status["status"] = "authorized"
        raise httpx.ReadTimeout("private-canary")
    with patch.object(edge, "_http_client", side_effect=lambda: httpx.AsyncClient(transport=httpx.MockTransport(backend))):
        response = harness.client.get(BASE + "/callback?state=s&code=c", headers={"Cookie": COOKIE})
    bare(response)
    assert "set-cookie" not in response.headers and len(calls) == 1
    observed = harness.client.get(f"{BASE}/{CHALLENGE}", headers=harness.headers)
    assert observed.json()["status"] == "authorized"


@pytest.mark.parametrize("changes", [{"target_authorization_enabled": False}, {"require_auth": False},
    {"authorization_workload_token_path": ""}, {"tool_gateway_url": "https://user:secret@tools.test"},
    {"tool_gateway_url": "https://tools.test?secret=x"}, {"delegation_audience": "other"}])
def test_missing_or_unsafe_configuration_is_fail_closed(harness, changes):
    from dataclasses import replace
    settings = replace(harness.settings, **changes)
    harness.app.dependency_overrides[get_settings] = lambda: settings
    bare(harness.client.get(BASE + "/callback?state=s&code=c", headers={"Cookie": COOKIE}))
    response = harness.client.post(f"{BASE}/{CHALLENGE}/start", headers=harness.headers)
    assert response.status_code in {403, 503}
    assert harness.calls == []


def test_authorization_mount_setting_from_env(monkeypatch):
    monkeypatch.setenv("PLATFORM_GATEWAY_AUTHORIZATION_WORKLOAD_TOKEN_PATH", "/projected/authorization.jwt")
    assert PlatformGatewaySettings.from_env().authorization_workload_token_path == "/projected/authorization.jwt"


@pytest.mark.parametrize("suffix, status, body", [
    (f"/{CHALLENGE}/cancel", 200, {}),
    (f"/{CHALLENGE}/cancel", 204, {"unexpected": "private-canary"}),
    ("/browser-reset", 204, None),
    ("/browser-reset", 200, {}),
    ("/browser-reset", 200, {"canceled": True}),
    ("/browser-reset", 200, {"canceled": -1}),
    ("/browser-reset", 200, {"canceled": 2}),
    ("/browser-reset", 200, {"canceled": 1, "extra": "private-canary"}),
])
def test_cleanup_invalid_ack_does_not_clear_cookie_or_retry(harness, suffix, status, body):
    calls = []
    def backend(request):
        calls.append(request)
        return httpx.Response(status, json=body) if body is not None else httpx.Response(status)
    with patch.object(edge, "_http_client", side_effect=lambda: httpx.AsyncClient(transport=httpx.MockTransport(backend))):
        response = harness.client.post(BASE + suffix, headers={**harness.headers, "Cookie": COOKIE})
    assert response.status_code == 502
    assert "set-cookie" not in response.headers and len(calls) == 1
    assert "private-canary" not in response.text
