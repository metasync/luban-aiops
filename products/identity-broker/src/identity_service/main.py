import os
from urllib.parse import urlencode

from fastapi import FastAPI
from pydantic import BaseModel, Field


ROLE_MAPPINGS = {
    "ops-admins": "platform-admin",
    "ops-approvers": "approver",
    "ops-operators": "operator",
    "ops-observers": "read-only-observer",
}


class ClaimsPayload(BaseModel):
    sub: str
    preferred_username: str
    email: str | None = None
    groups: list[str] = Field(default_factory=list)


class IdentityContext(BaseModel):
    subject: str
    username: str
    email: str | None = None
    groups: list[str]
    roles: list[str]


app = FastAPI(title="identity-service", version="0.1.0")


def resolve_roles(groups: list[str]) -> list[str]:
    roles = {ROLE_MAPPINGS[group] for group in groups if group in ROLE_MAPPINGS}
    if not roles:
        roles.add("read-only-observer")
    return sorted(roles)


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok", "service": "identity-service", "version": "0.1.0"}


@app.get("/health/ready")
def ready() -> dict[str, str]:
    return {"status": "ok", "service": "identity-service", "version": "0.1.0"}


@app.get("/api/v1/auth/login-url")
def login_url() -> dict[str, str]:
    base_url = os.getenv("KEYCLOAK_BASE_URL", "https://keycloak.example.com")
    realm = os.getenv("KEYCLOAK_REALM", "luban")
    client_id = os.getenv("OIDC_CLIENT_ID", "luban-portal")
    redirect_uri = os.getenv("OIDC_REDIRECT_URI", "http://localhost:8080/callback")
    query = urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "scope": "openid profile email",
            "redirect_uri": redirect_uri,
        }
    )
    return {
        "login_url": (
            f"{base_url}/realms/{realm}/protocol/openid-connect/auth?{query}"
        )
    }


@app.post("/api/v1/identity/normalize", response_model=IdentityContext)
def normalize_identity(payload: ClaimsPayload) -> IdentityContext:
    return IdentityContext(
        subject=payload.sub,
        username=payload.preferred_username,
        email=payload.email,
        groups=payload.groups,
        roles=resolve_roles(payload.groups),
    )
