"""OQ-7 inert contracts; these tests do not prove OAuth or custody behavior."""

import inspect
import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from tool_gateway.app import create_app
from tool_gateway.schemas.authorization import (
    AuthorizationCallbackRequest,
    AuthorizationCallbackResponse,
    AuthorizationRequired,
    AuthorizationStatus,
    AuthorizationStatusResponse,
    ProviderAuthorizationResponse,
)
from tool_gateway.services.authorization_transactions import (
    AuthorizationLifetimes,
    AuthorizationTransaction,
    AuthorizationTransactionStore,
)

HANDLE = "11111111-1111-4111-8111-111111111111"
STAMP = "2030-01-01T00:00:00Z"
EXPIRY = "2030-01-01T00:10:00Z"


def test_metadata_matches_shared_contract_and_rejects_secret_fields():
    schema = json.loads((Path(__file__).resolve().parents[3] /
                        "shared/shared-contracts/schemas/tool-result.schema.json").read_text())
    contract = schema["properties"]["authorization_required"]
    assert set(AuthorizationRequired.model_fields) == set(contract["properties"])
    payload = {"challenge_id": HANDLE, "target": "Automation", "expires_at": EXPIRY}
    assert AuthorizationRequired(**payload).model_dump(mode="json") == payload
    jsonschema.validate(payload, contract, format_checker=jsonschema.FormatChecker())
    for key in ("code", "state", "verifier", "access_token", "refresh_token", "provider_url"):
        with pytest.raises(ValidationError):
            AuthorizationRequired(**payload, **{key: "must-not-survive"})
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({**payload, key: "must-not-survive"}, contract)
    for override in ({"challenge_id": "bad"}, {"target": " "},
                     {"target": 1}, {"expires_at": "2030-01-01T00:00:00"}):
        with pytest.raises(ValidationError):
            AuthorizationRequired(**{**payload, **override})


def test_status_projection_has_exact_public_vocabulary():
    assert set(AuthorizationStatus.__args__) == {"pending", "authorized", "canceled", "expired", "failed"}
    for status in AuthorizationStatus.__args__:
        payload = dict(challenge_id=HANDLE, status=status, target="Automation",
                       session_id="ses-1", updated_at=STAMP, expires_at=EXPIRY)
        assert AuthorizationStatusResponse(**payload).model_dump(mode="json") == payload
    with pytest.raises(ValidationError):
        AuthorizationStatusResponse(**{**payload, "status": "approved"})


def test_internal_material_is_redacted_and_never_accepts_browser_identity():
    request = AuthorizationCallbackRequest(code="opaque-code", state=HANDLE)
    provider = ProviderAuthorizationResponse(provider_url="https://provider.test/authorize",
                                             state=HANDLE, expires_at=EXPIRY)
    for model, secret in ((request, "opaque-code"), (provider, "https://provider.test/authorize")):
        assert secret not in repr(model)
        assert secret not in model.model_dump_json()
        assert HANDLE not in model.model_dump_json()
    with pytest.raises(ValidationError):
        AuthorizationCallbackRequest(code="opaque-code", state=HANDLE, owner_sub="mallory")
    assert request.code.get_secret_value() == "opaque-code"
    opaque_state = "opaque-state-" + "a" * 48
    assert AuthorizationCallbackRequest(code="code", state=opaque_state).state.get_secret_value() == opaque_state
    with pytest.raises(ValidationError):
        AuthorizationCallbackRequest(code="code", state="")
    with pytest.raises(ValidationError):
        AuthorizationCallbackResponse(status="authorized")
    with pytest.raises(ValidationError):
        AuthorizationCallbackResponse(status="failed", return_url="/")
    assert AuthorizationCallbackResponse(status="authorized", return_url="/").return_url == "/"
    for bad_path in ("https://evil.test", "//evil", "/?code=secret", "/%2fevil", "/a/../b", "/#secret"):
        with pytest.raises(ValidationError):
            AuthorizationCallbackResponse(status="authorized", return_url=bad_path)
    assert AuthorizationCallbackResponse(status="failed").model_dump(exclude_none=True) == {"status": "failed"}


def test_local_lifetimes_are_strict_and_bounded():
    assert AuthorizationLifetimes().model_dump() == {"start_ttl_seconds": 60, "transaction_ttl_seconds": 600}
    for key in ("start_ttl_seconds", "transaction_ttl_seconds"):
        for invalid in (0, -1, True, "60", 1.5, None):
            with pytest.raises(ValidationError):
                AuthorizationLifetimes(**{key: invalid})
    with pytest.raises(ValidationError):
        AuthorizationLifetimes(start_ttl_seconds=601)


def test_routing_record_is_closed_and_store_interface_is_inert():
    payload = dict(challenge_id=HANDLE, owner_namespace="issuer-1", owner_sub="alice",
                   target="Automation", credential_set_id="automation", config_generation="g1",
                   session_id="ses-1", call_id="call-1", return_url="/",
                   created_at=STAMP, updated_at=STAMP, expires_at=EXPIRY)
    record = AuthorizationTransaction(**payload)
    assert record.status == "pending" and record.consumed is False
    for key in ("code", "state", "pkce_verifier", "provider_url", "access_token", "refresh_token"):
        with pytest.raises(ValidationError):
            AuthorizationTransaction(**payload, **{key: "opaque-secret"})
    with pytest.raises(ValidationError):
        record.owner_sub = "mallory"
    with pytest.raises(ValidationError):
        AuthorizationTransaction(**{**payload, "expires_at": STAMP})
    assert AuthorizationTransactionStore._is_runtime_protocol
    with pytest.raises(TypeError):
        AuthorizationTransactionStore()
    for method in ("get", "claim_callback", "finish", "cancel"):
        params = inspect.signature(getattr(AuthorizationTransactionStore, method)).parameters
        assert {"owner_namespace", "owner_sub", "now"} <= set(params)
    assert not any("/targets/authorizations" in path for path in create_app().openapi()["paths"])
