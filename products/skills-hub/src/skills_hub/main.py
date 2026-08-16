import uvicorn
from skills_hub.app import app
from skills_hub.core.runtime import SkillsRunSettings


def run() -> None:
    settings = SkillsRunSettings.from_env()
    uvicorn.run(app, host=settings.host, port=settings.port)
