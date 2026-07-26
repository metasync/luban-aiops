from pydantic import BaseModel, Field


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
