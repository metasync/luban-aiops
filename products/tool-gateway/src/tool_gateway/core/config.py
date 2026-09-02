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

# Browser connector defaults (SPEC-049 R-1/R-2/R-4/R-5/R-6).
DEFAULT_BROWSER_CDP_ENDPOINT = "ws://localhost:9222"
DEFAULT_BROWSER_SESSION_TTL_SECONDS = 600
DEFAULT_BROWSER_MAX_SESSIONS = 4
DEFAULT_BROWSER_FLOW_MAX_STEPS = 20
DEFAULT_BROWSER_SCREENSHOT_MAX_BYTES = 65536

_TRUTHY = {"1", "true", "yes", "on"}


def _env_bool(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in _TRUTHY


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
    mutating_tools_enabled: bool = False
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
    skills_service_url: str = ""
    skills_client_id: str = "tool-gateway"
    skills_client_secret: str = ""
    incidents_service_url: str = ""
    incidents_client_id: str = "tool-gateway"
    incidents_client_secret: str = ""
    # Browser connector (SPEC-049): off by default; the engine rides a
    # chromium-headless-shell sidecar reached over CDP (D-6).
    browser_enabled: bool = False
    browser_cdp_endpoint: str = DEFAULT_BROWSER_CDP_ENDPOINT
    browser_session_ttl_seconds: int = DEFAULT_BROWSER_SESSION_TTL_SECONDS
    browser_max_sessions: int = DEFAULT_BROWSER_MAX_SESSIONS
    browser_allow_origins: tuple[str, ...] = ()
    browser_flow_max_steps: int = DEFAULT_BROWSER_FLOW_MAX_STEPS
    browser_credential_sets_path: str = ""
    browser_screenshot_max_bytes: int = DEFAULT_BROWSER_SCREENSHOT_MAX_BYTES

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
            mutating_tools_enabled=os.getenv(
                "GATEWAY_MUTATING_TOOLS_ENABLED", "false"
            )
            .strip()
            .lower()
            in {"1", "true", "yes", "on"},
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
            skills_service_url=os.getenv("GATEWAY_SKILLS_SERVICE_URL", ""),
            skills_client_id=os.getenv("GATEWAY_SKILLS_CLIENT_ID", "tool-gateway"),
            skills_client_secret=os.getenv("GATEWAY_SKILLS_CLIENT_SECRET", ""),
            incidents_service_url=os.getenv("GATEWAY_INCIDENTS_SERVICE_URL", ""),
            incidents_client_id=os.getenv(
                "GATEWAY_INCIDENTS_CLIENT_ID", "tool-gateway"
            ),
            incidents_client_secret=os.getenv(
                "GATEWAY_INCIDENTS_CLIENT_SECRET", ""
            ),
            # Browser connector knobs (SPEC-049). The allowlist is empty by
            # default, which denies all navigation (deny-by-default, R-2);
            # the credential-set knob is a secret-mounted file path only —
            # no inline credential values are ever accepted (R-5).
            browser_enabled=_env_bool("GATEWAY_BROWSER_ENABLED", "false"),
            browser_cdp_endpoint=os.getenv(
                "GATEWAY_BROWSER_CDP_ENDPOINT", DEFAULT_BROWSER_CDP_ENDPOINT
            ),
            browser_session_ttl_seconds=int(
                os.getenv(
                    "GATEWAY_BROWSER_SESSION_TTL",
                    str(DEFAULT_BROWSER_SESSION_TTL_SECONDS),
                )
            ),
            browser_max_sessions=int(
                os.getenv(
                    "GATEWAY_BROWSER_MAX_SESSIONS",
                    str(DEFAULT_BROWSER_MAX_SESSIONS),
                )
            ),
            browser_allow_origins=tuple(
                part.strip()
                for part in os.getenv("GATEWAY_BROWSER_ALLOW_ORIGINS", "").split(",")
                if part.strip()
            ),
            browser_flow_max_steps=int(
                os.getenv(
                    "GATEWAY_BROWSER_FLOW_MAX_STEPS",
                    str(DEFAULT_BROWSER_FLOW_MAX_STEPS),
                )
            ),
            browser_credential_sets_path=os.getenv(
                "GATEWAY_BROWSER_CREDENTIAL_SETS", ""
            ),
            browser_screenshot_max_bytes=int(
                os.getenv(
                    "GATEWAY_BROWSER_SCREENSHOT_MAX_BYTES",
                    str(DEFAULT_BROWSER_SCREENSHOT_MAX_BYTES),
                )
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> GatewaySettings:
    return GatewaySettings.from_env()
