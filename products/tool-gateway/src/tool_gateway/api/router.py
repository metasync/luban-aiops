from fastapi import APIRouter

from tool_gateway.api.routes import authorizations, health, secrets, tools

router = APIRouter()
router.include_router(health.router)
router.include_router(tools.router)
router.include_router(secrets.router)
router.include_router(authorizations.router)
