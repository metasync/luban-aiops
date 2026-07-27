from __future__ import annotations

import os
from dataclasses import dataclass

from identity_service.metadata import DEFAULT_HTTP_HOST, DEFAULT_HTTP_PORT


def _resolve_port(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        # Kubernetes service links can inject values like tcp://IP:PORT.
        return default


@dataclass(frozen=True)
class IdentityRunSettings:
    host: str = DEFAULT_HTTP_HOST
    port: int = DEFAULT_HTTP_PORT

    @classmethod
    def from_env(cls) -> "IdentityRunSettings":
        return cls(
            host=os.getenv("IDENTITY_SERVICE_HOST", DEFAULT_HTTP_HOST),
            port=_resolve_port(os.getenv("IDENTITY_SERVICE_PORT"), DEFAULT_HTTP_PORT),
        )
