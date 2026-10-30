"""Strict, provider-independent R-1 configuration. This module performs no network I/O."""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Mapping
from urllib.parse import urlsplit

SCHEME = "oauth2_authorization_code"
REQUIRED = frozenset(("scheme", "target", "authorization_url", "token_url", "client_id",
    "client_secret", "client_auth", "redirect_uri", "scope", "allowed_scopes", "oauth_origins",
    "resource_origins", "pkce_method", "store", "config_revision", "identity_profile",
    "identity_claim", "identity_mapping_path", "access_cache_ttl_seconds",
    "refresh_max_lifetime_seconds"))
OPTIONAL = frozenset(("renewal_url", "revocation_url", "identity_url", "audience", "resource"))
CALLBACK_PATH = "/api/v1/targets/authorizations/callback"

# Runtime delegated-policy bounds (plan §"Runtime composition and bounds"). Both
# are explicit string-valued per-set fields, validated as positive integers with
# hard maxima and folded into the configuration fingerprint so a policy change
# fences cached access tokens and in-flight claims across replicas.
ACCESS_CACHE_TTL_MAX_SECONDS = 300
REFRESH_MAX_LIFETIME_MAX_SECONDS = 2_592_000
_POLICY_BOUNDS = {
    "access_cache_ttl_seconds": ACCESS_CACHE_TTL_MAX_SECONDS,
    "refresh_max_lifetime_seconds": REFRESH_MAX_LIFETIME_MAX_SECONDS,
}


class ConfigurationError(ValueError):
    """Only static failure classes may cross this boundary."""


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigurationError("duplicate_key")
        result[key] = value
    return result


def read_json(path: str):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle, object_pairs_hook=unique_object)
    except (OSError, ValueError, TypeError):
        raise ConfigurationError("configuration_unavailable") from None


def https_origin(value: str, *, origin_only: bool = False) -> str:
    """Canonical origin; reject URL parser normalization of dangerous input."""
    try:
        if (not isinstance(value, str) or not value or any(ord(c) <= 32 or ord(c) >= 127 for c in value)
                or any(c in value for c in "\\#") or "%" in value.split("/", 3)[2]):
            raise ValueError
        url = urlsplit(value)
        if url.scheme != "https" or not url.hostname or url.username is not None or url.password is not None:
            raise ValueError
        host = url.hostname.lower()
        if ":" in host:
            host = f"[{ipaddress.IPv6Address(host).compressed}]"
        elif not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host):
            raise ValueError
        elif any(not part or len(part) > 63 or part.startswith("-") or part.endswith("-")
                 for part in host.split(".")):
            raise ValueError
        if url.port is not None and not 1 <= url.port <= 65535:
            raise ValueError
        if url.netloc.endswith(":"):
            raise ValueError
        if origin_only and (url.path or url.query or "?" in value):
            raise ValueError
        port = url.port or 443
        return f"https://{host}" + (f":{port}" if port != 443 else "")
    except (ValueError, IndexError):
        raise ConfigurationError("invalid_https_destination") from None


def _words(value: str, *, origins: bool = False) -> tuple[str, ...]:
    words = value.split(" ")
    if not all(words):
        raise ConfigurationError("invalid_list")
    if origins:
        words = [https_origin(word, origin_only=True) for word in words]
    elif not all(re.fullmatch(r"[\x21\x23-\x5b\x5d-\x7e]+", word) for word in words):
        raise ConfigurationError("invalid_scope")
    if len(set(words)) != len(words):
        raise ConfigurationError("duplicate_list_value")
    return tuple(words)


