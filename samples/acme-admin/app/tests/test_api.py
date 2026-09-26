"""SPEC-059 R-1: the store and the JSON surface, provable with no cluster.

Covers the acceptance criteria: health keys and types, hello's echo and pattern
refusal, the seeded user set, each mutation bumping `last_modified` **and**
`revision`, the 404 and 409 cases, auth required on every `/api/users*` route
and absent on `/healthz` and `/api/hello`, and `reset-demo` refusing without its
header and restoring the exact seed with it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from acme_admin.api import HEALTH_KEYS, HELLO_NAME_PATTERN
from acme_admin.auth import ADMIN_USERNAME, PASSWORD_ENV
from acme_admin.main import (
    SECRET_NAME,
    SYNC_SCRIPT,
    create_app,
    missing_credential_message,
)
from acme_admin.store import (
    SEED_REVISION,
    STORE,
    InvalidPassword,
    NoOpMutation,
    UnknownUser,
)

DEMO_RESET_HEADER = "X-Luban-Demo-Reset"
SEEDED_USERNAMES = ["alice", "bob", "carol", "dave"]


def _seed_fingerprint() -> dict[str, object]:
    """Everything `reseed()` must restore, in one comparable value."""
    return {
        "revision": STORE.revision,
        "last_reset": STORE.last_reset,
        "users": [user.to_detail_dict() for user in STORE.all_users()],
    }


# --- /healthz ---------------------------------------------------------------


def test_healthz_carries_exactly_the_eight_keys(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == set(HEALTH_KEYS)
    assert len(HEALTH_KEYS) == 8


def test_healthz_value_types_are_what_a_check_can_assert(client: TestClient) -> None:
    body = client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["service"] == "acme-admin"
    assert isinstance(body["version"], str) and body["version"]
    assert isinstance(body["hostname"], str) and body["hostname"]
    # `bool` is an `int` subclass; exclude it so a truthy flag cannot pass.
    assert isinstance(body["uptime_seconds"], (int, float))
    assert not isinstance(body["uptime_seconds"], bool)
    assert isinstance(body["started_at"], str) and body["started_at"].endswith("+00:00")
    assert body["users_seeded"] == len(SEEDED_USERNAMES)
    assert body["store_revision"] == SEED_REVISION


def test_healthz_needs_no_credentials(client: TestClient) -> None:
    assert client.get("/healthz").status_code == 200


def test_healthz_uptime_grows_and_started_at_does_not(client: TestClient) -> None:
    first = client.get("/healthz").json()
    second = client.get("/healthz").json()
    assert second["started_at"] == first["started_at"]
    assert second["uptime_seconds"] >= first["uptime_seconds"]


# --- /api/hello -------------------------------------------------------------


def test_hello_echoes_the_default_name(client: TestClient) -> None:
    assert client.get("/api/hello").json() == {"message": "hello, world!"}


def test_hello_echoes_a_supplied_name(client: TestClient) -> None:
    assert client.get("/api/hello", params={"name": "luban"}).json() == {
        "message": "hello, luban!"
    }


def test_hello_needs_no_credentials(client: TestClient) -> None:
    assert client.get("/api/hello").status_code == 200


@pytest.mark.parametrize(
    "name",
    [
        "<script>alert(1)</script>",  # markup, the reason the pattern exists
        "alice@example.com",  # '@' is outside the pattern
        "/admin/users/",  # path separators
        "a" * 65,  # one past the bound
        "has\ttab",
        "",  # zero-length is outside {1,64}
    ],
)
def test_hello_refuses_names_outside_the_pattern(
    client: TestClient, name: str
) -> None:
    assert client.get("/api/hello", params={"name": name}).status_code == 422


def test_hello_accepts_the_widest_name_inside_the_pattern(
    client: TestClient,
) -> None:
    name = ("A.b_c-d 9" * 8)[:64]  # 64 characters, every one of them permitted
    assert len(name) == 64
    response = client.get("/api/hello", params={"name": name})
    assert response.status_code == 200
    assert response.json() == {"message": f"hello, {name}!"}


def test_hello_pattern_constant_is_the_documented_one() -> None:
    assert HELLO_NAME_PATTERN == r"^[A-Za-z0-9 _.-]{1,64}$"


# --- the seeded set ---------------------------------------------------------


def test_seeded_user_set(admin_client: TestClient) -> None:
    body = admin_client.get("/api/users").json()
    assert [row["username"] for row in body["users"]] == SEEDED_USERNAMES
    assert body["store_revision"] == SEED_REVISION


def test_one_seeded_user_starts_locked(admin_client: TestClient) -> None:
    rows = {row["username"]: row for row in admin_client.get("/api/users").json()["users"]}
    assert rows["dave"]["locked"] is True
    assert [name for name in rows if rows[name]["locked"]] == ["dave"]


def test_list_rows_carry_exactly_the_four_contract_fields(
    admin_client: TestClient,
) -> None:
    for row in admin_client.get("/api/users").json()["users"]:
        assert set(row) == {"username", "locked", "last_modified", "revision"}


def test_detail_row_adds_identity_and_password_changed_at(
    admin_client: TestClient,
) -> None:
    detail = admin_client.get("/api/users/alice").json()
    assert set(detail) == {
        "username",
        "locked",
        "last_modified",
        "revision",
        "full_name",
        "email",
        "role",
        "password_changed_at",
    }
    assert detail["email"] == "alice@example.com"
    assert detail["password_changed_at"] is None


def test_identifier_resolution_accepts_email_and_is_case_insensitive(
    admin_client: TestClient,
) -> None:
    by_name = admin_client.get("/api/users/alice").json()
    by_email = admin_client.get("/api/users/alice@example.com").json()
    by_upper = admin_client.get("/api/users/ALICE@Example.COM").json()
    assert by_name == by_email == by_upper


# --- authentication ---------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/users"),
        ("GET", "/api/users/alice"),
        ("POST", "/api/users/alice/lock"),
        ("POST", "/api/users/alice/unlock"),
        ("POST", "/api/users/alice/password"),
    ],
)
def test_every_users_route_requires_credentials(
    client: TestClient, method: str, path: str
) -> None:
    response = client.request(method, path, json={"password": "x"})
    assert response.status_code == 401
    assert response.json()["error"] == "UNAUTHORIZED"
    # The challenge is what makes `curl -u` retry instead of guessing.
    assert response.headers["WWW-Authenticate"] == 'Basic realm="acme-admin"'


def test_a_wrong_password_is_refused_with_the_same_envelope(
    client: TestClient,
) -> None:
    client.auth = (ADMIN_USERNAME, "not-the-operator-password")
    response = client.get("/api/users")
    assert response.status_code == 401
    assert response.json()["error"] == "UNAUTHORIZED"


def test_a_seeded_user_is_not_an_account(client: TestClient, password: str) -> None:
    """`alice` is a record, not a login: no demo password exists to guess."""
    client.auth = ("alice", password)
    assert client.get("/api/users").status_code == 401


# --- mutations --------------------------------------------------------------


def test_lock_bumps_last_modified_and_revision(admin_client: TestClient) -> None:
    before = admin_client.get("/api/users/alice").json()
    response = admin_client.post("/api/users/alice/lock")
    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "lock"
    assert body["locked"] is True
    assert body["revision"] == before["revision"] + 1
    assert body["last_modified"] != before["last_modified"]
    # The store and the response agree.
    assert admin_client.get("/api/users/alice").json()["revision"] == body["revision"]


def test_second_identical_lock_is_409_and_bumps_nothing(
    admin_client: TestClient,
) -> None:
    first = admin_client.post("/api/users/alice/lock")
    assert first.status_code == 200
    revision = first.json()["revision"]

    second = admin_client.post("/api/users/alice/lock")
    assert second.status_code == 409
    assert second.json()["error"] == "NO_OP_MUTATION"
    assert admin_client.get("/api/users/alice").json()["revision"] == revision
    assert admin_client.get("/healthz").json()["store_revision"] == revision


def test_unlock_bumps_both_fields(admin_client: TestClient) -> None:
    admin_client.post("/api/users/alice/lock")
    before = admin_client.get("/api/users/alice").json()
    body = admin_client.post("/api/users/alice/unlock").json()
    assert body["locked"] is False
    assert body["revision"] == before["revision"] + 1
    assert body["last_modified"] != before["last_modified"]


def test_unlocking_an_unlocked_user_is_409(admin_client: TestClient) -> None:
    assert admin_client.post("/api/users/alice/unlock").status_code == 409


def test_the_pre_locked_user_can_be_unlocked(admin_client: TestClient) -> None:
    body = admin_client.post("/api/users/dave/unlock").json()
    assert body["locked"] is False
    assert body["revision"] == SEED_REVISION + 1


def test_password_reset_bumps_both_fields_and_records_when(
    admin_client: TestClient,
) -> None:
    before = admin_client.get("/api/users/alice").json()
    assert before["password_changed_at"] is None

    response = admin_client.post(
        "/api/users/alice/password", json={"password": "a-one-time-value"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "password_reset"
    assert body["revision"] == before["revision"] + 1
    assert body["last_modified"] != before["last_modified"]
    assert body["password_changed_at"] == body["last_modified"]


def test_the_reset_value_is_never_stored_or_echoed(admin_client: TestClient) -> None:
    """No plaintext survives: not in the response, not in the store."""
    one_time = "a-one-time-value"
    response = admin_client.post(
        "/api/users/alice/password", json={"password": one_time}
    )
    assert one_time not in response.text
    assert one_time not in str(STORE.users["alice"].__dict__)
    for user in STORE.all_users():
        assert one_time not in str(user.to_detail_dict())


def test_an_empty_reset_body_is_refused_by_validation(
    admin_client: TestClient,
) -> None:
    assert (
        admin_client.post("/api/users/alice/password", json={"password": ""}).status_code
        == 422
    )


def test_a_reset_body_without_the_field_is_refused(admin_client: TestClient) -> None:
    assert admin_client.post("/api/users/alice/password", json={}).status_code == 422


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/users/nobody"),
        ("POST", "/api/users/nobody/lock"),
        ("POST", "/api/users/nobody/unlock"),
    ],
)
def test_an_unknown_identifier_is_a_real_404(
    admin_client: TestClient, method: str, path: str
) -> None:
    response = admin_client.request(method, path)
    assert response.status_code == 404
    assert response.json()["error"] == "UNKNOWN_USER"


def test_an_unknown_identifier_cannot_reset_a_password(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/api/users/nobody/password", json={"password": "a-one-time-value"}
    )
    assert response.status_code == 404
    assert response.json()["error"] == "UNKNOWN_USER"


def test_mutations_are_visible_on_the_list_route(admin_client: TestClient) -> None:
    admin_client.post("/api/users/alice/lock")
    rows = {row["username"]: row for row in admin_client.get("/api/users").json()["users"]}
    assert rows["alice"]["locked"] is True
    assert rows["bob"]["locked"] is False


# --- the store, directly ----------------------------------------------------


def test_store_raises_typed_errors() -> None:
    with pytest.raises(UnknownUser):
        STORE.lock("nobody")
    with pytest.raises(NoOpMutation):
        STORE.lock("dave")  # seeded locked
    with pytest.raises(InvalidPassword):
        STORE.set_password("alice", "")


def test_revision_is_monotonic_across_different_users() -> None:
    first = STORE.lock("alice").revision
    second = STORE.set_password("bob", "a-one-time-value").revision
    third = STORE.lock("carol").revision
    assert first == SEED_REVISION + 1
    assert second > first
    assert third > second


def test_reseed_restores_the_exact_seed() -> None:
    started_at = STORE.started_at
    seed = _seed_fingerprint()
    STORE.lock("alice")
    STORE.set_password("bob", "a-one-time-value")
    assert _seed_fingerprint() != seed

    STORE.reseed()
    assert _seed_fingerprint() == seed
    # Uptime is *not* reset, so the restored timestamps match the original seed.
    assert STORE.started_at == started_at


# --- /internal/reset-demo ---------------------------------------------------


def test_reset_demo_refuses_without_the_header(client: TestClient) -> None:
    response = client.post("/internal/reset-demo")
    assert response.status_code == 403
    assert response.json()["error"] == "DEMO_RESET_HEADER_REQUIRED"


def test_reset_demo_restores_the_exact_seed_with_the_header(
    admin_client: TestClient,
) -> None:
    seed = _seed_fingerprint()
    admin_client.post("/api/users/alice/lock")
    admin_client.post("/api/users/bob/password", json={"password": "a-one-time-value"})
    assert _seed_fingerprint() != seed

    response = admin_client.post("/internal/reset-demo", headers={DEMO_RESET_HEADER: "1"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "reseeded"
    assert body["store_revision"] == SEED_REVISION
    assert body["users"] == SEEDED_USERNAMES
    assert _seed_fingerprint() == seed


def test_reset_demo_needs_no_admin_credential(admin_client: TestClient) -> None:
    """The header, not the credential, is the gate — and `http.post` cannot send it."""
    admin_client.post("/api/users/alice/lock")
    admin_client.auth = None
    assert (
        admin_client.post(
            "/internal/reset-demo", headers={DEMO_RESET_HEADER: "1"}
        ).status_code
        == 200
    )


def test_reset_demo_drops_sessions(browser: TestClient) -> None:
    assert browser.get("/admin/users/").status_code == 200
    browser.post("/internal/reset-demo", headers={DEMO_RESET_HEADER: "1"})
    response = browser.get("/admin/users/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/admin/"


# --- fail closed at startup -------------------------------------------------


def test_startup_refuses_to_run_without_the_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(PASSWORD_ENV, raising=False)
    with pytest.raises(RuntimeError) as excinfo:
        with TestClient(create_app()):
            pass  # pragma: no cover - the lifespan raises before this
    message = str(excinfo.value)
    assert PASSWORD_ENV in message
    assert SECRET_NAME in message
    assert SYNC_SCRIPT in message


def test_startup_refuses_an_empty_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PASSWORD_ENV, "")
    with pytest.raises(RuntimeError):
        with TestClient(create_app()):
            pass  # pragma: no cover


def test_the_failure_message_is_the_one_the_lifespan_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(PASSWORD_ENV, raising=False)
    with pytest.raises(RuntimeError) as excinfo:
        with TestClient(create_app()):
            pass  # pragma: no cover
    assert str(excinfo.value) == missing_credential_message()


def test_acceptance_user_is_opt_in_startup_only(monkeypatch, password):
    monkeypatch.setenv("ACME_ACCEPTANCE_USER", "spec063-accept")
    seed = _seed_fingerprint()
    with TestClient(create_app()) as client:
        client.auth = ("admin", password)
        user = client.get("/api/users/spec063-accept").json()
        assert user["revision"] == 0 and user["locked"] is False
        assert user["password_changed_at"] is None
        assert client.get("/healthz").json()["users_seeded"] == 5
        assert client.post("/api/users/spec063-accept/lock").json()["revision"] == 1
        assert client.get("/api/users/carol").json()["revision"] == 0
    assert seed != _seed_fingerprint()


@pytest.mark.parametrize("username", ["", "carol", "../carol", "spec063-", "spec063-" + "a" * 25])
def test_acceptance_user_rejects_invalid_names(monkeypatch, username):
    monkeypatch.setenv("ACME_ACCEPTANCE_USER", username)
    seed = _seed_fingerprint()
    with pytest.raises(ValueError):
        with TestClient(create_app()):
            pass
    assert _seed_fingerprint() == seed


def test_acceptance_user_cannot_overwrite_or_follow_mutations():
    from acme_admin.store import Store

    store = Store()
    store.seed_acceptance_user("spec063-accept")
    with pytest.raises(ValueError):
        store.seed_acceptance_user("spec063-accept")
    store.lock("spec063-accept")
    with pytest.raises(ValueError):
        store.seed_acceptance_user("spec063-another")
    assert store.resolve("spec063-accept").revision == 1
