"""User-delegated OAuth acquisition client (SPEC-070 R-2/R-3 acquisition leg).

This module owns the *noninteractive* acquisition engine for the
``oauth2_authorization_code`` scheme. It is the delegated analogue of
:class:`tool_gateway.tools.oauth_client.OAuth2TokenClient` (machine
``client_credentials``) but never shares a code path, a cache, or a fallback
with it: a delegated failure must open no target session and invoke none of the
Basic/static-bearer/machine-grant/unauthenticated paths.

Responsibilities (plan §"Delegated acquisition and provider contract"):

* Construct provider authorization URLs entirely in the gateway with PKCE S256,
  server-generated state, exact callback, scope, and audience/resource, rejecting
  configured endpoints that already carry reserved query parameters.
* Exchange an authorization code or refresh a grant over a hardened provider
  channel: no redirects, no environment proxy inheritance, no automatic retry, a
  10-second total deadline, and a 64-KiB response cap.
* Validate token responses strictly (unique JSON keys, scalar types, Bearer token
  type, bounded token values, a usable lifetime, and a granted scope that is a
  nonempty subset of the configured permitted scopes) and verify the caller
  against the explicitly configured HTTPS identity endpoint under the
  ``json_immutable_id`` profile before any custody publication.
* Serve the send-path access token from a process-local, memory-only, LRU-bounded
  cache keyed by the full binding, rereading authoritative configuration and
  credential metadata before every release (there is no positive validity cache).
* Serialize acquisition per binding (single-flight) with a bounded wait, and
* Apply grant-fenced invalidation on a target ``401``/``invalid-token`` response.

Access tokens are memory-only and never persisted, logged, echoed, or returned to
a caller as data; only the failure *class* and the set **name** ever surface. The
durable refresh credential lives only in the gateway custody store as authenticated
ciphertext and is released through a single-use claim.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from pydantic import SecretStr

from tool_gateway.services.custody_crypto import CustodyError
from tool_gateway.services.delegated_custody import CredentialMetadata, Owner
from tool_gateway.tools.delegated_configuration import (
    DelegatedConfiguration,
    unique_object,
)

LOGGER = logging.getLogger(__name__)

# Provider-channel hardening (plan §"OAuth requests and verification").
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_RESPONSE_BYTES = 65_536
MAX_TOKEN_BYTES = 16_384
# Effective access expiry is the shorter of provider expiry and the configured
# local cap, minus this fixed safety margin (plan §"Runtime composition and bounds").
SAFETY_MARGIN_SECONDS = 30.0
# Bound a waiter on an in-flight acquisition, then return a safe
# acquisition-in-progress error rather than an enrollment challenge.
DEFAULT_WAIT_TIMEOUT_SECONDS = 5.0
# Process-local access cache bound with LRU eviction.
ACCESS_CACHE_MAX_ENTRIES = 1_024

CLIENT_AUTH_BASIC = "client_secret_basic"
CLIENT_AUTH_POST = "client_secret_post"

# Query parameters the gateway always sets on an authorization URL; a configured
# endpoint that already carries one is rejected rather than silently overridden.
RESERVED_AUTH_PARAMS = frozenset({
    "response_type", "client_id", "redirect_uri", "scope", "state",
    "code_challenge", "code_challenge_method", "audience", "resource",
})

# Optional token-request parameters forwarded when configured.
_OPTIONAL_PARAMS = ("audience", "resource")


class DelegatedAcquisitionError(Exception):
    """A typed acquisition failure.

    ``kind`` distinguishes the plan's result classes so a connector can map each
    to the correct posture without ever falling back to another auth path:
    ``transport_failure``, ``malformed_response``, ``unsupported_renewal``,
    ``missing_identity``, ``configuration_failure``, ``store_failure``,
    ``authorization_required``, ``acquisition_in_progress``, ``invalid_grant``.
    """

    def __init__(self, kind: str, detail: str) -> None:
        self.kind = kind
        self.detail = detail
        super().__init__(f"{kind}: {detail}")


@dataclass(frozen=True)
class AcquisitionContext:
    """The typed requester/acquisition context threaded through connectors.

    Carries the gateway-verified requester (``owner_namespace``/``owner_sub``) and
    the selected set/target plus the optional audience/resource the token is bound
    to. It is identity and routing metadata only — never a credential value.
    """

    owner_namespace: str
    owner_sub: str
    set_name: str
    target: str
    audience: str | None = None
    resource: str | None = None


@dataclass(frozen=True)
class DelegatedAccessToken:
    """A memory-only access token, its monotonic expiry, and the binding it was
    acquired under. The token is a ``SecretStr`` so it never leaks through a
    repr, a log line, or a tool result."""

    token: SecretStr = field(repr=False)
    expires_at: float
    metadata: CredentialMetadata


@dataclass(frozen=True)
class _TokenBundle:
    """A validated provider token response, prior to custody publication."""

    access_token: SecretStr = field(repr=False)
    access_ttl_seconds: float
    refresh_secret: SecretStr | None = field(default=None, repr=False)
    refresh_expires_at: datetime | None = None
    scopes: str = ""
    account: str = ""


class _AccessCache:
    """Process-local, memory-only, LRU-bounded access-token cache."""

    def __init__(self, maxsize: int = ACCESS_CACHE_MAX_ENTRIES) -> None:
        self._maxsize = max(1, maxsize)
        self._data: OrderedDict[tuple, DelegatedAccessToken] = OrderedDict()

    def get(self, key: tuple) -> DelegatedAccessToken | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        self._data.move_to_end(key)
        return entry

    def put(self, key: tuple, value: DelegatedAccessToken) -> None:
        self._data[key] = value
        self._data.move_to_end(key)
        while len(self._data) > self._maxsize:
            self._data.popitem(last=False)

    def evict(self, key: tuple) -> None:
        self._data.pop(key, None)

    def evict_owner(self, owner_namespace: str, owner_sub: str) -> None:
        for key in [k for k in self._data if k[0] == owner_namespace and k[1] == owner_sub]:
            self._data.pop(key, None)

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)


def pkce_challenge(verifier: str) -> str:
    """RFC 7636 S256 code challenge for a verifier."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _bounded_secret(value: object) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value.encode("utf-8")) <= MAX_TOKEN_BYTES
        and all(32 <= ord(c) < 127 for c in value)
    )


