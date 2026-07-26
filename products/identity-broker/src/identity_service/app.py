from fastapi import FastAPI

from identity_service.api.router import router
from identity_service.metadata import SERVICE_TITLE, SERVICE_VERSION


def create_app() -> FastAPI:
    app = FastAPI(title=SERVICE_TITLE, version=SERVICE_VERSION)
    app.include_router(router)
    return app


app = create_app()
