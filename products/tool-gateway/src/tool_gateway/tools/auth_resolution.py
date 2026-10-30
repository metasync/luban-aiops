"""Reusable outbound auth-resolution seam (SPEC-068 R-3).

One acquisition path every connector reuses: resolve a named credential set's
scheme into the correct outbound auth. SPEC-058's ``http_connector`` is the
first consumer; SPEC-067's ServiceNow/MCP adapter is the second, reusing this
resolver and the same :class:`OAuth2TokenClient` with no re-implementation.

The resolver returns both an ``httpx.Auth`` (for httpx-based connectors) and the
resolved bearer token (for a non-httpx transport such as the MCP SDK's
streamable-HTTP client, which takes a header or client factory), so a single
acquisition serves either.

A credential/config failure is a structured **gateway** error — the deliberate
inverse of SPEC-058's "an upstream 4xx/5xx is a fact, not a tool error": a
missing credential is our failure to authenticate, never the target's answer, so
it is never projected as a successful result and never falls back to an
unauthenticated call. Only the set **name** ever surfaces; a credential value or
an acquired token never does.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass

import httpx

from tool_gateway.tools.credential_sets import scheme_of
from tool_gateway.tools.oauth_client import (
    CREDENTIAL_ACQUISITION_FAILED,
    OAuth2TokenClient,
)

# SPEC-070 R-4a/R-4c: the top-level audit ``delegation_mode``, derived from the
# *verified acquisition outcome* at this single seam rather than from a connector
# configuration label. A ``ContextVar`` (per-task) — never an attribute on a
# reusable connector singleton — so concurrent invocations cannot cross-
# contaminate. ``None`` (omitted from the audit event) until a resolution runs;
# the gateway reads it back inside the same request task, before redaction, so a
# REDACTION_OVERFLOW result replacement cannot drop it. Values: ``user_delegated``
# only after a verified user-delegated grant, ``acting_service`` for an actual
# machine credential, ``none`` when an acquisition was attempted but failed.
DELEGATION_MODE: ContextVar[str | None] = ContextVar("delegation_mode", default=None)


class BearerAuth(httpx.Auth):
    """Attaches ``Authorization: Bearer <token>`` to an outbound request."""

    def __init__(self, token: str) -> None:
        self._token = token

    def auth_flow(self, request: httpx.Request):
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request


@dataclass(frozen=True)
class ResolvedAuth:
    """The resolved outbound credential for one call.

    ``auth`` is what an httpx connector attaches; ``bearer_token`` is the raw
    token for a non-httpx transport (``None`` for ``basic``, which has no bearer
    form). ``scheme`` is recorded so a consumer can branch without re-deriving it
    from the entry.
    """

    scheme: str
    auth: httpx.Auth | None
    bearer_token: str | None = None
    # Private verified acquisition metadata for a user-delegated result
    # (SPEC-070): the target-account identity/generation/epoch the acquisition
    # client proved. ``None`` for every other scheme. An internal attribution
    # fact, never a connector configuration label and never surfaced in a result.
    acquisition: object | None = None


def _error(set_name: str, detail: str) -> tuple[str, str, str]:
    """A structured gateway error naming only the set (never a secret)."""
    return (
        CREDENTIAL_ACQUISITION_FAILED,
        f"Credential set '{set_name}': {detail}.",
        "error",
    )


def _delegated_error(set_name: str, exc: Exception) -> tuple[str, str, str]:
    """Map a ``DelegatedAcquisitionError`` kind to a structured gateway error.

    Only the set name and the failure *kind* surface — never a token, secret, or
    provider detail. ``authorization_required`` is a ``denied`` posture (the
    requester must re-authorize); a bounded concurrent acquisition is a safe
    ``error``, not an enrollment challenge; every other kind fails closed as a
    credential-acquisition error.
    """
    kind = getattr(exc, "kind", "acquisition_failed")
    if kind == "authorization_required":
        code, status = "DELEGATED_REAUTHORIZATION_REQUIRED", "denied"
    elif kind == "acquisition_in_progress":
        code, status = "DELEGATED_ACQUISITION_IN_PROGRESS", "error"
    else:
        code, status = CREDENTIAL_ACQUISITION_FAILED, "error"
    return (
        code,
        f"User-delegated acquisition for credential set '{set_name}' failed: {kind}.",
        status,
    )


async def resolve_outbound_auth(
    *,
    set_name: str,
    entry: dict[str, str],
    token_client: "OAuth2TokenClient",
    delegated_client: object | None = None,
    acquisition: object | None = None,
) -> tuple[ResolvedAuth | None, tuple[str, str, str] | None]:
    """Resolve one credential entry into outbound auth for its scheme.

    Returns ``(ResolvedAuth, None)`` on success or
    ``(None, (code, message, status))`` on a credential/config failure. Fails
    closed on every scheme: a missing field or a failed token acquisition is a
    gateway error, never an unauthenticated fallback.

    SPEC-070 R-4a/R-4c: as a side effect this derives the top-level audit
    ``delegation_mode`` from the *verified* outcome into :data:`DELEGATION_MODE`
    for the calling task to read back. The derivation rides the outcome, never a
    connector config label: a verified user-delegated grant (the only path that
    populates ``ResolvedAuth.acquisition``) is ``user_delegated``; any other
    successful machine credential is ``acting_service``; a failed acquisition
    acquired no credential and is ``none`` — authorization failure is never
    delegated success.
    """
    resolved, err = await _resolve_outbound_auth(
        set_name=set_name,
        entry=entry,
        token_client=token_client,
        delegated_client=delegated_client,
        acquisition=acquisition,
    )
    if err is not None or resolved is None:
        DELEGATION_MODE.set("none")
    elif resolved.acquisition is not None:
        DELEGATION_MODE.set("user_delegated")
    else:
        DELEGATION_MODE.set("acting_service")
    return resolved, err


async def _resolve_outbound_auth(
    *,
    set_name: str,
    entry: dict[str, str],
    token_client: "OAuth2TokenClient",
    delegated_client: object | None = None,
    acquisition: object | None = None,
) -> tuple[ResolvedAuth | None, tuple[str, str, str] | None]:
    """The scheme dispatch behind :func:`resolve_outbound_auth` (no side effect)."""

    scheme = scheme_of(entry)
    if scheme == "basic":
        username = entry.get("username")
        password = entry.get("password")
        if not username or not password:
            return None, _error(set_name, "a basic set needs username and password")
        return (
            ResolvedAuth(scheme="basic", auth=httpx.BasicAuth(username, password)),
            None,
        )
    if scheme == "bearer":
        token = entry.get("token")
        if not token:
            return None, _error(set_name, "a bearer set needs a token")
        return (
            ResolvedAuth(scheme="bearer", auth=BearerAuth(token), bearer_token=token),
            None,
        )
    if scheme == "oauth2_client_credentials":
        token, err = await token_client.acquire(set_name, entry)
        if err is not None:
            return None, err
        if not token:
            return None, _error(set_name, "OAuth2 token acquisition returned no token")
        return (
            ResolvedAuth(scheme=scheme, auth=BearerAuth(token), bearer_token=token),
            None,
        )
    if scheme == "oauth2_authorization_code":
        # SPEC-070: a user-delegated set acquires a per-user target token through
        # the dedicated acquisition client — never the machine-grant client. The
        # verified requester/acquisition context is supplied by the connector from
        # the gateway-verified identity; without it (or without a wired delegated
        # client) the resolution fails closed and no token is attached.
        from tool_gateway.tools.user_delegated_client import DelegatedAcquisitionError

        if delegated_client is None or acquisition is None:
            return None, _error(set_name, "delegated acquisition is not enabled")
        try:
            token = await delegated_client.access_token_for_send(acquisition)
        except DelegatedAcquisitionError as exc:
            return None, _delegated_error(set_name, exc)
        bearer = token.token.get_secret_value()
        return (
            ResolvedAuth(
                scheme=scheme,
                auth=BearerAuth(bearer),
                bearer_token=bearer,
                acquisition=token.metadata,
            ),
            None,
        )

    # ``CredentialSetStore`` already rejects unknown schemes at parse time; this
    # is the belt-and-braces fail-closed for a hand-built entry.
    return None, _error(set_name, f"unsupported scheme '{scheme}'")
