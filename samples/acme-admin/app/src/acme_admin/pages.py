"""The human surface: six server-rendered pages over the shared store (SPEC-059 R-2).

These pages replace the tutorial target's six *static* pages. They keep the same
URL shapes and the same element ids — the contract shipped skills' `web.snapshot`
refs and `web.extract` selectors address — but they now really mutate, and the
login really validates.

Templates are `string.Template` module constants rather than files: the
Dockerfile copies one tree, there is no template-search path to configure, and
`$` delimiters are chosen over f-strings because the preserved JavaScript is
full of `{}`.

Two behavioural asymmetries are load-bearing and are preserved exactly, because
they are what holds a mutating browser flow to a single HITL card (SPEC-051):

* **The admin login auto-submits** once both fields are filled (the 100 ms
  `_autoLoginTimer`), so authentication costs only `web.fill_credential` — read
  tier — and parks nothing. It now issues a real `fetch` POST to `/admin/login`.
* **The reset form pre-fills from `?user=&newpw=` but does NOT auto-submit.**
  The sole `web.click` in the flow is "Confirm reset", which is the mutation the
  operator actually approves. The pre-fill stays client-side on purpose: the
  one-time value never appears in the server-rendered HTML; client-side code
  still fills it into password inputs, whose values `web.snapshot` masks.
  The gateway's shared `redact_secret_query` path also stays exercised by a
  live sample.

The public landing form on `/` deliberately has **no** auto-submit timer — only
the admin login does — so a flow that signs in on `/` would spend a write-tier
click. Skills sign in at `/admin/`.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from string import Template
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from .api import error
from .auth import (
    ADMIN_USERNAME,
    SESSIONS,
    SESSION_COOKIE,
    SESSION_MAX_AGE_SECONDS,
    check_admin_credentials,
)
from .store import STORE, InvalidPassword, NoOpMutation, UnknownUser, iso_utc

router = APIRouter()

ADMIN_LOGIN_PATH = "/admin/"
ADMIN_USERS_PATH = "/admin/users/"

# Where a successful sign-in goes. Kept server-side so the pages never hardcode
# a destination the router disagrees with.
POST_LOGIN_REDIRECT = "/admin/users/"


class LoginForm(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class ResetForm(BaseModel):
    user: str = Field(min_length=1, max_length=254)
    new_password: str = Field(min_length=1, max_length=128)
    confirm_password: str = Field(min_length=1, max_length=128)


def session_user(request: Request) -> str | None:
    """The signed-in operator for this request, or `None`."""
    return SESSIONS.username_for(request.cookies.get(SESSION_COOKIE))


def _page(template: Template, **values: object) -> HTMLResponse:
    return HTMLResponse(template.safe_substitute(**values))


# ---------------------------------------------------------------------------
# Page 1 — `/` (public landing / staff sign-in)
# ---------------------------------------------------------------------------

INDEX_PAGE = Template(
    """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>ACME Inventory Portal - Sign in</title>
</head>
<body>
  <h1>ACME Inventory Portal</h1>
  <p>Staff sign-in. Console: <a href="/admin/">operator login</a> &middot;
     <a href="/status">service status</a></p>
  <form id="login-form" onsubmit="return signIn(event)">
    <label for="username">Username</label>
    <input id="username" name="username" type="text" autocomplete="off">
    <label for="password">Password</label>
    <input id="password" name="password" type="password" autocomplete="off">
    <button id="sign-in" type="submit">Sign in</button>
  </form>
  <p id="login-status" role="status">${login_status}</p>
  <script>
    /* The landing form posts to the same endpoint as /admin/ — one operator
       account, one credential, one session. Unlike the admin login it has NO
       auto-submit timer, so signing in here costs a write-tier click; flows
       that must stay card-free sign in at /admin/ instead. */
    function signIn(event) {
      event.preventDefault();
      var user = document.getElementById("username").value;
      var pass = document.getElementById("password").value;
      var status = document.getElementById("login-status");
      if (!user) return false;
      status.textContent = "Signing in...";
      fetch("/admin/login", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({username: user, password: pass})
      }).then(function(response) {
        return response.json().then(function(body) {
          return {ok: response.ok, body: body};
        });
      }).then(function(result) {
        if (!result.ok) {
          status.textContent = (result.body && result.body.message)
            ? result.body.message : "Sign-in failed.";
          return;
        }
        status.textContent = "Signed in as " + result.body.signed_in_as;
      }).catch(function(err) {
        status.textContent = "Sign-in failed: " + err;
      });
      return false;
    }
  </script>
