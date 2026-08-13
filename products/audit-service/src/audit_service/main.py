import uvicorn
from audit_service.app import app
from audit_service.core.runtime import AuditRunSettings


def run() -> None:
    settings = AuditRunSettings.from_env()
    uvicorn.run(app, host=settings.host, port=settings.port)
