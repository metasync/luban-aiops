import uvicorn
from api_gateway.app import app
from api_gateway.core.runtime import GatewayRunSettings


def run() -> None:
    settings = GatewayRunSettings.from_env()
    uvicorn.run(app, host=settings.host, port=settings.port)
