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

# Browser connector defaults (SPEC-049 R-1/R-2/R-4/R-5/R-6, SPEC-050).
DEFAULT_BROWSER_CDP_ENDPOINT = "ws://localhost:9222"
DEFAULT_BROWSER_SESSION_TTL_SECONDS = 600
DEFAULT_BROWSER_MAX_SESSIONS = 4
DEFAULT_BROWSER_FLOW_MAX_STEPS = 20
DEFAULT_BROWSER_SCREENSHOT_MAX_BYTES = 65536
DEFAULT_BROWSER_UPLOAD_DIR = "/tmp/browser-uploads"

# HTTP connector defaults (SPEC-058 R-1/R-3/R-4). Off by default with an empty
# allowlist, which denies every request (deny-by-default, R-2). The response
# cap mirrors the screenshot cap; the request cap bounds a JSON POST body.
DEFAULT_HTTP_TIMEOUT_MS = 10000
DEFAULT_HTTP_MAX_RESPONSE_BYTES = 65536
DEFAULT_HTTP_MAX_REQUEST_BYTES = 4096

# Secrets connector defaults (SPEC-062). Off by default; the delivery buffer is
# in-memory (single-replica, ephemeral) and email is unconfigured, so a cluster
# that enables nothing gains no tool and loses nothing. The delivery TTL is
# short by design — a generated value is stashed only long enough for the
# operator to click Copy — and the entry cap bounds the in-memory buffer.
DEFAULT_SECRET_DELIVERY_TTL_SECONDS = 300
DEFAULT_SECRET_DELIVERY_MAX_ENTRIES = 256
DEFAULT_SECRET_DELIVERY_REDIS_HOST = "127.0.0.1"
DEFAULT_SECRET_DELIVERY_REDIS_PORT = 6379
DEFAULT_SECRET_DELIVERY_REDIS_DB = 2
DEFAULT_EMAIL_PORT = 587

_TRUTHY = {"1", "true", "yes", "on"}


