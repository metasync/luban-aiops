"""Two authentication mechanisms over one password (SPEC-059 R-1).

The JSON API uses HTTP Basic; the HTML pages use an opaque session token in an
`HttpOnly`/`SameSite=Lax` cookie, held in a server-side dict. The session is
deliberately **not** a JWT: a tutorial target that signs tokens teaches the
wrong thing about where authority comes from. Authority here is a value the
server handed out and can revoke by forgetting it.

One password backs both, so the browser surface, the HTTP surface and the
application cannot disagree. It arrives as `ACME_ADMIN_PASSWORD` from the
`acme-admin-credentials` secret that `sync-browser-credentials.sh` writes from
the same random value it puts in the `acme-admin` credential set (SPEC-059 R-3).
Nothing is defaulted: when the variable is absent the app fails closed at
startup (`main.py`), and every check below also fails closed.
"""

from __future__ import annotations

import hmac
import os
import secrets

from fastapi import Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials

# The console has exactly one operator account. The seeded users (`alice`,
# `bob`, `carol`, `dave`) are records, not accounts — they cannot sign in.
ADMIN_USERNAME = "admin"

# The challenge the 401 carries, so `curl -u` retries without a stored realm.
BASIC_REALM = "acme-admin"

PASSWORD_ENV = "ACME_ADMIN_PASSWORD"
SESSION_COOKIE = "acme_session"
# Eight hours: long enough for a walkthrough, short enough that a leaked token
# does not outlive the working day it was minted in.
SESSION_MAX_AGE_SECONDS = 8 * 60 * 60

# `auto_error=False` so an absent header becomes our own 401 (with the
# `WWW-Authenticate` challenge a `curl -u` retry needs) rather than FastAPI's.
_basic_scheme = HTTPBasic(auto_error=False)


def admin_password() -> str | None:
    """Read the operator password lazily, so tests can set it per case."""
    value = os.environ.get(PASSWORD_ENV, "")
    return value or None


def _constant_time_equals(candidate: str, expected: str) -> bool:
    return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


class AdminAuthRequired(Exception):
    """The operator credential is missing or wrong.

    `main.py` turns this into a 401 in the same `{"error", "message"}` envelope
    the rest of the API uses, carrying the `WWW-Authenticate` challenge a
    `curl -u` retry needs. A custom exception rather than `HTTPException` so
    there is one error shape on this surface instead of two.
    """

    def __init__(self, message: str = "admin credentials required") -> None:
        super().__init__(message)
        self.message = message


def check_admin_credentials(username: str, password: str) -> bool:
    """Validate the operator account. Fails closed when no password is set."""
    expected = admin_password()
    if not expected:
        return False
    return _constant_time_equals(username, ADMIN_USERNAME) and _constant_time_equals(
        password, expected
    )


def require_admin(
    credentials: HTTPBasicCredentials | None = Depends(_basic_scheme),
) -> str:
    """FastAPI dependency: every `/api/users*` route hangs off this."""
    if credentials is None or not check_admin_credentials(
        credentials.username, credentials.password
    ):
        raise AdminAuthRequired()
    return credentials.username


class SessionStore:
    """Server-side session tokens. In memory, like everything else here."""

    def __init__(self) -> None:
        self._tokens: dict[str, str] = {}

    def create(self, username: str) -> str:
        token = secrets.token_urlsafe(32)
        self._tokens[token] = username
        return token

    def username_for(self, token: str | None) -> str | None:
        if not token:
            return None
        return self._tokens.get(token)

    def drop(self, token: str | None) -> None:
        if token:
            self._tokens.pop(token, None)

    def clear(self) -> None:
        """Forget every session. Used by `reseed()` so demos start logged out."""
        self._tokens.clear()

    def __len__(self) -> int:
        return len(self._tokens)


SESSIONS = SessionStore()
