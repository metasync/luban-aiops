from fastapi import APIRouter

from execution_runtime.api.routes import health, handoff

router = APIRouter()
router.include_router(health.router)
router.include_router(handoff.router)