@dataclass(frozen=True, repr=False)
class DelegatedConfiguration:
    _values: Mapping[str, str] = field(repr=False)

    @classmethod
    def parse(cls, value: object) -> DelegatedConfiguration:
        if not isinstance(value, dict) or not REQUIRED <= value.keys() or value.keys() - REQUIRED - OPTIONAL:
            raise ConfigurationError("invalid_fields")
        if any(not isinstance(v, str) or not v.strip() or any(ord(c) < 32 or ord(c) == 127 for c in v)
               for v in value.values()):
            raise ConfigurationError("invalid_field_type")
        for key, allowed in (("scheme", {SCHEME}), ("client_auth", {"client_secret_basic", "client_secret_post"}),
                             ("pkce_method", {"S256"}), ("store", {"postgres"}),
                             ("identity_profile", {"json_immutable_id"})):
            if value[key] not in allowed:
                raise ConfigurationError("unsupported_profile")
        if not re.fullmatch(r"[1-9][0-9]{0,17}", value["config_revision"]):
            raise ConfigurationError("invalid_revision")
        for key, maximum in _POLICY_BOUNDS.items():
            if not re.fullmatch(r"[1-9][0-9]*", value[key]) or int(value[key]) > maximum:
                raise ConfigurationError("invalid_policy_bound")
        if (not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", value["identity_claim"])
                or value["identity_claim"].lower() in {"email", "username", "name", "preferred_username"}):
            raise ConfigurationError("unsupported_identity_claim")
        if not Path(value["identity_mapping_path"]).is_absolute():
            raise ConfigurationError("invalid_mapping_path")
        permitted = set(_words(value["allowed_scopes"]))
        if not set(_words(value["scope"])) <= permitted:
            raise ConfigurationError("scope_not_permitted")
        oauth_origins = _words(value["oauth_origins"], origins=True)
        resources = _words(value["resource_origins"], origins=True)
        for key in ("authorization_url", "token_url", "renewal_url", "revocation_url", "identity_url"):
            if key in value and https_origin(value[key]) not in oauth_origins:
                raise ConfigurationError("untrusted_oauth_destination")
        https_origin(value["redirect_uri"])
        callback = urlsplit(value["redirect_uri"])
        if callback.path != CALLBACK_PATH or callback.query or "?" in value["redirect_uri"]:
            raise ConfigurationError("invalid_callback")
        if "resource" in value and https_origin(value["resource"]) not in resources:
            raise ConfigurationError("untrusted_resource")
        return cls(MappingProxyType(dict(value)))

    def projection(self) -> dict[str, str]:
        """Explicit private configuration transport, never a tool response."""
        return dict(self._values)

    def value(self, key: str) -> str:
        return self._values[key]

    @property
    def revision(self) -> int:
        return int(self._values["config_revision"])

    @property
    def access_cache_ttl_seconds(self) -> int:
        """Local cap on how long a verified access token may be cached."""
        return int(self._values["access_cache_ttl_seconds"])

    @property
    def refresh_max_lifetime_seconds(self) -> int:
        """Absolute authorization renewal deadline cap (local, not a provider guarantee)."""
        return int(self._values["refresh_max_lifetime_seconds"])

    @property
    def renewal(self) -> Literal["supported", "unsupported"]:
        return "supported" if "renewal_url" in self._values else "unsupported"

    @property
    def remote_revocation(self) -> Literal["supported", "unconfirmed"]:
        return "supported" if "revocation_url" in self._values else "unconfirmed"

    @property
    def identity_evidence(self) -> Literal["configured", "identity_evidence_unavailable"]:
        return "configured" if "identity_url" in self._values else "identity_evidence_unavailable"

    def fingerprint(self, key: bytes, linkage: dict[tuple[str, str], str]) -> str:
        if len(key) != 32:
            raise ConfigurationError("invalid_fingerprint_key")
        payload = json.dumps([dict(self._values), sorted((ns, sub, account) for (ns, sub), account in linkage.items())],
                             sort_keys=True, separators=(",", ":")).encode()
        return hmac.new(key, b"delegated-config-v1\x00" + payload, hashlib.sha256).hexdigest()


def load_snapshot(path: str, set_id: str, trusted_callback: str) -> tuple[DelegatedConfiguration, dict]:
    raw = read_json(path)
    if not isinstance(raw, dict) or set_id not in raw:
        raise ConfigurationError("configuration_missing")
    config = DelegatedConfiguration.parse(raw[set_id])
    if config.value("redirect_uri") != trusted_callback:
        raise ConfigurationError("callback_mismatch")
    rows = read_json(config.value("identity_mapping_path"))
    if not isinstance(rows, list):
        raise ConfigurationError("invalid_linkage")
    linkage = {}
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {"owner_namespace", "owner_sub", "target_account"}
                or any(not isinstance(v, str) or not v.strip() or any(ord(c) < 32 for c in v) for v in row.values())):
            raise ConfigurationError("invalid_linkage")
        owner = row["owner_namespace"], row["owner_sub"]
        if owner in linkage:
            raise ConfigurationError("ambiguous_linkage")
        linkage[owner] = row["target_account"]
    return config, linkage
