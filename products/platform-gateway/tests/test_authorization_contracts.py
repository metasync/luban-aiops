"""Public OQ-7 shape/omission checks; no OAuth handlers are enabled."""

import pytest
from pydantic import ValidationError

from platform_gateway.app import create_app
from platform_gateway.schemas.authorization import (
    AuthorizationStartResponse,
    AuthorizationStatus,
    AuthorizationStatusResponse,
)

HANDLE = "11111111-1111-4111-8111-111111111111"
STAMP = "2030-01-01T00:00:00Z"


def test_start_only_allows_backend_capability_path():
    payload = {"start_url": f"/api/v1/targets/authorizations/start/{HANDLE}", "expires_at": STAMP}
    assert AuthorizationStartResponse(**payload).model_dump(mode="json") == payload
    for url in ("https://provider.test", "//provider.test", "/other", payload["start_url"] + "?code=x",
                payload["start_url"] + "#x", payload["start_url"] + "/", payload["start_url"] + "\n"):
        with pytest.raises(ValidationError):
            AuthorizationStartResponse(**{**payload, "start_url": url})
    for key in ("state", "code", "provider_url", "access_token", "refresh_token", "owner_sub"):
        with pytest.raises(ValidationError):
            AuthorizationStartResponse(**payload, **{key: "must-not-survive"})


def test_status_has_exact_safe_fields_and_five_states():
    assert set(AuthorizationStatus.__args__) == {"pending", "authorized", "canceled", "expired", "failed"}
    for status in AuthorizationStatus.__args__:
        payload = dict(challenge_id=HANDLE, status=status, target="Automation",
                       session_id="ses-1", updated_at=STAMP, expires_at=STAMP)
        assert AuthorizationStatusResponse(**payload).model_dump(mode="json") == payload
    with pytest.raises(ValidationError):
        AuthorizationStatusResponse(**{**payload, "status": "approved"})
    for key in ("code", "state", "provider_url", "access_token", "verifier"):
        with pytest.raises(ValidationError):
            AuthorizationStatusResponse(**payload, **{key: "must-not-survive"})
    with pytest.raises(ValidationError):
        AuthorizationStatusResponse(**{**payload, "updated_at": "2030-01-01T00:00:00"})


def test_ratified_authorization_routes_are_registered():
    base = "/api/v1/targets/authorizations"
    paths = create_app().openapi()["paths"]
    assert {path for path in paths if "/targets/authorizations" in path} == {
        base + suffix for suffix in ("/callback", "/start/{start_token}", "/browser-reset",
                                     "/{challenge_id}", "/{challenge_id}/start", "/{challenge_id}/cancel")
    }
