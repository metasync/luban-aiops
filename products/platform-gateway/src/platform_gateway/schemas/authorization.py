"""SPEC-070 OQ-7 portal wire shapes; no authorization routes are registered.

Initiation POST and cancel POST have no request body. Browser start GET uses
an opaque path capability; callback GET contains provider query material and
must never use an ordinary logged request-body/response projection. These
models carry only the two public JSON responses. Their construction does not
verify the caller, ownership, target entitlement, or targets:authorize policy.
"""

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

UUID4_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
AuthorizationStatus = Literal["pending", "authorized", "canceled", "expired", "failed"]


class AuthorizationStartResponse(BaseModel):
    """POST /api/v1/targets/authorizations/{challenge_id}/start response.

    Only a backend start path is accepted; no arbitrary redirect URL is a
    public response. The single-use owner-bound handle expires no later than
    its transaction. Runtime minting/consumption remains foundation work.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    start_url: str = Field(
        strict=True,
        pattern=r"^/api/v1/targets/authorizations/start/[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        repr=False,
    )
    expires_at: AwareDatetime


class AuthorizationStatusResponse(BaseModel):
    """GET /api/v1/targets/authorizations/{challenge_id}; owner-scoped status."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    challenge_id: Annotated[str, Field(strict=True, pattern=UUID4_PATTERN)]
    status: AuthorizationStatus
    target: str = Field(strict=True, min_length=1, pattern=r"\S")
    session_id: str = Field(strict=True, min_length=1)
    updated_at: AwareDatetime
    expires_at: AwareDatetime
