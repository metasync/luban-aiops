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
# that enables nothing gains no tool and loses nothing. Two TTLs bound a stashed
# value: ``secret_delivery_ttl_seconds`` (300) is the standalone redemption
# window — how long a generated value waits for the operator to click Copy —
# while ``secret_delivery_hold_ttl_seconds`` (900) is the window a portal_copy
# delivery actually stashes under. The hold spans a full HITL approval wait
# (``hitl_confirm_timeout`` 600) plus the 300 redemption margin, so a password
# generated before a gated reset is still redeemable when the reset commits and
# the reveal-on-commit Copy button appears (SPEC-062 R-3). The entry cap bounds
# the in-memory buffer.
DEFAULT_SECRET_DELIVERY_TTL_SECONDS = 300
DEFAULT_SECRET_DELIVERY_HOLD_TTL_SECONDS = 900
DEFAULT_SECRET_DELIVERY_MAX_ENTRIES = 256
DEFAULT_SECRET_DELIVERY_REDIS_HOST = "127.0.0.1"
DEFAULT_SECRET_DELIVERY_REDIS_PORT = 6379
DEFAULT_SECRET_DELIVERY_REDIS_DB = 2
DEFAULT_EMAIL_PORT = 587

# Ansible MCP-ingestion defaults (SPEC-069 R-2). Off by default; the generic,
# server-agnostic adapter is inert until a flag is enabled and an endpoint is
# wired. The streamable-HTTP transport matches AAP's read-only-mode MCP server
# (ansible/aap-mcp-server, the production target) and the in-cluster thin mock
# used for CI; ``stdio`` covers a local server process. The timeout mirrors the
# HTTP connector default.
DEFAULT_ANSIBLE_MCP_TRANSPORT = "streamable_http"
DEFAULT_ANSIBLE_MCP_TIMEOUT_MS = 10000
DEFAULT_ANSIBLE_NATIVE_EXECUTABLE = "ansible-inventory"

# ServiceNow read-tier ingestion defaults (SPEC-067 R-2). Off by default; the
# native REST/Table-API connector is inert until the flag is enabled and a base
# URL is wired (the OQ-3 fallback taken at Stage-0 2026-10-19 — the PDI exposes
# no ServiceNow MCP server). The timeout mirrors the HTTP/Ansible defaults. The
# admitted read-tool allowlist, tables, field projections, and tiers are
# gateway-owned binding config (``ingestion/servicenow_binding.py``), never
# target-advertised metadata; the credential set resolves through the SPEC-068
# seam (OQ-1 = ``oauth2_client_credentials``). No new dependency: ``httpx``.
DEFAULT_SERVICENOW_TIMEOUT_MS = 10000

# SPEC-070 delegated execution route defaults. The dedicated workload audience
# pins the private ``/api/v2/tools/invoke-delegated`` handoff to the exact
# execution-runtime projected service-account token; no public token carries it.
DEFAULT_EXECUTION_WORKLOAD_AUDIENCE = "luban-target-execution-handoff"

