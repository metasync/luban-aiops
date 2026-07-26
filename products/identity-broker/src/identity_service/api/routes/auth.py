from fastapi import APIRouter, Depends

from identity_service.core.config import IdentitySettings, get_settings
from identity_service.services.identity_service import build_login_url

router = APIRouter()


@router.get("/api/v1/auth/login-url")
def login_url(settings: IdentitySettings = Depends(get_settings)) -> dict[str, str]:
    return build_login_url(settings)
