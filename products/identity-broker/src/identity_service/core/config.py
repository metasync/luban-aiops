from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class IdentitySettings:
    keycloak_base_url: str = "https://keycloak.example.com"
    keycloak_realm: str = "luban"
    oidc_client_id: str = "luban-portal"
    oidc_redirect_uri: str = "http://localhost:8080/callback"

    @classmethod
    def from_env(cls) -> "IdentitySettings":
        return cls(
            keycloak_base_url=os.getenv(
                "KEYCLOAK_BASE_URL",
                "https://keycloak.example.com",
            ),
            keycloak_realm=os.getenv("KEYCLOAK_REALM", "luban"),
            oidc_client_id=os.getenv("OIDC_CLIENT_ID", "luban-portal"),
            oidc_redirect_uri=os.getenv(
                "OIDC_REDIRECT_URI",
                "http://localhost:8080/callback",
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> IdentitySettings:
    return IdentitySettings.from_env()
