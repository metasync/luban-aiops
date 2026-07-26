from fastapi import APIRouter

from api_gateway.api.routes import auth, chat, health, identity, runtime, sessions

router = APIRouter()
router.include_router(health.router)
router.include_router(runtime.router)
router.include_router(auth.router)
router.include_router(identity.router)
router.include_router(sessions.router)
router.include_router(chat.router)
