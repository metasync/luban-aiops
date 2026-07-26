from __future__ import annotations

import os
from dataclasses import dataclass

from identity_service.metadata import DEFAULT_HTTP_HOST, DEFAULT_HTTP_PORT


@dataclass(frozen=True)
class IdentityRunSettings:
    host: str = DEFAULT_HTTP_HOST
    port: int = DEFAULT_HTTP_PORT

    @classmethod
    def from_env(cls) -> "IdentityRunSettings":
        return cls(
            host=os.getenv("IDENTITY_SERVICE_HOST", DEFAULT_HTTP_HOST),
            port=int(os.getenv("IDENTITY_SERVICE_PORT", str(DEFAULT_HTTP_PORT))),
        )
