from __future__ import annotations

import os
from dataclasses import dataclass

from execution_runtime.metadata import DEFAULT_HTTP_HOST, DEFAULT_HTTP_PORT


def _resolve_port(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        # Kubernetes service links can inject values like tcp://IP:PORT.
        return default


@dataclass(frozen=True)
class ExecutionRunSettings:
    host: str = DEFAULT_HTTP_HOST
    port: int = DEFAULT_HTTP_PORT

    @classmethod
    def from_env(cls) -> "ExecutionRunSettings":
        return cls(
            host=os.getenv("EXECUTION_HOST", DEFAULT_HTTP_HOST),
            port=_resolve_port(os.getenv("EXECUTION_PORT"), DEFAULT_HTTP_PORT),
        )
