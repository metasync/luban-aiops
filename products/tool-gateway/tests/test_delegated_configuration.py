"""Failure-first R-1 checks; no provider or deployment dependency."""
import asyncio
import json

import pytest

from tool_gateway.tools.credential_sets import CredentialSetStore, _parse_set
from tool_gateway.tools.delegated_configuration import (
    ACCESS_CACHE_TTL_MAX_SECONDS,
    REFRESH_MAX_LIFETIME_MAX_SECONDS,
    DelegatedConfiguration,
)


def entry():
    return dict(scheme="oauth2_authorization_code", target="Automation",
                authorization_url="https://oauth.test/authorize", token_url="https://oauth.test/token",
                client_id="client", client_secret="opaque-client-value", client_auth="client_secret_basic",
                redirect_uri="https://portal.test/api/v1/targets/authorizations/callback",
                scope="read", allowed_scopes="read write", oauth_origins="https://oauth.test",
                resource_origins="https://resource.test", pkce_method="S256", store="postgres",
                config_revision="1", identity_profile="json_immutable_id", identity_claim="id",
                identity_mapping_path="/run/mapping.json",
                access_cache_ttl_seconds="300", refresh_max_lifetime_seconds="2592000")


def test_valid_projection_and_optional_absence():
    assert _parse_set("automation", entry()) == entry()
    from tool_gateway.tools.delegated_configuration import DelegatedConfiguration
    config = DelegatedConfiguration.parse(entry())
    assert config.renewal == "unsupported"
    assert config.remote_revocation == "unconfirmed"
    assert config.identity_evidence == "identity_evidence_unavailable"
    assert "opaque-client-value" not in repr(config)


@pytest.mark.parametrize("key", list(entry()))
@pytest.mark.parametrize("bad", [None, True, 5, [], {}, "", " "])
def test_required_fields_fail_closed(key, bad, caplog):
    value = {**entry(), key: bad}
    assert _parse_set("automation", value) is None
    assert "opaque-client-value" not in caplog.text


@pytest.mark.parametrize("key", ["renewal_url", "revocation_url", "identity_url"])
@pytest.mark.parametrize("bad", [None, 1, True, "", " ", "http://oauth.test/x",
    "https://oauth.test@evil.test/x", "https://oauth.test/x#s", "https://other.test/x",
    "https://oauth.test/x\n", "https://oauth.test:invalid/x", "https://oauth.test\\@evil.test/x"])
def test_optional_present_is_not_optional_validation(key, bad):
    assert _parse_set("automation", {**entry(), key: bad}) is None


@pytest.mark.parametrize("override", [
    {"scope": "admin"}, {"scope": "read read"}, {"allowed_scopes": "read  write"},
    {"oauth_origins": "https://oauth.test/path"}, {"oauth_origins": "https://*.test"},
    {"oauth_origins": "https://oauth.test https://oauth.test:443"},
    {"pkce_method": "plain"}, {"client_auth": "none"}, {"store": "memory"},
    {"config_revision": "0"}, {"config_revision": "1.0"}, {"config_revision": "01"},
    {"identity_profile": "id_token"}, {"identity_claim": "email"},
    {"redirect_uri": "https://portal.test/wrong"},
    {"redirect_uri": "https://portal.test/api/v1/targets/authorizations/callback?code=x"},
    {"resource": "https://other.test/api"}, {"extra": "opaque-client-value"},
])
def test_unsupported_profiles_and_trust(override):
    assert _parse_set("automation", {**entry(), **override}) is None


@pytest.mark.parametrize("key,bad", [
    ("access_cache_ttl_seconds", "0"), ("access_cache_ttl_seconds", "301"),
    ("access_cache_ttl_seconds", "-1"), ("access_cache_ttl_seconds", "1.5"),
    ("access_cache_ttl_seconds", "abc"), ("access_cache_ttl_seconds", "1e3"),
    ("access_cache_ttl_seconds", " 300"), ("access_cache_ttl_seconds", "300 "),
    ("access_cache_ttl_seconds", "0300"),
    ("refresh_max_lifetime_seconds", "0"), ("refresh_max_lifetime_seconds", "2592001"),
    ("refresh_max_lifetime_seconds", "-1"), ("refresh_max_lifetime_seconds", "1.5"),
    ("refresh_max_lifetime_seconds", "abc"), ("refresh_max_lifetime_seconds", "02592000"),
])
def test_delegated_policy_ttl_bounds_rejected(key, bad):
    assert _parse_set("automation", {**entry(), key: bad}) is None


