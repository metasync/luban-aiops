"""SPEC-070 OQ-7 outbound user-delegated target-authorization runtime.

Owns the six ``/api/v2/targets/authorizations`` handlers and the two independent
verifiers that guard them:

- ``authenticate_authorization_workload`` proves the platform-gateway projected
  service-account token for the bearerless browser handoffs (provider-url and
  callback). It uses the dedicated ``luban-target-authorization-handoff``
  audience, never the execution-handoff audience, and never a Basic/static
  fallback.
- ``authenticate_authorization_human`` proves a genuine delegated-human bearer
  for the owner-scoped edges (start, status, cancel, browser-reset) and derives
  the owner from the verified claims — the request never asserts an owner.

Trust boundaries held here:

- Human and workload bearers are identity/transport material only: verified,
  used to scope a store lookup, then discarded. They are never persisted,
  echoed, or logged, and every refusal is a fixed, non-sensitive class.
- Workload authentication alone is never authority. The provider-url and
  callback edges recover the owner and credential set from the stored
  transaction selected by an opaque handle, so a valid workload token that
  cannot present the matching handle and browser proof obtains nothing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import jwt
from pydantic import SecretStr

from tool_gateway.core.config import GatewaySettings
from tool_gateway.schemas.api import IdentityContext
from tool_gateway.schemas.authorization import (
    AuthorizationCallbackRequest,
    AuthorizationCallbackResponse,
    AuthorizationRequired,
    AuthorizationStartRequest,
    AuthorizationStartResponse,
    AuthorizationStatusResponse,
    BrowserResetRequest,
    ProviderAuthorizationResponse,
    ProviderUrlRequest,
)
from tool_gateway.services.authorization_transactions import (
    AuthorizationLifetimes,
    AuthorizationTransaction,
)
from tool_gateway.services.custody_crypto import CustodyError
from tool_gateway.services.delegated_custody import Owner
from tool_gateway.services.delegated_invoke import (
    MAX_TOKEN_BYTES,
    decode_delegated_human_claims,
    reset_delegated_state,
)
from tool_gateway.tools.user_delegated_client import DelegatedAcquisitionError

LOGGER = logging.getLogger(__name__)

# Cached JWKS client per configured authorization-workload JWKS URL (module-level
# so repeated create_app() calls never re-fetch per request); cleared by
# ``reset_authorization_state``. The human JWKS cache is shared with the
# execution-handoff verifier and lives in ``delegated_invoke``.
_AUTH_WORKLOAD_JWKS: dict[str, jwt.PyJWKClient] = {}


class AuthorizationError(Exception):
    """A fail-closed refusal carrying an HTTP status and a non-sensitive detail."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def reset_authorization_state() -> None:
    """Clear cached JWKS clients (for tests).

    Also clears the shared delegated-human JWKS cache in ``delegated_invoke`` so
    a single reset fully re-primes every verifier this workflow uses.
    """
    _AUTH_WORKLOAD_JWKS.clear()
    reset_delegated_state()


def _auth_workload_jwks_client(settings: GatewaySettings) -> jwt.PyJWKClient:
    cached = _AUTH_WORKLOAD_JWKS.get(settings.authorization_workload_jwks_url)
    if cached is None:
        cached = jwt.PyJWKClient(
            settings.authorization_workload_jwks_url,
            cache_keys=True,
            lifespan=settings.identity_jwks_cache_seconds,
            timeout=5,
        )
        _AUTH_WORKLOAD_JWKS[settings.authorization_workload_jwks_url] = cached
    return cached


def _bearer(request: Any) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthorizationError(401, "bearer authentication required")
    token = token.strip()
    if len(token) > MAX_TOKEN_BYTES:
        raise AuthorizationError(401, "bearer token invalid")
    return token


def authenticate_authorization_workload(settings: GatewaySettings, request: Any) -> str:
    """Verify the platform-gateway projected SA token; return its subject.

    Mirrors the execution-workload path but pins the dedicated authorization
    handoff audience and subject allowlist: RS256 via the cluster JWKS, required
    exp/iss/sub/aud, and an exact subject match. Any failure is a generic 401
    that never echoes the token or the library exception text.
    """
    token = _bearer(request)
    try:
        key = _auth_workload_jwks_client(settings).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key.key,
            algorithms=["RS256"],
            issuer=settings.authorization_workload_issuer,
            audience=settings.authorization_workload_audience,
            options={"require": ["exp", "iss", "sub", "aud"]},
        )
    except Exception:
        raise AuthorizationError(401, "workload token invalid") from None
    subject = str(claims.get("sub", ""))
    if subject not in settings.authorization_workload_subjects:
        raise AuthorizationError(401, "workload subject not authorized")
    return subject


