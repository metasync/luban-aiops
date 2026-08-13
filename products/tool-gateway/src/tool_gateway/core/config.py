from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

DEFAULT_IDENTITY_SERVICE_HOST = "identity-service"
DEFAULT_IDENTITY_SERVICE_PORT = 8000
DEFAULT_IDENTITY_SERVICE_URL = (
    f"http://{DEFAULT_IDENTITY_SERVICE_HOST}:{DEFAULT_IDENTITY_SERVICE_PORT}"
)
DEFAULT_IDENTITY_JWKS_URL = (
    f"http://{DEFAULT_IDENTITY_SERVICE_HOST}:{DEFAULT_IDENTITY_SERVICE_PORT}"
    "/.well-known/jwks.json"
)


@dataclass(frozen=True)
class GatewaySettings:
    identity_service_url: str = DEFAULT_IDENTITY_SERVICE_URL
    identity_jwks_url: str = DEFAULT_IDENTITY_JWKS_URL
    identity_jwks_cache_seconds: int = 300
    identity_token_issuer: str = "luban-identity-broker"
    token_audience: str = "tool-gateway"
    dev_user: str = "dev.operator"
    policy_path: str = ""
    require_auth: bool = True
    k8s_enabled: bool = False
    k8s_namespace: str = ""
    redaction_enabled: bool = True
    redaction_overflow_fraction: float = 0.2
    elastic_enabled: bool = False
    elastic_url: str = ""
    elastic_api_key: str = ""
    elastic_username: str = ""
    elastic_password: str = ""
    elastic_verify_tls: bool = True
    elastic_alerts_index: str = ".alerts-*"
    audit_service_url: str = ""
    audit_client_id: str = "tool-gateway"
    audit_client_secret: str = ""

    @classmethod
    def from_env(cls) -> "GatewaySettings":
        return cls(
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
            dev_user=os.getenv("GATEWAY_DEV_USER", "dev.operator"),
            policy_path=os.getenv("GATEWAY_POLICY_PATH", ""),
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
            elastic_enabled=os.getenv("GATEWAY_ELASTIC_ENABLED", "false")
            .strip()
            .lower()
            in {"1", "true", "yes", "on"},
            elastic_url=os.getenv("GATEWAY_ELASTIC_URL", ""),
            elastic_api_key=os.getenv("GATEWAY_ELASTIC_API_KEY", ""),
            elastic_username=os.getenv("GATEWAY_ELASTIC_USERNAME", ""),
            elastic_password=os.getenv("GATEWAY_ELASTIC_PASSWORD", ""),
            elastic_verify_tls=os.getenv("GATEWAY_ELASTIC_VERIFY_TLS", "true")
            .strip()
            .lower()
            in {"1", "true", "yes", "on"},
            elastic_alerts_index=os.getenv(
                "GATEWAY_ELASTIC_ALERTS_INDEX", ".alerts-*"
            ),
            audit_service_url=os.getenv("GATEWAY_AUDIT_SERVICE_URL", ""),
            audit_client_id=os.getenv("GATEWAY_AUDIT_CLIENT_ID", "tool-gateway"),
            audit_client_secret=os.getenv("GATEWAY_AUDIT_CLIENT_SECRET", ""),
        )


@lru_cache(maxsize=1)
def get_settings() -> GatewaySettings:
    return GatewaySettings.from_env()