def _env_bool(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in _TRUTHY


def _env_optional_int(name: str) -> int | None:
    """Parse an optional int override; unset/blank is ``None`` (use contract)."""
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else None


def _env_optional_tuple(name: str) -> tuple[str, ...] | None:
    """Parse an optional comma list override; unset/blank is ``None``."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    return tuple(part.strip() for part in raw.split(",") if part.strip())



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
    browser_upload_dir: str = DEFAULT_BROWSER_UPLOAD_DIR
    # HTTP connector (SPEC-058): off by default; a model-supplied URL is
    # ``web.navigate``'s shape, so it inherits the browser's origin-allowlist
    # discipline (R-2). The credential-set path defaults to the browser path
    # in ``from_env`` so one mounted secret serves both surfaces.
    http_enabled: bool = False
    http_allow_origins: tuple[str, ...] = ()
    http_timeout_ms: int = DEFAULT_HTTP_TIMEOUT_MS
    http_max_response_bytes: int = DEFAULT_HTTP_MAX_RESPONSE_BYTES
    http_max_request_bytes: int = DEFAULT_HTTP_MAX_REQUEST_BYTES
    http_credential_sets_path: str = ""
    # Secrets connector (SPEC-062): off by default. ``secrets_enabled`` is the
    # discovery gate (the honest switch, mirroring ``http_enabled``); the
    # password policy path defaults to the packaged contract synced into the
    # image. The ``password_*`` overrides may only *tighten* the contract floor
    # — ``__post_init__`` raises on any override that would weaken it (R-2/R-7).
    secrets_enabled: bool = False
    password_policy_path: str = ""
    password_min_length: int | None = None
    password_required_classes: tuple[str, ...] | None = None
    password_exclude_ambiguous: bool = False
    # One-time delivery buffer (R-3): in-memory by default (single-replica,
    # ephemeral); ``redis`` is the additive backend for ``replicas > 1`` and
    # fails open to in-memory with a recorded fallback.
    secret_delivery_backend: str = "memory"
    secret_delivery_ttl_seconds: int = DEFAULT_SECRET_DELIVERY_TTL_SECONDS
    secret_delivery_max_entries: int = DEFAULT_SECRET_DELIVERY_MAX_ENTRIES
    secret_delivery_redis_host: str = DEFAULT_SECRET_DELIVERY_REDIS_HOST
    secret_delivery_redis_port: int = DEFAULT_SECRET_DELIVERY_REDIS_PORT
    secret_delivery_redis_db: int = DEFAULT_SECRET_DELIVERY_REDIS_DB
    # Email delivery channel (R-4): unconfigured by default, so ``secrets.deliver``
    # over email fails closed with ``EMAIL_NOT_CONFIGURED``. The recipient
    # allowlist is empty (deny-by-default under a strict posture); the SMTP
    # password is a secret-mounted value, never logged.
    email_host: str = ""
    email_port: int = DEFAULT_EMAIL_PORT
    email_user: str = ""
    email_password: str = ""
    email_from: str = ""
    email_use_tls: bool = True
    email_recipient_allowlist: tuple[str, ...] = ()
    email_strict_allowlist: bool = False

    def __post_init__(self) -> None:
        """Fail fast on a password-policy override that would *weaken* the floor.

        SPEC-062 R-2/R-7: env overrides may only tighten the contract. The
        canonical floor lives in ``tools/password_policy.py`` (pinned to the
        contract by the ``validate-password-policy`` leg of ``make verify``); it
        is imported lazily here so ``core.config`` carries no module-level
        dependency on the tools package. A frozen dataclass cannot assign, so a
        weakening override raises rather than being silently corrected.
        """
        if self.secret_delivery_backend not in {"memory", "redis"}:
            raise ValueError("GATEWAY_SECRET_DELIVERY_BACKEND must be memory or redis")
        for value in (self.secret_delivery_ttl_seconds, self.secret_delivery_max_entries):
            if type(value) is not int or value <= 0:
                raise ValueError("Secret delivery TTL and capacity must be positive integers")
        for port in (self.secret_delivery_redis_port, self.email_port):
            if type(port) is not int or not 1 <= port <= 65535:
                raise ValueError("Redis and SMTP ports must be between 1 and 65535")
        if self.secret_delivery_redis_db < 0:
            raise ValueError("Redis database must be nonnegative")
        if self.password_min_length is None and self.password_required_classes is None:
            return
        from tool_gateway.tools.password_policy import (
            KNOWN_CLASSES, MAX_PASSWORD_LENGTH, PasswordPolicyError, PasswordPolicyStore,
        )

        try:
            policy = PasswordPolicyStore(self.password_policy_path).default()
        except PasswordPolicyError as exc:
            raise ValueError("Cannot validate overrides without a valid password policy") from exc
        if self.password_min_length is not None:
            if (type(self.password_min_length) is not int
                    or not policy.min_length <= self.password_min_length <= MAX_PASSWORD_LENGTH):
                raise ValueError("GATEWAY_PASSWORD_MIN_LENGTH must tighten the active policy within generation bounds")
        if self.password_required_classes is not None:
            classes = self.password_required_classes
            if (not all(isinstance(c, str) and c in KNOWN_CLASSES for c in classes)
                    or len(classes) != len(set(classes))
                    or not set(policy.required_classes).issubset(classes)):
                raise ValueError("GATEWAY_PASSWORD_REQUIRED_CLASSES must retain every required class without unknowns or duplicates")

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
            browser_upload_dir=os.getenv(
                "GATEWAY_BROWSER_UPLOAD_DIR", DEFAULT_BROWSER_UPLOAD_DIR
            ),
            # HTTP connector knobs (SPEC-058). The allowlist is empty by
            # default, which denies every request (deny-by-default, R-2), and
            # the credential-set path falls back to the browser mount when
            # unset so a single synced secret serves both surfaces (R-4) —
            # no inline credential values are ever accepted.
            http_enabled=_env_bool("GATEWAY_HTTP_ENABLED", "false"),
            http_allow_origins=tuple(
                part.strip()
                for part in os.getenv("GATEWAY_HTTP_ALLOW_ORIGINS", "").split(",")
                if part.strip()
            ),
            http_timeout_ms=int(
                os.getenv(
                    "GATEWAY_HTTP_TIMEOUT_MS",
                    str(DEFAULT_HTTP_TIMEOUT_MS),
                )
            ),
            http_max_response_bytes=int(
                os.getenv(
                    "GATEWAY_HTTP_MAX_RESPONSE_BYTES",
                    str(DEFAULT_HTTP_MAX_RESPONSE_BYTES),
                )
            ),
            http_max_request_bytes=int(
                os.getenv(
                    "GATEWAY_HTTP_MAX_REQUEST_BYTES",
                    str(DEFAULT_HTTP_MAX_REQUEST_BYTES),
                )
            ),
            http_credential_sets_path=(
                os.getenv("GATEWAY_HTTP_CREDENTIAL_SETS", "")
                or os.getenv("GATEWAY_BROWSER_CREDENTIAL_SETS", "")
            ),
            # Secrets connector knobs (SPEC-062). ``secrets_enabled`` is the
            # discovery gate; the policy path defaults to the packaged contract
            # (an empty path makes the store load the synced resource). The
            # ``password_*`` overrides may only tighten — ``__post_init__``
            # raises on a weakening value. Email is unconfigured by default and
            # the recipient allowlist is empty (deny-by-default under a strict
            # posture); the SMTP password is a secret-mounted value.
            secrets_enabled=_env_bool("GATEWAY_SECRETS_ENABLED", "false"),
            password_policy_path=os.getenv("GATEWAY_PASSWORD_POLICY_PATH", ""),
            password_min_length=_env_optional_int("GATEWAY_PASSWORD_MIN_LENGTH"),
            password_required_classes=_env_optional_tuple(
                "GATEWAY_PASSWORD_REQUIRED_CLASSES"
            ),
            password_exclude_ambiguous=_env_bool(
                "GATEWAY_PASSWORD_EXCLUDE_AMBIGUOUS", "false"
            ),
            secret_delivery_backend=os.getenv(
                "GATEWAY_SECRET_DELIVERY_BACKEND", "memory"
            ).strip().lower(),
            secret_delivery_ttl_seconds=int(
                os.getenv(
                    "GATEWAY_SECRET_DELIVERY_TTL_SECONDS",
                    str(DEFAULT_SECRET_DELIVERY_TTL_SECONDS),
                )
            ),
            secret_delivery_max_entries=int(
                os.getenv(
                    "GATEWAY_SECRET_DELIVERY_MAX_ENTRIES",
                    str(DEFAULT_SECRET_DELIVERY_MAX_ENTRIES),
                )
            ),
            secret_delivery_redis_host=os.getenv(
                "GATEWAY_SECRET_DELIVERY_REDIS_HOST",
                DEFAULT_SECRET_DELIVERY_REDIS_HOST,
            ),
            secret_delivery_redis_port=int(
                os.getenv(
                    "GATEWAY_SECRET_DELIVERY_REDIS_PORT",
                    str(DEFAULT_SECRET_DELIVERY_REDIS_PORT),
                )
            ),
            secret_delivery_redis_db=int(
                os.getenv(
                    "GATEWAY_SECRET_DELIVERY_REDIS_DB",
                    str(DEFAULT_SECRET_DELIVERY_REDIS_DB),
                )
            ),
            email_host=os.getenv("GATEWAY_EMAIL_HOST", ""),
            email_port=int(
                os.getenv("GATEWAY_EMAIL_PORT", str(DEFAULT_EMAIL_PORT))
            ),
            email_user=os.getenv("GATEWAY_EMAIL_USER", ""),
            email_password=os.getenv("GATEWAY_EMAIL_PASSWORD", ""),
            email_from=os.getenv("GATEWAY_EMAIL_FROM", ""),
            email_use_tls=_env_bool("GATEWAY_EMAIL_USE_TLS", "true"),
            email_recipient_allowlist=tuple(
                part.strip()
                for part in os.getenv(
                    "GATEWAY_EMAIL_RECIPIENT_ALLOWLIST", ""
                ).split(",")
                if part.strip()
            ),
            email_strict_allowlist=_env_bool(
                "GATEWAY_EMAIL_STRICT_ALLOWLIST", "false"
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> GatewaySettings:
    return GatewaySettings.from_env()