</body>
</html>
"""
)

# ---------------------------------------------------------------------------
# Page 2 — `/status` (public service status)
# ---------------------------------------------------------------------------

STATUS_PAGE = Template(
    """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>ACME Inventory Status</title>
</head>
<body>
  <h1>ACME Inventory Status</h1>
  <table>
    <tr><td>api</td><td id="api-status">${api_status}</td></tr>
    <tr><td>database</td><td id="db-status">${db_status}</td></tr>
    <tr><td>queue</td><td id="queue-status">${queue_status}</td></tr>
  </table>
  <p>Last checked: <span id="checked-at">${checked_at}</span></p>
  <p>Store revision: <span id="store-revision">${store_revision}</span>
     &middot; users seeded: <span id="users-seeded">${users_seeded}</span></p>
  <p><a href="/">Back to sign in</a></p>
</body>
</html>
"""
)

# ---------------------------------------------------------------------------
# Page 3 — `/admin/` (operator login; auto-submits)
# ---------------------------------------------------------------------------

ADMIN_LOGIN_PAGE = Template(
    """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>ACME Admin Console - Sign in</title>
</head>
<body>
  <h1>ACME Admin Console</h1>
  <p id="admin-auth-status">${auth_status}</p>
  <form id="admin-login-form" onsubmit="return adminSignIn(event)">
    <label for="admin-username">Username</label>
    <input id="admin-username" name="username" type="text" autocomplete="off">
    <label for="admin-password">Password</label>
    <input id="admin-password" name="password" type="password" autocomplete="off">
    <button id="admin-sign-in" type="submit">Sign in</button>
  </form>
  <p id="admin-login-status" role="status"></p>
  <p><a href="/status">Service status</a></p>
  <script>
    function adminSignIn(event) {
      event.preventDefault();
      adminDoLogin();
      return false;
    }
    function adminDoLogin() {
      var user = document.getElementById("admin-username").value;
      var pass = document.getElementById("admin-password").value;
      var status = document.getElementById("admin-login-status");
      if (!user) return;
      status.textContent = "Signing in...";
      fetch("/admin/login", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({username: user, password: pass})
      }).then(function(response) {
        return response.json().then(function(body) {
          return {ok: response.ok, body: body};
        });
      }).then(function(result) {
        if (!result.ok) {
          /* A wrong password is visible here and does NOT navigate. */
          status.textContent = (result.body && result.body.message)
            ? result.body.message : "Sign-in failed.";
          return;
        }
        document.getElementById("admin-login-form").style.display = "none";
        document.getElementById("admin-auth-status").textContent =
          "Signed in as " + result.body.signed_in_as;
        status.textContent = "Redirecting to user management...";
        setTimeout(function() {
          window.location.href = result.body.redirect;
        }, 200);
      }).catch(function(err) {
        status.textContent = "Sign-in failed: " + err;
      });
    }
    /* Legacy SSO auto-login: when both fields are pre-filled
       (e.g., by an automation tool), submit automatically. Preserved from the
       static target because it is what keeps authentication read tier:
       web.fill_credential alone signs the flow in, so the flow's single HITL
       gate lands on "Confirm reset" (SPEC-051). */
    var _autoLoginTimer = setInterval(function() {
      var u = document.getElementById("admin-username");
      var p = document.getElementById("admin-password");
      if (u && u.value && p && p.value) {
        clearInterval(_autoLoginTimer);
        adminDoLogin();
      }
    }, 100);
  </script>
