from fastapi import APIRouter

from incident_service.api.routes import health, incidents, webhooks

router = APIRouter()
router.include_router(health.router)
router.include_router(webhooks.router)
router.include_router(incidents.router)
