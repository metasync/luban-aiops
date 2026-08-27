"""Frozen worker settings loaded from environment variables (SPEC-038 R-1).

The worker carries its own ``EXECUTION_*`` prefix: it owns no LLM keys,
no kernel state, and no session data — only the signing key, the static
handoff credential, the tool-gateway endpoint, and the execution-record
store knobs. Missing secrets never fail startup: the app still serves
health checks, and every handoff fails closed at the corresponding
verification step (SPEC-038 R-2).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

_SUPPORTED_STORE_BACKENDS = frozenset({"memory", "postgres"})


@dataclass(frozen=True)
class ExecutionSettings:
    """Frozen settings with startup validation (SPEC-038 R-1)."""

    execution_signing_key: str | None = None
    handoff_token: str | None = None
    tool_gateway_url: str = ""
    gateway_timeout_seconds: float = 30.0
    state_store_backend: str = "memory"
    state_db_url: str = ""
    audit_service_url: str | None = None
    audit_client_id: str = "execution-runtime"
    audit_client_secret: str | None = None
    flight_retention_seconds: int = 900

    def __post_init__(self) -> None:
        if self.gateway_timeout_seconds <= 0:
            raise ValueError("EXECUTION_GATEWAY_TIMEOUT_SECONDS must be > 0.")
        if self.state_store_backend not in _SUPPORTED_STORE_BACKENDS:
            raise ValueError(
                f"Unknown EXECUTION_STATE_STORE_BACKEND: "
                f"{self.state_store_backend!r} (expected 'memory' or 'postgres')"
            )
        if self.state_store_backend == "postgres" and not self.state_db_url:
            raise ValueError(
                "EXECUTION_STATE_STORE_BACKEND=postgres requires "
                "EXECUTION_STATE_DB_URL to be set."
            )
        if self.flight_retention_seconds < 1:
            raise ValueError("EXECUTION_FLIGHT_RETENTION_SECONDS must be >= 1.")

    @classmethod
    def from_env(cls) -> "ExecutionSettings":
        def _secret(name: str) -> str | None:
            value = (os.getenv(name) or "").strip()
            return value or None

        return cls(
            execution_signing_key=_secret("EXECUTION_SIGNING_KEY"),
            handoff_token=_secret("EXECUTION_HANDOFF_TOKEN"),
            tool_gateway_url=os.getenv("TOOL_GATEWAY_URL", "").strip(),
            gateway_timeout_seconds=float(
                os.getenv("EXECUTION_GATEWAY_TIMEOUT_SECONDS", "30")
            ),
            state_store_backend=os.getenv(
                "EXECUTION_STATE_STORE_BACKEND", "memory"
            )
            .strip()
            .lower(),
            state_db_url=os.getenv("EXECUTION_STATE_DB_URL", "").strip(),
            audit_service_url=_secret("EXECUTION_AUDIT_SERVICE_URL"),
            audit_client_id=os.getenv(
                "EXECUTION_AUDIT_CLIENT_ID", "execution-runtime"
            ),
            audit_client_secret=_secret("EXECUTION_AUDIT_CLIENT_SECRET"),
            flight_retention_seconds=int(
                os.getenv("EXECUTION_FLIGHT_RETENTION_SECONDS", "900")
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> ExecutionSettings:
    return ExecutionSettings.from_env()