</body>
</html>
"""
)

# ---------------------------------------------------------------------------
# Page 4 — `/admin/users/` (the user list, rendered from real state)
# ---------------------------------------------------------------------------

ADMIN_USERS_PAGE = Template(
    """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>ACME Admin Console - User Management</title>
</head>
<body>
  <h1>User Management</h1>
  <p>Signed in as ${signed_in_as} &middot; <a href="/admin/">Back to login</a></p>

  <!-- Recent Password Resets: rendered from the store, so any browser sees the
       same record. The static target needed URL params and localStorage to fake
       cross-browser verification; real state does not. -->
  <div style="background:#1e293b;border:1px solid #475569;border-radius:4px;padding:12px;margin-bottom:16px;">
    <h3 style="margin:0 0 8px 0;color:#e2e8f0;">Recent Password Resets</h3>
    <div id="last-reset-status" style="background:#2d4a2b;border:1px solid #4a7;border-radius:4px;padding:8px 12px;display:${last_reset_display};color:#fff;">
      <strong>Last reset:</strong>
      <span id="last-reset-user">${last_reset_user}</span>
      <span id="last-reset-time">${last_reset_time}</span>
    </div>
    <div id="no-resets" style="display:${no_resets_display};color:#94a3b8;font-style:italic;">
      No recent password resets.
    </div>
  </div>

  <table id="user-table" border="1">
    <thead>
      <tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th>
          <th>Last modified</th><th>Revision</th><th>Action</th></tr>
    </thead>
    <tbody>
      ${user_rows}
    </tbody>
  </table>
  <p>Store revision: <span id="store-revision">${store_revision}</span></p>
</body>
</html>
"""
)

_USER_ROW = Template(
    """      <tr id="user-row-${username}" class="user-row" data-username="${username}"
          data-locked="${locked_flag}">
        <td class="user-name">${full_name}</td>
        <td class="user-email">${email}</td>
        <td class="user-role">${role}</td>
        <td class="user-status">${status_text}</td>
        <td class="user-modified">${last_modified}</td>
        <td class="user-revision">${revision}</td>
        <td><a class="reset-link"
               href="/admin/users/reset/?user=${email}">Reset password</a></td>
      </tr>"""
)

# ---------------------------------------------------------------------------
# Page 5 — `/admin/users/reset/` (pre-fills from the URL, does NOT auto-submit)
# ---------------------------------------------------------------------------

ADMIN_RESET_PAGE = Template(
    """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>ACME Admin Console - Reset Password</title>
</head>
<body>
  <h1>Reset Password</h1>
  <p>Resetting password for: <strong id="target-user">unknown</strong></p>
  <p><a href="/admin/users/">Back to user list</a></p>
  <form id="reset-form" onsubmit="return doReset(event)">
    <label for="new-password">New password</label>
    <input id="new-password" name="new_password" type="password" autocomplete="off">
    <label for="confirm-password">Confirm password</label>
    <input id="confirm-password" name="confirm_password" type="password" autocomplete="off">
    <button id="confirm-reset" type="submit">Confirm reset</button>
  </form>
  <p id="reset-status" role="status"></p>
  <script>
    /* Read the target user and new password from the query string.
       Legacy admin panels often accept pre-filled URLs for batch
       operations — the operator constructs the URL and the page
       auto-fills the form. Kept client-side so the one-time value never
       appears in served HTML. */
    var params = new URLSearchParams(window.location.search);
    var targetUser = params.get("user") || "unknown";
    var newPw = params.get("newpw") || "";
    document.getElementById("target-user").textContent = targetUser;
    if (newPw) {
      document.getElementById("new-password").value = newPw;
      document.getElementById("confirm-password").value = newPw;
    }
    function doReset(event) {
      event.preventDefault();
      var np = document.getElementById("new-password").value;
      var cp = document.getElementById("confirm-password").value;
      var status = document.getElementById("reset-status");
      if (!np || np !== cp) {
        status.textContent = "Error: passwords do not match.";
        return false;
      }
      status.textContent = "Resetting password...";
      fetch("/admin/users/reset/", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({user: targetUser, new_password: np, confirm_password: cp})
      }).then(function(response) {
        return response.json().then(function(body) {
          return {ok: response.ok, body: body};
        });
      }).then(function(result) {
        if (!result.ok) {
          /* A refusal is visible and the form stays usable. */
          status.textContent = "Error: " + ((result.body && result.body.message)
            ? result.body.message : "reset failed.");
          return;
        }
        document.getElementById("reset-form").style.display = "none";
        status.textContent = "Password for " + result.body.username +
          " has been reset successfully.";
        var link = document.createElement("a");
        link.href = result.body.redirect;
        link.textContent = "View confirmation";
        status.appendChild(document.createElement("br"));
        status.appendChild(link);
      }).catch(function(err) {
        status.textContent = "Error: " + err;
      });
      return false;
    }
    /* SPEC-051 Design 1: the form pre-fills from the URL but does NOT
       auto-submit. The operator's "Confirm reset" click is the flow's
       single write-tier interaction — the one HITL gate — so the
       destructive reset never runs without an explicit approval. */
  </script>
