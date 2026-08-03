import uvicorn
from platform_gateway.app import app
from platform_gateway.core.runtime import GatewayRunSettings


def run() -> None:
    settings = GatewayRunSettings.from_env()
    uvicorn.run(app, host=settings.host, port=settings.port)