def _parse_unique_json(raw: bytes) -> dict:
    """Parse JSON rejecting duplicate object keys (a token-response hardening)."""
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    except (ValueError, UnicodeDecodeError):
        raise DelegatedAcquisitionError("malformed_response", "provider response was not valid JSON")
    if not isinstance(payload, dict):
        raise DelegatedAcquisitionError("malformed_response", "provider response was not a JSON object")
    return payload


class UserDelegatedClient:
    """Acquires and caches user-delegated access tokens for the send path.

    One instance is owned by the gateway lifespan and shared by the HTTP and MCP
    connectors. The custody store (duck-typed to :class:`PostgresCustodyStore`)
    is the only durable authority; an injected ``transport``
    (``httpx.MockTransport``) replaces the real socket at every provider call so
    tests drive the whole grant with no live external request, and an injected
    ``clock``/``utcnow`` make expiry and deadlines deterministic.
    """

    def __init__(
        self,
        *,
        custody,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        cache_maxsize: int = ACCESS_CACHE_MAX_ENTRIES,
        wait_timeout_seconds: float = DEFAULT_WAIT_TIMEOUT_SECONDS,
        clock=time.monotonic,
        utcnow=lambda: datetime.now(timezone.utc),
    ) -> None:
        self._custody = custody
        self._transport = transport
        self._timeout = timeout_seconds
        self._max_bytes = max_response_bytes
        self._wait_timeout = wait_timeout_seconds
        self._clock = clock
        self._utcnow = utcnow
        self._cache = _AccessCache(cache_maxsize)
        self._locks: dict[tuple, asyncio.Lock] = {}

    # -- public API ---------------------------------------------------------

    def reset_cache(self) -> None:
        self._cache.clear()

    @property
    def cache_size(self) -> int:
        return len(self._cache)

    def build_authorization_url(self, config: DelegatedConfiguration, *, state: str, verifier: str) -> str:
        """Construct the provider authorization URL entirely in the gateway."""
        base = config.value("authorization_url")
        parts = urlsplit(base)
        if parts.query:
            existing = {key for key, _ in parse_qsl(parts.query, keep_blank_values=True)}
            if existing & RESERVED_AUTH_PARAMS:
                raise DelegatedAcquisitionError(
                    "configuration_failure", "authorization_url carries reserved query parameters"
                )
        projection = config.projection()
        params: dict[str, str] = {
            "response_type": "code",
            "client_id": config.value("client_id"),
            "redirect_uri": config.value("redirect_uri"),
            "scope": config.value("scope"),
            "state": state,
            "code_challenge": pkce_challenge(verifier),
            "code_challenge_method": "S256",
        }
        for key in _OPTIONAL_PARAMS:
            if projection.get(key):
                params[key] = projection[key]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), ""))

    async def access_token_for_send(self, ctx: AcquisitionContext) -> DelegatedAccessToken:
        """Return a verified, unexpired access token for one delegated send.

        Single-flight per binding with a bounded wait; rereads authoritative
        configuration and credential metadata before every release.
        """
        owner = Owner(ctx.owner_namespace, ctx.owner_sub)
        binding = (ctx.owner_namespace, ctx.owner_sub, ctx.set_name, ctx.target, ctx.audience, ctx.resource)
        lock = self._lock_for(binding)
        try:
            await asyncio.wait_for(lock.acquire(), timeout=self._wait_timeout)
        except (asyncio.TimeoutError, TimeoutError):
            raise DelegatedAcquisitionError(
                "acquisition_in_progress", "delegated acquisition already in flight for this binding"
            )
        try:
            return await self._acquire(owner, ctx)
        finally:
            lock.release()

    async def exchange_authorization_code(
        self,
        config: DelegatedConfiguration,
        linkage: dict,
        *,
        owner: Owner,
        code: str,
        verifier: str,
    ) -> _TokenBundle:
        """Redeem an authorization code (callback leg) into a verified bundle.

        Provider-facing only: the caller (workflow) publishes the result through
        the transaction store's ``complete_authorization``. Identity is verified
        before this returns, so no token is released to a resource unverified.
        """
        expected_account = linkage.get((owner.namespace, owner.subject))
        if not expected_account:
            raise DelegatedAcquisitionError("missing_identity", "no administered linkage for this owner")
        permitted = set(config.value("allowed_scopes").split(" "))
        return await self._token_request(
            config,
            grant="authorization_code",
            code=code,
            verifier=verifier,
            requested_scope=config.value("scope"),
            permitted_scopes=permitted,
            existing_scope=None,
            is_renewal=False,
            original_refresh_deadline=None,
            expected_account=expected_account,
        )

    async def invalidate_grant(self, ctx: AcquisitionContext) -> None:
        """Grant-fenced invalidation after a target 401/invalid-token response.

        Evicts the process-local cache and revokes the durable grant so the next
        authorization check on every replica blocks. A target 403 is a permission
        denial and must never call this.
        """
        owner = Owner(ctx.owner_namespace, ctx.owner_sub)
        self._cache.evict_owner(ctx.owner_namespace, ctx.owner_sub)
        try:
            await self._custody.revoke(owner)
        except CustodyError as exc:
            raise self._map_store_error(exc)

    async def revoke_token(self, config: DelegatedConfiguration, refresh_secret: SecretStr) -> str:
        """One bounded RFC 7009 revocation attempt over the hardened channel.

        SPEC-070 (plan §"Provisioning and operator operations"): the operator
        ``remote-revoke`` step, invoked only *after* a local revocation has already
        committed. Returns ``"revoked"`` only when the provider accepted the
        revocation (HTTP 200 — an RFC 7009 server answers 200 for an accepted or
        already-invalid token), and ``"remote_unconfirmed"`` for a missing
        revocation endpoint, an unknown client-auth variant, a transport failure, a
        timeout, or any non-200. It never retries an uncertain result and never
        rolls back the committed local revocation, which is a separate operation.
        The refresh credential is a memory-only ``SecretStr`` the operator supplies
        from a fenced file; it is never logged, echoed, or persisted here.
        """
        if config.remote_revocation != "supported":
            return "remote_unconfirmed"
        data = {"token": refresh_secret.get_secret_value(), "token_type_hint": "refresh_token"}
        headers = {"Accept": "application/json"}
        try:
            self._apply_client_auth(config, data, headers)
            status, _body = await self._provider_request(
                "POST", config.value("revocation_url"), data=data, headers=headers
            )
        except DelegatedAcquisitionError:
            return "remote_unconfirmed"
        return "revoked" if status == 200 else "remote_unconfirmed"

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _apply_client_auth(config: DelegatedConfiguration, data: dict, headers: dict) -> None:
        """Apply the configured confidential-client authentication in place.

        Single-sourced by the token exchange and the RFC 7009 revocation attempt so
        both present client credentials exactly as configured (Basic or POST) and
        fail closed on an unknown variant rather than sending an unauthenticated
        request.
        """
        client_auth = config.value("client_auth")
        client_id = config.value("client_id")
        client_secret = config.value("client_secret")
        if client_auth == CLIENT_AUTH_POST:
            data["client_id"] = client_id
            data["client_secret"] = client_secret
        elif client_auth == CLIENT_AUTH_BASIC:
            raw = f"{client_id}:{client_secret}".encode("utf-8")
            headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
        else:
            raise DelegatedAcquisitionError("configuration_failure", "unknown client_auth variant")

    def _lock_for(self, binding: tuple) -> asyncio.Lock:
        lock = self._locks.get(binding)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[binding] = lock
        return lock

    @staticmethod
    def _map_store_error(exc: CustodyError) -> DelegatedAcquisitionError:
        code = str(exc)
        if code in {"reauthorization_required", "recovery_epoch_mismatch"}:
            return DelegatedAcquisitionError("authorization_required", code)
        if code in {"configuration_unavailable", "stale_configuration", "configuration_revision_reused",
                    "configuration_invalidated", "configuration_changed"}:
            return DelegatedAcquisitionError("configuration_failure", code)
        return DelegatedAcquisitionError("store_failure", code or "store_failure")

    async def _acquire(self, owner: Owner, ctx: AcquisitionContext) -> DelegatedAccessToken:
        try:
            config, linkage, keys, _generation, _fingerprint = await self._custody.sync_configuration()
        except CustodyError as exc:
            raise self._map_store_error(exc)
        recovery_epoch = getattr(keys, "recovery_epoch", None)
        try:
            metadata = await self._custody.metadata(owner)
        except CustodyError as exc:
            raise self._map_store_error(exc)
        if metadata is None:
            raise DelegatedAcquisitionError("authorization_required", "no active delegated grant for this binding")
        expected_account = linkage.get((owner.namespace, owner.subject))
        if expected_account != metadata.target_account:
            raise DelegatedAcquisitionError("authorization_required", "linkage does not match the published grant")

        cache_key = self._cache_key(ctx, metadata, recovery_epoch)
        cached = self._cache.get(cache_key)
        if cached is not None and self._clock() < cached.expires_at:
            return cached

        token = await self._refresh(owner, ctx, config, linkage, metadata, expected_account)
        self._cache.put(self._cache_key(ctx, token.metadata, recovery_epoch), token)
        return token

    @staticmethod
    def _cache_key(ctx: AcquisitionContext, metadata: CredentialMetadata, recovery_epoch) -> tuple:
        return (
            ctx.owner_namespace, ctx.owner_sub, ctx.set_name, ctx.target, ctx.audience, ctx.resource,
            metadata.scopes, metadata.generation, metadata.epoch, recovery_epoch,
        )

    async def _refresh(
        self, owner: Owner, ctx: AcquisitionContext, config: DelegatedConfiguration,
        linkage: dict, metadata: CredentialMetadata, expected_account: str,
    ) -> DelegatedAccessToken:
        if config.renewal == "unsupported":
            raise DelegatedAcquisitionError("unsupported_renewal", "this delegated target does not support renewal")
        try:
            claim = await self._custody.begin_refresh(owner)
        except CustodyError as exc:
            raise self._map_store_error(exc)
        if claim is None:
            raise DelegatedAcquisitionError("authorization_required", "no renewable delegated grant")
        permitted = set(config.value("allowed_scopes").split(" "))
        requested_scope = metadata.scopes or config.value("scope")
        try:
            bundle = await self._token_request(
                config,
                grant="refresh_token",
                refresh_secret=claim.refresh_secret.get_secret_value(),
                requested_scope=requested_scope,
                permitted_scopes=permitted,
                existing_scope=metadata.scopes,
                is_renewal=True,
                original_refresh_deadline=claim.original_refresh_expires_at,
                expected_account=expected_account,
            )
            # A successful refresh that omits a replacement refresh token retains
            # only the actual previously issued token held by this claim.
            new_refresh_secret = bundle.refresh_secret or claim.refresh_secret
            try:
                published = await self._custody.complete_refresh(
                    claim, new_refresh_secret, refresh_expires_at=bundle.refresh_expires_at
                )
            except CustodyError as exc:
                raise self._map_store_error(exc)
            if published is None:
                raise DelegatedAcquisitionError("store_failure", "refresh publication was fenced")
        except BaseException:
            # Any uncertain exchange or staging failure abandons the attempt
            # without replay; the claim's consumed refresh secret is never reused.
            try:
                await self._custody.abandon_refresh(claim)
            except CustodyError:
                pass
            raise
        return DelegatedAccessToken(
            token=bundle.access_token,
            expires_at=self._clock() + bundle.access_ttl_seconds,
            metadata=published,
        )

    async def _token_request(
        self, config: DelegatedConfiguration, *, grant: str, requested_scope: str,
        permitted_scopes: set[str], existing_scope: str | None, is_renewal: bool,
        original_refresh_deadline: datetime | None, expected_account: str,
        code: str | None = None, verifier: str | None = None, refresh_secret: str | None = None,
    ) -> _TokenBundle:
        data: dict[str, str] = {"grant_type": grant}
        if grant == "authorization_code":
            data["code"] = code or ""
            data["redirect_uri"] = config.value("redirect_uri")
            data["code_verifier"] = verifier or ""
        else:
            data["refresh_token"] = refresh_secret or ""
        if requested_scope:
            data["scope"] = requested_scope
        projection = config.projection()
        for key in _OPTIONAL_PARAMS:
            if projection.get(key):
                data[key] = projection[key]

        headers = {"Accept": "application/json"}
        self._apply_client_auth(config, data, headers)

        status, body = await self._provider_request("POST", config.value("token_url"), data=data, headers=headers)
        payload = _parse_unique_json(body)
        if status != 200:
            error_code = payload.get("error") if isinstance(payload.get("error"), str) else ""
            if error_code == "invalid_grant":
                raise DelegatedAcquisitionError("invalid_grant", "provider rejected the grant")
            raise DelegatedAcquisitionError("transport_failure", f"token endpoint returned {status}")

        bundle = self._validate_token_response(
            payload, config,
            requested_scope=requested_scope, permitted_scopes=permitted_scopes,
            existing_scope=existing_scope, is_renewal=is_renewal,
            original_refresh_deadline=original_refresh_deadline,
        )
        # Never release a token to a resource before account verification.
        await self._verify_identity(config, bundle.access_token.get_secret_value(), expected_account)
        return bundle

    def _validate_token_response(
        self, payload: dict, config: DelegatedConfiguration, *, requested_scope: str,
        permitted_scopes: set[str], existing_scope: str | None, is_renewal: bool,
        original_refresh_deadline: datetime | None,
    ) -> _TokenBundle:
        access_token = payload.get("access_token")
        if not _bounded_secret(access_token):
            raise DelegatedAcquisitionError("malformed_response", "token response carried no usable access_token")
        token_type = payload.get("token_type")
        if not isinstance(token_type, str) or token_type.strip().lower() != "bearer":
            raise DelegatedAcquisitionError("malformed_response", "token response was not a Bearer token")

        expires_in = payload.get("expires_in")
        if isinstance(expires_in, bool) or not isinstance(expires_in, (int, float)) or not expires_in > 0:
            raise DelegatedAcquisitionError("malformed_response", "token response carried no usable lifetime")
        effective_ttl = min(float(expires_in), float(config.access_cache_ttl_seconds)) - SAFETY_MARGIN_SECONDS
        if effective_ttl <= 0:
            raise DelegatedAcquisitionError("malformed_response", "token lifetime is not usable after the safety margin")

        granted_scope = self._resolve_scope(
            payload, requested_scope=requested_scope, permitted_scopes=permitted_scopes,
            existing_scope=existing_scope, is_renewal=is_renewal,
        )

        refresh_secret: SecretStr | None = None
        raw_refresh = payload.get("refresh_token")
        if raw_refresh is not None:
            if not _bounded_secret(raw_refresh):
                raise DelegatedAcquisitionError("malformed_response", "token response carried a malformed refresh_token")
            refresh_secret = SecretStr(raw_refresh)

        refresh_expires_at = self._resolve_refresh_deadline(
            payload, config, original_refresh_deadline=original_refresh_deadline
        )
        return _TokenBundle(
            access_token=SecretStr(access_token),
            access_ttl_seconds=effective_ttl,
            refresh_secret=refresh_secret,
            refresh_expires_at=refresh_expires_at,
            scopes=granted_scope,
            account="",
        )

    @staticmethod
    def _resolve_scope(payload: dict, *, requested_scope: str, permitted_scopes: set[str],
                       existing_scope: str | None, is_renewal: bool) -> str:
        if "scope" not in payload:
            # An omitted scope retains the requested scope for code redemption and
            # the existing verified scope for renewal.
            retained = existing_scope if is_renewal else requested_scope
            if not retained:
                raise DelegatedAcquisitionError("malformed_response", "no scope granted and none retained")
            return retained
        scope = payload.get("scope")
        if not isinstance(scope, str) or not scope.strip():
            raise DelegatedAcquisitionError("malformed_response", "token response carried a malformed scope")
        tokens = scope.split(" ")
        if not all(tokens) or len(set(tokens)) != len(tokens):
            raise DelegatedAcquisitionError("malformed_response", "token response carried a malformed scope")
        if not set(tokens) <= permitted_scopes:
            raise DelegatedAcquisitionError("malformed_response", "token response expanded the granted scope")
        return " ".join(tokens)

    def _resolve_refresh_deadline(self, payload: dict, config: DelegatedConfiguration, *,
                                  original_refresh_deadline: datetime | None) -> datetime | None:
        now = self._utcnow()
        local_cap = now + timedelta(seconds=config.refresh_max_lifetime_seconds)
        deadline = original_refresh_deadline if original_refresh_deadline is not None else local_cap
        # A renewal can never extend the original authorization deadline.
        if original_refresh_deadline is not None and deadline > original_refresh_deadline:
            deadline = original_refresh_deadline
        provider_refresh = payload.get("refresh_expires_in")
        if provider_refresh is not None:
            if isinstance(provider_refresh, bool) or not isinstance(provider_refresh, (int, float)) or provider_refresh <= 0:
                raise DelegatedAcquisitionError("malformed_response", "token response carried a malformed refresh expiry")
            provider_deadline = now + timedelta(seconds=float(provider_refresh))
            deadline = min(deadline, provider_deadline)
        return deadline

    async def _verify_identity(self, config: DelegatedConfiguration, access_token: str, expected_account: str) -> None:
        if config.identity_evidence != "configured":
            raise DelegatedAcquisitionError("missing_identity", "no identity endpoint configured for verification")
        identity_url = config.value("identity_url")
        status, body = await self._provider_request(
            "GET", identity_url, headers={"Accept": "application/json", "Authorization": f"Bearer {access_token}"}
        )
        if status != 200:
            raise DelegatedAcquisitionError("missing_identity", f"identity endpoint returned {status}")
        payload = _parse_unique_json(body)
        claim_name = config.value("identity_claim")
        claim = payload.get(claim_name)
        # ID tokens are ignored as evidence under json_immutable_id; only the
        # configured immutable claim is accepted, with no username/email equivalence.
        if not isinstance(claim, str) or not claim.strip() or len(claim.encode("utf-8")) > MAX_TOKEN_BYTES:
            raise DelegatedAcquisitionError("missing_identity", "identity response lacked the configured immutable claim")
        if claim != expected_account:
            raise DelegatedAcquisitionError("missing_identity", "identity claim does not match the administered account")

    async def _provider_request(self, method: str, url: str, *, data=None, headers=None) -> tuple[int, bytes]:
        """One hardened provider call: no redirects, no proxy, no retry, bounded."""
        client_kwargs: dict = {
            "timeout": self._timeout,
            "follow_redirects": False,
            "trust_env": False,
        }
        if self._transport is not None:
            client_kwargs["transport"] = self._transport
        request_headers = dict(headers or {})
        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                request = client.build_request(method, url, data=data, headers=request_headers)
                response = await client.send(request, stream=True)
                try:
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > self._max_bytes:
                            raise DelegatedAcquisitionError("malformed_response", "provider response exceeded the size cap")
                        chunks.append(chunk)
                    return response.status_code, b"".join(chunks)
                finally:
                    await response.aclose()
        except DelegatedAcquisitionError:
            raise
        except httpx.TimeoutException:
            raise DelegatedAcquisitionError("transport_failure", "provider request timed out")
        except httpx.HTTPError as exc:
            LOGGER.warning("delegated provider request failed: %s", exc.__class__.__name__)
            raise DelegatedAcquisitionError("transport_failure", "provider request failed")