@pytest.mark.parametrize("key,good", [
    ("access_cache_ttl_seconds", "1"), ("access_cache_ttl_seconds", "300"),
    ("refresh_max_lifetime_seconds", "1"), ("refresh_max_lifetime_seconds", "2592000"),
])
def test_delegated_policy_ttl_bounds_accepted(key, good):
    assert _parse_set("automation", {**entry(), key: good}) is not None


def test_delegated_policy_ttl_in_fingerprint():
    linkage = {("issuer", "alice"): "42"}
    base = DelegatedConfiguration.parse(entry())
    shorter = DelegatedConfiguration.parse({**entry(), "access_cache_ttl_seconds": "60"})
    longer = DelegatedConfiguration.parse({**entry(), "refresh_max_lifetime_seconds": "60"})
    key = b"f" * 32
    assert base.fingerprint(key, linkage) != shorter.fingerprint(key, linkage)
    assert base.fingerprint(key, linkage) != longer.fingerprint(key, linkage)


def test_delegated_policy_ttl_accessors_and_maxima():
    config = DelegatedConfiguration.parse(entry())
    assert config.access_cache_ttl_seconds == 300
    assert config.refresh_max_lifetime_seconds == 2592000
    assert ACCESS_CACHE_TTL_MAX_SECONDS == 300
    assert REFRESH_MAX_LIFETIME_MAX_SECONDS == 2_592_000


@pytest.mark.parametrize("damage", ["{", "[]", "missing", "{}", "invalid"])
def test_delegated_reload_never_keeps_last_good(tmp_path, damage):
    path = tmp_path / "sets.json"
    path.write_text(json.dumps({"user": entry(), "machine": {"username": "a", "password": "b"}}))
    store = CredentialSetStore(str(path))
    assert store.get("user") == entry()
    if damage == "missing":
        path.unlink()
    elif damage == "invalid":
        path.write_text(json.dumps({"user": {**entry(), "scope": "admin"},
                                    "machine": {"username": "a", "password": "b"}}))
    else:
        path.write_text(damage)
    assert store.get("user") is None
    if damage in ("{", "[]", "missing"):
        assert store.get("machine") == {"username": "a", "password": "b"}


@pytest.mark.parametrize("key", list(entry()))
def test_missing_required_fields(key):
    value = entry()
    value.pop(key)
    assert _parse_set("automation", value) is None


@pytest.mark.parametrize("destination", ["https://[::1]suffix/token", "https://[::1]:443suffix/token",
                                         "https://[::1]suffix:443/token"])
def test_ambiguous_bracket_authority_rejected(destination):
    from tool_gateway.tools.delegated_configuration import ConfigurationError, https_origin
    with pytest.raises(ConfigurationError):
        https_origin(destination)


def test_unknown_scheme_does_not_log_supplied_values(caplog):
    assert _parse_set("opaque-name-marker", {**entry(), "scheme": "opaque-scheme-marker"}) is None
    assert "opaque-name-marker" not in caplog.text
    assert "opaque-scheme-marker" not in caplog.text


def test_rejection_does_not_invoke_machine_client():
    from tool_gateway.tools.auth_resolution import resolve_outbound_auth
    class NoMachineClient:
        async def acquire(self, *args):
            pytest.fail("delegated configuration invoked machine grant")
    auth, error = asyncio.run(resolve_outbound_auth(set_name="user", entry=entry(), token_client=NoMachineClient()))
    assert auth is None and error is not None


def test_snapshot_callback_mapping_and_fingerprint(tmp_path):
    from tool_gateway.tools.delegated_configuration import load_snapshot, ConfigurationError
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps([dict(owner_namespace="issuer", owner_sub="alice", target_account="42")]))
    value = {**entry(), "identity_mapping_path": str(mapping)}
    sets = tmp_path / "sets.json"
    sets.write_text(json.dumps({"user": value}))
    config, linkage = load_snapshot(str(sets), "user", value["redirect_uri"])
    assert linkage == {("issuer", "alice"): "42"}
    fingerprint = config.fingerprint(b"f" * 32, linkage)
    assert fingerprint != config.fingerprint(b"f" * 32, {("issuer", "alice"): "43"})
    with pytest.raises(ConfigurationError, match="callback_mismatch"):
        load_snapshot(str(sets), "user", "https://other.test/api/v1/targets/authorizations/callback")
    mapping.write_text('[{"owner_namespace":"issuer","owner_sub":"alice","target_account":"42"},'
                       '{"owner_namespace":"issuer","owner_sub":"alice","target_account":"43"}]')
    with pytest.raises(ConfigurationError):
        load_snapshot(str(sets), "user", value["redirect_uri"])
