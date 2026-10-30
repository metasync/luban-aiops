"""Failure-first tests for the user-delegated acquisition client (SPEC-070).

A fake custody store (duck-typed to ``PostgresCustodyStore``) and an
``httpx.MockTransport`` provider drive the whole grant with no live external call
and no Postgres. The tests prove the plan's acquisition contract: hardened
provider channel, strict response/identity verification, the LRU access cache with
authoritative reread, single-flight bounded wait, refresh-deadline capping, and
grant-fenced invalidation — and that every failure is a typed
``DelegatedAcquisitionError`` rather than a fallback to another auth path.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from pydantic import SecretStr

from tool_gateway.services.custody_crypto import CustodyError
from tool_gateway.services.delegated_custody import CredentialMetadata, Owner
from tool_gateway.tools.delegated_configuration import DelegatedConfiguration
from tool_gateway.tools.user_delegated_client import (
    AcquisitionContext,
    DelegatedAcquisitionError,
    UserDelegatedClient,
    pkce_challenge,
)

LINKAGE = {("issuer", "alice"): "42"}
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _entry(**over):
    base = dict(
        scheme="oauth2_authorization_code", target="Automation",
        authorization_url="https://oauth.test/authorize", token_url="https://oauth.test/token",
        renewal_url="https://oauth.test/token", identity_url="https://oauth.test/whoami",
        client_id="client", client_secret="opaque-client-value", client_auth="client_secret_basic",
        redirect_uri="https://portal.test/api/v1/targets/authorizations/callback",
        scope="read", allowed_scopes="read write", oauth_origins="https://oauth.test",
        resource_origins="https://resource.test", pkce_method="S256", store="postgres",
        config_revision="1", identity_profile="json_immutable_id", identity_claim="id",
        identity_mapping_path="/run/mapping.json", access_cache_ttl_seconds="300",
        refresh_max_lifetime_seconds="2592000",
    )
    base.update(over)
    return base


def _config(**over):
    return DelegatedConfiguration.parse(_entry(**over))


def _token_json(**over):
    base = {"access_token": "at-123", "token_type": "Bearer", "expires_in": 600,
            "scope": "read", "refresh_token": "new-refresh", "refresh_expires_in": 100000}
    base.update(over)
    return base


def _ctx(**over):
    base = dict(owner_namespace="issuer", owner_sub="alice", set_name="user", target="Automation")
    base.update(over)
    return AcquisitionContext(**base)


class _FakeKeys:
    def __init__(self, recovery_epoch="epoch1"):
        self.recovery_epoch = recovery_epoch

    def snapshot(self):
        return self


class _FakeClaim:
    def __init__(self, owner, refresh_secret, original_deadline, generation="gen1", epoch=2):
        self.owner = owner
        self.generation = generation
        self.epoch = epoch
        self.attempt_id = "attempt-1"
        self.operation = SecretStr("op")
        self.refresh_secret = SecretStr(refresh_secret)
        self.original_refresh_expires_at = original_deadline


class _FakeCustody:
    def __init__(self, config, *, metadata=None, refresh_secret="old-refresh",
                 original_deadline=None, recovery_epoch="epoch1"):
        self._config = config
        self._linkage = dict(LINKAGE)
        self._keys = _FakeKeys(recovery_epoch)
        self._metadata = metadata if metadata is not None else CredentialMetadata("gen1", 1, "42", "read")
        self.refresh_secret = refresh_secret
        self.original_deadline = original_deadline
        self.begin_returns = "claim"
        self.metadata_raises = None
        self.sync_raises = None
        self.complete_raises = None
        self.begin_calls = 0
        self.complete_calls = 0
        self.abandon_calls = 0
        self.revoke_calls = 0
        self.completed_secret = None
        self.completed_deadline = None

    @property
    def keyring(self):
        return self._keys

    async def sync_configuration(self):
        if self.sync_raises is not None:
            raise self.sync_raises
        return self._config, self._linkage, self._keys, "gen1", "fingerprint"

    async def metadata(self, owner):
        if self.metadata_raises is not None:
            raise self.metadata_raises
        return self._metadata

    async def begin_refresh(self, owner):
        self.begin_calls += 1
        if isinstance(self.begin_returns, Exception):
            raise self.begin_returns
        if self.begin_returns is None:
            return None
        return _FakeClaim(owner, self.refresh_secret, self.original_deadline)

    async def complete_refresh(self, claim, refresh_secret, *, refresh_expires_at):
        self.complete_calls += 1
        if self.complete_raises is not None:
            raise self.complete_raises
        self.completed_secret = refresh_secret.get_secret_value()
        self.completed_deadline = refresh_expires_at
        published = CredentialMetadata(claim.generation, claim.epoch, "42", self._metadata.scopes)
        self._metadata = published
        return published

    async def abandon_refresh(self, claim):
        self.abandon_calls += 1

    async def revoke(self, owner):
        self.revoke_calls += 1
        return "local_revoked_remote_unconfirmed"


def _handler(*, token=None, token_status=200, identity=None, identity_status=200,
             raw_token=None, requests=None, token_exc=None):
    def handler(request):
        if requests is not None:
            requests.append(request)
        if request.url.path == "/token":
            if token_exc is not None:
                raise token_exc
            if raw_token is not None:
                return httpx.Response(token_status, content=raw_token,
                                      headers={"content-type": "application/json"})
            return httpx.Response(token_status, json=_token_json() if token is None else token)
        if request.url.path == "/whoami":
            return httpx.Response(identity_status, json={"id": "42"} if identity is None else identity)
        return httpx.Response(404)
    return handler


def _client(custody, handler=None, **kwargs):
    transport = httpx.MockTransport(handler or _handler())
    kwargs.setdefault("utcnow", lambda: NOW)
    return UserDelegatedClient(custody=custody, transport=transport, **kwargs)


# -- authorization URL construction -----------------------------------------

def test_pkce_challenge_matches_rfc7636_vector():
    # The RFC 7636 appendix B verifier.
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert pkce_challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_authorization_url_carries_required_params():
    config = _config(audience="https://aud.test", resource="https://resource.test")
    client = _client(_FakeCustody(config))
    url = client.build_authorization_url(config, state="st-1", verifier="verifier-value")
    assert url.startswith("https://oauth.test/authorize?")
    assert "response_type=code" in url
    assert "client_id=client" in url
    assert "code_challenge_method=S256" in url
    assert f"code_challenge={pkce_challenge('verifier-value')}" in url
    assert "state=st-1" in url
    assert "scope=read" in url
    assert "audience=" in url and "resource=" in url


def test_authorization_url_rejects_reserved_query_in_config():
    config = _config(authorization_url="https://oauth.test/authorize?response_type=code")
    client = _client(_FakeCustody(config))
    with pytest.raises(DelegatedAcquisitionError) as exc:
        client.build_authorization_url(config, state="st-1", verifier="v")
    assert exc.value.kind == "configuration_failure"


# -- happy path + cache ------------------------------------------------------

def test_access_token_refreshes_verifies_and_caches():
    config = _config()
    custody = _FakeCustody(config)
    requests: list = []
    client = _client(custody, _handler(requests=requests))
    token = asyncio.run(client.access_token_for_send(_ctx()))
    assert token.token.get_secret_value() == "at-123"
    assert token.metadata.epoch == 2
    assert custody.complete_calls == 1
    assert client.cache_size == 1
    # Second send is a cache hit: no further provider calls.
    token2 = asyncio.run(client.access_token_for_send(_ctx()))
    assert token2.token.get_secret_value() == "at-123"
    assert custody.begin_calls == 1
    assert len([r for r in requests if r.url.path == "/token"]) == 1
    assert len([r for r in requests if r.url.path == "/whoami"]) == 1


def test_provider_channel_disables_redirects():
    config = _config()
    custody = _FakeCustody(config)
    requests: list = []
    client = _client(custody, _handler(token_status=302, requests=requests))
    with pytest.raises(DelegatedAcquisitionError) as exc:
        asyncio.run(client.access_token_for_send(_ctx()))
    assert exc.value.kind == "transport_failure"
    # The 302 was never followed: exactly one token request was made.
    assert len([r for r in requests if r.url.path == "/token"]) == 1


# -- authorization-required / linkage ---------------------------------------

def test_no_active_grant_is_authorization_required():
    config = _config()
    custody = _FakeCustody(config)
    custody._metadata = None
    client = _client(custody)
    with pytest.raises(DelegatedAcquisitionError) as exc:
        asyncio.run(client.access_token_for_send(_ctx()))
    assert exc.value.kind == "authorization_required"


def test_linkage_mismatch_is_authorization_required():
    config = _config()
    custody = _FakeCustody(config, metadata=CredentialMetadata("gen1", 1, "999", "read"))
    client = _client(custody)
    with pytest.raises(DelegatedAcquisitionError) as exc:
        asyncio.run(client.access_token_for_send(_ctx()))
    assert exc.value.kind == "authorization_required"


def test_unsupported_renewal_when_no_renewal_url():
    config = _config()
    config_no_renew = DelegatedConfiguration.parse(
        {k: v for k, v in _entry().items() if k != "renewal_url"}
    )
    custody = _FakeCustody(config_no_renew)
    client = _client(custody)
    with pytest.raises(DelegatedAcquisitionError) as exc:
        asyncio.run(client.access_token_for_send(_ctx()))
    assert exc.value.kind == "unsupported_renewal"


# -- provider response validation -------------------------------------------

@pytest.mark.parametrize("token,status,kind", [
    ({"access_token": "at", "token_type": "MAC", "expires_in": 600, "scope": "read"}, 200, "malformed_response"),
    ({"access_token": "at", "token_type": "Bearer", "expires_in": 20, "scope": "read"}, 200, "malformed_response"),
    ({"access_token": "", "token_type": "Bearer", "expires_in": 600, "scope": "read"}, 200, "malformed_response"),
    ({"token_type": "Bearer", "expires_in": 600, "scope": "read"}, 200, "malformed_response"),
    ({"access_token": "at", "token_type": "Bearer", "expires_in": 600, "scope": "read write admin"}, 200, "malformed_response"),
    ({"access_token": "at", "token_type": "Bearer", "expires_in": 600, "scope": "read read"}, 200, "malformed_response"),
    ({"error": "invalid_grant"}, 400, "invalid_grant"),
    ({}, 500, "transport_failure"),
])
def test_token_response_validation(token, status, kind):
    config = _config()
    custody = _FakeCustody(config)
    client = _client(custody, _handler(token=token, token_status=status))
    with pytest.raises(DelegatedAcquisitionError) as exc:
        asyncio.run(client.access_token_for_send(_ctx()))
    assert exc.value.kind == kind
    assert custody.complete_calls == 0


def test_duplicate_json_keys_rejected():
    config = _config()
    custody = _FakeCustody(config)
    raw = b'{"access_token":"at","access_token":"at2","token_type":"Bearer","expires_in":600,"scope":"read"}'
    client = _client(custody, _handler(raw_token=raw))
    with pytest.raises(DelegatedAcquisitionError) as exc:
        asyncio.run(client.access_token_for_send(_ctx()))
    assert exc.value.kind == "malformed_response"


def test_oversized_response_rejected():
    config = _config()
    custody = _FakeCustody(config)
    client = _client(custody, _handler(), max_response_bytes=16)
    with pytest.raises(DelegatedAcquisitionError) as exc:
        asyncio.run(client.access_token_for_send(_ctx()))
    assert exc.value.kind == "malformed_response"


def test_provider_timeout_is_transport_failure():
    config = _config()
    custody = _FakeCustody(config)
    client = _client(custody, _handler(token_exc=httpx.ConnectTimeout("boom")))
    with pytest.raises(DelegatedAcquisitionError) as exc:
        asyncio.run(client.access_token_for_send(_ctx()))
    assert exc.value.kind == "transport_failure"


def test_omitted_scope_retains_existing_on_renewal():
    config = _config()
    custody = _FakeCustody(config)
    token = _token_json()
    token.pop("scope")
    client = _client(custody, _handler(token=token))
    result = asyncio.run(client.access_token_for_send(_ctx()))
    assert result.metadata.scopes == "read"
    assert custody.complete_calls == 1


# -- identity verification ---------------------------------------------------

def test_identity_mismatch_is_missing_identity():
    config = _config()
    custody = _FakeCustody(config)
    client = _client(custody, _handler(identity={"id": "999"}))
    with pytest.raises(DelegatedAcquisitionError) as exc:
        asyncio.run(client.access_token_for_send(_ctx()))
    assert exc.value.kind == "missing_identity"
    assert custody.complete_calls == 0
    assert custody.abandon_calls == 1


def test_identity_claim_absent_is_missing_identity():
    config = _config()
    custody = _FakeCustody(config)
    client = _client(custody, _handler(identity={"other": "x"}))
    with pytest.raises(DelegatedAcquisitionError) as exc:
        asyncio.run(client.access_token_for_send(_ctx()))
    assert exc.value.kind == "missing_identity"


def test_no_identity_endpoint_is_missing_identity():
    config = DelegatedConfiguration.parse(
        {k: v for k, v in _entry().items() if k != "identity_url"}
    )
    custody = _FakeCustody(config)
    client = _client(custody)
    with pytest.raises(DelegatedAcquisitionError) as exc:
        asyncio.run(client.access_token_for_send(_ctx()))
    assert exc.value.kind == "missing_identity"


def test_identity_endpoint_non_200_is_missing_identity():
    config = _config()
    custody = _FakeCustody(config)
    client = _client(custody, _handler(identity_status=500))
    with pytest.raises(DelegatedAcquisitionError) as exc:
        asyncio.run(client.access_token_for_send(_ctx()))
    assert exc.value.kind == "missing_identity"


# -- refresh deadline + token retention -------------------------------------

def test_renewal_cannot_extend_original_deadline():
    config = _config()
    original = NOW + timedelta(seconds=100)
    custody = _FakeCustody(config, original_deadline=original)
    # Provider offers a very long refresh lifetime; the cap must win.
    client = _client(custody, _handler(token=_token_json(refresh_expires_in=10_000_000)))
    asyncio.run(client.access_token_for_send(_ctx()))
    assert custody.completed_deadline == original


def test_shorter_provider_refresh_expiry_wins():
    config = _config()
    original = NOW + timedelta(seconds=100_000)
    custody = _FakeCustody(config, original_deadline=original)
    client = _client(custody, _handler(token=_token_json(refresh_expires_in=50)))
    asyncio.run(client.access_token_for_send(_ctx()))
    assert custody.completed_deadline == NOW + timedelta(seconds=50)


def test_refresh_omitting_token_retains_previous_secret():
    config = _config()
    custody = _FakeCustody(config, refresh_secret="prior-refresh")
    token = _token_json()
    token.pop("refresh_token")
    client = _client(custody, _handler(token=token))
    asyncio.run(client.access_token_for_send(_ctx()))
    assert custody.completed_secret == "prior-refresh"


def test_refresh_with_replacement_token_uses_new_secret():
    config = _config()
    custody = _FakeCustody(config, refresh_secret="prior-refresh")
    client = _client(custody, _handler(token=_token_json(refresh_token="rotated-refresh")))
    asyncio.run(client.access_token_for_send(_ctx()))
    assert custody.completed_secret == "rotated-refresh"


# -- store-error mapping + abandon ------------------------------------------

def test_begin_refresh_reauthorization_maps_to_authorization_required():
    config = _config()
    custody = _FakeCustody(config)
    custody.begin_returns = CustodyError("reauthorization_required")
    client = _client(custody)
    with pytest.raises(DelegatedAcquisitionError) as exc:
        asyncio.run(client.access_token_for_send(_ctx()))
    assert exc.value.kind == "authorization_required"


def test_configuration_failure_maps_from_sync():
    config = _config()
    custody = _FakeCustody(config)
    custody.sync_raises = CustodyError("configuration_unavailable")
    client = _client(custody)
    with pytest.raises(DelegatedAcquisitionError) as exc:
        asyncio.run(client.access_token_for_send(_ctx()))
    assert exc.value.kind == "configuration_failure"


def test_no_renewable_claim_is_authorization_required():
    config = _config()
    custody = _FakeCustody(config)
    custody.begin_returns = None
    client = _client(custody)
    with pytest.raises(DelegatedAcquisitionError) as exc:
        asyncio.run(client.access_token_for_send(_ctx()))
    assert exc.value.kind == "authorization_required"


def test_publication_fence_abandons_and_raises_store_failure():
    config = _config()
    custody = _FakeCustody(config)
    custody.complete_raises = CustodyError("publication_fenced")
    client = _client(custody)
    with pytest.raises(DelegatedAcquisitionError) as exc:
        asyncio.run(client.access_token_for_send(_ctx()))
    assert exc.value.kind == "store_failure"
    assert custody.abandon_calls == 1


# -- single-flight bounded wait ---------------------------------------------

def test_concurrent_acquisition_times_out_to_in_progress():
    config = _config()
    custody = _FakeCustody(config)
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_handler(request):
        if request.url.path == "/token":
            started.set()
            await release.wait()
            return httpx.Response(200, json=_token_json())
        return httpx.Response(200, json={"id": "42"})

    async def scenario():
        client = UserDelegatedClient(custody=custody, transport=httpx.MockTransport(slow_handler),
                                     wait_timeout_seconds=0.05, utcnow=lambda: NOW)
        first = asyncio.create_task(client.access_token_for_send(_ctx()))
        await started.wait()
        with pytest.raises(DelegatedAcquisitionError) as exc:
            await client.access_token_for_send(_ctx())
        assert exc.value.kind == "acquisition_in_progress"
        release.set()
        await first

    asyncio.run(scenario())


# -- invalidation + LRU bound ------------------------------------------------

def test_invalidate_grant_evicts_cache_and_revokes():
    config = _config()
    custody = _FakeCustody(config)
    client = _client(custody)
    asyncio.run(client.access_token_for_send(_ctx()))
    assert client.cache_size == 1
    asyncio.run(client.invalidate_grant(_ctx()))
    assert client.cache_size == 0
    assert custody.revoke_calls == 1


def test_access_cache_is_lru_bounded():
    config = _config()
    custody = _FakeCustody(config)
    client = _client(custody, cache_maxsize=2)
    for target in ("Automation", "Other", "Third"):
        asyncio.run(client.access_token_for_send(_ctx(target=target)))
    assert client.cache_size <= 2


def test_client_auth_post_sends_credentials_in_body():
    config = _config(client_auth="client_secret_post")
    custody = _FakeCustody(config)
    requests: list = []
    client = _client(custody, _handler(requests=requests))
    asyncio.run(client.access_token_for_send(_ctx()))
    token_req = next(r for r in requests if r.url.path == "/token")
    assert "Authorization" not in token_req.headers
    body = token_req.content.decode()
    assert "client_id=client" in body and "client_secret=" in body
