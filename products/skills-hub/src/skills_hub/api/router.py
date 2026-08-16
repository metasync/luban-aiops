from fastapi import APIRouter

from skills_hub.api.routes import health, skills, status

router = APIRouter()
router.include_router(health.router)
# status/search are registered before the {skill_id:path} catch-all in
# skills.router; FastAPI matches in declaration order.
router.include_router(status.router)
router.include_router(skills.router)
