from __future__ import annotations

from urllib.parse import urlencode

from identity_service.core.config import IdentitySettings
from identity_service.metadata import SERVICE_NAME, SERVICE_VERSION
from identity_service.schemas.identity import ClaimsPayload, IdentityContext

ROLE_MAPPINGS = {
    "ops-admins": "platform-admin",
    "ops-approvers": "approver",
    "ops-operators": "operator",
    "ops-observers": "read-only-observer",
}


def resolve_roles(groups: list[str]) -> list[str]:
    roles = {ROLE_MAPPINGS[group] for group in groups if group in ROLE_MAPPINGS}
    if not roles:
        roles.add("read-only-observer")
    return sorted(roles)


def health_status() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "version": SERVICE_VERSION}


def build_login_url(settings: IdentitySettings) -> dict[str, str]:
    query = urlencode(
        {
            "client_id": settings.oidc_client_id,
            "response_type": "code",
            "scope": "openid profile email",
            "redirect_uri": settings.oidc_redirect_uri,
        }
    )
    return {
        "login_url": (
            f"{settings.keycloak_base_url}/realms/{settings.keycloak_realm}"
            f"/protocol/openid-connect/auth?{query}"
        )
    }


def normalize_identity(payload: ClaimsPayload) -> IdentityContext:
    return IdentityContext(
        subject=payload.sub,
        username=payload.preferred_username,
        email=payload.email,
        groups=payload.groups,
        roles=resolve_roles(payload.groups),
    )
