"""SPEC-070 OQ-7 wire models only; no routes, provider calls, or custody.

Shape validation is not authorization. Runtime handlers must authenticate the
service caller, recover trusted owner/config bindings, and enforce endpoint and
return-path allowlists before using any internal value.
"""

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr, model_validator

UUID4_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
ChallengeId = Annotated[str, Field(strict=True, pattern=UUID4_PATTERN)]
DisplayLabel = Annotated[str, Field(strict=True, min_length=1, pattern=r"\S")]
LocalReturnPath = Annotated[str, Field(strict=True, pattern=r"^/(?:[A-Za-z0-9_-][A-Za-z0-9/_-]*)?$")]
AuthorizationStatus = Literal["pending", "authorized", "canceled", "expired", "failed"]
CallbackStatus = Literal["authorized", "canceled", "expired", "failed"]

# SPEC-070 initiating-browser binding: the browser presents its whole
# ``__Host-luban-oauth-<challenge_uuid>`` cookie jar on the bearerless
# provider-url navigation and again on the callback. The jar is bounded here as a
# body-size guard; the transaction store's ``select_browser_secret`` is the
# authoritative validator (it mirrors this bound and fails closed on an
# ambiguous/malformed/oversized jar). Values are ``SecretStr`` so a cookie secret
# never leaks through a repr, a log line, or a dumped body.
MAX_BROWSER_BINDINGS = 8
BrowserBindings = Annotated[
    dict[str, SecretStr], Field(max_length=MAX_BROWSER_BINDINGS)
]

# A normalized provider-denial outcome (RFC 6749 §4.1.2.1 / OIDC). The
# platform-gateway callback edge maps the provider's ``error`` parameter into this
# closed set and NEVER forwards ``error_description`` free text, so no provider
# internal reaches the tool-gateway, a response body, or a log line.
DenialReason = Literal[
    "access_denied",
    "interaction_required",
    "login_required",
    "consent_required",
    "invalid_request",
    "invalid_scope",
    "unauthorized_client",
    "unsupported_response_type",
    "server_error",
    "temporarily_unavailable",
]


class AuthorizationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class AuthorizationRequired(AuthorizationModel):
    """Public, opaque challenge metadata; carries no execution authority."""

    challenge_id: ChallengeId
    target: DisplayLabel
    expires_at: AwareDatetime | None = None


class AuthorizationStatusResponse(AuthorizationModel):
    """GET /api/v2/targets/authorizations/{challenge_id}; owner-scoped."""

    challenge_id: ChallengeId
    status: AuthorizationStatus
    target: DisplayLabel
    session_id: str = Field(strict=True, min_length=1)
    updated_at: AwareDatetime
    expires_at: AwareDatetime


class AuthorizationStartRequest(AuthorizationModel):
    """POST /api/v2/targets/authorizations/{challenge_id}/start; human bearer.

    Carries only the initiating browser's freshly generated per-challenge cookie
    secret. The route rechecks policy, the administered owner->target mapping,
    current invocation entitlement, and challenge ownership before minting a
    start handle; this body confers no authority by itself.
    """

    browser_secret: SecretStr = Field(min_length=1, max_length=256)


class AuthorizationStartResponse(AuthorizationModel):
    """Backend start handle for the bearerless provider-url navigation.

    ``start_token`` is the single-use handle the same browser presents to
    ``POST /provider-url``; it is a SecretStr so it never reaches a log line, a
    response repr, or portal JavaScript.
    """

    start_token: SecretStr = Field(min_length=1)
    expires_at: AwareDatetime


class ProviderUrlRequest(AuthorizationModel):
    """POST /api/v2/targets/authorizations/provider-url; workload only.

    Bearerless browser navigation knows the single-use start token (not a
    trustworthy challenge owner) and re-presents its whole cookie jar. The route
    consumes the start handle and verifies the browser proof before returning a
    provider URL, so a repeated navigation cannot obtain another URL.
    """

    start_token: SecretStr = Field(min_length=1)
    browser_bindings: BrowserBindings


class ProviderAuthorizationResponse(AuthorizationModel):
    """POST /api/v2/targets/authorizations/provider-url; backend-only 302 material.

    SecretStr deliberately redacts repr/ordinary dumps. The authenticated
    platform-gateway transport unwraps ``provider_url`` into a bare 302 Location;
    never serialize this model into a public response or use its shape as an
    endpoint trust decision. The provider URL already embeds the opaque state, so
    the state is not returned as a separate secret surface.
    """

    provider_url: SecretStr = Field(min_length=1)
    expires_at: AwareDatetime


class AuthorizationCallbackRequest(AuthorizationModel):
    """POST /api/v2/targets/authorizations/callback; workload only, never persisted.

    A discriminated body: the browser re-presents its cookie jar and the
    platform-gateway callback edge supplies either the provider ``code`` or a
    normalized ``denial`` outcome — never both, never neither, and never the
    provider's ``error_description`` free text. The stored state selects the
    owner and credential set; this request supplies neither.
    """

    state: SecretStr = Field(min_length=1)
    browser_bindings: BrowserBindings
    code: Annotated[SecretStr, Field(min_length=1)] | None = None
    denial: DenialReason | None = None

    @model_validator(mode="after")
    def _exactly_one_outcome(self) -> "AuthorizationCallbackRequest":
        if (self.code is None) == (self.denial is None):
            raise ValueError("callback carries exactly one of code or denial")
        return self


class AuthorizationCallbackResponse(AuthorizationModel):
    """Backend-only safe outcome. Return path is selected from trusted state.

    A browser-verified transaction returns to the server-chosen
    ``/authorizations/return/<challenge_uuid>`` for ANY outcome; unknown or
    mismatched input returns to ``/``. ``return_url`` is therefore decoupled from
    ``status`` and stays bounded to a local path — arbitrary return URLs remain
    forbidden by ``LocalReturnPath``.
    """

    status: CallbackStatus
    return_url: LocalReturnPath | None = None


class BrowserResetRequest(AuthorizationModel):
    """POST /api/v2/targets/authorizations/browser-reset; human bearer.

    Portal logout presents the owner's whole cookie jar so the route can cancel
    that owner's matching pending browser transactions and expire their cookies.
    Bounded cleanup only: it never revokes target credentials or creates a cookie
    login session, and it accepts no caller-asserted owner identity.
    """

    browser_bindings: BrowserBindings
