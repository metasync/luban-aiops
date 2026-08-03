import uvicorn
from tool_gateway.app import app
from tool_gateway.core.runtime import GatewayRunSettings


def run() -> None:
    settings = GatewayRunSettings.from_env()
    uvicorn.run(app, host=settings.host, port=settings.port)