# SPEC-070 delegated target-authorization route defaults. A *second* dedicated
# workload audience pins the bearerless ``/api/v2/targets/authorizations``
# provider-url and callback handoffs to the exact platform-gateway projected
# service-account token, distinct from the execution-runtime audience above so
# neither handoff can replay the other's token.
DEFAULT_AUTHORIZATION_WORKLOAD_AUDIENCE = "luban-target-authorization-handoff"

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
    # fails open to in-memory with a recorded fallback. ``_ttl_seconds`` is the
    # standalone redemption window; ``_hold_ttl_seconds`` is the longer window a
    # portal_copy delivery stashes under so it survives a full approval wait
    # before the reveal-on-commit Copy button appears (see the defaults above).
    secret_delivery_backend: str = "memory"
    secret_delivery_ttl_seconds: int = DEFAULT_SECRET_DELIVERY_TTL_SECONDS
    secret_delivery_hold_ttl_seconds: int = DEFAULT_SECRET_DELIVERY_HOLD_TTL_SECONDS
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
    # Ansible MCP-ingestion connector (SPEC-069 R-2): off by default. The
    # generic, server-agnostic adapter binds a self-hosted Ansible MCP server
    # (dev) or AAP read-only mode (production) over the official ``mcp`` SDK.
    # The admitted read-only tool set + tiers are gateway-owned binding config
    # (``ingestion/ansible_binding.py``), never server-advertised metadata; the
    # adapter treats everything the server says as untrusted. The optional
    # credential set resolves through the SPEC-068 seam (a loopback sidecar
    # needs none). ``ansible_native_enabled`` is the OQ-1 fallback — a read-only
    # ``ansible-inventory`` shell-out (no ``--check``) used only when no MCP
    # server is wired; it does not prove the MCP substrate. Endpoint, inventory
    # source, and executable path are operator configuration, never model args.
    ansible_mcp_enabled: bool = False
    ansible_mcp_transport: str = DEFAULT_ANSIBLE_MCP_TRANSPORT
    ansible_mcp_url: str = ""
    ansible_mcp_command: str = ""
    ansible_mcp_args: tuple[str, ...] = ()
    ansible_mcp_timeout_ms: int = DEFAULT_ANSIBLE_MCP_TIMEOUT_MS
    ansible_mcp_credential_set: str = ""
    ansible_mcp_credential_sets_path: str = ""
    ansible_native_enabled: bool = False
    ansible_inventory_path: str = ""
    ansible_native_executable: str = DEFAULT_ANSIBLE_NATIVE_EXECUTABLE
    # ServiceNow read-tier ingestion connector (SPEC-067 R-2): off by default.
    # The native REST/Table-API connector (the OQ-3 fallback taken at Stage-0
    # 2026-10-19) admits only the six gateway-owned read tools declared in
    # ``ingestion/servicenow_binding.py`` (incident/change_request list+get,
    # user.get, cmdb_ci.get), each a fixed table with an allowlisted field
    # projection, a validated ``sys_id``, and a capped ``sysparm_limit``. The
    # bound credential set resolves through the SPEC-068 seam (OQ-1 =
    # ``oauth2_client_credentials``); it is operator config, never a model
    # argument, and no token reaches a result or log. Base URL, credential set,
    # and timeout are operator configuration, never model args.
    servicenow_enabled: bool = False
    servicenow_base_url: str = ""
    servicenow_credential_set: str = ""
    servicenow_credential_sets_path: str = ""
    servicenow_timeout_ms: int = DEFAULT_SERVICENOW_TIMEOUT_MS
    # SPEC-070 private delegated execution route (``/api/v2/tools/invoke-delegated``):
    # off by default. When enabled the route is callable only by the exact
    # execution-runtime workload identity (a projected service-account JWT with
    # the dedicated ``luban-target-execution-handoff`` audience and a subject on
    # the allowlist). Tool-gateway independently re-verifies the requester and
    # approver human bearers against the signed projection using the delegated
    # identity trust config below — the SAME issuer/audience/JWKS/actor set the
    # worker uses — then applies the existing invocation/mutation policy under
    # the approver's roles. The execution HMAC signing secret is never
    # distributed here; workload authentication alone is not execution authority.
    delegated_invoke_enabled: bool = False
    delegated_identity_issuer: str = ""
    delegated_identity_jwks_url: str = ""
    delegated_identity_audience: str = ""
    delegated_identity_actors: tuple[str, ...] = ()
    execution_workload_issuer: str = ""
    execution_workload_jwks_url: str = ""
    execution_workload_audience: str = DEFAULT_EXECUTION_WORKLOAD_AUDIENCE
    execution_workload_subjects: tuple[str, ...] = ()
    # SPEC-070 delegated *acquisition* runtime — the send-path user-delegated
    # client wired into the HTTP/MCP authentication seam (distinct from the
    # machine-grant token client, which is unchanged). Off by default: the client
    # is composed only when this gate is on AND the full Postgres-custody runtime
    # below is configured, so until database schema, versioned key mount, trusted
    # callback, and identity linkage are provisioned a delegated credential set
    # fails closed at the connector — never a machine grant, never a reauth loop.
    # The custody store is per-set; one administered delegated target set is wired.
    delegated_acquisition_enabled: bool = False
    delegated_custody_db_url: str = ""
    delegated_custody_keyring_path: str = ""
    delegated_custody_config_path: str = ""
    delegated_custody_set_id: str = ""
    delegated_custody_trusted_callback: str = ""
    # SPEC-070 delegated target-authorization workflow — the human-initiated
    # ``/api/v2/targets/authorizations`` routes (start/provider-url/callback/
    # status/cancel/browser-reset) that enroll and renew a user-delegated grant.
    # Off by default and *independent* of ``delegated_acquisition_enabled``: the
    # send path can be provisioned without the enrollment portal and vice versa,
    # but both compose over the same Postgres custody runtime above. Enabling
    # requires (validated in ``__post_init__``) the full Postgres custody runtime,
    # the delegated-human trust set (shared with the execution route — the
    # owner_namespace is pinned to ``delegated_identity_issuer``), AND a separate
    # authorization-workload trust set whose dedicated audience pins the
    # bearerless provider-url/callback handoffs to the exact platform-gateway
    # projected service-account token. The human edges reject permissive
    # development minting; the workload edges take no Basic/static fallback.
    delegated_authorization_enabled: bool = False
    authorization_workload_issuer: str = ""
    authorization_workload_jwks_url: str = ""
    authorization_workload_audience: str = DEFAULT_AUTHORIZATION_WORKLOAD_AUDIENCE
    authorization_workload_subjects: tuple[str, ...] = ()

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
        if self.delegated_invoke_enabled:
            self._validate_delegated_invoke()
        if self.delegated_acquisition_enabled:
            self._validate_delegated_acquisition()
        if self.delegated_authorization_enabled:
            self._validate_delegated_authorization()
        for value in (
            self.secret_delivery_ttl_seconds,
            self.secret_delivery_hold_ttl_seconds,
            self.secret_delivery_max_entries,
        ):
            if type(value) is not int or value <= 0:
                raise ValueError("Secret delivery TTL and capacity must be positive integers")
        for port in (self.secret_delivery_redis_port, self.email_port):
            if type(port) is not int or not 1 <= port <= 65535:
                raise ValueError("Redis and SMTP ports must be between 1 and 65535")
        if self.secret_delivery_redis_db < 0:
            raise ValueError("Redis database must be nonnegative")
        if self.ansible_mcp_transport not in {"streamable_http", "stdio"}:
            raise ValueError(
                "GATEWAY_ANSIBLE_MCP_TRANSPORT must be streamable_http or stdio"
            )
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

    def _validate_delegated_invoke(self) -> None:
        """Fail closed when the private delegated route is enabled but untrusted.

        SPEC-070: enabling ``GATEWAY_DELEGATED_INVOKE_ENABLED`` requires an
        explicit delegated-human trust set (issuer/audience/JWKS + a nonempty
        actor allowlist) AND an explicit execution-workload trust set
        (issuer/audience/JWKS + a nonempty subject allowlist). A missing or
        unbounded value aborts startup rather than degrading to an
        anything-goes route.
        """
        def _bounded(value: object) -> bool:
            return (
                isinstance(value, str) and 0 < len(value) <= 256
                and value == value.strip()
                and not any(ord(char) < 32 or ord(char) == 127 for char in value)
            )

        def _http_url(value: str) -> bool:
            from urllib.parse import urlsplit

            url = urlsplit(value or "")
            return (
                url.scheme in {"http", "https"} and bool(url.hostname)
                and url.username is None and url.password is None
                and not url.query and not url.fragment
            )

        if not (_bounded(self.delegated_identity_issuer)
                and _bounded(self.delegated_identity_audience)
                and _http_url(self.delegated_identity_jwks_url)
                and self.delegated_identity_actors
                and all(_bounded(actor) for actor in self.delegated_identity_actors)):
            raise ValueError(
                "GATEWAY_DELEGATED_INVOKE_ENABLED requires explicit delegated "
                "identity trust (issuer, audience, JWKS URL, actor allowlist)"
            )
        if not (_bounded(self.execution_workload_issuer)
                and _bounded(self.execution_workload_audience)
                and _http_url(self.execution_workload_jwks_url)
                and self.execution_workload_subjects
                and all(_bounded(sub) for sub in self.execution_workload_subjects)):
            raise ValueError(
                "GATEWAY_DELEGATED_INVOKE_ENABLED requires explicit execution "
                "workload trust (issuer, audience, JWKS URL, subject allowlist)"
            )

    def _validate_delegated_acquisition(self) -> None:
        """Fail closed when delegated acquisition is enabled but unprovisioned.

        SPEC-070 (plan §"Runtime composition and bounds"): the send-path
        user-delegated client requires Postgres custody state and a versioned key
        mount. Enabling ``GATEWAY_DELEGATED_ACQUISITION_ENABLED`` therefore
        requires an explicit Postgres DSN, keyring path, delegated config path,
        set id, and a trusted HTTPS callback whose path is the ratified
        ``CALLBACK_PATH``. Missing infrastructure is a startup configuration
        error — never a runtime reauthorization loop and never a silent fall-back
        to a machine grant. ``CALLBACK_PATH`` is imported lazily so ``core.config``
        keeps no module-level dependency on the tools package.
        """
        from urllib.parse import urlsplit

        from tool_gateway.tools.delegated_configuration import CALLBACK_PATH

        def _bounded(value: object) -> bool:
            return (
                isinstance(value, str) and 0 < len(value) <= 1024
                and value == value.strip()
                and not any(ord(char) < 32 or ord(char) == 127 for char in value)
            )

        dsn = urlsplit(self.delegated_custody_db_url or "")
        callback = urlsplit(self.delegated_custody_trusted_callback or "")
        if not (
            dsn.scheme in {"postgres", "postgresql"}
            and bool(dsn.hostname)
            and _bounded(self.delegated_custody_keyring_path)
            and _bounded(self.delegated_custody_config_path)
            and _bounded(self.delegated_custody_set_id)
            and callback.scheme == "https"
            and bool(callback.hostname)
            and callback.path == CALLBACK_PATH
            and not callback.query
        ):
            raise ValueError(
                "GATEWAY_DELEGATED_ACQUISITION_ENABLED requires explicit Postgres "
                "custody runtime (DSN, keyring path, config path, set id, trusted "
                "HTTPS callback)"
            )

    def _validate_delegated_authorization(self) -> None:
        """Fail closed when the authorization workflow is enabled but untrusted.

        SPEC-070 OQ-7: the human-initiated ``/api/v2/targets/authorizations``
        routes enroll and renew a durable grant, so enabling
        ``GATEWAY_DELEGATED_AUTHORIZATION_ENABLED`` requires all three legs at
        startup — the same Postgres custody runtime as acquisition (DSN, keyring,
        config path, set id, trusted HTTPS callback on the ratified
        ``CALLBACK_PATH``), the delegated-human trust set that pins
        ``owner_namespace`` to ``delegated_identity_issuer`` (issuer, audience,
        JWKS URL, nonempty actor allowlist), and a *separate*
        authorization-workload trust set whose dedicated audience pins the
        bearerless provider-url/callback handoffs (issuer, audience, JWKS URL,
        nonempty subject allowlist). A missing or unbounded value aborts startup
        rather than degrading to an anything-goes enrollment surface; the human
        edges never accept permissive development minting and the workload edges
        never fall back to Basic/static auth.
        """
        from urllib.parse import urlsplit

        from tool_gateway.tools.delegated_configuration import CALLBACK_PATH

        def _bounded(value: object, maximum: int = 256) -> bool:
            return (
                isinstance(value, str) and 0 < len(value) <= maximum
                and value == value.strip()
                and not any(ord(char) < 32 or ord(char) == 127 for char in value)
            )

        def _http_url(value: str) -> bool:
            url = urlsplit(value or "")
            return (
                url.scheme in {"http", "https"} and bool(url.hostname)
                and url.username is None and url.password is None
                and not url.query and not url.fragment
            )

        dsn = urlsplit(self.delegated_custody_db_url or "")
        callback = urlsplit(self.delegated_custody_trusted_callback or "")
        if not (
            dsn.scheme in {"postgres", "postgresql"}
            and bool(dsn.hostname)
            and _bounded(self.delegated_custody_keyring_path, 1024)
            and _bounded(self.delegated_custody_config_path, 1024)
            and _bounded(self.delegated_custody_set_id, 1024)
            and callback.scheme == "https"
            and bool(callback.hostname)
            and callback.path == CALLBACK_PATH
            and not callback.query
        ):
            raise ValueError(
                "GATEWAY_DELEGATED_AUTHORIZATION_ENABLED requires explicit Postgres "
                "custody runtime (DSN, keyring path, config path, set id, trusted "
                "HTTPS callback)"
            )
        if not (_bounded(self.delegated_identity_issuer)
                and _bounded(self.delegated_identity_audience)
                and _http_url(self.delegated_identity_jwks_url)
                and self.delegated_identity_actors
                and all(_bounded(actor) for actor in self.delegated_identity_actors)):
            raise ValueError(
                "GATEWAY_DELEGATED_AUTHORIZATION_ENABLED requires explicit delegated "
                "identity trust (issuer, audience, JWKS URL, actor allowlist)"
            )
        if not (_bounded(self.authorization_workload_issuer)
                and _bounded(self.authorization_workload_audience)
                and _http_url(self.authorization_workload_jwks_url)
                and self.authorization_workload_subjects
                and all(_bounded(sub) for sub in self.authorization_workload_subjects)):
            raise ValueError(
                "GATEWAY_DELEGATED_AUTHORIZATION_ENABLED requires explicit "
                "authorization workload trust (issuer, audience, JWKS URL, subject "
                "allowlist)"
            )

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
            secret_delivery_hold_ttl_seconds=int(
                os.getenv(
                    "GATEWAY_SECRET_DELIVERY_HOLD_TTL_SECONDS",
                    str(DEFAULT_SECRET_DELIVERY_HOLD_TTL_SECONDS),
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
            # Ansible MCP-ingestion knobs (SPEC-069 R-2). Off by default; the
            # credential-set path falls back to the http/browser mount so one
            # synced secret can serve it, and no inline credential value is ever
            # accepted. Transport is validated in ``__post_init__``.
            ansible_mcp_enabled=_env_bool("GATEWAY_ANSIBLE_MCP_ENABLED", "false"),
            ansible_mcp_transport=os.getenv(
                "GATEWAY_ANSIBLE_MCP_TRANSPORT", DEFAULT_ANSIBLE_MCP_TRANSPORT
            ).strip().lower(),
            ansible_mcp_url=os.getenv("GATEWAY_ANSIBLE_MCP_URL", ""),
            ansible_mcp_command=os.getenv("GATEWAY_ANSIBLE_MCP_COMMAND", ""),
            ansible_mcp_args=_env_optional_tuple("GATEWAY_ANSIBLE_MCP_ARGS") or (),
            ansible_mcp_timeout_ms=int(
                os.getenv(
                    "GATEWAY_ANSIBLE_MCP_TIMEOUT_MS",
                    str(DEFAULT_ANSIBLE_MCP_TIMEOUT_MS),
                )
            ),
            ansible_mcp_credential_set=os.getenv(
                "GATEWAY_ANSIBLE_MCP_CREDENTIAL_SET", ""
            ),
            ansible_mcp_credential_sets_path=(
                os.getenv("GATEWAY_ANSIBLE_MCP_CREDENTIAL_SETS", "")
                or os.getenv("GATEWAY_HTTP_CREDENTIAL_SETS", "")
                or os.getenv("GATEWAY_BROWSER_CREDENTIAL_SETS", "")
            ),
            ansible_native_enabled=_env_bool(
                "GATEWAY_ANSIBLE_NATIVE_ENABLED", "false"
            ),
            ansible_inventory_path=os.getenv("GATEWAY_ANSIBLE_INVENTORY_PATH", ""),
            ansible_native_executable=os.getenv(
                "GATEWAY_ANSIBLE_NATIVE_EXECUTABLE",
                DEFAULT_ANSIBLE_NATIVE_EXECUTABLE,
            ),
            # ServiceNow read-tier ingestion knobs (SPEC-067 R-2). Off by
            # default; the credential-set path falls back to the http/browser
            # mount so one synced secret can serve it, and no inline credential
            # value is ever accepted (the set is a file path reference only).
            servicenow_enabled=_env_bool("GATEWAY_SERVICENOW_ENABLED", "false"),
            servicenow_base_url=os.getenv("GATEWAY_SERVICENOW_BASE_URL", ""),
            servicenow_credential_set=os.getenv(
                "GATEWAY_SERVICENOW_CREDENTIAL_SET", ""
            ),
            servicenow_credential_sets_path=(
                os.getenv("GATEWAY_SERVICENOW_CREDENTIAL_SETS", "")
                or os.getenv("GATEWAY_HTTP_CREDENTIAL_SETS", "")
                or os.getenv("GATEWAY_BROWSER_CREDENTIAL_SETS", "")
            ),
            servicenow_timeout_ms=int(
                os.getenv(
                    "GATEWAY_SERVICENOW_TIMEOUT_MS",
                    str(DEFAULT_SERVICENOW_TIMEOUT_MS),
                )
            ),
            # SPEC-070 private delegated execution route knobs. Off by default;
            # enabling requires the full delegated-human and execution-workload
            # trust sets (validated in ``__post_init__``). The workload audience
            # defaults to the dedicated handoff audience; the allowlists are
            # empty (deny-by-default) so an enabled-but-unconfigured route fails
            # closed at startup rather than admitting any caller.
            delegated_invoke_enabled=_env_bool(
                "GATEWAY_DELEGATED_INVOKE_ENABLED", "false"
            ),
            delegated_identity_issuer=os.getenv(
                "GATEWAY_DELEGATED_IDENTITY_ISSUER", ""
            ),
            delegated_identity_jwks_url=os.getenv(
                "GATEWAY_DELEGATED_IDENTITY_JWKS_URL", ""
            ),
            delegated_identity_audience=os.getenv(
                "GATEWAY_DELEGATED_IDENTITY_AUDIENCE", ""
            ),
            delegated_identity_actors=_env_optional_tuple(
                "GATEWAY_DELEGATED_IDENTITY_ACTORS"
            ) or (),
            execution_workload_issuer=os.getenv(
                "GATEWAY_EXECUTION_WORKLOAD_ISSUER", ""
            ),
            execution_workload_jwks_url=os.getenv(
                "GATEWAY_EXECUTION_WORKLOAD_JWKS_URL", ""
            ),
            execution_workload_audience=os.getenv(
                "GATEWAY_EXECUTION_WORKLOAD_AUDIENCE",
                DEFAULT_EXECUTION_WORKLOAD_AUDIENCE,
            ),
            execution_workload_subjects=_env_optional_tuple(
                "GATEWAY_EXECUTION_WORKLOAD_SUBJECTS"
            ) or (),
            # SPEC-070 delegated *acquisition* runtime (the send-path
            # user-delegated client). Off by default; enabling requires the full
            # Postgres-custody runtime (validated in ``__post_init__``) so an
            # enabled-but-unprovisioned gateway fails closed at startup rather
            # than composing a client with no durable custody authority.
            delegated_acquisition_enabled=_env_bool(
                "GATEWAY_DELEGATED_ACQUISITION_ENABLED", "false"
            ),
            delegated_custody_db_url=os.getenv(
                "GATEWAY_DELEGATED_CUSTODY_DB_URL", ""
            ),
            delegated_custody_keyring_path=os.getenv(
                "GATEWAY_DELEGATED_CUSTODY_KEYRING_PATH", ""
            ),
            delegated_custody_config_path=os.getenv(
                "GATEWAY_DELEGATED_CUSTODY_CONFIG_PATH", ""
            ),
            delegated_custody_set_id=os.getenv(
                "GATEWAY_DELEGATED_CUSTODY_SET_ID", ""
            ),
            delegated_custody_trusted_callback=os.getenv(
                "GATEWAY_DELEGATED_CUSTODY_TRUSTED_CALLBACK", ""
            ),
            # SPEC-070 delegated target-authorization workflow knobs. Off by
            # default and independent of the acquisition gate; enabling requires
            # the full Postgres custody runtime (reused above), the delegated
            # human trust set (reused above), AND the separate authorization
            # workload trust set below (validated in ``__post_init__``). The
            # workload audience defaults to the dedicated handoff audience and
            # the subject allowlist is empty (deny-by-default), so an
            # enabled-but-unconfigured route fails closed at startup rather than
            # admitting any bearerless caller.
            delegated_authorization_enabled=_env_bool(
                "GATEWAY_DELEGATED_AUTHORIZATION_ENABLED", "false"
            ),
            authorization_workload_issuer=os.getenv(
                "GATEWAY_AUTHORIZATION_WORKLOAD_ISSUER", ""
            ),
            authorization_workload_jwks_url=os.getenv(
                "GATEWAY_AUTHORIZATION_WORKLOAD_JWKS_URL", ""
            ),
            authorization_workload_audience=os.getenv(
                "GATEWAY_AUTHORIZATION_WORKLOAD_AUDIENCE",
                DEFAULT_AUTHORIZATION_WORKLOAD_AUDIENCE,
            ),
            authorization_workload_subjects=_env_optional_tuple(
                "GATEWAY_AUTHORIZATION_WORKLOAD_SUBJECTS"
            ) or (),
        )


@lru_cache(maxsize=1)
def get_settings() -> GatewaySettings:
    return GatewaySettings.from_env()
