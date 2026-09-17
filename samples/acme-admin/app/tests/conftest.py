"""Shared fixtures for the `acme-admin` suite.

Every test runs against a freshly reseeded store and no sessions, because the
whole point of the app is that its state is real: a test that inherited a
mutation from the test before it would be asserting nothing.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from acme_admin.auth import ADMIN_USERNAME, PASSWORD_ENV, SESSIONS
from acme_admin.main import create_app
from acme_admin.store import STORE

# A test-only value. It is set in the environment per test and never written to
# disk, never committed, and never appears in a response body.
TEST_PASSWORD = "unit-test-only-not-a-credential"


@pytest.fixture(autouse=True)
def clean_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """One password, one seed, no sessions — before *and* after every test."""
    monkeypatch.setenv(PASSWORD_ENV, TEST_PASSWORD)
    STORE.reseed()
    SESSIONS.clear()
    yield
    STORE.reseed()
    SESSIONS.clear()


@pytest.fixture()
def password() -> str:
    """The test-only operator password, for cases that build their own auth."""
    return TEST_PASSWORD


@pytest.fixture()
def client() -> TestClient:
    """An unauthenticated client. Entering the context runs the lifespan."""
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture()
def admin_client(client: TestClient) -> TestClient:
    """The same client carrying the operator's HTTP Basic credential."""
    client.auth = (ADMIN_USERNAME, TEST_PASSWORD)
    return client


@pytest.fixture()
def browser(client: TestClient) -> TestClient:
    """A client with a real HTML-surface session cookie, as a browser would have.

    Signs in through `POST /admin/login` — the endpoint the auto-submitting
    admin form calls — rather than by injecting a cookie, so the session path
    the skills exercise is the one under test.
    """
    response = client.post(
        "/admin/login",
        json={"username": ADMIN_USERNAME, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return client
