from fastapi import FastAPI

from agent_service.api.router import router
from agent_service.metadata import SERVICE_TITLE, SERVICE_VERSION


def create_app() -> FastAPI:
    app = FastAPI(title=SERVICE_TITLE, version=SERVICE_VERSION)
    app.include_router(router)
    return app


app = create_app()
