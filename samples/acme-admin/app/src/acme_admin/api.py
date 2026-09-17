"""The machine surface: JSON endpoints over the shared store (SPEC-059 R-1).

`/healthz` and `/api/hello` are unauthenticated on purpose — `CheckServiceHealth`
is the first genuinely card-free read-only skill in the repository, and a health
check that needs a credential is not a health check. Every `/api/users*` route is
behind HTTP Basic (`auth.require_admin`).

Error bodies are one envelope, `{"error": "<CODE>", "message": "<human>"}`, so a
caller can branch on a code rather than parse prose. The two codes that matter
to SPEC-058 R-3's `mutation_confirmed` marker are real status codes: **404**
`UNKNOWN_USER` and **409** `NO_OP_MUTATION` — locking an already-locked user is
not a success, and a target that says otherwise makes the marker meaningless.
"""

from __future__ import annotations

import socket
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import SERVICE_NAME, __version__
from .auth import BASIC_REALM, SESSIONS, require_admin
from .store import (
    SEED_REVISION,
    STORE,
    InvalidPassword,
    NoOpMutation,
    UnknownUser,
    iso_utc,
)

router = APIRouter()

# `POST /internal/reset-demo` is gated on this header, which the demo scripts
# set with `curl` and which `http.post` has no way to send — SPEC-058 R-4 ships
# no `headers` parameter. The agent therefore cannot reset the demo state
# mid-run even though the endpoint sits on an allowlisted origin: a structural
# control, not a hope. No skill document names this endpoint.
DEMO_RESET_HEADER = "X-Luban-Demo-Reset"

# Bounded, and deliberately narrow: `/api/hello` echoes its argument back, so a
# value outside this pattern could carry markup into a rendered page. Refused
# with 422 by FastAPI's own validation.
HELLO_NAME_PATTERN = r"^[A-Za-z0-9 _.-]{1,64}$"

# Keys `/healthz` must carry — a health check with something to assert, not a
# bare 200. The sample suite's tests and `deploy.sh` both assert all eight.
HEALTH_KEYS = (
    "status",
    "service",
    "version",
    "hostname",
    "uptime_seconds",
    "started_at",
    "users_seeded",
    "store_revision",
)


class PasswordBody(BaseModel):
    """The reset body. The value is recorded as an event and then discarded."""

    password: str = Field(min_length=1, max_length=128)


def error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"error": code, "message": message}
    )


def unauthorized(message: str = "admin credentials required") -> JSONResponse:
    """The one 401 shape, carrying the Basic challenge a `curl -u` retry needs."""
    return JSONResponse(
        status_code=401,
        content={"error": "UNAUTHORIZED", "message": message},
        headers={"WWW-Authenticate": f'Basic realm="{BASIC_REALM}"'},
    )


def _uptime_seconds(now: datetime) -> float:
    return round((now - STORE.started_at).total_seconds(), 3)


@router.get("/healthz")
def healthz() -> dict[str, object]:
    """Liveness/readiness probe target and `CheckServiceHealth`'s subject."""
    now = datetime.now(timezone.utc)
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": __version__,
        # The pod name, so an operator can tell which replica answered.
        "hostname": socket.gethostname(),
        "uptime_seconds": _uptime_seconds(now),
        "started_at": iso_utc(STORE.started_at),
        "users_seeded": STORE.users_seeded,
        "store_revision": STORE.revision,
    }


@router.get("/api/hello")
def hello(
    name: str = Query(default="world", pattern=HELLO_NAME_PATTERN),
) -> dict[str, str]:
    """The "does the basic function work" probe. Echoes, so round-trip is assertable."""
    return {"message": f"hello, {name}!"}


@router.get("/api/users")
def list_users(_admin: str = Depends(require_admin)) -> JSONResponse:
    """The user list: `username`, `locked`, `last_modified`, `revision` per row."""
    return JSONResponse(
        content={
            "users": [user.to_list_dict() for user in STORE.all_users()],
            "store_revision": STORE.revision,
        }
    )


@router.get("/api/users/{identifier}")
def get_user(identifier: str, _admin: str = Depends(require_admin)) -> JSONResponse:
    """One user by username **or** email: the list fields plus identity."""
    try:
        user = STORE.resolve(identifier)
    except UnknownUser as exc:
        return error(404, "UNKNOWN_USER", str(exc))
    return JSONResponse(content=user.to_detail_dict())


def _mutation_response(action: str, identifier: str, mutate) -> JSONResponse:
    """Run a store mutation and shape the response, mapping 400, 404 and 409."""
    try:
        user = mutate(identifier)
    except UnknownUser as exc:
        return error(404, "UNKNOWN_USER", str(exc))
    except NoOpMutation as exc:
        return error(409, "NO_OP_MUTATION", str(exc))
    except InvalidPassword as exc:
        return error(400, "INVALID_PASSWORD", str(exc))
    # Every mutating response carries the post-mutation revision, so a caller can
    # prove *which* action changed the row rather than only that something did.
    return JSONResponse(content={"action": action, **user.to_detail_dict()})


@router.post("/api/users/{identifier}/lock")
def lock_user(identifier: str, _admin: str = Depends(require_admin)) -> JSONResponse:
    return _mutation_response("lock", identifier, STORE.lock)


@router.post("/api/users/{identifier}/unlock")
def unlock_user(identifier: str, _admin: str = Depends(require_admin)) -> JSONResponse:
    return _mutation_response("unlock", identifier, STORE.unlock)


@router.post("/api/users/{identifier}/password")
def set_password(
    identifier: str,
    body: PasswordBody,
    _admin: str = Depends(require_admin),
) -> JSONResponse:
    return _mutation_response(
        "password_reset", identifier, lambda ident: STORE.set_password(ident, body.password)
    )


@router.post("/internal/reset-demo")
def reset_demo(
    x_luban_demo_reset: str | None = Header(default=None, alias=DEMO_RESET_HEADER),
) -> JSONResponse:
    """Restore the deterministic seed. Demo scripts only; header-gated.

    Sessions are dropped too, so a reseeded run also starts logged out and a
    stale cookie cannot carry authority into fresh state.
    """
    if not x_luban_demo_reset:
        return error(
            403,
            "DEMO_RESET_HEADER_REQUIRED",
            f"set the {DEMO_RESET_HEADER} request header to reset the demo state",
        )
    STORE.reseed()
    SESSIONS.clear()
    return JSONResponse(
        content={
            "status": "reseeded",
            "store_revision": STORE.revision,
            "seed_revision": SEED_REVISION,
            "users_seeded": STORE.users_seeded,
            "users": [user.username for user in STORE.all_users()],
        }
    )
