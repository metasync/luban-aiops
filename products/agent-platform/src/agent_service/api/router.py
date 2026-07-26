from fastapi import APIRouter

from agent_service.api.routes import chat, health, runtime, sessions

router = APIRouter()
router.include_router(health.router)
router.include_router(runtime.router)
router.include_router(sessions.router)
router.include_router(chat.router)
