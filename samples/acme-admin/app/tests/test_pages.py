"""SPEC-059 R-2: the six URL shapes and the element-id contract.

The id contract is **transcribed below** rather than read out of a shipped
ConfigMap. It originally lived in the static `browser-check-target` target's
pages ConfigMap, which SPEC-061 retired along with the mock app; what that
ConfigMap carried is the set of element ids the `acme-admin` console must keep
rendering, because shipped skills' `web.extract` / `web.click` selectors address
them. Inlining the set keeps the guard mechanical — a template edit that renames
an id still fails here — without depending on a retired artifact.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from acme_admin.auth import ADMIN_USERNAME, SESSION_COOKIE
from acme_admin.store import SEED_REVISION, STORE

# The element-id contract, per route: the ids the `acme-admin` console must keep
# rendering because shipped skills' `web.extract` / `web.click` selectors address
# them. Originally read out of the static `browser-check-target` pages ConfigMap;
# SPEC-061 retired that mock app, so the contract is transcribed here.
# `test_the_contract_covers_28_ids` pins the count the spec quotes (28), derived
# from this set minus `EXTRA_IDS`.
CONTRACT: dict[str, set[str]] = {
    "/": {"login-form", "login-status", "password", "sign-in", "username"},
    "/status": {"api-status", "checked-at", "db-status", "queue-status"},
    "/admin/": {
        "admin-auth-status",
        "admin-login-form",
        "admin-login-status",
        "admin-password",
        "admin-sign-in",
        "admin-username",
    },
    "/admin/users/": {
        "last-reset-status",
        "last-reset-time",
        "last-reset-user",
        "no-resets",
        "user-table",
    },
    "/admin/users/reset/": {
        "confirm-password",
        "confirm-reset",
        "new-password",
        "reset-form",
        "reset-status",
        "target-user",
    },
    "/admin/users/reset/done/": {
        "back-to-users",
        "confirmation-message",
        "reset-timestamp",
    },
}

# Ids `acme-admin` renders beyond the contract above. A superset costs nothing
# and keeps the retarget honest: `reset-timestamp` is served by the done page but
# omitted from the spec's 28-id list, the `user-row-*` ids are what
# `CheckUserStatus` reads a single row's state from, and the revision ids expose
# the state the JSON API already reports.
EXTRA_IDS = {
    "reset-timestamp",
    "store-revision",
    "users-seeded",
    "user-row-alice",
    "user-row-bob",
    "user-row-carol",
    "user-row-dave",
}

# The one-time value used throughout. It must never reach a served document.
ONE_TIME = "a-one-time-value"


class IdCollector(HTMLParser):
    """Collect every `id` attribute, so ids in JS-built markup still count."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name == "id" and value:
                self.ids.append(value)


def ids_in(markup: str) -> set[str]:
    parser = IdCollector()
    parser.feed(markup)
    return set(parser.ids)


@pytest.fixture(scope="module")
def contract() -> dict[str, set[str]]:
    return CONTRACT


def _render(browser: TestClient, path: str) -> str:
    response = browser.get(path)
    assert response.status_code == 200, f"{path} -> {response.status_code}"
    return response.text


# --- the id contract --------------------------------------------------------


def test_the_contract_covers_28_ids(contract: dict[str, set[str]]) -> None:
    """The count the spec quotes, derived rather than asserted from memory.

    The static target's done page also carries `reset-timestamp`, which the
    spec's list omits — `acme-admin` renders it too, since being a superset
    costs nothing and dropping it would be a silent retarget regression.
    """
    every_id = set().union(*contract.values()) - EXTRA_IDS
    assert len(every_id) == 28, sorted(every_id)


def test_every_route_renders_its_full_contract_id_set(
    browser: TestClient, contract: dict[str, set[str]]
) -> None:
    for path, expected in contract.items():
        found = ids_in(_render(browser, path))
        missing = expected - found
        assert not missing, f"{path} is missing {sorted(missing)}"
        unexpected = found - expected - EXTRA_IDS
        assert not unexpected, f"{path} grew unaccounted-for ids {sorted(unexpected)}"


def test_no_contract_id_is_lost_anywhere_in_the_app(
    browser: TestClient, contract: dict[str, set[str]]
) -> None:
    rendered = set().union(
        *[ids_in(_render(browser, path)) for path in contract]
    )
    assert set().union(*contract.values()) <= rendered


def test_the_done_page_also_carries_reset_timestamp(browser: TestClient) -> None:
    assert "reset-timestamp" in ids_in(_render(browser, "/admin/users/reset/done/"))


def test_the_users_table_carries_one_addressable_row_per_user(
    browser: TestClient,
) -> None:
    markup = _render(browser, "/admin/users/")
    for username in ("alice", "bob", "carol", "dave"):
        assert f'id="user-row-{username}"' in markup
        assert f'data-username="{username}"' in markup


# --- the six URL shapes -----------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/status",
        "/admin/",
        "/admin/users/",
        "/admin/users/reset/",
        "/admin/users/reset/done/",
    ],
)
def test_every_route_resolves_for_a_signed_in_session(
    browser: TestClient, path: str
) -> None:
    assert browser.get(path).status_code == 200


