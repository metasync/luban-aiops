import httpx
import logging
from fastapi import APIRouter, Depends, Header, HTTPException

from identity_service.core.config import IdentitySettings, get_settings
from identity_service.core.observability import log_event
from identity_service.schemas.identity import ClaimsPayload, IdentityContext
from identity_service.services.identity_service import (
    fetch_identity_from_authorization,
    normalize_identity,
)

router = APIRouter()
LOGGER = logging.getLogger(__name__)


@router.post("/api/v1/identity/normalize", response_model=IdentityContext)
def normalize_identity_route(payload: ClaimsPayload) -> IdentityContext:
    identity = normalize_identity(payload)
    log_event(LOGGER, "identity_normalized", user_id=identity.username)
    return identity


@router.get("/api/v1/identity/me", response_model=IdentityContext)
async def current_identity_route(
    authorization: str | None = Header(default=None),
    x_request_id: str | None = Header(default=None),
    settings: IdentitySettings = Depends(get_settings),
) -> IdentityContext:
    if authorization is None:
        raise HTTPException(status_code=401, detail="missing Authorization header")

    try:
        identity = await fetch_identity_from_authorization(settings, authorization)
        log_event(
            LOGGER,
            "identity_resolved_from_bearer",
            request_id=x_request_id,
            user_id=identity.username,
        )
        return identity
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=401, detail="invalid bearer token") from exc
