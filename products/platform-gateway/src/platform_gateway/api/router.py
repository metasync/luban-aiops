from fastapi import APIRouter

from platform_gateway.api.routes import (
    approvals,
    audit,
    auth,
    chat,
    documents,
    health,
    identity,
    incidents,
    models,
    policy,
    runtime,
    sessions,
    skills,
    tools,
)

router = APIRouter()
router.include_router(health.router)
router.include_router(runtime.router)
router.include_router(auth.router)
router.include_router(identity.router)
router.include_router(sessions.router)
router.include_router(chat.router)
router.include_router(audit.router)
router.include_router(incidents.router)
router.include_router(policy.router)
router.include_router(tools.router)
router.include_router(skills.router)
router.include_router(models.router)
router.include_router(approvals.router)
router.include_router(documents.router)
