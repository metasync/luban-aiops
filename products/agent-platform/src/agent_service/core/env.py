from __future__ import annotations

import os


def get_env_value(*names: str, default: str | None) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is not None:
            return value
    return default


def get_env_int(*names: str, default: int) -> int:
    return int(get_env_value(*names, default=str(default)))
