import uvicorn
from identity_service.app import app
from identity_service.core.runtime import IdentityRunSettings


def run() -> None:
    settings = IdentityRunSettings.from_env()
    uvicorn.run(app, host=settings.host, port=settings.port)
