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


class ProviderAuthorizationResponse(AuthorizationModel):
    """POST .../{challenge_id}/provider-url; backend-only 302 material.

    SecretStr deliberately redacts repr/ordinary dumps. A future authenticated
    transport must explicitly unwrap these values; never serialize this model
    into public responses or use its shape as an endpoint trust decision.
    """

    provider_url: SecretStr = Field(min_length=1)
    state: SecretStr = Field(min_length=1)
    expires_at: AwareDatetime


class AuthorizationCallbackRequest(AuthorizationModel):
    """POST /api/v2/targets/authorizations/callback; never persist this body."""

    code: SecretStr = Field(min_length=1)
    state: SecretStr = Field(min_length=1)


class AuthorizationCallbackResponse(AuthorizationModel):
    """Backend-only safe outcome. Return path is selected from trusted state."""

    status: CallbackStatus
    return_url: LocalReturnPath | None = None

    @model_validator(mode="after")
    def _success_return_path(self) -> "AuthorizationCallbackResponse":
        if (self.status == "authorized") != (self.return_url is not None):
            raise ValueError("only authorized callbacks require a trusted return path")
        return self
