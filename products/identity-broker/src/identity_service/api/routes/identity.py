from fastapi import APIRouter

from identity_service.schemas.identity import ClaimsPayload, IdentityContext
from identity_service.services.identity_service import normalize_identity

router = APIRouter()


@router.post("/api/v1/identity/normalize", response_model=IdentityContext)
def normalize_identity_route(payload: ClaimsPayload) -> IdentityContext:
    return normalize_identity(payload)
