import uvicorn
from incident_service.app import app
from incident_service.core.runtime import IncidentRunSettings


def run() -> None:
    settings = IncidentRunSettings.from_env()
    uvicorn.run(app, host=settings.host, port=settings.port)
