from fastapi import APIRouter

from tool_gateway.api.routes import health, tools

router = APIRouter()
router.include_router(health.router)
router.include_router(tools.router)
