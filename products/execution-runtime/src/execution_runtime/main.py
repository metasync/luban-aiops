import uvicorn
from execution_runtime.app import app
from execution_runtime.core.runtime import ExecutionRunSettings


def run() -> None:
    settings = ExecutionRunSettings.from_env()
    uvicorn.run(app, host=settings.host, port=settings.port)