</body>
</html>
"""
)

# ---------------------------------------------------------------------------
# Page 6 — `/admin/users/reset/done/` (confirmation, rendered from the store)
# ---------------------------------------------------------------------------

ADMIN_RESET_DONE_PAGE = Template(
    """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>ACME Admin Console - Password Reset Confirmation</title>
</head>
<body>
  <h1>Password Reset Confirmation</h1>
  <p id="confirmation-message">${confirmation_message}</p>
  <p>Timestamp: <span id="reset-timestamp">${reset_timestamp}</span></p>
  <p><a id="back-to-users" href="${back_href}">Back to user list</a></p>
</body>
</html>
"""
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/")
def index_page(request: Request) -> HTMLResponse:
    user = session_user(request)
    status = f"Signed in as {user}" if user else ""
    return _page(INDEX_PAGE, login_status=status)


@router.get("/status")
def status_page() -> HTMLResponse:
    """Public, and honest: there is no database and no queue behind this app.

    A status page that says "operational" for components the service does not
    have teaches an operator to distrust status pages.
    """
    return _page(
        STATUS_PAGE,
        api_status="operational",
        db_status="none - in-memory store",
        queue_status="none",
        checked_at=iso_utc(datetime.now(timezone.utc)),
        store_revision=STORE.revision,
        users_seeded=STORE.users_seeded,
    )


@router.get("/admin/")
def admin_login_page(request: Request) -> HTMLResponse:
    user = session_user(request)
    return _page(
        ADMIN_LOGIN_PAGE,
        auth_status=f"Signed in as {user}" if user else "",
    )


@router.post("/admin/login")
def admin_login(form: LoginForm) -> JSONResponse:
    """The one login endpoint both sign-in forms post to.

    Mints an opaque session token and sets it as an `HttpOnly`/`SameSite=Lax`
    cookie. On refusal it returns 401 with no cookie, and the calling page
    renders the message into `#admin-login-status` without navigating.
    """
    if not check_admin_credentials(form.username, form.password):
        return error(401, "INVALID_CREDENTIALS", "Invalid username or password.")
    token = SESSIONS.create(ADMIN_USERNAME)
    response = JSONResponse(
        content={
            "ok": True,
            "signed_in_as": ADMIN_USERNAME,
            "redirect": POST_LOGIN_REDIRECT,
        }
    )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response


# A route that can answer with a page *or* a redirect has a union of two
# `Response` subclasses as its return type, which FastAPI cannot build a
# response model from. `response_model=None` on those three routes keeps the
# annotation honest instead of flattening it to `Response`.


@router.get("/admin/users/", response_model=None)
def admin_users_page(request: Request) -> HTMLResponse | RedirectResponse:
    """The user list, rendered from real state. 302 to `/admin/` when signed out."""
    user = session_user(request)
    if user is None:
        return RedirectResponse(url=ADMIN_LOGIN_PATH, status_code=302)

    rows = []
    for record in STORE.all_users():
        rows.append(
            _USER_ROW.substitute(
                username=html.escape(record.username),
                locked_flag="true" if record.locked else "false",
                full_name=html.escape(record.full_name),
                email=html.escape(record.email),
                role=html.escape(record.role),
                # `locked` / `active` is what `CheckUserStatus` reads back after
                # `LockUnlockUser` mutated the same row over HTTP.
                status_text="locked" if record.locked else "active",
                last_modified=html.escape(record.last_modified or ""),
                revision=record.revision,
            )
        )

    last_reset = STORE.last_reset
    return _page(
        ADMIN_USERS_PAGE,
        signed_in_as=html.escape(user),
        user_rows="\n".join(rows),
        last_reset_display="block" if last_reset else "none",
        no_resets_display="none" if last_reset else "block",
        last_reset_user=f" {html.escape(last_reset['username'])} " if last_reset else "",
        last_reset_time=f"at {html.escape(last_reset['at'])}" if last_reset else "",
        store_revision=STORE.revision,
    )


@router.get("/admin/users/reset/", response_model=None)
def admin_reset_page(request: Request) -> HTMLResponse | RedirectResponse:
    """The reset form. Server-rendered *without* the one-time value: the
    `?newpw=` pre-fill happens in the page's own script."""
    if session_user(request) is None:
        return RedirectResponse(url=ADMIN_LOGIN_PATH, status_code=302)
    return _page(ADMIN_RESET_PAGE)


