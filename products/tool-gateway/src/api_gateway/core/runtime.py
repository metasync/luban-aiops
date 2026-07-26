from __future__ import annotations

import os
from dataclasses import dataclass

from api_gateway.metadata import DEFAULT_HTTP_HOST, DEFAULT_HTTP_PORT


@dataclass(frozen=True)
class GatewayRunSettings:
    host: str = DEFAULT_HTTP_HOST
    port: int = DEFAULT_HTTP_PORT

    @classmethod
    def from_env(cls) -> "GatewayRunSettings":
        return cls(
            host=os.getenv("API_GATEWAY_HOST", DEFAULT_HTTP_HOST),
            port=int(os.getenv("API_GATEWAY_PORT", str(DEFAULT_HTTP_PORT))),
        )
