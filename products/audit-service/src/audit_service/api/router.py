from fastapi import APIRouter

from audit_service.api.routes import health, ingest, query

router = APIRouter()
router.include_router(health.router)
router.include_router(ingest.router)
router.include_router(query.router)
