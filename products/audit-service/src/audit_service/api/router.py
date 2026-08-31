from fastapi import APIRouter

from audit_service.api.routes import export, health, ingest, query, summary

router = APIRouter()
router.include_router(health.router)
router.include_router(ingest.router)
router.include_router(query.router)
router.include_router(summary.router)
router.include_router(export.router)
