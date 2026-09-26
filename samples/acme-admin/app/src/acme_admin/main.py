"""Application assembly, fail-closed startup, and the console entry point.

`create_app()` wires the two routers over the one store and registers the single
error shape. The lifespan is where the credential contract is enforced: with no
`ACME_ADMIN_PASSWORD` the app **refuses to start** and says which secret and
which sync script produce it. Failing closed at startup beats failing open to a
well-known default password, which is why `SKIP_BROWSER_CREDENTIALS=true`
leaves a pod that will not come up rather than a console anyone can sign into.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from . import SERVICE_NAME, __version__
from .api import router as api_router
from .api import unauthorized
from .auth import PASSWORD_ENV, AdminAuthRequired, admin_password
from .pages import router as pages_router

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8080

SYNC_SCRIPT = "shared/platform-ops/gitops/sync-browser-credentials.sh"
SECRET_NAME = "acme-admin-credentials"


def missing_credential_message() -> str:
    """The startup failure text, kept in one place so tests assert the real one."""
    return (
        f"{PASSWORD_ENV} is not set, so {SERVICE_NAME} cannot authenticate its "
        f"operator account and refuses to start. Provision the {SECRET_NAME} "
        f"secret with {SYNC_SCRIPT} (it writes the same random value into the "
        f"`acme-admin` browser credential set), then redeploy. There is no "
        f"default password."
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not admin_password():
        raise RuntimeError(missing_credential_message())
    acceptance_user = os.environ.get("ACME_ACCEPTANCE_USER")
    if acceptance_user is not None:
        from .store import STORE

        STORE.seed_acceptance_user(acceptance_user)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="ACME Admin Console",
        version=__version__,
        lifespan=lifespan,
        # No interactive docs and no OpenAPI document. Both are unauthenticated
        # by nature and would publish `/internal/reset-demo` — the header-gated
        # reseed no skill document names — to anything that can reach the pod.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.exception_handler(AdminAuthRequired)
    async def _admin_auth_required(request, exc: AdminAuthRequired) -> JSONResponse:
        return unauthorized(exc.message)

    app.include_router(api_router)
    app.include_router(pages_router)
    return app


def run() -> None:
    """Console-script entry point: `uv run acme-admin`."""
    import uvicorn

    uvicorn.run(
        create_app(),
        host=os.environ.get("ACME_ADMIN_HOST", DEFAULT_HOST),
        port=int(os.environ.get("ACME_ADMIN_PORT", DEFAULT_PORT)),
    )


__all__ = [
    "create_app",
    "missing_credential_message",
    "run",
]
