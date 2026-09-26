import uvicorn
from execution_runtime.app import app
from execution_runtime.core.runtime import ExecutionRunSettings

# SPEC-063 R-7c: bound the graceful drain to 35s so in-flight work finishes
# inside the 45s pod grace period. SIGTERM (handled in the app lifespan) flips
# ``draining`` first, refusing new handoffs and marking the worker unready; no
# claim is released on shutdown.
GRACEFUL_DRAIN_SECONDS = 35


def run() -> None:
    settings = ExecutionRunSettings.from_env()
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        timeout_graceful_shutdown=GRACEFUL_DRAIN_SECONDS,
    )
