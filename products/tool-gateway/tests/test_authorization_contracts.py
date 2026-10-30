"""OQ-7 inert contracts; these tests do not prove OAuth or custody behavior."""

import inspect
import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import SecretStr, ValidationError

from tool_gateway.app import create_app
from tool_gateway.schemas.authorization import (
    MAX_BROWSER_BINDINGS,
    AuthorizationCallbackRequest,
    AuthorizationCallbackResponse,
    AuthorizationRequired,
    AuthorizationStartRequest,
    AuthorizationStartResponse,
    AuthorizationStatus,
    AuthorizationStatusResponse,
    BrowserResetRequest,
    ProviderAuthorizationResponse,
    ProviderUrlRequest,
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
    # The callback body is discriminated (code XOR denial), re-presents the
    # browser cookie jar, and carries no owner identity: the stored state selects
    # the owner/set. Every secret-bearing value is a SecretStr, so it is redacted
    # from reprs and dumped bodies. The cookie NAME is the public challenge uuid
    # and is deliberately not a secret.
    opaque_state = "opaque-state-" + "a" * 48
    jar = {HANDLE: SecretStr("cookie-secret-value")}
    request = AuthorizationCallbackRequest(state=opaque_state, browser_bindings=jar, code="opaque-code")
    provider = ProviderAuthorizationResponse(provider_url="https://provider.test/authorize",
                                             expires_at=EXPIRY)
    for model, secret in ((request, "opaque-code"), (provider, "https://provider.test/authorize")):
        assert secret not in repr(model)
        assert secret not in model.model_dump_json()
    assert "cookie-secret-value" not in repr(request)
    assert "cookie-secret-value" not in request.model_dump_json()
    assert opaque_state not in request.model_dump_json()
    assert HANDLE not in provider.model_dump_json()
    assert request.code.get_secret_value() == "opaque-code"
    assert request.state.get_secret_value() == opaque_state
    assert request.browser_bindings[HANDLE].get_secret_value() == "cookie-secret-value"
    # A caller-supplied owner identity is rejected: extra fields are forbidden.
    with pytest.raises(ValidationError):
        AuthorizationCallbackRequest(state=opaque_state, browser_bindings=jar,
                                     code="opaque-code", owner_sub="mallory")
    # Exactly one outcome: both code and denial, or neither, is rejected.
    with pytest.raises(ValidationError):
        AuthorizationCallbackRequest(state=opaque_state, browser_bindings=jar,
                                     code="opaque-code", denial="access_denied")
    with pytest.raises(ValidationError):
        AuthorizationCallbackRequest(state=opaque_state, browser_bindings=jar)
    # The denial vocabulary is closed; provider error_description free text never
    # fits, so it can never be forwarded onward.
    denied = AuthorizationCallbackRequest(state=opaque_state, browser_bindings=jar, denial="access_denied")
    assert denied.denial == "access_denied" and denied.code is None
    with pytest.raises(ValidationError):
        AuthorizationCallbackRequest(state=opaque_state, browser_bindings=jar, denial="error_description")
    # Empty state is rejected; the cookie jar is bounded above.
    with pytest.raises(ValidationError):
        AuthorizationCallbackRequest(state="", browser_bindings=jar, code="opaque-code")
    oversized = {str(index): SecretStr("s") for index in range(MAX_BROWSER_BINDINGS + 1)}
    with pytest.raises(ValidationError):
        AuthorizationCallbackRequest(state=opaque_state, browser_bindings=oversized, code="opaque-code")
    # The return path is decoupled from status (a browser-verified transaction
    # returns to /authorizations/return/<uuid> for ANY outcome; unknown input
    # returns to /) but stays bounded to a local path.
    assert AuthorizationCallbackResponse(status="authorized").model_dump(exclude_none=True) == {"status": "authorized"}
    assert AuthorizationCallbackResponse(status="failed", return_url="/").return_url == "/"
    return_path = f"/authorizations/return/{HANDLE}"
    assert AuthorizationCallbackResponse(status="canceled", return_url=return_path).return_url == return_path
    for bad_path in ("https://evil.test", "//evil", "/?code=secret", "/%2fevil", "/a/../b", "/#secret"):
        with pytest.raises(ValidationError):
            AuthorizationCallbackResponse(status="authorized", return_url=bad_path)


def test_start_provider_url_and_browser_reset_shapes():
    # The start request carries only the initiating browser's per-challenge cookie
    # secret (bounded); the start response hands back a single-use SecretStr token
    # plus expiry — never a provider URL, an owner, or a challenge.
    start = AuthorizationStartRequest(browser_secret="browser-secret-value")
    assert "browser-secret-value" not in repr(start)
    assert "browser-secret-value" not in start.model_dump_json()
    assert start.browser_secret.get_secret_value() == "browser-secret-value"
    for bad in ("", "x" * 257):
        with pytest.raises(ValidationError):
            AuthorizationStartRequest(browser_secret=bad)
    issued = AuthorizationStartResponse(start_token="start-token-value", expires_at=EXPIRY)
    assert "start-token-value" not in issued.model_dump_json()
    assert issued.start_token.get_secret_value() == "start-token-value"
    with pytest.raises(ValidationError):
        AuthorizationStartResponse(start_token="", expires_at=EXPIRY)
    # The bearerless provider-url navigation presents the start token plus the
    # whole cookie jar; both are bounded and redacted, and no owner is accepted.
    jar = {HANDLE: SecretStr("cookie-secret-value")}
    nav = ProviderUrlRequest(start_token="start-token-value", browser_bindings=jar)
    assert "start-token-value" not in nav.model_dump_json()
    assert "cookie-secret-value" not in nav.model_dump_json()
    assert nav.browser_bindings[HANDLE].get_secret_value() == "cookie-secret-value"
    with pytest.raises(ValidationError):
        ProviderUrlRequest(start_token="", browser_bindings=jar)
    with pytest.raises(ValidationError):
        ProviderUrlRequest(start_token="start-token-value", browser_bindings=jar, owner_sub="mallory")
    # Browser-reset presents only the cookie jar for bounded cleanup and refuses
    # any caller-asserted owner identity.
    reset = BrowserResetRequest(browser_bindings=jar)
    assert "cookie-secret-value" not in reset.model_dump_json()
    with pytest.raises(ValidationError):
        BrowserResetRequest(browser_bindings=jar, owner_sub="mallory")


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
    # The six internal authorization routes are registered unconditionally and
    # fail closed when the runtime gate is off, so they are always advertised.
    paths = create_app().openapi()["paths"]
    for expected in (
        "/api/v2/targets/authorizations/{challenge_id}/start",
        "/api/v2/targets/authorizations/provider-url",
        "/api/v2/targets/authorizations/callback",
        "/api/v2/targets/authorizations/browser-reset",
        "/api/v2/targets/authorizations/{challenge_id}",
        "/api/v2/targets/authorizations/{challenge_id}/cancel",
    ):
        assert expected in paths