def authenticate_authorization_human(settings: GatewaySettings, request: Any) -> IdentityContext:
    """Verify a genuine delegated-human bearer and derive the owner from it.

    Holds the identical human-trust bar as the execution handoff (shared
    ``decode_delegated_human_claims``), but there is no signed projection to bind
    against: the verified claims ARE the owner source, so ``owner_namespace`` is
    the configured delegated-identity issuer and ``owner_sub`` the verified
    subject. A missing bearer is a 401; any verification failure is a fixed 403
    that never echoes token material.
    """
    token = _bearer(request)
    try:
        claims = decode_delegated_human_claims(settings, token)
    except Exception:
        raise AuthorizationError(403, "delegated identity verification failed") from None
    actor = claims["act"]
    roles = claims.get("roles", [])
    groups = claims.get("groups", [])
    return IdentityContext(
        subject=str(claims["sub"]),
        username=str(claims["username"]),
        email=claims.get("email"),
        groups=[str(g) for g in groups] if isinstance(groups, list) else [],
        roles=[str(r) for r in roles] if isinstance(roles, list) else [],
        actor=actor["sub"],
    )


# A normalized provider denial maps to a terminal callback status: an explicit
# ``access_denied`` refusal becomes ``canceled``; every other normalized denial
# becomes ``failed``. The provider's ``error_description`` free text never reaches
# this map (the wire model forbids it), so no provider internal is forwarded.
_DENIAL_STATUS = {"access_denied": "canceled"}


def _unwrap_bindings(browser_bindings: dict[str, SecretStr]) -> dict[str, str]:
    """Unwrap the wire ``dict[str, SecretStr]`` jar to the plaintext the store proofs compare."""
    return {name: secret.get_secret_value() for name, secret in browser_bindings.items()}


