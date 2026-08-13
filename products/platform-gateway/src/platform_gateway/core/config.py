from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

DEFAULT_AGENT_SERVICE_HOST = "agent-service"
DEFAULT_AGENT_SERVICE_PORT = 8000
DEFAULT_IDENTITY_SERVICE_HOST = "identity-service"
DEFAULT_IDENTITY_SERVICE_PORT = 8000
DEFAULT_AGENT_SERVICE_URL = (
    f"http://{DEFAULT_AGENT_SERVICE_HOST}:{DEFAULT_AGENT_SERVICE_PORT}"
)
DEFAULT_IDENTITY_SERVICE_URL = (
    f"http://{DEFAULT_IDENTITY_SERVICE_HOST}:{DEFAULT_IDENTITY_SERVICE_PORT}"
)
DEFAULT_IDENTITY_JWKS_URL = (
    f"http://{DEFAULT_IDENTITY_SERVICE_HOST}:{DEFAULT_IDENTITY_SERVICE_PORT}"
    "/.well-known/jwks.json"
)


@dataclass(frozen=True)
class PlatformGatewaySettings:
    agent_service_url: str = DEFAULT_AGENT_SERVICE_URL
    identity_service_url: str = DEFAULT_IDENTITY_SERVICE_URL
    identity_jwks_url: str = DEFAULT_IDENTITY_JWKS_URL
    identity_jwks_cache_seconds: int = 300
    identity_token_issuer: str = "luban-identity-broker"
    token_audience: str = "platform-gateway"
    service_client_id: str = "platform-gateway"
    service_client_secret: str = ""
    delegation_audience: str = "tool-gateway"
    workload_token_path: str = ""
    dev_signing_key_path: str = ""
    dev_user: str = "dev.operator"
    policy_path: str = ""
    chat_response_timeout_seconds: float = 30.0
    require_auth: bool = True
    audit_service_url: str = ""
    audit_client_id: str = "platform-gateway"
    audit_client_secret: str = ""

    @classmethod
    def from_env(cls) -> "PlatformGatewaySettings":
        return cls(
            agent_service_url=os.getenv(
                "AGENT_SERVICE_URL",
                DEFAULT_AGENT_SERVICE_URL,
            ),
            identity_service_url=os.getenv(
                "IDENTITY_SERVICE_URL",
                DEFAULT_IDENTITY_SERVICE_URL,
            ),
            identity_jwks_url=os.getenv(
                "IDENTITY_JWKS_URL",
                DEFAULT_IDENTITY_JWKS_URL,
            ),
            identity_jwks_cache_seconds=int(
                os.getenv("IDENTITY_JWKS_CACHE_SECONDS", "300")
            ),
            identity_token_issuer=os.getenv(
                "IDENTITY_TOKEN_ISSUER", "luban-identity-broker"
            ),
            token_audience=os.getenv(
                "PLATFORM_GATEWAY_TOKEN_AUDIENCE", "platform-gateway"
            ),
            service_client_id=os.getenv(
                "PLATFORM_GATEWAY_SERVICE_CLIENT_ID", "platform-gateway"
            ),
            service_client_secret=os.getenv(
                "PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET", ""
            ),
            delegation_audience=os.getenv(
                "PLATFORM_GATEWAY_DELEGATION_AUDIENCE", "tool-gateway"
            ),
            workload_token_path=os.getenv("PLATFORM_GATEWAY_WORKLOAD_TOKEN_PATH", ""),
            dev_signing_key_path=os.getenv("PLATFORM_GATEWAY_DEV_SIGNING_KEY_PATH", ""),
            dev_user=os.getenv("PLATFORM_GATEWAY_DEV_USER", "dev.operator"),
            policy_path=os.getenv("PLATFORM_GATEWAY_POLICY_PATH", ""),
            chat_response_timeout_seconds=float(
                os.getenv("CHAT_RESPONSE_TIMEOUT_SECONDS", "30")
            ),
            require_auth=os.getenv("PLATFORM_GATEWAY_REQUIRE_AUTH", "true")
            .strip()
            .lower()
            in {"1", "true", "yes", "on"},
            audit_service_url=os.getenv("PLATFORM_GATEWAY_AUDIT_SERVICE_URL", ""),
            audit_client_id=os.getenv(
                "PLATFORM_GATEWAY_AUDIT_CLIENT_ID", "platform-gateway"
            ),
            audit_client_secret=os.getenv(
                "PLATFORM_GATEWAY_AUDIT_CLIENT_SECRET", ""
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> PlatformGatewaySettings:
    return PlatformGatewaySettings.from_env()
