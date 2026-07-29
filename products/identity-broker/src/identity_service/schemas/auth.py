from pydantic import BaseModel

from identity_service.schemas.identity import IdentityContext


class LoginStartResponse(BaseModel):
    authorization_url: str
    state: str
    code_verifier: str
    redirect_uri: str


class AuthorizationCodeExchangeRequest(BaseModel):
    code: str
    code_verifier: str
    redirect_uri: str | None = None


class AuthenticatedSession(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None
    refresh_token: str | None = None
    id_token: str | None = None
    identity: IdentityContext


class LogoutRequest(BaseModel):
    id_token_hint: str | None = None
    post_logout_redirect_uri: str | None = None


class LogoutResponse(BaseModel):
    logout_url: str


class TokenRequest(BaseModel):
    username: str
    email: str | None = None
    roles: list[str] | None = None
    groups: list[str] | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
