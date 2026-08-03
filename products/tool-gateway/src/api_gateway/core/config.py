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
class GatewaySettings:
    agent_service_url: str = DEFAULT_AGENT_SERVICE_URL
    identity_service_url: str = DEFAULT_IDENTITY_SERVICE_URL
    identity_jwks_url: str = DEFAULT_IDENTITY_JWKS_URL
    identity_jwks_cache_seconds: int = 300
    identity_token_issuer: str = "luban-identity-broker"
    token_audience: str = "tool-gateway"
    service_client_id: str = ""
    service_client_secret: str = ""
    delegation_audience: str = "tool-gateway"
    workload_token_path: str = ""
    dev_signing_key_path: str = ""
    dev_user: str = "dev.operator"
    policy_path: str = ""
    chat_response_timeout_seconds: float = 30.0
    require_auth: bool = True
    k8s_enabled: bool = False
    k8s_namespace: str = ""
    redaction_enabled: bool = True
    redaction_overflow_fraction: float = 0.2

    @classmethod
    def from_env(cls) -> "GatewaySettings":
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
            token_audience=os.getenv("GATEWAY_TOKEN_AUDIENCE", "tool-gateway"),
            service_client_id=os.getenv("GATEWAY_SERVICE_CLIENT_ID", ""),
            service_client_secret=os.getenv("GATEWAY_SERVICE_CLIENT_SECRET", ""),
            delegation_audience=os.getenv("GATEWAY_DELEGATION_AUDIENCE", "tool-gateway"),
            workload_token_path=os.getenv("GATEWAY_WORKLOAD_TOKEN_PATH", ""),
            dev_signing_key_path=os.getenv("GATEWAY_DEV_SIGNING_KEY_PATH", ""),
            dev_user=os.getenv("GATEWAY_DEV_USER", "dev.operator"),
            policy_path=os.getenv("GATEWAY_POLICY_PATH", ""),
            chat_response_timeout_seconds=float(
                os.getenv("CHAT_RESPONSE_TIMEOUT_SECONDS", "30")
            ),
            require_auth=os.getenv("GATEWAY_REQUIRE_AUTH", "true").strip().lower()
            in {"1", "true", "yes", "on"},
            k8s_enabled=os.getenv("GATEWAY_K8S_ENABLED", "false").strip().lower()
            in {"1", "true", "yes", "on"},
            k8s_namespace=os.getenv("GATEWAY_K8S_NAMESPACE", ""),
            redaction_enabled=os.getenv("GATEWAY_REDACTION_ENABLED", "true")
            .strip()
            .lower()
            in {"1", "true", "yes", "on"},
            redaction_overflow_fraction=float(
                os.getenv("GATEWAY_REDACTION_OVERFLOW_FRACTION", "0.2")
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> GatewaySettings:
    return GatewaySettings.from_env()