@pytest.mark.parametrize(
    "path", ["/admin/users/", "/admin/users/reset/", "/admin/users/reset/done/"]
)
def test_console_pages_redirect_to_login_without_a_session(
    client: TestClient, path: str
) -> None:
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/admin/"


def test_public_pages_need_no_session(client: TestClient) -> None:
    assert client.get("/").status_code == 200
    assert client.get("/status").status_code == 200
    assert client.get("/admin/").status_code == 200


# --- the login: validates, and auto-submits ---------------------------------


def test_a_valid_login_mints_a_session(browser: TestClient) -> None:
    assert browser.get("/admin/users/").status_code == 200


def test_a_valid_login_sets_an_httponly_lax_cookie(
    client: TestClient, password: str
) -> None:
    response = client.post(
        "/admin/login",
        json={"username": ADMIN_USERNAME, "password": password},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["signed_in_as"] == ADMIN_USERNAME
    assert body["redirect"] == "/admin/users/"

    set_cookie = response.headers["set-cookie"]
    assert set_cookie.startswith(f"{SESSION_COOKIE}=")
    assert "HttpOnly" in set_cookie
    assert "SameSite=Lax" in set_cookie or "samesite=lax" in set_cookie.lower()


def test_an_invalid_login_is_refused_and_mints_nothing(client: TestClient) -> None:
    response = client.post(
        "/admin/login",
        json={"username": ADMIN_USERNAME, "password": "not-the-operator-password"},
    )
    assert response.status_code == 401
    assert response.json()["error"] == "INVALID_CREDENTIALS"
    assert "set-cookie" not in {k.lower() for k in response.headers}
    # And the refusal leaves the console pages closed.
    assert client.get("/admin/users/", follow_redirects=False).status_code == 302


def test_a_seeded_user_cannot_sign_in_to_the_console(
    client: TestClient, password: str
) -> None:
    response = client.post(
        "/admin/login", json={"username": "alice", "password": password}
    )
    assert response.status_code == 401


def test_the_admin_login_auto_submits_on_a_100ms_timer(client: TestClient) -> None:
    """Load-bearing (SPEC-051): authentication must cost no write-tier click."""
    markup = client.get("/admin/").text
    assert "_autoLoginTimer" in markup
    assert "setInterval" in markup
    assert "}, 100);" in markup
    assert "adminDoLogin();" in markup


def test_the_landing_login_has_no_auto_submit_timer(client: TestClient) -> None:
    """Only `/admin/` auto-submits; a flow signing in on `/` spends a click."""
    markup = client.get("/").text
    assert "_autoLoginTimer" not in markup
    assert "setInterval" not in markup


def test_both_login_forms_post_to_the_one_login_endpoint(client: TestClient) -> None:
    for path in ("/", "/admin/"):
        assert 'fetch("/admin/login"' in client.get(path).text


def test_a_signed_in_admin_page_reports_the_session(browser: TestClient) -> None:
    assert "Signed in as admin" in browser.get("/admin/").text


# --- the reset form: pre-fills, never auto-submits, really mutates ----------


def test_the_reset_form_pre_fills_from_the_query_without_serving_the_value(
    browser: TestClient,
) -> None:
    response = browser.get(
        "/admin/users/reset/", params={"user": "alice@example.com", "newpw": ONE_TIME}
    )
    assert response.status_code == 200
    markup = response.text
    # The pre-fill is client-side, so neither the target nor the one-time value
    # ever appears in a served document a `web.snapshot` could capture.
    assert ONE_TIME not in markup
    assert "alice@example.com" not in markup
    assert 'params.get("newpw")' in markup
    assert 'id="target-user"' in markup


def test_the_reset_form_keeps_the_does_not_auto_submit_contract(
    browser: TestClient,
) -> None:
    markup = browser.get("/admin/users/reset/").text
    assert "does NOT" in markup  # the SPEC-051 comment, preserved
    assert "setInterval" not in markup
    assert "_autoLoginTimer" not in markup


def test_pre_filling_a_reset_does_not_mutate_the_store(browser: TestClient) -> None:
    before = STORE.revision
    browser.get(
        "/admin/users/reset/", params={"user": "alice@example.com", "newpw": ONE_TIME}
    )
    assert STORE.revision == before == SEED_REVISION
    assert STORE.last_reset is None


def test_the_confirm_click_is_the_mutation(browser: TestClient) -> None:
    """`GET` pre-fills; only the `POST` the click issues changes anything."""
    response = browser.post(
        "/admin/users/reset/",
        json={
            "user": "alice@example.com",
            "new_password": ONE_TIME,
            "confirm_password": ONE_TIME,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["username"] == "alice"
    assert body["revision"] == SEED_REVISION + 1
    assert body["redirect"].startswith("/admin/users/reset/done/?user=alice&at=")

    assert STORE.users["alice"].password_changed_at == body["password_changed_at"]
    assert STORE.users["alice"].revision == body["revision"]
    assert STORE.last_reset == {
        "username": "alice",
        "at": body["password_changed_at"],
    }


def test_the_reset_is_visible_on_the_user_list(browser: TestClient) -> None:
    browser.post(
        "/admin/users/reset/",
        json={
            "user": "alice@example.com",
            "new_password": ONE_TIME,
            "confirm_password": ONE_TIME,
        },
    )
    markup = browser.get("/admin/users/").text
    assert 'id="last-reset-status"' in markup
    assert "display:block" in markup
    assert " alice " in markup
    assert "No recent password resets." in markup  # present but hidden
    assert 'id="no-resets" style="display:none' in markup


def test_a_fresh_console_reports_no_resets(browser: TestClient) -> None:
    markup = browser.get("/admin/users/").text
    assert 'id="last-reset-status"' in markup and "display:none" in markup
    assert 'id="no-resets" style="display:block' in markup


def test_the_reset_form_posts_through_fetch(browser: TestClient) -> None:
    assert 'fetch("/admin/users/reset/"' in browser.get("/admin/users/reset/").text


def test_mismatched_confirmation_is_refused(browser: TestClient) -> None:
    response = browser.post(
        "/admin/users/reset/",
        json={
            "user": "alice@example.com",
            "new_password": ONE_TIME,
            "confirm_password": "a-different-value",
        },
    )
    assert response.status_code == 400
    assert response.json()["error"] == "PASSWORD_MISMATCH"
    assert STORE.last_reset is None


def test_resetting_an_unknown_user_is_a_404(browser: TestClient) -> None:
    response = browser.post(
        "/admin/users/reset/",
        json={
            "user": "nobody@example.com",
            "new_password": ONE_TIME,
            "confirm_password": ONE_TIME,
        },
    )
    assert response.status_code == 404
    assert response.json()["error"] == "UNKNOWN_USER"


def test_submitting_a_reset_without_a_session_is_refused(client: TestClient) -> None:
    response = client.post(
        "/admin/users/reset/",
        json={
            "user": "alice@example.com",
            "new_password": ONE_TIME,
            "confirm_password": ONE_TIME,
        },
    )
    assert response.status_code == 401
    assert response.json()["error"] == "SESSION_REQUIRED"
    assert STORE.last_reset is None


# --- the confirmation page --------------------------------------------------


def test_the_done_page_renders_the_recorded_reset(browser: TestClient) -> None:
    browser.post(
        "/admin/users/reset/",
        json={
            "user": "alice@example.com",
            "new_password": ONE_TIME,
            "confirm_password": ONE_TIME,
        },
    )
    markup = browser.get("/admin/users/reset/done/").text
    assert "Password for alice has been reset successfully." in markup
    assert STORE.last_reset["at"] in markup
    assert 'id="back-to-users" href="/admin/users/"' in markup


def test_the_done_page_says_so_when_nothing_is_recorded(browser: TestClient) -> None:
    markup = browser.get("/admin/users/reset/done/").text
    assert "No reset is recorded" in markup


def test_the_done_page_escapes_a_reflected_identifier(browser: TestClient) -> None:
    response = browser.get(
        "/admin/users/reset/done/", params={"user": "<script>alert(1)</script>"}
    )
    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text


# --- the status page --------------------------------------------------------


def test_the_status_page_is_honest_about_what_exists(client: TestClient) -> None:
    """A status page that claims components this app does not have teaches an
    operator to distrust status pages."""
    markup = client.get("/status").text
    assert 'id="api-status">operational<' in markup
    assert "in-memory" in markup
    assert 'id="queue-status">none<' in markup
    assert 'id="checked-at">' in markup
    assert "static dev fixture" not in markup


# --- the user list renders real state ---------------------------------------


def test_the_pre_locked_user_renders_as_locked(browser: TestClient) -> None:
    markup = browser.get("/admin/users/").text
    dave_row = re.search(
        r'<tr id="user-row-dave".*?</tr>', markup, re.DOTALL
    ).group(0)
    alice_row = re.search(
        r'<tr id="user-row-alice".*?</tr>', markup, re.DOTALL
    ).group(0)
    assert 'class="user-status">locked<' in dave_row
    assert 'data-locked="true"' in dave_row
    assert 'class="user-status">active<' in alice_row


def test_an_http_lock_is_visible_on_the_rendered_page(
    browser: TestClient, password: str
) -> None:
    """The cross-skill claim: mutate over HTTP, read it back off rendered HTML.

    `LockUnlockUser` posts to `/api/users/{id}/lock`; `CheckUserStatus` reads the
    row off `/admin/users/`. Same store, two surfaces, one story.
    """
    browser.auth = (ADMIN_USERNAME, password)
    response = browser.post("/api/users/alice/lock")
    assert response.status_code == 200
    browser.auth = None

    markup = browser.get("/admin/users/").text
    alice_row = re.search(
        r'<tr id="user-row-alice".*?</tr>', markup, re.DOTALL
    ).group(0)
    assert 'class="user-status">locked<' in alice_row
    assert 'data-locked="true"' in alice_row
