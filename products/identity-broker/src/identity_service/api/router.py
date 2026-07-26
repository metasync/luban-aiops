from fastapi import APIRouter

from identity_service.api.routes import auth, health, identity

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(identity.router)