class AuthorizationService:
    """Drives the six owner/workload-scoped ``/targets/authorizations`` handlers.

    Composition only: it holds the transaction store (routing state, single-use
    handles, and browser proofs), the Postgres custody store (durable publication
    authority), and the acquisition client (provider-URL construction and code
    exchange). It never persists, echoes, or logs a bearer, code, state, PKCE
    verifier, browser secret, or provider URL, and every refusal is a fixed,
    non-sensitive :class:`AuthorizationError`.

    Trust posture per edge (OQ-7 contract §5–§6, superseded route shapes per plan):

    - Human edges (start/status/cancel/browser-reset) derive the owner from the
      verified bearer; the request never asserts one. Wrong-owner/unknown/expired
      collapse to a single 404 no-oracle, terminal challenges to 409, and an
      entitlement/config gap to 403.
    - Workload edges (provider-url/callback) recover the owner and set from the
      stored transaction selected by an opaque single-use handle plus a browser
      proof, so workload authentication alone is never authority.
    """

    def __init__(self, *, store, custody, client, lifetimes=None,
                 utcnow=lambda: datetime.now(timezone.utc), audit=None) -> None:
        self._store = store
        self._custody = custody
        self._client = client
        self._lifetimes = lifetimes or AuthorizationLifetimes()
        self._utcnow = utcnow
        # SPEC-070 R-4a/c (plan line 155): an optional fire-and-forget emitter for
        # the narrowly scoped ``target_authorization`` lifecycle audit event, wired
        # by ``app`` bound to settings. ``None`` (the default) keeps every existing
        # construction byte-identical and emits nothing, so the runtime is inert
        # until an emitter is supplied.
        self._audit = audit

    @staticmethod
    def _owner(settings: GatewaySettings, identity: IdentityContext) -> tuple[str, str]:
        """Owner namespace is pinned to the delegated-identity issuer; sub is the
        verified human subject. The request never asserts an owner."""
        return settings.delegated_identity_issuer, identity.subject

    async def _entitlement(self, txn) -> tuple[Any, dict]:
        """Recheck the administered owner->target mapping and current generation.

        Reads authoritative configuration and confirms the challenge's target and
        config generation are current and the owner is still administered for the
        target. Any gap is a fixed 403 entitlement denial — never a 404 oracle and
        never a fallback to another grant.
        """
        try:
            config, linkage, _keys, generation, _fingerprint = await self._custody.sync_configuration()
        except CustodyError:
            raise AuthorizationError(403, "delegated target entitlement unavailable") from None
        if generation != txn.config_generation or config.value("target") != txn.target:
            raise AuthorizationError(403, "delegated target entitlement changed")
        if not linkage.get((txn.owner_namespace, txn.owner_sub)):
            raise AuthorizationError(403, "no administered delegated target mapping")
        return config, linkage

    def _emit_authorization(self, *, operation: str, outcome: str, txn,
                            reason: str | None = None,
                            delegation_mode: str | None = None) -> None:
        """Emit a ``target_authorization`` lifecycle event (SPEC-070 R-4a/c).

        Called ONLY at an actual stored transition the caller just finalized, so
        the store's single-use finalization — a claimed state, a ``consumed``
        pending row, a ``finish``/``cancel`` that reported the transition — IS the
        stored transition identity that dedupes a repeated observation: a second
        callback or cancel finds nothing left to finalize and emits nothing. It
        never fabricates — a successful ``authorized`` is emitted only after
        acknowledged publication, never from a callback response alone and never
        as a stand-in ``tool_invoked``. Only bounded fields ride the event
        (operation, outcome, an optional reason class, and challenge/target/
        session correlation); no bearer, code, state, verifier, browser secret,
        provider URL, or owner namespace is ever included. No emitter wired → a
        silent no-op.
        """
        if self._audit is None:
            return
        self._audit(
            operation=operation,
            authorization_outcome=outcome,
            challenge_id=txn.challenge_id,
            target=txn.target,
            session_id=txn.session_id,
            owner_sub=txn.owner_sub,
            reason=reason,
            delegation_mode=delegation_mode,
        )

    async def produce_challenge(
        self, *, owner_namespace: str, owner_sub: str, session_id: str,
        call_id: str, return_url: str = "/",
    ) -> AuthorizationRequired | None:
        """Create a durable pending challenge for a verified owner; return safe metadata.

        SPEC-070 producer — the bridge from a verified ``authorization_required``
        acquisition failure to the kernel's bounded stop. The caller supplies the
        owner it already verified from authenticated server context (never a
        model-asserted value) and the exact invocation handles (``session_id``,
        ``call_id``) so the challenge binds to the call that needs it.

        Reads authoritative configuration for the current target and generation,
        confirms the owner is administered for the target, mints a fresh
        single-use challenge id, and inserts one pending transaction bound to the
        owner/target/credential-set/generation and the invocation. Returns ONLY
        the public ``{challenge_id, target, expires_at}`` triple the kernel
        promotes — never a token, state, PKCE verifier, provider URL, set id, or
        owner identity.

        Fail-closed to ``None`` (no challenge, no oracle) when configuration is
        unavailable, the owner has no administered mapping (a challenge that
        could never complete), or the store refuses the insert; the caller's
        pre-existing denial then stands. A challenge id is never returned unless
        it was durably inserted.
        """
        try:
            config, linkage, _keys, generation, _fingerprint = await self._custody.sync_configuration()
        except CustodyError:
            return None
        if not linkage.get((owner_namespace, owner_sub)):
            return None
        now = self._utcnow()
        target = config.value("target")
        challenge_id = str(uuid4())
        expires_at = now + timedelta(seconds=self._lifetimes.transaction_ttl_seconds)
        transaction = AuthorizationTransaction(
            challenge_id=challenge_id, owner_namespace=owner_namespace, owner_sub=owner_sub,
            target=target, credential_set_id=self._custody.set_id, config_generation=generation,
            session_id=session_id, call_id=call_id, return_url=return_url,
            created_at=now, updated_at=now, expires_at=expires_at,
        )
        try:
            await self._store.create(transaction)
        except Exception:
            # A store conflict or backend failure is fail-closed: never surface a
            # challenge id that was not durably inserted.
            return None
        return AuthorizationRequired(challenge_id=challenge_id, target=target, expires_at=expires_at)

    async def start(self, settings: GatewaySettings, identity: IdentityContext,
                    challenge_id: str, request: AuthorizationStartRequest) -> AuthorizationStartResponse:
        """Mint a single-use start handle for an owned, pending, entitled challenge."""
        namespace, subject = self._owner(settings, identity)
        now = self._utcnow()
        txn = await self._store.get(challenge_id, namespace, subject, now=now)
        # No-oracle: wrong owner, unknown, and expired are indistinguishable.
        if txn is None or txn.status == "expired":
            raise AuthorizationError(404, "authorization challenge not found")
        if txn.status != "pending":
            raise AuthorizationError(409, "authorization challenge is not pending")
        await self._entitlement(txn)
        token = await self._store.issue_start(
            challenge_id, namespace, subject, browser_secret=request.browser_secret, now=now
        )
        if token is None:
            # A concurrent consume/cancel/expiry, or an already-spent single-use start.
            raise AuthorizationError(409, "authorization challenge is not pending")
        expiry = min(txn.expires_at, now + timedelta(seconds=self._lifetimes.start_ttl_seconds))
        return AuthorizationStartResponse(start_token=token, expires_at=expiry)

    async def provider_url(self, request: ProviderUrlRequest) -> ProviderAuthorizationResponse:
        """Consume the start handle with a browser proof and build the provider URL.

        Workload-only edge: the owner/set come from the stored transaction, so a
        valid workload token that cannot present the matching single-use start
        token AND the browser proof obtains nothing (404 no-oracle).
        """
        now = self._utcnow()
        prepared = await self._store.consume_start(
            request.start_token, browser_bindings=_unwrap_bindings(request.browser_bindings), now=now
        )
        if prepared is None:
            raise AuthorizationError(404, "authorization start handle not found")
        txn = prepared.transaction
        config, _linkage = await self._entitlement(txn)
        state, verifier = prepared.state, prepared.verifier
        try:
            url = self._client.build_authorization_url(
                config, state=state.get_secret_value(), verifier=verifier.get_secret_value()
            )
        except DelegatedAcquisitionError:
            raise AuthorizationError(502, "provider authorization URL unavailable") from None
        return ProviderAuthorizationResponse(provider_url=SecretStr(url), expires_at=txn.expires_at)

    async def callback(self, request: AuthorizationCallbackRequest) -> AuthorizationCallbackResponse:
        """Resolve a browser-verified callback to a safe outcome and return path.

        The stored state selects the owner and credential set; the request supplies
        neither. Once a state is claimed, every outcome is a safe response (never a
        raised oracle): a denial finalizes to its mapped status, a code is redeemed,
        identity-verified, and published atomically — publication, not this response,
        is the authority that flips the challenge to ``authorized``.
        """
        now = self._utcnow()
        claim = await self._store.claim_state(
            request.state, browser_bindings=_unwrap_bindings(request.browser_bindings), now=now
        )
        if claim is None:
            # Unknown/mismatched/expired state or a failed browser proof: a safe
            # failure returning to the portal root, never an oracle and no dispatch.
            return AuthorizationCallbackResponse(status="failed", return_url="/")
        txn = claim.transaction
        return_url = f"/authorizations/return/{txn.challenge_id}"
        if request.denial is not None:
            status = _DENIAL_STATUS.get(request.denial, "failed")
            if await self._store.finish(txn.challenge_id, txn.owner_namespace, txn.owner_sub,
                                        txn.config_generation, status, now=now):
                # The denial finalized this pending challenge. ``request.denial`` is
                # the bounded DenialReason literal, never the provider's free text.
                self._emit_authorization(operation="enroll", outcome=status, txn=txn,
                                         reason=request.denial)
            return AuthorizationCallbackResponse(status=status, return_url=return_url)
        try:
            config, linkage, _keys, _generation, _fingerprint = await self._custody.sync_configuration()
        except CustodyError:
            if await self._store.finish(txn.challenge_id, txn.owner_namespace, txn.owner_sub,
                                        txn.config_generation, "failed", now=now):
                self._emit_authorization(operation="enroll", outcome="failed", txn=txn,
                                         reason="configuration_unavailable")
            return AuthorizationCallbackResponse(status="failed", return_url=return_url)
        owner = Owner(txn.owner_namespace, txn.owner_sub)
        try:
            bundle = await self._client.exchange_authorization_code(
                config, linkage, owner=owner, code=request.code.get_secret_value(),
                verifier=claim.verifier.get_secret_value(),
            )
        except DelegatedAcquisitionError:
            if await self._store.finish(txn.challenge_id, txn.owner_namespace, txn.owner_sub,
                                        txn.config_generation, "failed", now=now):
                self._emit_authorization(operation="enroll", outcome="failed", txn=txn,
                                         reason="code_exchange_failed")
            return AuthorizationCallbackResponse(status="failed", return_url=return_url)
        try:
            metadata = await self._store.complete_authorization(
                claim, target_account=linkage.get((owner.namespace, owner.subject)) or "",
                scopes=bundle.scopes, refresh_secret=bundle.refresh_secret,
                refresh_expires_at=bundle.refresh_expires_at, now=now,
            )
        except Exception:
            # Publication was fenced; the store's uncertainty cleanup already ran.
            # Report a safe failure — the next owner status read is authoritative
            # and a lost response is never manufactured into a false success. This
            # path emits NOTHING: no stored transition was acknowledged here, so a
            # recorded outcome would be fabricated.
            return AuthorizationCallbackResponse(status="failed", return_url=return_url)
        if metadata is None:
            if await self._store.finish(txn.challenge_id, txn.owner_namespace, txn.owner_sub,
                                        txn.config_generation, "failed", now=now):
                self._emit_authorization(operation="enroll", outcome="failed", txn=txn,
                                         reason="publication_failed")
            return AuthorizationCallbackResponse(status="failed", return_url=return_url)
        # Acknowledged publication (metadata non-None) is the ONLY authority that
        # flips the challenge to authorized, so this is the sole place a successful
        # ``target_authorization`` is recorded — never from a callback response alone
        # and never as a stand-in ``tool_invoked``. The verified oauth2 grant makes
        # this a user-delegated success.
        self._emit_authorization(operation="enroll", outcome="authorized", txn=txn,
                                 delegation_mode="user_delegated")
        return AuthorizationCallbackResponse(status="authorized", return_url=return_url)

    async def status(self, settings: GatewaySettings, identity: IdentityContext,
                     challenge_id: str) -> AuthorizationStatusResponse:
        """Non-destructive owner-scoped status projection; wrong-owner/unknown → 404."""
        namespace, subject = self._owner(settings, identity)
        txn = await self._store.get(challenge_id, namespace, subject, now=self._utcnow())
        if txn is None:
            raise AuthorizationError(404, "authorization challenge not found")
        return AuthorizationStatusResponse(
            challenge_id=txn.challenge_id, status=txn.status, target=txn.target,
            session_id=txn.session_id, updated_at=txn.updated_at, expires_at=txn.expires_at,
        )

    async def cancel(self, settings: GatewaySettings, identity: IdentityContext,
                     challenge_id: str) -> None:
        """Idempotent, no-oracle cancellation: found/spent/expired/wrong-owner all succeed.

        Burns the pending transaction and verifier but never revokes an installed
        credential; the route answers 204 regardless of which case applied.
        """
        namespace, subject = self._owner(settings, identity)
        canceled = await self._store.cancel(challenge_id, namespace, subject, now=self._utcnow())
        # The store returns the transitioned transaction ONLY when it actually
        # finalized a pending row — the single-use dedup identity. A repeat cancel
        # or a spent/expired/foreign/unknown challenge returns ``None`` and emits
        # nothing, so an idempotent 204 never double-records and stays no-oracle.
        if canceled is not None:
            self._emit_authorization(operation="cancel", outcome="canceled", txn=canceled)

    async def browser_reset(self, settings: GatewaySettings, identity: IdentityContext,
                            request: BrowserResetRequest) -> int:
        """Cancel this owner's matching pending browser transactions; return the count.

        Bounded portal-logout cleanup driven by the presented cookie jar and the
        verified owner. It never revokes a target credential, creates a login
        session, or accepts a caller-asserted owner.
        """
        namespace, subject = self._owner(settings, identity)
        return await self._store.browser_reset(
            namespace, subject, browser_bindings=_unwrap_bindings(request.browser_bindings),
            now=self._utcnow(),
        )