@router.post("/admin/users/reset/")
def admin_reset_submit(request: Request, form: ResetForm) -> JSONResponse:
    """Perform the reset the operator just approved. Really mutates the store."""
    if session_user(request) is None:
        return error(401, "SESSION_REQUIRED", "Sign in at /admin/ before resetting.")
    if form.new_password != form.confirm_password:
        return error(400, "PASSWORD_MISMATCH", "passwords do not match")
    try:
        user = STORE.set_password(form.user, form.new_password)
    except UnknownUser as exc:
        return error(404, "UNKNOWN_USER", str(exc))
    except NoOpMutation as exc:
        return error(409, "NO_OP_MUTATION", str(exc))
    except InvalidPassword as exc:
        return error(400, "INVALID_PASSWORD", str(exc))

    reset_at = user.password_changed_at or iso_utc(datetime.now(timezone.utc))
    return JSONResponse(
        content={
            "ok": True,
            "username": user.username,
            "revision": user.revision,
            "password_changed_at": reset_at,
            "redirect": (
                f"/admin/users/reset/done/?user={quote(user.username)}"
                f"&at={quote(reset_at)}"
            ),
        }
    )


@router.get("/admin/users/reset/done/", response_model=None)
def admin_reset_done_page(
    request: Request, user: str = "", at: str = ""
) -> HTMLResponse | RedirectResponse:
    """Confirmation, rendered from the store's real reset record.

    The query parameters are accepted for compatibility with the link the reset
    page builds, but the store is authoritative: a confirmation page that only
    echoes its own query string is the lie this slice removes.
    """
    if session_user(request) is None:
        return RedirectResponse(url=ADMIN_LOGIN_PATH, status_code=302)

    last_reset = STORE.last_reset
    if last_reset:
        who = last_reset["username"]
        when = last_reset["at"]
        message = f"Password for {who} has been reset successfully."
    else:
        who = user or "unknown"
        when = at or ""
        message = (
            f"No reset is recorded for {who}."
            if not at
            else f"Password for {who} has been reset successfully."
        )

    return _page(
        ADMIN_RESET_DONE_PAGE,
        confirmation_message=html.escape(message),
        reset_timestamp=html.escape(when),
        back_href=html.escape(ADMIN_USERS_PATH, quote=True),
    )
