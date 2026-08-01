from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass(frozen=True)
class ServiceClient:
    """A registered service caller permitted to request delegated tokens (R-3).

    ``allowed_audiences`` pins the audiences this client may request; the
    exchange endpoint rejects any audience not in this list.
    """

    client_id: str
    secret: str
    allowed_audiences: tuple[str, ...] = ()


def _parse_service_clients(raw: str) -> tuple[ServiceClient, ...]:
    """Parse ``IDENTITY_SERVICE_CLIENTS``.

    Format: comma-separated entries of ``client_id:secret:aud1|aud2``. The
    audience segment is optional (defaults to no allowed audiences). Example:
    ``tool-gateway:s3cr3t:tool-gateway``.
    """
    clients: list[ServiceClient] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":")
        client_id = parts[0].strip()
        secret = parts[1].strip() if len(parts) > 1 else ""
        audiences = tuple(
            aud.strip()
            for aud in (parts[2].split("|") if len(parts) > 2 else [])
            if aud.strip()
        )
        if client_id and secret:
            clients.append(
                ServiceClient(
                    client_id=client_id,
                    secret=secret,
                    allowed_audiences=audiences,
                )
            )
    return tuple(clients)


@dataclass(frozen=True)
class IdentitySettings:
    keycloak_base_url: str = "https://keycloak.example.com"
    keycloak_realm: str = "luban"
    oidc_client_id: str = "luban-portal"
    oidc_client_secret: str | None = None
    oidc_scopes: str = "openid profile email"
    oidc_redirect_uri: str = "http://localhost:8080/callback"
    oidc_post_logout_redirect_uri: str = "http://localhost:8080/"
    jwt_private_key_path: str | None = None
    jwt_token_ttl_seconds: int = 900
    jwt_issuer: str = "luban-identity-broker"
    jwt_audience: str = "tool-gateway"
    delegated_token_ttl_seconds: int = 300
    service_clients: tuple[ServiceClient, ...] = field(default_factory=tuple)

    @classmethod
    def from_env(cls) -> "IdentitySettings":
        return cls(
            keycloak_base_url=os.getenv(
                "KEYCLOAK_BASE_URL",
                "https://keycloak.example.com",
            ),
            keycloak_realm=os.getenv("KEYCLOAK_REALM", "luban"),
            oidc_client_id=os.getenv("OIDC_CLIENT_ID", "luban-portal"),
            oidc_client_secret=os.getenv("OIDC_CLIENT_SECRET") or None,
            oidc_scopes=os.getenv("OIDC_SCOPES", "openid profile email"),
            oidc_redirect_uri=os.getenv(
                "OIDC_REDIRECT_URI",
                "http://localhost:8080/callback",
            ),
            oidc_post_logout_redirect_uri=os.getenv(
                "OIDC_POST_LOGOUT_REDIRECT_URI",
                "http://localhost:8080/",
            ),
            jwt_private_key_path=os.getenv("IDENTITY_JWT_PRIVATE_KEY_PATH") or None,
            jwt_token_ttl_seconds=int(
                os.getenv("IDENTITY_TOKEN_TTL_SECONDS", "900")
            ),
            jwt_issuer=os.getenv("IDENTITY_TOKEN_ISSUER", "luban-identity-broker"),
            jwt_audience=os.getenv("IDENTITY_TOKEN_AUDIENCE", "tool-gateway"),
            delegated_token_ttl_seconds=int(
                os.getenv("IDENTITY_DELEGATED_TOKEN_TTL_SECONDS", "300")
            ),
            service_clients=_parse_service_clients(
                os.getenv("IDENTITY_SERVICE_CLIENTS", "")
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> IdentitySettings:
    return IdentitySettings.from_env()
